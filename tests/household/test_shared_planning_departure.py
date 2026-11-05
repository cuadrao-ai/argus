"""Retained canonical consent pins departure history and never grants rejoin."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from argus.domain.household import planning_schemas as wire
from argus.domain.household.errors import HouseholdNotFound
from argus.domain.household.financial import HouseholdFinancialService
from argus.domain.owner_scope import PERSONAL
from argus.domain.planning.budget_schemas import BudgetEdit
from argus.domain.planning.budgets import BudgetService
from argus.domain.planning.service import PlanService
from argus.domain.recording.errors import RecordingInputError
from argus.domain.recording.money_schemas import MoneyRequest
from argus.domain.recording.money_service import MoneyService
from argus.domain.recording.service import FinancialAccountService

from tests.household.financial_fixtures import DSN, NOW, key
from tests.household.financial_fixtures import command as household_command
from tests.household.shared_plan_fixtures import (
    command,
    create,
    get,
    money,
    request,
    scene,
    scope,
)

pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL required")


def leave(s, actor):
    household_command(
        s["households"],
        actor,
        "leave",
        lambda: s["households"].leave(user_id=actor, household_id=s["hid"]),
        s["hid"],
    )


def invitation(s, actor):
    return household_command(
        s["households"],
        actor,
        "invite",
        lambda: s["households"].invite(user_id=actor, household_id=s["hid"]),
        s["hid"],
    ).invitation.token


def accept(s, actor, token):
    return household_command(
        s["households"],
        actor,
        "accept",
        lambda: s["households"].accept(
            user_id=actor, token=token, display_name="Returned member"
        ),
    ).membership_id


@pytest.mark.parametrize("kind", ["budget", "bill", "goal", "debt"])
def test_owner_departure_freezes_definition_history_actuals_and_denies_future_writes(
    lane, kind
):
    s = scene(lane)
    p = create(s, kind)
    if kind in {"budget", "bill"}:
        saved, body = money(
            s,
            s["a"],
            p,
            request("expense", s["aa"], "20"),
            "spending" if kind == "budget" else "bill_payment",
            p["occurrences"][0]["id"] if kind == "bill" else None,
        )
    else:
        saved = None
    # Admin role and definition ownership are independent.
    household_command(
        s["households"],
        s["a"],
        "transfer",
        lambda: s["households"].transfer_admin(
            user_id=s["a"], household_id=s["hid"], new_admin_user_id=s["b"]
        ),
        s["hid"],
    )
    leave(s, s["a"])
    retained = get(s, s["b"], p)
    assert retained["archive_reason"] == "owner_departed"
    assert retained["read_only"] and not retained["can_restore"]
    assert all(str(o["date"]) <= NOW.date().isoformat() for o in retained["occurrences"])
    assert retained["owner"]["membership_id"] == s["amid"]
    with pytest.raises(HouseholdNotFound):
        get(s, s["a"], p)
    with pytest.raises(RecordingInputError):
        s["plans"].edit(
            s["b"],
            s["hid"],
            kind,
            str(p["ref"]["id"]),
            command(s, s["b"], p, wire.EditPlan, definition=dict(archived=False)),
            key(),
        )
    if kind == "budget":
        personal = PlanService(FinancialAccountService(s["records"], clock=lambda: NOW))
        BudgetService(personal).edit(
            s["a"],
            str(p["ref"]["id"]),
            BudgetEdit(
                expected_version=retained["version"],
                name="PRIVATE AFTER DEPARTURE",
                limit="900",
            ),
            key(),
        )
        aid = saved["plan"]["contributions"][0]["original"]["activity_id"]
        original = MoneyService(personal.accounts)
        corrected = request(
            "expense",
            s["aa"],
            "90",
            expected_revision=1,
            reason="Private later correction",
        )
        preview = original.preview(
            user_id=s["a"], request=corrected, activity_id=aid, scope=PERSONAL
        )
        original.write(
            user_id=s["a"],
            activity_id=aid,
            request=MoneyRequest.model_validate(
                preview["reviewed_request"] | {"preview_token": preview["preview_token"]}
            ),
            idempotency_key=key(),
            scope=PERSONAL,
        )
        frozen = get(s, s["b"], p)
        assert frozen["definition"]["limit_minor"] == "10000"
        assert frozen["definition"]["name"] == "Shared groceries"
        assert frozen["progress"]["spent_minor"] == "2000"
        assert frozen["contributions"][0]["amount_minor"] == "2000"
        assert "PRIVATE AFTER DEPARTURE" not in json.dumps(
            s["plans"].history(s["b"], s["hid"], kind, str(p["ref"]["id"])), default=str
        )
    newmid = accept(s, s["a"], invitation(s, s["b"]))
    assert newmid != s["amid"]
    with pytest.raises(HouseholdNotFound):
        get(s, s["a"], p)
    assert get(s, s["b"], p)["archive_reason"] == "owner_departed"
    if kind == "budget":
        current = BudgetService(personal).get(s["a"], str(p["ref"]["id"]))["budget"]
        fresh = s["plans"].share(
            s["a"],
            s["hid"],
            kind,
            str(p["ref"]["id"]),
            wire.SharePlan(**scope(s, s["a"], current["version"]), participants=[]),
            key(),
        )["plan"]
        assert fresh["owner"]["membership_id"] == newmid and not fresh["read_only"]
        # Existing recipients retain their earlier consent until explicitly named again.
        assert get(s, s["b"], p)["archive_reason"] == "owner_departed"


def test_recipient_leave_rejoin_receipt_and_cursor_require_fresh_consent(lane):
    s = scene(lane)
    p = create(s, "budget")
    saved, body = money(s, s["b"], p, request("expense", s["ba"], "10"), "spending")
    financial = HouseholdFinancialService(s["households"])
    assert financial.search(s["b"], s["hid"], "", None, 1)["items"]
    old = s["bmid"]
    leave(s, s["b"])
    new = accept(s, s["b"], invitation(s, s["a"]))
    assert old != new
    with pytest.raises(HouseholdNotFound):
        get(s, s["b"], p)
    assert s["plans"].snapshot(s["b"], s["hid"])["plans"] == []
    assert financial.search(s["b"], s["hid"], "", None, 10)["items"] == []
    s["plans"].replace_participants(
        s["a"],
        s["hid"],
        "budget",
        str(p["ref"]["id"]),
        command(
            s, s["a"], p, wire.ReplaceParticipants, participants=[dict(membership_id=new)]
        ),
        key(),
    )
    fresh = get(s, s["b"], p)
    assert fresh["contributions"][0]["person"]["membership_id"] == old
    assert (
        not fresh["contributions"][0]["can_correct"]
        and not fresh["contributions"][0]["can_release"]
    )
    assert (
        len(s["plans"].history(s["b"], s["hid"], "budget", str(p["ref"]["id"]))["items"])
        == 1
    )


def test_departure_and_shared_write_use_household_then_ordered_owner_locks(lane):
    s = scene(lane)
    p = create(s, "budget")
    household_command(
        s["households"],
        s["a"],
        "transfer",
        lambda: s["households"].transfer_admin(
            user_id=s["a"], household_id=s["hid"], new_admin_user_id=s["b"]
        ),
        s["hid"],
    )
    held, release = Event(), Event()

    def departure():
        with s["households"].transaction(s["a"], s["hid"]):
            held.set()
            assert release.wait(5)
            leave(s, s["a"])

    def blocked_write():
        assert held.wait(5)
        try:
            get(s, s["a"], p)
        except HouseholdNotFound:
            return "revoked"

    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(departure)
        assert held.wait(5)
        second = workers.submit(blocked_write)
        release.set()
        first.result(timeout=8)
        assert second.result(timeout=8) == "revoked"
    assert get(s, s["b"], p)["read_only"]
