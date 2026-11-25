"""The per-Business read budget: how many provider reads a Business may start
today and this month, whichever channel the receipt came from.

Charged at the one place a read is about to start (``DocumentsService.resume``,
just before the provider is reached), so web uploads, email, WhatsApp, "Leer de
nuevo" and a worker retry all count once. The check and the count are one step:
in Postgres under a per-Business advisory lock, in memory under one lock.
"""

from __future__ import annotations

import threading
from datetime import date, datetime, time
from typing import Any, Literal

from loguru import logger
from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from argus.domain.ingestion.email_intake.budget import BUSINESS_ZONE, business_day
from argus.settings_names import setting_aliases

HELD_READ_REFUSAL = "whatsapp_held_read_budget_day"
HandOver = Literal["transferred", "business_full", "no_held_read"]

ReadBudgetRefusal = Literal["business_read_budget_day", "business_read_budget_month"]
READ_BUDGET_REFUSALS: frozenset[str] = frozenset(
    {"business_read_budget_day", "business_read_budget_month", HELD_READ_REFUSAL}
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


def window_start(code: str, now: datetime) -> datetime:
    """When the budget that refuses with ``code`` last started over: the start
    of ``now``'s Santo Domingo day, or of its month. A read refused before it
    is no longer held by that refusal."""

    day = business_day(now)
    if code == "business_read_budget_month":
        day = month_start(day)
    return datetime.combine(day, time.min, tzinfo=BUSINESS_ZONE)


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
            return _charge_business(connection, business_id, day, self.settings)


def _charge_business(
    connection: Any, business_id: str, day: date, settings: ReadBudgetSettings
) -> ReadBudgetRefusal | None:
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
    refused = refusal(settings, int(today), int(month))
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


def _held_limit() -> int:
    from argus.domain.ingestion.whatsapp.config import load_whatsapp_settings

    return load_whatsapp_settings().held_reads_per_day


class InMemoryHeldReadBudget:
    def __init__(
        self, business: InMemoryReadBudget, *, per_day: int | None = None
    ) -> None:
        self.business = business
        self.per_day = _held_limit() if per_day is None else per_day
        self._reads: dict[tuple[str, date], int] = {}
        self._lock = threading.Lock()

    def charge(self, user_id: str, now: datetime) -> str | None:
        key = user_id, business_day(now)
        with self._lock:
            reads = self._reads.get(key, 0)
            if reads >= self.per_day:
                return HELD_READ_REFUSAL
            self._reads[key] = reads + 1
        return None

    def hand_over(
        self,
        user_id: str,
        business_id: str,
        now: datetime,
        *,
        charged_at: datetime | None = None,
    ) -> HandOver:
        """Transfer the named charge, or the oldest outstanding charge.

        A specific read supplies its actual charge instant, not held_at.
        Its caller settles once under the held-file assignment lock.
        """
        with self._lock:
            day = (
                business_day(charged_at)
                if charged_at
                else min(
                    (
                        used
                        for (user, used), reads in self._reads.items()
                        if user == user_id and reads > 0 and used <= business_day(now)
                    ),
                    default=None,
                )
            )
            key = user_id, day
            if day is None or not self._reads.get(key, 0):
                return "no_held_read"
            if self.business.charge(business_id, now) is not None:
                return "business_full"
            self._reads[key] -= 1
            return "transferred"


class PostgresHeldReadBudget:
    def __init__(
        self,
        pool: Any,
        settings: ReadBudgetSettings | None = None,
        *,
        per_day: int | None = None,
    ) -> None:
        self._pool = pool
        self.settings = settings or load_read_budget_settings()
        self.per_day = _held_limit() if per_day is None else per_day

    @staticmethod
    def _lock(db: Any, user_id: str) -> None:
        db.execute(
            "select pg_advisory_xact_lock(hashtextextended(%s,0))",
            (f"whatsapp_held_read_budget:{user_id}",),
        )

    def charge(self, user_id: str, now: datetime) -> str | None:
        day = business_day(now)
        with self._pool.connection() as db, db.transaction():
            self._lock(db, user_id)
            row = db.execute(
                "select reads from public.whatsapp_held_read_usage where user_id=%s and day=%s",
                (user_id, day),
            ).fetchone()
            if row is not None and row[0] >= self.per_day:
                return HELD_READ_REFUSAL
            db.execute(
                "insert into public.whatsapp_held_read_usage(user_id,day,reads) values(%s,%s,1) on conflict(user_id,day) do update set reads=whatsapp_held_read_usage.reads+1",
                (user_id, day),
            )
        return None

    def hand_over(
        self,
        user_id: str,
        business_id: str,
        now: datetime,
        *,
        charged_at: datetime | None = None,
    ) -> HandOver:
        """Move a charge atomically; bind the pool to include caller settlement.

        Specific reads name their actual charge instant. Without one, transfer
        the oldest outstanding held charge. Never infer the day from held_at.
        """
        with self._pool.connection() as db, db.transaction():
            self._lock(db, user_id)
            predicate = "day=%s" if charged_at else "day<=%s"
            row = db.execute(
                "select day from public.whatsapp_held_read_usage where user_id=%s "
                f"and {predicate} and reads>0 order by day limit 1",
                (user_id, business_day(charged_at or now)),
            ).fetchone()
            if row is None:
                return "no_held_read"
            if (
                _charge_business(db, business_id, business_day(now), self.settings)
                is not None
            ):
                return "business_full"
            db.execute(
                "update public.whatsapp_held_read_usage set reads=reads-1 where user_id=%s and day=%s",
                (user_id, row[0]),
            )
            return "transferred"
