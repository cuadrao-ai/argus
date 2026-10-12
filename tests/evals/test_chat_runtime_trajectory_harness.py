from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest
from argus.agent_runtime.stages.interpret import StructuredInterpretation
from argus.api import state as api_state
from argus.llm.openrouter import _SCHEMA_IN_PROMPT_INSTRUCTION
from pydantic import ValidationError

from tests.evals.chat_runtime_eval_harness import (
    ALPHA_TRAJECTORY_PATH,
    StepObservation,
    TrajectoryAdapters,
    load_alpha_trajectories,
    run_alpha_trajectory,
    trajectory_scorecard_for_results,
    write_trajectory_scorecard,
)
from tests.evals.chat_runtime_trajectory_adapters import ConcreteTrajectoryRuntime


def _typed_transport_content(mode: str, content: str) -> str:
    schema_text = _SCHEMA_IN_PROMPT_INSTRUCTION + json.dumps(
        StructuredInterpretation.model_json_schema()
    )
    schema_content: str | list[dict[str, str]] = schema_text
    if mode == "cache_block":
        schema_content = [{"type": "text", "text": schema_text}]
    messages: list[dict[str, Any]] = [{"role": "user", "content": content}]
    if mode != "native":
        messages.insert(0, {"role": "system", "content": schema_content})
    payload: dict[str, Any] = {"messages": messages}
    if mode == "native":
        payload["response_format"] = {"type": "json_schema"}
    request = httpx.Request(
        "POST", "https://openrouter.ai/api/v1/chat/completions", json=payload
    )
    response = ConcreteTrajectoryRuntime._typed_provider_response(request)
    return response.json()["choices"][0]["message"]["content"]


@pytest.mark.parametrize("mode", ["native", "prompt_text", "cache_block"])
def test_trajectory_provider_recognizes_complete_typed_transport(mode: str) -> None:
    typed = StructuredInterpretation(
        intent="conversation_followup",
        task_relation="new_task",
        user_goal_summary="Test a supplied interpretation.",
    ).model_dump_json()
    assert _typed_transport_content(mode, typed) == typed


def test_trajectory_provider_rejects_wrong_schema_and_malformed_typed_output() -> None:
    typed = StructuredInterpretation(
        intent="conversation_followup",
        task_relation="new_task",
        user_goal_summary="Test a supplied interpretation.",
    ).model_dump_json()
    wrong = _SCHEMA_IN_PROMPT_INSTRUCTION + json.dumps({"type": "object"})
    request = httpx.Request(
        "POST",
        "https://openrouter.ai/api/v1/chat/completions",
        json={
            "messages": [
                {"role": "system", "content": wrong},
                {"role": "user", "content": typed},
            ]
        },
    )
    fallback = ConcreteTrajectoryRuntime._typed_provider_response(request)
    assert fallback.json()["choices"][0]["message"]["content"] != typed
    for mode in ("native", "prompt_text", "cache_block"):
        with pytest.raises(ValidationError):
            _typed_transport_content(mode, "not-json")


EXPECTED_ALPHA_LABELS = {f"alpha_session_{index:02d}" for index in range(1, 8)}
ISSUE_LABELS = {
    "#238": "alpha_session_01",
    "#239": "alpha_session_02",
    "#251": "alpha_session_04",
    "#242": "alpha_session_05",
    "#230": "alpha_session_06",
    "#240": "alpha_session_07",
}
EXPECTED_UNRESOLVED_ISSUES = {"#239"}
EXPECTED_OPERATIONS = {
    "stream",
    "action",
    "disconnect",
    "reload",
    "retry",
    "persistence",
}


def test_concrete_trajectory_adapters_observe_the_integrated_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with ConcreteTrajectoryRuntime(monkeypatch=monkeypatch) as runtime:
        results = {
            trajectory.label: run_alpha_trajectory(
                trajectory=trajectory,
                adapters=runtime.adapters,
            )
            for trajectory in load_alpha_trajectories()
        }

    assert {label: result.status for label, result in results.items()} == {
        "alpha_session_01": "passed",
        "alpha_session_02": "expected_failed",
        "alpha_session_03": "passed",
        "alpha_session_04": "passed",
        "alpha_session_05": "passed",
        "alpha_session_06": "passed",
        "alpha_session_07": "passed",
    }
    assert all(
        result.failed_checks
        for label, result in results.items()
        if label == "alpha_session_02"
    )


def test_concrete_effective_window_trajectory_passes_unmasked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trajectory = _trajectory_for_issue("#251")
    assert trajectory.expected_fail is None

    with ConcreteTrajectoryRuntime(monkeypatch=monkeypatch) as runtime:
        result = run_alpha_trajectory(
            trajectory=trajectory,
            adapters=runtime.adapters,
        )

    assert result.status == "passed", result.failed_checks
    assert result.failed_checks == ()


def test_concrete_discovery_recovery_trajectory_passes_unmasked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trajectory = _trajectory_for_label("alpha_session_03")
    assert trajectory.expected_fail is None

    with ConcreteTrajectoryRuntime(monkeypatch=monkeypatch) as runtime:
        result = run_alpha_trajectory(
            trajectory=trajectory,
            adapters=runtime.adapters,
        )

    assert result.status == "passed", result.failed_checks
    assert result.failed_checks == ()


def test_concrete_effective_window_requires_durable_coverage_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trajectory = _trajectory_for_issue("#251")
    with ConcreteTrajectoryRuntime(monkeypatch=monkeypatch) as runtime:
        for step in trajectory.steps[:2]:
            runtime.adapters.for_operation(step.operation)(
                trajectory=trajectory,
                step=step,
                history=(),
            )
        state = runtime._state(trajectory)
        confirmation_alias = "alpha_session_04:confirmation:1"
        raw_confirmation_id = state.raw_artifact_ids[confirmation_alias]
        confirmation = next(
            message
            for message in api_state.store.messages[state.conversation_id]
            if message.role == "assistant"
            and message.metadata.get("confirmation_card", {}).get("confirmation_id")
            == raw_confirmation_id
        )
        confirmation.metadata["confirmation_payload"]["launch_payload"].pop(
            "coverage_preflight"
        )

        observation = runtime.persistence(
            trajectory=trajectory,
            step=trajectory.steps[2],
            history=(),
        )

    assert observation.persistence_state is None
    assert observation.checkpoints["effective_window.durable"] is False


def test_concrete_effective_window_rejects_mismatched_preflight_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trajectory = _trajectory_for_issue("#251")
    with ConcreteTrajectoryRuntime(monkeypatch=monkeypatch) as runtime:
        for step in trajectory.steps[:2]:
            runtime.adapters.for_operation(step.operation)(
                trajectory=trajectory,
                step=step,
                history=(),
            )
        state = runtime._state(trajectory)
        job = runtime._job_for_confirmation(
            state=state,
            confirmation_alias="alpha_session_04:confirmation:1",
        )
        assert job is not None
        job["launch_payload"]["request"]["coverage_preflight"]["preflight_id"] = (
            "different-prepared-dataset"
        )

        observation = runtime.persistence(
            trajectory=trajectory,
            step=trajectory.steps[2],
            history=(),
        )

    assert observation.persistence_state is None
    assert observation.checkpoints["effective_window.durable"] is False


def test_concrete_effective_window_completion_rejects_mismatched_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trajectory = _trajectory_for_issue("#251")
    with ConcreteTrajectoryRuntime(monkeypatch=monkeypatch) as runtime:
        runtime.stream(trajectory=trajectory, step=trajectory.steps[0], history=())
        state = runtime._state(trajectory)
        confirmation_alias = "alpha_session_04:confirmation:1"
        raw_confirmation_id = state.raw_artifact_ids[confirmation_alias]
        confirmation = next(
            message
            for message in api_state.store.messages[state.conversation_id]
            if message.role == "assistant"
            and message.metadata.get("confirmation_card", {}).get("confirmation_id")
            == raw_confirmation_id
        )
        confirmation.metadata["confirmation_payload"]["launch_payload"][
            "coverage_preflight"
        ]["preflight_id"] = "different-prepared-dataset"

        observation = runtime.action(
            trajectory=trajectory,
            step=trajectory.steps[1],
            history=(),
        )
        job = runtime._job_for_confirmation(
            state=state,
            confirmation_alias=confirmation_alias,
        )
        assert job is not None
        assert job["status"] == "failed"
        assert job["failure_code"] == "approved_data_window_unavailable"
        assert job["result_run_id"] is None
        assert runtime._run_for_job(job) is None
        assert api_state.store.evidence_artifacts == {}

    assert (
        observation.checkpoints["effective_window.completed_result_matches_approval"]
        is False
    )
    assert observation.checkpoints["effective_window.result_surfaces_complete"] is False


def test_concrete_reload_cannot_pass_from_cached_alias_when_persistence_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trajectory = _trajectory_for_issue("#239")
    with ConcreteTrajectoryRuntime(monkeypatch=monkeypatch) as runtime:
        runtime.stream(trajectory=trajectory, step=trajectory.steps[0], history=())
        state = runtime._state(trajectory)
        api_state.store.messages[state.conversation_id] = []

        observation = runtime.reload(
            trajectory=trajectory,
            step=trajectory.steps[3],
            history=(),
        )

    assert observation.artifact_identity is None
    assert observation.reload_state is None


def test_concrete_stream_fails_closed_when_route_fingerprint_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import agent as agent_router

    trajectory = _trajectory_for_issue("#239")
    monkeypatch.setattr(
        agent_router,
        "turn_execution_summary",
        lambda _receipts: {
            "input_fingerprint": None,
            "output_fingerprint": None,
        },
    )
    with ConcreteTrajectoryRuntime(monkeypatch=monkeypatch) as runtime:
        with pytest.raises(
            AssertionError,
            match="persisted route execution fingerprint",
        ):
            runtime.stream(
                trajectory=trajectory,
                step=trajectory.steps[0],
                history=(),
            )


def test_run_disconnect_submits_once_through_the_real_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trajectory = _trajectory_for_issue("#242")
    with ConcreteTrajectoryRuntime(monkeypatch=monkeypatch) as runtime:
        runtime.stream(trajectory=trajectory, step=trajectory.steps[0], history=())
        state = runtime._state(trajectory)
        before_count = len(api_state.store.messages[state.conversation_id])

        observation = runtime.disconnect(
            trajectory=trajectory,
            step=trajectory.steps[1],
            history=(),
        )

        submitted_actions = [
            message
            for message in api_state.store.messages[state.conversation_id][before_count:]
            if message.role == "user"
            and message.metadata.get("chat_action", {}).get("type") == "run_backtest"
        ]
        jobs = [
            job
            for job in api_state.store.backtest_jobs.values()
            if job.get("conversation_id") == state.conversation_id
        ]

    assert observation.typed_terminal is False
    assert len(submitted_actions) == 1
    assert len(jobs) == 1


def test_run_replay_after_message_persistence_404_keeps_one_action_and_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.chat.request_admission import ChatRequestAdmission

    from tests.evals.chat_runtime_trajectory_adapters import _TransportCut

    trajectory = _trajectory_for_issue("#242")
    with ConcreteTrajectoryRuntime(monkeypatch=monkeypatch) as runtime:
        runtime.stream(trajectory=trajectory, step=trajectory.steps[0], history=())
        state = runtime._state(trajectory)
        raw_confirmation_id = state.raw_artifact_ids["alpha_session_05:confirmation:1"]
        action = deepcopy(trajectory.steps[1].request["submission"]["request"]["action"])
        action.update(
            label="Run backtest",
            presentation="confirmation",
            payload={"confirmation_id": raw_confirmation_id},
        )
        request = {
            "conversation_id": state.conversation_id,
            "language": trajectory.locale,
            "action": action,
        }
        headers = {"Idempotency-Key": raw_confirmation_id}
        original_persist = ChatRequestAdmission.persist

        def persist_then_disconnect(admission: ChatRequestAdmission):
            message = original_persist(admission)
            if admission.owner == "message_only":
                raise _TransportCut("after_action_message_persistence")
            return message

        with monkeypatch.context() as cut:
            cut.setattr(ChatRequestAdmission, "persist", persist_then_disconnect)
            try:
                runtime._http.post(
                    "/api/v1/chat/stream",
                    headers=headers,
                    json=request,
                )
            except BaseException as exc:
                assert runtime._contains_transport_cut(exc)
            else:
                raise AssertionError("action transport cut did not fire")

        run_actions_before = [
            message
            for message in api_state.store.messages[state.conversation_id]
            if message.role == "user"
            and message.metadata.get("chat_action", {}).get("type") == "run_backtest"
        ]
        assert len(run_actions_before) == 1
        assert api_state.store.backtest_jobs == {}
        assert api_state.store.backtest_job_reservations == {}
        assert all(key[1] != "backtest_runs" for key in api_state.store.usage_counters)

        with monkeypatch.context() as lookup_patch:
            lookup_patch.setattr(
                api_state,
                "supabase_gateway",
                runtime._backtest_gateway,
            )
            lookup = runtime._http.get(
                f"/api/v1/backtest-jobs/by-action/{raw_confirmation_id}"
            )
        assert lookup.status_code == 404

        admission_calls: list[dict[str, Any]] = []
        original_admit = runtime._backtest_gateway.admit_backtest_job

        def counted_admit(**kwargs: Any) -> dict[str, Any]:
            admission_calls.append(kwargs)
            return original_admit(**kwargs)

        monkeypatch.setattr(
            runtime._backtest_gateway,
            "admit_backtest_job",
            counted_admit,
        )
        replay = runtime._http.post(
            "/api/v1/chat/stream",
            headers=headers,
            json=request,
        )
        replay.raise_for_status()
        reload_response = runtime._http.get(
            f"/api/v1/conversations/{state.conversation_id}/messages"
        )
        reload_response.raise_for_status()

        run_actions_after = [
            message
            for message in api_state.store.messages[state.conversation_id]
            if message.role == "user"
            and message.metadata.get("chat_action", {}).get("type") == "run_backtest"
        ]
        reloaded_run_actions = [
            message
            for message in reload_response.json()["items"]
            if message["role"] == "user"
            and message["metadata"].get("chat_action", {}).get("type") == "run_backtest"
        ]
        jobs = [
            job
            for job in api_state.store.backtest_jobs.values()
            if job.get("conversation_id") == state.conversation_id
        ]

    assert [message.id for message in run_actions_after] == [run_actions_before[0].id]
    assert [message["id"] for message in reloaded_run_actions] == [
        run_actions_before[0].id
    ]
    assert len(admission_calls) == 1
    assert len(jobs) == 1
    assert len(api_state.store.backtest_job_reservations) == 1
    assert {
        int(row.get("used_count", 0))
        for key, row in api_state.store.usage_counters.items()
        if key[1] == "backtest_runs"
    } == {1}
    assert api_state.store.backtest_runs == {}
    assert api_state.store.backtest_finalizations == {}


def test_direct_job_bypass_cannot_satisfy_persisted_trajectory_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trajectory = _trajectory_for_issue("#242")
    with ConcreteTrajectoryRuntime(monkeypatch=monkeypatch) as runtime:
        runtime.stream(trajectory=trajectory, step=trajectory.steps[0], history=())
        state = runtime._state(trajectory)
        confirmation_alias = "alpha_session_05:confirmation:1"
        raw_confirmation_id = state.raw_artifact_ids[confirmation_alias]
        confirmation_message = next(
            message
            for message in api_state.store.messages[state.conversation_id]
            if message.role == "assistant"
            and message.metadata.get("confirmation_card", {}).get("confirmation_id")
            == raw_confirmation_id
        )
        raw_job_id = "direct-bypass-job"
        job_alias = "alpha_session_05:job:1"
        api_state.store.backtest_jobs[raw_job_id] = {
            "id": raw_job_id,
            "conversation_id": state.conversation_id,
            "idempotency_key": raw_confirmation_id,
            "confirmation_message_id": confirmation_message.id,
            "created_at": "9999-12-31T00:00:00+00:00",
        }
        state.artifact_aliases[raw_job_id] = job_alias
        state.raw_artifact_ids[job_alias] = raw_job_id

        observation = runtime.persistence(
            trajectory=trajectory,
            step=trajectory.steps[-1],
            history=(),
        )

    assert observation.artifact_identity == confirmation_alias
    assert observation.artifact_identity != job_alias


def test_concrete_expected_fail_masks_exactly_match_observed_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with ConcreteTrajectoryRuntime(monkeypatch=monkeypatch) as runtime:
        results = {
            trajectory.label: (
                trajectory,
                run_alpha_trajectory(
                    trajectory=trajectory,
                    adapters=runtime.adapters,
                ),
            )
            for trajectory in load_alpha_trajectories()
            if trajectory.expected_fail is not None
        }

    for trajectory, result in results.values():
        assert trajectory.expected_fail is not None
        configured = {
            (allowed.step_id, allowed.prefix)
            for allowed in trajectory.expected_fail.allowed_failures
        }
        observed = {
            (step_result.step_id, f"{failure.split(':', 1)[0]}:")
            for step_result in result.step_results
            for failure in step_result.failed_checks
        }
        assert configured == observed, trajectory.label


def test_concrete_persistence_counts_injected_stale_job_owner_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trajectory = next(
        item for item in load_alpha_trajectories() if item.label == "alpha_session_01"
    )
    with ConcreteTrajectoryRuntime(monkeypatch=monkeypatch) as runtime:
        for step in trajectory.steps[:3]:
            runtime.adapters.for_operation(step.operation)(
                trajectory=trajectory,
                step=step,
                history=(),
            )
        state = runtime._state(trajectory)
        old_confirmation = state.raw_artifact_ids["alpha_session_01:confirmation:1"]
        api_state.store.backtest_jobs["injected-stale-job"] = {
            "id": "injected-stale-job",
            "conversation_id": state.conversation_id,
            "idempotency_key": old_confirmation,
        }

        observation = runtime.persistence(
            trajectory=trajectory,
            step=trajectory.steps[3],
            history=(),
        )

    assert observation.checkpoints["stale_action.persisted_execution_count"] == 1


def test_concrete_persistence_counts_repeated_terminal_fingerprint_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trajectory = _trajectory_for_issue("#239")
    with ConcreteTrajectoryRuntime(monkeypatch=monkeypatch) as runtime:
        for step in trajectory.steps[:2]:
            runtime.adapters.for_operation(step.operation)(
                trajectory=trajectory,
                step=step,
                history=(),
            )
        state = runtime._state(trajectory)
        evidence = runtime._persisted_route_evidence[state.conversation_id]
        evidence.append(deepcopy(evidence[-1]))

        observation = runtime.persistence(
            trajectory=trajectory,
            step=trajectory.steps[2],
            history=(),
        )

    assert observation.checkpoints["terminal.repeated_fingerprint_count"] == 1


def test_concrete_persistence_counts_duplicate_lifecycle_identity_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trajectory = _trajectory_for_issue("#240")
    with ConcreteTrajectoryRuntime(monkeypatch=monkeypatch) as runtime:
        runtime.stream(trajectory=trajectory, step=trajectory.steps[0], history=())
        runtime.disconnect(
            trajectory=trajectory,
            step=trajectory.steps[1],
            history=(),
        )
        state = runtime._state(trajectory)
        assert state.disconnected_turn_id is not None
        original = api_state.store.chat_turn_lifecycles[state.disconnected_turn_id]
        original_message = next(
            message
            for message in api_state.store.messages[state.conversation_id]
            if message.id == state.disconnected_turn_id
        )
        duplicate_turn_id = "injected-duplicate-turn"
        api_state.store.messages[state.conversation_id].append(
            original_message.model_copy(update={"id": duplicate_turn_id})
        )
        api_state.store.chat_turn_lifecycles[duplicate_turn_id] = {
            **original,
            "turn_id": duplicate_turn_id,
        }

        observation = runtime.persistence(
            trajectory=trajectory,
            step=trajectory.steps[2],
            history=(),
        )

    assert observation.checkpoints["persistence.durable_identity_count"] == 2


def test_abandoned_retry_uses_projected_authority_and_creates_one_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trajectory = _trajectory_for_issue("#240")
    with ConcreteTrajectoryRuntime(monkeypatch=monkeypatch) as runtime:
        for step in trajectory.steps[:4]:
            runtime.adapters.for_operation(step.operation)(
                trajectory=trajectory,
                step=step,
                history=(),
            )
        state = runtime._state(trajectory)
        before_lifecycles = len(
            [
                row
                for row in api_state.store.chat_turn_lifecycles.values()
                if row["conversation_id"] == state.conversation_id
            ]
        )
        observation = runtime.retry(
            trajectory=trajectory,
            step=trajectory.steps[4],
            history=(),
        )
        after_rows = [
            row
            for row in api_state.store.chat_turn_lifecycles.values()
            if row["conversation_id"] == state.conversation_id
        ]
        persisted_requests = [
            message
            for message in api_state.store.messages[state.conversation_id]
            if message.role == "user"
            and message.content == "Change the active test to the last six months."
        ]

    assert len(after_rows) == before_lifecycles + 1
    assert len(persisted_requests) == 2
    assert observation.checkpoints == {
        "retry_last_turn.request_message_id": "alpha_session_07:turn:1",
        "orphan_turn.duplicate_turn_count": 0,
        "terminal.artifact_identity": "alpha_session_07:confirmation:2",
    }


def test_abandoned_retry_reports_injected_duplicate_attempt_owner_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trajectory = _trajectory_for_issue("#240")
    with ConcreteTrajectoryRuntime(monkeypatch=monkeypatch) as runtime:
        for step in trajectory.steps[:4]:
            runtime.adapters.for_operation(step.operation)(
                trajectory=trajectory,
                step=step,
                history=(),
            )
        state = runtime._state(trajectory)
        submit_stream = runtime._submit_stream

        def _submit_with_duplicate_owner(**kwargs: Any):
            result = submit_stream(**kwargs)
            retry_rows = [
                row
                for row in runtime._matching_lifecycle_rows(state=state)
                if row["turn_id"] != state.disconnected_turn_id
            ]
            assert len(retry_rows) == 1
            retry_row = retry_rows[0]
            retry_message = next(
                message
                for message in api_state.store.messages[state.conversation_id]
                if message.id == retry_row["turn_id"]
            )
            duplicate_turn_id = "injected-duplicate-retry"
            api_state.store.messages[state.conversation_id].append(
                retry_message.model_copy(update={"id": duplicate_turn_id})
            )
            api_state.store.chat_turn_lifecycles[duplicate_turn_id] = {
                **retry_row,
                "turn_id": duplicate_turn_id,
                "request_id": "injected-duplicate-request",
            }
            return result

        monkeypatch.setattr(runtime, "_submit_stream", _submit_with_duplicate_owner)
        observation = runtime.retry(
            trajectory=trajectory,
            step=trajectory.steps[4],
            history=(),
        )

    assert observation.checkpoints["orphan_turn.duplicate_turn_count"] == 1


def test_abandoned_retry_rejects_a_fixture_identity_without_projected_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trajectory = _trajectory_for_issue("#240")
    retry_step = replace(
        trajectory.steps[4],
        request={
            "action": {
                "type": "retry_last_turn",
                "payload": {"request_message_id": "alpha_session_07:turn:other"},
            }
        },
    )
    with ConcreteTrajectoryRuntime(monkeypatch=monkeypatch) as runtime:
        for step in trajectory.steps[:4]:
            runtime.adapters.for_operation(step.operation)(
                trajectory=trajectory,
                step=step,
                history=(),
            )

        with pytest.raises(
            AssertionError,
            match="projected retry authority",
        ):
            runtime.retry(
                trajectory=trajectory,
                step=retry_step,
                history=(),
            )


def _matching_observation(step: Any) -> StepObservation:
    expectation = step.expectation
    raw_sse = None
    if expectation.canonical_sse:
        outcome = expectation.stage_outcome or "ready_to_respond"
        raw_sse = "\n\n".join(
            [
                'data: {"type":"stage_start","stage":"interpret"}',
                f'data: {{"type":"stage_outcome","outcome":"{outcome}"}}',
                f'data: {{"type":"final","payload":{{"stage_outcome":"{outcome}"}}}}',
                "data: [DONE]",
            ]
        )
    route_receipts: tuple[dict[str, Any], ...] = ()
    if expectation.route_budget is not None:
        route_receipts = (
            {
                "task": "interpretation",
                "latency_ms": min(expectation.route_budget.max_latency_ms or 1, 100),
                "usage_cost_usd": min(
                    expectation.route_budget.max_cost_usd or 0.0,
                    0.001,
                ),
            },
        )
    return StepObservation(
        raw_sse=raw_sse,
        visible_response_category=expectation.visible_response_category,
        stage_outcome=expectation.stage_outcome,
        artifact_identity=expectation.artifact_identity,
        action_identity=expectation.action_identity,
        persistence_state=expectation.persistence_state,
        reload_state=expectation.reload_state,
        recovery_code=expectation.recovery_code,
        route_receipts=route_receipts,
        typed_terminal=expectation.typed_terminal,
        fingerprint=step.step_id,
        checkpoints=dict(expectation.checkpoints),
    )


def _recording_adapters(
    calls: list[tuple[str, str]],
    *,
    overrides: dict[str, StepObservation] | None = None,
) -> TrajectoryAdapters:
    resolved_overrides = overrides or {}

    def handler(*, trajectory: Any, step: Any, history: Any) -> StepObservation:
        del trajectory, history
        calls.append((step.operation, step.step_id))
        return resolved_overrides.get(step.step_id, _matching_observation(step))

    return TrajectoryAdapters(
        stream=handler,
        action=handler,
        disconnect=handler,
        reload=handler,
        retry=handler,
        persistence=handler,
    )


def _trajectory_for_issue(issue: str) -> Any:
    return next(
        trajectory
        for trajectory in load_alpha_trajectories()
        if trajectory.label == ISSUE_LABELS[issue]
    )


def _trajectory_for_label(label: str) -> Any:
    return next(
        trajectory
        for trajectory in load_alpha_trajectories()
        if trajectory.label == label
    )


def _run_action_envelopes(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [envelope for item in value for envelope in _run_action_envelopes(item)]
    if not isinstance(value, dict):
        return []

    action = value.get("action")
    envelopes = (
        [value]
        if isinstance(action, dict) and action.get("type") == "run_backtest"
        else []
    )
    return envelopes + [
        envelope
        for key, item in value.items()
        if key != "action"
        for envelope in _run_action_envelopes(item)
    ]


def test_alpha_trajectory_fixtures_are_complete_sanitized_and_issue_tagged() -> None:
    raw = ALPHA_TRAJECTORY_PATH.read_text(encoding="utf-8")
    trajectories = load_alpha_trajectories()

    assert {trajectory.label for trajectory in trajectories} == EXPECTED_ALPHA_LABELS
    assert {trajectory.locale for trajectory in trajectories} == {"en", "es-419"}
    assert {
        trajectory.expected_fail.issue
        for trajectory in trajectories
        if trajectory.expected_fail is not None
    } == EXPECTED_UNRESOLVED_ISSUES
    assert {
        step.operation for trajectory in trajectories for step in trajectory.steps
    } == EXPECTED_OPERATIONS

    covered_expectations = {
        key
        for trajectory in trajectories
        for step in trajectory.steps
        for key, value in step.expectation.as_dict().items()
        if value not in (None, {}, ())
    }
    assert {
        "visible_response_category",
        "stage_outcome",
        "canonical_sse",
        "artifact_identity",
        "action_identity",
        "persistence_state",
        "reload_state",
        "recovery_code",
        "route_budget",
        "typed_terminal",
        "checkpoints",
    }.issubset(covered_expectations)

    for trajectory in trajectories:
        assert trajectory.purpose
        assert len(trajectory.steps) >= 3
        if trajectory.expected_fail is not None:
            assert trajectory.expected_fail.reason
            assert trajectory.expected_fail.allowed_failures
            assert re.fullmatch(r"#\d+", trajectory.expected_fail.issue)
            assert all(
                allowed_failure.step_id.startswith(f"{trajectory.label}:step:")
                and allowed_failure.prefix.endswith(":")
                for allowed_failure in trajectory.expected_fail.allowed_failures
            )
        assert [step.index for step in trajectory.steps] == list(
            range(1, len(trajectory.steps) + 1)
        )
        assert all(
            step.step_id.startswith(f"{trajectory.label}:step:")
            for step in trajectory.steps
        )

    data_window = _trajectory_for_issue("#251")
    assert "retail" in data_window.tags
    assert data_window.expected_fail is None
    assert {
        checkpoint
        for step in data_window.steps
        for checkpoint in step.expectation.checkpoints
        if checkpoint.startswith("effective_window.")
    } == {
        "effective_window.requested_start",
        "effective_window.source",
        "effective_window.visible_before_approval",
        "effective_window.execution_matches_approval",
        "effective_window.completed_result_matches_approval",
        "effective_window.result_surfaces_complete",
        "effective_window.durable",
        "effective_window.completed_result_durable",
        "effective_window.reload_matches_approval",
        "effective_window.completed_result_reloads",
    }

    orphan_reconciliation = _trajectory_for_issue("#240")
    assert orphan_reconciliation.steps[0].request == {
        "message": "Backtest holding MSFT for the past year."
    }
    assert (
        orphan_reconciliation.steps[0].expectation.artifact_identity
        == "alpha_session_07:confirmation:1"
    )
    assert orphan_reconciliation.steps[1].request["submission"] == {
        "operation": "stream",
        "identity": "alpha_session_07:turn:1",
        "request": {"message": "Change the active test to the last six months."},
    }

    assert (
        re.search(
            r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b",
            raw,
        )
        is None
    )
    assert re.search(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b", raw) is None
    assert not any(
        forbidden_key in raw
        for forbidden_key in (
            "raw_conversation_id",
            "source_conversation_id",
            "provider_secret",
            "api_key",
            "access_token",
        )
    )
    assert '"artifact":' not in raw
    assert '"idempotency_label":' not in raw


def test_disconnect_fixtures_own_the_submission_before_client_terminal() -> None:
    disconnect_steps = [
        step
        for trajectory in load_alpha_trajectories()
        for step in trajectory.steps
        if step.operation == "disconnect"
    ]

    assert disconnect_steps
    for step in disconnect_steps:
        submission = step.request.get("submission")
        assert isinstance(submission, dict)
        assert submission.get("operation") in {"stream", "action"}
        assert isinstance(submission.get("identity"), str)
        assert submission["identity"]
        assert isinstance(submission.get("request"), dict)
        assert "after" not in step.request
        assert step.expectation.typed_terminal is False


def test_run_actions_use_confirmation_id_as_the_exact_idempotency_identity() -> None:
    run_action_steps: list[tuple[Any, dict[str, Any]]] = []

    for trajectory in load_alpha_trajectories():
        for step in trajectory.steps:
            action_identity = step.expectation.action_identity
            if action_identity is not None:
                assert re.fullmatch(
                    rf"{trajectory.label}:confirmation:\d+",
                    action_identity,
                )
                if ":confirmation:" in (step.expectation.artifact_identity or ""):
                    assert action_identity == step.expectation.artifact_identity

            run_action_steps.extend(
                (step, envelope) for envelope in _run_action_envelopes(step.request)
            )

    assert run_action_steps
    for step, envelope in run_action_steps:
        action = envelope["action"]
        confirmation_id = action["payload"]["confirmation_id"]
        assert envelope["headers"] == {"Idempotency-Key": confirmation_id}
        assert step.expectation.action_identity == confirmation_id

        if step.operation == "disconnect":
            assert step.request["submission"]["identity"] == confirmation_id


def test_ambiguous_run_reconciles_by_action_without_replay() -> None:
    trajectory = _trajectory_for_issue("#242")
    confirmation_id = "alpha_session_05:confirmation:1"
    lookup_path = f"/api/v1/backtest-jobs/by-action/{confirmation_id}"
    lookup_step = trajectory.steps[2]

    assert lookup_step.operation == "reload"
    assert lookup_step.request == {
        "method": "GET",
        "path": lookup_path,
    }
    assert lookup_step.expectation.reload_state == "found"
    assert lookup_step.expectation.artifact_identity == "alpha_session_05:job:1"
    assert lookup_step.expectation.action_identity == confirmation_id
    assert lookup_step.expectation.checkpoints == {
        "by_action.lookup_status": 200,
        "by_action.replay_allowed": False,
        "admission.execution_count": 1,
    }
    assert all(step.operation != "retry" for step in trajectory.steps)


def test_abandoned_turn_projects_terminal_recovery_and_keyed_retry() -> None:
    trajectory = _trajectory_for_issue("#240")
    turn_id = "alpha_session_07:turn:1"
    request_id = "alpha_session_07:request:1"
    interrupted_message = "Change the active test to the last six months."
    disconnect_step = trajectory.steps[1]
    persistence_step = trajectory.steps[2]
    reload_step = trajectory.steps[3]
    retry_step = trajectory.steps[4]

    assert disconnect_step.request["submission"] == {
        "operation": "stream",
        "identity": turn_id,
        "request": {"message": interrupted_message},
    }
    assert disconnect_step.expectation.persistence_state == "accepted"
    assert persistence_step.expectation.persistence_state == "accepted"

    assert reload_step.expectation.reload_state == "abandoned"
    assert reload_step.expectation.recovery_code == "turn_abandoned"
    assert reload_step.expectation.typed_terminal is True
    assert reload_step.expectation.checkpoints == {
        "agent_runtime_turn.turn_id": turn_id,
        "agent_runtime_turn.request_id": request_id,
        "agent_runtime_turn.status": "abandoned",
        "agent_runtime_turn.terminal": True,
        "agent_runtime_turn.reconciled_outcome": None,
        "agent_runtime_turn.failure_code": "turn_abandoned",
        "agent_runtime_turn.retryable": True,
        "recovery.code": "turn_abandoned",
        "recovery.retryable": True,
        "retry_last_turn.request_message_id": turn_id,
        "retry_last_turn.message": interrupted_message,
        "orphan_turn.after_window_count": 0,
    }

    assert retry_step.request == {
        "action": {
            "type": "retry_last_turn",
            "payload": {"request_message_id": turn_id},
        }
    }
    assert retry_step.expectation.checkpoints["retry_last_turn.request_message_id"] == (
        turn_id
    )


def test_unapproved_recovery_codes_and_reload_states_are_not_fixtures() -> None:
    raw = ALPHA_TRAJECTORY_PATH.read_text(encoding="utf-8")
    assert "runtime_budget_exhausted" not in raw
    assert "asset_discovery_unavailable" not in raw

    trajectories = [_trajectory_for_issue("#239")]
    for trajectory in trajectories:
        for step in trajectory.steps:
            assert step.expectation.recovery_code is None
            if step.operation in {"persistence", "reload"}:
                assert step.expectation.persistence_state is None
                assert step.expectation.reload_state is None

    budget_retry = _trajectory_for_issue("#239").steps[1]
    assert budget_retry.expectation.visible_response_category == "typed_recovery"
    assert budget_retry.expectation.stage_outcome == "ready_to_respond"

    discovery_recovery = _trajectory_for_label("alpha_session_03").steps[0]
    assert discovery_recovery.expectation.visible_response_category == "typed_recovery"
    assert discovery_recovery.expectation.stage_outcome == "ready_to_respond"
    assert discovery_recovery.expectation.recovery_code == "discovery_unavailable"
    assert discovery_recovery.expectation.route_budget is not None
    assert discovery_recovery.expectation.route_budget.max_calls == 1
    assert discovery_recovery.expectation.checkpoints == {
        "discovery.route_receipt_count": 1
    }

    orphan_recovery = _trajectory_for_issue("#240").steps[3]
    assert orphan_recovery.expectation.reload_state == "abandoned"
    assert orphan_recovery.expectation.recovery_code == "turn_abandoned"
    assert orphan_recovery.expectation.typed_terminal is True


def test_expected_fail_prefixes_are_emitted_by_the_trajectory_contract() -> None:
    direct_expectation_prefixes = {
        "visible_response_category": "visible_response:",
        "stage_outcome": "stage_outcome:",
        "artifact_identity": "artifact_identity:",
        "action_identity": "action_identity:",
        "persistence_state": "persistence:",
        "reload_state": "reload:",
        "recovery_code": "recovery:",
        "typed_terminal": "terminal:",
    }

    for trajectory in load_alpha_trajectories():
        if trajectory.expected_fail is None:
            continue
        supported_by_step: dict[str, set[str]] = {}
        for step in trajectory.steps:
            supported = {"stale_action:", "orphan_turn:", "fingerprint:"}
            expectation = step.expectation
            for field_name, prefix in direct_expectation_prefixes.items():
                if getattr(expectation, field_name) is not None:
                    supported.add(prefix)
            if expectation.canonical_sse:
                supported.add("sse:")
            if expectation.route_budget is not None:
                supported.update({"budget.calls:", "budget.cost:", "budget.latency:"})
            supported.update(
                f"{checkpoint.split('.', 1)[0]}:"
                for checkpoint in expectation.checkpoints
            )
            supported_by_step[step.step_id] = supported

        masks = {
            (allowed_failure.step_id, allowed_failure.prefix)
            for allowed_failure in trajectory.expected_fail.allowed_failures
        }
        assert len(masks) == len(trajectory.expected_fail.allowed_failures)
        for allowed_failure in trajectory.expected_fail.allowed_failures:
            assert allowed_failure.step_id in supported_by_step
            assert allowed_failure.prefix in supported_by_step[allowed_failure.step_id], (
                trajectory.label,
                allowed_failure.step_id,
                allowed_failure.prefix,
            )


def test_trajectory_runner_dispatches_every_step_through_typed_adapters() -> None:
    trajectories = load_alpha_trajectories()
    calls: list[tuple[str, str]] = []
    adapters = _recording_adapters(calls)

    results = [
        run_alpha_trajectory(trajectory=trajectory, adapters=adapters)
        for trajectory in trajectories
    ]

    assert calls == [
        (step.operation, step.step_id)
        for trajectory in trajectories
        for step in trajectory.steps
    ]
    assert all(
        len(result.step_results) == len(trajectory.steps)
        for result, trajectory in zip(results, trajectories, strict=True)
    )
    assert {result.status for result in results} == {"passed", "unexpected_pass"}
    assert sum(result.status == "passed" for result in results) == 6
    assert sum(result.status == "unexpected_pass" for result in results) == 1
    assert all(result.failed_checks == () for result in results)


def test_expected_fail_allows_only_its_exact_failure_prefixes() -> None:
    trajectory = _trajectory_for_issue("#239")
    first_step = trajectory.steps[0]
    matching = _matching_observation(first_step)
    allowed_failure = replace(
        matching,
        visible_response_category="unexpected_response",
    )

    expected_failed = run_alpha_trajectory(
        trajectory=trajectory,
        adapters=_recording_adapters(
            [],
            overrides={first_step.step_id: allowed_failure},
        ),
    )
    assert expected_failed.status == "expected_failed"
    assert expected_failed.failed_checks[0].startswith("visible_response:")

    unrelated_failure = replace(
        allowed_failure,
        raw_sse='event: final\ndata: {"type":"final","payload":{}}',
    )
    failed = run_alpha_trajectory(
        trajectory=trajectory,
        adapters=_recording_adapters(
            [],
            overrides={first_step.step_id: unrelated_failure},
        ),
    )
    assert failed.status == "failed"
    assert any(check.startswith("sse:") for check in failed.failed_checks)


def test_expected_fail_does_not_mask_same_prefix_at_another_step() -> None:
    trajectory = _trajectory_for_issue("#239")
    first_step = trajectory.steps[0]
    other_step = trajectory.steps[2]
    assert any(
        allowed_failure.step_id == first_step.step_id
        and allowed_failure.prefix == "visible_response:"
        for allowed_failure in trajectory.expected_fail.allowed_failures
    )

    other_step = replace(
        other_step,
        expectation=replace(
            other_step.expectation,
            checkpoints={"terminal.repeated_fingerprint_count": 1},
        ),
    )
    trajectory = replace(
        trajectory,
        steps=(first_step, trajectory.steps[1], other_step, *trajectory.steps[3:]),
    )
    matching = _matching_observation(other_step)
    same_family_wrong_step = replace(
        matching,
        checkpoints={"terminal.repeated_fingerprint_count": 0},
    )
    result = run_alpha_trajectory(
        trajectory=trajectory,
        adapters=_recording_adapters(
            [], overrides={other_step.step_id: same_family_wrong_step}
        ),
    )

    assert result.status == "failed"
    assert any(check.startswith("terminal:") for check in result.failed_checks)


def test_runner_rejects_disconnect_after_terminal_for_same_submission() -> None:
    trajectory = _trajectory_for_issue("#242")
    terminal_step = replace(
        trajectory.steps[0],
        request={
            **trajectory.steps[0].request,
            "submission_identity": "alpha_session_05:submission:run:1",
        },
    )
    disconnect_step = replace(
        trajectory.steps[1],
        request={
            "submission": {
                "operation": "action",
                "identity": "alpha_session_05:submission:run:1",
                "request": {"type": "run_backtest"},
            }
        },
    )
    invalid_trajectory = replace(
        trajectory,
        steps=(
            terminal_step,
            disconnect_step,
            *trajectory.steps[2:],
        ),
    )

    result = run_alpha_trajectory(
        trajectory=invalid_trajectory,
        adapters=_recording_adapters([]),
    )

    assert result.status == "failed"
    assert any(check.startswith("disconnect:") for check in result.failed_checks)


def test_orphan_recovery_terminal_must_keep_the_same_durable_identity() -> None:
    trajectory = _trajectory_for_issue("#240")
    reload_step = trajectory.steps[3]
    assert reload_step.operation == "reload"
    matching = _matching_observation(reload_step)
    unrelated_terminal = replace(
        matching,
        checkpoints={
            **matching.checkpoints,
            "agent_runtime_turn.turn_id": "alpha_session_other:turn:1",
        },
    )

    result = run_alpha_trajectory(
        trajectory=trajectory,
        adapters=_recording_adapters(
            [], overrides={reload_step.step_id: unrelated_terminal}
        ),
    )

    assert result.status == "failed"
    assert any(check.startswith("agent_runtime_turn:") for check in result.failed_checks)


def test_runner_enforces_sse_budget_and_session_terminal_invariants() -> None:
    budget_trajectory = _trajectory_for_issue("#239")
    budget_step = budget_trajectory.steps[0]
    budget_observation = replace(
        _matching_observation(budget_step),
        route_receipts=tuple(
            {"task": f"call-{index}", "latency_ms": 100, "usage_cost_usd": 0.001}
            for index in range(2)
        ),
    )
    budget_result = run_alpha_trajectory(
        trajectory=replace(budget_trajectory, expected_fail=None),
        adapters=_recording_adapters(
            [], overrides={budget_step.step_id: budget_observation}
        ),
    )
    assert budget_result.status == "failed"
    assert any(check.startswith("budget.calls:") for check in budget_result.failed_checks)

    stale_trajectory = _trajectory_for_issue("#238")
    stale_step = stale_trajectory.steps[2]
    stale_observation = replace(
        _matching_observation(stale_step),
        stale_action_executions=1,
    )
    stale_result = run_alpha_trajectory(
        trajectory=stale_trajectory,
        adapters=_recording_adapters(
            [], overrides={stale_step.step_id: stale_observation}
        ),
    )
    assert stale_result.status == "failed"
    assert any(check.startswith("stale_action:") for check in stale_result.failed_checks)

    orphan_trajectory = _trajectory_for_issue("#240")
    orphan_step = orphan_trajectory.steps[3]
    orphan_observation = replace(
        _matching_observation(orphan_step),
        accepted_orphan_turns_after_window=1,
    )
    orphan_result = run_alpha_trajectory(
        trajectory=orphan_trajectory,
        adapters=_recording_adapters(
            [], overrides={orphan_step.step_id: orphan_observation}
        ),
    )
    assert orphan_result.status == "failed"
    assert any(check.startswith("orphan_turn:") for check in orphan_result.failed_checks)

    sse_trajectory = _trajectory_for_issue("#251")
    sse_step = sse_trajectory.steps[0]
    invalid_sse = replace(
        _matching_observation(sse_step),
        raw_sse='event: final\ndata: {"type":"final","payload":{}}',
    )
    sse_result = run_alpha_trajectory(
        trajectory=sse_trajectory,
        adapters=_recording_adapters([], overrides={sse_step.step_id: invalid_sse}),
    )
    assert sse_result.status == "failed"
    assert any(check.startswith("sse:") for check in sse_result.failed_checks)


def test_canonical_sse_requires_framed_stage_sequence() -> None:
    trajectory = _trajectory_for_issue("#251")
    step = trajectory.steps[0]
    matching = _matching_observation(step)

    invalid_streams = (
        # A terminal plus [DONE] is not the canonical stage lifecycle.
        'data: {"type":"final","payload":{"stage_outcome":"ready_for_confirmation"}}\n\ndata: [DONE]',
        # SSE events must be separated by a blank line.
        "\n".join(
            (
                'data: {"type":"stage_start","stage":"interpret"}',
                'data: {"type":"stage_outcome","outcome":"ready_for_confirmation"}',
                'data: {"type":"final","payload":{"stage_outcome":"ready_for_confirmation"}}',
                "data: [DONE]",
            )
        ),
        # Canonical stages cannot complete before they start.
        "\n\n".join(
            (
                'data: {"type":"stage_outcome","outcome":"ready_for_confirmation"}',
                'data: {"type":"stage_start","stage":"interpret"}',
                'data: {"type":"final","payload":{"stage_outcome":"ready_for_confirmation"}}',
                "data: [DONE]",
            )
        ),
        # A canonical stream needs exactly one typed terminal.
        "\n\n".join(
            (
                'data: {"type":"stage_start","stage":"interpret"}',
                'data: {"type":"stage_outcome","outcome":"ready_for_confirmation"}',
                "data: [DONE]",
            )
        ),
        "\n\n".join(
            (
                'data: {"type":"stage_start","stage":"interpret"}',
                'data: {"type":"stage_outcome","outcome":"ready_for_confirmation"}',
                'data: {"type":"final","payload":{"stage_outcome":"ready_for_confirmation"}}',
                'data: {"type":"final","payload":{"stage_outcome":"ready_for_confirmation"}}',
                "data: [DONE]",
            )
        ),
        # No data event may follow the typed terminal.
        "\n\n".join(
            (
                'data: {"type":"stage_start","stage":"interpret"}',
                'data: {"type":"stage_outcome","outcome":"ready_for_confirmation"}',
                'data: {"type":"final","payload":{"stage_outcome":"ready_for_confirmation"}}',
                'data: {"type":"token","content":"late"}',
                "data: [DONE]",
            )
        ),
    )

    for raw_sse in invalid_streams:
        result = run_alpha_trajectory(
            trajectory=trajectory,
            adapters=_recording_adapters(
                [],
                overrides={step.step_id: replace(matching, raw_sse=raw_sse)},
            ),
        )

        assert result.status == "failed"
        assert any(check.startswith("sse:") for check in result.failed_checks)

    valid_stream = "\n\n".join(
        (
            ": keepalive",
            "retry: 3000",
            'data: {"type":"stage_start","stage":"interpret"}',
            'data: {"type":"stage_outcome","outcome":"ready_for_confirmation"}',
            'data: {"type":"final","payload":{"stage_outcome":"ready_for_confirmation"}}',
            "data: [DONE]",
        )
    )
    valid_result = run_alpha_trajectory(
        trajectory=trajectory,
        adapters=_recording_adapters(
            [],
            overrides={step.step_id: replace(matching, raw_sse=valid_stream)},
        ),
    )

    assert not any(check.startswith("sse:") for check in valid_result.failed_checks)

    valid_error_stream = "\n\n".join(
        (
            'data: {"type":"error","code":"agent_runtime_failure","message":"Saved for retry."}',
            "data: [DONE]",
        )
    )
    valid_error_result = run_alpha_trajectory(
        trajectory=trajectory,
        adapters=_recording_adapters(
            [],
            overrides={step.step_id: replace(matching, raw_sse=valid_error_stream)},
        ),
    )

    assert not any(check.startswith("sse:") for check in valid_error_result.failed_checks)


def test_canonical_sse_rejects_invalid_event_schemas_and_unknown_types() -> None:
    trajectory = _trajectory_for_issue("#251")
    step = trajectory.steps[0]
    matching = _matching_observation(step)
    invalid_events = (
        (
            'data: {"type":"stage_start"}',
            'data: {"type":"stage_outcome","outcome":"ready_for_confirmation"}',
            'data: {"type":"final","payload":{"stage_outcome":"ready_for_confirmation"}}',
        ),
        (
            'data: {"type":"stage_start","stage":"interpret"}',
            'data: {"type":"stage_outcome"}',
            'data: {"type":"final","payload":{"stage_outcome":"ready_for_confirmation"}}',
        ),
        (
            'data: {"type":"stage_start","stage":"interpret"}',
            'data: {"type":"stage_outcome","outcome":"ready_for_confirmation"}',
            'data: {"type":"final","payload":{}}',
        ),
        (
            'data: {"type":"stage_start","stage":"interpret"}',
            'data: {"type":"bogus"}',
            'data: {"type":"stage_outcome","outcome":"ready_for_confirmation"}',
            'data: {"type":"final","payload":{"stage_outcome":"ready_for_confirmation"}}',
        ),
        (
            'data: {"type":"stage_start","stage":"bogus"}',
            'data: {"type":"stage_outcome","outcome":"ready_for_confirmation"}',
            'data: {"type":"final","payload":{"stage_outcome":"ready_for_confirmation"}}',
        ),
        (
            'data: {"type":"stage_start","stage":"interpret"}',
            'data: {"type":"stage_outcome","outcome":"bogus"}',
            'data: {"type":"final","payload":{"stage_outcome":"ready_for_confirmation"}}',
        ),
        (
            'data: {"type":"stage_start","stage":"interpret"}',
            'data: {"type":"stage_outcome","outcome":"ready_for_confirmation"}',
            'data: {"type":"final","payload":{"stage_outcome":"bogus"}}',
        ),
    )

    for event_frames in invalid_events:
        raw_sse = "\n\n".join((*event_frames, "data: [DONE]"))
        result = run_alpha_trajectory(
            trajectory=trajectory,
            adapters=_recording_adapters(
                [],
                overrides={step.step_id: replace(matching, raw_sse=raw_sse)},
            ),
        )

        assert result.status == "failed"
        assert any(check.startswith("sse:") for check in result.failed_checks)


def test_route_budget_rejects_missing_or_invalid_measurements() -> None:
    trajectory = _trajectory_for_issue("#251")
    step = trajectory.steps[0]
    malformed = replace(
        _matching_observation(step),
        route_receipts=(
            {
                "task": "interpretation",
                "latency_ms": float("nan"),
            },
        ),
    )

    result = run_alpha_trajectory(
        trajectory=trajectory,
        adapters=_recording_adapters([], overrides={step.step_id: malformed}),
    )

    assert result.status == "failed"
    prefixes = {check.split(":", 1)[0] for check in result.failed_checks}
    assert "budget.cost" in prefixes
    assert "budget.latency" in prefixes

    missing_result = run_alpha_trajectory(
        trajectory=trajectory,
        adapters=_recording_adapters(
            [],
            overrides={
                step.step_id: replace(_matching_observation(step), route_receipts=())
            },
        ),
    )

    assert missing_result.status == "failed"
    assert any(
        check.startswith("budget.calls:") for check in missing_result.failed_checks
    )


def test_trajectory_scorecard_is_privacy_safe_and_marks_unexpected_passes(
    tmp_path: Path,
) -> None:
    trajectories = load_alpha_trajectories()
    results = [
        run_alpha_trajectory(
            trajectory=trajectory,
            adapters=_recording_adapters([]),
        )
        for trajectory in trajectories
    ]

    scorecard = trajectory_scorecard_for_results(results)
    path = write_trajectory_scorecard(results, output_dir=tmp_path)
    stored = json.loads(path.read_text(encoding="utf-8"))
    serialized = json.dumps(stored, sort_keys=True)

    assert stored == scorecard | {"generated_at": stored["generated_at"]}
    assert stored["totals"] == {
        "passed": 6,
        "failed": 0,
        "expected_failed": 0,
        "unexpected_pass": 1,
    }
    assert {result["label"] for result in stored["results"]} == EXPECTED_ALPHA_LABELS
    assert all(
        set(result)
        == {
            "label",
            "locale",
            "status",
            "expected_fail_issue",
            "allowed_failures",
            "failure_prefixes",
            "steps",
        }
        for result in stored["results"]
    )
    assert all(
        set(step) == {"step_id", "operation", "failure_prefixes"}
        for result in stored["results"]
        for step in result["steps"]
    )
    assert all(
        all(set(mask) == {"step_id", "prefix"} for mask in result["allowed_failures"])
        for result in stored["results"]
    )
    for trajectory in trajectories:
        for step in trajectory.steps:
            assert all(str(value) not in serialized for value in step.request.values())
    assert "raw_sse" not in serialized
    assert "route_receipts" not in serialized
