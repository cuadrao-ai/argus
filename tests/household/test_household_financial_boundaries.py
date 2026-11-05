"""Financial security boundaries through the canonical Household adapter."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from argus.domain.household.errors import HouseholdNotFound as HouseholdUnavailable
from argus.domain.household.errors import HouseholdRule, InvitationConsumed
from argus.domain.household.financial import HouseholdFinancialService
from argus.domain.household.financial_schemas import Snapshot
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.errors import IdempotencyConflict, StaleVersion
from argus.domain.recording.money_schemas import MoneyRequest
from argus.domain.recording.money_service import MoneyService
from argus.domain.recording.service import FinancialAccountService
from psycopg.errors import InsufficientPrivilege

from tests.household.financial_fixtures import (
    DSN,
    NOW,
    account,
    command,
    expense,
    key,
    reviewed,
    setup,
    share,
)

pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL required")


def stored_account(records, owner, amount=1000, **kwargs):
    aid = account(records, owner, amount, **kwargs)
    return records.get_account(user_id=owner, account_id=aid, scope=PERSONAL)


def scoped_money(
    financial, actor, hid, body, aid=None, *, k=None, member=None, version=None
):
    h = financial.households.get(user_id=actor, household_id=hid)
    return financial.money(
        actor,
        hid,
        body,
        aid,
        k,
        membership_id=member or h.membership_id,
        expected_household_version=version or h.version,
    )


def withdraw(service, owner, hid, aid, version=None):
    return command(
        service,
        owner,
        "withdraw:" + aid,
        lambda: service.replace_grants(
            user_id=owner, household_id=hid, account_id=aid, recipients=[]
        ),
        hid,
        None if version is None else {"expected_version": version},
    )


def test_projection_hides_linked_accounts_and_search_never_matches_private_records(lane):
    service, records, (a, b, _) = lane
    financial = HouseholdFinancialService(service)
    hid, mid, _ = setup(lane)
    visible = stored_account(records, a)
    hidden = stored_account(records, a)
    money = MoneyService(FinancialAccountService(records, clock=lambda: NOW))
    request = MoneyRequest(
        kind="transfer",
        source_account_id=visible.account.id,
        destination_account_id=hidden.account.id,
        amount="20",
        occurred_at=NOW - timedelta(days=1),
        time_zone="UTC",
    )
    preview = money.preview(user_id=a, request=request, scope=PERSONAL)
    request = MoneyRequest.model_validate(
        preview["reviewed_request"] | {"preview_token": preview["preview_token"]}
    )
    receipt = money.write(
        user_id=a, request=request, idempotency_key=key(), scope=PERSONAL
    )
    share(service, a, hid, visible.account.id, mid, "edit")
    snap = financial.snapshot(b, hid)
    Snapshot.model_validate(snap)
    encoded = json.dumps(snap, default=str)
    assert hidden.account.id not in encoded
    assert snap["activities"][0]["private_counterpart"]
    assert not snap["activities"][0]["can_edit"]
    assert len(snap["activities"][0]["activity"]["legs"]) == 1
    assert financial.search(b, hid, hidden.account.nickname, None, 10)["items"] == []
    with pytest.raises(HouseholdUnavailable):
        financial.detail(b, hid, hidden.account.id)
    correction = request.model_copy(
        update={
            "amount": "15",
            "reason": "Correction",
            "expected_revision": 1,
            "expected_versions": {},
            "preview_token": None,
        }
    )
    with pytest.raises(HouseholdUnavailable):
        scoped_money(financial, b, hid, correction, receipt["activity"]["activity_id"])


def test_reverse_refund_dependency_is_checked_before_private_limits(lane):
    service, records, (a, b, _) = lane
    financial = HouseholdFinancialService(service)
    hid, mid, _ = setup(lane)
    visible = stored_account(records, a)
    hidden = stored_account(records, a)
    money = MoneyService(FinancialAccountService(records, clock=lambda: NOW))

    def post(body):
        p = money.preview(user_id=a, request=body, scope=PERSONAL)
        return money.write(
            user_id=a,
            request=MoneyRequest.model_validate(
                p["reviewed_request"] | {"preview_token": p["preview_token"]}
            ),
            idempotency_key=key(),
            scope=PERSONAL,
        )

    purchase = post(expense(visible.account.id))
    aid = purchase["activity"]["activity_id"]
    post(
        MoneyRequest(
            kind="refund",
            account_id=hidden.account.id,
            amount="5",
            occurred_at=NOW,
            time_zone="UTC",
            purchase_activity_id=aid,
        )
    )
    share(service, a, hid, visible.account.id, mid, "edit")
    request = expense(visible.account.id, "1").model_copy(
        update={"expected_revision": 1, "reason": "Correction"}
    )
    with pytest.raises(HouseholdUnavailable):
        scoped_money(financial, b, hid, request, aid)


@pytest.mark.parametrize(
    "kind,target_kind",
    [
        ("transfer", "checking"),
        ("card_payment", "credit_card"),
        ("debt_payment", "other_debt"),
    ],
)
@pytest.mark.parametrize("visible_role", ["source", "destination"])
def test_partial_paired_history_never_promotes_destination_to_total(
    lane, kind, target_kind, visible_role
):
    service, records, (a, b, _) = lane
    financial = HouseholdFinancialService(service)
    hid, mid, _ = setup(lane)
    source = stored_account(records, a)
    dest = stored_account(records, a, kind=target_kind)
    money = MoneyService(FinancialAccountService(records, clock=lambda: NOW))
    request = MoneyRequest(
        kind=kind,
        source_account_id=source.account.id,
        destination_account_id=dest.account.id,
        amount="110",
        principal="100" if kind == "debt_payment" else None,
        interest="8" if kind == "debt_payment" else None,
        fees="2" if kind == "debt_payment" else None,
        occurred_at=NOW - timedelta(days=1),
        time_zone="UTC",
    )
    p = money.preview(user_id=a, request=request, scope=PERSONAL)
    receipt = money.write(
        user_id=a,
        request=MoneyRequest.model_validate(
            p["reviewed_request"] | {"preview_token": p["preview_token"]}
        ),
        idempotency_key=key(),
        scope=PERSONAL,
    )
    visible = source if visible_role == "source" else dest
    hidden = dest if visible_role == "source" else source
    share(service, a, hid, visible.account.id, mid)
    snap = financial.snapshot(b, hid)
    Snapshot.model_validate(snap)
    result = snap["activities"][0]["activity"]
    assert result["amount_minor"] == (11000 if visible_role == "source" else None)
    assert result["principal_minor"] is None and result["fees_minor"] is None
    assert hidden.account.id not in json.dumps(snap, default=str)
    history = financial.history(b, hid, receipt["activity"]["activity_id"])
    assert history["items"][0]["activity"]["amount_minor"] == result["amount_minor"]


def test_historical_reassignment_redacts_old_and_current_legs(lane):
    service, records, (a, b, _) = lane
    financial = HouseholdFinancialService(service)
    hid, mid, _ = setup(lane)
    visible = stored_account(records, a)
    old_private = stored_account(records, a)
    new_private = stored_account(records, a)
    money = MoneyService(FinancialAccountService(records, clock=lambda: NOW))

    def post(request, activity_id=None):
        p = money.preview(
            user_id=a, request=request, activity_id=activity_id, scope=PERSONAL
        )
        return money.write(
            user_id=a,
            request=MoneyRequest.model_validate(
                p["reviewed_request"] | {"preview_token": p["preview_token"]}
            ),
            activity_id=activity_id,
            idempotency_key=key(),
            scope=PERSONAL,
        )

    request = MoneyRequest(
        kind="transfer",
        source_account_id=old_private.account.id,
        destination_account_id=visible.account.id,
        amount="30",
        occurred_at=NOW - timedelta(days=1),
        time_zone="UTC",
    )
    result = post(request)
    aid = result["activity"]["activity_id"]
    post(
        request.model_copy(
            update={
                "source_account_id": new_private.account.id,
                "expected_revision": 1,
                "reason": "Correct source",
            }
        ),
        aid,
    )
    share(service, a, hid, visible.account.id, mid)
    history = financial.history(b, hid, aid)
    assert [item["activity"]["revision"] for item in history["items"]] == [2, 1]
    for item in history["items"]:
        assert item["activity"]["amount_minor"] is None
        assert [leg["account_id"] for leg in item["activity"]["legs"]] == [
            visible.account.id
        ]
    body = json.dumps(history, default=str)
    assert old_private.account.id not in body and new_private.account.id not in body


def test_corrected_away_activity_is_absent_without_losing_authorized_position(lane):
    service, records, (owner, recipient, _) = lane
    financial = HouseholdFinancialService(service)
    hid, mid, _ = setup(lane)
    visible = stored_account(records, owner)
    private = stored_account(records, owner)
    money = MoneyService(FinancialAccountService(records, clock=lambda: NOW))

    def post(request, activity_id=None):
        preview = money.preview(
            user_id=owner, request=request, activity_id=activity_id, scope=PERSONAL
        )
        return money.write(
            user_id=owner,
            request=MoneyRequest.model_validate(
                preview["reviewed_request"] | {"preview_token": preview["preview_token"]}
            ),
            activity_id=activity_id,
            idempotency_key=key(),
            scope=PERSONAL,
        )["activity"]

    original = post(expense(visible.account.id))
    post(
        expense(private.account.id, "15", revision=original["revision"]),
        original["activity_id"],
    )
    share(service, owner, hid, visible.account.id, mid)

    snapshot = financial.snapshot(recipient, hid)

    assert snapshot["activities"] == []
    assert [item["account"]["id"] for item in snapshot["accounts"]] == [
        visible.account.id
    ]
    expected = FinancialAccountService(records, clock=lambda: NOW).get(
        user_id=owner, account_id=visible.account.id, scope=PERSONAL
    )
    from argus.domain.recording.schemas import account_response

    assert snapshot["positions"][0]["amount_minor"] == (
        account_response(expected).balance.amount_minor
    )
    assert private.account.id not in json.dumps(snapshot, default=str)
    history = financial.history(recipient, hid, original["activity_id"])
    assert [item["activity"]["revision"] for item in history["items"]] == [1]


@pytest.mark.parametrize("surface", ["snapshot", "detail", "activity-options"])
def test_changed_asset_uses_redacted_household_wire_contract(lane, surface):
    from argus.api.households import HouseholdsContext, require_households_context
    from argus.api.routers.household_financial import router
    from argus.domain.recording.asset_schemas import AssetDetailsRequest
    from argus.domain.recording.assets import AssetService
    from argus.domain.recording.schemas import account_response
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    service, records, (owner, recipient, _) = lane
    hid, mid, _ = setup(lane)
    asset = stored_account(records, owner, amount=8000, kind="property")
    debt = stored_account(records, owner, kind="other_debt", amount=2000)
    assets = AssetService(FinancialAccountService(records, clock=lambda: NOW))
    for version, share_bps, debt_id in (
        (asset.account.version, 5000, debt.account.id),
        (asset.account.version + 1, 6000, None),
    ):
        assets.details(
            owner,
            asset.account.id,
            AssetDetailsRequest(
                expected_version=version,
                ownership_share_bps=share_bps,
                related_debt_account_id=debt_id,
            ),
            key(),
        )
    share(service, owner, hid, asset.account.id, mid, "edit")
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_households_context] = lambda: (
        HouseholdsContext(service, recipient)
    )
    suffix = f"accounts/{asset.account.id}" if surface == "detail" else surface
    with TestClient(app) as client:
        response = client.get(f"/api/v1/households/{hid}/{suffix}")
    assert response.status_code == 200
    body = response.json()
    if surface == "detail":
        shared = body["account"]["account"]
    elif surface == "snapshot":
        shared = body["accounts"][0]["account"]
    else:
        shared = body["accounts"][0]
    assert shared["asset"]["personal_position_minor"] == 480000
    changes = shared["asset"]["changes"]
    assert [change["ownership_share_bps"] for change in changes] == [5000, 6000]
    assert all(change["recorded_by"] is None for change in changes)
    assert all(change["previous_debt_account_id"] is None for change in changes)
    assert all(change["related_debt_account_id"] is None for change in changes)
    assert owner not in response.text and debt.account.id not in response.text
    personal = account_response(
        FinancialAccountService(records, clock=lambda: NOW).get(
            user_id=owner, account_id=asset.account.id, scope=PERSONAL
        )
    )
    assert personal.asset.changes[-1].recorded_by == owner
    assert personal.asset.changes[-1].previous_debt_account_id == debt.account.id


def test_concurrent_revoke_and_write_is_serialized_before_receipt_replay(lane):
    service, records, (a, b, _) = lane
    financial = HouseholdFinancialService(service)
    hid, mid, _ = setup(lane)
    aid = account(records, a)
    share(service, a, hid, aid, mid, "edit")
    body = reviewed(service, b, hid, expense(aid))
    token = key()
    barrier = Barrier(2)
    version = service.get(user_id=a, household_id=hid).version

    def write():
        barrier.wait()
        try:
            return scoped_money(
                financial, b, hid, body, k=token, member=mid, version=version
            )
        except (HouseholdUnavailable, StaleVersion):
            return None

    def revoke():
        barrier.wait()
        withdraw(service, a, hid, aid, version)

    with ThreadPoolExecutor(max_workers=2) as executor:
        posting, revoking = executor.submit(write), executor.submit(revoke)
        result = posting.result()
        revoking.result()
    assert len(
        records.get_account(user_id=a, account_id=aid, scope=PERSONAL).expenses
    ) == (1 if result else 0)
    with pytest.raises(HouseholdUnavailable):
        scoped_money(financial, b, hid, body, k=token)


def test_concurrent_exact_financial_retry_and_conflicting_body(lane):
    service, records, (a, b, _) = lane
    hid, mid, _ = setup(lane)
    financial = HouseholdFinancialService(service)
    aid = account(records, a)
    share(service, a, hid, aid, mid, "edit")
    body = reviewed(service, b, hid, expense(aid))
    token = key()
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(
            executor.map(
                lambda _: scoped_money(financial, b, hid, body, k=token), range(2)
            )
        )
    assert {x["replayed"] for x in outcomes} == {False, True}
    assert len({x["activity"]["activity"]["activity_id"] for x in outcomes}) == 1
    assert (
        len(records.get_account(user_id=a, account_id=aid, scope=PERSONAL).expenses) == 1
    )
    with pytest.raises(IdempotencyConflict):
        scoped_money(financial, b, hid, body.model_copy(update={"amount": "30"}), k=token)


def test_old_membership_journal_cannot_replay_after_rejoin_and_fresh_share(lane):
    service, records, (a, b, _) = lane
    hid, mid, token = setup(lane)
    aid = account(records, a)
    share(service, a, hid, aid, mid, "edit")
    body = reviewed(service, b, hid, expense(aid))
    financial = HouseholdFinancialService(service)
    k = key()
    scoped_money(financial, b, hid, body, k=k)
    command(service, b, "leave", lambda: service.leave(user_id=b, household_id=hid), hid)
    invite = command(
        service, a, "invite", lambda: service.invite(user_id=a, household_id=hid), hid
    ).invitation
    rejoined = service.accept(user_id=b, token=invite.token)
    share(service, a, hid, aid, rejoined.membership_id, "edit")
    with pytest.raises(HouseholdUnavailable):
        scoped_money(financial, b, hid, body, k=k, member=mid)
    assert service.accept(user_id=b, token=token).membership_id == mid
    assert (
        len(records.get_account(user_id=a, account_id=aid, scope=PERSONAL).expenses) == 1
    )


def test_search_cursor_invalidates_on_consent_change(lane):
    service, records, (a, b, _) = lane
    hid, mid, _ = setup(lane)
    first, second = account(records, a), account(records, a)
    for aid in [first, second]:
        share(service, a, hid, aid, mid)
    financial = HouseholdFinancialService(service)
    page = financial.search(b, hid, "", None, 1)
    assert page["next_cursor"]
    withdraw(service, a, hid, first)
    with pytest.raises(HouseholdRule):
        financial.search(b, hid, "", page["next_cursor"], 1)


def test_direct_rls_stays_owner_only_and_authorization_tables_are_service_owned(lane):
    service, records, (a, b, _) = lane
    hid, mid, _ = setup(lane)
    aid = account(records, a)
    share(service, a, hid, aid, mid, "edit")
    with service._repository.connection() as c, c.transaction():
        c.execute("set local role authenticated")
        c.execute(
            "select set_config('request.jwt.claims',%s,true)",
            (json.dumps({"sub": b, "role": "authenticated", "is_anonymous": False}),),
        )
        assert (
            c.execute(
                "select count(*) from public.financial_accounts where id=%s", (aid,)
            ).fetchone()[0]
            == 0
        )
        for table in [
            "households",
            "household_members",
            "household_invitations",
            "household_account_grants",
            "household_command_receipts",
        ]:
            with pytest.raises(InsufficientPrivilege), c.transaction():
                c.execute("select * from public." + table)


def test_invitation_single_use_race_has_one_membership_and_utc_expiry(lane):
    from argus.domain.household.errors import InvitationExpired

    service, _, (a, b, other) = lane
    hid, _, _ = setup(lane)
    invite = command(
        service, a, "invite", lambda: service.invite(user_id=a, household_id=hid), hid
    ).invitation

    def accept(actor):
        try:
            return service.accept(user_id=actor, token=invite.token)
        except InvitationConsumed:
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(accept, [b, other]))
    assert sum(x is not None for x in results) == 1
    invite = command(
        service, a, "invite", lambda: service.invite(user_id=a, household_id=hid), hid
    ).invitation
    service._repository._clock = lambda: NOW + timedelta(days=7)
    assert not service.preview_invitation(user_id=other, token=invite.token).available
    with pytest.raises(InvitationExpired):
        service.accept(user_id=other, token=invite.token)


def test_paired_recording_cannot_invent_cross_owner_transfer(lane):
    service, records, (a, b, _) = lane
    hid, mid, _ = setup(lane)
    first, second = account(records, a), account(records, b)
    share(service, a, hid, first, mid, "edit")
    admin = service.get(user_id=a, household_id=hid).membership_id
    share(service, b, hid, second, admin, "edit")
    body = MoneyRequest(
        kind="transfer",
        source_account_id=first,
        destination_account_id=second,
        amount="10",
        occurred_at=NOW - timedelta(days=1),
        time_zone="UTC",
    )
    with pytest.raises(HouseholdUnavailable):
        scoped_money(HouseholdFinancialService(service), b, hid, body)
