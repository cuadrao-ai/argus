from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from argus.domain.financial_search import search
from argus.domain.owner_scope import PERSONAL
from argus.domain.planning.budget_schemas import BudgetCreate, BudgetEdit, BudgetProgress
from argus.domain.planning.budgets import BudgetScopeConflict, BudgetService
from argus.domain.planning.schemas import SelectionWrite
from argus.domain.planning.service import PlanService
from argus.domain.recording.errors import (
    AccountNotFound,
    IdempotencyConflict,
    RecordingInputError,
    StaleVersion,
)
from argus.domain.recording.money_schemas import MoneyCoverage, MoneyRequest
from argus.domain.recording.money_service import MoneyService
from argus.domain.recording.schemas import EditFinancialAccountRequest
from faker import Faker
from pydantic import ValidationError

from tests.financial_accounts import test_loop_commands as shared
from tests.financial_accounts.test_loop_commands import NOW
from tests.financial_accounts.test_personal_money import account, save

scene = shared.scene
fake = Faker()


def setup_budget(scene, **changes):
    aid = changes.pop("aid", None) or account(scene, "checking")
    planner = PlanService(scene[0])
    service = BudgetService(planner)
    body = BudgetCreate.model_validate(
        dict(
            name=fake.word(),
            limit="150",
            currency="DOP",
            month="2026-09",
            account_ids=[aid],
            category_ids=["groceries"],
            include_uncategorized=False,
        )
        | changes
    )
    receipt = service.create(scene[1], body, str(uuid4()))
    return service, aid, receipt["budget"], body


def write(scene, *, identifier=None, **values):
    service = MoneyService(scene[0])
    command = MoneyRequest.model_validate(
        dict(occurred_at=NOW - timedelta(days=2)) | values
    )
    preview = service.preview(
        user_id=scene[1], request=command, activity_id=identifier, scope=PERSONAL
    )
    if not preview["ready"]:
        command = command.model_copy(
            update={
                "coverage": [
                    MoneyCoverage(
                        account_id=a["account_id"],
                        observation_id=o["observation_id"],
                        included=False,
                    )
                    for a in preview["affected_accounts"]
                    for o in a["observations"]
                ]
            }
        )
        preview = service.preview(
            user_id=scene[1], request=command, activity_id=identifier, scope=PERSONAL
        )
    assert preview["ready"]
    reviewed = MoneyRequest.model_validate(preview["reviewed_request"]).model_copy(
        update={"preview_token": preview["preview_token"]}
    )
    return service.write(
        user_id=scene[1],
        request=reviewed,
        activity_id=identifier,
        idempotency_key=str(uuid4()),
        scope=PERSONAL,
    )["activity"]


def test_connected_acceptance_actuals_contributors_and_cash_independence(scene):
    checking, card = account(scene, "checking"), account(scene, "credit_card")
    unknown, dollar, other = (
        account(scene, amount=None),
        account(scene, currency="USD"),
        account(scene),
    )
    purchase = save(
        scene, kind="expense", account_id=checking, amount="120", category_id="groceries"
    )["activity"]
    for aid, amount, category in [
        (checking, "10", "transport"),
        (checking, "7", None),
        (unknown, "3", "groceries"),
        (dollar, "50", "groceries"),
    ]:
        save(scene, kind="expense", account_id=aid, amount=amount, category_id=category)
    save(
        scene,
        kind="transfer",
        source_account_id=checking,
        destination_account_id=other,
        amount="40",
    )
    save(
        scene,
        kind="card_payment",
        source_account_id=checking,
        destination_account_id=card,
        amount="20",
    )
    before = PlanService(scene[0]).read(scene[1])
    service, _, budget, _ = setup_budget(
        scene, aid=checking, account_ids=[checking, card]
    )

    def check(spent, remaining, over, count):
        result = service.get(scene[1], budget["id"])
        BudgetProgress.model_validate(result)
        assert (
            result["spent_minor"],
            result["remaining_minor"],
            result["over_budget_minor"],
        ) == (spent, remaining, over)
        assert len(result["contributors"]) == count
        projection = service.planner.read(scene[1])
        assert projection["budgets"][0] == result == projection["home"]["budgets"][0]
        assert service.home(scene[1], None, None)["budgets"][0] == result

    check("12000", "3000", "0", 1)
    after = service.planner.read(scene[1])
    assert before["currencies"] == after["currencies"]
    assert before["accounts"] == after["accounts"]
    second = save(
        scene, kind="expense", account_id=card, amount="80", category_id="groceries"
    )["activity"]
    check("20000", "-5000", "5000", 2)
    write(
        scene,
        identifier=second["activity_id"],
        kind="expense",
        account_id=card,
        amount="60",
        category_id="groceries",
        expected_revision=1,
        reason=fake.sentence(),
    )
    check("18000", "-3000", "3000", 2)
    save(
        scene,
        kind="refund",
        account_id=other,
        amount="25",
        purchase_activity_id=purchase["activity_id"],
    )
    check("15500", "-500", "500", 3)
    untouched = scene[0].get(user_id=scene[1], account_id=unknown, scope=PERSONAL)
    assert [r.amount_minor for r in untouched.opening.revisions] == [0]
    assert untouched.checks == ()


def test_archive_restore_duplicate_replay_stale_and_search(scene):
    service, aid, budget, body = setup_budget(scene)
    user = scene[1]
    with pytest.raises(BudgetScopeConflict):
        service.create(user, body, "duplicate")
    archived = service.edit(
        user, budget["id"], BudgetEdit(expected_version=1, archived=True), "archive"
    )
    assert archived["budget"]["archived"]
    assert service.edit(
        user, budget["id"], BudgetEdit(expected_version=1, archived=True), "archive"
    )["replayed"]
    with pytest.raises(IdempotencyConflict):
        service.edit(
            user, budget["id"], BudgetEdit(expected_version=1, name="Other"), "archive"
        )
    assert not service.home(user, None, None)["budgets"]
    with pytest.raises(StaleVersion):
        service.edit(
            user, budget["id"], BudgetEdit(expected_version=1, limit="200"), "stale"
        )
    replacement = service.create(user, body, "replacement")["budget"]
    with pytest.raises(BudgetScopeConflict):
        service.edit(
            user, budget["id"], BudgetEdit(expected_version=2, archived=False), "restore"
        )
    service.edit(
        user,
        replacement["id"],
        BudgetEdit(expected_version=1, archived=True),
        "archive-replacement",
    )
    restored = service.edit(
        user, budget["id"], BudgetEdit(expected_version=2, archived=False), "restore"
    )
    assert restored["budget"]["version"] == 3
    assert len(search(scene[0], user, kind="budget").items) == 2
    with pytest.raises(AccountNotFound):
        service.get(str(uuid4()), budget["id"])


def test_refund_received_month_current_purchase_scope_and_negative_net(scene):
    first, other = account(scene), account(scene)
    service, _, budget, _ = setup_budget(scene, aid=first)
    purchase = write(
        scene,
        kind="expense",
        account_id=first,
        amount="50",
        category_id="groceries",
        occurred_at=datetime(2026, 8, 31, 12, tzinfo=timezone.utc),
    )
    save(
        scene,
        kind="refund",
        account_id=other,
        amount="25",
        purchase_activity_id=purchase["activity_id"],
    )
    assert service.get(scene[1], budget["id"])["spent_minor"] == "-2500"
    write(
        scene,
        identifier=purchase["activity_id"],
        kind="expense",
        account_id=other,
        amount="50",
        category_id="groceries",
        occurred_at=datetime(2026, 8, 31, 12, tzinfo=timezone.utc),
        expected_revision=1,
        reason=fake.sentence(),
    )
    assert service.get(scene[1], budget["id"])["spent_minor"] == "0"
    save(scene, kind="refund", account_id=first, amount="7", category_id="groceries")
    assert service.get(scene[1], budget["id"])["spent_minor"] == "-700"


def test_uncategorized_and_zone_change_recompute_half_open_boundaries(scene):
    aid = account(scene)
    service, _, budget, _ = setup_budget(
        scene, aid=aid, month="2026-08", category_ids=[], include_uncategorized=True
    )
    write(
        scene,
        kind="expense",
        account_id=aid,
        amount="7",
        occurred_at=datetime(2026, 9, 1, 4, tzinfo=timezone.utc),
    )
    assert service.get(scene[1], budget["id"])["spent_minor"] == "0"
    service.planner.selection(
        scene[1],
        SelectionWrite(expected_version=0, account_ids=[], time_zone="America/Chicago"),
        "zone",
    )
    assert service.get(scene[1], budget["id"])["spent_minor"] == "700"
    report = service.get(scene[1], budget["id"])
    assert report["period"]["end_at_exclusive"].hour == 0
    assert report["period"]["time_zone"] == "America/Chicago"


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"limit": "0"}, "amount_positive"),
        ({"limit": "1.001"}, "precision"),
        ({"category_ids": []}, "budget_category"),
        ({"category_ids": ["invalid"]}, "category_invalid"),
        ({"category_ids": ["groceries", "groceries"]}, "budget_scope_duplicate"),
        ({"month": "2026-13"}, "month_invalid"),
    ],
)
def test_definition_validation(scene, changes, code):
    with pytest.raises(RecordingInputError) as caught:
        setup_budget(scene, **changes)
    assert code in caught.value.code


def test_edit_null_fails_at_boundary():
    with pytest.raises(ValidationError):
        BudgetEdit(expected_version=1, limit=None)


@pytest.mark.parametrize(
    "zone,month,start,end",
    [
        (
            "America/New_York",
            "2026-03",
            "2026-03-01T05:00:00+00:00",
            "2026-04-01T04:00:00+00:00",
        ),
        (
            "America/Chicago",
            "2026-08",
            "2026-08-01T05:00:00+00:00",
            "2026-09-01T05:00:00+00:00",
        ),
    ],
)
def test_month_half_open_dst_and_date_correction(scene, zone, month, start, end):
    aid = account(scene, amount=None)
    service, _, budget, _ = setup_budget(scene, aid=aid, month=month)
    service.planner.selection(
        scene[1],
        SelectionWrite(expected_version=0, account_ids=[], time_zone=zone),
        "zone",
    )
    left, right = datetime.fromisoformat(start), datetime.fromisoformat(end)
    entries = []
    for when, amount in [
        (left - timedelta(microseconds=1), "3"),
        (left, "5"),
        (right - timedelta(microseconds=1), "7"),
        (right, "11"),
    ]:
        entries.append(
            write(
                scene,
                kind="expense",
                account_id=aid,
                amount=amount,
                category_id="groceries",
                occurred_at=when,
            )
        )
    result = service.get(scene[1], budget["id"])
    assert result["spent_minor"] == "1200"
    assert {a["activity_id"] for a in result["contributors"]} == {
        entries[1]["activity_id"],
        entries[2]["activity_id"],
    }
    write(
        scene,
        identifier=entries[1]["activity_id"],
        kind="expense",
        account_id=aid,
        amount="5",
        category_id="groceries",
        occurred_at=right,
        expected_revision=1,
        reason=fake.sentence(),
    )
    assert service.get(scene[1], budget["id"])["spent_minor"] == "700"


@pytest.mark.parametrize(
    "changes,error_code",
    [
        ({"type": "investment"}, "account_ineligible"),
        ({"currency": "USD"}, "currency_mismatch"),
    ],
)
@pytest.mark.usefixtures("legacy_blank_accounts")
def test_archive_survives_account_scope_change_but_restore_revalidates(
    scene, changes, error_code
):
    aid = account(scene, "checking", amount=None)
    service, _, budget, _ = setup_budget(scene, aid=aid)
    scene[0].edit(
        user_id=scene[1],
        account_id=aid,
        request=EditFinancialAccountRequest(expected_version=1, **changes),
        scope=PERSONAL,
    )
    command = BudgetEdit(expected_version=1, archived=True)
    archived = service.edit(scene[1], budget["id"], command, "archive-changed-account")
    assert archived["budget"]["archived"] and archived["budget"]["version"] == 2
    replay = service.edit(scene[1], budget["id"], command, "archive-changed-account")
    assert replay["replayed"] and replay["budget"] == archived["budget"]
    with pytest.raises(StaleVersion):
        service.edit(scene[1], budget["id"], command, "stale-archive")
    with pytest.raises(RecordingInputError) as error:
        service.edit(
            scene[1],
            budget["id"],
            BudgetEdit(expected_version=2, archived=False),
            "restore-changed-account",
        )
    assert error.value.code == error_code
    assert service.get(scene[1], budget["id"])["budget"] == archived["budget"]
    with pytest.raises(AccountNotFound):
        service.edit(
            scene[1],
            budget["id"],
            BudgetEdit(expected_version=2, account_ids=[uuid4()]),
            "foreign-scope",
        )
    with pytest.raises(RecordingInputError, match="budget_category_required"):
        service.edit(
            scene[1],
            budget["id"],
            BudgetEdit(expected_version=2, category_ids=[]),
            "empty-scope",
        )
    replacement = account(scene, "checking", amount=None)
    restored = service.edit(
        scene[1],
        budget["id"],
        BudgetEdit(expected_version=2, archived=False, account_ids=[replacement]),
        "restore-changed-account",
    )
    assert not restored["budget"]["archived"]
    assert restored["budget"]["version"] == 3
    assert restored["budget"]["account_ids"] == [replacement]
