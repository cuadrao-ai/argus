"""The read breaker: when the provider keeps failing, every send stops for a
cooldown, then one read probes it.

The state is one row, so every worker and every new deploy agree. The rules
are the four pure functions below; a store only loads the state, applies one
of them under a lock and saves the result. A read the breaker holds back was
never sent, so it is charged nothing. Nothing here runs on a timer: the state
moves only when a read asks to be sent or reports how its call ended.

Only the probe moves an open breaker. Its admission carries the probe's id,
and the call reports its end with that id. A call admitted before the breaker
opened, or a probe that was given up, carries no id or an old one: its late
answer does not close the breaker and its late failure does not restart the
cooldown.

Every admitted call ends at the breaker once (``AdmittedCall``): it failed for
now, the provider answered, or it was never sent. An answer is any end of a
sent call that is not a failure for now, a wrong answer and a refused key
included: the provider is up, so the probe's answer closes the breaker. A
probe that was never sent gives its turn back, and the next read probes.
"""

from __future__ import annotations

import threading
import uuid
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
    open breaker was sent, and ``probe_id`` names that probe."""

    failures: tuple[datetime, ...] = ()
    opened_at: datetime | None = None
    probe_at: datetime | None = None
    probe_id: str | None = None


@dataclass(frozen=True)
class Admission:
    """The answer to a read that asks to be sent. ``until`` set: held back,
    ask again then. ``probe`` set: sent as the probe of an open breaker; the
    call reports its end with it."""

    until: datetime | None = None
    probe: str | None = None


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
    state: BreakerState, now: datetime, probe_id: str
) -> tuple[BreakerState, Admission]:
    """Ask to send one read. The first to ask after the cooldown is the probe,
    named ``probe_id``."""
    until = paused_until(state, now)
    if until is not None or state.opened_at is None:
        return state, Admission(until=until)
    return replace(state, probe_at=now, probe_id=probe_id), Admission(probe=probe_id)


def _current_probe(state: BreakerState, probe: str | None) -> bool:
    return probe is not None and probe == state.probe_id


def failed(
    state: BreakerState, now: datetime, probe: str | None = None
) -> BreakerState:
    """A provider call failed. Enough of them in the window open a closed
    breaker. Only the failure of the current probe moves an open one: it
    starts the cooldown again."""
    if state.opened_at is not None:
        return BreakerState(opened_at=now) if _current_probe(state, probe) else state
    recent = (*(at for at in state.failures if at > now - WINDOW), now)
    if len(recent) >= BREAKER_FAILURES:
        return BreakerState(opened_at=now)
    return replace(state, failures=recent)


def succeeded(state: BreakerState, probe: str | None = None) -> BreakerState:
    """A provider call answered. Only the answer of the current probe closes
    an open breaker."""
    return BreakerState() if _current_probe(state, probe) else state


def unsent(state: BreakerState, probe: str | None = None) -> BreakerState:
    """A call was admitted and never sent. The current probe gives its turn
    back: the breaker stays open, its cooldown as it was, and the next read to
    ask probes."""
    if not _current_probe(state, probe):
        return state
    return replace(state, probe_at=None, probe_id=None)


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
        if after.opened_at == before.opened_at:
            logger.warning("document_read_breaker_probe_unsent")
        else:
            logger.error("document_read_breaker_probe_failed")
    elif before.probe_at != after.probe_at:
        logger.warning("document_read_breaker_probe_sent")


class ReadBreaker(Protocol):
    def paused_until(self, now: datetime) -> datetime | None:
        """Read only: when a read may next be sent, or ``None`` for now."""
        ...

    def admit(self, now: datetime) -> Admission:
        """Ask to send one read."""
        ...

    def failed(self, now: datetime, probe: str | None = None) -> None:
        """The call admitted with ``probe`` failed."""
        ...

    def succeeded(self, now: datetime, probe: str | None = None) -> None:
        """The call admitted with ``probe`` answered."""
        ...

    def unsent(self, now: datetime, probe: str | None = None) -> None:
        """The call admitted with ``probe`` was never sent."""
        ...


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

    def admit(self, now: datetime) -> Admission:
        with self._lock:
            after, admission = admitted(self.state, now, uuid.uuid4().hex)
            self._move(after)
            return admission

    def failed(self, now: datetime, probe: str | None = None) -> None:
        with self._lock:
            self._move(failed(self.state, now, probe))

    def succeeded(self, now: datetime, probe: str | None = None) -> None:
        with self._lock:
            self._move(succeeded(self.state, probe))

    def unsent(self, now: datetime, probe: str | None = None) -> None:
        with self._lock:
            self._move(unsent(self.state, probe))


_COLUMNS = "failures, opened_at, probe_at, probe_id"
_TABLE = "public.document_read_breaker"


class PostgresReadBreaker:
    """The one row of ``document_read_breaker``. A closed breaker costs a read
    one select and a successful call nothing; a write happens only when a call
    fails or the breaker changes state."""

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
                    f"update {_TABLE} set failures=%s, opened_at=%s, probe_at=%s, "
                    "probe_id=%s",
                    (
                        list(after.failures),
                        after.opened_at,
                        after.probe_at,
                        after.probe_id,
                    ),
                )
        _log(before, after)
        return after

    def paused_until(self, now: datetime) -> datetime | None:
        return paused_until(self._load(), now)

    def admit(self, now: datetime) -> Admission:
        if self._load().opened_at is None:
            return Admission()
        answer: list[Admission] = []

        def move(state: BreakerState) -> BreakerState:
            after, admission = admitted(state, now, uuid.uuid4().hex)
            answer.append(admission)
            return after

        self._apply(move)
        return answer[0]

    def failed(self, now: datetime, probe: str | None = None) -> None:
        self._apply(lambda state: failed(state, now, probe))

    def succeeded(self, now: datetime, probe: str | None = None) -> None:
        # Only a probe's answer can move the breaker: any other costs nothing.
        if probe is not None:
            self._apply(lambda state: succeeded(state, probe))

    def unsent(self, now: datetime, probe: str | None = None) -> None:
        if probe is not None:
            self._apply(lambda state: unsent(state, probe))


def ask_breaker(
    breaker: ReadBreaker | None, ask: str, now: datetime, *probe: str | None
) -> datetime | Admission | None:
    """Ask the breaker (``paused_until``, ``admit``) or tell it how the call
    admitted with ``probe`` ended (``failed``, ``succeeded``, ``unsent``). A
    breaker that cannot be reached never stops a read: the failure is logged
    and the read goes on."""
    if breaker is None:
        return None
    try:
        return getattr(breaker, ask)(now, *probe)
    except Exception as error:
        logger.warning(
            "document_read_breaker_unavailable ask={} failure_mode={}",
            ask,
            type(error).__name__,
        )
        return None


class AdmittedCall:
    """One call the breaker admitted, from its admission to its end. However
    it ends, the breaker hears it once: an ``end`` after the first does
    nothing. ``sent`` is set once nothing here can stop the call any more."""

    def __init__(self, breaker: ReadBreaker | None, admission: Admission) -> None:
        self._breaker, self._probe = breaker, admission.probe
        self.sent = False
        self._ended = False

    def end(self, now: datetime, answered: bool) -> None:
        """The call ended: the provider ``answered`` it or it failed for now.
        A call that was never sent says so instead."""
        if self._ended:
            return
        self._ended = True
        ask = "unsent" if not self.sent else "succeeded" if answered else "failed"
        ask_breaker(self._breaker, ask, now, self._probe)
