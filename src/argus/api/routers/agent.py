from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse
from loguru import logger

from argus.agent_runtime.recovery_messages import recovery_message, recovery_state
from argus.agent_runtime.resolution import mention_to_provenance
from argus.agent_runtime.runtime import build_workflow_input, stream_agent_turn_events
from argus.agent_runtime.turn_execution import (
    RuntimeEventTimeoutError as TurnRuntimeEventTimeoutError,
)
from argus.agent_runtime.turn_execution import (
    apply_turn_progress_evidence,
    claim_turn_terminal,
    record_exit_progress,
    runtime_events_with_keepalive,
    set_turn_entry_state,
    turn_execution_scope,
    turn_execution_summary,
)
from argus.api import state as api_state
from argus.api.artifact_presentation import reader_chat_result
from argus.api.chat import confirmation as chat_confirmation
from argus.api.chat import retry as chat_retry
from argus.api.chat.actions import (
    chat_display_message,
    chat_request_message,
    confirmation_action_id,
    is_cancel_confirmation_action,
    is_confirmation_action,
    is_result_action,
    latest_active_confirmation_id,
    missing_run_confirmation_action_id_message,
    persisted_chat_action,
    recent_confirmation_messages,
    recent_metadata_invalidates_confirmation,
    run_for_result_action,
    stale_confirmation_action_message,
)
from argus.api.chat.artifacts import (
    ensure_unspent_confirmation_identity,
    result_fact_bank,
    result_followup_metadata_from_run,
)
from argus.api.chat.backtest_jobs import (
    BacktestJobShadowContext,
    reset_backtest_job_shadow_context,
    set_backtest_job_shadow_context,
)
from argus.api.chat.breakdown_jobs import start_result_breakdown
from argus.api.chat.cancellation import (
    complete_confirmation_cancellation,
    prepare_confirmation_cancellation,
)
from argus.api.chat.discovery_evidence import discovery_allowance_for_turn
from argus.api.chat.guest_compute_ceiling import (
    check_guest_compute_ceiling,
    guest_compute_settlement,
)
from argus.api.chat.measurement_events import (
    schedule_runtime_measurement_events_after_stream,
)
from argus.api.chat.memory_recall import annotate_memory_recalls
from argus.api.chat.recovery import (
    RuntimeFallbackContext,
    checkpoint_has_pending_confirmation,
    confirmation_metadata_fallback_context,
    failed_action_metadata_fallback_context,
    latest_result_fallback_context,
    mark_terminal_runtime_failure_checkpoint,
    ordinary_turn_metadata_fallback_context,
    runtime_checkpoint_values,
)
from argus.api.chat.refusal_evidence import bind_refusal_request
from argus.api.chat.request_admission import (
    prepare_chat_request_admission,
    reject_invalid_non_run_confirmation_action,
)
from argus.api.chat.research_evidence import (
    claim_research_provider_attempt,
    guest_research_visitor_key,
    release_research_provider_claim,
)
from argus.api.chat.result_actions import result_action_request_type
from argus.api.chat.result_link import apply_result_link_outcome
from argus.api.chat.retest import (
    complete_retest_turn,
    failed_retest_turn,
    is_retest_action,
    prepare_retest_turn,
)
from argus.api.chat.route_receipts import persist_route_receipts
from argus.api.chat.run_action_identity import (
    require_run_action_identity,
    validated_optional_idempotency_key,
)
from argus.api.chat.runtime_user import runtime_user_for
from argus.api.chat.runtime_worker import (
    runtime_worker_enabled,
    threaded_runtime_event_source,
)
from argus.api.chat.streaming import (
    runtime_result_envelope,
    runtime_result_message,
    runtime_stage_status,
    sse_data,
    sse_done,
    sse_keepalive,
)
from argus.api.chat.title_finalization import schedule_artifact_naming_after_stream
from argus.api.chat.tool_results import (
    computation_marker,
    prepare_runtime_tool_publication,
    runtime_tool_result_cards,
)
from argus.api.chat.turn_metering import settle_metered_turn
from argus.api.chat.visible_reply import ReplyRewrites, rewrite_visible_reply
from argus.api.conversation_surface import conversation_not_found, refuse_closed_chat
from argus.api.dependencies import current_user, dev_memory_fallback_enabled, problem
from argus.api.guest_access import account_context, client_identity
from argus.api.message_store import (
    latest_unresolved_terminal_runtime_failure_metadata,
    load_chat_request_history,
    reconcile_stale_chat_turns,
)
from argus.api.naming import get_starter_prompts
from argus.api.schemas import (
    BacktestRun,
    ChatStreamRequest,
    StarterPromptsResponse,
    User,
)
from argus.domain.artifact_presentation_kind import artifact_presentation_kind
from argus.domain.backtest_finalization import BacktestFinalizationError
from argus.domain.research.admission import research_attempt_admission_context
from argus.domain.result_readout_content import (
    READOUT_METADATA_KEYS,
    stored_readout_metadata,
)
from argus.domain.usage_limits import (
    SIMULATION_USAGE_RESOURCE,
    allowance_windows,
)
from argus.domain.visitor_usage import visitor_key_for
from argus.llm.openrouter import (
    begin_openrouter_route_receipt_capture,
    end_openrouter_route_receipt_capture,
)
from argus.llm.openrouter_key_policy import openrouter_traffic_class

router = APIRouter(tags=["agent"])
RUNTIME_EVENT_TIMEOUT_SECONDS = 120.0
RUNTIME_EVENT_KEEPALIVE_SECONDS = 15.0
RuntimeEventTimeoutError = TurnRuntimeEventTimeoutError


def _runtime_event_timeout_seconds() -> float:
    return _positive_float_env(
        "ARGUS_RUNTIME_EVENT_TIMEOUT_SECONDS",
        RUNTIME_EVENT_TIMEOUT_SECONDS,
        min_value=1.0,
    )


def _runtime_event_keepalive_seconds() -> float:
    timeout_seconds = _runtime_event_timeout_seconds()
    return min(
        timeout_seconds,
        _positive_float_env(
            "ARGUS_RUNTIME_EVENT_KEEPALIVE_SECONDS",
            RUNTIME_EVENT_KEEPALIVE_SECONDS,
            min_value=0.1,
        ),
    )


def _positive_float_env(name: str, default: float, *, min_value: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(value, min_value)


async def _runtime_events_with_keepalive(
    runtime_events: AsyncIterator[dict[str, Any]],
) -> AsyncIterator[dict[str, Any] | None]:
    async for event in runtime_events_with_keepalive(
        runtime_events,
        runtime_timeout_seconds=_runtime_event_timeout_seconds(),
        runtime_keepalive_seconds=_runtime_event_keepalive_seconds(),
    ):
        yield event


def _runtime_failure_diagnostics(exc: BaseException) -> dict[str, Any] | None:
    diagnostics = getattr(exc, "diagnostics", None)
    return dict(diagnostics) if isinstance(diagnostics, dict) else None


async def compose_private_alpha_save_response(**kwargs: Any) -> str | None:
    from argus.agent_runtime.result_followups import (
        compose_private_alpha_save_response as _compose_private_alpha_save_response,
    )

    return await _compose_private_alpha_save_response(**kwargs)


def fallback_private_alpha_save_response(language: str | None = None) -> str:
    from argus.agent_runtime.result_followups import (
        fallback_private_alpha_save_response as _fallback_private_alpha_save_response,
    )

    return _fallback_private_alpha_save_response(language=language)


def missing_result_action_run_message(
    *,
    action_type: str,
    language: str | None,
) -> str:
    is_es = str(language or "").lower().startswith("es")
    if action_type == "save_strategy":
        if is_es:
            return (
                "La acción heredada Guardar se retiró. No pude encontrar el "
                "backtest completado para esta solicitud antigua; continúa "
                "desde una ejecución que siga disponible en este chat o en "
                "Recientes."
            )
        return (
            "The legacy Save action has been retired. I could not find the "
            "completed backtest for this stale request; continue from a run "
            "that is still available in this chat or Recents."
        )
    if is_es:
        return (
            "No pude encontrar el backtest completado para explicarlo. Ejecuta "
            "la estrategia de nuevo y luego usa Explicar resultado desde la "
            "tarjeta de resultado."
        )
    return (
        "I could not find the completed backtest to explain. Run the strategy "
        "again, then explain it from the result card."
    )


@router.get("/api/v1/chat/starter-prompts", response_model=StarterPromptsResponse)
def list_starter_prompts(
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> StarterPromptsResponse:
    prompts = get_starter_prompts(user.language)
    return StarterPromptsResponse(prompts=prompts)


@router.post("/api/v1/chat/stream")
async def chat_stream(
    payload: ChatStreamRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(current_user),  # noqa: B008
) -> StreamingResponse:
    from argus.api.conversation_surface import refuse_business_under_grant as refuse

    refuse(request, user_id=user.id, conversation_id=payload.conversation_id)
    bind_refusal_request(request, payload=payload, user_id=user.id)
    turn_account = account_context(request)
    # One turn, one subject: allowance read, job row and settlement agree.
    turn_is_guest = turn_account.kind == "guest"
    turn_client_identity = client_identity(request)
    turn_visitor_key = visitor_key_for(turn_client_identity)
    turn_guest_research_key = guest_research_visitor_key(
        is_guest=turn_is_guest, client_identity=turn_client_identity, user_id=user.id
    )
    clean_idempotency_key = validated_optional_idempotency_key(
        request,
        idempotency_key,
    )
    headers = {"X-Request-Id": request.state.request_id, "X-Accel-Buffering": "no"}
    is_run_backtest_turn = (
        payload.action is not None and payload.action.type == "run_backtest"
    )
    cancel_confirmation_action = is_cancel_confirmation_action(payload)
    if is_run_backtest_turn:
        require_run_action_identity(
            payload=payload,
            request=request,
            idempotency_key=clean_idempotency_key,
        )

    current_user_profile = None
    if api_state.supabase_gateway is not None:
        try:
            current_user_profile = api_state.supabase_gateway.get_user(user_id=user.id)
        except Exception as exc:
            if not dev_memory_fallback_enabled():
                raise
            logger.warning(
                "Supabase user read failed; using dev memory fallback",
                error=str(exc),
                user_id=user.id,
            )
    else:
        current_user_profile = api_state.store.users.get(user.id, user)
    if current_user_profile is None:
        current_user_profile = user

    language = payload.language or current_user_profile.language or "en"
    request_message = chat_request_message(payload, language=language)
    display_message = chat_display_message(payload, language=language)

    conversation = None
    if api_state.supabase_gateway is not None:
        try:
            conversation = api_state.supabase_gateway.get_conversation(
                user_id=user.id,
                conversation_id=payload.conversation_id,
            )
        except Exception as exc:
            if not dev_memory_fallback_enabled():
                raise
            logger.warning(
                "Supabase conversation read failed; using dev memory fallback",
                error=str(exc),
                conversation_id=payload.conversation_id,
            )
            conversation = api_state.store.conversations.get(payload.conversation_id)
    else:
        conversation = api_state.store.conversations.get(payload.conversation_id)
    memory_owner_id = api_state.store.conversation_owners.get(payload.conversation_id)
    if not conversation or (
        api_state.supabase_gateway is None
        and memory_owner_id is not None
        and memory_owner_id != user.id
    ):
        raise conversation_not_found(request)
    refuse_closed_chat(request, conversation.surface)
    reconcile_stale_chat_turns(
        user_id=user.id,
        conversation_id=conversation.id,
    )
    payload, recent_thread_history = load_chat_request_history(
        user_id=user.id,
        conversation_id=conversation.id,
        payload=payload,
    )
    confirmation_action_messages = recent_confirmation_messages(
        payload=payload,
        user_id=user.id,
        conversation_id=conversation.id,
    )
    cancellation_admission = None
    if cancel_confirmation_action:
        cancellation_admission, cancellation_response = prepare_confirmation_cancellation(
            payload=payload,
            request=request,
            recent_messages=confirmation_action_messages or [],
            headers=headers,
        )
        if cancellation_response is not None:
            return cancellation_response
    terminal_failure_metadata = latest_unresolved_terminal_runtime_failure_metadata(
        user_id=user.id,
        conversation_id=conversation.id,
    )
    mention_provenance = [
        mention_to_provenance(mention.model_dump(mode="python"), index=index)
        for index, mention in enumerate(payload.mentions)
    ]
    runtime_user = runtime_user_for(
        user_id=user.id,
        profile=current_user_profile,
        turn_language=payload.language or conversation.language,
    )
    stale_confirmation_message = stale_confirmation_action_message(
        payload=payload,
        user_id=user.id,
        conversation_id=conversation.id,
        recent_messages=confirmation_action_messages,
        language=language,
    )
    reject_invalid_non_run_confirmation_action(
        payload=payload,
        request=request,
        active_confirmation_id=(
            latest_active_confirmation_id(
                user_id=user.id,
                conversation_id=conversation.id,
                recent_messages=confirmation_action_messages,
            )
            if confirmation_action_messages is not None
            else None
        ),
        stale_confirmation_message=stale_confirmation_message,
        language=language,
    )
    retest_turn = None
    if is_retest_action(payload):
        retest_turn = await asyncio.to_thread(
            prepare_retest_turn,
            payload=payload,
            request=request,
            user_id=user.id,
            conversation_id=conversation.id,
            language=language,
            before_provider_work=lambda: check_guest_compute_ceiling(request, user),
        )
    elif not is_run_backtest_turn and not cancel_confirmation_action:
        check_guest_compute_ceiling(request, user)
    request_admission = prepare_chat_request_admission(
        payload=payload,
        request=request,
        user_id=user.id,
        conversation_id=conversation.id,
        display_message=display_message,
        mention_provenance=mention_provenance,
        enabled=True,
        language=language,
        owner="message_only" if is_run_backtest_turn else "ordinary_turn",
        extra_user_metadata=(
            {"retest_receipt": dict(retest_turn.receipt)}
            if retest_turn is not None
            else None
        ),
    )
    runtime_fallback = RuntimeFallbackContext()
    validated_result_action_run: BacktestRun | None = None
    validated_option_source = request_admission.admit_response_option()
    if validated_option_source is not None:
        runtime_fallback = validated_option_source.runtime_fallback
        accepted_option_request = request_admission.request_message_record
        if accepted_option_request is None:
            raise RuntimeError("Response-option admission returned no request.")
        request_message = accepted_option_request.content
        display_message = accepted_option_request.content
        if payload.action is not None and payload.action.payload.get(
            "request_message_id"
        ):
            mention_provenance = []
    lifecycle_hooks = (
        None if is_run_backtest_turn else request_admission.lifecycle_hooks()
    )
    deterministic_control_turn = cancel_confirmation_action or is_retest_action(payload)

    workflow: Any | None = None
    retry_finalization_execution_identity: str | None = None
    try:
        if lifecycle_hooks is not None and not deterministic_control_turn:
            lifecycle_hooks.mark_running()
        if deterministic_control_turn:
            checkpoint_values = {}
        else:
            workflow = api_state.get_agent_runtime_workflow(request)
            retry_finalization_execution_identity = (
                chat_retry.retryable_finalization_execution_identity(
                    terminal_failure_metadata,
                    request_message=request_message,
                )
            )
            if terminal_failure_metadata is not None:
                await mark_terminal_runtime_failure_checkpoint(
                    workflow=workflow,
                    conversation_id=conversation.id,
                    user=runtime_user,
                    message=request_message,
                    recent_thread_history=recent_thread_history,
                    failure_metadata=terminal_failure_metadata,
                )
            checkpoint_values = await runtime_checkpoint_values(
                workflow=workflow,
                conversation_id=conversation.id,
            )
    except Exception:
        logger.exception(
            "Agent runtime initialization failed",
            conversation_id=conversation.id,
        )
        lifecycle_hooks = request_admission.lifecycle_hooks()
        language = (
            payload.language or conversation.language or current_user_profile.language
        )
        assistant_text = recovery_message("runtime_failure", language=language)
        recovery = recovery_state(
            "runtime_failure",
            language=language,
            retryable=not is_run_backtest_turn,
        )
        failure_metadata: dict[str, Any] = {
            "conversation_mode": "recovery",
            "agent_runtime_stage_outcome": "agent_runtime_failure",
            "recovery": recovery,
        }
        if workflow is not None:
            await mark_terminal_runtime_failure_checkpoint(
                workflow=workflow,
                conversation_id=conversation.id,
                user=runtime_user,
                message=request_message,
                recent_thread_history=recent_thread_history,
                failure_metadata=failure_metadata,
            )
        assistant_message = lifecycle_hooks.recoverable_failure(
            content=assistant_text,
            metadata=failure_metadata,
            failure_code="runtime_initialization_failed",
            retryable=not is_run_backtest_turn,
        )
        retry_last_turn = (
            assistant_message.metadata.get("retry_last_turn")
            if isinstance(assistant_message.metadata, dict)
            else None
        )

        async def initialization_failure_events() -> AsyncIterator[str]:
            with turn_execution_scope(entry_state={}):
                claim_turn_terminal(
                    "recoverable_failed",
                    "runtime_initialization_failed",
                )
                record_exit_progress({}, terminal="recoverable_failed")
                yield sse_data(
                    {
                        "type": "error",
                        "code": "agent_runtime_failure",
                        "message": assistant_text,
                        "message_id": assistant_message.id,
                        "recovery": recovery,
                        **(
                            {"retry_last_turn": retry_last_turn}
                            if isinstance(retry_last_turn, dict)
                            else {}
                        ),
                    }
                )
                yield sse_done()

        return StreamingResponse(
            initialization_failure_events(),
            media_type="text/event-stream",
            headers=headers,
        )
    if stale_confirmation_message is not None:
        runtime_fallback = RuntimeFallbackContext(
            recovery_message=stale_confirmation_message,
            recovery=recovery_state(
                "confirmation_action_stale_card",
                language=language,
                retryable=False,
            ),
        )
    elif is_confirmation_action(payload) and not cancel_confirmation_action:
        metadata_fallback = confirmation_metadata_fallback_context(
            user_id=user.id,
            conversation_id=conversation.id,
            recent_messages=confirmation_action_messages,
            language=language,
            admit_consumed_run_replay=is_run_backtest_turn,
        )
        missing_run_confirmation_action_id = (
            payload.action is not None
            and payload.action.type == "run_backtest"
            and confirmation_action_id(payload) is None
        )
        if metadata_fallback is not None and metadata_fallback.recovery_message:
            runtime_fallback = metadata_fallback
        elif metadata_fallback is None and not checkpoint_has_pending_confirmation(
            checkpoint_values
        ):
            raise problem(
                request,
                status_code=409,
                code="confirmation_required",
                title="Confirmation Required",
                detail=(
                    "There is no pending strategy confirmation to approve. "
                    "Describe the idea again and I will prepare a fresh confirmation."
                ),
            )
        elif metadata_fallback is None and recent_metadata_invalidates_confirmation(
            confirmation_action_messages
        ):
            raise problem(
                request,
                status_code=409,
                code="confirmation_required",
                title="Confirmation Required",
                detail=(
                    "That confirmation is no longer active. Describe the idea again "
                    "and I will prepare a fresh confirmation."
                ),
            )
        elif missing_run_confirmation_action_id:
            runtime_fallback = RuntimeFallbackContext(
                recovery_message=missing_run_confirmation_action_id_message(language),
                recovery=recovery_state(
                    "confirmation_action_missing_identity",
                    language=language,
                    retryable=False,
                ),
            )
        elif metadata_fallback is not None:
            runtime_fallback = metadata_fallback
    elif is_result_action(payload):
        validated_result_action_run = run_for_result_action(
            payload=payload,
            user=user,
            conversation_id=conversation.id,
            require_run_id=True,
        )
        result_fallback = latest_result_fallback_context(
            user_id=user.id,
            conversation_id=conversation.id,
            action_run=validated_result_action_run,
        )
        if result_fallback is not None:
            runtime_fallback = result_fallback
    elif payload.action is not None and payload.action.type == "retry_failed_action":
        failed_fallback = failed_action_metadata_fallback_context(
            user_id=user.id,
            conversation_id=conversation.id,
        )
        if failed_fallback is not None:
            runtime_fallback = failed_fallback
    elif payload.action is None:
        ordinary_fallback = ordinary_turn_metadata_fallback_context(
            user_id=user.id,
            conversation_id=conversation.id,
            language=language,
        )
        if ordinary_fallback is not None:
            runtime_fallback = ordinary_fallback
    lifecycle_hooks = request_admission.lifecycle_hooks()
    request_message_record = lifecycle_hooks.request_message

    action_context = request_admission.runtime_action_context()

    async def accepted_turn_events(
        workflow_input: dict[str, Any],
        workflow_input_error: Exception | None = None,
    ) -> AsyncIterator[str]:
        if deterministic_control_turn:
            lifecycle_hooks.mark_running()
        active_finalization_execution_identity: str | None = None
        naming_language = (
            payload.language
            or conversation.language
            or current_user_profile.language
            or "en"
        )
        receipt_run_id: str | None = None
        receipt_message_id: str | None = request_message_record.id
        receipt_metadata: dict[str, Any] = {
            "request_id": request.state.request_id,
            "source": "api_turn",
            "turn_id": request_message_record.id,
        }
        receipt_token = begin_openrouter_route_receipt_capture()

        def persist_turn_evidence() -> None:
            receipts = end_openrouter_route_receipt_capture(receipt_token)
            receipt_metadata["turn_execution"] = turn_execution_summary(receipts)
            persist_route_receipts(
                receipts=receipts,
                user_id=user.id,
                conversation_id=conversation.id,
                run_id=receipt_run_id,
                message_id=receipt_message_id,
                metadata=receipt_metadata,
            )

        def record_control_exit(semantic_turn_act: str, terminal: Any) -> None:
            exit_state = {**workflow_input, "semantic_turn_act": semantic_turn_act}
            record_exit_progress(exit_state, terminal=terminal)

        def schedule_artifact_naming(
            *,
            assistant_message: str | None,
            assistant_metadata: dict[str, Any] | None = None,
            current_run: BacktestRun | None = None,
            message_id: str | None = None,
        ) -> None:
            try:
                schedule_artifact_naming_after_stream(
                    user_id=user.id,
                    conversation_id=conversation.id,
                    language=naming_language,
                    current_run=current_run,
                    user_message=display_message,
                    assistant_message=assistant_message,
                    assistant_metadata=assistant_metadata,
                    message_id=message_id,
                    run_id=current_run.id if current_run is not None else None,
                    viewport=payload.viewport,
                )
            except Exception:
                logger.opt(exception=True).warning(
                    "Artifact naming scheduling failed",
                    user_id=user.id,
                    conversation_id=conversation.id,
                )

        if runtime_fallback.recovery_message:
            assistant_text = rewrite_visible_reply(
                runtime_fallback.recovery_message, surface="chat_stream"
            ).text
            recovery = runtime_fallback.recovery
            recovery_code = recovery.get("code") if isinstance(recovery, dict) else None
            stale_card_redirect = recovery_code == "confirmation_action_stale_card"
            stage_status = (
                "ready_to_respond" if stale_card_redirect else "await_user_reply"
            )
            metadata: dict[str, Any] = {
                "conversation_mode": "confirm",
                "agent_runtime_stage_outcome": stage_status,
                "recovery_reason": "missing_confirmation_checkpoint",
            }
            if payload.action is not None:
                metadata["chat_action"] = persisted_chat_action(payload)
            if recovery is not None:
                metadata["recovery"] = dict(recovery)
            assistant_message = lifecycle_hooks.complete(
                content=assistant_text,
                metadata=metadata,
                settle_usage=guest_compute_settlement(
                    turn_account,
                    is_run_backtest_turn=is_run_backtest_turn,
                    visitor_key=turn_visitor_key,
                ),
            )
            progress = "redirected" if stale_card_redirect else "clarification"
            record_control_exit("retry_failed_action", progress)
            persist_turn_evidence()
            yield sse_data({"type": "stage_start", "stage": "clarify"})
            if recovery is None:
                yield sse_data({"type": "token", "content": assistant_text})
            yield sse_data(
                {
                    "type": "stage_outcome",
                    "outcome": stage_status,
                }
            )
            yield sse_data(
                {
                    "type": "final",
                    "payload": {
                        "stage_outcome": stage_status,
                        "assistant_response": assistant_text,
                        "message_id": assistant_message.id,
                        **({"recovery": recovery} if recovery is not None else {}),
                    },
                }
            )
            yield sse_done()
            return

        if retest_turn is not None:
            try:
                retest_payload = complete_retest_turn(
                    turn=retest_turn,
                    lifecycle_hooks=lifecycle_hooks,
                    conversation_id=conversation.id,
                    language=runtime_user.language_preference,
                    settle_usage=guest_compute_settlement(
                        turn_account,
                        is_run_backtest_turn=False,
                        visitor_key=turn_visitor_key,
                    ),
                )
            except Exception:
                logger.exception(
                    "Retest confirmation materialization failed",
                    conversation_id=conversation.id,
                    source_run_id=retest_turn.source_run_id,
                )
                failure_payload = failed_retest_turn(
                    turn=retest_turn,
                    lifecycle_hooks=lifecycle_hooks,
                    request_message=request_message_record,
                    language=runtime_user.language_preference,
                )
                claim_turn_terminal("recoverable_failed", "agent_runtime_failure")
                record_control_exit("retest_run", "recoverable_failed")
                persist_turn_evidence()
                yield sse_data({"type": "final", "payload": failure_payload})
                yield sse_done()
                return
            record_control_exit("retest_run", "finished")
            persist_turn_evidence()
            yield sse_data({"type": "final", "payload": retest_payload})
            yield sse_done()
            return

        if cancel_confirmation_action and payload.action is not None:
            assert cancellation_admission is not None
            _, final_payload = complete_confirmation_cancellation(
                payload=payload,
                admission=cancellation_admission,
                lifecycle_hooks=lifecycle_hooks,
            )
            record_control_exit("approval", "finished")
            persist_turn_evidence()
            yield sse_data({"type": "final", "payload": final_payload})
            yield sse_done()
            return

        streamed_text_parts: list[str] = []
        reply_rewrites = ReplyRewrites(surface="chat_stream")
        shadow_context_token = set_backtest_job_shadow_context(
            BacktestJobShadowContext(
                user_id=user.id,
                conversation_id=conversation.id,
                account_kind=turn_account.kind,
                request_message_id=(
                    request_message_record.id if request_message_record else None
                ),
                confirmation_message_id=runtime_fallback.confirmation_message_id,
                idempotency_key=clean_idempotency_key,
                request_id=request.state.request_id,
                chat_action=action_context,
                allowance_limits=allowance_windows(
                    turn_account,
                    SIMULATION_USAGE_RESOURCE,
                ),
                visitor_key=(
                    visitor_key_for(turn_client_identity)
                    if turn_account.kind == "guest"
                    else None
                ),
            )
        )
        try:
            if workflow_input_error is not None:
                raise workflow_input_error

            def runtime_event_source(
                active_workflow: Any,
            ) -> AsyncIterator[dict[str, Any]]:
                return stream_agent_turn_events(
                    workflow=active_workflow,
                    user=runtime_user,
                    thread_id=conversation.id,
                    message=request_message,
                    workflow_input=workflow_input,
                    recent_thread_history=recent_thread_history,
                    context_hints=[
                        item.model_dump(mode="python") for item in mention_provenance
                    ],
                    action_context=action_context,
                    fallback_latest_task_snapshot=runtime_fallback.latest_task_snapshot,
                    fallback_selected_thread_metadata=(
                        runtime_fallback.selected_thread_metadata
                    ),
                    fallback_artifact_references=runtime_fallback.artifact_references,
                    fallback_confirmation_payload=runtime_fallback.confirmation_payload,
                )

            async def isolated_runtime_event_source() -> AsyncIterator[dict[str, Any]]:
                async with api_state.isolated_agent_runtime_workflow() as active_workflow:
                    async for event in runtime_event_source(active_workflow):
                        yield event

            runtime_events = (
                threaded_runtime_event_source(isolated_runtime_event_source)
                if runtime_worker_enabled()
                else runtime_event_source(workflow)
            )
            final_seen = False
            private_result_stream = (
                getattr(payload.action, "type", None) == "show_breakdown"
            )
            async for runtime_event in _runtime_events_with_keepalive(runtime_events):
                if runtime_event is None:
                    yield sse_keepalive()
                    continue
                event_type = runtime_event.get("type")
                if event_type == "token":
                    content = reply_rewrites.token(
                        str(runtime_event.get("content") or "")
                    )
                    if content:
                        streamed_text_parts.append(content)
                    if not private_result_stream:
                        yield sse_data({**runtime_event, "content": content})
                    continue
                if event_type in {"stage_start", "stage_outcome"}:
                    if runtime_event.get("stage") == "explain":
                        private_result_stream = True
                    yield sse_data(runtime_event)
                    continue
                if event_type != "final":
                    continue

                final_seen = True
                if (flushed := reply_rewrites.flush()) and not private_result_stream:
                    streamed_text_parts.append(flushed)
                    yield sse_data({"type": "token", "content": flushed})
                apply_turn_progress_evidence(runtime_event.get("_turn_progress"))
                discovery_usage_evidence = runtime_event.get("_discovery_usage")
                runtime_result = dict(runtime_event.get("payload") or {})
                recovery = runtime_result.get("recovery")
                if (
                    isinstance(recovery, dict)
                    and recovery.get("retryable") is True
                    and isinstance(runtime_result.get("retry_last_turn"), dict)
                ):
                    raise RuntimeError("agent_runtime_typed_recovery")
                stage_status = runtime_stage_status(runtime_result)
                assistant_text = runtime_result_message(runtime_result)
                confirmation_id = ensure_unspent_confirmation_identity(
                    runtime_result,
                    gateway=api_state.supabase_gateway,
                    user_id=user.id,
                )
                confirmation_card = chat_confirmation.runtime_confirmation_card(
                    runtime_result,
                    confirmation_id=confirmation_id,
                    conversation_id=conversation.id,
                    language=runtime_user.language_preference,
                )
                if confirmation_card is not None:
                    assistant_text = None
                    runtime_result.pop("assistant_response", None)
                    runtime_result.pop("assistant_prompt", None)
                tool_publication = prepare_runtime_tool_publication(
                    runtime_result,
                    runtime_event.get("_tool_effects"),
                    assistant_text=assistant_text,
                    user_id=user.id,
                    conversation_id=conversation.id,
                    request_message_id=lifecycle_hooks.turn_id,
                    request_id=request.state.request_id,
                )
                tool_result_cards = tool_publication.cards
                assistant_text = tool_publication.assistant_text
                result_card = tool_publication.result_card
                envelope = runtime_result_envelope(runtime_result)
                backtest_job = tool_publication.backtest_job
                run = None
                completed_breakdown_message = None
                result_action_run = validated_result_action_run
                result_action_type = result_action_request_type(runtime_result)
                if (
                    result_action_type is None
                    and payload.action is not None
                    and payload.action.presentation == "result"
                    and payload.action.type in {"show_breakdown", "save_strategy"}
                    and (not assistant_text or stage_status == "await_approval")
                ):
                    result_action_type = payload.action.type

                if result_card is not None:
                    from argus.api.chat.persistence import persist_runtime_backtest_run

                    result_card.update(stored_readout_metadata(runtime_result))
                    active_finalization_execution_identity = chat_retry.backtest_finalization_execution_identity(
                        backtest_job=backtest_job,
                        retry_execution_identity=retry_finalization_execution_identity,
                        idempotency_key=clean_idempotency_key,
                        request_id=request.state.request_id,
                    )
                    run = persist_runtime_backtest_run(
                        user=user,
                        conversation=conversation,
                        result_card=result_card,
                        envelope=envelope,
                        quick_take=assistant_text,
                        execution_identity=active_finalization_execution_identity,
                    )

                metadata: dict[str, Any] = {
                    "conversation_mode": (
                        "result_review"
                        if result_card is not None or result_action_type is not None
                        else "confirm"
                        if stage_status == "await_approval"
                        else "setup"
                        if stage_status == "await_user_reply"
                        else "guide"
                    ),
                    "agent_runtime_stage_outcome": stage_status,
                }
                if payload.action is not None:
                    metadata["chat_action"] = persisted_chat_action(payload)
                if result_action_type is not None and payload.action is not None:
                    confirmation_card = None
                    runtime_result.pop("confirmation", None)
                    runtime_result.pop("confirmation_payload", None)
                    runtime_result.pop("active_confirmation_reference", None)
                    if result_action_run is None:
                        result_action_run = run_for_result_action(
                            payload=payload,
                            user=user,
                            conversation_id=conversation.id,
                            require_run_id=True,
                        )
                    if result_action_type == "show_breakdown":
                        completion = start_result_breakdown(
                            result_action_run,
                            language=runtime_user.language_preference,
                            lifecycle=lifecycle_hooks,
                            settle_usage=guest_compute_settlement(
                                turn_account,
                                is_run_backtest_turn=is_run_backtest_turn,
                                visitor_key=turn_visitor_key,
                            ),
                        )
                        yield sse_data({"type": "stage_start", "stage": "explain"})
                        dispatched = await asyncio.shield(completion)
                        backtest_job = dispatched.job
                        completed_breakdown_message = dispatched.message
                        assistant_text = dispatched.text
                        metadata.update(dispatched.metadata)
                        runtime_result.update(dispatched.metadata)
                    elif result_action_type == "save_strategy":
                        yield sse_data({"type": "stage_start", "stage": "next_step"})
                        if result_action_run is None:
                            assistant_text = missing_result_action_run_message(
                                action_type=result_action_type,
                                language=runtime_user.language_preference,
                            )
                        else:
                            assistant_text = await compose_private_alpha_save_response(
                                metadata=result_followup_metadata_from_run(
                                    result_action_run
                                ),
                                user_message=request_message,
                                language=runtime_user.language_preference,
                            )
                            if assistant_text is None:
                                assistant_text = fallback_private_alpha_save_response(
                                    language=runtime_user.language_preference
                                )
                    if assistant_text:
                        runtime_result["assistant_response"] = assistant_text
                    if result_action_run is not None:
                        receipt_run_id = result_action_run.id
                        runtime_result["latest_run_id"] = result_action_run.id
                        runtime_result["result_fact_bank"] = result_fact_bank(
                            result_action_run
                        )
                        runtime_result["result_run_id"] = result_action_run.id
                        runtime_result["result_strategy_id"] = (
                            result_action_run.strategy_id
                        )
                for key in (
                    *READOUT_METADATA_KEYS,
                    "latest_run_id",
                    "source_result_run_id",
                    "strategy_path_id",
                    "result_run_id",
                    "result_strategy_id",
                    "result_conversation_id",
                    "result_fact_bank",
                    "response_intent",
                    "clarification",
                    "discovery",
                    "next_experiments",
                    "next_steps",
                    "answer_text_template",
                    "answer_assumptions",
                    "calculation_offer",
                    "research",
                ):
                    value = runtime_result.get(key)
                    if value is not None:
                        metadata[key] = value
                if runtime_result.get("resolution_provenance"):
                    metadata["resolution_provenance"] = runtime_result[
                        "resolution_provenance"
                    ]
                if isinstance(runtime_result.get("pending_strategy"), dict):
                    metadata["pending_strategy"] = runtime_result["pending_strategy"]
                if confirmation_card is not None:
                    metadata["confirmation_card"] = confirmation_card
                    if isinstance(runtime_result.get("confirmation_payload"), dict):
                        from argus.agent_runtime.confirmation_artifacts import (
                            confirmation_artifact_reference,
                        )

                        metadata["confirmation_payload"] = runtime_result[
                            "confirmation_payload"
                        ]
                        confirmation_reference = confirmation_artifact_reference(
                            confirmation_id=str(
                                confirmation_card.get("confirmation_id")
                                or confirmation_card.get("confirmationId")
                                or api_state.store.new_id()
                            ),
                            confirmation_payload=runtime_result["confirmation_payload"],
                            confirmation_card=confirmation_card,
                        )
                        metadata["active_confirmation_reference"] = (
                            confirmation_reference.model_dump(mode="python")
                        )
                        metadata["artifact_references"] = [
                            confirmation_reference.model_dump(mode="python")
                        ]
                        runtime_result["active_confirmation_reference"] = (
                            confirmation_reference.model_dump(mode="python")
                        )
                        runtime_result["artifact_references"] = [
                            confirmation_reference.model_dump(mode="python")
                        ]
                    runtime_result["confirmation"] = confirmation_card
                    chat_confirmation.attach_research_peer_rows(
                        runtime_result,
                        metadata,
                        user_id=user.id,
                        conversation_id=conversation.id,
                        language=runtime_user.language_preference or "en",
                    )
                if result_card is not None:
                    metadata["result_card"] = result_card
                if tool_result_cards:
                    metadata["tool_result_cards"] = tool_result_cards
                    computation = computation_marker(tool_result_cards)
                    if computation is not None:
                        metadata["computation"] = computation
                if runtime_result.get("tool_jobs"):
                    metadata["tool_jobs"] = runtime_result["tool_jobs"]
                if backtest_job is not None:
                    metadata["backtest_job"] = backtest_job
                    metadata["backtest_job_id"] = backtest_job.get("id")
                    runtime_result["backtest_job"] = backtest_job
                latest_failed_action_reference = runtime_result.get(
                    "latest_failed_action_reference"
                )
                if isinstance(latest_failed_action_reference, dict):
                    metadata["latest_failed_action_reference"] = (
                        latest_failed_action_reference
                    )
                    failed_action_metadata = latest_failed_action_reference.get(
                        "metadata"
                    )
                    if isinstance(failed_action_metadata, dict):
                        metadata["failed_action"] = dict(failed_action_metadata)
                retry_last_turn = runtime_result.get("retry_last_turn")
                if isinstance(retry_last_turn, dict):
                    metadata["retry_last_turn"] = dict(retry_last_turn)
                recovery = runtime_result.get("recovery")
                if isinstance(recovery, dict):
                    metadata["recovery"] = dict(recovery)
                if run is not None:
                    # Publication derives from what the link write did; a
                    # refused link withholds the result and settles the
                    # turn on the run_result_withheld recovery.
                    publication = apply_result_link_outcome(
                        run=run,
                        metadata=metadata,
                        runtime_result=runtime_result,
                        gateway=api_state.supabase_gateway,
                        user_id=user.id,
                        language=runtime_user.language_preference,
                        dev_memory_fallback_enabled=dev_memory_fallback_enabled(),
                    )
                    if publication.publishable:
                        receipt_run_id = run.id
                        result_card = publication.result_card
                    else:
                        assistant_text = publication.assistant_text
                        tool_result_cards = runtime_tool_result_cards(runtime_result)
                        run = None

                streamed_text = "".join(streamed_text_parts).strip()
                if (
                    streamed_text
                    and confirmation_card is None
                    and run is None
                    and not assistant_text
                ):
                    assistant_text = streamed_text
                    runtime_result["assistant_response"] = streamed_text

                # A card turn persists no prose; its readers derive from the card.
                persisted_text = (
                    ""
                    if confirmation_card is not None
                    else assistant_text or streamed_text
                )
                assistant_text, persisted_text = reply_rewrites.finalize(
                    runtime_result=runtime_result,
                    metadata=metadata,
                    assistant_text=assistant_text,
                    persisted_text=persisted_text,
                )
                typed_artifact_answer = (
                    artifact_presentation_kind(metadata) in {"assumptions", "breakdown"}
                    or confirmation_card is not None
                    or bool(tool_result_cards)
                )
                if not (
                    persisted_text
                    or confirmation_card is not None
                    or run is not None
                    or backtest_job is not None
                    or typed_artifact_answer
                ):
                    logger.warning(
                        "Agent runtime returned no visible terminal state",
                        conversation_id=conversation.id,
                        request_id=request.state.request_id,
                        stage_outcome=stage_status,
                        final_payload_keys=sorted(runtime_result.keys()),
                    )
                    raise RuntimeError("agent_runtime_empty_final")
                assistant_message = completed_breakdown_message
                if assistant_message is None and (
                    persisted_text
                    or typed_artifact_answer
                    or lifecycle_hooks.turn_id is not None
                ):
                    retryable_recovery_code = chat_retry.durable_retry_code(recovery)
                    if retryable_recovery_code is not None:
                        # The lifecycle owns durable retries on failed lookups.
                        assistant_message = lifecycle_hooks.recoverable_failure(
                            content=persisted_text or "",
                            metadata=metadata,
                            failure_code=retryable_recovery_code,
                            retryable=True,
                        )
                        live_retry = chat_retry.live_retry_payload(assistant_message)
                        if live_retry is not None:
                            runtime_result["retry_last_turn"] = live_retry
                    else:
                        await annotate_memory_recalls(
                            metadata,
                            runtime_result,
                            user=user,
                            account=turn_account,
                            conversation_id=conversation.id,
                            user_message=display_message,
                            memory_opt_out=payload.memory_opt_out,
                        )
                        assistant_message = lifecycle_hooks.complete(
                            content=persisted_text or "",
                            metadata=metadata,
                            settle_usage=guest_compute_settlement(
                                turn_account,
                                is_run_backtest_turn=is_run_backtest_turn,
                                visitor_key=turn_visitor_key,
                            ),
                        )
                    if (
                        lifecycle_hooks.turn_id is not None
                        and retryable_recovery_code is None
                    ):
                        runtime_result.pop("retry_last_turn", None)
                    receipt_message_id = assistant_message.id
                elif assistant_message is not None:
                    receipt_message_id = assistant_message.id
                settle_metered_turn(
                    runtime_result,
                    discovery_usage=discovery_usage_evidence,
                    user_id=user.id,
                    is_guest=turn_is_guest,
                    client_identity=turn_client_identity,
                    conversation_id=conversation.id,
                    message_id=assistant_message.id
                    if assistant_message is not None
                    else None,
                    request_id=request.state.request_id,
                    tool_effects=tool_publication.effects,
                )
                receipt_metadata = {
                    "request_id": request.state.request_id,
                    "source": "api_turn",
                    "stage_outcome": stage_status,
                    "conversation_mode": metadata.get("conversation_mode"),
                }
                if result_action_type is not None:
                    receipt_metadata["chat_action"] = result_action_type

                runtime_result["message_id"] = (
                    assistant_message.id if assistant_message is not None else None
                )
                if assistant_text and not runtime_result.get("assistant_response"):
                    runtime_result["assistant_response"] = assistant_text
                public_result = reader_chat_result(runtime_result, metadata)
                if (
                    not streamed_text_parts
                    and confirmation_card is None
                    and run is None
                    and assistant_text
                    and public_result.get("assistant_response")
                ):
                    yield sse_data({"type": "token", "content": assistant_text})

                yield sse_data(
                    {
                        "type": "final",
                        "payload": public_result,
                    }
                )
                yield sse_done()
                schedule_runtime_measurement_events_after_stream(
                    user_id=user.id,
                    conversation_id=conversation.id,
                    runtime_result=runtime_result,
                    metadata=metadata,
                )
                schedule_artifact_naming(
                    assistant_message=persisted_text,
                    assistant_metadata=metadata,
                    current_run=result_action_run or run,
                    message_id=(
                        assistant_message.id if assistant_message is not None else None
                    ),
                )
                return
            if not final_seen:
                raise RuntimeError("agent_runtime_missing_final")
        except Exception as exc:
            finalization_failed = isinstance(exc, BacktestFinalizationError)
            failure_code = (
                "finalization_failed" if finalization_failed else "agent_runtime_failure"
            )
            runtime_diagnostics = _runtime_failure_diagnostics(exc)
            logger.exception(
                "Agent runtime chat streaming failed",
                conversation_id=conversation.id,
                runtime_diagnostics=runtime_diagnostics,
            )
            assistant_text = recovery_message(
                "runtime_failure",
                language=runtime_user.language_preference,
            )
            failure_metadata: dict[str, Any] = {
                "conversation_mode": "recovery",
                "agent_runtime_stage_outcome": "agent_runtime_failure",
                "failure_code": failure_code,
                "retryable": finalization_failed or not is_run_backtest_turn,
            }
            if finalization_failed and active_finalization_execution_identity:
                failure_metadata["backtest_finalization"] = {
                    "execution_identity": active_finalization_execution_identity,
                }
            durable_retryable = finalization_failed or not is_run_backtest_turn
            recovery = recovery_state(
                "runtime_failure",
                language=runtime_user.language_preference,
                retryable=durable_retryable,
            )
            failure_metadata["recovery"] = recovery
            if durable_retryable:
                failure_metadata.update(
                    chat_retry.durable_retry_last_turn_metadata(
                        request_message_record,
                    )
                )
            await mark_terminal_runtime_failure_checkpoint(
                workflow=workflow,
                conversation_id=conversation.id,
                user=runtime_user,
                message=request_message,
                recent_thread_history=recent_thread_history,
                failure_metadata=failure_metadata,
            )
            assistant_message = lifecycle_hooks.recoverable_failure(
                content=assistant_text,
                metadata=failure_metadata,
                failure_code=failure_code,
                retryable=durable_retryable,
            )
            retry_last_turn = (
                assistant_message.metadata.get("retry_last_turn")
                if isinstance(assistant_message.metadata, dict)
                else None
            )
            receipt_message_id = assistant_message.id
            receipt_metadata = {
                "request_id": request.state.request_id,
                "source": "api_turn",
                "stage_outcome": failure_code,
                "conversation_mode": "recovery",
            }
            if runtime_diagnostics is not None:
                receipt_metadata["runtime_diagnostics"] = runtime_diagnostics
            claim_turn_terminal(
                "recoverable_failed",
                (
                    str(runtime_diagnostics.get("code"))
                    if runtime_diagnostics is not None and runtime_diagnostics.get("code")
                    else failure_code
                ),
            )
            record_exit_progress(workflow_input, terminal="recoverable_failed")
            yield sse_data(
                {
                    "type": "error",
                    "code": failure_code,
                    "message": assistant_text,
                    "message_id": assistant_message.id,
                    "recovery": recovery,
                    **(
                        {"retry_last_turn": retry_last_turn}
                        if isinstance(retry_last_turn, dict)
                        else {}
                    ),
                }
            )
            yield sse_done()
            return
        finally:
            reset_backtest_job_shadow_context(shadow_context_token)
            claim_turn_terminal("recoverable_failed", "stream_severed")
            persist_turn_evidence()

    async def events() -> AsyncIterator[str]:
        with (
            openrouter_traffic_class(turn_account.kind),
            turn_execution_scope(entry_state=checkpoint_values or {}),
            research_attempt_admission_context(
                lambda: claim_research_provider_attempt(
                    guest_visitor_key=turn_guest_research_key
                ),
                release=lambda admission: release_research_provider_claim(
                    admission, guest_visitor_key=turn_guest_research_key
                ),
            ),
        ):
            workflow_input_error: Exception | None = None
            try:
                workflow_input = build_workflow_input(
                    user=runtime_user,
                    message=request_message,
                    recent_thread_history=recent_thread_history,
                    discovery_allowance_available=discovery_allowance_for_turn(
                        user.id,
                        is_guest=turn_is_guest,
                        client_identity=turn_client_identity,
                    ),
                    context_hints=[
                        item.model_dump(mode="python") for item in mention_provenance
                    ],
                    action_context=action_context,
                    fallback_latest_task_snapshot=runtime_fallback.latest_task_snapshot,
                    fallback_selected_thread_metadata=(
                        runtime_fallback.selected_thread_metadata
                    ),
                    fallback_artifact_references=runtime_fallback.artifact_references,
                    fallback_confirmation_payload=runtime_fallback.confirmation_payload,
                )
                set_turn_entry_state(workflow_input)
            except Exception as exc:
                workflow_input = {}
                workflow_input_error = exc
            accepted_events = accepted_turn_events(workflow_input, workflow_input_error)
            try:
                async for event in accepted_events:
                    yield event
            finally:
                await accepted_events.aclose()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers=headers,
    )
