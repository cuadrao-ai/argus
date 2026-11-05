"""Explicit monthly reporting interval shared by every currency subtotal."""

import re
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from argus.domain.recording.errors import RecordingInputError


def period(
    month: str | None, time_zone: str, now: datetime | None = None
) -> dict[str, Any]:
    try:
        zone = ZoneInfo(time_zone)
    except (ZoneInfoNotFoundError, ValueError):
        raise RecordingInputError(
            "time_zone_invalid", "Choose a valid reporting time zone."
        ) from None
    if month is None:
        month = (now or datetime.now(timezone.utc)).astimezone(zone).strftime("%Y-%m")
    try:
        if not re.fullmatch(r"\d{4}-\d{2}", month):
            raise ValueError()
        year, number = map(int, month.split("-"))
        start = datetime(year, number, 1, tzinfo=zone)
        end = datetime(
            year + (number == 12), 1 if number == 12 else number + 1, 1, tzinfo=zone
        )
    except ValueError:
        raise RecordingInputError(
            "month_invalid", "Choose a valid reporting month."
        ) from None
    return {
        "month": month,
        "time_zone": time_zone,
        "start_at": start,
        "end_at_exclusive": end,
    }
