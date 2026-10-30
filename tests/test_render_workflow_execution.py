from __future__ import annotations

import importlib
import sys
from datetime import date, datetime, timezone
from types import ModuleType
from uuid import UUID, uuid4

import pytest
from argus.domain.backtest_finalization import (
    BacktestFinalizationInput,
    MemoryBacktestFinalizationGateway,
    PreparedBacktestFinalization,
    finalize_backtest_completion,
    stable_backtest_run_id,
)
from argus.domain.store import AlphaStore, utcnow


class FakeBacktestJobGateway:
    def __init__(self, row: dict[str, object]) -> None:
        self.row = dict(row)
        self.transitions: list[str] = []
        self.failed_updates: list[dict[str, object]] = []
        self.failure_expected_statuses: list[str | None] = []
        self.route_receipts: list[dict[str, object]] = []
        self.cost_ledger_entries: list[dict[str, object]] = []
        self.finalization_store = AlphaStore()
        self.finalization_calls: list[PreparedBacktestFinalization] = []
        self.fail_finalization_after_commit_once = False
        self.fail_result_link_once = False
        self.fail_result_link_after_commit_once = False
        self.refuse_result_link_once = False
        self.fail_run_cleanup_once = False
        self.deleted_runs: list[str] = []
        self.running_started_at_arguments: list[str | None] = []

    def fetch_job(self, job_id: str) -> dict[str, object] | None:
        if self.row["id"] != job_id:
            return None
        return dict(self.row)

    def mark_backtest_job_running(
        self,
        *,
        user_id: str,
        job_id: str,
        execution_metadata: dict[str, object],
        started_at: str | None = None,
    ) -> dict[str, object]:
        assert self.row["user_id"] == user_id
        assert self.row["id"] == job_id
        self.transitions.append("running")
        self.running_started_at_arguments.append(started_at)
        self.row["status"] = "running"
        self.row["started_at"] = started_at or datetime.now(timezone.utc).isoformat()
        self.row["attempts"] = int(self.row.get("attempts") or 0) + 1
        self.row["result_run_id"] = None
        self.row["finished_at"] = None
        self.row["failure_code"] = None
        self.row["failure_detail"] = None
        self.row["retryable"] = False
        self.row["execution_metadata"] = execution_metadata
        return dict(self.row)

    def finalize_backtest_completion(
        self,
        *,
        finalization: PreparedBacktestFinalization,
    ):
        self.transitions.append("finalize")
        self.finalization_calls.append(finalization)
        finalized = MemoryBacktestFinalizationGateway(
            self.finalization_store
        ).finalize_backtest_completion(finalization=finalization)
        if self.fail_finalization_after_commit_once:
            self.fail_finalization_after_commit_once = False
            raise RuntimeError("finalization response lost")
        return finalized

    def merge_backtest_job_execution_metadata(
        self,
        *,
        user_id: str,
        job_id: str,
        execution_metadata: dict[str, object],
    ) -> dict[str, object]:
        assert self.row["user_id"] == user_id
        assert self.row["id"] == job_id
        self.row["execution_metadata"] = execution_metadata
        return dict(self.row)

    def link_backtest_job_result(
        self,
        *,
        user_id: str,
        job_id: str,
        result_run_id: str,
        execution_metadata: dict[str, object] | None = None,
        mark_succeeded: bool = False,
    ) -> dict[str, object]:
        assert self.row["user_id"] == user_id
        assert self.row["id"] == job_id
        assert mark_succeeded is True
        if self.fail_result_link_once:
            self.fail_result_link_once = False
            raise RuntimeError("job result link unavailable")
        if self.refuse_result_link_once:
            # The lifecycle statement refused the attach: the standing
            # terminal row comes back without the requested result.
            self.refuse_result_link_once = False
            self.row["status"] = "canceled"
            self.row["retryable"] = False
            self.row["result_run_id"] = None
            return dict(self.row)
        self.transitions.append("succeeded")
        metadata = dict(self.row.get("execution_metadata") or {})
        metadata.update(execution_metadata or {})
        self.row["status"] = "succeeded"
        self.row["result_run_id"] = result_run_id
        self.row["failure_code"] = None
        self.row["failure_detail"] = None
        self.row["retryable"] = False
        self.row["finished_at"] = datetime.now(timezone.utc).isoformat()
        self.row["execution_metadata"] = metadata
        if self.fail_result_link_after_commit_once:
            self.fail_result_link_after_commit_once = False
            raise RuntimeError("job result link response lost")
        return dict(self.row)

    def delete_withheld_backtest_result(self, *, user_id: str, run_id: str) -> bool:
        assert self.row["user_id"] == user_id
        if self.fail_run_cleanup_once:
            self.fail_run_cleanup_once = False
            raise RuntimeError("cleanup unavailable")
        self.deleted_runs.append(run_id)
        return True

    def mark_backtest_job_failed(
        self,
        *,
        user_id: str,
        job_id: str,
        failure_code: str,
        failure_detail: str,
        retryable: bool,
        execution_metadata: dict[str, object] | None = None,
        finished_at: str | None = None,
        expected_status: str | None = None,
    ) -> dict[str, object]:
        assert self.row["user_id"] == user_id
        assert self.row["id"] == job_id
        self.failure_expected_statuses.append(expected_status)
        if expected_status is not None:
            assert self.row["status"] == expected_status
        self.transitions.append("failed")
        metadata = dict(self.row.get("execution_metadata") or {})
        metadata.update(execution_metadata or {})
        self.row["status"] = "failed"
        self.row["failure_code"] = failure_code
        self.row["failure_detail"] = failure_detail
        self.row["retryable"] = retryable
        self.row["result_run_id"] = None
        self.row["finished_at"] = finished_at
        self.row["execution_metadata"] = metadata
        self.failed_updates.append(
            {
                "failure_code": failure_code,
                "failure_detail": failure_detail,
                "retryable": retryable,
                "execution_metadata": execution_metadata,
            }
        )
        return dict(self.row)

    def create_route_receipt(
        self,
        *,
        user_id: str | None,
        receipt: dict[str, object],
        conversation_id: str | None = None,
        run_id: str | None = None,
        message_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object]:
        row = {
            "id": f"receipt-{len(self.route_receipts) + 1}",
            "user_id": user_id,
            "conversation_id": conversation_id,
            "run_id": run_id,
            "message_id": message_id,
            "metadata": metadata or {},
            **receipt,
        }
        self.route_receipts.append(row)
        return row

    def create_cost_ledger_entry(self, *, entry: dict[str, object]) -> dict[str, object]:
        row = {"id": f"ledger-{len(self.cost_ledger_entries) + 1}", **entry}
        self.cost_ledger_entries.append(row)
        return row


class FakeBacktestTool:
    def __init__(self, result: dict[str, object]) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(payload)
        return self.result


def _job_row(*, launch_payload: dict[str, object]) -> dict[str, object]:
    return {
        "id": str(uuid4()),
        "user_id": "user-1",
        "conversation_id": "conversation-1",
        "status": "queued",
        "attempts": 0,
        "launch_payload": launch_payload,
        "execution_metadata": {
            "existing": "kept",
            "openrouter_traffic_class": "registered",
        },
        "result_run_id": None,
    }


def _request_payload() -> dict[str, object]:
    return {
        "strategy_type": "buy_and_hold",
        "symbol": "AAPL",
        "symbols": ["AAPL"],
        "asset_class": "equity",
        "timeframe": "1D",
        "date_range": "past year",
        "language": "en",
    }


def _successful_tool_result() -> dict[str, object]:
    return {
        "success": True,
        "payload": {
            "envelope": {
                "resolved_strategy": {
                    "strategy_type": "buy_and_hold",
                    "asset_universe": ["AAPL"],
                    "symbol": "AAPL",
                },
                "resolved_parameters": {
                    "timeframe": "1D",
                    "date_range": "past year",
                    "benchmark_symbol": "SPY",
                },
                "metrics": {
                    "aggregate": {
                        "total_return": 0.123,
                        "total_return_pct": 12.3,
                        "performance": {
                            "total_return_pct": 12.3,
                            "benchmark_return_pct": 8.1,
                            "delta_vs_benchmark_pct": 4.2,
                        },
                    }
                },
                "benchmark_metrics": {
                    "symbol": "SPY",
                    "benchmark_return_pct": 8.1,
                    "total_return": 0.081,
                    "total_return_pct": 8.1,
                },
                "provider_metadata": {"provider": "synthetic_unit_fixture"},
            },
            "result_card": {
                "title": "Apple buy and hold",
                "actions": [{"type": "save_strategy", "payload": {}}],
                "chart": {
                    "kind": "portfolio_equity",
                    "markers": [
                        {
                            "time": "2025-01-02",
                            "type": "entry",
                            "symbols": ["AAPL"],
                        }
                    ],
                },
            },
            "explanation_context": {},
        },
        "error_type": None,
        "error_message": None,
        "retryable": False,
        "capability_context": {"execution_status": "succeeded"},
    }


def _successful_tool_result_with_timings() -> dict[str, object]:
    result = _successful_tool_result()
    result["execution_metadata"] = {
        "timings_ms": {
            "provider_fetch_total": 12.3456,
            "engine_compute_total": 45.6789,
            "chart_result_build_total": 7.8912,
        }
    }
    return result


def test_run_backtest_job_rejects_proof_payloads() -> None:
    from workflows.backtest_job import WorkflowBacktestJobError, run_backtest_job

    job = _job_row(launch_payload={"kind": "render_workflow_proof"})
    gateway = FakeBacktestJobGateway(job)

    with pytest.raises(WorkflowBacktestJobError, match="run_backtest_job"):
        run_backtest_job(
            gateway,
            job_id=str(job["id"]),
            backtest_tool=FakeBacktestTool(_successful_tool_result()),
        )

    assert gateway.transitions == []


@pytest.mark.parametrize(
    "execution_metadata",
    [
        pytest.param({}, id="legacy-missing"),
        pytest.param(
            {"openrouter_traffic_class": "unexpected"},
            id="malformed-literal",
        ),
    ],
)
def test_run_backtest_job_terminalizes_invalid_traffic_class_metadata(
    execution_metadata: dict[str, object],
) -> None:
    from workflows.backtest_job import REAL_BACKTEST_JOB_KIND, run_backtest_job

    job = _job_row(
        launch_payload={
            "kind": REAL_BACKTEST_JOB_KIND,
            "schema_version": "backtest_job_launch/v1",
            "request": _request_payload(),
        }
    )
    job["execution_metadata"] = execution_metadata
    gateway = FakeBacktestJobGateway(job)
    tool = FakeBacktestTool(_successful_tool_result())

    result = run_backtest_job(
        gateway,
        job_id=str(job["id"]),
        backtest_tool=tool,
        workflow_run_id="invalid-envelope-run",
    )

    assert result["status"] == "failed"
    assert result["failure_code"] == "invalid_job_contract"
    assert result["failure_detail"] == "execution_failed"
    assert result["retryable"] is False
    assert gateway.transitions == ["failed"]
    assert tool.calls == []
    workflow_metadata = gateway.row["execution_metadata"]["workflow_backtest"]
    assert workflow_metadata["failure_category"] == "invalid_job_contract"
    assert "source_error_type" not in workflow_metadata
    assert "source_traceback" not in workflow_metadata


def test_postgres_backtest_job_gateway_reuses_connection_in_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from workflows.backtest_job import PostgresBacktestJobGateway

    connect_calls = 0

    class FakeCursor:
        def __init__(self) -> None:
            self.query = ""

        def __enter__(self) -> FakeCursor:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def execute(self, query: str, params: object = None) -> None:
            del params
            self.query = query

        def fetchone(self) -> dict[str, object]:
            if "select *" in self.query.lower():
                return {"id": "job-1", "execution_metadata": {}}
            return {"id": "job-1", "execution_metadata": {"kept": True}}

    class FakeConnection:
        def __enter__(self) -> FakeConnection:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def cursor(self) -> FakeCursor:
            return FakeCursor()

    def fake_connect(self: PostgresBacktestJobGateway) -> FakeConnection:
        del self
        nonlocal connect_calls
        connect_calls += 1
        return FakeConnection()

    monkeypatch.setattr(PostgresBacktestJobGateway, "_connect", fake_connect)
    gateway = PostgresBacktestJobGateway("postgres://example")

    with gateway:
        assert gateway.fetch_job("job-1") == {"id": "job-1", "execution_metadata": {}}
        assert gateway.merge_backtest_job_execution_metadata(
            user_id="user-1",
            job_id="job-1",
            execution_metadata={"kept": True},
        ) == {"id": "job-1", "execution_metadata": {"kept": True}}

    assert connect_calls == 1


def test_postgres_backtest_job_gateway_disables_pooled_prepared_statements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import psycopg

    from workflows.backtest_job import PostgresBacktestJobGateway

    captured: dict[str, object] = {}
    sentinel = object()

    def fake_connect(database_url: str, **kwargs: object) -> object:
        captured["database_url"] = database_url
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(psycopg, "connect", fake_connect)
    gateway = PostgresBacktestJobGateway("postgres://pooled-example")

    connection = gateway._connect()

    assert connection is sentinel
    assert captured["database_url"] == "postgres://pooled-example"
    assert captured["autocommit"] is True
    assert captured["prepare_threshold"] is None


def test_postgres_failed_update_types_nullable_expected_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from workflows.backtest_job import PostgresBacktestJobGateway

    captured: dict[str, object] = {}

    class FakeCursor:
        def __enter__(self) -> FakeCursor:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def execute(self, query: str, params: object = None) -> None:
            captured["query"] = " ".join(query.split())
            captured["params"] = params

        def fetchone(self) -> dict[str, object]:
            return {"id": "job-1", "status": "failed"}

    class FakeConnection:
        def __enter__(self) -> FakeConnection:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def cursor(self) -> FakeCursor:
            return FakeCursor()

    monkeypatch.setattr(
        PostgresBacktestJobGateway,
        "_connect",
        lambda _self: FakeConnection(),
    )
    gateway = PostgresBacktestJobGateway("postgres://example")

    row = gateway.mark_backtest_job_failed(
        user_id="user-1",
        job_id="job-1",
        failure_code="invalid_job_contract",
        failure_detail="execution_failed",
        retryable=False,
        expected_status=None,
    )

    assert row["status"] == "failed"
    assert "%(expected_status)s::text is null" in str(captured["query"])


def test_postgres_backtest_job_gateway_waits_for_capacity_before_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import workflows.backtest_job as workflow_module
    from workflows.backtest_job import PostgresBacktestJobGateway

    gateway = PostgresBacktestJobGateway(
        "postgres://example",
        capacity_wait_seconds=10.0,
        capacity_poll_seconds=0.25,
    )
    attempts = iter(
        [
            None,
            {"id": "job-1", "user_id": "user-1", "status": "running"},
        ]
    )
    sleeps: list[float] = []
    monotonic = iter([100.0, 100.1])
    monkeypatch.setattr(
        gateway,
        "_try_mark_backtest_job_running",
        lambda **_kwargs: next(attempts),
    )
    monkeypatch.setattr(workflow_module.time, "monotonic", lambda: next(monotonic))
    monkeypatch.setattr(workflow_module.time, "sleep", sleeps.append)

    row = gateway.mark_backtest_job_running(
        user_id="user-1",
        job_id="job-1",
        execution_metadata={"workflow_run_id": "run-1"},
    )

    assert row["status"] == "running"
    assert sleeps == [0.25]


def test_postgres_backtest_job_gateway_rejects_running_job_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from workflows.backtest_job import (
        PostgresBacktestJobGateway,
        WorkflowBacktestJobError,
    )

    queries: list[str] = []

    class FakeCursor:
        query = ""

        def __enter__(self) -> FakeCursor:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def execute(self, query: str, params: object = None) -> None:
            del params
            self.query = " ".join(query.split())
            queries.append(self.query)

        def fetchone(self) -> dict[str, object] | None:
            if self.query.startswith("select status, failure_code"):
                return {"id": "job-1", "status": "running"}
            return None

    class FakeConnection:
        def __enter__(self) -> FakeConnection:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def transaction(self) -> FakeConnection:
            return self

        def cursor(self) -> FakeCursor:
            return FakeCursor()

    monkeypatch.setattr(
        PostgresBacktestJobGateway,
        "_connect",
        lambda _self: FakeConnection(),
    )
    gateway = PostgresBacktestJobGateway("postgres://example")

    with pytest.raises(WorkflowBacktestJobError, match="cannot be started or retried"):
        gateway.mark_backtest_job_running(
            user_id="user-1",
            job_id="job-1",
            execution_metadata={"workflow_run_id": "overlap"},
        )

    assert "pg_advisory_xact_lock(hashtext('backtest_admission'))" in queries[0]
    assert "for update" in queries[1]
    assert not any(query.startswith("update public.backtest_jobs") for query in queries)


@pytest.mark.parametrize(
    "candidate",
    [
        {
            "status": "queued",
            "failure_code": None,
            "retryable": False,
            "attempts": 0,
            "execution_metadata": {},
        },
        {
            "status": "failed",
            "failure_code": "finalization_failed",
            "retryable": True,
            "attempts": 1,
            "execution_metadata": {},
        },
    ],
)
def test_postgres_backtest_job_gateway_leaves_candidate_at_user_capacity(
    monkeypatch: pytest.MonkeyPatch,
    candidate: dict[str, object],
) -> None:
    from workflows.backtest_job import PostgresBacktestJobGateway

    queries: list[str] = []
    transaction_events: list[str] = []

    class FakeCursor:
        query = ""

        def __enter__(self) -> FakeCursor:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def execute(self, query: str, params: object = None) -> None:
            del params
            self.query = " ".join(query.split())
            queries.append(self.query)

        def fetchone(self) -> dict[str, object] | None:
            if self.query.startswith("select status, failure_code"):
                return candidate
            if "as user_running" in self.query:
                return {"user_running": 1, "global_running": 1}
            raise AssertionError(f"unexpected fetch for query: {self.query}")

    class FakeTransaction:
        def __enter__(self) -> FakeTransaction:
            transaction_events.append("begin")
            return self

        def __exit__(self, *_: object) -> None:
            transaction_events.append("commit")

    class FakeConnection:
        def __enter__(self) -> FakeConnection:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def transaction(self) -> FakeTransaction:
            return FakeTransaction()

        def cursor(self) -> FakeCursor:
            return FakeCursor()

    monkeypatch.setenv("ARGUS_BACKTEST_JOBS_USER_RUNNING_LIMIT", "1")
    monkeypatch.setenv("ARGUS_BACKTEST_JOBS_GLOBAL_RUNNING_LIMIT", "5")
    monkeypatch.setattr(
        PostgresBacktestJobGateway,
        "_connect",
        lambda _self: FakeConnection(),
    )
    gateway = PostgresBacktestJobGateway("postgres://example")

    row = gateway._try_mark_backtest_job_running(
        user_id="user-1",
        job_id="job-1",
        execution_metadata={"workflow_run_id": "waiting-run"},
    )

    assert row is None
    assert transaction_events == ["begin", "commit"]
    assert "pg_advisory_xact_lock(hashtext('backtest_admission'))" in queries[0]
    assert "for update" in queries[1]
    assert "as user_running" in queries[2]
    assert not any(query.startswith("update public.backtest_jobs") for query in queries)


def test_postgres_backtest_job_gateway_appends_cost_ledger_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from workflows.backtest_job import PostgresBacktestJobGateway

    captured: dict[str, object] = {}

    class FakeCursor:
        def __enter__(self) -> FakeCursor:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def execute(self, query: str, params: object = None) -> None:
            captured["query"] = query
            captured["params"] = params

        def fetchone(self) -> dict[str, object]:
            return {
                "id": "ledger-1",
                "source": "render_workflow",
                "correlation_id": "workflow:render-run:job-1:run-1",
            }

    class FakeConnection:
        def __enter__(self) -> FakeConnection:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def cursor(self) -> FakeCursor:
            return FakeCursor()

    def fake_connect(self: PostgresBacktestJobGateway) -> FakeConnection:
        del self
        return FakeConnection()

    monkeypatch.setattr(PostgresBacktestJobGateway, "_connect", fake_connect)
    gateway = PostgresBacktestJobGateway("postgres://example")

    row = gateway.create_cost_ledger_entry(
        entry={
            "source": "render_workflow",
            "service": "openrouter",
            "provider": "openrouter",
            "model": "openai/gpt-4.1-mini",
            "feature_area": "result_readout",
            "task": "result_summary",
            "user_id": "user-1",
            "conversation_id": "conversation-1",
            "backtest_run_id": "run-1",
            "backtest_job_id": "job-1",
            "route_receipt_id": "receipt-1",
            "correlation_id": "workflow:render-run:job-1:run-1",
            "usage_metadata": {"prompt_tokens": 21, "completion_tokens": 9},
            "input_tokens": 21,
            "output_tokens": 9,
            "total_tokens": 30,
            "billable_unit": "token",
            "billable_quantity": 30,
            "cost_amount": 0.0009,
            "cost_currency": "USD",
            "cost_source": "provider_reported",
            "latency_ms": 42,
            "status": "succeeded",
            "metadata": {"source": "render_workflow"},
            "occurred_at": "2026-07-02T18:00:00+00:00",
        }
    )

    assert row["id"] == "ledger-1"
    assert "insert into public.cost_ledger_entries" in str(captured["query"]).lower()
    params = captured["params"]
    assert isinstance(params, dict)
    assert params["source"] == "render_workflow"
    assert params["service"] == "openrouter"
    assert params["feature_area"] == "result_readout"
    assert params["backtest_job_id"] == "job-1"
    assert params["route_receipt_id"] == "receipt-1"
    assert params["correlation_id"] == "workflow:render-run:job-1:run-1"
    assert params["usage_metadata"].obj == {
        "prompt_tokens": 21,
        "completion_tokens": 9,
    }
    assert params["metadata"].obj == {"source": "render_workflow"}
    assert params["billable_quantity"] == 30
    assert params["cost_amount"] == 0.0009
    assert params["occurred_at"] == "2026-07-02T18:00:00+00:00"


def test_postgres_backtest_job_gateway_calls_shared_finalization_rpc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.schemas import BacktestRun

    from workflows.backtest_job import PostgresBacktestJobGateway

    captured: dict[str, object] = {}
    run = BacktestRun(
        id="run-1",
        conversation_id="conversation-1",
        strategy_id=None,
        status="completed",
        asset_class="equity",
        symbols=["AAPL"],
        allocation_method="equal_weight",
        benchmark_symbol="SPY",
        metrics={"aggregate": {"performance": {"total_return_pct": 12.4}}},
        config_snapshot={"template": "buy_and_hold", "symbols": ["AAPL"]},
        conversation_result_card={"title": "AAPL buy and hold", "actions": []},
        created_at=utcnow(),
        chart=None,
        trades=[],
    )

    class FakeCursor:
        def __enter__(self) -> FakeCursor:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def execute(self, query: str, params: object = None) -> None:
            captured["query"] = query
            captured["params"] = params

        def fetchone(self) -> dict[str, object]:
            params = captured["params"]
            assert isinstance(params, dict)
            return {
                "run": params["run"].obj,
                "idea": params["idea"].obj,
                "idea_version": params["idea_version"].obj,
                "evidence_artifact": params["evidence_artifact"].obj,
            }

    class FakeConnection:
        def __enter__(self) -> FakeConnection:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def cursor(self) -> FakeCursor:
            return FakeCursor()

    monkeypatch.setattr(
        PostgresBacktestJobGateway,
        "_connect",
        lambda _self: FakeConnection(),
    )
    gateway = PostgresBacktestJobGateway("postgres://example")
    finalization = BacktestFinalizationInput(
        user_id="user-1",
        execution_identity="backtest_job:job-1",
        run=run,
        result_card=dict(run.conversation_result_card),
        idea_id="idea-1",
        idea_version_id="version-1",
        evidence_artifact_id="artifact-1",
        finalized_at=utcnow(),
    )

    finalized = finalize_backtest_completion(gateway, finalization)

    assert "public.finalize_backtest_completion" in str(captured["query"])
    assert finalized.identity.run_id == "run-1"
    assert finalized.identity.evidence_artifact_id == "artifact-1"


def test_run_backtest_job_marks_queued_job_running_then_succeeded_with_result_run() -> (
    None
):
    from workflows.backtest_job import REAL_BACKTEST_JOB_KIND, run_backtest_job

    request = _request_payload()
    job = _job_row(
        launch_payload={
            "kind": REAL_BACKTEST_JOB_KIND,
            "schema_version": "backtest_job_launch/v1",
            "request": request,
        }
    )
    gateway = FakeBacktestJobGateway(job)
    tool = FakeBacktestTool(_successful_tool_result())

    result = run_backtest_job(
        gateway,
        job_id=str(job["id"]),
        backtest_tool=tool,
        workflow_run_id="local-run",
        run_id_factory=lambda: "run-workflow",
    )

    assert result["job_id"] == job["id"]
    assert result["status"] == "succeeded"
    assert result["result_run_id"] == "run-workflow"
    assert gateway.transitions == ["running", "finalize", "succeeded"]
    assert gateway.running_started_at_arguments == [None]
    assert tool.calls == [request]
    created_run = gateway.finalization_store.backtest_runs["run-workflow"]
    assert created_run.id == "run-workflow"
    assert created_run.conversation_id == "conversation-1"
    assert created_run.status == "completed"
    assert created_run.symbols == ["AAPL"]
    assert created_run.benchmark_symbol == "SPY"
    assert (
        created_run.conversation_result_card["actions"][0]["payload"]["run_id"]
        == "run-workflow"
    )
    assert gateway.row["result_run_id"] == "run-workflow"
    assert len(gateway.finalization_store.ideas) == 1
    assert len(gateway.finalization_store.idea_versions) == 1
    assert len(gateway.finalization_store.evidence_artifacts) == 1
    assert created_run.conversation_result_card["evidence_artifact_id"]
    assert gateway.row["execution_metadata"]["existing"] == "kept"
    assert (
        gateway.row["execution_metadata"]["workflow_backtest"]["workflow_run_id"]
        == "local-run"
    )


def test_run_backtest_job_persists_terminal_capacity_wait_timeout() -> None:
    from workflows.backtest_job import (
        REAL_BACKTEST_JOB_KIND,
        WorkflowCapacityTimeout,
        run_backtest_job,
    )

    class CapacityTimedOutGateway(FakeBacktestJobGateway):
        def mark_backtest_job_running(self, **_kwargs: object) -> dict[str, object]:
            raise WorkflowCapacityTimeout("running slot wait expired")

    job = _job_row(
        launch_payload={
            "kind": REAL_BACKTEST_JOB_KIND,
            "schema_version": "backtest_job_launch/v1",
            "request": _request_payload(),
        }
    )
    gateway = CapacityTimedOutGateway(job)
    tool = FakeBacktestTool(_successful_tool_result())

    result = run_backtest_job(
        gateway,
        job_id=str(job["id"]),
        backtest_tool=tool,
        workflow_run_id="capacity-timeout-run",
    )

    assert result["status"] == "failed"
    assert result["failure_code"] == "capacity_timeout"
    assert result["retryable"] is False
    assert gateway.row["status"] == "failed"
    assert gateway.transitions == ["failed"]
    assert gateway.failure_expected_statuses == ["queued"]
    assert tool.calls == []


def test_capacity_wait_timeout_preserves_finalization_retry_state() -> None:
    from workflows.backtest_job import (
        REAL_BACKTEST_JOB_KIND,
        WorkflowCapacityTimeout,
        run_backtest_job,
    )

    class CapacityTimedOutGateway(FakeBacktestJobGateway):
        def mark_backtest_job_running(self, **_kwargs: object) -> dict[str, object]:
            raise WorkflowCapacityTimeout("running slot wait expired")

    job = _job_row(
        launch_payload={
            "kind": REAL_BACKTEST_JOB_KIND,
            "schema_version": "backtest_job_launch/v1",
            "request": _request_payload(),
        }
    )
    job.update(
        status="failed",
        failure_code="finalization_failed",
        failure_detail="execution_failed",
        retryable=True,
        attempts=1,
    )
    gateway = CapacityTimedOutGateway(job)

    result = run_backtest_job(
        gateway,
        job_id=str(job["id"]),
        backtest_tool=FakeBacktestTool(_successful_tool_result()),
        workflow_run_id="finalization-capacity-timeout",
    )

    assert result["status"] == "failed"
    assert result["failure_code"] == "finalization_failed"
    assert result["retryable"] is True
    assert gateway.row["failure_code"] == "finalization_failed"
    assert gateway.row["retryable"] is True
    assert gateway.failure_expected_statuses == ["failed"]


def test_run_backtest_job_persists_workflow_internal_timings_on_success() -> None:
    from workflows.backtest_job import REAL_BACKTEST_JOB_KIND, run_backtest_job

    job = _job_row(
        launch_payload={
            "kind": REAL_BACKTEST_JOB_KIND,
            "schema_version": "backtest_job_launch/v1",
            "request": _request_payload(),
        }
    )
    gateway = FakeBacktestJobGateway(job)

    result = run_backtest_job(
        gateway,
        job_id=str(job["id"]),
        backtest_tool=FakeBacktestTool(_successful_tool_result_with_timings()),
        workflow_run_id="local-run",
        run_id_factory=lambda: "run-workflow",
    )

    assert result["status"] == "succeeded"
    metadata = gateway.row["execution_metadata"]["workflow_backtest"]
    timings = metadata["timings_ms"]
    assert timings["provider_fetch_total"] == pytest.approx(12.346)
    assert timings["engine_compute_total"] == pytest.approx(45.679)
    assert timings["chart_result_build_total"] == pytest.approx(7.891)
    for key in (
        "workflow_task_total",
        "job_fetch",
        "mark_running",
        "backtest_tool_run_total",
        "backtest_finalization",
        "result_readout_total",
        "link_result",
    ):
        assert timings[key] >= 0.0


def test_run_backtest_job_finalization_failure_is_retryable_and_replay_safe() -> None:
    from workflows.backtest_job import REAL_BACKTEST_JOB_KIND, run_backtest_job

    job = _job_row(
        launch_payload={
            "kind": REAL_BACKTEST_JOB_KIND,
            "schema_version": "backtest_job_launch/v1",
            "request": _request_payload(),
        }
    )
    gateway = FakeBacktestJobGateway(job)
    gateway.fail_finalization_after_commit_once = True
    tool = FakeBacktestTool(_successful_tool_result())
    expected_run_id = stable_backtest_run_id("user-1", f"backtest_job:{job['id']}")

    first = run_backtest_job(
        gateway,
        job_id=str(job["id"]),
        backtest_tool=tool,
        workflow_run_id="first-attempt",
    )

    assert first == {
        "job_id": job["id"],
        "status": "failed",
        "failure_code": "finalization_failed",
        "failure_detail": "execution_failed",
        "retryable": True,
        "workflow_run_id": "first-attempt",
        "execution_metadata": gateway.row["execution_metadata"],
    }
    assert gateway.row["result_run_id"] is None
    assert len(gateway.finalization_store.backtest_runs) == 1
    assert len(gateway.finalization_store.evidence_artifacts) == 1

    second = run_backtest_job(
        gateway,
        job_id=str(job["id"]),
        backtest_tool=tool,
        workflow_run_id="retry-attempt",
    )

    assert second["status"] == "succeeded"
    assert second["result_run_id"] == expected_run_id
    assert len(gateway.finalization_store.backtest_runs) == 1
    assert len(gateway.finalization_store.ideas) == 1
    assert len(gateway.finalization_store.idea_versions) == 1
    assert len(gateway.finalization_store.evidence_artifacts) == 1
    assert len(gateway.finalization_calls) == 2


def test_run_backtest_job_result_link_failure_retries_finalized_tuple() -> None:
    from workflows.backtest_job import REAL_BACKTEST_JOB_KIND, run_backtest_job

    job = _job_row(
        launch_payload={
            "kind": REAL_BACKTEST_JOB_KIND,
            "schema_version": "backtest_job_launch/v1",
            "request": _request_payload(),
        }
    )
    gateway = FakeBacktestJobGateway(job)
    gateway.fail_result_link_once = True
    tool = FakeBacktestTool(_successful_tool_result())
    expected_run_id = stable_backtest_run_id("user-1", f"backtest_job:{job['id']}")

    first = run_backtest_job(
        gateway,
        job_id=str(job["id"]),
        backtest_tool=tool,
        workflow_run_id="first-attempt",
    )

    assert first["status"] == "failed"
    assert first["failure_code"] == "finalization_failed"
    assert first["failure_detail"] == "execution_failed"
    assert first["retryable"] is True
    assert gateway.row["result_run_id"] is None
    assert len(gateway.finalization_store.backtest_runs) == 1
    assert len(gateway.finalization_store.evidence_artifacts) == 1

    second = run_backtest_job(
        gateway,
        job_id=str(job["id"]),
        backtest_tool=tool,
        workflow_run_id="retry-attempt",
    )

    assert second["status"] == "succeeded"
    assert second["result_run_id"] == expected_run_id
    assert len(gateway.finalization_store.backtest_runs) == 1
    assert len(gateway.finalization_store.ideas) == 1
    assert len(gateway.finalization_store.idea_versions) == 1
    assert len(gateway.finalization_store.evidence_artifacts) == 1
    assert len(gateway.finalization_calls) == 2


def test_run_backtest_job_reconciles_result_link_response_loss() -> None:
    from workflows.backtest_job import REAL_BACKTEST_JOB_KIND, run_backtest_job

    job = _job_row(
        launch_payload={
            "kind": REAL_BACKTEST_JOB_KIND,
            "schema_version": "backtest_job_launch/v1",
            "request": _request_payload(),
        }
    )
    gateway = FakeBacktestJobGateway(job)
    gateway.fail_result_link_after_commit_once = True
    tool = FakeBacktestTool(_successful_tool_result())
    expected_run_id = stable_backtest_run_id("user-1", f"backtest_job:{job['id']}")

    result = run_backtest_job(
        gateway,
        job_id=str(job["id"]),
        backtest_tool=tool,
        workflow_run_id="ambiguous-link-attempt",
    )

    assert result["status"] == "succeeded"
    assert result["result_run_id"] == expected_run_id
    assert gateway.row["status"] == "succeeded"
    assert gateway.row["result_run_id"] == expected_run_id
    assert gateway.failed_updates == []
    assert len(gateway.finalization_store.backtest_runs) == 1
    assert len(gateway.finalization_store.evidence_artifacts) == 1
    assert tool.calls == [_request_payload()]


def test_run_backtest_job_replay_after_success_does_not_recompute() -> None:
    from workflows.backtest_job import REAL_BACKTEST_JOB_KIND, run_backtest_job

    job = _job_row(
        launch_payload={
            "kind": REAL_BACKTEST_JOB_KIND,
            "schema_version": "backtest_job_launch/v1",
            "request": _request_payload(),
        }
    )
    gateway = FakeBacktestJobGateway(job)
    tool = FakeBacktestTool(_successful_tool_result())

    first = run_backtest_job(
        gateway,
        job_id=str(job["id"]),
        backtest_tool=tool,
        workflow_run_id="first-attempt",
    )
    transitions_after_success = list(gateway.transitions)
    second = run_backtest_job(
        gateway,
        job_id=str(job["id"]),
        backtest_tool=tool,
        workflow_run_id="replayed-task",
    )

    assert second["status"] == "succeeded"
    assert second["result_run_id"] == first["result_run_id"]
    assert tool.calls == [_request_payload()]
    assert gateway.transitions == transitions_after_success
    assert len(gateway.finalization_calls) == 1


def test_run_backtest_job_persists_backend_result_readout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.agent_runtime.result_readout import ResultReadout

    from workflows import backtest_job as workflow_module
    from workflows.backtest_job import REAL_BACKTEST_JOB_KIND, run_backtest_job

    readout = (
        "**Quick take**\n\n"
        "Backend generated readout.\n\n"
        "- Tested: AAPL buy and hold."
    )
    monkeypatch.setattr(
        workflow_module,
        "result_readout_with_metadata_from_backtest_payload",
        lambda **kwargs: ResultReadout(
            text=readout,
            source="llm_explain_stage",
            fallback_used=False,
        ),
    )
    job = _job_row(
        launch_payload={
            "kind": REAL_BACKTEST_JOB_KIND,
            "schema_version": "backtest_job_launch/v1",
            "request": _request_payload(),
        }
    )
    gateway = FakeBacktestJobGateway(job)

    result = run_backtest_job(
        gateway,
        job_id=str(job["id"]),
        backtest_tool=FakeBacktestTool(_successful_tool_result()),
        workflow_run_id="local-run",
        run_id_factory=lambda: "run-workflow",
    )

    assert result["result_readout"] == readout
    metadata = gateway.row["execution_metadata"]["workflow_backtest"]
    assert metadata["result_readout"] == readout
    assert metadata["result_readout_source"] == "llm_explain_stage"
    assert metadata["result_readout_fallback_used"] is False
    saved_run = next(iter(gateway.finalization_store.backtest_runs.values()))
    assert saved_run.conversation_result_card["result_readout_content"] == {
        "schema_version": "result_readout/v1",
        "surface": "quick_take",
        "language": "en",
        "text": readout,
    }


def test_run_backtest_job_restores_guest_openrouter_scope_for_result_readout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.agent_runtime.result_readout import ResultReadout
    from argus.llm.openrouter_key_policy import resolve_openrouter_api_key

    from workflows import backtest_job as workflow_module
    from workflows.backtest_job import REAL_BACKTEST_JOB_KIND, run_backtest_job

    observed_keys: list[str] = []

    def scoped_result_readout(**_: object) -> ResultReadout:
        observed_keys.append(resolve_openrouter_api_key())
        return ResultReadout(
            text="Scoped guest readout.",
            source="llm_explain_stage",
            fallback_used=False,
        )

    monkeypatch.setattr(
        workflow_module,
        "result_readout_with_metadata_from_backtest_payload",
        scoped_result_readout,
    )
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("OPENROUTER_API_KEY", "dev-only")
    monkeypatch.setenv("CUADRAO_PROD_OPENROUTER_API_KEY", "registered-key")
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_OPENROUTER_API_KEY", "guest-key")
    job = _job_row(
        launch_payload={
            "kind": REAL_BACKTEST_JOB_KIND,
            "schema_version": "backtest_job_launch/v1",
            "request": _request_payload(),
        }
    )
    job["execution_metadata"]["openrouter_traffic_class"] = "guest"
    gateway = FakeBacktestJobGateway(job)

    result = run_backtest_job(
        gateway,
        job_id=str(job["id"]),
        backtest_tool=FakeBacktestTool(_successful_tool_result()),
        workflow_run_id="local-run",
        run_id_factory=lambda: "run-workflow",
    )

    assert result["result_readout"] == "Scoped guest readout."
    assert observed_keys == ["guest-key"]
    with pytest.raises(RuntimeError, match="traffic class"):
        resolve_openrouter_api_key()


def test_run_backtest_job_persists_result_summary_route_receipts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.agent_runtime.result_readout import ResultReadout
    from argus.llm.openrouter import (
        clear_openrouter_route_receipts,
        record_openrouter_route_receipt,
    )

    from workflows import backtest_job as workflow_module
    from workflows.backtest_job import REAL_BACKTEST_JOB_KIND, run_backtest_job

    clear_openrouter_route_receipts()

    def fake_result_readout(**_: object) -> ResultReadout:
        record_openrouter_route_receipt(
            task="result_summary",
            model_name="unit-test-model",
            mode="json_schema",
            schema_name="QuickTakeDraft",
            latency_ms=42,
            outcome="succeeded",
            token_usage={
                "prompt_tokens": 21,
                "completion_tokens": 9,
                "total_tokens": 30,
            },
            usage_cost_usd=0.0009,
            context_packet_ids=["packet-1"],
        )
        return ResultReadout(
            text="**Quick take**\n\nAAPL beat SPY in this test.",
            source="llm_explain_stage",
            fallback_used=False,
        )

    monkeypatch.setattr(
        workflow_module,
        "result_readout_with_metadata_from_backtest_payload",
        fake_result_readout,
    )
    job = _job_row(
        launch_payload={
            "kind": REAL_BACKTEST_JOB_KIND,
            "schema_version": "backtest_job_launch/v1",
            "request": _request_payload(),
        }
    )
    gateway = FakeBacktestJobGateway(job)

    result = run_backtest_job(
        gateway,
        job_id=str(job["id"]),
        backtest_tool=FakeBacktestTool(_successful_tool_result()),
        workflow_run_id="local-run",
        run_id_factory=lambda: "run-workflow",
    )

    assert result["status"] == "succeeded"
    assert len(gateway.route_receipts) == 1
    receipt = gateway.route_receipts[0]
    assert receipt["user_id"] == "user-1"
    assert receipt["conversation_id"] == "conversation-1"
    assert receipt["run_id"] == "run-workflow"
    assert receipt["metadata"] == {
        "job_id": job["id"],
        "workflow_run_id": "local-run",
        "source": "render_workflow",
    }
    assert receipt["task"] == "result_summary"
    assert receipt["tier"] == "readout"
    assert receipt["model"] == "unit-test-model"
    assert receipt["mode"] == "json_schema"
    assert receipt["schema_name"] == "QuickTakeDraft"
    assert receipt["latency_ms"] == 42
    assert receipt["outcome"] == "succeeded"
    assert receipt["failure_mode"] is None
    assert receipt["fallback_used"] is False
    assert receipt["context_packet_ids"] == ["packet-1"]
    assert len(gateway.cost_ledger_entries) == 1
    ledger_entry = gateway.cost_ledger_entries[0]
    assert ledger_entry["source"] == "render_workflow"
    assert ledger_entry["provider"] == "openrouter"
    assert ledger_entry["model"] == "unit-test-model"
    assert ledger_entry["backtest_run_id"] == "run-workflow"
    assert ledger_entry["backtest_job_id"] == job["id"]
    assert ledger_entry["route_receipt_id"] == "receipt-1"
    assert (
        ledger_entry["correlation_id"] == f"workflow:local-run:{job['id']}:run-workflow"
    )
    assert ledger_entry["total_tokens"] == 30
    assert ledger_entry["cost_amount"] == 0.0009


def test_run_backtest_job_succeeds_when_cost_ledger_table_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.agent_runtime.result_readout import ResultReadout
    from argus.llm.openrouter import (
        clear_openrouter_route_receipts,
        record_openrouter_route_receipt,
    )
    from argus.observability import cost_ledger as cost_ledger_module

    from workflows import backtest_job as workflow_module
    from workflows.backtest_job import REAL_BACKTEST_JOB_KIND, run_backtest_job

    class UnavailableCostLedgerGateway(FakeBacktestJobGateway):
        def create_cost_ledger_entry(
            self,
            *,
            entry: dict[str, object],
        ) -> dict[str, object]:
            del entry
            raise RuntimeError("PGRST205: cost_ledger_entries is unavailable")

    class WarningCapture:
        def __init__(self) -> None:
            self.records: list[tuple[str, dict[str, object]]] = []

        def warning(self, message: str, **context: object) -> None:
            self.records.append((message, context))

    clear_openrouter_route_receipts()

    def fake_result_readout(**_: object) -> ResultReadout:
        record_openrouter_route_receipt(
            task="result_summary",
            model_name="unit-test-model",
            mode="json_schema",
            schema_name="QuickTakeDraft",
            latency_ms=42,
            outcome="succeeded",
            token_usage={
                "prompt_tokens": 21,
                "completion_tokens": 9,
                "total_tokens": 30,
            },
            usage_cost_usd=0.0009,
        )
        return ResultReadout(
            text="**Quick take**\n\nAAPL beat SPY in this test.",
            source="llm_explain_stage",
            fallback_used=False,
        )

    warning_capture = WarningCapture()
    monkeypatch.setattr(cost_ledger_module, "logger", warning_capture)
    monkeypatch.setattr(
        workflow_module,
        "result_readout_with_metadata_from_backtest_payload",
        fake_result_readout,
    )
    job = _job_row(
        launch_payload={
            "kind": REAL_BACKTEST_JOB_KIND,
            "schema_version": "backtest_job_launch/v1",
            "request": _request_payload(),
        }
    )
    gateway = UnavailableCostLedgerGateway(job)

    result = run_backtest_job(
        gateway,
        job_id=str(job["id"]),
        backtest_tool=FakeBacktestTool(_successful_tool_result()),
        workflow_run_id="local-run",
        run_id_factory=lambda: "run-workflow",
    )

    assert result["status"] == "succeeded"
    assert result["result_run_id"] == "run-workflow"
    assert gateway.transitions == ["running", "finalize", "succeeded"]
    assert len(gateway.route_receipts) == 1
    assert gateway.cost_ledger_entries == []
    assert len(warning_capture.records) == 1
    message, context = warning_capture.records[0]
    assert message == "Cost ledger persistence failed; continuing without spend row"
    assert context["failure_classification"] == "telemetry_only"
    assert context["source"] == "render_workflow"


def test_run_backtest_job_uses_mainline_llm_quick_take_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.agent_runtime.stages import explain as explain_module

    from tests.result_readout_fixtures import readout_draft
    from workflows.backtest_job import REAL_BACKTEST_JOB_KIND, run_backtest_job

    model_takeaway = "AAPL beat SPY by 4.2 percentage points in this historical test."
    model_tested_bullet = "Tested AAPL buy and hold over the requested window."
    model_meaning_bullet = "The result is grounded in the completed backtest run."

    async def fake_quick_take_plan(**_: object) -> dict[str, object]:
        return readout_draft(
            "\n\n".join([model_takeaway, model_tested_bullet, model_meaning_bullet]),
            [("portfolio.benchmark_gap", 4.2)],
        )

    monkeypatch.setattr(
        explain_module,
        "invoke_openrouter_json_schema",
        fake_quick_take_plan,
    )
    job = _job_row(
        launch_payload={
            "kind": REAL_BACKTEST_JOB_KIND,
            "schema_version": "backtest_job_launch/v1",
            "request": _request_payload(),
        }
    )
    gateway = FakeBacktestJobGateway(job)

    result = run_backtest_job(
        gateway,
        job_id=str(job["id"]),
        backtest_tool=FakeBacktestTool(_successful_tool_result()),
        workflow_run_id="local-run",
        run_id_factory=lambda: "run-workflow",
    )

    readout = result["result_readout"]
    assert readout.splitlines()[0] == model_takeaway
    assert model_tested_bullet in readout
    assert model_meaning_bullet in readout
    metadata = gateway.row["execution_metadata"]["workflow_backtest"]
    assert metadata["result_readout_source"] == "llm_explain_stage"
    assert metadata["result_readout_fallback_used"] is False
    assert "result_readout_failure_mode" not in metadata


def test_run_backtest_job_marks_result_readout_fallback_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.agent_runtime.stages import explain as explain_module

    from workflows.backtest_job import REAL_BACKTEST_JOB_KIND, run_backtest_job

    async def failing_quick_take_plan(**_: object) -> dict[str, object]:
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(
        explain_module,
        "invoke_openrouter_json_schema",
        failing_quick_take_plan,
    )
    job = _job_row(
        launch_payload={
            "kind": REAL_BACKTEST_JOB_KIND,
            "schema_version": "backtest_job_launch/v1",
            "request": _request_payload(),
        }
    )
    gateway = FakeBacktestJobGateway(job)

    result = run_backtest_job(
        gateway,
        job_id=str(job["id"]),
        backtest_tool=FakeBacktestTool(_successful_tool_result()),
        workflow_run_id="local-run",
        run_id_factory=lambda: "run-workflow",
    )

    readout = result["result_readout"]
    assert "12.3%" in readout
    assert "SPY" in readout
    assert "8.1%" in readout
    assert "outperformed by 4.2 percentage points" in readout
    metadata = gateway.row["execution_metadata"]["workflow_backtest"]
    assert metadata["result_readout_source"] == "deterministic_fallback"
    assert metadata["result_readout_fallback_used"] is True
    assert metadata["result_readout_failure_mode"] == "llm_unavailable_or_rejected"
    saved_run = next(iter(gateway.finalization_store.backtest_runs.values()))
    assert saved_run.conversation_result_card["result_readout_content"] == {
        "schema_version": "result_readout/v1",
        "surface": "quick_take",
        "language": "en",
        "text": None,
    }


def test_run_backtest_job_marks_tool_failure_with_structured_metadata() -> None:
    from workflows.backtest_job import REAL_BACKTEST_JOB_KIND, run_backtest_job

    job = _job_row(
        launch_payload={
            "kind": REAL_BACKTEST_JOB_KIND,
            "schema_version": "backtest_job_launch/v1",
            "request": _request_payload(),
        }
    )
    gateway = FakeBacktestJobGateway(job)
    tool = FakeBacktestTool(
        {
            "success": False,
            "payload": None,
            "error_type": "upstream_dependency_error",
            "error_message": "Market data is temporarily unavailable.",
            "retryable": True,
            "capability_context": {"failure_detail": "market_data_issue"},
        }
    )

    result = run_backtest_job(
        gateway,
        job_id=str(job["id"]),
        backtest_tool=tool,
        workflow_run_id="local-run",
    )

    assert result["job_id"] == job["id"]
    assert result["status"] == "failed"
    assert result["failure_code"] == "upstream_dependency_error"
    assert result["failure_detail"] == "market_data_issue"
    assert result["retryable"] is True
    assert gateway.transitions == ["running", "failed"]
    assert gateway.finalization_calls == []
    assert gateway.row["failure_code"] == "upstream_dependency_error"
    assert gateway.row["failure_detail"] == "market_data_issue"
    assert gateway.row["retryable"] is True
    assert (
        gateway.row["execution_metadata"]["workflow_backtest"]["failure_category"]
        == "upstream_dependency_error"
    )
    timings = gateway.row["execution_metadata"]["workflow_backtest"]["timings_ms"]
    assert timings["workflow_task_total"] >= 0.0
    assert timings["job_fetch"] >= 0.0
    assert timings["mark_running"] >= 0.0
    assert timings["backtest_tool_run_total"] >= 0.0


def test_run_backtest_job_preserves_safe_coverage_drift_failure_code() -> None:
    from workflows.backtest_job import REAL_BACKTEST_JOB_KIND, run_backtest_job

    job = _job_row(
        launch_payload={
            "kind": REAL_BACKTEST_JOB_KIND,
            "schema_version": "backtest_job_launch/v1",
            "request": _request_payload(),
        }
    )
    gateway = FakeBacktestJobGateway(job)
    tool = FakeBacktestTool(
        {
            "success": False,
            "payload": None,
            "error_type": "parameter_validation_error",
            "error_message": "Review the refreshed dates and approve again.",
            "retryable": False,
            "capability_context": {
                "failure_code": "approved_data_window_unavailable",
                "failure_detail": "approved_data_window_unavailable",
            },
        }
    )

    result = run_backtest_job(
        gateway,
        job_id=str(job["id"]),
        backtest_tool=tool,
        workflow_run_id="local-run",
    )

    assert result["status"] == "failed"
    assert result["failure_code"] == "approved_data_window_unavailable"
    assert gateway.row["failure_code"] == "approved_data_window_unavailable"
    assert gateway.row["result_run_id"] is None
    assert gateway.finalization_calls == []
    assert (
        gateway.row["execution_metadata"]["workflow_backtest"]["failure_category"]
        == "parameter_validation_error"
    )


def test_run_backtest_job_rejects_untrusted_nested_failure_code() -> None:
    from workflows.backtest_job import REAL_BACKTEST_JOB_KIND, run_backtest_job

    job = _job_row(
        launch_payload={
            "kind": REAL_BACKTEST_JOB_KIND,
            "schema_version": "backtest_job_launch/v1",
            "request": _request_payload(),
        }
    )
    gateway = FakeBacktestJobGateway(job)
    tool = FakeBacktestTool(
        {
            "success": False,
            "payload": None,
            "error_type": "upstream_dependency_error",
            "error_message": "Market data is temporarily unavailable.",
            "retryable": True,
            "capability_context": {
                "failure_code": "internal_provider_secret_code",
                "failure_detail": "alpaca_provider_internal_timeout_bucket_17",
            },
        }
    )

    result = run_backtest_job(
        gateway,
        job_id=str(job["id"]),
        backtest_tool=tool,
        workflow_run_id="local-run",
    )

    assert result["failure_code"] == "upstream_dependency_error"
    assert result["failure_detail"] == "temporary_dependency_issue"
    assert gateway.row["failure_code"] == "upstream_dependency_error"
    assert gateway.row["failure_detail"] == "temporary_dependency_issue"
    assert (
        gateway.row["execution_metadata"]["workflow_backtest"]["failure_category"]
        == "upstream_dependency_error"
    )


def test_run_backtest_job_tool_failure_preserves_collected_timings() -> None:
    from workflows.backtest_job import REAL_BACKTEST_JOB_KIND, run_backtest_job

    job = _job_row(
        launch_payload={
            "kind": REAL_BACKTEST_JOB_KIND,
            "schema_version": "backtest_job_launch/v1",
            "request": _request_payload(),
        }
    )
    gateway = FakeBacktestJobGateway(job)
    tool = FakeBacktestTool(
        {
            "success": False,
            "payload": None,
            "error_type": "market_data_unavailable",
            "error_message": "Market data is temporarily unavailable.",
            "retryable": True,
            "capability_context": {"failure_detail": "market_data_issue"},
            "execution_metadata": {
                "timings_ms": {
                    "provider_fetch_total": 22.2222,
                    "engine_compute_total": 33.3333,
                }
            },
        }
    )

    result = run_backtest_job(
        gateway,
        job_id=str(job["id"]),
        backtest_tool=tool,
        workflow_run_id="local-run",
    )

    assert result["status"] == "failed"
    metadata = gateway.row["execution_metadata"]["workflow_backtest"]
    assert metadata["failure_category"] == "market_data_unavailable"
    assert metadata["failure_detail"] == "market_data_issue"
    timings = metadata["timings_ms"]
    assert timings["provider_fetch_total"] == pytest.approx(22.222)
    assert timings["engine_compute_total"] == pytest.approx(33.333)
    assert timings["workflow_task_total"] >= 0.0
    assert timings["backtest_tool_run_total"] >= 0.0


def test_backtest_workflow_json_safe_normalizes_postgres_scalars() -> None:
    from workflows.backtest_job import _json_safe

    user_id = uuid4()
    created_at = datetime(2026, 6, 6, 12, 30, tzinfo=timezone.utc)
    payload = {
        "id": user_id,
        "created_at": created_at,
        "nested": {"date": date(2026, 6, 6), "uuids": [UUID(str(user_id))]},
    }

    assert _json_safe(payload) == {
        "id": str(user_id),
        "created_at": created_at.isoformat(),
        "nested": {"date": "2026-06-06", "uuids": [str(user_id)]},
    }


def test_workflow_task_registration_includes_proof_and_real_backtest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.llm import openrouter_key_policy

    tasks: dict[str, dict[str, object]] = {}
    boot_events: list[str] = []
    monkeypatch.setattr(
        openrouter_key_policy,
        "validate_hosted_openrouter_configuration",
        lambda: boot_events.append("validate"),
    )

    class FakeRetry:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    class FakeWorkflows:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs
            boot_events.append("construct")

        def task(self, fn: object | None = None, **kwargs: object):
            def decorate(inner: object) -> object:
                name = str(kwargs.get("name") or getattr(inner, "__name__", "task"))
                tasks[name] = {"fn": inner, "kwargs": dict(kwargs)}
                return inner

            if fn is not None:
                return decorate(fn)
            return decorate

        def start(self) -> None:
            return None

    fake_render_sdk = ModuleType("render_sdk")
    fake_render_sdk.Retry = FakeRetry
    fake_render_sdk.Workflows = FakeWorkflows
    monkeypatch.setitem(sys.modules, "render_sdk", fake_render_sdk)
    sys.modules.pop("workflows.main", None)

    module = importlib.import_module("workflows.main")

    assert boot_events[:2] == ["validate", "construct"]
    assert {"workflow_proof", "run_backtest_job"}.issubset(tasks)
    assert tasks["workflow_proof"]["kwargs"]["timeout_seconds"] == 60
    assert tasks["run_backtest_job"]["kwargs"]["timeout_seconds"] >= 300
    assert tasks["run_backtest_job"]["kwargs"]["plan"] == "standard"
    retry = tasks["run_backtest_job"]["kwargs"]["retry"]
    assert isinstance(retry, FakeRetry)
    assert retry.kwargs == {"max_retries": 1, "wait_duration_ms": 1000}

    class FakeGatewayContext:
        def __enter__(self) -> FakeGatewayContext:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        @classmethod
        def from_env(cls) -> FakeGatewayContext:
            return cls()

    monkeypatch.setattr(module, "PostgresBacktestJobGateway", FakeGatewayContext)
    monkeypatch.setattr(
        module,
        "run_backtest_job_workflow",
        lambda *_args, **_kwargs: {
            "status": "failed",
            "execution_metadata": {
                "source": "public_alpha_capacity_load",
                "ops_authority": "service_role",
                "capacity_probe": {"mode": "invalid_envelope"},
            },
        },
    )

    with pytest.raises(RuntimeError, match="Controlled public-alpha capacity probe"):
        module.run_backtest_job("opaque-job")


def test_capacity_probe_marker_is_never_read_from_public_launch_payload() -> None:
    from workflows.backtest_job import capacity_probe_mode

    assert (
        capacity_probe_mode(
            {
                "launch_payload": {
                    "source": "public_alpha_capacity_load",
                    "capacity_probe": {"mode": "upstream_transient_once"},
                },
                "execution_metadata": {
                    "source": "api_chat",
                    "ops_authority": "service_role",
                },
            }
        )
        is None
    )


def test_controlled_upstream_probe_fails_once_then_runs_normally() -> None:
    from workflows.backtest_job import (
        REAL_BACKTEST_JOB_KIND,
        capacity_probe_should_raise,
        run_backtest_job,
    )

    job = _job_row(
        launch_payload={
            "kind": REAL_BACKTEST_JOB_KIND,
            "schema_version": "backtest_job_launch/v1",
            "request": _request_payload(),
        }
    )
    job["execution_metadata"] = {
        "source": "public_alpha_capacity_load",
        "ops_authority": "service_role",
        "openrouter_traffic_class": "registered",
        "capacity_probe": {"mode": "upstream_transient_once"},
    }
    gateway = FakeBacktestJobGateway(job)
    tool = FakeBacktestTool(_successful_tool_result())

    first = run_backtest_job(
        gateway,
        job_id=str(job["id"]),
        backtest_tool=tool,
        workflow_run_id="attempt-1",
    )

    assert first["status"] == "failed"
    assert first["failure_code"] == "failed_upstream"
    assert first["retryable"] is True
    assert gateway.row["attempts"] == 1
    assert capacity_probe_should_raise(first) is True
    assert tool.calls == []

    second = run_backtest_job(
        gateway,
        job_id=str(job["id"]),
        backtest_tool=tool,
        workflow_run_id="attempt-2",
    )

    assert second["status"] == "succeeded"
    assert gateway.row["attempts"] == 2
    assert capacity_probe_should_raise(second) is False
    assert tool.calls == [_request_payload()]


def test_invalid_capacity_probe_records_two_attempts_and_terminal_failure() -> None:
    from workflows.backtest_job import (
        REAL_BACKTEST_JOB_KIND,
        capacity_probe_should_raise,
        run_backtest_job,
    )

    job = _job_row(
        launch_payload={
            "kind": REAL_BACKTEST_JOB_KIND,
            "schema_version": "backtest_job_launch/v1",
            "request": "not-an-object",
        }
    )
    job["execution_metadata"] = {
        "source": "public_alpha_capacity_load",
        "ops_authority": "service_role",
        "openrouter_traffic_class": "registered",
        "capacity_probe": {"mode": "invalid_envelope"},
    }
    gateway = FakeBacktestJobGateway(job)
    tool = FakeBacktestTool(_successful_tool_result())

    first = run_backtest_job(
        gateway,
        job_id=str(job["id"]),
        backtest_tool=tool,
        workflow_run_id="attempt-1",
    )

    assert first["failure_code"] == "invalid_job_contract"
    assert first["retryable"] is True
    assert capacity_probe_should_raise(first) is True

    second = run_backtest_job(
        gateway,
        job_id=str(job["id"]),
        backtest_tool=tool,
        workflow_run_id="attempt-2",
    )

    assert second["failure_code"] == "invalid_job_contract"
    assert second["retryable"] is False
    assert gateway.row["attempts"] == 2
    assert capacity_probe_should_raise(second) is True
    assert tool.calls == []
