"""Ended consent retains history without observing later private facts."""

import json

import pytest
from argus.domain.financial_search import search
from argus.domain.household import planning_schemas as wire
from argus.domain.household import planning_store
from argus.domain.household.errors import HouseholdNotFound
from argus.domain.household.financial import HouseholdFinancialService
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.money_schemas import MoneyRequest
from argus.domain.recording.money_service import MoneyService

from tests.household.financial_fixtures import DSN, NOW, account, key, share
from tests.household.financial_fixtures import command as household_command
from tests.household.shared_plan_fixtures import (
    command,
    create,
    get,
    link,
    money,
    personal,
    request,
    scene,
)
from tests.household.test_shared_personal_bridge import personal_view
from tests.household.test_shared_planning_departure import accept, invitation, leave
from tests.household.test_shared_planning_money import planners

pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL required")


def depart(s, operation):
    if operation == "leave":
        leave(s, s["b"])
    else:
        household_command(
            s["households"],
            s["a"],
            "remove",
            lambda: s["households"].remove_member(
                user_id=s["a"], household_id=s["hid"], member_user_id=s["b"]
            ),
            s["hid"],
        )


def correct_private(s, aid, body):
    service = MoneyService(planners(s, s["b"]).accounts)
    preview = service.preview(
        user_id=s["b"], request=body, activity_id=aid, scope=PERSONAL
    )
    return service.write(
        user_id=s["b"],
        activity_id=aid,
        idempotency_key=key(),
        request=MoneyRequest.model_validate(
            preview["reviewed_request"] | {"preview_token": preview["preview_token"]}
        ),
        scope=PERSONAL,
    )


def readbacks(s):
    household = HouseholdFinancialService(s["households"])
    planner = planners(s, s["a"])
    return dict(
        personal=planner.read(s["a"], end=NOW.date()),
        household=household.snapshot(s["a"], s["hid"]),
        personal_search=search(planner.accounts, s["a"]).model_dump(mode="json"),
        household_search=household.search(s["a"], s["hid"], "Shared", None, 20),
    )


@pytest.mark.parametrize("operation", ["leave", "remove"])
@pytest.mark.parametrize("kind", ["budget", "bill", "goal"])
def test_departed_private_original_is_retained_while_remaining_contributions_stay_live(
    lane, operation, kind
):
    s = scene(lane)
    p = create(s, kind)
    oid = p["occurrences"][0]["id"] if kind != "budget" else None
    destination = s["bd"] if kind == "goal" else None
    activity = request(
        "transfer" if kind == "goal" else "expense",
        s["ba"],
        "30",
        destination,
        note="PRIVATE BEFORE LEAVE",
    )
    purpose = dict(
        budget="spending", bill="bill_payment", goal="goal_saving", debt="debt_payment"
    )[kind]
    saved, _ = money(s, s["b"], p, activity, purpose, oid)
    original = saved["plan"]["contributions"][0]
    depart(s, operation)
    with pytest.raises(HouseholdNotFound):
        get(s, s["b"], p)
    retained = get(s, s["a"], p)
    assert not retained["read_only"]
    assert retained["contributions"][0]["applied_minor"] == (
        None if kind == "goal" else "3000"
    )
    personal_view(s)
    authorized = readbacks(s)
    correct_private(
        s,
        original["original"]["activity_id"],
        activity.model_copy(
            update={
                "amount": "90",
                "expected_revision": 1,
                "reason": "PRIVATE AFTER LEAVE",
            }
        ),
    )
    after = get(s, s["a"], p)
    assert after["contributions"] == retained["contributions"]
    assert after["progress"] == retained["progress"]
    assert readbacks(s) == authorized
    assert all(
        secret not in json.dumps(after, default=str)
        for secret in (s["ba"], s["bd"], "PRIVATE AFTER LEAVE")
    )
    if kind != "budget":
        row = next(o for o in personal_view(s)["occurrences"] if o["id"] == oid)
        assert row["remaining_minor"] == (None if kind == "goal" else 7000)
    if kind in {"budget", "bill"}:
        live, _ = money(s, s["a"], p, request("expense", s["aa"], "20"), purpose, oid)
        assert live["plan"]["progress"]["applied_minor"] == "5000"
    else:
        live, _ = money(
            s, s["a"], p, request("transfer", s["aa"], "20", s["ad"]), purpose, oid
        )
        assert (
            next(
                c
                for c in live["plan"]["contributions"]
                if c["person"]["membership_id"] == s["amid"]
            )["applied_minor"]
            == "2000"
        )


@pytest.mark.parametrize("operation", ["leave", "remove"])
def test_allocation_backing_stops_at_departure_and_rejoin_requires_fresh_consent(
    lane, operation
):
    s = scene(lane)
    p = create(s, "goal")
    allocated = s["plans"].allocate(
        s["b"],
        s["hid"],
        "goal",
        str(p["ref"]["id"]),
        command(
            s,
            s["b"],
            p,
            wire.AllocationWrite,
            account_id=s["bd"],
            amount="150",
            expected_account_versions={
                s["bd"]: s["records"]
                .get_account(user_id=s["b"], account_id=s["bd"], scope=PERSONAL)
                .account.version
            },
        ),
        key(),
    )["plan"]
    allocation = allocated["allocations"][0]
    assert allocation["supported_minor"] == "15000"
    depart(s, operation)
    before = get(s, s["a"], p)
    assert before["allocations"][0]["assigned_minor"] == "15000"
    assert before["allocations"][0]["supported_minor"] is None
    personal(s, s["b"], request("expense", s["bd"], "600", note="PRIVATE WITHDRAWAL"))
    assert get(s, s["a"], p)["allocations"] == before["allocations"]
    new_mid = accept(s, s["b"], invitation(s, s["a"]))
    assert new_mid != s["bmid"]
    with pytest.raises(HouseholdNotFound):
        get(s, s["b"], p)
    s["plans"].replace_participants(
        s["a"],
        s["hid"],
        "goal",
        str(p["ref"]["id"]),
        command(
            s,
            s["a"],
            p,
            wire.ReplaceParticipants,
            participants=[dict(membership_id=new_mid)],
        ),
        key(),
    )
    fresh = s["plans"].allocate(
        s["b"],
        s["hid"],
        "goal",
        str(p["ref"]["id"]),
        command(
            s,
            s["b"],
            p,
            wire.AllocationWrite,
            account_id=s["bd"],
            amount="100",
            expected_account_versions={
                s["bd"]: s["records"]
                .get_account(user_id=s["b"], account_id=s["bd"], scope=PERSONAL)
                .account.version
            },
        ),
        key(),
    )["plan"]
    assert fresh["allocations"][0]["supported_minor"] == "10000"
    assert fresh["allocations"][0]["person"]["membership_id"] == new_mid
    with s["records"]._pool.connection() as c:
        retained = c.execute(
            "select last_supported_minor from household_plan_archived_allocations where allocation_id=%s and membership_ended_at is not null",
            (allocation["id"],),
        ).fetchall()
        assert retained == [(15000,)]


@pytest.mark.parametrize("released", [False, True])
def test_negative_refund_history_and_released_claim_do_not_follow_private_corrections(
    lane, released
):
    s = scene(lane)
    p = create(s, "budget")
    purchase = personal(s, s["b"], request("expense", s["ba"], "100"))
    refund = personal(
        s,
        s["b"],
        request(
            "refund",
            s["ba"],
            "20",
            purchase_activity_id=purchase["activity"]["activity_id"],
        ),
    )
    linked = link(s, s["b"], p, refund, "spending")["plan"]
    cid = linked["contributions"][0]["id"]
    if released:
        s["plans"].release(
            s["b"],
            s["hid"],
            "budget",
            str(p["ref"]["id"]),
            cid,
            command(s, s["b"], p),
            key(),
        )
    depart(s, "leave")
    before = get(s, s["a"], p)
    assert before["progress"]["spent_minor"] == ("0" if released else "-2000")
    correct_private(
        s,
        refund["activity"]["activity_id"],
        request(
            "refund",
            s["ba"],
            "30",
            purchase_activity_id=purchase["activity"]["activity_id"],
            expected_revision=1,
            reason="Private refund correction",
        ),
    )
    assert get(s, s["a"], p)["contributions"] == before["contributions"]
    assert get(s, s["a"], p)["progress"] == before["progress"]
    with s["records"]._pool.connection() as c:
        assert c.execute(
            "select last_applied_minor from household_plan_archived_claims where claim_id=%s",
            (cid,),
        ).fetchone()[0] == (0 if released else -2000)


def test_later_private_refund_cannot_enter_retained_spending_or_owner_archive(lane):
    s = scene(lane)
    p = create(s, "budget")
    saved, _ = money(s, s["b"], p, request("expense", s["ba"], "100"), "spending")
    aid = saved["plan"]["contributions"][0]["original"]["activity_id"]
    personal(s, s["b"], request("refund", s["ba"], "20", purchase_activity_id=aid))
    depart(s, "leave")
    before = get(s, s["a"], p)
    assert before["progress"]["spent_minor"] == "8000"
    personal(s, s["b"], request("refund", s["ba"], "10", purchase_activity_id=aid))
    assert get(s, s["a"], p)["progress"] == before["progress"]
    # Closing archives the owner's definition using those same clipped facts.
    household_command(
        s["households"],
        s["a"],
        "close",
        lambda: s["households"].close(user_id=s["a"], household_id=s["hid"]),
        s["hid"],
    )
    with s["records"]._pool.connection() as c:
        assert (
            c.execute(
                "select count(*) from household_plan_archived_activities a join household_plan_bindings b on b.id=a.binding_id where b.household_id=%s",
                (s["hid"],),
            ).fetchone()[0]
            == 2
        )


def test_departed_debt_contributor_private_spending_does_not_change_retained_payment(
    lane,
):
    s = scene(lane)
    s["loan"] = account(s["records"], s["a"], amount=-1000, kind="other_debt")
    p = create(s, "debt")
    oid = p["occurrences"][0]["id"]
    share(s["households"], s["a"], s["hid"], s["loan"], s["bmid"], "edit")
    money(
        s,
        s["b"],
        p,
        request(
            "debt_payment",
            s["ba"],
            "30",
            s["loan"],
            principal="26",
            interest="3",
            fees="1",
        ),
        "debt_payment",
        oid,
    )
    depart(s, "leave")
    personal_view(s)
    before = readbacks(s)
    personal(
        s, s["b"], request("expense", s["ba"], "800", note="PRIVATE DEBT FUNDING BALANCE")
    )
    assert readbacks(s) == before
    assert get(s, s["a"], p)["occurrences"][0]["remaining_minor"] == "7000"
    live, _ = money(
        s,
        s["a"],
        p,
        request(
            "debt_payment",
            s["aa"],
            "20",
            s["loan"],
            principal="20",
            interest="0",
            fees="0",
        ),
        "debt_payment",
        oid,
    )
    assert live["plan"]["occurrences"][0]["remaining_minor"] == "5000"


def test_departure_and_retention_roll_back_together_on_later_lifecycle_failure(
    lane, monkeypatch
):
    s = scene(lane)
    p = create(s, "bill")
    money(
        s,
        s["b"],
        p,
        request("expense", s["ba"], "30"),
        "bill_payment",
        p["occurrences"][0]["id"],
    )
    before = s["households"].get(user_id=s["b"], household_id=s["hid"])

    def interrupted(*_):
        raise RuntimeError("Synthetic interruption after retaining consent")

    with monkeypatch.context() as patch:
        patch.setattr(planning_store, "archive_owner", interrupted)
        with pytest.raises(RuntimeError, match="Synthetic interruption"):
            depart(s, "leave")
    assert (
        s["households"].get(user_id=s["b"], household_id=s["hid"]).version
        == before.version
    )
    assert get(s, s["b"], p)["contributions"][0]["applied_minor"] == "3000"
    with s["records"]._pool.connection() as c:
        assert (
            c.execute(
                "select count(*) from household_plan_archived_claims a join household_plan_bindings b on b.id=a.binding_id where b.household_id=%s",
                (s["hid"],),
            ).fetchone()[0]
            == 0
        )
