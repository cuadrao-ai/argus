"""Independent money outcomes for current goal intentions and shared backing."""

from datetime import timedelta
from uuid import uuid4

import pytest
from argus.domain.owner_scope import PERSONAL
from argus.domain.planning.goal_schemas import (
    AllocationWrite,
    ContributionLink,
    ContributionRecord,
    ContributionRelease,
    GoalCreate,
    GoalEdit,
    GoalProgress,
)
from argus.domain.planning.goals import GoalService
from argus.domain.planning.schemas import SelectionWrite
from argus.domain.planning.service import PlanService
from argus.domain.recording.errors import RecordingInputError, StaleVersion
from argus.domain.recording.money_schemas import MoneyRequest
from argus.domain.recording.schemas import EditFinancialAccountRequest, account_response
from faker import Faker

from tests.financial_accounts import test_loop_commands as shared
from tests.financial_accounts.test_budgets import write
from tests.financial_accounts.test_loop_commands import NOW
from tests.financial_accounts.test_personal_money import account, save

scene = shared.scene
fake = Faker()


def setup_goal(scene, aid=None, **changes):
    aid = aid or account(scene, "savings", amount="1000")
    service = GoalService(PlanService(scene[0]))
    body = GoalCreate.model_validate(
        dict(name=fake.word(), currency="DOP", target="2000", destination_account_id=aid)
        | changes
    )
    return service, aid, service.create(scene[1], body, str(uuid4()))["goal"]["goal"]


def versions(scene, *ids):
    return {
        aid: scene[0]
        .get(user_id=scene[1], account_id=aid, scope=PERSONAL)
        .account.version
        for aid in ids
    }


def allocate(scene, service, changes, key=None):
    body = AllocationWrite.model_validate(
        dict(
            changes=[
                dict(
                    goal_id=g["id"],
                    expected_version=g["version"],
                    account_id=aid,
                    amount=amount,
                )
                for g, aid, amount in changes
            ],
            expected_account_versions=versions(scene, *(aid for _, aid, _ in changes)),
        )
    )
    return service.allocate(scene[1], body, key or str(uuid4()))


def link(scene, service, goal, entry, treatment="add", occurrence_id=None, key=None):
    body = ContributionLink.model_validate(
        dict(
            expected_version=goal["version"],
            activity_id=entry["activity_id"],
            activity_revision=entry["revision"],
            treatment=treatment,
            occurrence_id=occurrence_id,
            expected_account_versions=versions(
                scene, *(leg["account_id"] for leg in entry["legs"])
            ),
        )
    )
    return service.link(scene[1], goal["id"], body, key or str(uuid4()))


def test_shared_allocations_withdrawal_and_atomic_rebalance(scene):
    service, aid, a = setup_goal(scene)
    _, _, b = setup_goal(scene, aid)
    result = allocate(scene, service, [(a, aid, "600"), (b, aid, "300")])
    assert sorted(p["supported_minor"] for p in result["goals"]) == ["30000", "60000"]
    assert (
        next(p for p in result["pools"] if p["account_id"] == aid)["available_minor"]
        == "10000"
    )
    original = scene[0].get(user_id=scene[1], account_id=aid, scope=PERSONAL)
    assert (
        account_response(original).balance.amount_minor == 100000
        and original.expenses == ()
    )
    save(scene, kind="expense", account_id=aid, amount="200")
    current = [service.get(scene[1], g["id"]) for g in [a, b]]
    assert all(
        p["supported_minor"] is None and p["state"] == "needs_review" for p in current
    )
    assert current[0]["pools"][0]["shortfall_minor"] == "10000"
    recovered = allocate(
        scene,
        service,
        [(current[0]["goal"], aid, "500"), (current[1]["goal"], aid, "300")],
    )
    assert sorted(p["supported_minor"] for p in recovered["goals"]) == ["30000", "50000"]
    assert (
        account_response(
            scene[0].get(user_id=scene[1], account_id=aid, scope=PERSONAL)
        ).balance.amount_minor
        == 80000
    )


@pytest.mark.parametrize("corrected,expected", [("150", "55000"), ("250", "65000")])
def test_included_transfer_correction_uses_current_amount(scene, corrected, expected):
    service, aid, g = setup_goal(scene)
    source = account(scene, amount="1000")
    entry = save(
        scene,
        kind="transfer",
        source_account_id=source,
        destination_account_id=aid,
        amount="200",
    )["activity"]
    allocate(scene, service, [(g, aid, "600")])
    g = service.get(scene[1], g["id"])["goal"]
    linked = link(scene, service, g, entry, "included", key="included")
    assert linked["goal"]["assigned_minor"] == "60000"
    assert linked["goal"]["goal"]["allocations"] == [
        {"account_id": aid, "unlinked_minor": 40000}
    ]
    assert link(scene, service, g, entry, "included", key="included")["replayed"]
    write(
        scene,
        identifier=entry["activity_id"],
        kind="transfer",
        source_account_id=source,
        destination_account_id=aid,
        amount=corrected,
        expected_revision=1,
        reason=fake.sentence(),
    )
    current = service.get(scene[1], g["id"])
    GoalProgress.model_validate(current)
    assert (
        current["supported_minor"] == expected and current["assigned_minor"] == expected
    )
    assert current["contributions"][0]["reviewed_personal_minor"] == "20000"


@pytest.mark.parametrize(
    "amount,code", [(None, "goal_backing_unknown"), ("0", "goal_backing_shortfall")]
)
@pytest.mark.usefixtures("legacy_blank_accounts")
def test_unknown_and_known_zero_do_not_fund_positive_claims(scene, amount, code):
    aid = account(scene, "savings", amount=amount)
    service, _, g = setup_goal(scene, aid)
    with pytest.raises(RecordingInputError, match=code):
        allocate(scene, service, [(g, aid, "1")])
    assert service.get(scene[1], g["id"])["assigned_minor"] == "0"


def test_single_shortfall_reduction_archive_and_restore(scene):
    service, aid, g = setup_goal(scene)
    allocate(scene, service, [(g, aid, "900")])
    save(scene, kind="expense", account_id=aid, amount="200")
    current = service.get(scene[1], g["id"])
    assert current["supported_minor"] == "80000" and current["state"] == "needs_review"
    allocate(scene, service, [(current["goal"], aid, "850")])
    current = service.get(scene[1], g["id"])
    archived = service.edit(
        scene[1],
        g["id"],
        GoalEdit(expected_version=current["goal"]["version"], archived=True),
        "archive",
    )["goal"]
    assert archived["supported_minor"] == "80000" and archived["goal"]["archived"]
    _, _, b = setup_goal(scene, aid)
    with pytest.raises(RecordingInputError):
        allocate(scene, service, [(b, aid, "1")])
    restored = service.edit(
        scene[1],
        g["id"],
        GoalEdit(expected_version=archived["goal"]["version"], archived=False),
        "restore",
    )["goal"]
    assert restored["state"] == "needs_review" and restored["goal"]["id"] == g["id"]


def test_transfer_schedule_nets_selected_legs_and_release_keeps_fulfillment(scene):
    source = account(scene, "checking", amount="1000")
    aid = account(scene, "savings", amount="0")
    service, _, g = setup_goal(
        scene,
        aid,
        contribution_plan=dict(
            source_account_id=source,
            amount="100",
            schedule=dict(cadence="once", start_date=NOW.date().isoformat()),
        ),
    )
    planner = service.planner
    planner.selection(
        scene[1],
        SelectionWrite(
            expected_version=0,
            account_ids=[source, aid],
            time_zone="America/Santo_Domingo",
        ),
        "selection",
    )
    before = planner.read(scene[1])
    forecast = before["currencies"][0]
    assert (
        forecast["ending_minor"] == "100000" and forecast["net_cash_change_minor"] == "0"
    )
    assert (
        forecast["expected_income_minor"] == "0"
        and forecast["expected_bills_minor"] == "0"
    )
    assert (
        before["goals"][0]["supported_minor"] == "0"
        and before["goals"][0]["planned_minor"] == "10000"
    )
    oid = before["occurrences"][0]["id"]
    body = ContributionRecord(
        expected_version=1,
        occurrence_id=oid,
        activity=MoneyRequest(
            kind="transfer",
            source_account_id=source,
            destination_account_id=aid,
            amount="100",
            occurred_at=NOW - timedelta(days=1),
        ),
    )
    preview = service.preview(scene[1], g["id"], body)["money"]
    reviewed = body.model_copy(
        update={
            "activity": MoneyRequest.model_validate(
                preview["reviewed_request"]
            ).model_copy(update={"preview_token": preview["preview_token"]})
        }
    )
    receipt = service.record(scene[1], g["id"], reviewed, "record")
    assert service.record(scene[1], g["id"], reviewed, "record")["replayed"]
    assert receipt["goal"]["supported_minor"] == "10000"
    claim = receipt["goal"]["contributions"][0]
    service.release(
        scene[1], g["id"], claim["id"], ContributionRelease(expected_version=2), "release"
    )
    after = planner.read(scene[1])
    assert after["goals"][0]["supported_minor"] == "0"
    assert after["occurrences"][0]["status"] == "fulfilled"
    assert after["currencies"][0]["ending_minor"] == "100000"
    assert after["home"]["currencies"][0]["net_spending_minor"] == "0"


def test_shared_ownership_capacity_and_stale_review(scene):
    service, aid, g = setup_goal(scene, account(scene, amount="10.01"))
    scene[0].edit(
        user_id=scene[1],
        account_id=aid,
        request=EditFinancialAccountRequest(expected_version=1, ownership_share_bps=5000),
        scope=PERSONAL,
    )
    with pytest.raises(RecordingInputError):
        allocate(scene, service, [(g, aid, "5.01")])
    allocate(scene, service, [(g, aid, "5")])
    assert service.get(scene[1], g["id"])["supported_minor"] == "500"
    with pytest.raises(StaleVersion):
        allocate(scene, service, [(g, aid, "4")])
