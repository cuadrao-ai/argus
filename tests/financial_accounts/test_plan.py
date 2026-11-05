from datetime import timedelta
from uuid import uuid4

import pytest
from argus.domain.owner_scope import PERSONAL
from argus.domain.planning.model import UnsafeCutover
from argus.domain.planning.schemas import (
    ExpectationCreate,
    ExpectationEdit,
    Fulfillment,
    LinkWrite,
    Schedule,
    SelectionWrite,
)
from argus.domain.planning.service import PlanService
from argus.domain.recording.errors import (
    AccountNotFound,
    IdempotencyConflict,
    RecordingInputError,
    StaleVersion,
)
from argus.domain.recording.money_schemas import MoneyRequest
from argus.domain.recording.money_service import MoneyService
from argus.domain.recording.schemas import EditFinancialAccountRequest
from faker import Faker

from tests.financial_accounts import test_loop_commands as shared
from tests.financial_accounts.test_loop_commands import NOW
from tests.financial_accounts.test_personal_money import account, save

scene = shared.scene
fake = Faker()


def setup_plan(scene, *, amount="50", kind="bill", due=None, cadence="once", aid=None):
    service, user, _ = scene
    aid = aid or account(scene)
    planner = PlanService(service)
    if planner.read(user)["selection"]["version"] == 0:
        planner.selection(
            user,
            SelectionWrite(
                expected_version=0, account_ids=[aid], time_zone="America/Santo_Domingo"
            ),
            str(uuid4()),
        )
    receipt = planner.create(
        user,
        ExpectationCreate(
            kind=kind,
            title=fake.word(),
            currency="DOP",
            amount=amount,
            account_id=aid,
            schedule=Schedule(cadence=cadence, start_date=due or NOW.date()),
        ),
        str(uuid4()),
    )
    occurrence = next(
        r
        for r in planner.read(user)["occurrences"]
        if r["expectation_id"] == receipt["expectation"]["id"]
    )
    return planner, aid, receipt["expectation"], occurrence


def confirmed(planner, user, occurrence, amount="50"):
    request = Fulfillment(
        expected_version=occurrence["expectation_version"],
        activity=MoneyRequest(
            kind="income" if occurrence["kind"] == "income" else "expense",
            account_id=occurrence["account_id"],
            amount=amount,
            occurred_at=NOW - timedelta(days=3),
        ),
    )
    preview = planner.preview(user, occurrence["id"], request)["money"]
    assert preview["ready"]
    return request.model_copy(
        update={
            "activity": MoneyRequest.model_validate(
                preview["reviewed_request"]
            ).model_copy(update={"preview_token": preview["preview_token"]})
        }
    )


def test_expectations_never_write_balances_and_same_day_bills_expose_shortfall(scene):
    planner, aid, expectation, bill = setup_plan(scene, amount="150")
    setup_plan(scene, amount="200", kind="income", aid=aid)
    read = planner.read(scene[1])
    group = read["currencies"][0]
    assert group["starting_minor"] == "10000"
    assert read["home"]["currencies"][0]["cash_minor"] == "1010000"
    assert group["ending_minor"] == "15000"
    assert group["first_shortfall_date"] == NOW.date().isoformat()
    assert group["points"][0]["occurrence_id"] is None
    assert group["points"][1]["balance_minor"] == "-5000"
    assert scene[0].get(user_id=scene[1], account_id=aid, scope=PERSONAL).expenses == ()


def test_fulfillment_replay_refund_and_amount_correction_keep_one_occurrence(scene):
    planner, aid, expectation, occurrence = setup_plan(scene)
    body = confirmed(planner, scene[1], occurrence)
    result = planner.fulfill(scene[1], occurrence["id"], body, "lost-response")
    replay = planner.fulfill(scene[1], occurrence["id"], body, "lost-response")
    assert replay["replayed"] and result["activity"] == replay["activity"]
    purchase = result["activity"]
    save(
        scene,
        kind="refund",
        account_id=aid,
        amount="5",
        purchase_activity_id=purchase["activity_id"],
    )
    money = MoneyService(scene[0])
    correction = MoneyRequest(
        kind="expense",
        account_id=aid,
        amount="60",
        occurred_at=NOW - timedelta(days=2),
        expected_revision=purchase["revision"],
        reason=fake.sentence(),
    )
    preview = money.preview(
        user_id=scene[1],
        request=correction,
        activity_id=purchase["activity_id"],
        scope=PERSONAL,
    )
    correction = MoneyRequest.model_validate(preview["reviewed_request"]).model_copy(
        update={"preview_token": preview["preview_token"]}
    )
    money.write(
        user_id=scene[1],
        request=correction,
        activity_id=purchase["activity_id"],
        idempotency_key=str(uuid4()),
        scope=PERSONAL,
    )
    read = planner.read(scene[1])
    assert read["occurrences"][0]["status"] == "fulfilled"
    assert read["currencies"][0]["expected_bills_minor"] == "0"
    assert read["currencies"][0]["starting_minor"] == "4500"
    with pytest.raises(RecordingInputError, match="occurrence_already_linked"):
        planner.fulfill(scene[1], occurrence["id"], body, str(uuid4()))


def test_account_correction_needs_review_then_explicit_relink(scene):
    planner, aid, _, occurrence = setup_plan(scene)
    result = planner.fulfill(
        scene[1], occurrence["id"], confirmed(planner, scene[1], occurrence), str(uuid4())
    )
    second = account(scene)
    money = MoneyService(scene[0])
    correction = MoneyRequest(
        kind="expense",
        account_id=second,
        amount="50",
        occurred_at=NOW - timedelta(days=1),
        expected_revision=1,
        reason=fake.sentence(),
    )
    preview = money.preview(
        user_id=scene[1],
        request=correction,
        activity_id=result["activity"]["activity_id"],
        scope=PERSONAL,
    )
    correction = MoneyRequest.model_validate(preview["reviewed_request"]).model_copy(
        update={"preview_token": preview["preview_token"]}
    )
    money.write(
        user_id=scene[1],
        request=correction,
        activity_id=result["activity"]["activity_id"],
        idempotency_key=str(uuid4()),
        scope=PERSONAL,
    )
    row = planner.read(scene[1])["occurrences"][0]
    assert (
        row["status"] == "needs_review" and row["exclusion_reason"] == "link_needs_review"
    )
    replacement = save(scene, kind="expense", account_id=aid, amount="45")["activity"]
    assert [
        a["activity_id"] for a in planner.candidates(scene[1], row["id"])["items"]
    ] == [replacement["activity_id"]]
    linked = planner.link(
        scene[1],
        row["id"],
        LinkWrite(
            expected_version=1,
            activity_id=replacement["activity_id"],
            activity_revision=1,
        ),
        "link",
    )
    assert linked["occurrence"]["status"] == "fulfilled"


def test_prepaid_future_occurrence_survives_edits_and_safe_recurrence_cutover(scene):
    future = NOW.date() + timedelta(days=7)
    planner, aid, expectation, occurrence = setup_plan(
        scene, due=future, cadence="weekly"
    )
    planner.fulfill(
        scene[1], occurrence["id"], confirmed(planner, scene[1], occurrence), "pay-early"
    )
    changed = planner.edit(
        scene[1],
        expectation["id"],
        ExpectationEdit(expected_version=1, amount="75", title=fake.word()),
        "amount",
    )["expectation"]
    assert changed["earliest_effective_date"] == (future + timedelta(days=1)).isoformat()
    with pytest.raises(UnsafeCutover):
        planner.edit(
            scene[1],
            expectation["id"],
            ExpectationEdit(
                expected_version=2,
                schedule=Schedule(cadence="weekly", start_date=NOW.date()),
                effective_date=NOW.date(),
            ),
            "unsafe",
        )
    second = account(scene)
    edited = planner.edit(
        scene[1],
        expectation["id"],
        ExpectationEdit(expected_version=2, account_id=second),
        "account",
    )["expectation"]
    assert edited["schedule"]["start_date"] == (future + timedelta(days=7)).isoformat()
    rows = planner.read(scene[1])["occurrences"]
    paid = next(r for r in rows if r["id"] == occurrence["id"])
    assert paid["status"] == "fulfilled" and paid["amount_minor"] == 5000
    assert sum(r["due_date"] == future.isoformat() for r in rows) == 1
    assert all(r["amount_minor"] == 7500 for r in rows if r["status"] == "planned")


@pytest.mark.usefixtures("legacy_blank_accounts")
def test_overdue_and_unknown_currencies_and_explicit_empty_selection(scene):
    planner, aid, _, occurrence = setup_plan(scene, due=NOW.date() - timedelta(days=3))
    unknown = account(scene, amount=None)
    usd = account(scene, currency="USD", amount="25")
    planner.selection(
        scene[1],
        SelectionWrite(
            expected_version=1,
            account_ids=[aid, unknown, usd],
            time_zone="America/Santo_Domingo",
        ),
        "selection",
    )
    read = planner.read(scene[1])
    assert read["occurrences"][0]["overdue"]
    assert read["occurrences"][0]["projection_date"] == NOW.date().isoformat()
    dop, dollars = read["currencies"]
    assert dop["starting_minor"] is None and dop["ending_minor"] is None
    assert dop["known_starting_minor"] == "10000" and dop["unknown_account_ids"] == [
        unknown
    ]
    assert dollars["starting_minor"] == "2500"
    planner.selection(
        scene[1],
        SelectionWrite(
            expected_version=2, account_ids=[], time_zone="America/Santo_Domingo"
        ),
        "empty",
    )
    assert planner.read(scene[1])["currencies"] == []
    assert (
        planner.read(scene[1])["occurrences"][0]["exclusion_reason"]
        == "account_not_selected"
    )


def test_link_is_unique_owner_scoped_stale_checked_and_replayed(scene):
    planner, aid, expectation, occurrence = setup_plan(scene)
    second = setup_plan(scene, aid=aid)[3]
    actual = save(scene, kind="expense", account_id=aid, amount="40")["activity"]
    body = LinkWrite(
        expected_version=1, activity_id=actual["activity_id"], activity_revision=1
    )
    planner.link(scene[1], occurrence["id"], body, "match")
    assert planner.link(scene[1], occurrence["id"], body, "match")["replayed"]
    with pytest.raises(RecordingInputError, match="activity_already_linked"):
        planner.link(scene[1], second["id"], body, "another")
    with pytest.raises(AccountNotFound):
        planner.candidates(str(uuid4()), occurrence["id"])
    with pytest.raises(StaleVersion):
        planner.link(
            scene[1],
            occurrence["id"],
            body.model_copy(update={"activity_revision": 2}),
            "stale",
        )
    with pytest.raises(IdempotencyConflict):
        planner.link(
            scene[1],
            occurrence["id"],
            body.model_copy(update={"activity_revision": 2}),
            "match",
        )


def test_archiving_restoring_and_reloading_keep_identity(scene):
    planner, aid, expectation, occurrence = setup_plan(scene)
    planner.edit(
        scene[1],
        expectation["id"],
        ExpectationEdit(expected_version=1, archived=True),
        "archive",
    )
    assert planner.read(scene[1])["occurrences"] == []
    planner.edit(
        scene[1],
        expectation["id"],
        ExpectationEdit(expected_version=2, archived=False),
        "restore",
    )
    reopened = PlanService(scene[0]).read(scene[1])
    assert reopened["occurrences"][0]["id"] == occurrence["id"]
    assert reopened["selection"]["account_ids"] == [aid]


@pytest.mark.usefixtures("legacy_blank_accounts")
def test_changed_empty_account_is_explicitly_excluded(scene):
    from argus.domain.recording.schemas import EditFinancialAccountRequest

    aid = account(scene, amount=None)
    planner, _, _, _ = setup_plan(scene, aid=aid)
    scene[0].edit(
        user_id=scene[1],
        account_id=aid,
        request=EditFinancialAccountRequest(expected_version=1, currency="USD"),
        scope=PERSONAL,
    )
    read = planner.read(scene[1])
    assert read["occurrences"][0]["exclusion_reason"] == "account_changed"
    assert read["currencies"][0]["currency"] == "USD"
    assert read["currencies"][0]["expected_bills_minor"] == "0"


def test_stored_reporting_zone_owns_today_boundary(scene):
    from datetime import datetime, timezone

    from argus.domain.recording.service import FinancialAccountService

    service = FinancialAccountService(
        scene[0]._repository, lambda: datetime(2026, 9, 21, 2, tzinfo=timezone.utc)
    )
    planner = PlanService(service)
    assert planner.read(scene[1])["start_date"] == "2026-09-20"
    planner.selection(
        scene[1],
        SelectionWrite(expected_version=0, account_ids=[], time_zone="Asia/Tokyo"),
        "zone",
    )
    assert PlanService(service).read(scene[1])["start_date"] == "2026-09-21"


def test_earlier_new_cutover_cannot_overlap_previous_schedule_segments(scene):
    planner, aid, expectation, _ = setup_plan(scene, cadence="weekly")
    planner.edit(
        scene[1],
        expectation["id"],
        ExpectationEdit(
            expected_version=1,
            effective_date=NOW.date() + timedelta(days=14),
            schedule=Schedule(
                cadence="weekly", start_date=NOW.date() + timedelta(days=14)
            ),
        ),
        "future",
    )
    planner.edit(
        scene[1],
        expectation["id"],
        ExpectationEdit(
            expected_version=2,
            effective_date=NOW.date() + timedelta(days=7),
            schedule=Schedule(
                cadence="weekly", start_date=NOW.date() + timedelta(days=7)
            ),
        ),
        "earlier",
    )
    dates = [r["due_date"] for r in planner.read(scene[1])["occurrences"]]
    assert len(dates) == len(set(dates))


@pytest.mark.parametrize(
    "opening,amount,share",
    [("100", "60", 5000), ("100.01", "0.02", 5000), ("100.01", "0.01", 3333)],
)
@pytest.mark.parametrize("kind", ["bill", "income"])
def test_forecast_ownership_and_rounding_survive_identical_fulfillment(
    scene, opening, amount, share, kind
):
    service, user, _ = scene
    aid = account(scene, amount=opening)
    service.edit(
        user_id=user,
        account_id=aid,
        request=EditFinancialAccountRequest(
            expected_version=1, ownership_share_bps=share
        ),
        scope=PERSONAL,
    )
    planner, _, _, occurrence = setup_plan(scene, amount=amount, kind=kind, aid=aid)
    expected = planner.read(user)["currencies"][0]
    planner.fulfill(
        user,
        occurrence["id"],
        confirmed(planner, user, occurrence, amount=amount),
        str(uuid4()),
    )
    actual = planner.read(user)["currencies"][0]
    assert actual["ending_minor"] == expected["ending_minor"]
    assert actual["first_shortfall_date"] == expected["first_shortfall_date"]
