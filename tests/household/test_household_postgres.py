"""Canonical Household authorization and retries on disposable PostgreSQL."""

from datetime import timedelta

import pytest
from argus.domain.household.errors import (
    HouseholdNotFound,
    InvitationConsumed,
    MustTransferOrClose,
)
from argus.domain.household.financial import HouseholdFinancialService
from argus.domain.household.schemas import CreateHouseholdRequest, Recipient
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.errors import IdempotencyConflict, StaleVersion

from tests.household.financial_fixtures import (
    DSN,
    NOW,
    account,
    command,
    expense,
    key,
    money,
    reviewed,
    setup,
    share,
)

pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL required")


def test_create_and_invitation_retry_are_durable_and_do_not_repeat_capabilities(lane):
    s, _, (a, b, other) = lane
    k = key()
    body = {"name": "One"}

    def action():
        return s.create(user_id=a, request=CreateHouseholdRequest(name="One"))

    first = command(s, a, "create", action, body=body, k=k)
    assert (
        command(s, a, "create", action, body=body, k=k).household_id == first.household_id
    )
    with pytest.raises(IdempotencyConflict):
        command(s, a, "create", action, body={"name": "Different"}, k=k)
    hid = first.household_id
    version = s.get(user_id=a, household_id=hid).version
    k = key()

    def action():
        return s.invite(user_id=a, household_id=hid)

    invite = command(
        s, a, "invite", action, hid, {"expected_version": version}, k
    ).invitation
    retry = command(s, a, "invite", action, hid, {"expected_version": version}, k)
    assert retry.invitation.token is None and retry.invitation.id == invite.id
    assert invite.expires_at == NOW + timedelta(days=7)
    assert s.preview_invitation(user_id=b, token=invite.token).available
    accepted = s.accept(user_id=b, token=invite.token, display_name="Bob")
    assert s.accept(user_id=b, token=invite.token) == accepted
    with pytest.raises(InvitationConsumed):
        s.accept(user_id=other, token=invite.token)
    assert HouseholdFinancialService(s).snapshot(b, hid)["accounts"] == []


@pytest.mark.parametrize("ending", ["leave", "remove", "close"])
def test_departure_replay_and_rejoin_require_fresh_consent(lane, ending):
    s, records, (a, b, _) = lane
    hid, mid, token = setup(lane)
    aid = account(records, a)
    bid = account(records, b)
    amid = s.get(user_id=a, household_id=hid).membership_id
    share(s, a, hid, aid, mid)
    share(s, b, hid, bid, amid)
    actor = b if ending == "leave" else a
    action = (
        (lambda: s.leave(user_id=b, household_id=hid))
        if ending == "leave"
        else (lambda: s.remove_member(user_id=a, household_id=hid, member_user_id=b))
        if ending == "remove"
        else (lambda: s.close(user_id=a, household_id=hid))
    )
    version = s.get(user_id=actor, household_id=hid).version
    k = key()
    command(s, actor, ending, action, hid, {"expected_version": version}, k)
    assert command(
        s, actor, ending, action, hid, {"expected_version": version}, k
    ).replayed
    original = s.accept(user_id=b, token=token)
    assert original.membership_id == mid and original.state == "departed"
    assert records.get_account(
        user_id=a, account_id=aid, scope=PERSONAL
    ) and records.get_account(user_id=b, account_id=bid, scope=PERSONAL)
    if ending != "close":
        inv = command(
            s, a, "invite", lambda: s.invite(user_id=a, household_id=hid), hid
        ).invitation
        rejoined = s.accept(user_id=b, token=inv.token)
        assert rejoined.membership_id != mid
        assert HouseholdFinancialService(s).snapshot(b, hid)["accounts"] == []
        assert s.accept(user_id=b, token=token).state == "departed"


def test_shared_edit_owner_actor_correction_and_revoked_replay(lane):
    s, records, (a, b, _) = lane
    hid, mid, _ = setup(lane)
    aid = account(records, a)
    share(s, a, hid, aid, mid)
    with pytest.raises(HouseholdNotFound):
        money(s, b, hid, expense(aid))
    share(s, a, hid, aid, mid, "edit")
    body = reviewed(s, b, hid, expense(aid))
    k = key()
    first = money(s, b, hid, body, k=k)
    activity_id = first["activity"]["activity"]["activity_id"]
    assert money(s, b, hid, body, k=k)["replayed"]
    assert (
        records.get_account(user_id=a, account_id=aid, scope=PERSONAL)
        .expenses[0]
        .current.recorded_by
        == b
    )
    corrected = reviewed(s, b, hid, expense(aid, "20", 1), activity_id)
    result = money(s, b, hid, corrected, aid=activity_id, k=key())
    assert result["accounts"][0]["account"]["balance"]["amount"] == "980.00"
    version = s.get(user_id=a, household_id=hid).version
    command(
        s,
        a,
        "withdraw",
        lambda: s.replace_grants(
            user_id=a, household_id=hid, account_id=aid, recipients=[]
        ),
        hid,
    )
    with pytest.raises(HouseholdNotFound):
        money(s, b, hid, body, k=k)
    with pytest.raises(StaleVersion):
        command(s, a, "stale", lambda: None, hid, {"expected_version": version})


def test_projection_deduplicates_named_grants_and_keeps_currency_unknowns(lane):
    s, records, (a, b, c) = lane
    hid, mid, _ = setup(lane)
    inv = command(
        s, a, "invite", lambda: s.invite(user_id=a, household_id=hid), hid
    ).invitation
    third = s.accept(user_id=c, token=inv.token).membership_id
    cash = account(records, a)
    asset = account(records, a, 8000, share=5000, kind="property")
    unknown = account(records, a, None, currency="USD")
    account(records, a, 9000)
    for aid in [cash, asset, unknown]:
        command(
            s,
            a,
            "share:" + aid,
            lambda aid=aid: s.replace_grants(
                user_id=a,
                household_id=hid,
                account_id=aid,
                recipients=[Recipient(membership_id=mid), Recipient(membership_id=third)],
            ),
            hid,
        )
    for actor in [a, b, c]:
        snap = HouseholdFinancialService(s).snapshot(actor, hid)
        assert len(snap["accounts"]) == 3
        totals = {p["currency"]: p for p in snap["positions"]}
        assert totals["DOP"]["amount_minor"] == 500000
        assert totals["USD"]["unknown_count"] == 1 and totals["USD"]["amount_minor"] == 0


def test_single_admin_must_explicitly_close(lane):
    s, _, (a, _, _) = lane
    h = s.create(user_id=a, request=CreateHouseholdRequest())
    with pytest.raises(MustTransferOrClose):
        s.leave(user_id=a, household_id=h.id)
