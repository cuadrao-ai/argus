"""Request-scoped admission for one billable research provider path.

The API owns durable allowance state. Runtime research operations own the
precise point where a cache miss becomes provider work. This context is the
small bridge between them: the first provider path claims capacity, while
later defensive checks in the same turn reuse that result. Provider work that
fails with no usable response gives the claim back, and only a confirmed
release lets the next provider path claim again. The charge stands for the rest
of the turn once provider work was served, was cancelled while it may still be
billing, or could not be released.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Callable, Iterator


@dataclass(frozen=True)
class ResearchAttemptAdmission:
    """Whether this turn may start billable research provider work.

    ``period_start`` names the allowance period an admitted claim charged, so
    that charge can be returned exactly."""

    available: bool
    guest_exhausted: bool = False
    registered_exhausted: bool = False
    period_start: str | None = None


class ResearchCapacityExhausted(RuntimeError):
    """A provider path lost the atomic capacity claim."""

    def __init__(self, admission: ResearchAttemptAdmission) -> None:
        super().__init__("Research capacity exhausted")
        self.admission = admission


@dataclass
class _AdmissionScope:
    claim: Callable[[], ResearchAttemptAdmission]
    release: Callable[[ResearchAttemptAdmission], bool] | None = None
    result: ResearchAttemptAdmission | None = None
    charge_stands: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)


_CURRENT_SCOPE: ContextVar[_AdmissionScope | None] = ContextVar(
    "argus_research_attempt_admission",
    default=None,
)


@contextmanager
def research_attempt_admission_context(
    claim: Callable[[], ResearchAttemptAdmission],
    release: Callable[[ResearchAttemptAdmission], bool] | None = None,
) -> Iterator[None]:
    """Install the API's atomic claim for the duration of one chat turn.

    ``release`` gives an admitted claim back and returns whether the charge went
    back; it must never raise."""

    token = _CURRENT_SCOPE.set(_AdmissionScope(claim=claim, release=release))
    try:
        yield
    finally:
        _CURRENT_SCOPE.reset(token)


def claim_current_research_attempt() -> ResearchAttemptAdmission:
    """Claim once per request; non-API callers remain dependency-free."""

    scope = _CURRENT_SCOPE.get()
    if scope is None:
        return ResearchAttemptAdmission(available=True)
    with scope.lock:
        if scope.result is None:
            scope.result = scope.claim()
        return scope.result


@contextmanager
def admitted_provider_work() -> Iterator[None]:
    """One provider call under this turn's claim.

    A call that returns was served, and a cancelled call may still be billing,
    so either keeps the charge. A call that fails with an error gives the claim
    back, unless the charge already stands."""

    try:
        yield
    except Exception:
        _release_unserved_claim()
        raise
    except BaseException:
        _keep_the_charge()
        raise
    _keep_the_charge()


def _keep_the_charge() -> None:
    scope = _CURRENT_SCOPE.get()
    if scope is not None:
        with scope.lock:
            scope.charge_stands = True


def _release_unserved_claim() -> None:
    scope = _CURRENT_SCOPE.get()
    if scope is None or scope.release is None:
        return
    with scope.lock:
        admission = scope.result
        if scope.charge_stands or admission is None or not admission.available:
            return
        # Held across the release, so no path claims while the charge is in doubt.
        if scope.release(admission) is True:
            # A later provider path in this turn claims again.
            scope.result = None
        else:
            scope.charge_stands = True
