from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from argus.agent_runtime.capabilities.contract import (
    CapabilityContract,
    build_default_capability_contract,
)
from argus.agent_runtime.graph.workflow import WorkflowStageOutcome
from argus.agent_runtime.workflow_contract import WORKFLOW_NODE_NAMES
from argus.domain.indicators import EXECUTABLE_INDICATORS
from argus.llm.openrouter import OpenRouterRouteReceipt
from argus.observability.cost_ledger import (
    CostLedgerGateway,
    persist_openrouter_cost_ledger_entries,
)

MANIFEST_PATH = Path(__file__).with_name("chat_runtime_scenarios.json")
ALPHA_TRAJECTORY_PATH = Path(__file__).with_name("alpha_session_trajectories.json")
TRAJECTORY_SCORECARD_DIR = Path("temp/argus_eval_scorecards")
TRAJECTORY_OPERATIONS = {
    "stream",
    "action",
    "disconnect",
    "reload",
    "retry",
    "persistence",
}
CANONICAL_SSE_EVENT_TYPES = {
    "stage_start",
    "token",
    "stage_outcome",
    "title",
    "final",
    "error",
}
WORKFLOW_STAGE_OUTCOMES = frozenset(outcome.value for outcome in WorkflowStageOutcome)


@dataclass(frozen=True)
class RouteBudget:
    max_calls: int | None = None
    max_cost_usd: float | None = None
    max_latency_ms: int | None = None

    def as_dict(self) -> dict[str, int | float | None]:
        return {
            "max_calls": self.max_calls,
            "max_cost_usd": self.max_cost_usd,
            "max_latency_ms": self.max_latency_ms,
        }


@dataclass(frozen=True)
class TrajectoryExpectation:
    visible_response_category: str | None = None
    stage_outcome: str | None = None
    canonical_sse: bool | None = None
    artifact_identity: str | None = None
    action_identity: str | None = None
    persistence_state: str | None = None
    reload_state: str | None = None
    recovery_code: str | None = None
    route_budget: RouteBudget | None = None
    typed_terminal: bool | None = None
    checkpoints: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "visible_response_category": self.visible_response_category,
            "stage_outcome": self.stage_outcome,
            "canonical_sse": self.canonical_sse,
            "artifact_identity": self.artifact_identity,
            "action_identity": self.action_identity,
            "persistence_state": self.persistence_state,
            "reload_state": self.reload_state,
            "recovery_code": self.recovery_code,
            "route_budget": (
                None if self.route_budget is None else self.route_budget.as_dict()
            ),
            "typed_terminal": self.typed_terminal,
            "checkpoints": dict(self.checkpoints),
        }


@dataclass(frozen=True)
class TrajectoryAllowedFailure:
    step_id: str
    prefix: str


@dataclass(frozen=True)
class TrajectoryExpectedFail:
    issue: str
    reason: str
    allowed_failures: tuple[TrajectoryAllowedFailure, ...]


@dataclass(frozen=True)
class TrajectoryStep:
    step_id: str
    index: int
    operation: str
    request: dict[str, Any]
    expectation: TrajectoryExpectation


@dataclass(frozen=True)
class AlphaTrajectory:
    label: str
    locale: str
    purpose: str
    tags: tuple[str, ...]
    steps: tuple[TrajectoryStep, ...]
    expected_fail: TrajectoryExpectedFail | None


@dataclass(frozen=True)
class StepObservation:
    raw_sse: str | None = None
    visible_response_category: str | None = None
    stage_outcome: str | None = None
    artifact_identity: str | None = None
    action_identity: str | None = None
    persistence_state: str | None = None
    reload_state: str | None = None
    recovery_code: str | None = None
    route_receipts: tuple[dict[str, Any], ...] = ()
    typed_terminal: bool | None = None
    fingerprint: str | None = None
    checkpoints: dict[str, Any] = field(default_factory=dict)
    stale_action_executions: int = 0
    accepted_orphan_turns_after_window: int = 0


TrajectoryStepHandler = Callable[..., StepObservation]


@dataclass(frozen=True)
class TrajectoryAdapters:
    stream: TrajectoryStepHandler
    action: TrajectoryStepHandler
    disconnect: TrajectoryStepHandler
    reload: TrajectoryStepHandler
    retry: TrajectoryStepHandler
    persistence: TrajectoryStepHandler

    def for_operation(self, operation: str) -> TrajectoryStepHandler:
        if operation not in TRAJECTORY_OPERATIONS:
            raise ValueError(f"unsupported trajectory operation: {operation}")
        return getattr(self, operation)


@dataclass(frozen=True)
class TrajectoryStepResult:
    step_id: str
    operation: str
    observation: StepObservation
    failed_checks: tuple[str, ...]


@dataclass(frozen=True)
class TrajectoryResult:
    label: str
    locale: str
    status: str
    failed_checks: tuple[str, ...]
    expected_fail: TrajectoryExpectedFail | None
    step_results: tuple[TrajectoryStepResult, ...]


@dataclass(frozen=True)
class ChatRuntimeEvalStep:
    step_id: str
    actor: str
    prompt_variants: tuple[str, ...]
    action_type: str | None
    semantic_target: str
    hard_checks: tuple[str, ...]


@dataclass(frozen=True)
class ChatRuntimeEvalCase:
    scenario_id: str
    qa_id: str
    priority: str
    prompt: str
    steps: tuple[ChatRuntimeEvalStep, ...]
    semantic_target: str
    hard_checks: tuple[str, ...]
    forbidden_outcomes: tuple[str, ...]
    judge_rubric: str


def load_eval_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_alpha_trajectories(
    path: Path = ALPHA_TRAJECTORY_PATH,
) -> list[AlphaTrajectory]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    trajectories: list[AlphaTrajectory] = []
    for raw_trajectory in payload["trajectories"]:
        steps = tuple(
            _trajectory_step_from_raw(
                label=str(raw_trajectory["label"]),
                index=index,
                raw_step=raw_step,
            )
            for index, raw_step in enumerate(raw_trajectory["steps"], start=1)
        )
        expected_fail = raw_trajectory.get("expected_fail")
        trajectories.append(
            AlphaTrajectory(
                label=str(raw_trajectory["label"]),
                locale=str(raw_trajectory["locale"]),
                purpose=str(raw_trajectory["purpose"]),
                tags=tuple(str(tag) for tag in raw_trajectory.get("tags") or ()),
                steps=steps,
                expected_fail=(
                    None
                    if expected_fail is None
                    else TrajectoryExpectedFail(
                        issue=str(expected_fail["issue"]),
                        reason=str(expected_fail["reason"]),
                        allowed_failures=tuple(
                            TrajectoryAllowedFailure(
                                step_id=str(allowed_failure["step_id"]),
                                prefix=str(allowed_failure["prefix"]),
                            )
                            for allowed_failure in expected_fail.get("allowed_failures")
                            or ()
                        ),
                    )
                ),
            )
        )
    return trajectories


def _trajectory_step_from_raw(
    *,
    label: str,
    index: int,
    raw_step: dict[str, Any],
) -> TrajectoryStep:
    operation = str(raw_step["operation"])
    if operation not in TRAJECTORY_OPERATIONS:
        raise ValueError(f"unsupported trajectory operation: {operation}")
    raw_expectation = dict(raw_step.get("expect") or {})
    raw_budget = raw_expectation.get("route_budget")
    budget = (
        None
        if raw_budget is None
        else RouteBudget(
            max_calls=raw_budget.get("max_calls"),
            max_cost_usd=raw_budget.get("max_cost_usd"),
            max_latency_ms=raw_budget.get("max_latency_ms"),
        )
    )
    request = dict(raw_step.get("request") or {})
    if operation == "disconnect":
        _validate_disconnect_submission(request=request, step_id=f"{label}:step:{index}")
    return TrajectoryStep(
        step_id=f"{label}:step:{index}",
        index=index,
        operation=operation,
        request=request,
        expectation=TrajectoryExpectation(
            visible_response_category=raw_expectation.get("visible_response_category"),
            stage_outcome=raw_expectation.get("stage_outcome"),
            canonical_sse=raw_expectation.get("canonical_sse"),
            artifact_identity=raw_expectation.get("artifact_identity"),
            action_identity=raw_expectation.get("action_identity"),
            persistence_state=raw_expectation.get("persistence_state"),
            reload_state=raw_expectation.get("reload_state"),
            recovery_code=raw_expectation.get("recovery_code"),
            route_budget=budget,
            typed_terminal=raw_expectation.get("typed_terminal"),
            checkpoints=dict(raw_expectation.get("checkpoints") or {}),
        ),
    )


def run_alpha_trajectory(
    *,
    trajectory: AlphaTrajectory,
    adapters: TrajectoryAdapters,
) -> TrajectoryResult:
    step_results: list[TrajectoryStepResult] = []
    failed_checks: list[str] = []
    unterminated_fingerprints: set[str] = set()
    client_terminal_submissions: set[str] = set()

    for step in trajectory.steps:
        handler = adapters.for_operation(step.operation)
        observation = handler(
            trajectory=trajectory,
            step=step,
            history=tuple(step_results),
        )
        if not isinstance(observation, StepObservation):
            raise TypeError(
                f"trajectory adapter for {step.operation} must return StepObservation"
            )
        step_failures = _trajectory_step_failures(
            step=step,
            observation=observation,
            unterminated_fingerprints=unterminated_fingerprints,
        )
        submission_identity = _submission_identity(step)
        if (
            step.operation == "disconnect"
            and submission_identity in client_terminal_submissions
        ):
            step_failures.append(
                "disconnect: "
                f"{step.step_id} attempted to disconnect submission "
                f"{submission_identity!r} after its client terminal was observed"
            )
        if observation.typed_terminal is True and submission_identity is not None:
            client_terminal_submissions.add(submission_identity)
        step_results.append(
            TrajectoryStepResult(
                step_id=step.step_id,
                operation=step.operation,
                observation=observation,
                failed_checks=tuple(step_failures),
            )
        )
        failed_checks.extend(step_failures)

    resolved_step_results = tuple(step_results)
    return TrajectoryResult(
        label=trajectory.label,
        locale=trajectory.locale,
        status=_trajectory_status(
            resolved_step_results,
            expected_fail=trajectory.expected_fail,
        ),
        failed_checks=tuple(failed_checks),
        expected_fail=trajectory.expected_fail,
        step_results=resolved_step_results,
    )


def _validate_disconnect_submission(*, request: dict[str, Any], step_id: str) -> None:
    submission = request.get("submission")
    if not isinstance(submission, dict):
        raise ValueError(f"disconnect step {step_id} must own a submission")
    if submission.get("operation") not in {"stream", "action"}:
        raise ValueError(
            f"disconnect step {step_id} submission must use stream or action"
        )
    if not _non_empty_string(submission.get("identity")):
        raise ValueError(
            f"disconnect step {step_id} submission must have a stable identity"
        )
    if not isinstance(submission.get("request"), dict):
        raise ValueError(
            f"disconnect step {step_id} submission must include a request object"
        )


def _submission_identity(step: TrajectoryStep) -> str | None:
    if step.operation == "disconnect":
        submission = step.request.get("submission")
        if isinstance(submission, dict) and _non_empty_string(submission.get("identity")):
            return str(submission["identity"])
        return None
    identity = step.request.get("submission_identity")
    return str(identity) if _non_empty_string(identity) else None


def _trajectory_step_failures(
    *,
    step: TrajectoryStep,
    observation: StepObservation,
    unterminated_fingerprints: set[str],
) -> list[str]:
    expectation = step.expectation
    failures: list[str] = []
    _trajectory_compare(
        "visible_response",
        expectation.visible_response_category,
        observation.visible_response_category,
        step_id=step.step_id,
        failures=failures,
    )
    _trajectory_compare(
        "stage_outcome",
        expectation.stage_outcome,
        observation.stage_outcome,
        step_id=step.step_id,
        failures=failures,
    )
    _trajectory_compare(
        "artifact_identity",
        expectation.artifact_identity,
        observation.artifact_identity,
        step_id=step.step_id,
        failures=failures,
    )
    _trajectory_compare(
        "action_identity",
        expectation.action_identity,
        observation.action_identity,
        step_id=step.step_id,
        failures=failures,
    )
    _trajectory_compare(
        "persistence",
        expectation.persistence_state,
        observation.persistence_state,
        step_id=step.step_id,
        failures=failures,
    )
    _trajectory_compare(
        "reload",
        expectation.reload_state,
        observation.reload_state,
        step_id=step.step_id,
        failures=failures,
    )
    _trajectory_compare(
        "recovery",
        expectation.recovery_code,
        observation.recovery_code,
        step_id=step.step_id,
        failures=failures,
    )
    _trajectory_compare(
        "terminal",
        expectation.typed_terminal,
        observation.typed_terminal,
        step_id=step.step_id,
        failures=failures,
    )

    if expectation.canonical_sse is True:
        failures.extend(
            _canonical_sse_failures(
                raw_sse=observation.raw_sse,
                step_id=step.step_id,
            )
        )
    if expectation.route_budget is not None:
        failures.extend(
            _route_budget_failures(
                budget=expectation.route_budget,
                receipts=observation.route_receipts,
                step_id=step.step_id,
            )
        )
    for checkpoint, expected_value in expectation.checkpoints.items():
        actual_value = observation.checkpoints.get(checkpoint)
        prefix = checkpoint.split(".", 1)[0]
        _trajectory_compare(
            prefix,
            expected_value,
            actual_value,
            step_id=step.step_id,
            detail=checkpoint,
            failures=failures,
        )

    if observation.stale_action_executions != 0:
        failures.append(
            "stale_action: "
            f"{step.step_id} executed {observation.stale_action_executions} stale action(s)"
        )
    if observation.accepted_orphan_turns_after_window != 0:
        failures.append(
            "orphan_turn: "
            f"{step.step_id} retained {observation.accepted_orphan_turns_after_window} "
            "accepted orphan turn(s) after the reconciliation window"
        )

    fingerprint = observation.fingerprint
    if fingerprint:
        if observation.typed_terminal is True:
            unterminated_fingerprints.discard(fingerprint)
        elif fingerprint in unterminated_fingerprints:
            failures.append(
                f"fingerprint: {step.step_id} repeated {fingerprint!r} without a typed terminal"
            )
        else:
            unterminated_fingerprints.add(fingerprint)
    return failures


def _trajectory_compare(
    prefix: str,
    expected: Any,
    actual: Any,
    *,
    step_id: str,
    failures: list[str],
    detail: str | None = None,
) -> None:
    if expected is None:
        return
    if actual != expected:
        label = detail or prefix
        failures.append(
            f"{prefix}: {step_id} {label} expected {expected!r}, got {actual!r}"
        )


def _canonical_sse_failures(*, raw_sse: str | None, step_id: str) -> list[str]:
    if not raw_sse:
        return [f"sse: {step_id} expected canonical SSE frames, got no stream"]
    normalized = raw_sse.replace("\r\n", "\n").strip()
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    if any(line.startswith("event:") for line in lines):
        return [f"sse: {step_id} used legacy named event frames"]
    frames = normalized.split("\n\n") if normalized else []
    if not frames or frames[-1].strip() != "data: [DONE]":
        return [f"sse: {step_id} did not end with data: [DONE]"]
    decoded_events: list[dict[str, Any]] = []
    for frame in frames[:-1]:
        frame_lines = [line.strip() for line in frame.splitlines() if line.strip()]
        if len(frame_lines) != 1:
            return [f"sse: {step_id} contains unframed canonical events"]
        line = frame_lines[0]
        if line.startswith(":"):
            continue
        if line.startswith("retry:"):
            retry_milliseconds = line.partition(":")[2].strip()
            if not retry_milliseconds.isdigit():
                return [f"sse: {step_id} contains an invalid retry control field"]
            continue
        if not line.startswith("data: "):
            return [f"sse: {step_id} contains a non-data frame"]
        try:
            payload = json.loads(line.removeprefix("data: "))
        except json.JSONDecodeError:
            return [f"sse: {step_id} contains invalid JSON data"]
        if not isinstance(payload, dict) or not isinstance(payload.get("type"), str):
            return [f"sse: {step_id} contains an untyped data frame"]
        schema_failure = _canonical_sse_event_schema_failure(payload)
        if schema_failure is not None:
            return [f"sse: {step_id} {schema_failure}"]
        decoded_events.append(payload)
    event_types = [str(event["type"]) for event in decoded_events]
    terminal_indices = [
        index
        for index, event_type in enumerate(event_types)
        if event_type in {"final", "error"}
    ]
    if not terminal_indices:
        return [f"sse: {step_id} has no typed terminal frame"]
    if len(terminal_indices) != 1:
        return [f"sse: {step_id} has multiple typed terminal frames"]
    terminal_index = terminal_indices[0]
    if terminal_index != len(event_types) - 1:
        return [f"sse: {step_id} emitted data after the typed terminal frame"]
    if event_types == ["error"]:
        return []
    if not event_types or event_types[0] != "stage_start":
        return [f"sse: {step_id} did not start with a stage_start frame"]

    stage_started = False
    stage_outcome_seen = False
    for event_type in event_types[:terminal_index]:
        if event_type == "stage_start":
            stage_started = True
        elif event_type == "stage_outcome":
            if not stage_started:
                return [f"sse: {step_id} emitted stage_outcome before stage_start"]
            stage_outcome_seen = True
    if event_types[terminal_index] == "final" and not stage_outcome_seen:
        return [f"sse: {step_id} emitted final before a stage_outcome frame"]
    return []


def _canonical_sse_event_schema_failure(event: dict[str, Any]) -> str | None:
    event_type = str(event["type"])
    if event_type not in CANONICAL_SSE_EVENT_TYPES:
        return f"contains unknown event type {event_type!r}"
    if event_type == "stage_start":
        stage = event.get("stage")
        if not _non_empty_string(stage):
            return "stage_start is missing a typed stage"
        if stage not in WORKFLOW_NODE_NAMES:
            return f"stage_start has unknown stage {stage!r}"
    if event_type == "stage_outcome":
        outcome = event.get("outcome")
        if not _non_empty_string(outcome):
            return "stage_outcome is missing a typed outcome"
        if outcome not in WORKFLOW_STAGE_OUTCOMES:
            return f"stage_outcome has unknown outcome {outcome!r}"
    if event_type == "token" and not isinstance(event.get("content"), str):
        return "token is missing string content"
    if event_type == "title" and (
        not _non_empty_string(event.get("conversation_id"))
        or not _non_empty_string(event.get("title"))
    ):
        return "title is missing conversation_id or title"
    if event_type == "final":
        payload = event.get("payload")
        if not isinstance(payload, dict) or not _non_empty_string(
            payload.get("stage_outcome")
        ):
            return "final is missing payload.stage_outcome"
        if payload["stage_outcome"] not in WORKFLOW_STAGE_OUTCOMES:
            return (
                "final has unknown payload.stage_outcome " f"{payload['stage_outcome']!r}"
            )
    if event_type == "error" and (
        not _non_empty_string(event.get("code"))
        or not _non_empty_string(event.get("message"))
    ):
        return "error is missing code or message"
    return None


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _route_budget_failures(
    *,
    budget: RouteBudget,
    receipts: tuple[dict[str, Any], ...],
    step_id: str,
) -> list[str]:
    failures: list[str] = []
    if not receipts:
        failures.append(f"budget.calls: {step_id} has no route-receipt evidence")
    if budget.max_calls is not None and len(receipts) > budget.max_calls:
        failures.append(
            f"budget.calls: {step_id} expected at most {budget.max_calls}, got {len(receipts)}"
        )
    if budget.max_cost_usd is not None:
        costs = [_receipt_number(receipt, "usage_cost_usd") for receipt in receipts]
        if any(cost is None for cost in costs):
            failures.append(
                f"budget.cost: {step_id} contains missing or invalid usage_cost_usd"
            )
        else:
            total_cost = sum(cost for cost in costs if cost is not None)
            if total_cost > budget.max_cost_usd:
                failures.append(
                    f"budget.cost: {step_id} expected at most "
                    f"{budget.max_cost_usd}, got {total_cost}"
                )
    if budget.max_latency_ms is not None:
        latencies = [_receipt_number(receipt, "latency_ms") for receipt in receipts]
        if any(latency is None for latency in latencies):
            failures.append(
                f"budget.latency: {step_id} contains missing or invalid latency_ms"
            )
        else:
            total_latency = sum(latency for latency in latencies if latency is not None)
            if total_latency > budget.max_latency_ms:
                failures.append(
                    f"budget.latency: {step_id} expected at most "
                    f"{budget.max_latency_ms}, got {total_latency}"
                )
    return failures


def _receipt_number(receipt: dict[str, Any], key: str) -> float | None:
    value = receipt.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number) or number < 0:
        return None
    return number


def _trajectory_status(
    step_results: tuple[TrajectoryStepResult, ...],
    *,
    expected_fail: TrajectoryExpectedFail | None,
) -> str:
    failed_step_results = [result for result in step_results if result.failed_checks]
    if not failed_step_results:
        return "unexpected_pass" if expected_fail is not None else "passed"
    if expected_fail is None or not expected_fail.allowed_failures:
        return "failed"
    if all(
        any(
            allowed_failure.step_id == step_result.step_id
            and check.startswith(allowed_failure.prefix)
            for allowed_failure in expected_fail.allowed_failures
        )
        for step_result in failed_step_results
        for check in step_result.failed_checks
    ):
        return "expected_failed"
    return "failed"


def trajectory_scorecard_for_results(
    results: list[TrajectoryResult],
) -> dict[str, Any]:
    statuses = ("passed", "failed", "expected_failed", "unexpected_pass")
    totals = {status: 0 for status in statuses}
    safe_results: list[dict[str, Any]] = []
    for result in results:
        status = result.status if result.status in totals else "failed"
        totals[status] += 1
        expected_fail = result.expected_fail
        safe_results.append(
            {
                "label": result.label,
                "locale": result.locale,
                "status": status,
                "expected_fail_issue": (
                    None if expected_fail is None else expected_fail.issue
                ),
                "allowed_failures": (
                    []
                    if expected_fail is None
                    else [
                        {
                            "step_id": allowed_failure.step_id,
                            "prefix": allowed_failure.prefix,
                        }
                        for allowed_failure in expected_fail.allowed_failures
                    ]
                ),
                "failure_prefixes": _failure_prefixes(result.failed_checks),
                "steps": [
                    {
                        "step_id": step_result.step_id,
                        "operation": step_result.operation,
                        "failure_prefixes": _failure_prefixes(step_result.failed_checks),
                    }
                    for step_result in result.step_results
                ],
            }
        )
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_fixture": ALPHA_TRAJECTORY_PATH.name,
        "totals": totals,
        "results": safe_results,
    }


def write_trajectory_scorecard(
    results: list[TrajectoryResult],
    *,
    output_dir: Path = TRAJECTORY_SCORECARD_DIR,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    scorecard = trajectory_scorecard_for_results(results)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"alpha-trajectory-scorecard-{stamp}.json"
    path.write_text(json.dumps(scorecard, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _failure_prefixes(failed_checks: tuple[str, ...]) -> list[str]:
    return sorted({f"{check.partition(':')[0]}:" for check in failed_checks})


def capability_context_payload(
    contract: CapabilityContract | None = None,
) -> dict[str, Any]:
    resolved_contract = contract or build_default_capability_contract()
    return {
        "contract_version": resolved_contract.version,
        "supported_intents": list(resolved_contract.supported_intents),
        "supported_tool_families": list(resolved_contract.supported_tool_families),
        "required_fields": list(resolved_contract.required_fields),
        "optional_defaults": resolved_contract.optional_defaults,
        "validation_rules": [
            {
                "field_name": rule.field_name,
                "rule_type": rule.rule_type,
                "message": rule.message,
            }
            for rule in resolved_contract.validation_rules
        ],
        "simplification_options": {
            category: [
                option.model_dump(mode="python")
                for option in resolved_contract.get_simplification_options(category)
            ]
            for category in resolved_contract.simplification_templates
        },
        "executable_indicators": [
            {
                "key": key,
                "label": spec.label,
                "default_parameters": dict(spec.default_parameters),
                "support_status": spec.support_status,
                "provider_source": spec.provider_source,
            }
            for key, spec in sorted(EXECUTABLE_INDICATORS.items())
        ],
        "deterministic_boundaries": [
            "asset resolution and provider availability",
            "same-asset-class validation",
            "max symbol limits",
            "benchmark defaults and explicit benchmark metadata",
            "engine run facts and persisted result truth",
        ],
    }


def iter_eval_cases(
    manifest: dict[str, Any] | None = None,
    *,
    priority: str | None = None,
) -> list[ChatRuntimeEvalCase]:
    source = manifest or load_eval_manifest()
    cases: list[ChatRuntimeEvalCase] = []
    for scenario in source["scenarios"]:
        if priority is not None and scenario["priority"] != priority:
            continue
        for prompt in scenario["natural_prompt_variants"]:
            steps = tuple(
                ChatRuntimeEvalStep(
                    step_id=f"{scenario['id']}:step:{index}",
                    actor=str(raw_step["actor"]),
                    prompt_variants=(
                        (prompt,)
                        if index == 1
                        else tuple(str(item) for item in raw_step.get("variants") or ())
                    ),
                    action_type=raw_step.get("action_type"),
                    semantic_target=str(raw_step["semantic_target"]),
                    hard_checks=tuple(
                        str(item) for item in raw_step.get("hard_checks") or ()
                    ),
                )
                for index, raw_step in enumerate(scenario["conversation_steps"], start=1)
            )
            first_step = steps[0]
            cases.append(
                ChatRuntimeEvalCase(
                    scenario_id=scenario["id"],
                    qa_id=scenario["qa_id"],
                    priority=scenario["priority"],
                    prompt=prompt,
                    steps=steps,
                    semantic_target=first_step.semantic_target,
                    hard_checks=first_step.hard_checks,
                    forbidden_outcomes=tuple(scenario["forbidden_outcomes"]),
                    judge_rubric=scenario["judge_rubric"],
                )
            )
    return cases


def build_semantic_judge_messages(
    *,
    case: ChatRuntimeEvalCase,
    assistant_response: str,
    final_payload: dict[str, Any] | None,
    route_receipts: list[dict[str, Any]],
    capability_context: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    payload = {
        "case": {
            "scenario_id": case.scenario_id,
            "qa_id": case.qa_id,
            "priority": case.priority,
            "prompt": case.prompt,
            "semantic_target": case.semantic_target,
            "hard_checks": list(case.hard_checks),
            "semantic_steps": [
                {
                    "step_id": step.step_id,
                    "semantic_target": step.semantic_target,
                    "hard_checks": list(step.hard_checks),
                }
                for step in case.steps
            ],
            "forbidden_outcomes": list(case.forbidden_outcomes),
            "judge_rubric": case.judge_rubric,
        },
        "capability_context": capability_context or capability_context_payload(),
        "runtime_output": {
            "assistant_response": assistant_response,
            "final_payload": final_payload or {},
            "route_receipts": route_receipts,
        },
    }
    return [
        {
            "role": "system",
            "content": (
                "You are the Argus chat-runtime semantic evaluator. Judge whether "
                "the ordered semantic steps satisfy every target and hard check "
                "using the capability context provided here. Do not require exact "
                "wording. Do not reward claims that unsupported behavior is "
                "executable. Return compact JSON with pass, failed_checks, "
                "forbidden_outcomes_seen, groundedness_notes, and "
                "route_receipt_notes."
            ),
        },
        {"role": "user", "content": json.dumps(payload, sort_keys=True)},
    ]


def persist_eval_harness_cost_ledger_entries(
    *,
    gateway: CostLedgerGateway,
    receipts: list[OpenRouterRouteReceipt],
    eval_suite_id: str,
    eval_case_id: str,
) -> None:
    persist_openrouter_cost_ledger_entries(
        gateway=gateway,
        receipts=receipts,
        source="eval_harness",
        feature_area="eval_readiness",
        correlation_id=f"eval:{eval_suite_id}:{eval_case_id}",
        metadata={
            "eval_suite_id": eval_suite_id,
            "eval_case_id": eval_case_id,
        },
    )


def parse_sse_events(raw_stream: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in raw_stream.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line.removeprefix("data: ")
        if payload == "[DONE]":
            continue
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict):
            events.append(decoded)
    return events
