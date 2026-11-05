from datetime import date

import pytest
from argus.domain.planning.recurrence import dates
from argus.domain.planning.schemas import Schedule


@pytest.mark.parametrize("year, february", [(2024, 29), (2025, 28)])
def test_month_end_stays_anchored_after_february(year, february):
    schedule = Schedule(cadence="monthly", start_date=date(year, 1, 31))
    assert dates(schedule, date(year, 3, 31)) == [
        date(year, 1, 31),
        date(year, 2, february),
        date(year, 3, 31),
    ]


def test_quincena_clamps_and_deduplicates():
    schedule = Schedule(
        cadence="twice_monthly", start_date=date(2025, 2, 1), month_days=[30, 31]
    )
    assert dates(schedule, date(2025, 3, 31)) == [
        date(2025, 2, 28),
        date(2025, 3, 30),
        date(2025, 3, 31),
    ]


def test_monthly_recurrence_crosses_year_and_respects_end():
    schedule = Schedule(
        cadence="monthly", start_date=date(2026, 12, 31), end_date=date(2027, 2, 28)
    )
    assert dates(schedule, date(2027, 4, 30)) == [
        date(2026, 12, 31),
        date(2027, 1, 31),
        date(2027, 2, 28),
    ]


def test_month_end_anchor_returns_after_every_short_month_of_a_year():
    schedule = Schedule(cadence="monthly", start_date=date(2025, 1, 31), month_days=[31])
    assert dates(schedule, date(2025, 12, 31)) == [
        date(2025, 1, 31),
        date(2025, 2, 28),
        date(2025, 3, 31),
        date(2025, 4, 30),
        date(2025, 5, 31),
        date(2025, 6, 30),
        date(2025, 7, 31),
        date(2025, 8, 31),
        date(2025, 9, 30),
        date(2025, 10, 31),
        date(2025, 11, 30),
        date(2025, 12, 31),
    ]


def test_every_two_weeks_steps_fourteen_days_and_respects_end():
    schedule = Schedule(
        cadence="every_two_weeks",
        start_date=date(2026, 10, 5),
        end_date=date(2026, 11, 16),
    )
    assert dates(schedule, date(2027, 1, 1)) == [
        date(2026, 10, 5),
        date(2026, 10, 19),
        date(2026, 11, 2),
        date(2026, 11, 16),
    ]


def test_monthly_without_month_days_follows_the_start_day_even_when_it_was_clamped():
    clamped = Schedule(cadence="monthly", start_date=date(2026, 2, 28))
    anchored = Schedule(cadence="monthly", start_date=date(2026, 2, 28), month_days=[31])
    assert dates(clamped, date(2026, 4, 30)) == [
        date(2026, 2, 28),
        date(2026, 3, 28),
        date(2026, 4, 28),
    ]
    assert dates(anchored, date(2026, 4, 30)) == [
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 30),
    ]
