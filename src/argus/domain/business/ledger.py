"""Saved expenses and their per-currency totals, read from canonical activity.

Each currency is totaled on its own. Nothing is converted.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from argus.domain.recording.currency import format_minor_units


def _when(value: datetime | str) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)


def occurred_on(activity: Mapping[str, Any]) -> date:
    """The calendar day the person recorded it on, in its own time zone."""

    return (
        _when(activity["occurred_at"]).astimezone(ZoneInfo(activity["time_zone"])).date()
    )


def expense_activities(
    activities: Iterable[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    return kind_activities(activities, "expense")


def kind_activities(
    activities: Iterable[Mapping[str, Any]], kind: str
) -> list[Mapping[str, Any]]:
    return [item for item in activities if item["kind"] == kind]


def today() -> date:
    """The Business day: the one clock's instant, read in the recording time zone.

    The instant comes from the clock every "today" derives from, so a frozen
    clock freezes this day too; the calendar is Santo Domingo's, never the
    host's or the browser's."""

    from argus.domain.clock import new_york_now
    from argus.domain.recording.records import DEFAULT_TIME_ZONE

    return new_york_now().astimezone(ZoneInfo(DEFAULT_TIME_ZONE)).date()


def expenses(
    activities: Iterable[Mapping[str, Any]],
    receipt_of: Mapping[str, str],
    start: date,
    end: date,
    *,
    kind: str = "expense",
) -> list[dict[str, Any]]:
    """Expenses (or another ``kind``, as a venta's income) that happened in
    ``[start, end]``, newest first."""

    items = [
        {
            "id": item["activity_id"],
            "merchant": item["note"],
            "amount": item["amount"],
            "amount_minor": item["amount_minor"],
            "currency": item["currency"],
            "category_id": item["category_id"],
            "account_id": item["legs"][0]["account_id"] if item["legs"] else None,
            **({"funding": item["funding"]} if item.get("funding") else {}),
            "occurred_on": occurred_on(item),
            "receipt_id": receipt_of.get(item["activity_id"]),
        }
        for item in kind_activities(activities, kind)
        if start <= occurred_on(item) <= end
    ]
    return sorted(items, key=lambda item: (item["occurred_on"], item["id"]), reverse=True)


def totals(items: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    sums: dict[str, tuple[int, int]] = {}
    for item in items:
        minor, count = sums.get(item["currency"], (0, 0))
        sums[item["currency"]] = (minor + item["amount_minor"], count + 1)
    return [
        {
            "currency": currency,
            "amount": format_minor_units(minor, currency),
            "count": count,
        }
        for currency, (minor, count) in sorted(sums.items())
    ]


def recorded_at(activities: Iterable[Mapping[str, Any]]) -> dict[str, datetime]:
    return {
        item["activity_id"]: _when(item["recorded_at"])
        for item in expense_activities(activities)
    }
