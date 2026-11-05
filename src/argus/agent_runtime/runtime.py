from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable
from typing import Any

from loguru import logger

from argus.agent_runtime.artifact_action_recovery import (
    artifact_action_recovery_message,
)
from argus.agent_runtime.history import select_thread_history
from argus.agent_runtime.next_experiments import offered_kinds_from_thread_metadata
from argus.agent_runtime.state.models import (
    ArtifactReference,
    ConfirmationPayload,
    ConversationMessage,
    ResolutionProvenance,
    RunState,
    StrategySummary,
    TaskSnapshot,
    UserState,
    dedupe_resolution_provenance_items,
)
from argus.agent_runtime.substage_events import (
    bind_substage_channel,
    close_substage_channel,
)
from argus.agent_runtime.turn_execution import (
    record_exit_progress,
    turn_progress_evidence,
)
from argus.agent_runtime.workflow_contract import (
    TOKEN_STREAM_NODES,
    WORKFLOW_NODE_NAMES,
)
from argus.domain.result_readout_content import READOUT_METADATA_KEYS

MAX_RECENT_THREAD_HISTORY = 6
WorkflowState = dict[str, Any]


def build_workflow_input(
    *,
    user: UserState,
    message: str,
    recent_thread_history: Iterable[ConversationMessage | dict[str, Any]] | None = None,
    context_hints: Iterable[ResolutionProvenance | dict[str, Any]] | None = None,
    action_context: dict[str, Any] | None = None,
    fallback_latest_task_snapshot: TaskSnapshot | dict[str, Any] | None = None,
    fallback_selected_thread_metadata: dict[str, Any] | None = None,
    fallback_artifact_references: Iterable[ArtifactReference | dict[str, Any]]
    | None = None,
    fallback_confirmation_payload: ConfirmationPayload | dict[str, Any] | None = None,
    discovery_allowance_available: bool = True,
) -> WorkflowState:
    normalized_message = " ".join(message.strip().split())
    run_state = RunState.new(
        current_user_message=normalized_message,
        recent_thread_history=_bounded_recent_thread_history(
            list(recent_thread_history or [])
        ),
        context_hints=list(context_hints or []),
        action_context=action_context,
    )
    run_state.discovery_allowance_available = discovery_allowance_available
    run_state.prior_next_experiment_kinds = offered_kinds_from_thread_metadata(
        fallback_selected_thread_metadata
    )
    if fallback_confirmation_payload is not None:
        run_state.confirmation_payload = ConfirmationPayload.model_validate(
            fallback_confirmation_payload
        )
    workflow_input: WorkflowState = {
        "run_state": run_state,
        "user": user,
    }
    if fallback_latest_task_snapshot is not None:
        workflow_input["latest_task_snapshot"] = TaskSnapshot.model_validate(
            fallback_latest_task_snapshot
        )
    if fallback_selected_thread_metadata:
        workflow_input["selected_thread_metadata"] = dict(
            fallback_selected_thread_metadata
        )
    if fallback_artifact_references is not None:
        workflow_input["artifact_references"] = resolve_persisted_artifact_references(
            fallback_artifact_references
        )
    return workflow_input


async def stream_agent_turn_events(
    *,
    workflow: Any,
    user: UserState,
    thread_id: str,
    message: str,
    workflow_input: WorkflowState | None = None,
    recent_thread_history: Iterable[ConversationMessage | dict[str, Any]] | None = None,
    context_hints: Iterable[ResolutionProvenance | dict[str, Any]] | None = None,
    action_context: dict[str, Any] | None = None,
    fallback_latest_task_snapshot: TaskSnapshot | dict[str, Any] | None = None,
    fallback_selected_thread_metadata: dict[str, Any] | None = None,
    fallback_artifact_references: Iterable[ArtifactReference | dict[str, Any]]
    | None = None,
    fallback_confirmation_payload: ConfirmationPayload | dict[str, Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    initial_state = (
        workflow_input
        if workflow_input is not None
        else build_workflow_input(
            user=user,
            message=message,
            recent_thread_history=recent_thread_history,
            context_hints=context_hints,
            action_context=action_context,
            fallback_latest_task_snapshot=fallback_latest_task_snapshot,
            fallback_selected_thread_metadata=fallback_selected_thread_metadata,
            fallback_artifact_references=fallback_artifact_references,
            fallback_confirmation_payload=fallback_confirmation_payload,
        )
    )
    config = {"configurable": {"thread_id": thread_id}}
    seen_stage_starts: set[str] = set()
    seen_stage_outcomes: set[str] = set()
    logger.debug("Agent runtime stream started", thread_id=thread_id)

    # Sub-stage events (work inside a node) merge with LangGraph's stream
    # through one queue, so they reach the client while the node still runs.
    queue: asyncio.Queue[Any] = asyncio.Queue()

    async def _pump_workflow_events() -> None:
        # Bound inside this task: stages run in its context tree, and the
        # binding cannot outlive the turn.
        channel_token = bind_substage_channel(queue)
        try:
            async for event in workflow.astream_events(
                initial_state,
                config=config,
                version="v2",
            ):
                queue.put_nowait(("langgraph", event))
        except BaseException as exc:
            queue.put_nowait(("error", exc))
            return
        finally:
            close_substage_channel(channel_token)
        queue.put_nowait(("done", None))

    pump = asyncio.create_task(_pump_workflow_events())
    try:
        while True:
            item_kind, item = await queue.get()
            if item_kind == "done":
                break
            if item_kind == "error":
                raise item
            if item_kind == "substage":
                logger.debug(
                    "Agent runtime sub-stage started",
                    thread_id=thread_id,
                    stage=item.get("stage"),
                )
                yield {"type": "stage_start", **item}
                continue
            event = item
            kind = event.get("event")
            node_name = _event_node_name(event)
            if kind == "on_chain_start" and node_name in WORKFLOW_NODE_NAMES:
                if node_name not in seen_stage_starts:
                    seen_stage_starts.add(node_name)
                    logger.debug(
                        "Agent runtime stage started",
                        thread_id=thread_id,
                        stage=node_name,
                    )
                    yield {"type": "stage_start", "stage": node_name}
                continue
            if kind == "on_chat_model_stream" and node_name in TOKEN_STREAM_NODES:
                content = _chunk_content(event.get("data", {}).get("chunk"))
                if content:
                    yield {"type": "token", "content": content}
                continue
            if kind == "on_chain_end" and node_name in WORKFLOW_NODE_NAMES:
                outcome = _stage_outcome_from_event(event)
                if outcome is not None and outcome not in seen_stage_outcomes:
                    seen_stage_outcomes.add(outcome)
                    logger.debug(
                        "Agent runtime stage outcome",
                        thread_id=thread_id,
                        stage=node_name,
                        outcome=outcome,
                    )
                    yield {"type": "stage_outcome", "outcome": outcome}
    finally:
        pump.cancel()

    logger.debug("Agent runtime final state fetch started", thread_id=thread_id)
    final_state = await _final_workflow_state(workflow=workflow, config=config)
    logger.debug("Agent runtime final state fetch completed", thread_id=thread_id)
    record_exit_progress(
        final_state,
        terminal=_progress_terminal(final_state.get("stage_outcome")),
    )
    yield {
        "type": "final",
        "payload": _public_result(final_state),
        "_turn_progress": turn_progress_evidence(),
        "_discovery_usage": final_state.get("discovery_usage"),
        "_tool_effects": final_state.get("tool_effects"),
    }


def _progress_terminal(stage_outcome: Any) -> str | None:
    normalized = str(getattr(stage_outcome, "value", stage_outcome) or "")
    if normalized in {"await_user_reply", "needs_clarification"}:
        return "clarification"
    if normalized == "execution_failed_recoverably":
        return "recoverable_failed"
    if normalized == "execution_failed_terminally":
        return "terminal_failed"
    if normalized == "end_run":
        return "finished"
    return None


async def run_agent_turn(
    *,
    workflow: Any,
    user: UserState,
    thread_id: str,
    message: str,
    recent_thread_history: Iterable[ConversationMessage | dict[str, Any]] | None = None,
    context_hints: Iterable[ResolutionProvenance | dict[str, Any]] | None = None,
    action_context: dict[str, Any] | None = None,
    fallback_latest_task_snapshot: TaskSnapshot | dict[str, Any] | None = None,
    fallback_selected_thread_metadata: dict[str, Any] | None = None,
    fallback_artifact_references: Iterable[ArtifactReference | dict[str, Any]]
    | None = None,
    fallback_confirmation_payload: ConfirmationPayload | dict[str, Any] | None = None,
) -> dict[str, Any]:
    final_payload: dict[str, Any] | None = None
    async for event in stream_agent_turn_events(
        workflow=workflow,
        user=user,
        thread_id=thread_id,
        message=message,
        recent_thread_history=recent_thread_history,
        context_hints=context_hints,
        action_context=action_context,
        fallback_latest_task_snapshot=fallback_latest_task_snapshot,
        fallback_selected_thread_metadata=fallback_selected_thread_metadata,
        fallback_artifact_references=fallback_artifact_references,
        fallback_confirmation_payload=fallback_confirmation_payload,
    ):
        if event.get("type") == "final":
            payload = event.get("payload")
            if isinstance(payload, dict):
                final_payload = payload
    return final_payload or {}


async def _final_workflow_state(
    *, workflow: Any, config: dict[str, Any]
) -> dict[str, Any]:
    state_snapshot = await workflow.aget_state(config)
    values = getattr(state_snapshot, "values", None)
    if not isinstance(values, dict):
        return {}
    return _compose_runtime_response(values)


def _event_node_name(event: dict[str, Any]) -> str | None:
    metadata = event.get("metadata")
    if isinstance(metadata, dict):
        node_name = metadata.get("langgraph_node")
        if isinstance(node_name, str) and node_name in WORKFLOW_NODE_NAMES:
            return node_name
    name = event.get("name")
    if isinstance(name, str) and name in WORKFLOW_NODE_NAMES:
        return name
    return None


def _stage_outcome_from_event(event: dict[str, Any]) -> str | None:
    data = event.get("data")
    if not isinstance(data, dict):
        return None
    output = data.get("output")
    if not isinstance(output, dict):
        return None
    outcome = output.get("stage_outcome")
    if outcome is None:
        return None
    return str(getattr(outcome, "value", outcome))


def _chunk_content(chunk: Any) -> str:
    content = getattr(chunk, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    return ""


def _compose_runtime_response(result: dict[str, Any]) -> dict[str, Any]:
    run_state = result.get("run_state")
    if not isinstance(run_state, RunState):
        return result
    explicit_prompt = result.get("assistant_prompt")
    if isinstance(explicit_prompt, str) and explicit_prompt.strip():
        assistant_response = result.get("assistant_response")
        if assistant_response == explicit_prompt:
            return result
        patched = dict(result)
        if not isinstance(assistant_response, str) or not assistant_response.strip():
            patched["assistant_response"] = explicit_prompt
        return patched
    intent = run_state.response_intent
    if intent is None or intent.kind != "artifact_action_recovery":
        return result
    recovery = artifact_action_recovery_message(intent)
    if recovery is None:
        return result
    patched = dict(result)
    patched["assistant_prompt"] = recovery
    patched["assistant_response"] = recovery
    return patched


def _public_result(result: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = {
        *READOUT_METADATA_KEYS,
        "stage_outcome",
        "assistant_prompt",
        "assistant_response",
        "requested_field",
        "pending_strategy",
        "optional_parameter_choices",
        "confirmation_payload",
        "backtest_job",
        "next_actions",
        "failure_classification",
        "final_response_payload",
        "response_intent",
        "clarification",
        "resolution_provenance",
        "artifact_references",
        "latest_failed_action_reference",
        "latest_run_id",
        "source_result_run_id",
        "strategy_path_id",
        "result_run_id",
        "result_strategy_id",
        "result_conversation_id",
        "result_fact_bank",
        "result_action_request",
        "retry_last_turn",
        "recovery",
        "discovery",
        "next_experiments",
        "next_steps",
        "answer_text_template",
        "answer_assumptions",
        "calculation_offer",
        "research",
        "research_job_request",
    }
    serialized = {
        key: _serialize_public_value(key, value)
        for key, value in result.items()
        if key in allowed_keys and value is not None
    }
    selected_thread_metadata = result.get("selected_thread_metadata")
    if isinstance(selected_thread_metadata, dict):
        for key in ("source_result_run_id", "strategy_path_id"):
            value = selected_thread_metadata.get(key)
            if key not in serialized and isinstance(value, str) and value:
                serialized[key] = value
    run_state = result.get("run_state")
    if run_state is not None:
        if (
            "confirmation_payload" not in serialized
            and "discovery" not in serialized
            and not serialized.get("final_response_payload", {}).get("tool_result_cards")
            and not getattr(
                getattr(run_state, "final_response_payload", None),
                "tool_result_cards",
                [],
            )
            and getattr(run_state, "semantic_turn_act", None) != "asset_discovery"
            and getattr(run_state, "confirmation_payload", None) is not None
        ):
            # A discovery turn answers who exists — recovery paths included;
            # carried confirmation state never rides its public payload.
            serialized["confirmation_payload"] = _serialize_public_value(
                "confirmation_payload",
                run_state.confirmation_payload,
            )
        if (
            "final_response_payload" not in serialized
            and getattr(run_state, "final_response_payload", None) is not None
        ):
            serialized["final_response_payload"] = _serialize_public_value(
                "final_response_payload",
                run_state.final_response_payload,
            )
        if (
            "failure_classification" not in serialized
            and getattr(run_state, "failure_classification", None) is not None
        ):
            serialized["failure_classification"] = run_state.failure_classification
        if (
            "response_intent" not in serialized
            and getattr(run_state, "response_intent", None) is not None
        ):
            serialized["response_intent"] = _serialize_public_value(
                "response_intent",
                run_state.response_intent,
            )
        if "resolution_provenance" not in serialized and getattr(
            run_state, "resolution_provenance", None
        ):
            serialized["resolution_provenance"] = [
                item.model_dump(mode="python")
                for item in dedupe_resolution_provenance_items(
                    run_state.resolution_provenance
                )
            ]
        if "pending_strategy" not in serialized:
            pending_strategy = _pending_strategy_payload(result, run_state=run_state)
            if pending_strategy is not None:
                serialized["pending_strategy"] = pending_strategy
    stage_outcome = result.get("stage_outcome")
    if stage_outcome is not None:
        serialized["stage_outcome"] = getattr(stage_outcome, "value", stage_outcome)
    return serialized


def _pending_strategy_payload(
    result: dict[str, Any],
    *,
    run_state: RunState,
) -> dict[str, Any] | None:
    stage_outcome = result.get("stage_outcome")
    stage_outcome_value = str(getattr(stage_outcome, "value", stage_outcome or ""))
    if stage_outcome_value not in {
        "needs_clarification",
        "await_user_reply",
        "ready_for_confirmation",
        "await_approval",
        "execution_failed_recoverably",
    }:
        return None
    snapshot = _task_snapshot_from_value(result.get("latest_task_snapshot"))
    strategy = (
        snapshot.pending_strategy_summary
        if snapshot is not None and snapshot.pending_strategy_summary is not None
        else run_state.candidate_strategy_draft
    )
    if not _strategy_summary_has_content(strategy):
        return None
    missing_required_fields = result.get("missing_required_fields")
    if not isinstance(missing_required_fields, list):
        missing_required_fields = list(run_state.missing_required_fields)
    requested_field = result.get("requested_field")
    if requested_field in (None, ""):
        requested_field = getattr(run_state, "requested_field", None)
    payload = {
        "strategy": strategy.model_dump(mode="python"),
        "requested_field": (
            str(requested_field) if requested_field not in (None, "") else None
        ),
        "missing_required_fields": [
            str(field) for field in missing_required_fields if isinstance(field, str)
        ],
    }
    selected_thread_metadata = result.get("selected_thread_metadata")
    if isinstance(selected_thread_metadata, dict):
        pending_resolution = selected_thread_metadata.get("pending_resolution")
        if isinstance(pending_resolution, dict):
            payload["pending_resolution"] = dict(pending_resolution)
        response_intent = selected_thread_metadata.get("response_intent")
        if isinstance(response_intent, dict):
            payload["response_intent"] = dict(response_intent)
        clarification = selected_thread_metadata.get("clarification")
        if isinstance(clarification, dict):
            payload["clarification"] = dict(clarification)
    return payload


def _task_snapshot_from_value(value: Any) -> TaskSnapshot | None:
    if value is None:
        return None
    if isinstance(value, TaskSnapshot):
        return value
    try:
        return TaskSnapshot.model_validate(value)
    except Exception:
        return None


def _strategy_summary_has_content(strategy: Any) -> bool:
    if not isinstance(strategy, StrategySummary):
        try:
            strategy = StrategySummary.model_validate(strategy)
        except Exception:
            return False
    return any(
        value not in (None, "", [], {})
        for value in strategy.model_dump(mode="python").values()
    )


def _serialize_public_value(key: str, value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="python")
    if isinstance(value, list):
        return [
            item.model_dump(mode="python") if hasattr(item, "model_dump") else item
            for item in value
        ]
    return value


def _bounded_recent_thread_history(
    message_history: list[ConversationMessage | dict[str, Any]],
) -> list[ConversationMessage]:
    bounded: list[ConversationMessage] = []
    for message in select_thread_history(
        message_history, recent_limit=MAX_RECENT_THREAD_HISTORY
    ):
        if isinstance(message, ConversationMessage):
            bounded.append(message.model_copy(deep=True))
        else:
            bounded.append(ConversationMessage.model_validate(message))
    return bounded


def resolve_persisted_artifact_references(
    raw_references: Iterable[ArtifactReference | dict[str, Any]],
) -> list[ArtifactReference]:
    return [ArtifactReference.model_validate(reference) for reference in raw_references]
