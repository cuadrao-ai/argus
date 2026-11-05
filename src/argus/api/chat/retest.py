"""Typed `retest_run` admission, receipt projection, and turn completion.

The client submits identity and policy only. Everything executable is reloaded
from the owner-scoped stored run, so a tampered payload cannot change or expose
canonical state. Provider coverage is resolved before a runnable card persists.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, cast
from uuid import UUID

from fastapi import Request

from argus.agent_runtime.confirmation_artifacts import confirmation_artifact_reference
from argus.agent_runtime.recovery_messages import recovery_message, recovery_state
from argus.agent_runtime.retest_confirmation import (
    prepare_retest_confirmation_payload,
    retest_runtime_result,
)
from argus.api.chat import retry as chat_retry
from argus.api.chat.confirmation import (
    public_confirmation_projection,
    runtime_confirmation_card,
)
from argus.api.chat.recovery import _run_by_id_for_user
from argus.api.chat.turn_lifecycle_hooks import ChatTurnLifecycleHooks
from argus.api.dependencies import problem
from argus.api.schemas import ChatStreamRequest, Message
from argus.domain.market_data.new_york_clock import new_york_today
from argus.domain.retest_setup import (
    RETEST_CONTRACT_PAIRS,
    RETEST_CONTRACT_VERSION,
    RETEST_WINDOW_POLICY,
    RetestSetup,
    has_finalized_evidence_identity,
    repaired_retest_setup,
    retest_dossier_availability,
    retest_setup_from_run,
)

RETEST_ACTION_TYPE = "retest_run"
RETEST_ACTION_LABEL_KEY = "command_palette.retest_current_data"
_ENVELOPE_KEYS = frozenset({"source_run_id", "window_policy", "contract_version"})
# The canonical finalizer refuses to complete a run whose result card lacks
# these, so their presence is the durable marker of a finalized artifact.
_DAYS_PER_YEAR = 365
_DAYS_PER_MONTH = 30


@dataclass(frozen=True)
class RetestTurn:
    """Everything the accepted turn needs, resolved before the turn is admitted."""

    source_run_id: str
    setup: RetestSetup
    confirmation_payload: dict[str, Any]
    receipt: dict[str, Any]


def is_retest_action(payload: ChatStreamRequest) -> bool:
    return payload.action is not None and payload.action.type == RETEST_ACTION_TYPE


def retest_action_source_run_id(action_payload: Mapping[str, Any]) -> str | None:
    """Accept only exact legacy or current identity-only envelopes."""
    if set(action_payload) != _ENVELOPE_KEYS:
        return None
    contract_version = action_payload.get("contract_version")
    window_policy = action_payload.get("window_policy")
    if not isinstance(contract_version, str) or not isinstance(window_policy, str):
        return None
    if (contract_version, window_policy) not in RETEST_CONTRACT_PAIRS:
        return None
    source_run_id = action_payload.get("source_run_id")
    if not isinstance(source_run_id, str):
        return None
    try:
        # Run ids are UUIDs in both storage modes. Rejecting other shapes here
        # keeps a tampered id on the uniform invalid-state path instead of
        # reaching Postgres and surfacing a cast error as a 500. The canonical
        # form is what is returned: the parser also accepts URN, braced,
        # hyphenless, and uppercase spellings that Postgres rejects or stores
        # canonically, and the memory store keys runs by exact string.
        return str(UUID(source_run_id.strip()))
    except ValueError:
        return None


def sanitized_retest_action(source_run_id: str) -> dict[str, Any]:
    """Backend-owned action record; client display copy never reaches storage."""
    return {
        "type": RETEST_ACTION_TYPE,
        "label": None,
        "labelKey": RETEST_ACTION_LABEL_KEY,
        "payload": {
            "source_run_id": source_run_id,
            "window_policy": RETEST_WINDOW_POLICY,
            "contract_version": RETEST_CONTRACT_VERSION,
        },
        "presentation": None,
    }


def retest_receipt(
    setup: RetestSetup,
    *,
    confirmation_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Structured display context; the transcript localizes it on render."""
    period = _retest_period(setup, confirmation_payload=confirmation_payload)
    receipt: dict[str, Any] = {
        "contract_version": RETEST_CONTRACT_VERSION,
        "window_policy": RETEST_WINDOW_POLICY,
        "source_run_id": setup.source_run_id,
        "symbols": list(setup.symbols),
        "strategy_family": setup.strategy_type,
        "timeframe": setup.timeframe,
        **period,
    }
    if setup.cadence is not None:
        receipt["cadence"] = setup.cadence
    return receipt


def prepare_retest_turn(
    *,
    payload: ChatStreamRequest,
    request: Request,
    user_id: str,
    conversation_id: str,
    language: str | None,
    today: date | None = None,
    confirmation_id: str | None = None,
    before_provider_work: Callable[[], None] | None = None,
) -> RetestTurn | None:
    """Resolve canonical truth before admission, or reject as invalid state.

    ``before_provider_work`` runs after the cheap state checks and before
    market-data coverage, so a rejected retest costs no daily unit while an
    over-cap user cannot reach provider work (#692).
    """
    if not is_retest_action(payload) or payload.action is None:
        return None
    source_run_id = retest_action_source_run_id(payload.action.payload)
    setup = (
        _owned_retest_setup(
            user_id=user_id,
            conversation_id=conversation_id,
            source_run_id=source_run_id,
            today=today or new_york_today(),
        )
        if source_run_id is not None
        else None
    )
    availability = retest_dossier_availability(setup) if setup is not None else None
    if availability is not None and availability.state == "no_new_data":
        raise problem(
            request,
            status_code=409,
            code="artifact_action_invalid_state",
            title="Action No Longer Active",
            detail=recovery_message("artifact_action_invalid_state", language=language),
        )
    admitted_setup = (
        repaired_retest_setup(setup, availability)
        if setup is not None and availability is not None
        else setup
    )
    if admitted_setup is not None and before_provider_work is not None:
        before_provider_work()
    confirmation = (
        prepare_retest_confirmation_payload(
            admitted_setup,
            language=language or "en",
            confirmation_id=confirmation_id,
        )
        if admitted_setup is not None
        else None
    )
    if confirmation is not None and confirmation.coverage_error_code is not None:
        from argus.api.backtest_service import raise_backtest_problem

        raise_backtest_problem(request, confirmation.coverage_error_code)
    confirmation_payload = (
        confirmation.confirmation_payload if confirmation is not None else None
    )
    if admitted_setup is None or confirmation_payload is None:
        raise problem(
            request,
            status_code=409,
            code="artifact_action_invalid_state",
            title="Action No Longer Active",
            detail=recovery_message("artifact_action_invalid_state", language=language),
        )
    period = _retest_period(admitted_setup, confirmation_payload=confirmation_payload)
    confirmation_payload = {
        **confirmation_payload,
        "retest_period": period,
    }
    return RetestTurn(
        source_run_id=admitted_setup.source_run_id,
        setup=admitted_setup,
        confirmation_payload=confirmation_payload,
        receipt=retest_receipt(
            admitted_setup,
            confirmation_payload=confirmation_payload,
        ),
    )


def complete_retest_turn(
    *,
    turn: RetestTurn,
    lifecycle_hooks: ChatTurnLifecycleHooks,
    conversation_id: str,
    language: str,
    settle_usage: Any = None,
) -> dict[str, Any]:
    """Persist the confirmation artifact and stop; the user still approves."""
    payload = turn.confirmation_payload
    confirmation_id = str(payload["confirmation_id"])
    card = runtime_confirmation_card(
        retest_runtime_result(payload),
        confirmation_id=confirmation_id,
        conversation_id=conversation_id,
        language=language,
    )
    if card is None:
        raise RuntimeError("retest_confirmation_card_unavailable")
    reference = confirmation_artifact_reference(
        confirmation_id=confirmation_id,
        confirmation_payload=payload,
        confirmation_card=card,
    ).model_dump(mode="python")
    metadata: dict[str, Any] = {
        "conversation_mode": "confirm",
        "agent_runtime_stage_outcome": "await_approval",
        "chat_action": sanitized_retest_action(turn.source_run_id),
        "retest_receipt": dict(turn.receipt),
        "confirmation_card": card,
        "confirmation_payload": payload,
        "active_confirmation_reference": reference,
        "artifact_references": [reference],
    }
    assistant_message = lifecycle_hooks.complete(
        content="",
        metadata=metadata,
        settle_usage=settle_usage,
    )
    return cast(
        dict[str, Any],
        public_confirmation_projection(
            {
                "stage_outcome": "await_approval",
                "message_id": assistant_message.id,
                "confirmation": card,
                "confirmation_payload": payload,
                "active_confirmation_reference": reference,
                "artifact_references": [reference],
                "retest_receipt": dict(turn.receipt),
            }
        ),
    )


def failed_retest_turn(
    *,
    turn: RetestTurn,
    lifecycle_hooks: ChatTurnLifecycleHooks,
    request_message: Message,
    language: str,
) -> dict[str, Any]:
    """Map a transient materialization failure onto the shipped amber retry."""
    assistant_text = recovery_message("runtime_failure", language=language)
    recovery = recovery_state("runtime_failure", language=language, retryable=True)
    failure_metadata: dict[str, Any] = {
        "conversation_mode": "recovery",
        "agent_runtime_stage_outcome": "agent_runtime_failure",
        "failure_code": "agent_runtime_failure",
        "retryable": True,
        "recovery": recovery,
        "retest_receipt": dict(turn.receipt),
        **chat_retry.durable_retry_last_turn_metadata(request_message),
    }
    assistant_message = lifecycle_hooks.recoverable_failure(
        content=assistant_text,
        metadata=failure_metadata,
        failure_code="agent_runtime_failure",
        retryable=True,
    )
    durable_retry = (
        assistant_message.metadata.get("retry_last_turn")
        if isinstance(assistant_message.metadata, dict)
        else None
    )
    payload: dict[str, Any] = {
        # `ready_to_respond` keeps an unrelated open confirmation intact; the
        # failure belongs to this turn only.
        "stage_outcome": "ready_to_respond",
        "assistant_response": assistant_text,
        "message_id": assistant_message.id,
        "recovery": recovery,
        "retest_receipt": dict(turn.receipt),
    }
    if isinstance(durable_retry, dict):
        # Live frame carries the message-shaped retry so the amber assistant
        # recovery block owns it; hydration rebuilds the anchored shape from
        # the persisted request-linked metadata.
        payload["retry_last_turn"] = {
            key: durable_retry[key]
            for key in ("message", "action")
            if key in durable_retry
        }
    return payload


def _owned_retest_setup(
    *,
    user_id: str,
    conversation_id: str,
    source_run_id: str,
    today: date,
) -> RetestSetup | None:
    run = _run_by_id_for_user(user_id=user_id, run_id=source_run_id)
    if (
        run is None
        or run.conversation_id != conversation_id
        or run.status != "completed"
        or not has_finalized_evidence_identity(run.conversation_result_card)
    ):
        # One uniform outcome for missing, foreign, unfinished, and
        # cross-conversation runs so the caller cannot probe object existence.
        return None
    return retest_setup_from_run(run.model_dump(mode="python"), today=today)


def _retest_period(
    setup: RetestSetup,
    *,
    confirmation_payload: Mapping[str, Any],
) -> dict[str, Any]:
    launch_payload = confirmation_payload.get("launch_payload")
    if not isinstance(launch_payload, Mapping):
        raise ValueError("retest_confirmation_launch_payload_missing")
    coverage = launch_payload.get("coverage_preflight")
    if not isinstance(coverage, Mapping):
        raise ValueError("retest_confirmation_coverage_missing")

    requested = _validated_date_range(coverage.get("requested_date_range"))
    effective = _validated_date_range(coverage.get("effective_date_range"))
    if requested is None or effective is None:
        raise ValueError("retest_confirmation_period_invalid")
    if requested != _validated_date_range(launch_payload.get("requested_date_range")):
        raise ValueError("retest_confirmation_requested_period_mismatch")
    if effective != _validated_date_range(launch_payload.get("date_range")):
        raise ValueError("retest_confirmation_effective_period_mismatch")

    effective_start = date.fromisoformat(effective["start"])
    effective_end = date.fromisoformat(effective["end"])
    duration_days = (effective_end - effective_start).days
    original = {
        "start": setup.original_start.isoformat(),
        "end": setup.original_end.isoformat(),
    }
    return {
        "original_date_range": original,
        "requested_date_range": requested,
        "effective_date_range": effective,
        "duration_days": duration_days,
        "duration": _duration_descriptor(duration_days),
    }


def _validated_date_range(value: Any) -> dict[str, str] | None:
    if not isinstance(value, Mapping):
        return None
    start_value = value.get("start")
    end_value = value.get("end")
    if not isinstance(start_value, str) or not isinstance(end_value, str):
        return None
    try:
        start = date.fromisoformat(start_value)
        end = date.fromisoformat(end_value)
    except ValueError:
        return None
    if start > end:
        return None
    return {"start": start.isoformat(), "end": end.isoformat()}


def _duration_descriptor(duration_days: int) -> dict[str, Any]:
    if duration_days >= _DAYS_PER_YEAR:
        count = round(duration_days / _DAYS_PER_YEAR, 1)
        return {
            "unit": "year",
            "count": int(count) if count.is_integer() else count,
            "approximate": duration_days % _DAYS_PER_YEAR != 0,
        }
    if duration_days >= _DAYS_PER_MONTH:
        count = round(duration_days / _DAYS_PER_MONTH, 1)
        return {
            "unit": "month",
            "count": int(count) if count.is_integer() else count,
            "approximate": duration_days % _DAYS_PER_MONTH != 0,
        }
    return {"unit": "day", "count": duration_days, "approximate": False}
