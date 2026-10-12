from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from argus.agent_runtime.capabilities.contract import build_default_capability_contract
from argus.agent_runtime.llm_clarifier import OpenRouterClarificationGenerator
from argus.agent_runtime.llm_interpreter import OpenRouterStructuredInterpreter
from argus.agent_runtime.stages.clarify import clarify_stage
from argus.agent_runtime.stages.confirm import confirm_stage
from argus.agent_runtime.stages.interpret import interpret_stage
from argus.agent_runtime.state.models import (
    ArtifactReference,
    RunState,
    StrategySummary,
    TaskSnapshot,
    UserState,
)
from argus.llm.openrouter import (
    begin_openrouter_route_receipt_capture,
    end_openrouter_route_receipt_capture,
    invoke_openrouter_json_schema,
)
from pydantic import BaseModel, Field

from tests.evals.measurement_assertions import (
    _compare,
    _compare_date_range,
    _compare_subset,
    _date_range_expectation,
)
from tests.evals.measurement_eval_scorecard import (
    FIXTURE_DIR,
    measurement_fixture_documents,
)
from tests.evals.measurement_outcome import (
    compare_offered,
    offered_to_user,
    rendered_beside_reply,
)
from tests.evals.measurement_prose import (
    PROSE_JUDGE_RUBRIC,
    PROSE_JUDGE_RUBRIC_VERSION,
    composer_unavailability,
    retain_prose_context,
    unavailable_prose_result,
)

LOCKED_EVAL_CATEGORIES = {
    "messy_english",
    "messy_spanish",
    "ui_user_language_mismatch",
    "action_chip_semantics",
    "capability_honesty",
    "backtest_metric_correctness",
    "graceful_recovery",
    "asset_discovery_routing",
    "dca_capital_semantics",
    "ordinary_conversation",
}


@dataclass(frozen=True)
class ExpectedFail:
    issue: str
    reason: str
    allowed_failures: tuple[str, ...]


@dataclass(frozen=True)
class EvalAction:
    type: str
    label: str | None
    presentation: str | None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TypedExpectations:
    intent: str | tuple[str, ...]
    capability_verdict: str
    assets: tuple[str, ...] = ()
    asset_class: str | None = None
    requested_strategy_template: str | None = None
    strategy_type: str | None = None
    entry_rule: dict[str, Any] | None = None
    exit_rule: dict[str, Any] | None = None
    rule_spec: dict[str, Any] | None = None
    date_range: dict[str, str] | str | None = None
    requested_date_range: dict[str, str] | str | None = None
    effective_date_range: dict[str, str] | str | None = None
    adjustment_reason: str | None = None
    benchmark_symbol: str | None = None
    capital_amount: float | None = None
    # A recurring plan's two money roles and its period are peers with their
    # own names; capital_amount alone cannot see a role swap.
    starting_capital: float | None = None
    recurring_contribution: float | None = None
    contribution_period: str | None = None
    launch_validation_code: str | None = None
    missing_required_fields: tuple[str, ...] = ()
    fee_rate: float | None = None
    slippage: float | None = None
    cost_provenance: dict[str, str] | None = None
    launch_execution_realism: dict[str, Any] | None = None
    stage_outcomes: tuple[str, ...] = ()
    requested_field: str | None = None
    clarification: dict[str, Any] | None = None
    semantic_turn_act: str | None = None
    asset_discovery: dict[str, Any] | None = None
    # What reached the user. Routing fields say a turn was understood; this
    # says the turn went somewhere the user can act on, which is the only
    # thing a green case is supposed to promise.
    offered: dict[str, Any] | None = None
    # A grounded turn's typed sidecar: whether the answer published (no
    # degraded code) and, as `rows`, the least number of typed figures it
    # carried. A research turn that withheld its answer still reaches
    # ready_to_respond, so nothing above can see the refusal this pins.
    research: dict[str, Any] | None = None


@dataclass(frozen=True)
class EvalCase:
    id: str
    category: str
    prompt: str
    user_language: str
    ui_language: str
    expected: TypedExpectations
    action: EvalAction | None = None
    followup_prompt: str | None = None
    snapshot: TaskSnapshot | None = None
    confirmation_payload: dict[str, Any] | None = None
    recent_thread_history: tuple[dict[str, Any], ...] = ()
    thread_metadata: dict[str, Any] = field(default_factory=dict)
    degraded_mode: dict[str, Any] = field(default_factory=dict)
    expected_fail: ExpectedFail | None = None
    prose_judge_criteria: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


class ProseJudgeResponse(BaseModel):
    passed: bool = Field(alias="pass")
    failed_criteria: list[str] = Field(default_factory=list)
    notes: str = ""


def load_eval_cases(path: Path = FIXTURE_DIR) -> list[EvalCase]:
    cases: list[EvalCase] = []
    for fixture_path, payload in measurement_fixture_documents(path):
        category = str(payload["category"])
        if category not in LOCKED_EVAL_CATEGORIES:
            raise ValueError(f"unknown eval category: {category}")
        if fixture_path.stem != category:
            raise ValueError(f"fixture filename must match category: {fixture_path}")
        for raw_case in payload["cases"]:
            cases.append(_case_from_raw(category=category, raw_case=raw_case))
    return cases


def run_eval_case(
    case: EvalCase,
    *,
    run_prose_judge: bool = True,
) -> dict[str, Any]:
    contract = build_default_capability_contract()
    state = RunState.new(
        current_user_message=case.prompt,
        recent_thread_history=[dict(turn) for turn in case.recent_thread_history],
        action_context=_action_payload(case.action),
    )
    if case.confirmation_payload is not None:
        state.confirmation_payload = case.confirmation_payload

    user = UserState(
        user_id="argus-eval",
        language_preference=case.user_language,
        expertise_level="beginner",
    )
    interpreter = OpenRouterStructuredInterpreter(contract=contract)
    clarifier = (
        None
        if case.degraded_mode.get("clarifier") == "offline"
        else OpenRouterClarificationGenerator()
    )
    route_token = begin_openrouter_route_receipt_capture()
    confirm_result = None
    clarify_result = None
    followup_result = None
    try:
        interpret_result = interpret_stage(
            state=state,
            user=user,
            latest_task_snapshot=case.snapshot,
            selected_thread_metadata={
                "ui_language": case.ui_language,
                "last_stage_outcome": "await_approval",
                **case.thread_metadata,
            },
            structured_interpreter=interpreter,
        )
        if interpret_result.outcome == "ready_for_confirmation":
            confirm_state = _state_for_confirmation(
                case=case,
                interpret_patch=interpret_result.patch,
            )
            confirm_result = confirm_stage(
                state=confirm_state,
                contract=contract,
                language=case.user_language,
            )
            if confirm_result.outcome == "needs_clarification":
                clarify_result = clarify_stage(
                    state=_state_from_interpret_patch(
                        case=case,
                        interpret_patch={
                            **interpret_result.patch,
                            **confirm_result.patch,
                        },
                    ),
                    contract=contract,
                    clarification_generator=clarifier,
                    language=case.user_language,
                )
        elif interpret_result.outcome == "needs_clarification":
            clarify_state = _state_from_interpret_patch(
                case=case,
                interpret_patch=interpret_result.patch,
            )
            clarify_result = clarify_stage(
                state=clarify_state,
                contract=contract,
                clarification_generator=clarifier,
                language=case.user_language,
                prefilled_assistant_prompt=(
                    interpret_result.patch.get("assistant_response")
                    or interpret_result.patch.get("assistant_prompt")
                ),
            )
        followup_result = _run_followup_turn_if_needed(
            case=case,
            user=user,
            contract=contract,
            interpret_result=interpret_result,
            clarify_result=clarify_result,
            clarification_generator=clarifier,
        )
    finally:
        route_receipts = [
            receipt.as_dict()
            for receipt in end_openrouter_route_receipt_capture(route_token)
        ]

    typed_outcome = _typed_outcome(
        case=case,
        interpret_result=interpret_result,
        confirm_result=confirm_result,
        clarify_result=clarify_result,
        followup_result=followup_result,
    )
    failed_checks = typed_expectation_failures(case=case, outcome=typed_outcome)
    infrastructure_errors = composer_unavailability(route_receipts)
    judge_result = None
    if run_prose_judge and case.prose_judge_criteria:
        judged_final_patch = _final_patch(
            interpret_result=interpret_result,
            confirm_result=confirm_result,
            clarify_result=clarify_result,
        )
        assistant_text = _assistant_text(judged_final_patch)
        rendered_surface = rendered_beside_reply(
            final_patch=judged_final_patch,
            interpret_patch=interpret_result.patch,
        )
        if infrastructure_errors:
            judge_result = unavailable_prose_result(
                "runtime composer did not return prose"
            )
        elif not assistant_text.strip():
            judge_result = _missing_prose_judge_result()
            failed_checks.append("prose_judge:missing_assistant_text")
        else:
            judge_route_token = begin_openrouter_route_receipt_capture()
            try:
                judge_result = judge_prose_quality(
                    case=case,
                    assistant_text=assistant_text,
                    rendered_beside_reply=rendered_surface,
                )
            finally:
                route_receipts.extend(
                    receipt.as_dict()
                    for receipt in end_openrouter_route_receipt_capture(judge_route_token)
                )
            if judge_result.get("status") == "unavailable":
                infrastructure_errors.append(
                    {"component": "prose_judge", "code": "no_structured_result"}
                )
            elif not judge_result["pass"]:
                failed_checks.extend(
                    f"prose_judge:{criterion}"
                    for criterion in judge_result["failed_criteria"]
                )
                if not judge_result["failed_criteria"]:
                    failed_checks.append("prose_judge:failed_without_criteria")
        retain_prose_context(
            judge_result,
            criteria=case.prose_judge_criteria,
            text=assistant_text,
            rendered_surface=rendered_surface,
        )

    status = _result_status(failed_checks, expected_fail=case.expected_fail)
    if infrastructure_errors:
        status = "failed" if failed_checks else "infrastructure_error"
    return {
        "id": case.id,
        "category": case.category,
        "status": status,
        "failed_checks": failed_checks,
        "expected_fail": (
            None
            if case.expected_fail is None
            else {
                "issue": case.expected_fail.issue,
                "reason": case.expected_fail.reason,
                "allowed_failures": list(case.expected_fail.allowed_failures),
            }
        ),
        "typed_outcome": typed_outcome,
        "prose_judge": judge_result,
        "infrastructure_errors": infrastructure_errors,
        "route_receipts": route_receipts,
    }


def typed_expectation_failures(
    *,
    case: EvalCase,
    outcome: dict[str, Any],
) -> list[str]:
    expected = case.expected
    failures: list[str] = []
    _compare_intent(expected.intent, outcome.get("intent"), failures)
    _compare(
        "capability_verdict",
        expected.capability_verdict,
        outcome.get("capability_verdict"),
        failures,
    )
    if expected.assets:
        _compare("assets", list(expected.assets), outcome.get("assets"), failures)
    _compare("asset_class", expected.asset_class, outcome.get("asset_class"), failures)
    _compare(
        "requested_strategy_template",
        expected.requested_strategy_template,
        outcome.get("requested_strategy_template"),
        failures,
    )
    _compare(
        "strategy_type",
        expected.strategy_type,
        outcome.get("strategy_type"),
        failures,
    )
    _compare("entry_rule", expected.entry_rule, outcome.get("entry_rule"), failures)
    _compare("exit_rule", expected.exit_rule, outcome.get("exit_rule"), failures)
    _compare("rule_spec", expected.rule_spec, outcome.get("rule_spec"), failures)
    if expected.date_range is not None:
        _compare_date_range(
            "date_range",
            expected.date_range,
            outcome.get("date_range"),
            failures,
        )
    if expected.requested_date_range is not None:
        _compare_date_range(
            "requested_date_range",
            expected.requested_date_range,
            outcome.get("requested_date_range"),
            failures,
        )
    if expected.effective_date_range is not None:
        _compare_date_range(
            "effective_date_range",
            expected.effective_date_range,
            outcome.get("effective_date_range"),
            failures,
        )
    _compare(
        "adjustment_reason",
        expected.adjustment_reason,
        outcome.get("adjustment_reason"),
        failures,
    )
    _compare(
        "benchmark_symbol",
        expected.benchmark_symbol,
        outcome.get("benchmark_symbol"),
        failures,
    )
    _compare(
        "capital_amount",
        expected.capital_amount,
        outcome.get("capital_amount"),
        failures,
    )
    _compare(
        "starting_capital",
        expected.starting_capital,
        outcome.get("starting_capital"),
        failures,
    )
    _compare(
        "recurring_contribution",
        expected.recurring_contribution,
        outcome.get("recurring_contribution"),
        failures,
    )
    _compare(
        "contribution_period",
        expected.contribution_period,
        outcome.get("contribution_period"),
        failures,
    )
    _compare(
        "launch_validation_code",
        expected.launch_validation_code,
        outcome.get("launch_validation_code"),
        failures,
    )
    if expected.missing_required_fields:
        _compare(
            "missing_required_fields",
            list(expected.missing_required_fields),
            outcome.get("missing_required_fields"),
            failures,
        )
    _compare("fee_rate", expected.fee_rate, outcome.get("fee_rate"), failures)
    _compare("slippage", expected.slippage, outcome.get("slippage"), failures)
    if expected.cost_provenance is not None:
        _compare_subset(
            "cost_provenance",
            expected.cost_provenance,
            outcome.get("cost_provenance"),
            failures,
        )
    if expected.launch_execution_realism is not None:
        _compare_subset(
            "launch_execution_realism",
            expected.launch_execution_realism,
            outcome.get("launch_execution_realism"),
            failures,
        )
    if expected.stage_outcomes:
        _compare(
            "stage_outcomes",
            list(expected.stage_outcomes),
            outcome.get("stage_outcomes"),
            failures,
        )
    _compare(
        "requested_field",
        expected.requested_field,
        outcome.get("requested_field"),
        failures,
    )
    if expected.clarification is not None:
        _compare_subset(
            "clarification",
            expected.clarification,
            outcome.get("clarification"),
            failures,
        )
    _compare(
        "semantic_turn_act",
        expected.semantic_turn_act,
        outcome.get("semantic_turn_act"),
        failures,
    )
    if expected.asset_discovery is not None:
        _compare_asset_discovery(
            expected.asset_discovery,
            outcome.get("asset_discovery"),
            failures,
        )
    if expected.offered is not None:
        compare_offered(
            expected.offered,
            outcome.get("offered"),
            failures,
            expected_fields=vars(expected),
        )
    if expected.research is not None:
        _compare_research(expected.research, outcome.get("research"), failures)
    return failures


def blocking_eval_results(
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return result states that must fail a sanctioned live evaluation gate."""
    return [
        result
        for result in results
        if result.get("status") in {"failed", "unexpected_pass", "infrastructure_error"}
        or result.get("infrastructure_errors")
    ]


def expected_fail_issue_for_result(result: dict[str, Any]) -> str | None:
    """Return the exact expected-fail owner from a serialized eval result."""
    expected_fail = result.get("expected_fail")
    if not isinstance(expected_fail, dict):
        return None
    issue = expected_fail.get("issue")
    return issue if isinstance(issue, str) and issue else None


def judge_prose_quality(
    *,
    case: EvalCase,
    assistant_text: str,
    rendered_beside_reply: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        response = asyncio.run(
            _judge_prose_quality_async(
                case=case,
                assistant_text=assistant_text,
                rendered_beside_reply=rendered_beside_reply or {},
            )
        )
    except Exception as exc:
        # Judge transport/schema failures make this measurement unavailable;
        # retain the receipts in run_eval_case and fail the gate, not the prose.
        return unavailable_prose_result(f"prose judge error: {type(exc).__name__}")
    if response is None:
        return unavailable_prose_result("prose judge did not return a structured result")
    return {
        "pass": response.passed,
        "failed_criteria": response.failed_criteria,
        "notes": response.notes,
        "rubric_version": PROSE_JUDGE_RUBRIC_VERSION,
    }


def _missing_prose_judge_result() -> dict[str, Any]:
    return {
        "pass": False,
        "failed_criteria": ["missing_assistant_text"],
        "notes": "case requested prose judging but produced no assistant text",
        "rubric_version": PROSE_JUDGE_RUBRIC_VERSION,
    }


def _run_followup_turn_if_needed(
    *,
    case: EvalCase,
    user: UserState,
    contract: Any,
    interpret_result: Any,
    clarify_result: Any | None,
    clarification_generator: Any,
) -> dict[str, Any] | None:
    if not case.followup_prompt:
        return None
    if clarify_result is None:
        return {"skipped_reason": "initial_turn_did_not_clarify"}

    final_clarify_patch = {**interpret_result.patch, **clarify_result.patch}
    assistant_text = _assistant_text(final_clarify_patch)
    state = RunState.new(
        current_user_message=case.followup_prompt,
        recent_thread_history=(
            [{"role": "assistant", "content": assistant_text}] if assistant_text else []
        ),
    )
    followup_interpret = interpret_stage(
        state=state,
        user=user,
        latest_task_snapshot=case.snapshot
        or _followup_snapshot(case, final_clarify_patch, clarify_result.outcome),
        selected_thread_metadata=_followup_thread_metadata(
            final_clarify_patch,
            last_stage_outcome=str(clarify_result.outcome),
        ),
        structured_interpreter=OpenRouterStructuredInterpreter(contract=contract),
    )
    followup_confirm = None
    followup_clarify = None
    if followup_interpret.outcome == "ready_for_confirmation":
        followup_confirm = confirm_stage(
            state=_state_for_followup_confirmation(
                prompt=case.followup_prompt,
                interpret_patch=followup_interpret.patch,
            ),
            contract=contract,
            language=case.user_language,
        )
        if followup_confirm.outcome == "needs_clarification":
            followup_clarify = clarify_stage(
                state=_state_for_followup_clarification(
                    prompt=case.followup_prompt,
                    interpret_patch={
                        **followup_interpret.patch,
                        **followup_confirm.patch,
                    },
                ),
                contract=contract,
                clarification_generator=clarification_generator,
                language=case.user_language,
            )
    elif followup_interpret.outcome == "needs_clarification":
        followup_clarify = clarify_stage(
            state=_state_for_followup_clarification(
                prompt=case.followup_prompt,
                interpret_patch=followup_interpret.patch,
            ),
            contract=contract,
            clarification_generator=clarification_generator,
            language=case.user_language,
            prefilled_assistant_prompt=(
                followup_interpret.patch.get("assistant_response")
                or followup_interpret.patch.get("assistant_prompt")
            ),
        )
    return {
        "interpret_result": followup_interpret,
        "confirm_result": followup_confirm,
        "clarify_result": followup_clarify,
    }


def _followup_snapshot(case: EvalCase, patch: dict[str, Any], outcome: Any):
    """The setup the first turn left pending, built by the workflow's own owner."""
    from argus.agent_runtime.graph.workflow import _build_task_snapshot

    state = _state_from_interpret_patch(case=case, interpret_patch=patch)
    state.intent = patch.get("intent")
    state.user_goal_summary = patch.get("user_goal_summary")
    return _build_task_snapshot(
        run_state=state,
        stage_outcome=outcome,
        prior_task_snapshot=None,
        artifact_references=[],
    )


def _followup_thread_metadata(
    patch: dict[str, Any],
    *,
    last_stage_outcome: str,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {"last_stage_outcome": last_stage_outcome}
    for key in (
        "requested_field",
        "missing_required_fields",
        "response_intent",
        "clarification",
    ):
        value = patch.get(key)
        if value not in (None, "", [], {}):
            metadata[key] = value
    return metadata


def _state_for_followup_clarification(
    *,
    prompt: str,
    interpret_patch: dict[str, Any],
) -> RunState:
    state = _state_for_followup_confirmation(
        prompt=prompt,
        interpret_patch=interpret_patch,
    )
    state.missing_required_fields = list(
        interpret_patch.get("missing_required_fields") or []
    )
    state.requested_field = interpret_patch.get("requested_field")
    if "response_intent" in interpret_patch:
        state.response_intent = interpret_patch["response_intent"]
    return state


def _state_for_followup_confirmation(
    *,
    prompt: str,
    interpret_patch: dict[str, Any],
) -> RunState:
    state = RunState.new(current_user_message=prompt, recent_thread_history=[])
    if "candidate_strategy_draft" in interpret_patch:
        state.candidate_strategy_draft = StrategySummary.model_validate(
            interpret_patch["candidate_strategy_draft"]
        )
    if "optional_parameter_status" in interpret_patch:
        state.optional_parameter_status = dict(
            interpret_patch["optional_parameter_status"]
        )
    return state


async def _judge_prose_quality_async(
    *,
    case: EvalCase,
    assistant_text: str,
    rendered_beside_reply: dict[str, Any],
) -> ProseJudgeResponse | None:
    payload = {
        "case_id": case.id,
        "category": case.category,
        "user_language": case.user_language,
        "ui_language": case.ui_language,
        "prompt": case.prompt,
        "criteria": list(case.prose_judge_criteria),
        "assistant_text": assistant_text,
        "rendered_beside_reply": rendered_beside_reply,
    }
    result = await invoke_openrouter_json_schema(
        task="chat_composer",
        messages=[
            {"role": "system", "content": PROSE_JUDGE_RUBRIC},
            {"role": "user", "content": json.dumps(payload, sort_keys=True)},
        ],
        schema_model=ProseJudgeResponse,
        schema_name="ArgusProseJudgeResponse",
        model_name=os.getenv("ARGUS_EVAL_JUDGE_MODEL") or None,
    )
    return result if isinstance(result, ProseJudgeResponse) else None


def _case_from_raw(*, category: str, raw_case: dict[str, Any]) -> EvalCase:
    expected = raw_case["expected"]
    action = raw_case.get("action")
    expected_fail = raw_case.get("expected_fail")
    confirmation_payload = raw_case.get("confirmation_payload")
    snapshot = _snapshot_from_raw(raw_case.get("snapshot"))
    snapshot = _snapshot_with_confirmation_payload(
        snapshot=snapshot,
        confirmation_payload=confirmation_payload,
    )
    return EvalCase(
        id=str(raw_case["id"]),
        category=category,
        prompt=str(raw_case.get("prompt") or ""),
        user_language=str(raw_case.get("user_language") or "en"),
        ui_language=str(
            raw_case.get("ui_language") or raw_case.get("user_language") or "en"
        ),
        expected=TypedExpectations(
            intent=_intent_expectation(expected["intent"]),
            capability_verdict=str(expected["capability_verdict"]),
            assets=tuple(expected.get("assets") or ()),
            asset_class=expected.get("asset_class"),
            requested_strategy_template=expected.get("requested_strategy_template"),
            strategy_type=expected.get("strategy_type"),
            entry_rule=expected.get("entry_rule"),
            exit_rule=expected.get("exit_rule"),
            rule_spec=expected.get("rule_spec"),
            date_range=_date_range_expectation(expected.get("date_range")),
            requested_date_range=_date_range_expectation(expected.get("requested_date_range")),
            effective_date_range=_date_range_expectation(expected.get("effective_date_range")),
            adjustment_reason=expected.get("adjustment_reason"),
            benchmark_symbol=expected.get("benchmark_symbol"),
            capital_amount=expected.get("capital_amount"),
            starting_capital=expected.get("starting_capital"),
            recurring_contribution=expected.get("recurring_contribution"),
            contribution_period=expected.get("contribution_period"),
            launch_validation_code=expected.get("launch_validation_code"),
            missing_required_fields=tuple(expected.get("missing_required_fields") or ()),
            fee_rate=expected.get("fee_rate"),
            slippage=expected.get("slippage"),
            cost_provenance=expected.get("cost_provenance"),
            launch_execution_realism=expected.get("launch_execution_realism"),
            stage_outcomes=tuple(expected.get("stage_outcomes") or ()),
            requested_field=expected.get("requested_field"),
            clarification=expected.get("clarification"),
            semantic_turn_act=expected.get("semantic_turn_act"),
            asset_discovery=expected.get("asset_discovery"),
            offered=expected.get("offered"),
            research=expected.get("research"),
        ),
        action=(
            None
            if action is None
            else EvalAction(
                type=str(action["type"]),
                label=action.get("label"),
                presentation=action.get("presentation"),
                payload=dict(action.get("payload") or {}),
            )
        ),
        followup_prompt=(
            None
            if raw_case.get("followup_prompt") in (None, "")
            else str(raw_case.get("followup_prompt"))
        ),
        snapshot=snapshot,
        confirmation_payload=confirmation_payload,
        recent_thread_history=tuple(
            dict(turn) for turn in (raw_case.get("recent_thread_history") or ())
        ),
        thread_metadata=dict(raw_case.get("thread_metadata") or {}),
        degraded_mode=dict(raw_case.get("degraded_mode") or {}),
        expected_fail=(
            None
            if expected_fail is None
            else ExpectedFail(
                issue=str(expected_fail["issue"]),
                reason=str(expected_fail["reason"]),
                allowed_failures=tuple(expected_fail.get("allowed_failures") or ()),
            )
        ),
        prose_judge_criteria=tuple(raw_case.get("prose_judge", {}).get("criteria") or ()),
        raw=raw_case,
    )


def _snapshot_from_raw(raw: dict[str, Any] | None) -> TaskSnapshot | None:
    if raw is None:
        return None
    payload = dict(raw)
    if "pending_strategy" in payload:
        payload["pending_strategy_summary"] = StrategySummary.model_validate(
            payload.pop("pending_strategy")
        )
    if "active_confirmation_reference" in payload:
        reference = payload["active_confirmation_reference"]
        payload["active_confirmation_reference"] = reference
        payload["artifact_references"] = [reference]
    return TaskSnapshot.model_validate(payload)


def _snapshot_with_confirmation_payload(
    *,
    snapshot: TaskSnapshot | None,
    confirmation_payload: dict[str, Any] | None,
) -> TaskSnapshot | None:
    if snapshot is None or confirmation_payload is None:
        return snapshot
    if snapshot.active_confirmation_reference is not None:
        return snapshot
    confirmation_id = str(
        confirmation_payload.get("confirmation_id")
        or confirmation_payload.get("artifact_id")
        or "eval-confirmation"
    )
    reference_metadata = {
        "confirmation_id": confirmation_id,
        "confirmation_payload": dict(confirmation_payload),
    }
    active_reference = ArtifactReference(
        artifact_kind="confirmation",
        artifact_id=confirmation_id,
        artifact_status="active",
        metadata=dict(reference_metadata),
    )
    listed_reference = ArtifactReference(
        artifact_kind="confirmation",
        artifact_id=confirmation_id,
        artifact_status="active",
        metadata=dict(reference_metadata),
    )
    return snapshot.model_copy(
        update={
            "active_confirmation_reference": active_reference,
            "artifact_references": [*snapshot.artifact_references, listed_reference],
        },
        deep=True,
    )


def _action_payload(action: EvalAction | None) -> dict[str, Any] | None:
    if action is None:
        return None
    return {
        "type": action.type,
        "label": action.label,
        "presentation": action.presentation,
        "payload": dict(action.payload),
    }


def _state_for_confirmation(
    *,
    case: EvalCase,
    interpret_patch: dict[str, Any],
) -> RunState:
    state = RunState.new(current_user_message=case.prompt, recent_thread_history=[])
    if "candidate_strategy_draft" in interpret_patch:
        state.candidate_strategy_draft = StrategySummary.model_validate(
            interpret_patch["candidate_strategy_draft"]
        )
    if "optional_parameter_status" in interpret_patch:
        state.optional_parameter_status = dict(
            interpret_patch["optional_parameter_status"]
        )
    return state


def _state_from_interpret_patch(
    *,
    case: EvalCase,
    interpret_patch: dict[str, Any],
) -> RunState:
    state = _state_for_confirmation(case=case, interpret_patch=interpret_patch)
    state.missing_required_fields = list(
        interpret_patch.get("missing_required_fields") or []
    )
    state.requested_field = interpret_patch.get("requested_field")
    if "response_intent" in interpret_patch:
        state.response_intent = interpret_patch["response_intent"]
    return state


def _typed_outcome(
    *,
    case: EvalCase,
    interpret_result: Any,
    confirm_result: Any | None,
    clarify_result: Any | None,
    followup_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    followup_interpret = (
        followup_result.get("interpret_result") if followup_result else None
    )
    followup_confirm = followup_result.get("confirm_result") if followup_result else None
    followup_clarify = followup_result.get("clarify_result") if followup_result else None
    payload_interpret_result = followup_interpret or interpret_result
    payload_confirm_result = (
        followup_confirm if followup_interpret is not None else confirm_result
    )
    payload_clarify_result = (
        followup_clarify if followup_interpret is not None else clarify_result
    )

    interpret_patch = payload_interpret_result.patch
    final_patch = _final_patch(
        interpret_result=payload_interpret_result,
        confirm_result=payload_confirm_result,
        clarify_result=payload_clarify_result,
    )
    confirmation_payload = final_patch.get("confirmation_payload") or {}
    launch_payload = confirmation_payload.get("launch_payload") or {}
    strategy = (
        confirmation_payload.get("strategy")
        or final_patch.get("candidate_strategy_draft")
        or interpret_patch.get("candidate_strategy_draft")
        or {}
    )
    if not isinstance(strategy, dict):
        strategy = {}
    if not isinstance(launch_payload, dict):
        launch_payload = {}
    extra_parameters = strategy.get("extra_parameters")
    if not isinstance(extra_parameters, dict):
        extra_parameters = {}
    field_provenance = extra_parameters.get("field_provenance")
    if not isinstance(field_provenance, dict):
        field_provenance = {}
    coverage_preflight = launch_payload.get("coverage_preflight")
    if not isinstance(coverage_preflight, dict):
        coverage_preflight = {}
    requested_date_range = (
        launch_payload.get("requested_date_range")
        or coverage_preflight.get("requested_date_range")
        or strategy.get("date_range")
    )
    effective_date_range = (
        coverage_preflight.get("effective_date_range")
        or launch_payload.get("date_range")
        or strategy.get("date_range")
    )

    return {
        "intent": _intent(case=case, patch=interpret_patch),
        "stage_outcomes": [
            str(interpret_result.outcome),
            *([] if confirm_result is None else [str(confirm_result.outcome)]),
            *([] if clarify_result is None else [str(clarify_result.outcome)]),
            *([] if followup_interpret is None else [str(followup_interpret.outcome)]),
            *([] if followup_confirm is None else [str(followup_confirm.outcome)]),
            *([] if followup_clarify is None else [str(followup_clarify.outcome)]),
        ],
        "assets": _symbols(launch_payload=launch_payload, strategy=strategy),
        "asset_class": launch_payload.get("asset_class") or strategy.get("asset_class"),
        "requested_strategy_template": strategy.get("requested_strategy_template"),
        "strategy_type": launch_payload.get("strategy_type")
        or strategy.get("strategy_type"),
        "entry_rule": launch_payload.get("entry_rule") or strategy.get("entry_rule"),
        "exit_rule": launch_payload.get("exit_rule") or strategy.get("exit_rule"),
        "rule_spec": launch_payload.get("rule_spec") or strategy.get("rule_spec"),
        "date_range": requested_date_range,
        "requested_date_range": requested_date_range,
        "effective_date_range": effective_date_range,
        "adjustment_reason": coverage_preflight.get("adjustment_reason"),
        "benchmark_symbol": (
            launch_payload.get("benchmark_symbol")
            or strategy.get("benchmark_symbol")
            or strategy.get("comparison_baseline")
        ),
        "capital_amount": (
            launch_payload.get("capital_amount") or strategy.get("capital_amount")
        ),
        # Both DCA money roles come only from the launch payload: they exist
        # as launch truth or not at all, so a fixture cannot pass by reading
        # a draft field that never became a fundable plan.
        "starting_capital": launch_payload.get("starting_capital"),
        "recurring_contribution": launch_payload.get("recurring_contribution"),
        "contribution_period": (launch_payload.get("cadence") or strategy.get("cadence")),
        "launch_validation_code": final_patch.get("launch_validation_code"),
        "missing_required_fields": final_patch.get("missing_required_fields"),
        "fee_rate": extra_parameters.get("fee_rate"),
        "slippage": extra_parameters.get("slippage"),
        "cost_provenance": {
            key: field_provenance[key]
            for key in ("fee_rate", "slippage")
            if key in field_provenance
        },
        "launch_execution_realism": launch_payload.get("_execution_realism"),
        "capability_verdict": _capability_verdict(
            outcome=_last_stage_outcome(
                interpret_result=payload_interpret_result,
                confirm_result=payload_confirm_result,
                clarify_result=payload_clarify_result,
            ),
            patch=final_patch,
        ),
        "requested_field": final_patch.get("requested_field"),
        "clarification": final_patch.get("clarification"),
        "semantic_turn_act": interpret_patch.get("semantic_turn_act"),
        "asset_discovery": interpret_patch.get("asset_discovery"),
        "research": _research_outcome(final_patch),
        "offered": offered_to_user(
            final_patch=final_patch,
            interpret_patch=interpret_patch,
            launch_payload=launch_payload,
            assistant_text=_assistant_text(final_patch),
        ),
    }


def _research_outcome(patch: dict[str, Any]) -> dict[str, Any] | None:
    """The typed research sidecar as the eval reads it, or None when the turn
    took no rail: published is the absence of a degraded code, rows and
    sources are counts of what the sidecar carries."""
    sidecar = patch.get("research")
    if not isinstance(sidecar, dict):
        return None
    degraded = sidecar.get("degraded")
    return {
        "published": not degraded,
        "degraded_code": degraded.get("code") if isinstance(degraded, dict) else None,
        "shape": sidecar.get("shape"),
        "rows": len(sidecar.get("rows") or []),
        "sources": len(sidecar.get("sources") or []),
    }


def _compare_research(expected: dict[str, Any], actual: Any, failures: list[str]) -> None:
    if not isinstance(actual, dict):
        failures.append(f"research: expected a research sidecar, got {actual!r}")
        return
    _compare(
        "research.published", expected.get("published"), actual.get("published"), failures
    )
    _compare("research.shape", expected.get("shape"), actual.get("shape"), failures)
    # An expected row count is a floor: a green case promises at least that
    # many typed figures, and the provider is free to state more.
    rows = expected.get("rows")
    if rows is not None and (actual.get("rows") or 0) < rows:
        failures.append(
            f"research.rows: expected at least {rows}, got {actual.get('rows')!r}"
        )


def _final_patch(
    *,
    interpret_result: Any,
    confirm_result: Any | None,
    clarify_result: Any | None,
) -> dict[str, Any]:
    if clarify_result is not None:
        return {
            **interpret_result.patch,
            **(confirm_result.patch if confirm_result is not None else {}),
            **clarify_result.patch,
        }
    if confirm_result is not None:
        return confirm_result.patch
    return interpret_result.patch


def _intent(*, case: EvalCase, patch: dict[str, Any]) -> str | None:
    if patch.get("intent"):
        return str(patch["intent"])
    if case.action is None:
        return None
    if case.action.type == "run_backtest":
        return "backtest_execution"
    if case.action.type in {"change_asset", "change_dates", "adjust_assumptions"}:
        return "strategy_drafting"
    return "conversation_followup"


def _symbols(*, launch_payload: dict[str, Any], strategy: dict[str, Any]) -> list[str]:
    raw_symbols = launch_payload.get("symbols") or strategy.get("asset_universe") or []
    return [str(symbol).upper() for symbol in raw_symbols]


def _capability_verdict(*, outcome: str, patch: dict[str, Any]) -> str:
    confirmation_payload = patch.get("confirmation_payload")
    if outcome == "approved_for_execution":
        return "approved_for_execution"
    if isinstance(confirmation_payload, dict):
        validation = confirmation_payload.get("validation")
        if isinstance(validation, dict) and validation.get("executable") is True:
            return "executable"
    unsupported = patch.get("unsupported_constraints")
    if unsupported:
        return "unsupported"
    if outcome in {"needs_clarification", "await_user_reply"}:
        return "needs_clarification"
    if patch.get("intent") == "unsupported_or_out_of_scope":
        return "unsupported"
    return "answer_only"


def _assistant_text(patch: dict[str, Any]) -> str:
    return str(patch.get("assistant_response") or patch.get("assistant_prompt") or "")


def _intent_expectation(raw: Any) -> str | tuple[str, ...]:
    if isinstance(raw, list):
        intents = tuple(str(item) for item in raw)
        if not intents:
            raise ValueError("intent expectation list cannot be empty")
        return intents
    return str(raw)


def _compare_intent(
    expected: str | tuple[str, ...],
    actual: Any,
    failures: list[str],
) -> None:
    if isinstance(expected, tuple):
        if actual not in expected:
            failures.append(f"intent: expected one of {list(expected)!r}, got {actual!r}")
        return
    _compare("intent", expected, actual, failures)


def _compare_asset_discovery(
    expected: dict[str, Any],
    actual: Any,
    failures: list[str],
) -> None:
    if not isinstance(actual, dict):
        failures.append(f"asset_discovery: expected payload {expected!r}, got {actual!r}")
        return
    _compare(
        "asset_discovery.relationship",
        expected.get("relationship"),
        actual.get("relationship"),
        failures,
    )
    _compare(
        "asset_discovery.asset_class_hint",
        expected.get("asset_class_hint"),
        actual.get("asset_class_hint"),
        failures,
    )
    if "needs_current_facts" in expected:
        _compare(
            "asset_discovery.needs_current_facts",
            expected["needs_current_facts"],
            actual.get("needs_current_facts"),
            failures,
        )
    expected_anchors = expected.get("anchor_symbols")
    if expected_anchors is not None:
        actual_anchors = sorted(
            str(symbol).upper() for symbol in (actual.get("anchor_symbols") or [])
        )
        _compare(
            "asset_discovery.anchor_symbols",
            sorted(str(symbol).upper() for symbol in expected_anchors),
            actual_anchors,
            failures,
        )
    include_terms = expected.get("category_description_includes_any")
    if include_terms:
        description = str(actual.get("category_description") or "").lower()
        if not any(str(term).lower() in description for term in include_terms):
            failures.append(
                "asset_discovery.category_description: expected any of "
                f"{list(include_terms)!r} in {description!r}"
            )


def _last_stage_outcome(
    *,
    interpret_result: Any,
    confirm_result: Any | None,
    clarify_result: Any | None,
) -> str:
    if clarify_result is not None:
        return str(clarify_result.outcome)
    if confirm_result is not None:
        return str(confirm_result.outcome)
    return str(interpret_result.outcome)


def _result_status(
    failed_checks: list[str],
    *,
    expected_fail: ExpectedFail | None,
) -> str:
    if failed_checks and _all_failures_are_expected(
        failed_checks,
        expected_fail=expected_fail,
    ):
        return "expected_failed"
    if failed_checks:
        return "failed"
    if expected_fail is not None:
        return "unexpected_pass"
    return "passed"


def _all_failures_are_expected(
    failed_checks: list[str],
    *,
    expected_fail: ExpectedFail | None,
) -> bool:
    if expected_fail is None or not expected_fail.allowed_failures:
        return False
    return all(
        any(
            failed_check.startswith(allowed) for allowed in expected_fail.allowed_failures
        )
        for failed_check in failed_checks
    )
