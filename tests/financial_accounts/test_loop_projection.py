from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from argus.domain.recording.errors import RecordingInputError
from argus.domain.recording.loop import (
    CheckRecord,
    Coverage,
    ExpenseRecord,
    ExpenseRevision,
    observations,
    position,
    residuals,
    validate_monotonic,
)
from argus.domain.recording.records import OpeningRecord, OpeningRevision

T = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)
ZONE = "America/Santo_Domingo"


def expense(amount, day, revision=1):
    return ExpenseRecord(
        str(uuid4()),
        "account",
        (
            ExpenseRevision(
                revision,
                amount,
                T + timedelta(days=day),
                ZONE,
                None,
                None,
                None,
                "user",
                T + timedelta(days=5),
            ),
        ),
    )


def opening():
    return OpeningRecord(
        str(uuid4()), "account", (OpeningRevision(1, 1000000, T, ZONE, None, "user", T),)
    )


def check(amount, day):
    return CheckRecord(
        str(uuid4()),
        "account",
        amount,
        T + timedelta(days=day),
        ZONE,
        800000,
        -50000,
        2,
        "user",
        T + timedelta(days=day),
    )


def link(e, observation, value):
    return Coverage(observation.id, observation.revision, e.id, e.current.revision, value)


def test_unknown_expense_does_not_invent_zero_position():
    e = expense(200000, 1)
    assert position(None, (), (e,), ()).amount_minor is None
    assert position(None, (), (e,), ()).activity_since_tracking_minor == -200000


@pytest.mark.parametrize("late_amount,expected_residual", [(20000, -30000), (50000, 0)])
def test_late_included_expense_explains_check_without_charging_twice(
    late_amount, expected_residual
):
    o, c, e = opening(), check(750000, 3), expense(200000, 1)
    late = expense(late_amount, 2)
    a = observations(o, (c,))
    cov = (link(e, a[1], True), link(late, a[1], True))
    assert position(o, (c,), (e, late), cov).amount_minor == 750000
    assert residuals(o, (c,), (e, late), cov)[c.id] == expected_residual
    assert sum(x.current.amount_minor for x in (e, late)) == 200000 + late_amount


def test_new_or_explicitly_excluded_expense_changes_current_position():
    o, c = opening(), check(750000, 3)
    late, new = expense(50000, 2), expense(50000, 4)
    cov = (link(late, observations(o, (c,))[1], False),)
    assert position(o, (c,), (late, new), cov).amount_minor == 650000


def test_two_checks_allocate_late_expense_once_to_its_first_included_interval():
    o, c1, c2 = opening(), check(950000, 2), check(900000, 4)
    late = expense(50000, 1)
    anchors = observations(o, (c1, c2))
    cov = (link(late, anchors[1], True), link(late, anchors[2], True))
    assert residuals(o, (c1, c2), (late,), cov) == {c1.id: 0, c2.id: -50000}
    assert position(o, (c1, c2), (late,), cov).amount_minor == 900000
    with pytest.raises(RecordingInputError, match="included"):
        validate_monotonic(late, anchors, (cov[0], replace(cov[1], included=False)))


def test_same_local_day_requires_coverage_even_when_expense_time_is_later():
    o = opening()
    e = expense(50000, 0)
    e = replace(e, revisions=(replace(e.current, occurred_at=T + timedelta(hours=5)),))
    with pytest.raises(ValueError, match="coverage"):
        position(o, (), (e,), ())
    anchor = observations(o, ())[0]
    assert position(o, (), (e,), (link(e, anchor, True),)).amount_minor == 1000000
