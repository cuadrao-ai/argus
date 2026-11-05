"""Corrections, recurrence, and unresolved backing stay explicit across reads."""

from datetime import timedelta
from uuid import uuid4

import pytest
from argus.domain.financial_search import search
from argus.domain.owner_scope import PERSONAL
from argus.domain.planning.goal_schemas import (
    ContributionPlan,
    ContributionRelease,
    GoalEdit,
)
from argus.domain.planning.model import UnsafeCutover
from argus.domain.planning.schemas import Schedule, SelectionWrite
from argus.domain.recording.errors import RecordingInputError
from argus.domain.recording.schemas import EditFinancialAccountRequest

from tests.financial_accounts import test_loop_commands as shared
from tests.financial_accounts.test_budgets import write
from tests.financial_accounts.test_goals import allocate, link, setup_goal
from tests.financial_accounts.test_loop_commands import NOW
from tests.financial_accounts.test_personal_money import account, save

scene = shared.scene


def test_independent_component_is_labeled_while_shared_shortfall_is_unresolved(scene):
    service, aid, a = setup_goal(scene)
    _, _, b = setup_goal(scene, aid)
    extra = account(scene, amount="300")
    allocate(scene, service, [(a, aid, "600"), (a, extra, "200"), (b, aid, "300")])
    save(scene, kind="expense", account_id=aid, amount="200")
    result = service.get(scene[1], a["id"])
    assert (
        result["supported_minor"] is None
        and result["independently_backed_minor"] == "20000"
    )
    assert result["assigned_minor"] == "80000"
    assert sorted(
        (p["assigned_minor"], p["supported_minor"] or "null")
        for p in result["components"]
    ) == [("20000", "20000"), ("60000", "null")]


def test_endpoint_correction_requires_review_and_release_never_invents_residual(scene):
    service, aid, a = setup_goal(scene)
    source = account(scene, amount="1000")
    other = account(scene, amount="0")
    entry = save(
        scene,
        kind="transfer",
        source_account_id=source,
        destination_account_id=aid,
        amount="200",
    )["activity"]
    linked = link(scene, service, a, entry)["goal"]
    write(
        scene,
        identifier=entry["activity_id"],
        kind="transfer",
        source_account_id=source,
        destination_account_id=other,
        amount="200",
        expected_revision=1,
        reason="Correct destination",
    )
    current = service.get(scene[1], a["id"])
    assert current["supported_minor"] is None and current["assigned_minor"] == "0"
    assert current["contributions"][0]["current_personal_minor"] is None
    assert current["contributions"][0]["reviewed_personal_minor"] == "20000"
    service.release(
        scene[1],
        a["id"],
        linked["contributions"][0]["id"],
        ContributionRelease(expected_version=2),
        "release",
    )
    assert service.get(scene[1], a["id"])["supported_minor"] == "0"
    assert service.get(scene[1], a["id"])["goal"]["allocations"] == []


def test_activity_claim_conflict_included_limit_and_reverse_transfer(scene):
    service, aid, a = setup_goal(scene)
    _, _, b = setup_goal(scene, aid)
    source = account(scene, amount="1000")
    entry = save(
        scene,
        kind="transfer",
        source_account_id=source,
        destination_account_id=aid,
        amount="200",
    )["activity"]
    allocate(scene, service, [(a, aid, "100")])
    a = service.get(scene[1], a["id"])["goal"]
    with pytest.raises(RecordingInputError, match="goal_included_exceeds_allocation"):
        link(scene, service, a, entry, "included")
    a = link(scene, service, a, entry)["goal"]["goal"]
    with pytest.raises(RecordingInputError, match="activity_already_linked"):
        link(scene, service, b, entry)
    with pytest.raises(RecordingInputError, match="activity_already_linked"):
        link(scene, service, a, entry)
    save(
        scene,
        kind="transfer",
        source_account_id=aid,
        destination_account_id=source,
        amount="200",
    )
    assert service.get(scene[1], a["id"])["supported_minor"] == "30000"
    assert service.get(scene[1], a["id"])["contributions"][0]["status"] == "current"


@pytest.mark.parametrize(
    "selection,source_share,dest_share,effect",
    [
        ("both", 10000, 10000, "0"),
        ("source", 10000, 10000, "-10000"),
        ("destination", 10000, 10000, "10000"),
        ("both", 5000, 10000, "5000"),
        ("both", 10000, 5000, "-5000"),
    ],
)
def test_forecast_applies_selected_personal_legs_without_income_or_spending(
    scene, selection, source_share, dest_share, effect
):
    source = account(scene, amount="1000")
    dest = account(scene, amount="0")
    for aid, share in [(source, source_share), (dest, dest_share)]:
        if share != 10000:
            scene[0].edit(
                user_id=scene[1],
                account_id=aid,
                request=EditFinancialAccountRequest(
                    expected_version=1, ownership_share_bps=share
                ),
                scope=PERSONAL,
            )
    service, _, g = setup_goal(
        scene,
        dest,
        contribution_plan=dict(
            source_account_id=source,
            amount="100",
            schedule=dict(cadence="once", start_date=NOW.date().isoformat()),
        ),
    )
    selected = (
        [source, dest]
        if selection == "both"
        else [source]
        if selection == "source"
        else [dest]
    )
    service.planner.selection(
        scene[1],
        SelectionWrite(
            expected_version=0, account_ids=selected, time_zone="America/Santo_Domingo"
        ),
        str(uuid4()),
    )
    result = service.planner.read(scene[1])
    forecast = result["currencies"][0]
    assert (
        forecast["transfer_effect_minor"] == effect
        and forecast["net_cash_change_minor"] == effect
    )
    assert (
        forecast["expected_income_minor"] == "0"
        and forecast["expected_bills_minor"] == "0"
    )
    assert result["home"]["currencies"][0]["net_spending_minor"] == "0"
    assert service.get(scene[1], g["id"])["supported_minor"] == "0"


def test_prepaid_recurring_cutover_archive_and_timezone_preserve_fulfillment(scene):
    source = account(scene, amount="1000")
    dest = account(scene, amount="0")
    start = NOW.date() + timedelta(days=4)
    service, _, g = setup_goal(
        scene,
        dest,
        contribution_plan=dict(
            source_account_id=source,
            amount="100",
            schedule=dict(cadence="weekly", start_date=start.isoformat()),
        ),
    )
    row = service.planner.read(scene[1])["occurrences"][1]
    entry = save(
        scene,
        kind="transfer",
        source_account_id=source,
        destination_account_id=dest,
        amount="100",
    )["activity"]
    linked = link(scene, service, g, entry, occurrence_id=row["id"])["goal"]
    earliest = start + timedelta(days=8)
    assert linked["goal"]["earliest_effective_date"] == earliest.isoformat()
    with pytest.raises(UnsafeCutover):
        service.edit(
            scene[1],
            g["id"],
            GoalEdit(
                expected_version=2,
                contribution_plan=ContributionPlan(
                    source_account_id=source,
                    amount="150",
                    schedule=Schedule(cadence="weekly", start_date=start),
                ),
            ),
            "unsafe",
        )
    service.planner.selection(
        scene[1],
        SelectionWrite(
            expected_version=0, account_ids=[source, dest], time_zone="Pacific/Honolulu"
        ),
        "zone",
    )
    archived = service.edit(
        scene[1], g["id"], GoalEdit(expected_version=2, archived=True), "archive"
    )["goal"]
    history = service.planner.read(scene[1])["occurrences"]
    assert [r["id"] for r in history] == [row["id"]] and history[0][
        "status"
    ] == "fulfilled"
    assert archived["planned_minor"] == "0" and archived["supported_minor"] == "10000"
    service.edit(
        scene[1], g["id"], GoalEdit(expected_version=3, archived=False), "restore"
    )
    assert (
        next(
            r
            for r in service.planner.read(scene[1])["occurrences"]
            if r["id"] == row["id"]
        )["due_date"]
        == row["due_date"]
    )
    hit = search(scene[0], scene[1], kind="goal", q=g["name"]).items[0]
    assert hit.goal.supported_minor == "10000" and hit.goal.goal.id == g["id"]


def test_income_allocation_and_currency_isolation(scene):
    dest = account(scene, amount="0")
    foreign = account(scene, currency="USD", amount="1000")
    service, _, g = setup_goal(scene, dest)
    save(scene, kind="income", account_id=dest, amount="200", source_id="salary")
    allocate(scene, service, [(g, dest, "200")])
    current = service.get(scene[1], g["id"])
    assert current["supported_minor"] == "20000" and current["contributions"] == []
    with pytest.raises(RecordingInputError, match="currency_mismatch"):
        allocate(scene, service, [(current["goal"], foreign, "1")])


def test_unavailable_current_original_never_uses_reviewed_amount(scene, monkeypatch):
    from argus.domain.planning import goal_projection

    service, aid, goal = setup_goal(scene)
    source = account(scene, amount="1000")
    entry = save(
        scene,
        kind="transfer",
        source_account_id=source,
        destination_account_id=aid,
        amount="200",
    )["activity"]
    link(scene, service, goal, entry)
    original = goal_projection.current_activities
    monkeypatch.setattr(
        goal_projection,
        "current_activities",
        lambda accounts: [
            value
            for value in original(accounts)
            if value["activity_id"] != entry["activity_id"]
        ],
    )
    result = service.get(scene[1], goal["id"])
    assert result["supported_minor"] is None
    assert result["assigned_minor"] == "0"
    assert result["contributions"][0]["current_personal_minor"] is None
    assert result["contributions"][0]["reason"] == "contribution_unavailable"


def test_ad_hoc_claim_can_fulfill_own_occurrence_without_second_credit(scene):
    source = account(scene, amount="1000")
    service, aid, goal = setup_goal(
        scene,
        contribution_plan=dict(
            source_account_id=source,
            amount="100",
            schedule=dict(cadence="once", start_date=NOW.date().isoformat()),
        ),
    )
    occurrence = service.planner.read(scene[1])["occurrences"][0]
    entry = save(
        scene,
        kind="transfer",
        source_account_id=source,
        destination_account_id=aid,
        amount="100",
    )["activity"]
    first = link(scene, service, goal, entry)["goal"]
    second = link(scene, service, first["goal"], entry, occurrence_id=occurrence["id"])[
        "goal"
    ]
    assert first["supported_minor"] == second["supported_minor"] == "10000"
    assert first["contributions"][0]["id"] == second["contributions"][0]["id"]
    assert len(second["contributions"]) == 1
    assert second["planned_minor"] == "0"


def test_contribution_preview_exposes_source_pool_shortfall_without_writing(scene):
    from argus.domain.planning.goal_schemas import ContributionRecord
    from argus.domain.recording.money_schemas import MoneyRequest

    source = account(scene, amount="1000")
    dest = account(scene, amount="0")
    service, _, source_goal = setup_goal(scene, source)
    _, _, destination_goal = setup_goal(scene, dest)
    allocate(scene, service, [(source_goal, source, "900")])
    result = service.preview(
        scene[1],
        destination_goal["id"].upper(),
        ContributionRecord(
            expected_version=1,
            activity=MoneyRequest(
                kind="transfer",
                source_account_id=source,
                destination_account_id=dest,
                amount="200",
                occurred_at=NOW,
            ),
        ),
    )
    pool = next(value for value in result["pools"] if value["account_id"] == source)
    assert pool["shortfall_minor"] == "10000"
    assert result["goal"]["supported_minor"] == "20000"
    assert service.get(scene[1], source_goal["id"])["supported_minor"] == "90000"
    assert service.get(scene[1], destination_goal["id"])["supported_minor"] == "0"


def test_contribution_candidates_exclude_non_cash_funding(scene):
    service, dest, goal = setup_goal(scene)
    investment = account(scene, kind="investment", amount="1000")
    save(
        scene,
        kind="transfer",
        source_account_id=investment,
        destination_account_id=dest,
        amount="100",
    )
    assert service.candidates(scene[1], goal["id"])["items"] == []
    cash = account(scene, kind="checking", amount="1000")
    eligible = save(
        scene,
        kind="transfer",
        source_account_id=cash,
        destination_account_id=dest,
        amount="50",
    )["activity"]
    assert [
        entry["activity_id"]
        for entry in service.candidates(scene[1], goal["id"])["items"]
    ] == [eligible["activity_id"]]
