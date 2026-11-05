"""The opening-balance anchor, its append-only revisions, and the balance read.

A balance is derived on read from the current revision. With no opening the
balance is unknown; unknown is never zero. A correction appends a revision that
carries unchanged fields forward and keeps its reason and author.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from argus.domain.recording.accounts import signed_to_owner
from argus.domain.recording.currency import parse_minor_units
from argus.domain.recording.errors import RecordingInputError

DEFAULT_TIME_ZONE = "America/Santo_Domingo"
REASON_MAX_CODE_POINTS = 200
OPENING_KIND = "opening_balance"


@dataclass(frozen=True)
class OpeningRevision:
    revision: int
    amount_minor: int
    as_of: datetime
    time_zone: str
    reason: str | None
    recorded_by: str | None
    recorded_at: datetime
    estimate_basis: str | None = None
    # Recorded as 0 because the person left the balance blank; it never covers activity.
    blank: bool = False


@dataclass(frozen=True)
class OpeningRecord:
    id: str
    account_id: str
    revisions: tuple[OpeningRevision, ...]

    @property
    def current(self) -> OpeningRevision:
        return self.revisions[-1]


@dataclass(frozen=True)
class Balance:
    state: Literal["known", "unknown"]
    amount_minor: int | None = None
    as_of: datetime | None = None
    basis: Literal["opening", "balance_check"] | None = None
    # No activity can exist in this slice, so the unknown read always reports 0
    # recorded since tracking began. The field keeps the read shape stable.
    activity_since_tracking_minor: int = 0


def balance_of(opening: OpeningRecord | None) -> Balance:
    if opening is None:
        return Balance(state="unknown")
    current = opening.current
    return Balance(
        state="known",
        amount_minor=current.amount_minor,
        as_of=current.as_of,
        basis="opening",
    )


@dataclass(frozen=True)
class OpeningWrite:
    """A validated revision body, ready for storage."""

    amount_minor: int
    as_of: datetime
    time_zone: str
    reason: str | None
    estimate_basis: str | None = None
    blank: bool = False


def plan_opening_write(
    *,
    account_type: str,
    currency: str,
    amount: str | None,
    as_of: datetime | None,
    time_zone: str | None,
    reason: str | None,
    current: OpeningRevision | None,
    now: datetime,
) -> OpeningWrite:
    """Validate a first opening or a correction against the current revision.

    A first write needs an amount. A correction needs a reason and at least one
    change; unchanged fields carry forward from the current revision.
    """

    zone = _validate_zone(time_zone, current)
    if current is None:
        if amount is None:
            raise RecordingInputError(
                "field_missing", "a starting balance needs an amount"
            )
        cleaned_reason = _normalize_reason(reason, required=False)
    else:
        if amount is None and as_of is None and time_zone is None:
            raise RecordingInputError(
                "field_missing", "a correction changes the amount, the date or both"
            )
        cleaned_reason = _normalize_reason(reason, required=True)

    if amount is not None:
        amount_minor = signed_to_owner(parse_minor_units(amount, currency), account_type)
    else:
        assert current is not None
        amount_minor = current.amount_minor

    if as_of is not None:
        stamp = _as_instant(as_of)
    elif current is not None:
        stamp = current.as_of
    else:
        stamp = now
    if stamp > now:
        raise RecordingInputError(
            "date_in_future", "a balance date cannot be in the future"
        )
    return OpeningWrite(
        amount_minor=amount_minor,
        as_of=stamp,
        time_zone=zone,
        reason=cleaned_reason,
        estimate_basis=current.estimate_basis if current else None,
    )


def _validate_zone(time_zone: str | None, current: OpeningRevision | None) -> str:
    if time_zone is None:
        return current.time_zone if current is not None else DEFAULT_TIME_ZONE
    try:
        ZoneInfo(time_zone)
    except (ZoneInfoNotFoundError, ValueError):
        raise RecordingInputError(
            "time_zone_invalid", f"{time_zone!r} is not a time zone"
        ) from None
    return time_zone


def _normalize_reason(reason: str | None, *, required: bool) -> str | None:
    trimmed = (reason or "").strip()
    if not trimmed:
        if required:
            raise RecordingInputError(
                "reason_required", "a correction records why it was made"
            )
        return None
    if len(trimmed) > REASON_MAX_CODE_POINTS:
        raise RecordingInputError(
            "reason_invalid", f"a reason has at most {REASON_MAX_CODE_POINTS} characters"
        )
    return trimmed


def _as_instant(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise RecordingInputError("date_invalid", "a balance date needs a UTC offset")
    return value.astimezone(timezone.utc)
