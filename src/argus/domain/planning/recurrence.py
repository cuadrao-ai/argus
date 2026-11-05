"""Calendar recurrence preserves the original monthly anchors."""

from calendar import monthrange
from datetime import date, timedelta

from argus.domain.planning.schemas import Schedule


def dates(schedule: Schedule, until: date) -> list[date]:
    start = schedule.start_date
    end = min(until, schedule.end_date or until)
    if start > end:
        return []
    if schedule.cadence == "once":
        return [start]
    if schedule.cadence in {"weekly", "every_two_weeks"}:
        step = 7 if schedule.cadence == "weekly" else 14
        return [start + timedelta(days=n) for n in range(0, (end - start).days + 1, step)]
    anchors = schedule.month_days or [start.day]
    year, month = start.year, start.month
    result = []
    while date(year, month, 1) <= end:
        last = monthrange(year, month)[1]
        result.extend(
            sorted(
                {
                    date(year, month, min(day, last))
                    for day in anchors
                    if start <= date(year, month, min(day, last)) <= end
                }
            )
        )
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return result
