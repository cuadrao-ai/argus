"""Daily admission and per-fetch reservations, owned by the receiving address."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Protocol
from zoneinfo import ZoneInfo

from loguru import logger

from argus.domain.ingestion.documents.config import SOURCE_MAX_BYTES


@dataclass(frozen=True)
class DailyEmailBudget:
    messages: int
    bytes: int

    def blocked(self, messages: int, used_bytes: int, new_messages: int) -> str | None:
        if messages + new_messages > self.messages:
            return "email_daily_message_budget"
        if used_bytes + SOURCE_MAX_BYTES > self.bytes:
            return "email_daily_byte_budget"
        return None


@dataclass(frozen=True)
class FetchReservation:
    token: str
    day: date
    route_id: str


class EmailBudgetWait(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class FetchBudget(Protocol):
    async def reserve(self) -> FetchReservation: ...

    async def settle(self, reservation: FetchReservation, actual_bytes: int) -> None: ...


BUSINESS_ZONE = ZoneInfo("America/Santo_Domingo")


def business_day(now: datetime) -> date:
    return now.astimezone(BUSINESS_ZONE).date()


def next_business_day(now: datetime) -> datetime:
    local = now.astimezone(BUSINESS_ZONE)
    start = datetime.combine(
        local.date() + timedelta(days=1), datetime.min.time(), tzinfo=BUSINESS_ZONE
    )
    return start.astimezone(timezone.utc)


def log_budget_wait(
    route_id: str, now: datetime, code: str, messages: int, bytes_used: int
) -> None:
    day = business_day(now).isoformat()
    logger.info(
        "Email receiving paused until the next business day; "
        "route={} day={} reason={} messages={} bytes={}",
        route_id,
        day,
        code,
        messages,
        bytes_used,
    )
