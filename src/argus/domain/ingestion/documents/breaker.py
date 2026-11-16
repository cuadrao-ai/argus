"""The read breaker: when the provider keeps failing, every send stops for a
cooldown, then one read probes it.

The state is one row, so every worker and every new deploy agree. The rules
are the four pure functions below; a store only loads the state, applies one
of them under a lock and saves the result. A read the breaker holds back was
never sent, so it is charged nothing. Nothing here runs on a timer: the state
moves only when a read asks to be sent or reports how its call ended.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Protocol

from loguru import logger

from argus.domain.ingestion.documents.config import (
    BREAKER_COOLDOWN_SECONDS,
    BREAKER_FAILURES,
    BREAKER_WINDOW_SECONDS,
    RETRY_BASE_SECONDS,
    read_seconds,
)

WINDOW = timedelta(seconds=BREAKER_WINDOW_SECONDS)
COOLDOWN = timedelta(seconds=BREAKER_COOLDOWN_SECONDS)
# A read held back while another probes asks again this soon.
_ASK_AGAIN = timedelta(seconds=RETRY_BASE_SECONDS)


@dataclass(frozen=True)
class BreakerState:
    """Closed while ``opened_at`` is ``None``. ``failures`` are the recent
    failed calls of a closed breaker; ``probe_at`` is when the one probe of an
    open breaker was sent."""

    failures: tuple[datetime, ...] = ()
    opened_at: datetime | None = None
    probe_at: datetime | None = None


def _probe_window() -> timedelta:
    # A probe that never reports back (its worker died) is given up after the
    # longest one take can last.
    return timedelta(seconds=read_seconds())


def paused_until(state: BreakerState, now: datetime) -> datetime | None:
    """When a held read may ask again, or ``None`` when a read may be sent."""
    if state.opened_at is None:
        return None
    if now < state.opened_at + COOLDOWN:
        return state.opened_at + COOLDOWN
    if state.probe_at is not None and now < state.probe_at + _probe_window():
        return min(state.probe_at + _probe_window(), now + _ASK_AGAIN)
    return None


def admitted(
    state: BreakerState, now: datetime
) -> tuple[BreakerState, datetime | None]:
    """Ask to send one read. The first to ask after the cooldown is the probe."""
    until = paused_until(state, now)
    if until is not None or state.opened_at is None:
        return state, until
    return replace(state, probe_at=now), None


def failed(state: BreakerState, now: datetime) -> BreakerState:
    """A provider call failed. Enough of them in the window open the breaker;
    a failed probe starts the cooldown again. A call sent before the breaker
    opened changes nothing when it fails late."""
    if state.opened_at is not None:
        return state if state.probe_at is None else BreakerState(opened_at=now)
    recent = (*(at for at in state.failures if at > now - WINDOW), now)
    if len(recent) >= BREAKER_FAILURES:
        return BreakerState(opened_at=now)
    return replace(state, failures=recent)


def succeeded(state: BreakerState) -> BreakerState:
    """A provider call answered: an open breaker closes."""
    return state if state.opened_at is None else BreakerState()


def _log(before: BreakerState, after: BreakerState) -> None:
    if before.opened_at is None and after.opened_at is not None:
        logger.error(
            "document_read_breaker_opened failures={} window_seconds={} "
            "cooldown_seconds={}",
            BREAKER_FAILURES,
            BREAKER_WINDOW_SECONDS,
            BREAKER_COOLDOWN_SECONDS,
        )
    elif before.opened_at is not None and after.opened_at is None:
        logger.warning("document_read_breaker_closed")
    elif before.probe_at is not None and after.probe_at is None:
        logger.error("document_read_breaker_probe_failed")
    elif before.probe_at != after.probe_at:
        logger.warning("document_read_breaker_probe_sent")


class ReadBreaker(Protocol):
    def paused_until(self, now: datetime) -> datetime | None:
        """Read only: when a read may next be sent, or ``None`` for now."""
        ...

    def admit(self, now: datetime) -> datetime | None:
        """Ask to send one read: ``None`` to send it, else when to ask again."""
        ...

    def failed(self, now: datetime) -> None: ...
    def succeeded(self, now: datetime) -> None: ...


class InMemoryReadBreaker:
    def __init__(self) -> None:
        self.state = BreakerState()
        self._lock = threading.Lock()

    def _move(self, after: BreakerState) -> None:
        _log(self.state, after)
        self.state = after

    def paused_until(self, now: datetime) -> datetime | None:
        with self._lock:
            return paused_until(self.state, now)

    def admit(self, now: datetime) -> datetime | None:
        with self._lock:
            after, until = admitted(self.state, now)
            self._move(after)
            return until

    def failed(self, now: datetime) -> None:
        with self._lock:
            self._move(failed(self.state, now))

    def succeeded(self, now: datetime) -> None:
        with self._lock:
            self._move(succeeded(self.state))


_COLUMNS = "failures, opened_at, probe_at"
_TABLE = "public.document_read_breaker"


class PostgresReadBreaker:
    """The one row of ``document_read_breaker``. A closed breaker costs a read
    one select and a successful call nothing more; a write happens only when a
    call fails or the breaker changes state."""

    def __init__(self, pool) -> None:  # noqa: ANN001
        self._pool = pool

    @staticmethod
    def _state(row: tuple | None) -> BreakerState:
        return BreakerState() if row is None else BreakerState(tuple(row[0]), *row[1:])

    def _load(self) -> BreakerState:
        with self._pool.connection() as connection:
            return self._state(
                connection.execute(f"select {_COLUMNS} from {_TABLE}").fetchone()
            )

    def _apply(self, move) -> BreakerState:  # noqa: ANN001
        with self._pool.connection() as connection, connection.transaction():
            connection.execute(
                f"insert into {_TABLE} default values on conflict do nothing"
            )
            before = self._state(
                connection.execute(
                    f"select {_COLUMNS} from {_TABLE} for update"
                ).fetchone()
            )
            after = move(before)
            if after != before:
                connection.execute(
                    f"update {_TABLE} set failures=%s, opened_at=%s, probe_at=%s",
                    (list(after.failures), after.opened_at, after.probe_at),
                )
        _log(before, after)
        return after

    def paused_until(self, now: datetime) -> datetime | None:
        return paused_until(self._load(), now)

    def admit(self, now: datetime) -> datetime | None:
        if self._load().opened_at is None:
            return None
        until: list[datetime | None] = []

        def move(state: BreakerState) -> BreakerState:
            after, wait = admitted(state, now)
            until.append(wait)
            return after

        self._apply(move)
        return until[0]

    def failed(self, now: datetime) -> None:
        self._apply(lambda state: failed(state, now))

    def succeeded(self, now: datetime) -> None:
        if self._load().opened_at is not None:
            self._apply(succeeded)
