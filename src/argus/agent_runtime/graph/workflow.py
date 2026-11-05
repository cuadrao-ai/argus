from __future__ import annotations

from copy import deepcopy
from enum import Enum
from typing import TYPE_CHECKING, Any, TypedDict, cast

if TYPE_CHECKING:
    from argus.domain.tool_declaration import ToolCatalog

from argus.agent_runtime.artifacts.lifecycle import (
    RetryLifecycleDecision,
    retry_lifecycle_after_artifact_event,
)
from argus.agent_runtime.capabilities.contract import (
    CapabilityContract,
    build_default_capability_contract,
)
from argus.agent_runtime.confirmation_artifacts import (
    confirmation_artifact_reference,
    confirmation_id_from_payload,
    validate_confirmation_execution_payload,
)
from argus.agent_runtime.stages.clarify import (
    StructuredClarificationGenerator,
    clarify_stage_async,
)
from argus.agent_runtime.stages.confirm import confirm_stage
from argus.agent_runtime.stages.explain import explain_stage_async
from argus.agent_runtime.stages.interpret import (
    StageResult,
    StructuredInterpreter,
    interpret_stage_async,
)
from argus.agent_runtime.stages.next_step import next_step_stage_async
from argus.agent_runtime.stages.tool_execution import execute_tool_calls_async
from argus.agent_runtime.state.models import (
    ArtifactReference,
    RunState,
    StrategySummary,
    TaskSnapshot,
    UserState,
    dedupe_resolution_provenance_items,
)
from argus.agent_runtime.workflow_contract import WorkflowNode
from argus.domain.result_readout_content import (
    READOUT_METADATA_KEYS,
    readout_metadata_from_stage,
)
from langgraph.graph import END, StateGraph


class WorkflowRoute(str, Enum):
    CLARIFY = "clarify"
    CONFIRM = "confirm"
    EXECUTE = "execute"
    EXPLAIN = "explain"
    NEXT_STEP = "next_step"
    END = "end"


class WorkflowStageOutcome(str, Enum):
    NEEDS_CLARIFICATION = "needs_clarification"
    READY_FOR_CONFIRMATION = "ready_for_confirmation"
    AWAIT_USER_REPLY = "await_user_reply"
    AWAIT_APPROVAL = "await_approval"
    APPROVED_FOR_EXECUTION = "approved_for_execution"
    EXECUTION_SUCCEEDED = "execution_succeeded"
    EXECUTION_FAILED_RECOVERABLY = "execution_failed_recoverably"
    EXECUTION_FAILED_TERMINALLY = "execution_failed_terminally"
    READY_TO_RESPOND = "ready_to_respond"
    END_RUN = "end_run"


class WorkflowState(TypedDict, total=False):
    run_state: RunState
    user: UserState
    latest_task_snapshot: TaskSnapshot | None
    selected_thread_metadata: dict[str, Any]
    artifact_references: list[ArtifactReference]
    stage_outcome: WorkflowStageOutcome
    assistant_prompt: str | None
    assistant_response: str | None
    result_readout_content: dict[str, Any] | None
    result_readout_source: str | None
    result_readout_fallback_used: bool | None
    result_readout_failure_mode: str | None
    requested_field: str | None
    optional_parameter_choices: list[str]
    confirmation_payload: dict[str, Any]
    backtest_job: dict[str, Any]
    failure_classification: str | None
    final_response_payload: dict[str, Any]
    latest_failed_action_reference: ArtifactReference | dict[str, Any]
    next_actions: list[str]
    latest_run_id: str | None
    result_run_id: str | None
    result_strategy_id: str | None
    result_conversation_id: str | None
    result_fact_bank: dict[str, Any]
    result_action_request: dict[str, Any]
    clarification: dict[str, Any]
    recovery: dict[str, Any]
    discovery: dict[str, Any]
    discovery_usage: dict[str, Any]
    next_experiments: dict[str, Any]
    next_steps: dict[str, Any]
    answer_text_template: dict[str, Any]
    answer_assumptions: list[dict[str, Any]]
    calculation_offer: dict[str, Any]
    research: dict[str, Any]
    research_job_request: dict[str, Any]
    tool_effects: list[dict[str, Any]]
    business_plan: dict[str, Any]


RUN_STATE_FIELD_NAMES = frozenset(RunState.model_fields)
_TURN_SCOPED_OUTPUT_KEYS = frozenset(
    {
        "assistant_prompt",
        "assistant_response",
        *READOUT_METADATA_KEYS,
        "requested_field",
        "optional_parameter_choices",
        # The launch hand-off between interpret and execute lives one turn;
        # a stale value here is published over the turn's own card (#440).
        "confirmation_payload",
        "backtest_job",
        "failure_classification",
        "final_response_payload",
        "latest_failed_action_reference",
        "next_actions",
        "latest_run_id",
        "result_run_id",
        "result_strategy_id",
        "result_conversation_id",
        "result_fact_bank",
        "result_action_request",
        "clarification",
        "recovery",
        "discovery",
        "discovery_usage",
        "next_experiments",
        "next_steps",
        "answer_text_template",
        "answer_assumptions",
        "calculation_offer",
        "research",
        "research_job_request",
        "tool_effects",
    }
)


class DefaultBacktestTool:
    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        return deepcopy(
            {
                "success": True,
                "payload": {
                    "total_return": 0.14,
                    "benchmark_return": 0.09,
                },
                "error_type": None,
                "error_message": None,
                "retryable": False,
                "capability_context": {},
            }
        )


def build_workflow(
    *,
    contract: CapabilityContract | None = None,
    tool: Any | None = None,
    max_retries: int = 2,
    structured_interpreter: StructuredInterpreter | None = None,
    clarification_generator: StructuredClarificationGenerator | None = None,
    checkpointer: Any | None = None,
    tool_catalog: ToolCatalog | None = None,
    business_runtime: Any | None = None,
):
    active_contract = contract or build_default_capability_contract()
    active_tool = tool or DefaultBacktestTool()

    async def interpret_node(state: WorkflowState) -> WorkflowState:
        if business_runtime is not None:
            return await business_runtime.interpret(state)
        return await _interpret_node_async(
            state,
            structured_interpreter=structured_interpreter,
        )

    async def clarify_node(state: WorkflowState) -> WorkflowState:
        return await _clarify_node_async(
            state,
            contract=active_contract,
            clarification_generator=clarification_generator,
        )

    async def execute_node(state: WorkflowState) -> WorkflowState:
        if business_runtime is not None:
            return await business_runtime.execute(state)
        return await _execute_node_async(
            state,
            tool=active_tool,
            max_retries=max_retries,
            catalog=tool_catalog,
        )

    graph = StateGraph(WorkflowState)
    graph.add_node(WorkflowNode.INTERPRET.value, interpret_node)
    graph.add_node(WorkflowNode.CLARIFY.value, clarify_node)
    graph.add_node(
        WorkflowNode.CONFIRM.value,
        lambda state: _apply_stage_result(
            state,
            confirm_stage(
                state=_run_state(state),
                contract=active_contract,
                language=_user(state).language_preference,
            ),
        ),
    )
    graph.add_node(WorkflowNode.EXECUTE.value, execute_node)
    graph.add_node(WorkflowNode.EXPLAIN.value, _explain_node_async)
    graph.add_node(WorkflowNode.NEXT_STEP.value, _next_step_node_async)

    graph.set_entry_point(WorkflowNode.INTERPRET.value)
    graph.add_conditional_edges(
        WorkflowNode.INTERPRET.value,
        _route_from_stage_outcome,
        {
            WorkflowRoute.CLARIFY.value: WorkflowNode.CLARIFY.value,
            WorkflowRoute.CONFIRM.value: WorkflowNode.CONFIRM.value,
            WorkflowRoute.EXECUTE.value: WorkflowNode.EXECUTE.value,
            WorkflowRoute.END.value: END,
        },
    )
    graph.add_conditional_edges(
        WorkflowNode.CLARIFY.value,
        _route_from_stage_outcome,
        {
            WorkflowRoute.CONFIRM.value: WorkflowNode.CONFIRM.value,
            WorkflowRoute.END.value: END,
        },
    )
    graph.add_conditional_edges(
        WorkflowNode.CONFIRM.value,
        _route_from_stage_outcome,
        {
            WorkflowRoute.CLARIFY.value: WorkflowNode.CLARIFY.value,
            WorkflowRoute.EXECUTE.value: WorkflowNode.EXECUTE.value,
            WorkflowRoute.END.value: END,
        },
    )
    graph.add_conditional_edges(
        WorkflowNode.EXECUTE.value,
        _route_from_stage_outcome,
        {
            WorkflowRoute.CLARIFY.value: WorkflowNode.CLARIFY.value,
            WorkflowRoute.CONFIRM.value: WorkflowNode.CONFIRM.value,
            WorkflowRoute.EXPLAIN.value: WorkflowNode.EXPLAIN.value,
            WorkflowRoute.END.value: END,
        },
    )
    graph.add_conditional_edges(
        WorkflowNode.EXPLAIN.value,
        _route_from_explain_outcome,
        {
            WorkflowRoute.NEXT_STEP.value: WorkflowNode.NEXT_STEP.value,
            WorkflowRoute.END.value: END,
        },
    )
    graph.add_edge(WorkflowNode.NEXT_STEP.value, END)

    return graph.compile(checkpointer=checkpointer)


async def _interpret_node_async(
    state: WorkflowState,
    *,
    structured_interpreter: StructuredInterpreter | None,
) -> WorkflowState:
    return _apply_stage_result(
        state,
        await interpret_stage_async(
            state=_run_state(state),
            user=_user(state),
            latest_task_snapshot=state.get("latest_task_snapshot"),
            selected_thread_metadata=state.get("selected_thread_metadata", {}),
            structured_interpreter=structured_interpreter,
        ),
    )


async def _clarify_node_async(
    state: WorkflowState,
    *,
    contract: CapabilityContract,
    clarification_generator: StructuredClarificationGenerator | None,
) -> WorkflowState:
    return _apply_stage_result(
        state,
        await clarify_stage_async(
            state=_run_state(state),
            contract=contract,
            clarification_generator=clarification_generator,
            language=_user(state).language_preference,
            prefilled_assistant_prompt=state.get("assistant_response"),
        ),
    )


async def _execute_node_async(
    state: WorkflowState,
    *,
    tool: Any,
    max_retries: int,
    catalog: ToolCatalog | None = None,
) -> WorkflowState:
    run_state = _run_state(state)
    launch_payload = state.get("confirmation_payload")
    if _is_launch_request_payload(launch_payload):
        run_state = run_state.model_copy(deep=True)
        run_state.confirmation_payload = dict(launch_payload)
    return _apply_stage_result(
        state,
        await execute_tool_calls_async(
            state=run_state,
            tool=tool,
            max_retries=max_retries,
            language=_user(state).language_preference,
            catalog=catalog,
            user=_user(state),
            latest_task_snapshot=state.get("latest_task_snapshot"),
            selected_thread_metadata=state.get("selected_thread_metadata"),
        ),
    )


async def _explain_node_async(state: WorkflowState) -> WorkflowState:
    language = _user(state).language_preference
    result = await explain_stage_async(state=_run_state(state), language=language)
    result.stage_patch.update(
        readout_metadata_from_stage(result.stage_patch, language=language)
    )
    return _apply_stage_result(state, result)


async def _next_step_node_async(state: WorkflowState) -> WorkflowState:
    return _apply_stage_result(
        state,
        await next_step_stage_async(state=_run_state(state)),
    )


def _apply_stage_result(
    state: WorkflowState,
    result: StageResult,
) -> WorkflowState:
    outcome = WorkflowStageOutcome(result.outcome)
    run_state = _patched_run_state(
        run_state=_run_state(state),
        patch=result.patch,
    )
    cleared_output_keys = set(_TURN_SCOPED_OUTPUT_KEYS)
    effects = state.get("tool_effects")
    current_call_ids = {record.call_id for record in _run_state(state).tool_call_records}
    if (
        "tool_effects" not in result.patch
        and isinstance(effects, list)
        and effects
        and all(effect.get("call_id") in current_call_ids for effect in effects)
    ):
        # Explain and confirm may follow execution. Effects must reach the one
        # publication boundary, but a new RunState cannot replay the prior turn.
        cleared_output_keys.discard("tool_effects")
    if (
        outcome is WorkflowStageOutcome.END_RUN
        and "assistant_response" not in result.patch
        and isinstance(state.get("assistant_response"), str)
    ):
        cleared_output_keys.discard("assistant_response")
        cleared_output_keys.difference_update(READOUT_METADATA_KEYS)
    # The Try next rows and the list that orders them survive the closing no-op
    # stage the same way the response text does; only a stage that patches
    # them may replace them.
    for key in ("next_experiments", "next_steps"):
        if (
            outcome is WorkflowStageOutcome.END_RUN
            and key not in result.patch
            and isinstance(state.get(key), dict)
        ):
            cleared_output_keys.discard(key)
    workflow_state: WorkflowState = {
        **state,
        **{key: None for key in cleared_output_keys},
        "run_state": run_state,
        "stage_outcome": outcome,
    }

    for key, value in result.patch.items():
        if key in RUN_STATE_FIELD_NAMES and not (
            key == "confirmation_payload" and _is_launch_request_payload(value)
        ):
            continue
        workflow_state[key] = value

    artifact_references = _resolve_artifact_references(workflow_state)
    workflow_state["artifact_references"] = artifact_references
    workflow_state["latest_task_snapshot"] = _build_task_snapshot(
        run_state=run_state,
        stage_outcome=outcome,
        prior_task_snapshot=state.get("latest_task_snapshot"),
        artifact_references=artifact_references,
    )
    workflow_state["selected_thread_metadata"] = _build_thread_metadata(
        workflow_state=workflow_state,
        run_state=run_state,
        stage_outcome=outcome,
    )

    return workflow_state


def _patched_run_state(*, run_state: RunState, patch: dict[str, Any]) -> RunState:
    payload = run_state.model_dump(mode="python")
    for key, value in patch.items():
        if key == "confirmation_payload" and _is_launch_request_payload(value):
            continue
        if key in RUN_STATE_FIELD_NAMES:
            payload[key] = value
    return RunState.model_validate(payload)


def _route_from_stage_outcome(state: WorkflowState) -> str:
    outcome = WorkflowStageOutcome(state["stage_outcome"])
    failure_classification = state.get("failure_classification")

    if outcome is WorkflowStageOutcome.NEEDS_CLARIFICATION:
        if failure_classification == "unsupported_capability":
            return WorkflowRoute.END.value
        return WorkflowRoute.CLARIFY.value
    if outcome is WorkflowStageOutcome.READY_FOR_CONFIRMATION:
        return WorkflowRoute.CONFIRM.value
    if outcome is WorkflowStageOutcome.APPROVED_FOR_EXECUTION:
        return WorkflowRoute.EXECUTE.value
    if outcome is WorkflowStageOutcome.EXECUTION_SUCCEEDED:
        return WorkflowRoute.EXPLAIN.value
    return WorkflowRoute.END.value


def _route_from_explain_outcome(state: WorkflowState) -> str:
    outcome = WorkflowStageOutcome(state["stage_outcome"])
    if outcome is WorkflowStageOutcome.READY_TO_RESPOND:
        return WorkflowRoute.NEXT_STEP.value
    return WorkflowRoute.END.value


def _run_state(state: WorkflowState) -> RunState:
    return cast(RunState, state["run_state"])


def _user(state: WorkflowState) -> UserState:
    return cast(UserState, state["user"])


def _build_task_snapshot(
    *,
    run_state: RunState,
    stage_outcome: Any,
    prior_task_snapshot: TaskSnapshot | None,
    artifact_references: list[ArtifactReference],
) -> TaskSnapshot:
    stage_outcome_value = getattr(stage_outcome, "value", stage_outcome)
    completed_outcomes = {"execution_succeeded", "ready_to_respond", "end_run"}
    latest_backtest_reference = _latest_artifact_reference(
        artifact_references=artifact_references,
        artifact_kind="backtest_result",
    )
    latest_collection_reference = _latest_artifact_reference(
        artifact_references=artifact_references,
        artifact_kind="collection_action",
    )
    latest_failed_action_reference = _latest_artifact_reference(
        artifact_references=artifact_references,
        artifact_kind="failed_action",
    )
    latest_failed_action_reference = _current_failed_action_reference(
        latest_failed_action_reference=latest_failed_action_reference,
        prior_task_snapshot=prior_task_snapshot,
        artifact_references=artifact_references,
    )
    active_confirmation_reference = _active_confirmation_reference(
        run_state=run_state,
        artifact_references=artifact_references,
        prior_task_snapshot=prior_task_snapshot,
        stage_outcome_value=str(stage_outcome_value),
    )
    preserve_pending_strategy = _should_preserve_pending_strategy(
        run_state=run_state,
        stage_outcome_value=stage_outcome_value,
        prior_task_snapshot=prior_task_snapshot,
        latest_backtest_reference=latest_backtest_reference,
        latest_collection_reference=latest_collection_reference,
    )
    capture_current_pending_strategy = _should_capture_current_pending_strategy(
        run_state=run_state,
        stage_outcome_value=stage_outcome_value,
    )
    completed = (
        stage_outcome_value in completed_outcomes
        and not preserve_pending_strategy
        and not capture_current_pending_strategy
    )
    if capture_current_pending_strategy:
        pending_strategy_summary = run_state.candidate_strategy_draft
    elif preserve_pending_strategy and prior_task_snapshot is not None:
        pending_strategy_summary = prior_task_snapshot.pending_strategy_summary
    elif stage_outcome_value in {"await_user_reply", "await_approval"}:
        pending_strategy_summary = run_state.candidate_strategy_draft
    elif (
        prior_task_snapshot is not None and stage_outcome_value not in completed_outcomes
    ):
        pending_strategy_summary = prior_task_snapshot.pending_strategy_summary
    else:
        pending_strategy_summary = None
    prior_confirmed_strategy = (
        prior_task_snapshot.confirmed_strategy_summary
        if prior_task_snapshot is not None
        else None
    )
    return TaskSnapshot(
        latest_task_type=run_state.intent,
        completed=completed,
        pending_strategy_summary=pending_strategy_summary,
        confirmed_strategy_summary=(
            run_state.candidate_strategy_draft
            if completed
            and _strategy_summary_has_content(run_state.candidate_strategy_draft)
            else prior_confirmed_strategy
        ),
        latest_backtest_result_reference=(
            latest_backtest_reference
            or (
                prior_task_snapshot.latest_backtest_result_reference
                if prior_task_snapshot is not None
                else None
            )
        ),
        latest_collection_action_reference=(
            latest_collection_reference
            or (
                prior_task_snapshot.latest_collection_action_reference
                if prior_task_snapshot is not None
                else None
            )
        ),
        latest_failed_action_reference=latest_failed_action_reference,
        active_draft_reference=(
            prior_task_snapshot.active_draft_reference
            if prior_task_snapshot is not None
            else None
        ),
        active_confirmation_reference=active_confirmation_reference,
        saved_strategy_reference=(
            prior_task_snapshot.saved_strategy_reference
            if prior_task_snapshot is not None
            else None
        ),
        artifact_references=(
            artifact_references
            or (
                prior_task_snapshot.artifact_references
                if prior_task_snapshot is not None
                else []
            )
        ),
        last_unresolved_follow_up=(
            run_state.user_goal_summary
            if stage_outcome_value in {"await_user_reply", "await_approval"}
            or capture_current_pending_strategy
            else None
        ),
        resolution_provenance=dedupe_resolution_provenance_items(
            run_state.resolution_provenance
            or (
                prior_task_snapshot.resolution_provenance
                if prior_task_snapshot is not None
                else []
            )
        ),
    )


def _should_preserve_pending_strategy(
    *,
    run_state: RunState,
    stage_outcome_value: str,
    prior_task_snapshot: TaskSnapshot | None,
    latest_backtest_reference: ArtifactReference | None,
    latest_collection_reference: ArtifactReference | None,
) -> bool:
    if stage_outcome_value != "ready_to_respond":
        return False
    if (
        prior_task_snapshot is None
        or prior_task_snapshot.pending_strategy_summary is None
    ):
        return False
    if _has_new_artifact_reference(
        latest_backtest_reference,
        prior_task_snapshot.latest_backtest_result_reference,
    ) or _has_new_artifact_reference(
        latest_collection_reference,
        prior_task_snapshot.latest_collection_action_reference,
    ):
        return False
    action = run_state.structured_action
    return action is None or action.type != "cancel_confirmation"


def _should_capture_current_pending_strategy(
    *,
    run_state: RunState,
    stage_outcome_value: str,
) -> bool:
    if stage_outcome_value != "ready_to_respond":
        return False
    if not _strategy_summary_has_content(run_state.candidate_strategy_draft):
        return False
    response_intent = run_state.response_intent
    if response_intent is None:
        return False
    return bool(response_intent.semantic_needs or response_intent.requested_fields)


def _has_new_artifact_reference(
    current: ArtifactReference | None,
    prior: ArtifactReference | None,
) -> bool:
    if current is None:
        return False
    if prior is None:
        return True
    return (
        current.artifact_kind,
        current.artifact_id,
    ) != (
        prior.artifact_kind,
        prior.artifact_id,
    )


def _current_failed_action_reference(
    *,
    latest_failed_action_reference: ArtifactReference | None,
    prior_task_snapshot: TaskSnapshot | None,
    artifact_references: list[ArtifactReference],
) -> ArtifactReference | None:
    latest_failed_index = _latest_artifact_index(
        artifact_references=artifact_references,
        artifact_kind="failed_action",
    )
    prior_failed = (
        prior_task_snapshot.latest_failed_action_reference
        if prior_task_snapshot is not None
        else None
    )
    current_failed = latest_failed_action_reference or prior_failed
    if current_failed is None:
        return None
    subsequent = artifact_references[
        0 if latest_failed_index is None else latest_failed_index + 1 :
    ]
    for reference in subsequent:
        decision = retry_lifecycle_after_artifact_event(
            retry_artifact_id=current_failed.artifact_id,
            latest_failed_artifact_id=current_failed.artifact_id,
            new_artifact_kind=reference.artifact_kind,
            new_tool_result=reference.metadata,
        )
        if decision is not RetryLifecycleDecision.ACTIVE:
            return None
    return current_failed


def _latest_artifact_index(
    *,
    artifact_references: list[ArtifactReference],
    artifact_kind: str,
) -> int | None:
    for index in range(len(artifact_references) - 1, -1, -1):
        if artifact_references[index].artifact_kind == artifact_kind:
            return index
    return None


def _strategy_summary_has_content(strategy: StrategySummary) -> bool:
    return any(
        value not in (None, "", [], {})
        for value in strategy.model_dump(mode="python").values()
    )


def _build_thread_metadata(
    *,
    workflow_state: WorkflowState,
    run_state: RunState,
    stage_outcome: Any,
) -> dict[str, Any]:
    stage_outcome_value = getattr(stage_outcome, "value", stage_outcome)
    metadata: dict[str, Any] = {
        "latest_task_type": run_state.intent,
        "last_stage_outcome": stage_outcome_value,
    }
    offered = workflow_state.get("next_experiments")
    if isinstance(offered, dict):
        kinds = [
            str(row.get("kind"))
            for row in offered.get("rows") or []
            if isinstance(row, dict) and row.get("kind")
        ]
        if kinds:
            metadata["next_experiments_offered_kinds"] = kinds
            sends = {
                str(row.get("kind")): str(row.get("send_text"))
                for row in offered.get("rows") or []
                if isinstance(row, dict) and row.get("kind") and row.get("send_text")
            }
            if sends:
                metadata["next_experiments_offered_texts"] = sends
    if "next_experiments_offered_kinds" not in metadata:
        # A turn without a new result keeps the previous result's offer on
        # record; only a fresh offer replaces it (spec §4.3 non-repetition).
        prior_offer_metadata = workflow_state.get("selected_thread_metadata")
        if isinstance(prior_offer_metadata, dict):
            prior_kinds = prior_offer_metadata.get("next_experiments_offered_kinds")
            if isinstance(prior_kinds, list) and prior_kinds:
                metadata["next_experiments_offered_kinds"] = list(prior_kinds)
                prior_sends = prior_offer_metadata.get("next_experiments_offered_texts")
                if isinstance(prior_sends, dict) and prior_sends:
                    metadata["next_experiments_offered_texts"] = dict(prior_sends)
    requested_field = workflow_state.get("requested_field")
    if requested_field in (None, ""):
        requested_field = run_state.requested_field
    if (
        requested_field in (None, "")
        and run_state.response_intent is not None
        and run_state.response_intent.requested_fields
    ):
        requested_field = run_state.response_intent.requested_fields[0]
    if requested_field in (None, ""):
        prior_metadata = workflow_state.get("selected_thread_metadata")
        snapshot = workflow_state.get("latest_task_snapshot")
        if (
            stage_outcome_value == "ready_to_respond"
            and isinstance(prior_metadata, dict)
            and isinstance(snapshot, TaskSnapshot)
            and snapshot.pending_strategy_summary is not None
        ):
            requested_field = prior_metadata.get("requested_field")
    if isinstance(requested_field, str) and requested_field:
        metadata["requested_field"] = requested_field
    prior_metadata = workflow_state.get("selected_thread_metadata")
    if (
        stage_outcome_value
        in {
            "needs_clarification",
            "ready_for_confirmation",
            "await_user_reply",
            "await_approval",
        }
        and run_state.task_relation in {"continue", "refine"}
        and isinstance(prior_metadata, dict)
    ):
        for key in ("source_result_run_id", "strategy_path_id"):
            value = prior_metadata.get(key)
            if isinstance(value, str) and value:
                metadata[key] = value
    if run_state.response_intent is not None:
        metadata["response_intent"] = run_state.response_intent.model_dump(mode="python")
    clarification = workflow_state.get("clarification")
    if isinstance(clarification, dict):
        metadata["clarification"] = dict(clarification)
    recovery = workflow_state.get("recovery")
    if isinstance(recovery, dict):
        metadata["recovery"] = dict(recovery)
    pending_resolution = _pending_resolution_candidate(workflow_state=workflow_state)
    if pending_resolution is not None:
        metadata["pending_resolution"] = pending_resolution
    return metadata


def _pending_resolution_candidate(
    *,
    workflow_state: WorkflowState,
) -> dict[str, Any] | None:
    ambiguous_fields = workflow_state.get("ambiguous_fields")
    if not isinstance(ambiguous_fields, list):
        return None
    for field in ambiguous_fields:
        if not isinstance(field, dict):
            continue
        field_name = str(field.get("field_name") or "")
        if field_name.split("[", 1)[0] != "asset_universe":
            continue
        candidate = field.get("candidate_normalized_value")
        if not isinstance(candidate, str) or not candidate.strip():
            continue
        pending_resolution: dict[str, Any] = {
            "field": "asset_universe",
            "raw_value": str(field.get("raw_value") or "").strip(),
            "candidate_normalized_value": candidate.strip(),
        }
        strategy = _run_state(workflow_state).candidate_strategy_draft
        if strategy.asset_class:
            pending_resolution["asset_class"] = strategy.asset_class
        return pending_resolution
    return None


def _resolve_artifact_references(state: WorkflowState) -> list[ArtifactReference]:
    raw_references = state.get("artifact_references", [])
    references: list[ArtifactReference] = []
    for reference in raw_references:
        references.append(ArtifactReference.model_validate(reference))
    latest_failed = state.get("latest_failed_action_reference")
    if latest_failed is not None:
        references.append(ArtifactReference.model_validate(latest_failed))
    return _dedupe_artifact_references(references)


def _active_confirmation_reference(
    *,
    run_state: RunState,
    artifact_references: list[ArtifactReference],
    prior_task_snapshot: TaskSnapshot | None,
    stage_outcome_value: str,
) -> ArtifactReference | None:
    if stage_outcome_value == "await_approval":
        existing = _latest_artifact_reference(
            artifact_references=artifact_references,
            artifact_kind="confirmation",
        )
        if existing is not None:
            return existing
        payload = _confirmation_payload_dict(run_state.confirmation_payload)
        if payload:
            confirmation_id = confirmation_id_from_payload(payload)
            return confirmation_artifact_reference(
                confirmation_id=confirmation_id,
                confirmation_payload=payload,
            )
    if (
        stage_outcome_value == "ready_to_respond"
        and prior_task_snapshot is not None
        and prior_task_snapshot.pending_strategy_summary is not None
        and prior_task_snapshot.active_confirmation_reference is not None
    ):
        action = run_state.structured_action
        if action is None or action.type != "cancel_confirmation":
            return _valid_active_confirmation_reference(
                prior_task_snapshot.active_confirmation_reference
            )
    if stage_outcome_value in {
        "approved_for_execution",
        "execution_succeeded",
        "execution_failed_recoverably",
        "execution_failed_terminally",
        "ready_to_respond",
        "end_run",
    }:
        return None
    return (
        _valid_active_confirmation_reference(
            prior_task_snapshot.active_confirmation_reference
        )
        if prior_task_snapshot is not None
        else None
    )


def _confirmation_payload_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="python")
        return dict(dumped) if isinstance(dumped, dict) else {}
    return {}


def _valid_active_confirmation_reference(
    reference: ArtifactReference | None,
) -> ArtifactReference | None:
    if reference is None:
        return None
    payload = _confirmation_payload_dict(reference.metadata.get("confirmation_payload"))
    if not payload:
        return None
    if not validate_confirmation_execution_payload(payload).executable:
        return None
    return reference


def _dedupe_artifact_references(
    references: list[ArtifactReference],
) -> list[ArtifactReference]:
    seen: set[tuple[str, str]] = set()
    deduped: list[ArtifactReference] = []
    for reference in references:
        key = (reference.artifact_kind, reference.artifact_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(reference)
    return deduped


def _is_launch_request_payload(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    required_fields = {
        "strategy_type",
        "symbol",
        "timeframe",
        "date_range",
        "sizing_mode",
        "benchmark_symbol",
    }
    return required_fields.issubset(value)


def _latest_artifact_reference(
    *,
    artifact_references: list[ArtifactReference],
    artifact_kind: str,
) -> ArtifactReference | None:
    for reference in reversed(artifact_references):
        if reference.artifact_kind == artifact_kind:
            return reference.model_copy(deep=True)
    return None
