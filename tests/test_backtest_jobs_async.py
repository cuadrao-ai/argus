from __future__ import annotations

from datetime import datetime, timezone
from threading import Event, Lock, Thread
from typing import Any

import pytest
from argus.agent_runtime.stages.execute import execute_stage
from argus.agent_runtime.state.models import RunState
from argus.api.chat.backtest_jobs import (
    BacktestJobShadowContext,
    ShadowBacktestJobTool,
    backtest_job_shadow_context,
    payload_hash,
)
from argus.api.schemas import BacktestRun, User


class _DelegateTool:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.calls: list[dict[str, object]] = []

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        self.events.append("delegate")
        self.calls.append(payload)
        return {"success": True, "payload": {"result": "in-process"}}


class _Gateway:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.jobs: list[dict[str, object]] = []
        self.metadata_updates: list[dict[str, object]] = []
        self.failure_attempts: list[dict[str, object]] = []
        self.failed_updates: list[dict[str, object]] = []

    def create_backtest_job(self, **payload: object) -> dict[str, object]:
        self.events.append("job")
        job = {
            "id": "job-async-1",
            "status": "queued",
            "result_run_id": None,
            "failure_code": None,
            "failure_detail": None,
            "retryable": False,
            "queued_at": "2026-06-06T12:00:00+00:00",
            "created_at": "2026-06-06T12:00:00+00:00",
            "updated_at": "2026-06-06T12:00:00+00:00",
            **payload,
        }
        self.jobs.append(job)
        return job

    def admit_backtest_job(self, **payload: object) -> dict[str, object]:
        payload.pop("identity_hash", None)
        payload.pop("operation_scope", None)
        payload.pop("initial_status", None)
        return {"decision": "admitted", "job": self.create_backtest_job(**payload)}

    def list_backtest_jobs(
        self,
        *,
        status: str,
        user_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        return []

    def merge_backtest_job_execution_metadata(
        self, **payload: object
    ) -> dict[str, object]:
        self.events.append("metadata")
        self.metadata_updates.append(payload)
        return {"id": payload["job_id"], **payload}

    def count_backtest_jobs(
        self,
        *,
        status: str,
        user_id: str | None = None,
        limit: int = 100,
    ) -> int:
        del status, user_id, limit
        return 0

    def get_backtest_job(
        self, *, user_id: str, job_id: str
    ) -> dict[str, object] | None:
        return next(
            (
                dict(job)
                for job in self.jobs
                if job.get("user_id") == user_id and job.get("id") == job_id
            ),
            None,
        )

    def mark_backtest_job_failed(self, **payload: object) -> dict[str, object]:
        self.failure_attempts.append(payload)
        job = self.jobs[0]
        expected_status = payload.get("expected_status")
        if expected_status is not None and job.get("status") != expected_status:
            return {}
        expected_updated_at = payload.get("expected_updated_at")
        if expected_updated_at is not None and job.get("updated_at") != expected_updated_at:
            return {}
        job.update(
            {
                "status": "failed",
                "failure_code": payload["failure_code"],
                "failure_detail": payload["failure_detail"],
                "retryable": payload["retryable"],
                "finished_at": payload.get("finished_at"),
            }
        )
        self.failed_updates.append(dict(job))
        return dict(job)


class _IdentityCaptureGateway(_Gateway):
    def __init__(self, events: list[str]) -> None:
        super().__init__(events)
        self.admission_requests: list[dict[str, object]] = []

    def admit_backtest_job(self, **payload: object) -> dict[str, object]:
        self.admission_requests.append(dict(payload))
        return super().admit_backtest_job(**payload)


class _Dispatcher:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.calls: list[dict[str, object]] = []

    def dispatch(self, **payload: object) -> dict[str, object]:
        self.events.append("dispatch")
        self.calls.append(payload)
        return {"id": "task-run-real-1", "status": "pending"}


class _MetadataFailingGateway(_Gateway):
    def merge_backtest_job_execution_metadata(
        self, **payload: object
    ) -> dict[str, object]:
        self.events.append("metadata")
        self.metadata_updates.append(payload)
        raise RuntimeError("metadata write failed")


class _FailingDispatcher(_Dispatcher):
    def __init__(
        self,
        events: list[str],
        *,
        gateway: _Gateway,
        remote_status: str | None = None,
    ) -> None:
        super().__init__(events)
        self.gateway = gateway
        self.remote_status = remote_status

    def dispatch(self, **payload: object) -> dict[str, object]:
        self.events.append("dispatch")
        self.calls.append(payload)
        if self.remote_status is not None:
            self.gateway.jobs[0]["status"] = self.remote_status
            if self.remote_status == "succeeded":
                self.gateway.jobs[0]["result_run_id"] = "run-remote-1"
        raise TimeoutError("dispatch response was lost")


class _AtomicReplayGateway(_Gateway):
    def __init__(self, events: list[str]) -> None:
        super().__init__(events)
        self._lock = Lock()
        self.admission_calls = 0
        self.allowance_reservations = 0
        self.job: dict[str, object] | None = None

    def admit_backtest_job(self, **payload: object) -> dict[str, object]:
        with self._lock:
            self.admission_calls += 1
            if self.job is not None:
                return {"decision": "replay", "job": dict(self.job)}
            self.allowance_reservations += 1
            payload.pop("initial_status", None)
            self.job = {
                "id": "job-race-1",
                "status": "queued",
                "result_run_id": None,
                "failure_code": None,
                "failure_detail": None,
                "retryable": False,
                "queued_at": "2026-06-06T12:00:00+00:00",
                "created_at": "2026-06-06T12:00:00+00:00",
                "updated_at": "2026-06-06T12:00:00+00:00",
                "execution_metadata": {},
                **payload,
            }
            self.jobs.append(self.job)
            self.events.append("job")
            return {"decision": "admitted", "job": dict(self.job)}

    def merge_backtest_job_execution_metadata(
        self, **payload: object
    ) -> dict[str, object]:
        result = super().merge_backtest_job_execution_metadata(**payload)
        with self._lock:
            assert self.job is not None
            metadata = dict(self.job.get("execution_metadata") or {})
            metadata.update(dict(payload.get("execution_metadata") or {}))
            self.job["execution_metadata"] = metadata
        return result


class _GatedDispatcher(_Dispatcher):
    def __init__(self, events: list[str]) -> None:
        super().__init__(events)
        self.first_dispatch_entered = Event()
        self.release_first_dispatch = Event()

    def dispatch(self, **payload: object) -> dict[str, object]:
        result = super().dispatch(**payload)
        if len(self.calls) == 1:
            self.first_dispatch_entered.set()
            if not self.release_first_dispatch.wait(timeout=5):
                raise AssertionError("timed out waiting to release admitted dispatch")
        return result


class _AsyncJobTool:
    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        return {
            "success": True,
            "payload": {
                "backtest_job": {
                    "id": "job-async-1",
                    "conversation_id": "conversation-1",
                    "request_message_id": "message-1",
                    "confirmation_message_id": "confirmation-message-1",
                    "status": "queued",
                    "result_run_id": None,
                    "failure_code": None,
                    "failure_detail": None,
                    "retryable": False,
                }
            },
            "error_type": None,
            "error_message": None,
            "retryable": False,
            "capability_context": {"execution_status": "queued"},
        }


class _TimedOutJobGateway:
    def __init__(self) -> None:
        self.user = User(
            id="user-1",
            email="mock@example.com",
            username=None,
            display_name="Mock Developer",
            language="en",
            locale="en-US",
            is_admin=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.job: dict[str, object] = {
            "id": "job-timeout-1",
            "conversation_id": "conversation-1",
            "request_message_id": "message-1",
            "confirmation_message_id": "confirmation-message-1",
            "status": "running",
            "result_run_id": None,
            "failure_code": None,
            "failure_detail": None,
            "retryable": False,
            "queued_at": "2026-06-06T12:00:00+00:00",
            "started_at": "2026-06-06T12:00:10+00:00",
            "finished_at": None,
            "created_at": "2026-06-06T12:00:00+00:00",
            "updated_at": "2026-06-06T12:00:10+00:00",
            "execution_metadata": {
                "workflow_dispatch": {
                    "task": "argus-backtests/run_backtest_job",
                    "task_run_id": "trn-timeout-1",
                    "status": "pending",
                    "dispatched_at": "2026-06-06T12:00:01+00:00",
                },
                "workflow_backtest": {
                    "kind": "run_backtest_job",
                    "workflow_run_id": "trn-timeout-1",
                    "started_at": "2026-06-06T12:00:10+00:00",
                },
            },
        }
        self.failed_updates: list[dict[str, object]] = []

    def get_or_create_mock_user(self) -> User:
        return self.user

    def get_backtest_job(self, *, user_id: str, job_id: str) -> dict[str, object] | None:
        if user_id != self.user.id or job_id != self.job["id"]:
            return None
        return dict(self.job)

    def get_backtest_run(self, *, user_id: str, run_id: str) -> BacktestRun | None:
        del user_id, run_id
        return None

    def mark_backtest_job_failed(self, **payload: object) -> dict[str, object]:
        self.failed_updates.append(payload)
        execution_metadata = dict(self.job.get("execution_metadata") or {})
        execution_metadata.update(dict(payload.get("execution_metadata") or {}))
        self.job.update(
            {
                "status": "failed",
                "failure_code": payload["failure_code"],
                "failure_detail": payload["failure_detail"],
                "retryable": payload["retryable"],
                "finished_at": payload.get("finished_at"),
                "execution_metadata": execution_metadata,
            }
        )
        return dict(self.job)


class _FakeTerminalTaskRunClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[str] = []

    def get_task_run(self, task_run_id: str) -> dict[str, object]:
        self.calls.append(task_run_id)
        return dict(self.payload)


class _StaleJobScanGateway:
    def __init__(self) -> None:
        self.jobs: list[dict[str, object]] = [
            {
                "id": "job-stale-running",
                "user_id": "user-1",
                "status": "running",
                "queued_at": "2026-06-06T12:00:00+00:00",
                "started_at": "2026-06-06T12:01:00+00:00",
                "updated_at": "2026-06-06T12:01:00+00:00",
                "execution_metadata": {
                    "workflow_dispatch": {"task_run_id": "trn-stale-1"}
                },
            },
            {
                "id": "job-fresh-queued",
                "user_id": "user-1",
                "status": "queued",
                "queued_at": "2026-06-06T12:28:00+00:00",
                "created_at": "2026-06-06T12:28:00+00:00",
                "updated_at": "2026-06-06T12:28:00+00:00",
                "execution_metadata": {
                    "workflow_dispatch": {"task_run_id": "trn-fresh-1"}
                },
            },
        ]
        self.failed_updates: list[dict[str, object]] = []
        self.list_calls: list[dict[str, object]] = []

    def list_backtest_jobs(
        self,
        *,
        status: str,
        user_id: str | None = None,
        limit: int = 100,
        oldest_first: bool = False,
    ) -> list[dict[str, object]]:
        self.list_calls.append(
            {
                "status": status,
                "user_id": user_id,
                "limit": limit,
                "oldest_first": oldest_first,
            }
        )
        jobs = [
            dict(job)
            for job in self.jobs
            if job.get("status") == status
            and (user_id is None or job.get("user_id") == user_id)
        ]
        return jobs[:limit]

    def mark_backtest_job_failed(self, **payload: object) -> dict[str, object]:
        self.failed_updates.append(payload)
        for job in self.jobs:
            if job["id"] == payload["job_id"]:
                if (
                    payload.get("expected_status") is not None
                    and job.get("status") != payload["expected_status"]
                ):
                    return {}
                if (
                    payload.get("expected_updated_at") is not None
                    and job.get("updated_at") != payload["expected_updated_at"]
                ):
                    return {}
                execution_metadata = dict(job.get("execution_metadata") or {})
                execution_metadata.update(dict(payload.get("execution_metadata") or {}))
                job.update(
                    {
                        "status": "failed",
                        "failure_code": payload["failure_code"],
                        "failure_detail": payload["failure_detail"],
                        "retryable": payload["retryable"],
                        "finished_at": payload.get("finished_at"),
                        "execution_metadata": execution_metadata,
                    }
                )
                return dict(job)
        raise AssertionError("unknown job")

    def get_backtest_job(
        self,
        *,
        user_id: str,
        job_id: str,
    ) -> dict[str, object] | None:
        return next(
            (
                dict(job)
                for job in self.jobs
                if job.get("user_id") == user_id and job.get("id") == job_id
            ),
            None,
        )


def _payload() -> dict[str, object]:
    return {
        "strategy_type": "buy_and_hold",
        "symbol": "AAPL",
        "symbols": ["AAPL"],
        "asset_class": "equity",
        "timeframe": "1D",
        "date_range": "past year",
        "language": "en",
    }


def _coverage_payload(
    *,
    adjustment_reason: str | None,
) -> dict[str, object]:
    requested_date_range = {"start": "2024-01-01", "end": "2024-01-05"}
    effective_date_range = {"start": "2024-01-03", "end": "2024-01-05"}
    coverage_preflight: dict[str, object] = {
        "schema_version": "market_data_coverage_v1",
        "outcome": "adjusted_coverage",
        "requested_date_range": requested_date_range,
        "effective_date_range": effective_date_range,
        "preflight_id": "coverage-fixture",
        "observations_by_symbol": {"AAPL": 3, "SPY": 3},
    }
    if adjustment_reason is not None:
        coverage_preflight["adjustment_reason"] = adjustment_reason
    return {
        "strategy_type": "buy_and_hold",
        "symbol": "AAPL",
        "symbols": ["AAPL"],
        "asset_class": "equity",
        "timeframe": "1D",
        "date_range": effective_date_range,
        "requested_date_range": requested_date_range,
        "coverage_preflight": coverage_preflight,
        "entry_rule": None,
        "exit_rule": None,
        "rule_spec": None,
        "sizing_mode": "capital_amount",
        "capital_amount": 10_000.0,
        "position_size": None,
        "cadence": None,
        "parameters": {},
        "risk_rules": [],
        "benchmark_symbol": "SPY",
        "_execution_realism": None,
        "language": "en",
    }


def _context() -> BacktestJobShadowContext:
    context = BacktestJobShadowContext(
        user_id="user-1",
        conversation_id="conversation-1",
        account_kind="registered",
        request_message_id="message-1",
        confirmation_message_id="confirmation-message-1",
        idempotency_key="idem-1",
        request_id="request-1",
        chat_action={
            "type": "run_backtest",
            "payload": {"confirmation_id": "confirmation-1"},
        },
    )
    return context


def test_chat_job_identity_excludes_reason_while_execution_retains_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARGUS_BACKTEST_JOBS_SHADOW_ENABLED", "true")
    monkeypatch.setenv("ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED", "false")
    monkeypatch.setenv("ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED", "false")
    admission_requests: list[dict[str, object]] = []
    delegate_requests: list[dict[str, object]] = []

    for adjustment_reason in (None, "calendar_alignment"):
        events: list[str] = []
        gateway = _IdentityCaptureGateway(events)
        delegate = _DelegateTool(events)
        tool = ShadowBacktestJobTool(
            delegate=delegate,
            gateway_getter=lambda current_gateway=gateway: current_gateway,
            dev_memory_fallback_getter=lambda: False,
        )

        with backtest_job_shadow_context(_context()):
            result = tool.run(
                _coverage_payload(adjustment_reason=adjustment_reason)
            )

        assert result["success"] is True
        admission_requests.append(gateway.admission_requests[0])
        delegate_requests.append(delegate.calls[0])

    without_reason, with_reason = admission_requests
    expected_hash = payload_hash(_coverage_payload(adjustment_reason=None))
    assert without_reason["payload_hash"] == expected_hash
    assert without_reason["payload_hash"] == with_reason["payload_hash"]
    assert without_reason["identity_hash"] == with_reason["identity_hash"]
    stored_request = with_reason["launch_payload"]["request"]  # type: ignore[index]
    assert stored_request["coverage_preflight"]["adjustment_reason"] == (  # type: ignore[index]
        "calendar_alignment"
    )
    assert delegate_requests[1]["coverage_preflight"]["adjustment_reason"] == (  # type: ignore[index]
        "calendar_alignment"
    )


def _run() -> BacktestRun:
    return BacktestRun(
        id="run-workflow-1",
        conversation_id="conversation-1",
        strategy_id=None,
        status="completed",
        asset_class="equity",
        symbols=["AAPL"],
        allocation_method="equal_weight",
        benchmark_symbol="SPY",
        metrics={"aggregate": {"performance": {"total_return_pct": 12.4}}},
        config_snapshot={"template": "buy_and_hold", "benchmark_symbol": "SPY"},
        conversation_result_card={
            "title": "AAPL buy and hold",
            "date_range": {
                "start": "2025-06-06",
                "end": "2026-06-06",
                "display": "June 6, 2025 to June 6, 2026",
            },
            "status_label": "Simulation Complete",
            "rows": [
                {
                    "key": "total_return_pct",
                    "label": "Total return",
                    "value": "+12.4%",
                }
            ],
            "assumptions": ["Long-only", "Benchmark: SPY"],
            "actions": [],
        },
        created_at=datetime.now(timezone.utc),
        chart=None,
        trades=[],
    )


@pytest.fixture(autouse=True)
def _mock_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "true")
    monkeypatch.setenv("ARGUS_DEV_MEMORY_FALLBACK", "false")


def test_real_workflow_mode_returns_async_job_without_delegate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARGUS_BACKTEST_JOBS_SHADOW_ENABLED", "true")
    monkeypatch.setenv("ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED", "true")
    monkeypatch.setenv("ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED", "true")
    monkeypatch.delenv("ARGUS_BACKTEST_REAL_WORKFLOW_TASK", raising=False)
    events: list[str] = []
    gateway = _Gateway(events)
    dispatcher = _Dispatcher(events)
    delegate = _DelegateTool(events)
    tool = ShadowBacktestJobTool(
        delegate=delegate,
        gateway_getter=lambda: gateway,
        dev_memory_fallback_getter=lambda: False,
        dispatcher_getter=lambda: dispatcher,
    )

    with backtest_job_shadow_context(_context()):
        result = tool.run(_payload())

    assert result["success"] is True
    assert result["payload"]["backtest_job"]["id"] == "job-async-1"
    assert result["payload"]["backtest_job"]["status"] == "queued"
    assert events == ["job", "dispatch", "metadata"]
    assert delegate.calls == []
    assert gateway.jobs[0]["launch_payload"]["kind"] == "run_backtest_job"
    assert (
        gateway.jobs[0]["execution_metadata"]["openrouter_traffic_class"]
        == "registered"
    )
    assert (
        gateway.metadata_updates[0]["execution_metadata"]["workflow_dispatch"]["task"]
        == "argus-backtests/run_backtest_job"
    )


def test_dispatch_exception_terminalizes_still_queued_job_without_delegate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARGUS_BACKTEST_JOBS_SHADOW_ENABLED", "true")
    monkeypatch.setenv("ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED", "true")
    monkeypatch.setenv("ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED", "true")
    events: list[str] = []
    gateway = _Gateway(events)
    dispatcher = _FailingDispatcher(events, gateway=gateway)
    delegate = _DelegateTool(events)
    tool = ShadowBacktestJobTool(
        delegate=delegate,
        gateway_getter=lambda: gateway,
        dev_memory_fallback_getter=lambda: False,
        dispatcher_getter=lambda: dispatcher,
    )

    with backtest_job_shadow_context(_context()):
        result = tool.run(_payload())

    assert result["payload"]["backtest_job"]["status"] == "failed"
    assert result["payload"]["backtest_job"]["retryable"] is True
    assert gateway.failure_attempts[0]["expected_status"] == "queued"
    assert len(gateway.failed_updates) == 1
    assert len(dispatcher.calls) == 1
    assert delegate.calls == []


def test_dispatch_metadata_failure_preserves_dispatched_queued_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARGUS_BACKTEST_JOBS_SHADOW_ENABLED", "true")
    monkeypatch.setenv("ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED", "true")
    monkeypatch.setenv("ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED", "true")
    events: list[str] = []
    gateway = _MetadataFailingGateway(events)
    dispatcher = _Dispatcher(events)
    delegate = _DelegateTool(events)
    tool = ShadowBacktestJobTool(
        delegate=delegate,
        gateway_getter=lambda: gateway,
        dev_memory_fallback_getter=lambda: False,
        dispatcher_getter=lambda: dispatcher,
    )
    context = _context()

    with backtest_job_shadow_context(context):
        result = tool.run(_payload())

    assert result["payload"]["backtest_job"]["status"] == "queued"
    assert gateway.jobs[0]["status"] == "queued"
    assert gateway.failure_attempts == []
    assert gateway.failed_updates == []
    assert context.workflow_dispatch_started is True
    assert context.workflow_task_run_id == "task-run-real-1"
    assert context.workflow_dispatch_error is None
    assert events == ["job", "dispatch", "metadata"]
    assert len(dispatcher.calls) == 1
    assert delegate.calls == []


@pytest.mark.parametrize("remote_status", ["running", "succeeded"])
def test_dispatch_exception_does_not_overwrite_remote_terminal_progress(
    monkeypatch: pytest.MonkeyPatch,
    remote_status: str,
) -> None:
    monkeypatch.setenv("ARGUS_BACKTEST_JOBS_SHADOW_ENABLED", "true")
    monkeypatch.setenv("ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED", "true")
    monkeypatch.setenv("ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED", "true")
    events: list[str] = []
    gateway = _Gateway(events)
    dispatcher = _FailingDispatcher(
        events,
        gateway=gateway,
        remote_status=remote_status,
    )
    delegate = _DelegateTool(events)
    tool = ShadowBacktestJobTool(
        delegate=delegate,
        gateway_getter=lambda: gateway,
        dev_memory_fallback_getter=lambda: False,
        dispatcher_getter=lambda: dispatcher,
    )

    with backtest_job_shadow_context(_context()):
        result = tool.run(_payload())

    assert result["payload"]["backtest_job"]["status"] == remote_status
    assert gateway.failure_attempts[0]["expected_status"] == "queued"
    assert gateway.failed_updates == []
    assert len(dispatcher.calls) == 1
    assert delegate.calls == []


def test_atomic_replay_never_becomes_a_second_dispatch_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARGUS_BACKTEST_JOBS_SHADOW_ENABLED", "true")
    monkeypatch.setenv("ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED", "true")
    monkeypatch.setenv("ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED", "true")
    events: list[str] = []
    gateway = _AtomicReplayGateway(events)
    dispatcher = _GatedDispatcher(events)
    delegate = _DelegateTool(events)
    tool = ShadowBacktestJobTool(
        delegate=delegate,
        gateway_getter=lambda: gateway,
        dev_memory_fallback_getter=lambda: False,
        dispatcher_getter=lambda: dispatcher,
    )
    results: list[dict[str, object]] = []
    errors: list[BaseException] = []

    def run_same_key() -> None:
        try:
            with backtest_job_shadow_context(_context()):
                results.append(tool.run(_payload()))
        except BaseException as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    admitted_thread = Thread(target=run_same_key)
    admitted_thread.start()
    assert dispatcher.first_dispatch_entered.wait(timeout=5)

    replay_thread = Thread(target=run_same_key)
    replay_thread.start()
    replay_thread.join(timeout=5)
    dispatcher.release_first_dispatch.set()
    admitted_thread.join(timeout=5)

    assert not admitted_thread.is_alive()
    assert not replay_thread.is_alive()
    assert errors == []
    assert len(results) == 2
    assert gateway.admission_calls == 2
    assert gateway.allowance_reservations == 1
    assert len(gateway.jobs) == 1
    assert len(dispatcher.calls) == 1
    assert delegate.calls == []
    assert {
        result["payload"]["backtest_job"]["id"]  # type: ignore[index]
        for result in results
    } == {"job-race-1"}


def test_execute_stage_returns_job_artifact_without_result_explanation() -> None:
    state = RunState.new(current_user_message="Run it", recent_thread_history=[])
    state.confirmation_payload = {
        "strategy_type": "buy_and_hold",
        "symbol": "AAPL",
        "symbols": ["AAPL"],
        "asset_class": "equity",
        "date_range": "past year",
    }

    result = execute_stage(state=state, tool=_AsyncJobTool(), max_retries=1)

    assert result.outcome == "ready_to_respond"
    assert result.patch["backtest_job"]["id"] == "job-async-1"
    assert result.patch["final_response_payload"]["backtest_job"]["id"] == ("job-async-1")
    assert "started" in result.patch["assistant_response"].lower()
    assert result.patch["artifact_references"][0]["artifact_kind"] == "backtest_job"


def test_terminal_render_task_timeout_reconciles_running_job() -> None:
    from argus.api.chat.backtest_jobs import reconcile_terminal_render_task_run

    gateway = _TimedOutJobGateway()
    task_client = _FakeTerminalTaskRunClient(
        {
            "id": "trn-timeout-1",
            "status": "failed",
            "error": "task timed out",
            "completedAt": "2026-06-06T12:01:10Z",
        }
    )

    reconciled = reconcile_terminal_render_task_run(
        gateway=gateway,
        user_id="user-1",
        job=gateway.get_backtest_job(user_id="user-1", job_id="job-timeout-1"),
        task_run_client=task_client,
    )

    assert task_client.calls == ["trn-timeout-1"]
    assert reconciled["status"] == "failed"
    assert reconciled["failure_code"] == "workflow_task_timeout"
    assert reconciled["retryable"] is True
    assert gateway.failed_updates[0]["failure_detail"] == (
        "Backtest execution timed out before finishing."
    )
    metadata = reconciled["execution_metadata"]
    assert metadata["workflow_dispatch"]["status"] == "failed"
    assert metadata["workflow_dispatch"]["error"] == "task timed out"
    assert metadata["workflow_backtest"]["workflow_run_status"] == "failed"
    assert metadata["workflow_backtest"]["workflow_run_error"] == "task timed out"


def test_terminal_render_task_failure_cas_preserves_concurrent_success() -> None:
    from argus.api.chat.backtest_jobs import reconcile_terminal_render_task_run

    class _ConcurrentSuccessGateway(_TimedOutJobGateway):
        def mark_backtest_job_failed(self, **payload: object) -> dict[str, object]:
            self.failed_updates.append(payload)
            self.job.update(
                {
                    "status": "succeeded",
                    "result_run_id": "run-concurrent-success",
                    "finished_at": "2026-06-06T12:01:09+00:00",
                }
            )
            if payload.get("expected_status") != self.job["status"]:
                return {}
            raise AssertionError("failure update overwrote concurrent success")

    gateway = _ConcurrentSuccessGateway()
    reconciled = reconcile_terminal_render_task_run(
        gateway=gateway,
        user_id="user-1",
        job=gateway.get_backtest_job(user_id="user-1", job_id="job-timeout-1"),
        task_run_client=_FakeTerminalTaskRunClient(
            {
                "id": "trn-timeout-1",
                "status": "failed",
                "error": "task timed out",
                "completedAt": "2026-06-06T12:01:10Z",
            }
        ),
    )

    assert gateway.failed_updates[0]["expected_status"] == "running"
    assert reconciled is not None
    assert reconciled["status"] == "succeeded"
    assert reconciled["result_run_id"] == "run-concurrent-success"


def test_terminal_render_task_cancellation_reconciles_as_non_retryable() -> None:
    from argus.api.chat.backtest_jobs import reconcile_terminal_render_task_run

    gateway = _TimedOutJobGateway()
    task_client = _FakeTerminalTaskRunClient(
        {
            "id": "trn-timeout-1",
            "status": "canceled",
            "error": "canceled by operator",
            "completedAt": "2026-06-06T12:01:10Z",
        }
    )

    reconciled = reconcile_terminal_render_task_run(
        gateway=gateway,
        user_id="user-1",
        job=gateway.get_backtest_job(user_id="user-1", job_id="job-timeout-1"),
        task_run_client=task_client,
    )

    assert reconciled["status"] == "failed"
    assert reconciled["failure_code"] == "workflow_task_canceled"
    assert reconciled["retryable"] is False
    assert gateway.failed_updates[0]["failure_detail"] == (
        "Backtest execution was canceled before finishing."
    )


def test_terminal_render_task_expiration_reconciles_as_retryable() -> None:
    from argus.api.chat.backtest_jobs import reconcile_terminal_render_task_run

    gateway = _TimedOutJobGateway()
    task_client = _FakeTerminalTaskRunClient(
        {
            "id": "trn-timeout-1",
            "status": "expired",
            "error": "task expired",
            "completedAt": "2026-06-06T12:01:10Z",
        }
    )

    reconciled = reconcile_terminal_render_task_run(
        gateway=gateway,
        user_id="user-1",
        job=gateway.get_backtest_job(user_id="user-1", job_id="job-timeout-1"),
        task_run_client=task_client,
    )

    assert reconciled["status"] == "failed"
    assert reconciled["failure_code"] == "workflow_task_expired"
    assert reconciled["retryable"] is True
    assert gateway.failed_updates[0]["failure_detail"] == (
        "Backtest execution expired before finishing."
    )


def test_terminal_render_task_reconciliation_ignores_malformed_metadata() -> None:
    from argus.api.chat.backtest_jobs import reconcile_terminal_render_task_run

    gateway = _TimedOutJobGateway()
    job = gateway.get_backtest_job(user_id="user-1", job_id="job-timeout-1")
    assert job is not None
    job["execution_metadata"] = {"workflow_dispatch": "not-json-object"}
    task_client = _FakeTerminalTaskRunClient(
        {
            "id": "trn-timeout-1",
            "status": "failed",
            "error": "task timed out",
        }
    )

    reconciled = reconcile_terminal_render_task_run(
        gateway=gateway,
        user_id="user-1",
        job=job,
        task_run_client=task_client,
    )

    assert reconciled == job
    assert task_client.calls == []
    assert gateway.failed_updates == []


def test_stale_backtest_job_scan_reconciles_terminal_task_run() -> None:
    from argus.api.chat.backtest_jobs import scan_stale_backtest_jobs

    gateway = _StaleJobScanGateway()
    task_client = _FakeTerminalTaskRunClient(
        {
            "id": "trn-stale-1",
            "status": "failed",
            "error": "task timed out",
            "completedAt": "2026-06-06T12:03:00Z",
        }
    )

    report = scan_stale_backtest_jobs(
        gateway=gateway,
        now=datetime(2026, 6, 6, 12, 30, tzinfo=timezone.utc),
        queued_age_seconds=900,
        running_age_seconds=900,
        limit=20,
        task_run_client=task_client,
    )

    assert task_client.calls == ["trn-stale-1"]
    assert gateway.list_calls == [
        {
            "status": "queued",
            "user_id": None,
            "limit": 20,
            "oldest_first": True,
        },
        {
            "status": "running",
            "user_id": None,
            "limit": 20,
            "oldest_first": True,
        },
    ]
    assert gateway.failed_updates[0]["job_id"] == "job-stale-running"
    assert report["status"] == "ready"
    assert report["stale_count"] == 1
    assert report["reconciled_count"] == 1
    assert report["unresolved_count"] == 0


def test_stale_backtest_job_scan_reports_unresolved_jobs_without_task_metadata() -> None:
    from argus.api.chat.backtest_jobs import scan_stale_backtest_jobs

    gateway = _StaleJobScanGateway()
    gateway.jobs[0]["execution_metadata"] = {}
    task_client = _FakeTerminalTaskRunClient(
        {
            "id": "trn-stale-1",
            "status": "failed",
            "error": "task timed out",
        }
    )

    report = scan_stale_backtest_jobs(
        gateway=gateway,
        now=datetime(2026, 6, 6, 12, 30, tzinfo=timezone.utc),
        queued_age_seconds=900,
        running_age_seconds=900,
        limit=20,
        task_run_client=task_client,
    )

    assert task_client.calls == []
    assert report["status"] == "degraded"
    assert report["reconciled_count"] == 0
    assert report["unresolved_count"] == 1
    assert report["unresolved_jobs"] == [
        {
            "id": "job-stale-running",
            "status": "running",
            "user_id": "user-1",
            "age_seconds": 1740,
            "task_run_id": None,
        }
    ]


def test_stale_backtest_job_scan_fails_stale_proof_jobs_without_task_metadata() -> None:
    from argus.api.chat.backtest_jobs import scan_stale_backtest_jobs

    gateway = _StaleJobScanGateway()
    gateway.jobs = [
        {
            "id": "job-stale-proof",
            "user_id": "user-1",
            "status": "queued",
            "queued_at": "2026-06-06T12:00:00+00:00",
            "created_at": "2026-06-06T12:00:00+00:00",
            "updated_at": "2026-06-06T12:00:00+00:00",
            "launch_payload": {"kind": "render_workflow_proof"},
            "execution_metadata": {},
        }
    ]
    task_client = _FakeTerminalTaskRunClient(
        {
            "id": "trn-stale-1",
            "status": "failed",
            "error": "task timed out",
        }
    )

    report = scan_stale_backtest_jobs(
        gateway=gateway,
        now=datetime(2026, 6, 6, 12, 30, tzinfo=timezone.utc),
        queued_age_seconds=900,
        running_age_seconds=900,
        limit=20,
        task_run_client=task_client,
    )

    assert task_client.calls == []
    assert report["status"] == "ready"
    assert report["stale_count"] == 1
    assert report["reconciled_count"] == 1
    assert report["unresolved_count"] == 0
    assert gateway.failed_updates[0]["job_id"] == "job-stale-proof"
    assert gateway.failed_updates[0]["failure_code"] == "workflow_dispatch_missing"
    assert gateway.failed_updates[0]["retryable"] is True


def test_stale_backtest_job_scan_fails_real_queued_job_without_dispatch_proof() -> None:
    from argus.api.chat.backtest_jobs import scan_stale_backtest_jobs

    gateway = _StaleJobScanGateway()
    gateway.jobs = [
        {
            "id": "job-stale-real",
            "user_id": "user-1",
            "status": "queued",
            "queued_at": "2026-06-06T12:00:00+00:00",
            "created_at": "2026-06-06T12:00:00+00:00",
            "updated_at": "2026-06-06T12:00:00+00:00",
            "launch_payload": {"kind": "run_backtest_job"},
            "execution_metadata": {},
        }
    ]
    task_client = _FakeTerminalTaskRunClient(
        {"id": "trn-never-created", "status": "failed"}
    )

    report = scan_stale_backtest_jobs(
        gateway=gateway,
        now=datetime(2026, 6, 6, 12, 30, tzinfo=timezone.utc),
        queued_age_seconds=900,
        running_age_seconds=900,
        limit=20,
        task_run_client=task_client,
    )

    assert task_client.calls == []
    assert report["status"] == "ready"
    assert report["reconciled_count"] == 1
    assert report["unresolved_count"] == 0
    assert gateway.failed_updates[0]["job_id"] == "job-stale-real"
    assert gateway.failed_updates[0]["expected_status"] == "queued"
    assert gateway.failed_updates[0]["expected_updated_at"] == (
        "2026-06-06T12:00:00+00:00"
    )
    assert gateway.failed_updates[0]["retryable"] is True


def test_stale_undispatched_failure_loses_cas_to_concurrent_dispatch_metadata() -> None:
    from argus.api.chat.backtest_jobs import scan_stale_backtest_jobs

    class _ConcurrentDispatchGateway(_StaleJobScanGateway):
        def mark_backtest_job_failed(self, **payload: object) -> dict[str, object]:
            self.failed_updates.append(payload)
            [job] = self.jobs
            job.update(
                {
                    "status": "queued",
                    "updated_at": "2026-06-06T12:30:01+00:00",
                    "execution_metadata": {
                        "workflow_dispatch": {"task_run_id": "trn-concurrent-1"}
                    },
                }
            )
            if job["updated_at"] != payload.get("expected_updated_at"):
                return {}
            raise AssertionError("stale failure overwrote concurrent dispatch")

    gateway = _ConcurrentDispatchGateway()
    gateway.jobs = [
        {
            "id": "job-stale-real",
            "user_id": "user-1",
            "status": "queued",
            "queued_at": "2026-06-06T12:00:00+00:00",
            "created_at": "2026-06-06T12:00:00+00:00",
            "updated_at": "2026-06-06T12:00:00+00:00",
            "launch_payload": {"kind": "run_backtest_job"},
            "execution_metadata": {},
        }
    ]

    report = scan_stale_backtest_jobs(
        gateway=gateway,
        now=datetime(2026, 6, 6, 12, 30, tzinfo=timezone.utc),
        queued_age_seconds=900,
        running_age_seconds=900,
        limit=20,
        task_run_client=_FakeTerminalTaskRunClient(
            {"id": "trn-never-created", "status": "failed"}
        ),
    )

    [job] = gateway.jobs
    assert gateway.failed_updates[0]["expected_status"] == "queued"
    assert gateway.failed_updates[0]["expected_updated_at"] == (
        "2026-06-06T12:00:00+00:00"
    )
    assert job["status"] == "queued"
    assert job.get("failure_code") is None
    assert job["execution_metadata"] == {
        "workflow_dispatch": {"task_run_id": "trn-concurrent-1"}
    }
    assert report["reconciled_count"] == 0
    assert report["unresolved_count"] == 1
