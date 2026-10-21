from __future__ import annotations

import asyncio
import functools
import os
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Iterator
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, ParamSpec, TypeVar

from loguru import logger

from argus.agent_runtime.turn_progress import (
    ProgressAssessment,
    ProgressOutcome,
    ProgressSnapshot,
    assess_progress,
    semantic_progress_fingerprint,
    semantic_progress_snapshot,
)

if TYPE_CHECKING:
    from argus.llm.openrouter import OpenRouterRouteReceipt, OpenRouterTask


DEFAULT_TURN_DEADLINE_SECONDS = 120.0
# Evidence-calibrated production-builder corridor: asset preflight primary and
# fallback, interpretation primary and fallback, focused repair, then
# clarification primary and fallback.
DEFAULT_TURN_CALL_ALLOWANCE = 7
# The research rail's routing classification postdates that calibration. It is
# a required single call, not an enrichment, so with the rail on it holds one
# reserved slot outside the corridor: interpreter audits can never starve the
# router into a silent pre-rail fallback.
_ROUTING_RESERVED_TASK = "knowledge_route"
_EXPLICIT_PROGRESS_TERMINALS: frozenset[ProgressOutcome] = frozenset(
    {
        "clarification",
        "redirected",
        "finished",
        "no_progress",
        "recoverable_failed",
        "terminal_failed",
    }
)

_monotonic = time.monotonic


class RuntimeEventTimeoutError(asyncio.TimeoutError):
    def __init__(self, diagnostics: dict[str, Any]) -> None:
        super().__init__("agent_runtime_event_timeout")
        self.diagnostics = diagnostics


@dataclass(frozen=True)
class ProviderCallPermit:
    task: str
    timeout_seconds: float


@dataclass
class TurnExecutionContext:
    started_monotonic: float
    deadline_monotonic: float
    deadline_seconds: float
    call_allowance: int
    entry_fingerprint: str | None
    calls_reserved: int = 0
    routing_reserved: bool = False
    research_recovery_reserved: bool = False
    last_resort_repair_calls_granted: int = 0
    last_resort_repair_grant_used: int = 0
    repair_approval_grant_used: int = 0
    terminal: ProgressOutcome | None = None
    terminal_reason: str | None = None
    exit_fingerprint: str | None = None
    progress_outcome: ProgressOutcome | None = None
    blocked_tasks: list[str] = field(default_factory=list)
    deadline_exhausted: bool = False
    call_allowance_exhausted: bool = False
    _entry_snapshot: ProgressSnapshot | None = field(default=None, repr=False)

    def remaining_deadline_seconds(self) -> float:
        return max(0.0, self.deadline_monotonic - _monotonic())

    def elapsed_seconds(self) -> float:
        return max(0.0, _monotonic() - self.started_monotonic)

    @property
    def calls_exhausted(self) -> bool:
        return self.call_allowance_exhausted


_ACTIVE_TURN_EXECUTION: ContextVar[TurnExecutionContext | None] = ContextVar(
    "active_turn_execution",
    default=None,
)

# The repair pool: the calls a turn may make after its corridor is exhausted,
# shared by repair work. A last-resort repair draws from it (the only rescue
# once every interpretation candidate has failed), and so does the
# field-fidelity audit that approves a focused repair: without that audit the
# stated amount is dropped and re-asked (#928). The pool is drawn only after
# the corridor is exhausted, and a focused repair starts only while the pool
# can still fund its approval. Activation and every draw land in the turn's
# records (a structured log line, calls_reserved, and the summary counters).
_LAST_RESORT_REPAIR_SCOPE: ContextVar[bool] = ContextVar(
    "last_resort_repair_scope",
    default=False,
)
_FOCUSED_REPAIR_SCOPE: ContextVar[bool] = ContextVar(
    "focused_repair_scope",
    default=False,
)
LAST_RESORT_REPAIR_CALL_GRANT = 2

# Every provider post a turn can make: the corridor, the research rail's
# routing slot, the no-lookup research answer, and the repair pool. The turn
# deadline also bounds it.
TURN_PROVIDER_POST_CEILING = (
    DEFAULT_TURN_CALL_ALLOWANCE + 1 + 1 + LAST_RESORT_REPAIR_CALL_GRANT
)

_P = ParamSpec("_P")
_R = TypeVar("_R")

# Retrieval failure still needs one answer attempt after interpretation has
# used its corridor. Only the no-lookup answer enters this scope; the turn owns
# the single-use reservation, so nested/repeated recovery cannot replenish it.
_RESEARCH_RECOVERY_SCOPE: ContextVar[bool] = ContextVar(
    "research_recovery_scope", default=False
)


@contextmanager
def research_recovery_scope() -> Iterator[None]:
    token = _RESEARCH_RECOVERY_SCOPE.set(True)
    try:
        yield
    finally:
        _RESEARCH_RECOVERY_SCOPE.reset(token)


@contextmanager
def last_resort_repair_scope() -> Iterator[None]:
    token = _LAST_RESORT_REPAIR_SCOPE.set(True)
    try:
        yield
    finally:
        _LAST_RESORT_REPAIR_SCOPE.reset(token)


def focused_repair(
    repair: Callable[_P, Awaitable[_R]],
) -> Callable[_P, Awaitable[_R]]:
    @functools.wraps(repair)
    async def funded_repair(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        token = _FOCUSED_REPAIR_SCOPE.set(True)
        try:
            return await repair(*args, **kwargs)
        finally:
            _FOCUSED_REPAIR_SCOPE.reset(token)

    return funded_repair


def _repair_pool_draw(task_name: str) -> Literal["repair", "approval"] | None:
    if task_name == "interpretation_repair" and _LAST_RESORT_REPAIR_SCOPE.get():
        return "repair"
    if task_name == "field_fidelity" and _FOCUSED_REPAIR_SCOPE.get():
        return "approval"
    return None


def active_turn_execution() -> TurnExecutionContext | None:
    return _ACTIVE_TURN_EXECUTION.get()


def set_turn_entry_state(state: Any) -> None:
    execution = active_turn_execution()
    if execution is None:
        return
    execution.entry_fingerprint = semantic_progress_fingerprint(state)
    execution._entry_snapshot = semantic_progress_snapshot(state)


@contextmanager
def turn_execution_scope(*, entry_state: Any) -> Iterator[TurnExecutionContext]:
    started = _monotonic()
    deadline_seconds = _turn_deadline_seconds()
    entry_snapshot = semantic_progress_snapshot(entry_state)
    execution = TurnExecutionContext(
        started_monotonic=started,
        deadline_monotonic=started + deadline_seconds,
        deadline_seconds=deadline_seconds,
        call_allowance=_turn_call_allowance(),
        entry_fingerprint=semantic_progress_fingerprint(entry_state),
        _entry_snapshot=entry_snapshot,
    )
    token = _ACTIVE_TURN_EXECUTION.set(execution)
    try:
        yield execution
    finally:
        claim_turn_terminal("recoverable_failed", "stream_severed")
        _ACTIVE_TURN_EXECUTION.reset(token)


def reserve_provider_call(
    task: OpenRouterTask | str,
    task_timeout_seconds: float | None = None,
) -> ProviderCallPermit | None:
    task_name = str(task)
    execution = active_turn_execution()
    if execution is None:
        return ProviderCallPermit(
            task=task_name,
            timeout_seconds=(
                float(task_timeout_seconds)
                if task_timeout_seconds is not None
                else DEFAULT_TURN_DEADLINE_SECONDS
            ),
        )

    remaining_seconds = execution.remaining_deadline_seconds()
    if remaining_seconds <= 0:
        execution.deadline_exhausted = True
        execution.blocked_tasks.append(task_name)
        return None
    if (
        _RESEARCH_RECOVERY_SCOPE.get()
        and task_name == "knowledge_voicing"
        and not execution.research_recovery_reserved
    ):
        execution.research_recovery_reserved = True
        timeout_seconds = remaining_seconds
        if task_timeout_seconds is not None:
            timeout_seconds = min(timeout_seconds, float(task_timeout_seconds))
        return ProviderCallPermit(task=task_name, timeout_seconds=timeout_seconds)
    if task_name == _ROUTING_RESERVED_TASK and not execution.routing_reserved:
        from argus.domain.research.config import research_rail_enabled

        if research_rail_enabled():
            execution.routing_reserved = True
            timeout_seconds = remaining_seconds
            if task_timeout_seconds is not None:
                timeout_seconds = min(timeout_seconds, float(task_timeout_seconds))
            return ProviderCallPermit(task=task_name, timeout_seconds=timeout_seconds)
    pool_draw = _repair_pool_draw(task_name)
    if pool_draw is not None and execution.calls_reserved >= execution.call_allowance:
        if execution.last_resort_repair_calls_granted == 0:
            execution.last_resort_repair_calls_granted = LAST_RESORT_REPAIR_CALL_GRANT
            logger.bind(
                llm_task=task_name,
                calls_reserved=execution.calls_reserved,
                call_allowance=execution.call_allowance,
                grant=LAST_RESORT_REPAIR_CALL_GRANT,
            ).info("Last-resort repair call grant activated")
        pool_left = (
            execution.last_resort_repair_calls_granted
            - execution.last_resort_repair_grant_used
        )
        # A focused repair keeps one pool call back for its approval.
        needed = 2 if pool_draw == "repair" and _FOCUSED_REPAIR_SCOPE.get() else 1
        if pool_left >= needed:
            execution.last_resort_repair_grant_used += 1
            execution.calls_reserved += 1
            if pool_draw == "approval":
                execution.repair_approval_grant_used += 1
            timeout_seconds = remaining_seconds
            if task_timeout_seconds is not None:
                timeout_seconds = min(timeout_seconds, float(task_timeout_seconds))
            return ProviderCallPermit(task=task_name, timeout_seconds=timeout_seconds)
        if pool_left > 0:
            logger.bind(
                llm_task=task_name,
                calls_reserved=execution.calls_reserved,
                pool_left=pool_left,
            ).info("Focused repair refused: its approval cannot be funded")
    if execution.calls_reserved >= execution.call_allowance:
        execution.call_allowance_exhausted = True
        execution.blocked_tasks.append(task_name)
        return None

    execution.calls_reserved += 1
    timeout_seconds = remaining_seconds
    if task_timeout_seconds is not None:
        timeout_seconds = min(timeout_seconds, float(task_timeout_seconds))
    return ProviderCallPermit(task=task_name, timeout_seconds=timeout_seconds)


def turn_budget_block_reason() -> str | None:
    execution = active_turn_execution()
    if execution is None:
        return None
    if execution.deadline_exhausted or execution.remaining_deadline_seconds() <= 0:
        execution.deadline_exhausted = True
        return "turn_deadline_exhausted"
    if (
        execution.call_allowance_exhausted
        or execution.calls_reserved >= execution.call_allowance
    ):
        return "turn_call_allowance_exhausted"
    return None


def mark_turn_deadline_exhausted() -> None:
    execution = active_turn_execution()
    if execution is not None:
        execution.deadline_exhausted = True


def claim_turn_terminal(
    outcome: ProgressOutcome,
    reason: str | None = None,
) -> bool:
    execution = active_turn_execution()
    if execution is None or execution.terminal is not None:
        return False
    execution.terminal = outcome
    execution.terminal_reason = reason
    return True


def record_exit_progress(
    state: Any,
    terminal: ProgressOutcome | None,
) -> ProgressAssessment:
    execution = active_turn_execution()
    exit_snapshot = semantic_progress_snapshot(state)
    if execution is None:
        return assess_progress(None, exit_snapshot, terminal)

    authoritative_terminal = (
        execution.terminal
        if execution.terminal in _EXPLICIT_PROGRESS_TERMINALS
        else terminal
    )
    assessment = assess_progress(
        execution._entry_snapshot,
        exit_snapshot,
        authoritative_terminal,
    )
    execution.exit_fingerprint = semantic_progress_fingerprint(state)
    execution.progress_outcome = assessment.outcome
    claim_turn_terminal(
        assessment.outcome,
        "unchanged_typed_state"
        if assessment.outcome == "no_progress"
        else "runtime_final",
    )
    return assessment


def turn_progress_evidence() -> dict[str, Any]:
    execution = active_turn_execution()
    if execution is None:
        return {}
    return {
        "output_fingerprint": execution.exit_fingerprint,
        "progress_outcome": execution.progress_outcome,
        "terminal": execution.terminal,
        "terminal_reason": execution.terminal_reason,
    }


def apply_turn_progress_evidence(evidence: Any) -> None:
    execution = active_turn_execution()
    if execution is None or not isinstance(evidence, dict):
        return
    output_fingerprint = evidence.get("output_fingerprint")
    outcome = evidence.get("progress_outcome")
    terminal = evidence.get("terminal")
    if (
        isinstance(output_fingerprint, str)
        and len(output_fingerprint) == 64
        and all(char in "0123456789abcdef" for char in output_fingerprint)
    ):
        execution.exit_fingerprint = output_fingerprint
    if outcome in {
        "advanced",
        "clarification",
        "redirected",
        "finished",
        "no_progress",
        "recoverable_failed",
        "terminal_failed",
    }:
        execution.progress_outcome = outcome
    if terminal in {
        "advanced",
        "clarification",
        "redirected",
        "finished",
        "no_progress",
        "recoverable_failed",
        "terminal_failed",
    }:
        terminal_reason = evidence.get("terminal_reason")
        if terminal_reason not in {"runtime_final", "unchanged_typed_state"}:
            terminal_reason = "runtime_final"
        claim_turn_terminal(
            terminal,
            terminal_reason,
        )


def turn_execution_summary(
    receipts: Iterable[OpenRouterRouteReceipt],
) -> dict[str, Any]:
    receipt_outcomes = {
        "succeeded": 0,
        "failed": 0,
        "skipped": 0,
    }
    receipt_count = 0
    for receipt in receipts:
        receipt_count += 1
        outcome = getattr(receipt, "outcome", None)
        if outcome in receipt_outcomes:
            receipt_outcomes[outcome] += 1

    execution = active_turn_execution()
    if execution is None:
        return {
            "provider_receipt_count": receipt_count,
            "provider_outcomes": receipt_outcomes,
        }
    return {
        "input_fingerprint": execution.entry_fingerprint,
        "output_fingerprint": execution.exit_fingerprint,
        "progress_outcome": execution.progress_outcome,
        "terminal": execution.terminal,
        "terminal_reason": execution.terminal_reason,
        "calls_reserved": execution.calls_reserved,
        "call_allowance": execution.call_allowance,
        "routing_reserved": execution.routing_reserved,
        "research_recovery_reserved": execution.research_recovery_reserved,
        "last_resort_repair_calls_granted": execution.last_resort_repair_calls_granted,
        "last_resort_repair_grant_used": execution.last_resort_repair_grant_used,
        "repair_approval_grant_used": execution.repair_approval_grant_used,
        "deadline_seconds": execution.deadline_seconds,
        "elapsed_seconds": round(execution.elapsed_seconds(), 3),
        "deadline_exhausted": execution.deadline_exhausted,
        "call_allowance_exhausted": execution.call_allowance_exhausted,
        "provider_receipt_count": receipt_count,
        "provider_outcomes": receipt_outcomes,
    }


def detach_turn_execution() -> None:
    _ACTIVE_TURN_EXECUTION.set(None)


async def runtime_events_with_keepalive(
    runtime_events: AsyncIterator[dict[str, Any]],
    *,
    runtime_timeout_seconds: float,
    runtime_keepalive_seconds: float,
) -> AsyncIterator[dict[str, Any] | None]:
    next_event: asyncio.Task[dict[str, Any]] | None = None
    next_event_started = _monotonic()
    last_event: dict[str, str] | None = None
    event_count = 0
    try:
        while True:
            execution = active_turn_execution()
            if execution is not None and execution.remaining_deadline_seconds() <= 0:
                raise _turn_deadline_error(
                    execution, runtime_keepalive_seconds, event_count, last_event
                )
            if next_event is None:
                next_event = asyncio.create_task(anext(runtime_events))
                next_event_started = _monotonic()
            try:
                event_remaining = runtime_timeout_seconds - (
                    _monotonic() - next_event_started
                )
                if event_remaining <= 0:
                    raise asyncio.TimeoutError
                wait_seconds = min(runtime_keepalive_seconds, event_remaining)
                if execution is not None:
                    wait_seconds = min(
                        wait_seconds, execution.remaining_deadline_seconds()
                    )
                runtime_event = await asyncio.wait_for(
                    asyncio.shield(next_event),
                    timeout=wait_seconds,
                )
                next_event = None
                if execution is not None and execution.remaining_deadline_seconds() <= 0:
                    raise _turn_deadline_error(
                        execution,
                        runtime_keepalive_seconds,
                        event_count,
                        last_event,
                    )
            except asyncio.TimeoutError:
                if execution is not None and execution.remaining_deadline_seconds() <= 0:
                    if next_event is not None:
                        await _cancel_runtime_event_task(next_event)
                    next_event = None
                    raise _turn_deadline_error(
                        execution,
                        runtime_keepalive_seconds,
                        event_count,
                        last_event,
                    ) from None
                elapsed_seconds = _monotonic() - next_event_started
                if elapsed_seconds >= runtime_timeout_seconds:
                    if next_event is not None:
                        await _cancel_runtime_event_task(next_event)
                    next_event = None
                    raise RuntimeEventTimeoutError(
                        {
                            "code": "agent_runtime_event_timeout",
                            "timeout_seconds": runtime_timeout_seconds,
                            "elapsed_seconds": round(elapsed_seconds, 3),
                            "keepalive_seconds": runtime_keepalive_seconds,
                            "event_count": event_count,
                            "last_event": last_event,
                        }
                    ) from None
                yield None
                continue
            except StopAsyncIteration:
                break
            event_count += 1
            last_event = _runtime_event_boundary(runtime_event)
            yield runtime_event
    finally:
        if next_event is not None and not next_event.done():
            await _cancel_runtime_event_task(next_event)


async def _cancel_runtime_event_task(
    runtime_event_task: asyncio.Task[dict[str, Any]],
) -> None:
    runtime_event_task.cancel()
    with suppress(asyncio.CancelledError, StopAsyncIteration):
        await runtime_event_task


def _turn_deadline_error(
    execution: TurnExecutionContext,
    runtime_keepalive_seconds: float,
    event_count: int,
    last_event: dict[str, str] | None,
) -> RuntimeEventTimeoutError:
    mark_turn_deadline_exhausted()
    return RuntimeEventTimeoutError(
        {
            "code": "turn_deadline_exhausted",
            "timeout_seconds": execution.deadline_seconds,
            "elapsed_seconds": round(execution.elapsed_seconds(), 3),
            "keepalive_seconds": runtime_keepalive_seconds,
            "event_count": event_count,
            "last_event": last_event,
        }
    )


def _runtime_event_boundary(runtime_event: dict[str, Any]) -> dict[str, str]:
    boundary = {"type": str(runtime_event.get("type") or "unknown")}
    stage = runtime_event.get("stage")
    if stage not in (None, "", [], {}):
        boundary["stage"] = str(stage)
    outcome = runtime_event.get("outcome")
    if outcome not in (None, "", [], {}):
        boundary["outcome"] = str(outcome)
    return boundary


def _turn_deadline_seconds() -> float:
    raw = os.getenv("ARGUS_TURN_DEADLINE_SECONDS")
    if raw is None or not raw.strip():
        raw = os.getenv("ARGUS_RUNTIME_EVENT_TIMEOUT_SECONDS")
    if raw is None or not raw.strip():
        return DEFAULT_TURN_DEADLINE_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_TURN_DEADLINE_SECONDS
    return value if value > 0 else DEFAULT_TURN_DEADLINE_SECONDS


def _turn_call_allowance() -> int:
    raw = os.getenv("ARGUS_TURN_CALL_ALLOWANCE")
    if raw is None or not raw.strip():
        return DEFAULT_TURN_CALL_ALLOWANCE
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_TURN_CALL_ALLOWANCE
    if value <= 0:
        return DEFAULT_TURN_CALL_ALLOWANCE
    return min(value, DEFAULT_TURN_CALL_ALLOWANCE)
