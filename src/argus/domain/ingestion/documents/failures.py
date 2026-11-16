"""What a failed receipt read is, and how long its next take waits.

``classify`` is the one place a failure gets its kind. ``retry_wait`` is the
one place the numbers in ``config`` become a wait. A transient failure is
taken again through the queue; every other kind ends the read at once.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Literal

import httpx

from argus.domain.ingestion.documents.config import (
    MAX_PROVIDER_CALLS,
    RETRY_BASE_SECONDS,
    RETRY_FACTOR,
    RETRY_MAX_WAIT_SECONDS,
)
from argus.llm.openrouter_transport import timed_out

# transient: the provider may answer next time (a timeout, an interrupted
# connection, a 5xx, a 429). paused: the breaker held the read back before it
# was sent. config: our key or model is wrong, so no receipt can be read.
# permanent: this receipt cannot be read as it is.
FailureKind = Literal["transient", "paused", "config", "permanent"]

READS_PAUSED = "document_reads_paused"
# The searchable tag of the error log a config failure writes.
CONFIG_ALERT = "document_read_config_alert"
_CONFIG_CODES = frozenset({"missing_vision_model", "missing_api_key", "missing_model"})
_TRANSIENT_STATUS = frozenset({408, 429})
_CONFIG_STATUS = frozenset({401, 403})


@dataclass(frozen=True)
class ReadFailure:
    kind: FailureKind
    # Seconds the provider (``Retry-After``) or the breaker asks the next take
    # to wait.
    wait_seconds: float | None = None


@dataclass(frozen=True)
class Requeue:
    """The next take of a read whose failure the queue takes again.
    ``charged`` is false for a read the breaker held back."""

    wait_seconds: float
    charged: bool


def _retry_after(response: object) -> float | None:
    headers = getattr(response, "headers", None)
    value = headers.get("retry-after") if headers is not None else None
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            moment = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        seconds = (moment - datetime.now(timezone.utc)).total_seconds()
    return max(seconds, 0.0) if seconds == seconds else None


def classify(error: BaseException) -> ReadFailure:
    """The kind of a failed read. An error that already carries its kind keeps
    it. A coded refusal of ours is permanent unless it names our own setup. A
    raw provider error is transient only when the provider may answer next
    time; an answer that came back wrong is never read again."""

    carried = getattr(error, "read_failure", None)
    if isinstance(carried, ReadFailure):
        return carried
    code = getattr(error, "code", None)
    if isinstance(code, str):
        return ReadFailure("config" if code in _CONFIG_CODES else "permanent")
    if timed_out(error):
        return ReadFailure("transient")
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None)
    if isinstance(status, int) and not isinstance(status, bool):
        if status in _TRANSIENT_STATUS or status >= 500:
            return ReadFailure("transient", _retry_after(response))
        return ReadFailure("config" if status in _CONFIG_STATUS else "permanent")
    if isinstance(error, httpx.TransportError):
        return ReadFailure("transient")
    return ReadFailure("permanent")


def retry_wait(
    calls: int,
    waited: float,
    asked: float | None = None,
    rand: Callable[[], float] = random.random,
) -> float | None:
    """Seconds until the next take of a read that made ``calls`` provider
    calls and already waited ``waited`` seconds, or ``None`` when it gets no
    more. Half of each step is fixed and half random. A wait the provider
    ``asked`` for is never cut short: a read that cannot wait that long inside
    the total stops instead."""

    if calls >= MAX_PROVIDER_CALLS:
        return None
    step = RETRY_BASE_SECONDS * RETRY_FACTOR ** max(calls - 1, 0)
    wait = max(step / 2 + rand() * step / 2, asked or 0.0)
    return wait if waited + wait <= RETRY_MAX_WAIT_SECONDS else None
