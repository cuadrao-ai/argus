"""Declared calls executed inside the existing LangGraph execute stage."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from argus.agent_runtime.stages.interpret_types import StageOutcome, StageResult
from argus.agent_runtime.state.models import (
    ArtifactReference,
    RunState,
    TaskSnapshot,
    UserState,
)
from argus.agent_runtime.substage_events import emit_tool_progress
from argus.domain.tool_contracts import (
    MAX_TOOL_CALLS,
    ToolCall,
    ToolFailure,
    ToolOutcome,
    ToolResultCard,
)
from argus.domain.tool_declaration import (
    ToolCatalog,
    ToolDeclaration,
    ToolInvocationError,
)
from pydantic import ValidationError


@dataclass
class ToolExecutionContext:
    """Trusted dependencies and publication handoff; never model arguments."""

    state: RunState
    user: UserState | None
    backtest_tool: Any
    max_retries: int
    language: str
    latest_task_snapshot: TaskSnapshot | None = None
    selected_thread_metadata: dict[str, Any] = field(default_factory=dict)
    call: ToolCall | None = None
    artifact_id: str = field(default_factory=lambda: str(uuid4()))
    approval_available: bool = False
    stage_result: StageResult | None = None
    business: Any | None = None


_active_tool_context: ContextVar[ToolExecutionContext | None] = ContextVar(
    "argus_active_tool_context", default=None
)


def current_tool_execution_context() -> ToolExecutionContext | None:
    """Expose the same trusted context to an existing durable tool adapter."""
    return _active_tool_context.get()


async def execute_tool_calls_async(
    *,
    state: RunState,
    tool: Any,
    catalog: ToolCatalog | None = None,
    max_retries: int = 2,
    language: str = "en",
    user: UserState | None = None,
    latest_task_snapshot: TaskSnapshot | None = None,
    selected_thread_metadata: dict[str, Any] | None = None,
    business_bindings: tuple[Any, ...] | None = None,
) -> StageResult:
    calls = list(state.tool_calls)
    if business_bindings is not None and len(business_bindings) != len(calls):
        return _rejected_batch("business_binding_count_mismatch")
    if not calls and state.confirmation_payload is not None:
        from argus.agent_runtime.tools.registered_backtest import approved_backtest_call

        approved = approved_backtest_call(state)
        if approved is not None:
            calls = [approved]
    if not calls:
        return StageResult(
            outcome="ready_to_respond",
            stage_patch={"tool_calls": [], "tool_call_records": [], "tool_effects": []},
        )
    if len(calls) > MAX_TOOL_CALLS:
        return _rejected_batch("too_many_tool_calls")
    if len({call.call_id for call in calls}) != len(calls):
        return _rejected_batch("duplicate_tool_call_id")
    if catalog is None:
        from argus.domain.capability_registry import get_tool_catalog

        catalog = get_tool_catalog()
    if any(catalog.get(call.tool_name) is None for call in calls):
        return _rejected_batch("unknown_tool")

    patch: dict[str, Any] = {
        "tool_calls": [],
        "tool_call_records": [],
        "tool_effects": [],
    }
    cards: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []
    outcome: StageOutcome = "ready_to_respond"
    for index, call in enumerate(calls):
        declaration = catalog.get(call.tool_name)
        assert declaration is not None  # The whole batch was checked before dispatch.
        context = ToolExecutionContext(
            state=state,
            user=user,
            backtest_tool=tool,
            max_retries=max_retries,
            language=language,
            latest_task_snapshot=latest_task_snapshot,
            selected_thread_metadata=(
                selected_thread_metadata if selected_thread_metadata is not None else {}
            ),
            call=call,
            artifact_id=str(uuid4()),
            approval_available=index == 0 and business_bindings is None,
            business=business_bindings[index] if business_bindings is not None else None,
        )
        try:
            arguments = declaration.validate_arguments(call.arguments)
        except ToolInvocationError as exc:
            tool_outcome = exc.outcome
        except (ValidationError, ValueError, TypeError):
            tool_outcome = ToolOutcome(
                status="invalid", failure=ToolFailure(code="invalid_arguments")
            )
        else:
            if declaration.policy.confirmation == "required":
                prepared = await declaration.prepare_confirmation(
                    arguments, context=context
                )
                confirmation = StageResult.model_validate(
                    prepared.model_dump(mode="python")
                )
                if confirmation.outcome != "approved_for_execution":
                    patch.update(confirmation.patch)
                    patch["tool_calls"] = calls[index:]
                    return _with_cards(
                        confirmation.outcome,
                        patch=patch,
                        cards=cards,
                        references=references,
                    )
            emit_tool_progress(
                declaration.progress_facts(arguments, call_id=call.call_id)
            )
            token = _active_tool_context.set(context)
            try:
                tool_outcome = await declaration.invoke(arguments, context=context)
            finally:
                _active_tool_context.reset(token)

        # Durable admission may resolve this invocation to an existing call.
        # Its frozen binding owns the published identity on a replay.
        settled_call = ToolCall.model_validate(context.call)
        if (
            settled_call.tool_name != call.tool_name
            or settled_call.arguments != call.arguments
        ):
            raise ValueError("A durable replay cannot change the declared call")
        call = settled_call
        patch["tool_call_records"].append(_call_record(call, tool_outcome))
        if context.stage_result is not None:
            side_patch = context.stage_result.patch
            patch["tool_effects"].append(
                {
                    "call_id": call.call_id,
                    "tool_name": call.tool_name,
                    "artifact_id": context.artifact_id,
                    "stage_patch": dict(side_patch),
                }
            )
            # Existing durable backtest/research writers remain publication
            # owners. Execution traces never replace the identity of a call.
            side_patch.pop("tool_call_records", None)
            side_references = side_patch.pop("artifact_references", [])
            references.extend(side_references)
            patch.update(side_patch)
            outcome = context.stage_result.outcome
        card = declaration.result_card(
            call=call, outcome=tool_outcome, artifact_id=context.artifact_id
        )
        cards.append(card.model_dump(mode="json"))
        references.append(_card_reference(card))
        if business_bindings is not None and tool_outcome.status != "succeeded":
            break
    return _with_cards(outcome, patch=patch, cards=cards, references=references)


def local_tool_call_patch(
    *, declaration: ToolDeclaration, call: ToolCall, artifact_id: str
) -> dict[str, Any]:
    """One free local call run outside the execute loop, in the loop's own patch shape.

    A grounded answer that computes after retrieval publishes its card the way
    an executed call does: the same record, the same reference, the same card.
    """
    if (
        declaration.policy.execution != "local"
        or declaration.policy.confirmation != "never"
    ):
        raise ValueError("Only a free local tool runs outside the execute loop")
    outcome = declaration.invoke_sync(call.arguments)
    card = declaration.result_card(call=call, outcome=outcome, artifact_id=artifact_id)
    return {
        "tool_call_records": [_call_record(call, outcome)],
        "final_response_payload": {"tool_result_cards": [card.model_dump(mode="json")]},
        "artifact_references": [_card_reference(card)],
    }


def _call_record(call: ToolCall, outcome: ToolOutcome) -> dict[str, Any]:
    return {
        "tool_name": call.tool_name,
        "call_id": call.call_id,
        "outcome": outcome.status,
        "tool_outcome": outcome.model_dump(mode="json"),
    }


def _card_reference(card: ToolResultCard) -> dict[str, Any]:
    return ArtifactReference(
        artifact_kind="tool_result",
        artifact_id=card.artifact_id,
        artifact_status=card.artifact_state,
        metadata=card.model_dump(mode="json"),
    ).model_dump(mode="json")


def _with_cards(
    outcome: StageOutcome,
    *,
    patch: dict[str, Any],
    cards: list[dict[str, Any]],
    references: list[dict[str, Any]],
) -> StageResult:
    if cards:
        patch["final_response_payload"] = {
            **patch.get("final_response_payload", {}),
            "tool_result_cards": cards,
        }
    if references:
        patch["artifact_references"] = references
    return StageResult(outcome=outcome, stage_patch=patch)


def _rejected_batch(code: str) -> StageResult:
    return StageResult(
        outcome="execution_failed_terminally",
        stage_patch={
            "tool_calls": [],
            "tool_call_records": [],
            "tool_effects": [],
            "failure_classification": "invalid_tool_call",
            "final_response_payload": {"code": code},
        },
    )
