"""Consented private originals reduce intentions without granting account visibility."""

import json

import pytest
from argus.domain.financial_search import search
from argus.domain.owner_scope import PERSONAL
from argus.domain.planning import storage
from argus.domain.planning.budgets import BudgetService
from argus.domain.planning.schemas import SelectionWrite
from argus.domain.recording.money_schemas import MoneyRequest
from argus.domain.recording.money_service import MoneyService

from tests.household.financial_fixtures import DSN, NOW, account, key, share
from tests.household.financial_fixtures import command as household_command
from tests.household.shared_plan_fixtures import (
    create,
    get,
    money,
    personal,
    request,
    scene,
)
from tests.household.test_shared_planning_departure import leave
from tests.household.test_shared_planning_invariants import correct
from tests.household.test_shared_planning_money import planners

pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL required")


def personal_view(s):
    planner = planners(s, s["a"])
    state, _ = storage.read(s["records"], s["a"])
    planner.selection(
        s["a"],
        SelectionWrite(
            expected_version=state["selection"]["version"],
            account_ids=[s["aa"]],
            time_zone="UTC",
        ),
        key(),
    )
    return planner.read(s["a"], end=NOW.date())


@pytest.mark.parametrize("kind", ["bill", "goal", "debt"])
def test_private_contributor_original_reduces_personal_and_shared_current_obligation(
    lane, kind
):
    s = scene(lane)
    if kind == "debt":
        s["loan"] = account(s["records"], s["a"], amount=-1000, kind="other_debt")
    p = create(s, kind)
    oid = p["occurrences"][0]["id"]
    marker = "PRIVATE-CONTRIBUTOR-" + key()
    if kind == "debt":
        share(s["households"], s["a"], s["hid"], s["loan"], s["bmid"], "edit")
    destination = s["bd"] if kind == "goal" else s["loan"] if kind == "debt" else None
    activity = request(
        "transfer" if kind == "goal" else "debt_payment" if kind == "debt" else "expense",
        s["ba"],
        "30",
        destination,
        note=marker,
        **(dict(principal="30", interest="0", fees="0") if kind == "debt" else {}),
    )
    saved, _ = money(
        s,
        s["b"],
        p,
        activity,
        dict(bill="bill_payment", goal="goal_saving", debt="debt_payment")[kind],
        oid,
    )
    claim = saved["plan"]["contributions"][0]
    personal = personal_view(s)
    occurrence = next(o for o in personal["occurrences"] if o["id"] == oid)
    assert occurrence["remaining_minor"] == 7000
    assert occurrence["status"] == "planned" and occurrence["activity_id"] is None
    assert get(s, s["a"], p)["occurrences"][0]["remaining_minor"] == "7000"
    currency = personal["currencies"][0]
    assert currency["ending_minor"] == "93000"
    assert currency["transfer_effect_minor"] == ("-7000" if kind == "goal" else "0")
    assert currency["expected_bills_minor"] == ("0" if kind == "goal" else "7000")
    encoded = json.dumps(personal, default=str)
    assert all(secret not in encoded for secret in (s["ba"], s["bd"], marker))
    found = search(planners(s, s["a"]).accounts, s["a"], q=marker)
    assert found.items == [] and found.next_cursor is None
    # Read and write projections must share the same resolver, including current correction.
    corrected = correct(
        s,
        p,
        claim["id"],
        activity.model_copy(
            update={
                "amount": "20",
                "expected_revision": 1,
                "reason": "Receipt correction",
                **(dict(principal="20") if kind == "debt" else {}),
            }
        ),
    )
    assert corrected["occurrences"][0]["remaining_minor"] == "8000"
    personal = personal_view(s)
    assert (
        next(o for o in personal["occurrences"] if o["id"] == oid)["remaining_minor"]
        == 8000
    )
    assert personal["currencies"][0]["ending_minor"] == "92000"
    assert all(
        secret not in json.dumps(personal, default=str)
        for secret in (s["ba"], s["bd"], marker)
    )


def test_shared_budget_consent_never_becomes_personal_owned_spending(lane):
    s = scene(lane)
    p = create(s, "budget")
    money(s, s["b"], p, request("expense", s["ba"], "30"), "spending")
    assert get(s, s["a"], p)["progress"]["spent_minor"] == "3000"
    home = BudgetService(planners(s, s["a"])).home(s["a"], NOW.strftime("%Y-%m"), "UTC")
    assert home["currencies"][0]["net_spending_minor"] == "0"
    assert s["ba"] not in json.dumps(personal_view(s), default=str)


def test_departure_drops_live_personal_claim_owner_seed_and_retains_shared_revision(lane):
    s = scene(lane)
    p = create(s, "bill")
    saved, _ = money(
        s,
        s["b"],
        p,
        request("expense", s["ba"], "30"),
        "bill_payment",
        p["occurrences"][0]["id"],
    )
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
    state, accounts = storage.read(s["records"], s["a"])
    assert state["_shared_links"] == []
    assert s["b"] not in {a.account.user_id for a in accounts.canonical.records}
    assert get(s, s["b"], p)["occurrences"][0]["remaining_minor"] == "7000"
    # The remaining contributor may correct the private original, while retained
    # sharing continues to read the exact revision consented at owner departure.
    original = MoneyService(planners(s, s["b"]).accounts)
    aid = saved["plan"]["contributions"][0]["original"]["activity_id"]
    correction = request(
        "expense", s["ba"], "90", expected_revision=1, reason="Private later correction"
    )
    preview = original.preview(
        user_id=s["b"], request=correction, activity_id=aid, scope=PERSONAL
    )
    original.write(
        user_id=s["b"],
        activity_id=aid,
        idempotency_key=key(),
        request=MoneyRequest.model_validate(
            preview["reviewed_request"] | {"preview_token": preview["preview_token"]}
        ),
        scope=PERSONAL,
    )
    assert get(s, s["b"], p)["occurrences"][0]["remaining_minor"] == "7000"


def test_private_goal_backing_is_unknown_without_exposing_partial_private_balance(lane):
    s = scene(lane)
    p = create(s, "goal")
    oid = p["occurrences"][0]["id"]
    money(s, s["b"], p, request("transfer", s["ba"], "30", s["bd"]), "goal_saving", oid)
    # Destination balance falls to ten, below the consented thirty claim.
    # Shared credit must become unknown, never the hidden min(balance, claim).
    personal(s, s["b"], request("expense", s["bd"], "1020", note="PRIVATE BACKING"))
    assert get(s, s["a"], p)["occurrences"][0]["remaining_minor"] is None
    result = personal_view(s)
    occurrence = next(o for o in result["occurrences"] if o["id"] == oid)
    assert (
        occurrence["remaining_minor"] is None and occurrence["status"] == "needs_review"
    )
    assert result["goals"][0]["projected_minor"] is None
    assert all(
        secret not in json.dumps(result, default=str)
        for secret in (s["ba"], s["bd"], "PRIVATE BACKING")
    )
