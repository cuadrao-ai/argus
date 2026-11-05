"""Amount-only edits preserve the canonical cadence and fulfilled occurrence."""

import calendar
from datetime import date, timedelta

import pytest
from argus.domain.household import planning_schemas as wire
from argus.domain.recording.errors import RecordingInputError

from tests.household.financial_fixtures import DSN, NOW, key
from tests.household.shared_plan_fixtures import (
    command,
    create,
    get,
    money,
    request,
    scene,
)

pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL required")


def edit(s, p, **fields):
    return s["plans"].edit(
        s["a"],
        s["hid"],
        "goal",
        str(p["ref"]["id"]),
        command(s, s["a"], p, wire.EditPlan, definition=fields),
        key(),
    )["plan"]


@pytest.mark.parametrize("fulfilled", [False, True])
def test_monthly_amount_only_keeps_anchor_and_past_occurrence(lane, fulfilled):
    s = scene(lane)
    today = NOW.date()
    previous_month = today.replace(day=1) - timedelta(days=1)
    anchor = today.day
    start = previous_month.replace(day=min(anchor, previous_month.day))
    p = create(
        s,
        "goal",
        contribution_plan=dict(
            source_account_id=s["aa"],
            amount="100",
            schedule=dict(
                cadence="monthly", start_date=start.isoformat(), month_days=[anchor]
            ),
        ),
    )
    oid = next(o["id"] for o in p["occurrences"] if str(o["date"]) == today.isoformat())
    if fulfilled:
        money(
            s, s["a"], p, request("transfer", s["aa"], "100", s["ad"]), "goal_saving", oid
        )
    before = get(s, s["a"], p)
    renamed = edit(s, p, name="Renamed shared goal")
    assert renamed["definition"]["schedule"] == before["definition"]["schedule"]
    assert {o["id"] for o in renamed["occurrences"]} == {
        o["id"] for o in before["occurrences"]
    }
    cutoff = renamed["definition"]["earliest_effective_date"]
    changed = edit(s, p, planned_contribution_amount="60", effective_date=cutoff)
    assert changed["definition"]["planned_contribution_minor"] == "6000"
    assert changed["definition"]["schedule"]["month_days"] == [anchor]
    next_month = today.month % 12 + 1
    next_year = today.year + (today.month == 12)
    future_date = date(
        next_year, next_month, min(anchor, calendar.monthrange(next_year, next_month)[1])
    )
    expected_first = future_date if fulfilled else today
    assert changed["definition"]["schedule"]["start_date"] == expected_first.isoformat()
    future = next(
        o for o in changed["occurrences"] if str(o["date"]) == future_date.isoformat()
    )
    assert future["amount_minor"] == "6000"
    if fulfilled:
        retained = next(o for o in changed["occurrences"] if o["id"] == oid)
        assert retained["applied_minor"] == "10000" and retained["remaining_minor"] == "0"


def test_fulfilled_once_name_edit_succeeds_and_amount_edit_is_atomic_finished(lane):
    s = scene(lane)
    p = create(s, "goal")
    oid = p["occurrences"][0]["id"]
    money(s, s["a"], p, request("transfer", s["aa"], "100", s["ad"]), "goal_saving", oid)
    renamed = edit(s, p, name="Completed goal")
    assert renamed["occurrences"][0]["id"] == oid
    assert renamed["occurrences"][0]["applied_minor"] == "10000"
    with pytest.raises(RecordingInputError) as error:
        edit(
            s,
            p,
            planned_contribution_amount="60",
            effective_date=renamed["definition"]["earliest_effective_date"],
        )
    assert error.value.code == "schedule_finished"
    assert get(s, s["a"], p) == renamed
