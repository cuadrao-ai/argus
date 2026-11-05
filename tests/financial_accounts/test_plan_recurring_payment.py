"""Recurring expectation to confirmed payment: windows, single-effect fulfillment, access."""

from contextlib import contextmanager
from datetime import timedelta
from uuid import uuid4

import pytest
from argus.domain.planning.schemas import (
    ExpectationCreate,
    Fulfillment,
    LinkWrite,
    Schedule,
)
from argus.domain.recording.errors import (
    AccountNotFound,
    IdempotencyConflict,
    RecordingInputError,
)
from argus.domain.recording.money_schemas import MoneyRequest

from tests.financial_accounts import test_loop_commands as shared
from tests.financial_accounts.test_loop_commands import NOW
from tests.financial_accounts.test_personal_money import account, save
from tests.financial_accounts.test_plan import confirmed, setup_plan

scene = shared.scene
TODAY = NOW.date()


@contextmanager
def second_owner(scene):
    """A registered stranger: Postgres refuses writes from ids with no auth user."""
    stranger = str(uuid4())
    pool = getattr(scene[0]._repository, "_pool", None)
    if pool is None:
        yield stranger
        return
    with pool.connection() as connection:
        connection.execute(
            "insert into auth.users(id,email,is_anonymous) values(%s,%s,false)",
            (stranger, f"stranger-{stranger}@example.test"),
        )
    try:
        yield stranger
    finally:
        with pool.connection() as connection:
            connection.execute("delete from auth.users where id=%s", (stranger,))


def due_dates(read, expectation_id):
    return [
        r["due_date"]
        for r in read["occurrences"]
        if r["expectation_id"] == expectation_id
    ]


def totals(read):
    group = read["currencies"][0]
    return group["starting_minor"], group["expected_bills_minor"], group["ending_minor"]


def test_default_window_is_thirty_days_and_unaffected_by_a_longer_request(
    scene,
):
    planner, _, expectation, _ = setup_plan(
        scene, due=TODAY + timedelta(days=18), cadence="monthly"
    )
    eid = expectation["id"]
    default = planner.read(scene[1])
    assert (default["start_date"], default["end_date"]) == ("2026-09-20", "2026-10-20")
    assert due_dates(default, eid) == ["2026-10-08"]
    longer = planner.read(scene[1], TODAY, TODAY + timedelta(days=90))
    assert longer["end_date"] == "2026-12-19"
    assert due_dates(longer, eid) == ["2026-10-08", "2026-11-08", "2026-12-08"]
    again = planner.read(scene[1])
    assert (again["end_date"], due_dates(again, eid), totals(again)) == (
        "2026-10-20",
        ["2026-10-08"],
        totals(default),
    )


def test_thirty_day_window_includes_day_thirty_and_excludes_day_thirty_one(scene):
    planner, aid, last, _ = setup_plan(scene, due=TODAY + timedelta(days=30))
    beyond = planner.create(
        scene[1],
        ExpectationCreate(
            kind="bill",
            title="Later",
            currency="DOP",
            amount="10",
            account_id=aid,
            schedule=Schedule(cadence="once", start_date=TODAY + timedelta(days=31)),
        ),
        str(uuid4()),
    )["expectation"]
    read = planner.read(scene[1])
    assert due_dates(read, last["id"]) == ["2026-10-20"]
    assert due_dates(read, beyond["id"]) == []


@pytest.mark.parametrize(
    "start, end",
    [(TODAY, TODAY + timedelta(days=367)), (TODAY + timedelta(days=1), None)],
)
def test_plan_horizon_beyond_366_days_or_not_starting_today_is_refused(scene, start, end):
    planner, _, _, _ = setup_plan(scene)
    with pytest.raises(RecordingInputError, match="forecast_period_invalid"):
        planner.read(scene[1], start, end)


def test_linking_an_actual_payment_moves_bills_and_ending_once_and_replays_without_effect(
    scene,
):
    planner, aid, _, occurrence = setup_plan(scene, amount="50")
    assert totals(planner.read(scene[1])) == ("10000", "5000", "5000")
    paid = save(scene, kind="expense", account_id=aid, amount="50")["activity"]
    assert totals(planner.read(scene[1])) == ("5000", "5000", "0")
    body = LinkWrite(
        expected_version=1, activity_id=paid["activity_id"], activity_revision=1
    )
    planner.link(scene[1], occurrence["id"], body, "pay")
    assert totals(planner.read(scene[1])) == ("5000", "0", "5000")
    assert planner.link(scene[1], occurrence["id"], body, "pay")["replayed"]
    assert totals(planner.read(scene[1])) == ("5000", "0", "5000")


def test_new_payment_through_fulfillment_removes_one_occurrence_and_conflicting_replay_is_refused(
    scene,
):
    planner, aid, expectation, occurrence = setup_plan(
        scene, amount="50", cadence="weekly"
    )
    horizon = planner.read(scene[1], TODAY, TODAY + timedelta(days=14))
    assert due_dates(horizon, expectation["id"]) == [
        "2026-09-20",
        "2026-09-27",
        "2026-10-04",
    ]
    assert totals(horizon) == ("10000", "15000", "-5000")
    body = confirmed(planner, scene[1], occurrence, amount="50")
    first = planner.fulfill(scene[1], occurrence["id"], body, "pay")
    after = planner.read(scene[1], TODAY, TODAY + timedelta(days=14))
    assert totals(after) == ("5000", "10000", "-5000")
    assert [r["status"] for r in after["occurrences"]] == [
        "fulfilled",
        "planned",
        "planned",
    ]
    again = planner.fulfill(scene[1], occurrence["id"], body, "pay")
    assert (again["replayed"], again["activity"]["activity_id"]) == (
        True,
        first["activity"]["activity_id"],
    )
    assert totals(planner.read(scene[1], TODAY, TODAY + timedelta(days=14))) == totals(
        after
    )
    changed = body.model_copy(
        update={"activity": body.activity.model_copy(update={"amount": "60"})}
    )
    with pytest.raises(IdempotencyConflict):
        planner.fulfill(scene[1], occurrence["id"], changed, "pay")
    with pytest.raises(RecordingInputError, match="occurrence_already_linked"):
        planner.fulfill(scene[1], occurrence["id"], body, str(uuid4()))


def test_payment_on_another_account_cannot_fulfil_an_occurrence(scene):
    planner, aid, _, occurrence = setup_plan(scene)
    other = account(scene)
    request = Fulfillment(
        expected_version=1,
        activity=MoneyRequest(
            kind="expense",
            account_id=other,
            amount="50",
            occurred_at=NOW - timedelta(days=1),
        ),
    )
    with pytest.raises(RecordingInputError, match="fulfillment_mismatch"):
        planner.preview(scene[1], occurrence["id"], request)


@pytest.mark.parametrize(
    "kind, currency, code",
    [("cash", "USD", "currency_mismatch"), ("credit_card", "DOP", "account_ineligible")],
)
def test_expectation_account_must_be_same_currency_cash(scene, kind, currency, code):
    planner, _, _, _ = setup_plan(scene)
    target = account(scene, kind, currency, amount="25")
    body = ExpectationCreate(
        kind="bill",
        title="Cloud",
        currency="DOP",
        amount="10",
        account_id=target,
        schedule=Schedule(cadence="once", start_date=TODAY),
    )
    with pytest.raises(RecordingInputError, match=code):
        planner.create(scene[1], body, str(uuid4()))


def test_another_owner_cannot_read_edit_preview_fulfil_or_link(scene):
    planner, aid, expectation, occurrence = setup_plan(scene)
    paid = save(scene, kind="expense", account_id=aid, amount="50")["activity"]
    request = confirmed(planner, scene[1], occurrence)
    link = LinkWrite(
        expected_version=1, activity_id=paid["activity_id"], activity_revision=1
    )
    with second_owner(scene) as stranger:
        for attempt in (
            lambda: planner.get(stranger, expectation["id"]),
            lambda: planner.candidates(stranger, occurrence["id"]),
            lambda: planner.preview(stranger, occurrence["id"], request),
            lambda: planner.fulfill(stranger, occurrence["id"], request, str(uuid4())),
            lambda: planner.link(stranger, occurrence["id"], link, str(uuid4())),
        ):
            with pytest.raises(AccountNotFound):
                attempt()
    assert planner.read(scene[1])["occurrences"][0]["status"] == "planned"


def test_no_expectations_reports_no_invented_totals(scene):
    planner, _, _, _ = setup_plan(scene)
    with second_owner(scene) as newcomer:
        empty = planner.read(newcomer)
    assert (empty["has_expectations"], empty["occurrences"], empty["currencies"]) == (
        False,
        [],
        [],
    )
