"""The per-Business read budget: how many provider reads a Business may start
today and this month, whichever channel the receipt came from.

Charged at the one place a read is about to start (``DocumentsService.resume``,
just before the provider is reached), so web uploads, email, WhatsApp, "Leer de
nuevo" and a worker retry all count once. The check and the count are one step:
in Postgres under a per-Business advisory lock, in memory under one lock.
"""

from __future__ import annotations

import threading
from datetime import date, datetime
from typing import Literal

from loguru import logger
from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from argus.domain.ingestion.email_intake.budget import business_day
from argus.settings_names import setting_aliases

ReadBudgetRefusal = Literal["business_read_budget_day", "business_read_budget_month"]
READ_BUDGET_REFUSALS: frozenset[str] = frozenset(
    {"business_read_budget_day", "business_read_budget_month"}
)


class ReadBudgetSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)
    per_day: int = Field(
        default=300, ge=1, validation_alias=setting_aliases("BUSINESS_READS_PER_DAY")
    )
    per_month: int = Field(
        default=2000, ge=1, validation_alias=setting_aliases("BUSINESS_READS_PER_MONTH")
    )


def load_read_budget_settings() -> ReadBudgetSettings:
    """Read the budget settings, or the defaults when they cannot be read."""

    try:
        return ReadBudgetSettings()
    except ValidationError:
        logger.warning(
            "Business read budget settings are invalid; the defaults apply",
            failure_mode="ValidationError",
        )
        return ReadBudgetSettings.model_construct(per_day=300, per_month=2000)


def month_start(day: date) -> date:
    return day.replace(day=1)


def next_month_start(day: date) -> date:
    if day.month == 12:
        return date(day.year + 1, 1, 1)
    return date(day.year, day.month + 1, 1)


def refusal(
    settings: ReadBudgetSettings, today: int, month: int
) -> ReadBudgetRefusal | None:
    if today >= settings.per_day:
        return "business_read_budget_day"
    if month >= settings.per_month:
        return "business_read_budget_month"
    return None


def _log_refusal(business_id: str, day: date, code: str, today: int, month: int) -> None:
    logger.info(
        "Business read budget refused a read; business={} day={} reason={} "
        "today={} month={}",
        business_id,
        day.isoformat(),
        code,
        today,
        month,
    )


class InMemoryReadBudget:
    def __init__(self, settings: ReadBudgetSettings | None = None) -> None:
        self.settings = settings or load_read_budget_settings()
        self._reads: dict[tuple[str, date], int] = {}
        self._lock = threading.Lock()

    def charge(self, business_id: str, now: datetime) -> ReadBudgetRefusal | None:
        day = business_day(now)
        with self._lock:
            today = self._reads.get((business_id, day), 0)
            month = sum(
                reads
                for (business, used), reads in self._reads.items()
                if business == business_id and month_start(used) == month_start(day)
            )
            refused = refusal(self.settings, today, month)
            if refused is None:
                self._reads[(business_id, day)] = today + 1
            else:
                _log_refusal(business_id, day, refused, today, month)
            return refused


class PostgresReadBudget:
    def __init__(self, pool, settings: ReadBudgetSettings | None = None) -> None:  # noqa: ANN001
        self._pool = pool
        self.settings = settings or load_read_budget_settings()

    def charge(self, business_id: str, now: datetime) -> ReadBudgetRefusal | None:
        day = business_day(now)
        with self._pool.connection() as connection, connection.transaction():
            # One charge per Business at a time, so the count read here still
            # holds when the row is written.
            connection.execute(
                "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"business_read_budget:{business_id}",),
            )
            today, month = connection.execute(
                "select coalesce(sum(reads) filter (where day=%s), 0), "
                "coalesce(sum(reads), 0) from public.business_read_daily_usage "
                "where business_id=%s and day >= %s and day < %s",
                (day, business_id, month_start(day), next_month_start(day)),
            ).fetchone()
            refused = refusal(self.settings, int(today), int(month))
            if refused is None:
                connection.execute(
                    "insert into public.business_read_daily_usage(business_id, day, reads) "
                    "values (%s, %s, 1) on conflict (business_id, day) do update "
                    "set reads=business_read_daily_usage.reads + 1",
                    (business_id, day),
                )
            else:
                _log_refusal(business_id, day, refused, int(today), int(month))
            return refused
