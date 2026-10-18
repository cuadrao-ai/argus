"""Recovery for responses the runtime cannot act on.

A contract rejection is raised after the provider already answered, so it is a
pure function of (response, request): repeating the same call reproduces it.
This module owns the corrective re-ask, the rejection wording, and the receipt
that keeps those turns visible in telemetry.
"""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

from loguru import logger

from argus.agent_runtime.interpreter.draft_shape import (
    _request_has_active_strategy_context,
)
from argus.agent_runtime.interpreter.shared import (
    _llm_strategy_draft_has_extractable_fields,
)
from argus.agent_runtime.llm_interpreter_types import (
    InterpretationContractError,
    LLMInterpretationResponse,
)
from argus.agent_runtime.stages.interpret_types import InterpretationRequest
from argus.agent_runtime.turn_execution import active_turn_execution
from argus.llm.openrouter import (
    log_openrouter_failure,
    record_openrouter_route_receipt,
)

REPLAY_CORRECTIVE_HINT = (
    "Your previous response repeated the active strategy without applying "
    "anything from the current user message. Read the current message again "
    "and put what it changes into candidate_strategy_draft. If the message "
    "answers a pending question, set that field. If you genuinely cannot tell "
    "what it changes, set requires_clarification true and ask one specific "
    "question in assistant_response."
)

UNUSABLE_CORRECTIVE_HINT = (
    "Your previous response could not be acted on: it carried neither a usable "
    "strategy draft nor any assistant_response to show the user. Answer again. "
    "If the request is something you can express as a strategy, fill "
    "candidate_strategy_draft. If it is a knowledge or out-of-scope request, "
    "keep the draft empty and put the answer or one specific question in "
    "assistant_response."
)

_CORRECTION_MARKER = "<rejected by runtime validation>"


def incomplete_response_error(
    *,
    response: LLMInterpretationResponse,
    request: InterpretationRequest,
) -> InterpretationContractError:
    # Naming the actual gap: a knowledge turn has no strategy draft to be
    # incomplete, so reporting one sent readers looking in the wrong place.
    if response.intent not in {"strategy_drafting", "backtest_execution"}:
        reason = (
            "OpenRouter interpretation returned no assistant response for a "
            f"{response.intent} turn"
        )
    elif _llm_strategy_draft_has_extractable_fields(response.candidate_strategy_draft):
        reason = (
            "OpenRouter interpretation returned a strategy draft the runtime "
            "cannot execute"
        )
    elif _request_has_active_strategy_context(request):
        reason = (
            "OpenRouter interpretation returned no update for the active "
            "strategy and no assistant response"
        )
    else:
        reason = "OpenRouter interpretation returned an incomplete strategy draft"
    return InterpretationContractError(reason, corrective_hint=UNUSABLE_CORRECTIVE_HINT)


def replay_without_update_error() -> InterpretationContractError:
    return InterpretationContractError(
        "OpenRouter interpretation replayed the active artifact without a "
        "material current-turn update",
        corrective_hint=REPLAY_CORRECTIVE_HINT,
    )


async def handle_candidate_failure(
    *,
    interpreter: Any,
    exc: Exception,
    candidate_model: str,
    is_primary: bool,
    wire_messages: list[dict[str, str]],
    invoke_schema: Callable[..., Awaitable[Any]],
    ready_for_runtime: Callable[..., Awaitable[LLMInterpretationResponse]],
    request: InterpretationRequest,
    asset_resolution_context: str | None,
) -> Any | None:
    """Log, book telemetry, and try one in-tier correction.

    Returns a finished interpretation when the corrective re-ask succeeded, and
    records on the interpreter whether the failure was a contract rejection
    rather than a transport or schema failure.
    """
    log_openrouter_failure(
        task="interpretation",
        model_name=candidate_model,
        exc=exc,
        message=(
            "Direct LLM interpretation candidate failed; " "trying next configured model"
        ),
    )
    # The banner classifies on the LATEST candidate's failure: a transient
    # transport failure after a contract rejection must restore the retry
    # affordance, because retrying that tier could genuinely succeed.
    interpreter.last_failure_kind = (
        "contract_rejected" if isinstance(exc, InterpretationContractError) else None
    )
    if not isinstance(exc, InterpretationContractError):
        return None
    # The provider call already recorded its own succeeded receipt, so without
    # this the turn reads as green. Transport and schema failures are not
    # recorded here because invoke_openrouter_json_schema already books those.
    record_openrouter_route_receipt(
        task="interpretation",
        model_name=candidate_model,
        mode="json_schema",
        schema_name="LLMInterpretationResponse",
        # The provider call's own succeeded receipt carries the real latency.
        latency_ms=0,
        outcome="failed",
        failure_mode="interpretation_contract_rejected",
    )
    if not _correction_budget_allows_attempt(interpreter):
        return None
    interpreter.correction_attempted = True
    corrected = await self_corrected_response(
        error=exc,
        wire_messages=wire_messages,
        candidate_model=candidate_model,
        invoke_schema=invoke_schema,
        ready_for_runtime=ready_for_runtime,
        request=request,
        asset_resolution_context=asset_resolution_context,
    )
    if corrected is None:
        return None
    interpreter.last_failure_kind = None
    interpreter.last_status = "used" if is_primary else "fallback_used"
    return interpreter._to_runtime_interpretation(corrected, request=request)


# Focused repair plus the clarification primary/fallback pair must still fit
# inside the calibrated turn allowance after a failed correction.
_CORRECTION_RESERVED_CALLS = 3


def _correction_budget_allows_attempt(interpreter: Any) -> bool:
    """One correction per turn, and only with corridor headroom to spare."""
    if getattr(interpreter, "correction_attempted", False):
        return False
    execution = active_turn_execution()
    if execution is None:
        return True
    remaining = execution.call_allowance - execution.calls_reserved
    if remaining <= _CORRECTION_RESERVED_CALLS:
        logger.debug(
            f"Skipping interpretation self-correction remaining_calls={remaining}"
        )
        return False
    return True


async def self_corrected_response(
    *,
    error: InterpretationContractError,
    wire_messages: list[dict[str, str]],
    candidate_model: str,
    invoke_schema: Callable[..., Awaitable[Any]],
    ready_for_runtime: Callable[..., Awaitable[LLMInterpretationResponse]],
    request: InterpretationRequest,
    asset_resolution_context: str | None,
) -> LLMInterpretationResponse | None:
    """Re-ask the same tier once, with the rejection fed back.

    Bounded to a single attempt: a second rejection means the tier cannot
    satisfy the contract, and repeating it only reproduces the same failure.
    """
    corrective_messages = [
        *wire_messages,
        {"role": "assistant", "content": _CORRECTION_MARKER},
        {"role": "user", "content": error.corrective_hint},
    ]
    try:
        retried = await invoke_schema(
            task="interpretation",
            messages=corrective_messages,
            schema_model=LLMInterpretationResponse,
            schema_name="LLMInterpretationResponse",
            model_name=candidate_model,
        )
        if not isinstance(retried, LLMInterpretationResponse):
            return None
        return await ready_for_runtime(
            response=retried,
            preferred_model=candidate_model,
            request=request,
            asset_resolution_context=asset_resolution_context,
        )
    except Exception as retry_exc:  # noqa: BLE001
        log_openrouter_failure(
            task="interpretation",
            model_name=candidate_model,
            exc=retry_exc,
            message=(
                "LLM interpretation self-correction failed; "
                "trying next configured model"
            ),
        )
        return None


def record_legacy_failure(model_name: str | None, started_at: float, exc: Exception) -> None:
    record_openrouter_route_receipt(
        task="interpretation", model_name=model_name, mode="chat_model",
        schema_name="LLMInterpretationResponse", latency_ms=int((time.perf_counter() - started_at) * 1000),
        outcome="failed", failure_mode=type(exc).__name__,
    )
    log_openrouter_failure(
        task="interpretation", model_name=model_name, exc=exc,
        message="Primary LLM interpretation failed; attempting fallback",
    )
