"""Confirmed canonical Household replay, archive and deletion regressions."""

import pytest
from argus.domain.household.errors import HouseholdNotFound
from argus.domain.household.financial import HouseholdFinancialService
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.errors import StaleVersion
from argus.domain.recording.schemas import EditFinancialAccountRequest
from argus.domain.recording.service import FinancialAccountService

from tests.household.financial_fixtures import (
    DSN,
    account,
    command,
    expense,
    key,
    reviewed,
    setup,
    share,
)

pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL required")


@pytest.mark.parametrize("ending", ["withdraw", "leave", "rejoin"])
def test_committed_retry_ignores_unrelated_generation_but_requires_live_incarnation(
    lane, ending
):
    service, records, (owner, recipient, _) = lane
    hid, membership, _ = setup(lane)
    aid = account(records, owner)
    share(service, owner, hid, aid, membership, "edit")
    version = service.get(user_id=recipient, household_id=hid).version
    body = reviewed(service, recipient, hid, expense(aid))
    token = key()
    financial = HouseholdFinancialService(service)

    def post(receipt_key=token):
        return financial.money(
            recipient,
            hid,
            body,
            key=receipt_key,
            membership_id=membership,
            expected_household_version=version,
        )

    first = post()
    command(
        service,
        owner,
        "invite",
        lambda: service.invite(user_id=owner, household_id=hid),
        hid,
    )
    assert service.get(user_id=recipient, household_id=hid).version > version
    replay = post()
    assert replay["replayed"]
    assert (
        replay["activity"]["activity"]["activity_id"]
        == first["activity"]["activity"]["activity_id"]
    )
    for new_key in [None, key()]:
        with pytest.raises(StaleVersion):
            post(new_key)

    if ending == "withdraw":
        command(
            service,
            owner,
            "withdraw",
            lambda: service.replace_grants(
                user_id=owner, household_id=hid, account_id=aid, recipients=[]
            ),
            hid,
        )
    else:
        command(
            service,
            recipient,
            "leave",
            lambda: service.leave(user_id=recipient, household_id=hid),
            hid,
        )
        if ending == "rejoin":
            invite = command(
                service,
                owner,
                "invite",
                lambda: service.invite(user_id=owner, household_id=hid),
                hid,
            ).invitation
            new = service.accept(user_id=recipient, token=invite.token)
            assert new.membership_id != membership
            share(service, owner, hid, aid, new.membership_id, "edit")
    with pytest.raises(HouseholdNotFound):
        post()
    stored = records.get_account(user_id=owner, account_id=aid, scope=PERSONAL)
    assert len(stored.expenses) == 1
    assert stored.expenses[0].current.recorded_by == recipient


def test_archived_granted_cash_debt_and_unknown_keep_positions_on_restore(lane):
    service, records, (owner, recipient, _) = lane
    hid, membership, _ = setup(lane)
    ids = [
        account(records, owner, 1000, kind="cash"),
        account(records, owner, -200, kind="other_debt"),
        account(records, owner, None, currency="USD", kind="cash"),
    ]
    for aid in ids:
        share(service, owner, hid, aid, membership)
    financial = HouseholdFinancialService(service)
    expected = [
        {
            "currency": "DOP",
            "currency_fraction_digits": 2,
            "amount_minor": 80000,
            "unknown_count": 0,
        },
        {
            "currency": "USD",
            "currency_fraction_digits": 2,
            "amount_minor": 0,
            "unknown_count": 1,
        },
    ]
    assert financial.snapshot(recipient, hid)["positions"] == expected
    accounts = FinancialAccountService(records)
    for archived in [True, False]:
        for aid in ids:
            current = records.get_account(user_id=owner, account_id=aid, scope=PERSONAL)
            accounts.edit(
                user_id=owner,
                account_id=aid,
                request=EditFinancialAccountRequest(
                    expected_version=current.account.version, archived=archived
                ),
                scope=PERSONAL,
            )
        snapshot = financial.snapshot(recipient, hid)
        assert snapshot["positions"] == expected
        assert len(snapshot["accounts"]) == len(ids)
        assert all(
            item["account"]["archived"] == archived for item in snapshot["accounts"]
        )


@pytest.mark.parametrize("ending", ["leave", "close"])
def test_recipient_auth_deletion_removes_grants_and_preserves_owner_financial_history(
    lane, ending
):
    service, records, (owner, recipient, _) = lane
    hid, membership, _ = setup(lane)
    aid = account(records, owner)
    share(service, owner, hid, aid, membership, "edit")
    body = reviewed(service, recipient, hid, expense(aid))
    financial = HouseholdFinancialService(service)
    result = financial.money(
        recipient,
        hid,
        body,
        key=key(),
        membership_id=membership,
        expected_household_version=service.get(
            user_id=recipient, household_id=hid
        ).version,
    )
    activity_id = result["activity"]["activity"]["activity_id"]
    actor = recipient if ending == "leave" else owner
    command(
        service,
        actor,
        ending,
        (lambda: service.leave(user_id=recipient, household_id=hid))
        if ending == "leave"
        else (lambda: service.close(user_id=owner, household_id=hid)),
        hid,
    )
    with service._repository.connection() as c, c.transaction():
        assert (
            c.execute(
                "select count(*) from household_account_grants where household_id=%s and recipient_membership_id=%s and revoked_at is not null",
                (hid, membership),
            ).fetchone()[0]
            == 1
        )
        c.execute("delete from auth.users where id=%s", (recipient,))
        assert (
            c.execute(
                "select count(*) from household_account_grants where household_id=%s",
                (hid,),
            ).fetchone()[0]
            == 0
        )
        assert (
            c.execute(
                "select count(*) from household_members where user_id=%s", (recipient,)
            ).fetchone()[0]
            == 0
        )
    stored = records.get_account(user_id=owner, account_id=aid, scope=PERSONAL)
    assert stored.account.user_id == owner
    assert stored.opening.current.amount_minor == 100000
    assert len(stored.expenses) == 1
    assert stored.expenses[0].current.activity_id == activity_id
    assert stored.expenses[0].current.amount_minor == 2500
    assert stored.expenses[0].current.recorded_by is None
