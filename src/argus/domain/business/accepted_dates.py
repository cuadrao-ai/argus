"""Accepted dates at Business input boundaries, separate from saved evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Annotated, Literal

from pydantic import AfterValidator
from pydantic_core import PydanticCustomError

from argus.domain.business import ledger

DateRefusalCode = Literal["business_date_before_minimum", "business_date_after_today"]


@dataclass(frozen=True)
class DateReviewReason:
    code: DateRefusalCode
    min_date: str
    today: str


def reader_date_reason(value: date | None, *, future: bool = False) -> DateReviewReason | None:
    """An implausible read stays evidence and becomes a reason to correct it.

    This also supplies refusal metadata. Neither the reader nor the web owns
    another calculation of the accepted range. February 29 clamps to the last
    day of February when the floor year is not a leap year.
    """
    if value is None:
        return None
    today = ledger.today()
    try:
        minimum = today.replace(year=today.year - 10)
    except ValueError:
        minimum = today.replace(year=today.year - 10, day=28)
    code: DateRefusalCode
    if value < minimum:
        code = "business_date_before_minimum"
    elif not future and value > today:
        code = "business_date_after_today"
    else:
        return None
    return DateReviewReason(code, minimum.isoformat(), today.isoformat())


def _accepted(value: date, *, future: bool = False) -> date:
    reason = reader_date_reason(value, future=future)
    if reason is not None:
        # Codes are machine-readable; the locale files own the refusal sentence.
        raise PydanticCustomError(reason.code, reason.code, {
            "min_date": reason.min_date, "today": reason.today,
        })
    return value


def _due(value: date) -> date:
    return _accepted(value, future=True)


PastBusinessDate = Annotated[date, AfterValidator(_accepted)]
DueDate = Annotated[date, AfterValidator(_due)]
