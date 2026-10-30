#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import resource
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, NamedTuple
from uuid import uuid4

import psutil

FORBIDDEN_BACKTEST_COMPUTE_MODULE_PREFIXES = (
    "numpy",
    "pandas",
    "vectorbt",
    "vectorbtpro",
    "numba",
    "scipy",
    "argus.analysis",
    "argus.domain.engine",
    "argus.domain.backtesting.charts",
    "argus.domain.backtesting.execution",
    "argus.domain.backtesting.metrics",
    "argus.domain.backtesting.runner",
    "argus.domain.backtesting.signals",
    "argus.domain.engine_launch.adapter",
    "argus.domain.indicator_execution",
    "argus.domain.market_data.provider",
)

LOCAL_PROVIDER_MODES = {
    "synthetic_unit_fixture",
    "recorded_provider_fixture",
    "live_provider",
}


class BenchmarkCase(NamedTuple):
    case_id: str
    label: str
    request: dict[str, Any]


def default_output_dir(repo_root: Path) -> Path:
    return repo_root / "temp" / "benchmarks" / "backtest-infra"


def benchmark_cases() -> list[BenchmarkCase]:
    equity_start = "2019-06-05"
    crypto_start = "2023-06-05"
    end = "2026-06-05"
    base_equity = {
        "asset_class": "equity",
        "timeframe": "1D",
        "date_range": {"start": equity_start, "end": end},
        "sizing_mode": "capital_amount",
        "capital_amount": 10_000,
        "benchmark_symbol": "SPY",
        "language": "en",
    }
    base_crypto = {
        "asset_class": "crypto",
        "timeframe": "4h",
        "date_range": {"start": crypto_start, "end": end},
        "sizing_mode": "capital_amount",
        "capital_amount": 10_000,
        "benchmark_symbol": "BTC",
        "language": "en",
    }

    return [
        BenchmarkCase(
            case_id="equity_1_symbol_7y_1d_buy_hold",
            label="1 symbol, 7 years, 1D, equity, buy-and-hold",
            request={
                **base_equity,
                "strategy_type": "buy_and_hold",
                "symbol": "AAPL",
                "symbols": ["AAPL"],
            },
        ),
        BenchmarkCase(
            case_id="equity_5_symbol_7y_1d_buy_hold",
            label="5 symbols, 7 years, 1D, equity, equal-weight buy-and-hold",
            request={
                **base_equity,
                "strategy_type": "buy_and_hold",
                "symbol": "AAPL",
                "symbols": ["AAPL", "MSFT", "NVDA", "TSLA", "META"],
            },
        ),
        BenchmarkCase(
            case_id="crypto_1_symbol_3y_4h_buy_hold",
            label="1 symbol, 3 years, 4h, crypto, buy-and-hold",
            request={
                **base_crypto,
                "strategy_type": "buy_and_hold",
                "symbol": "BTC",
                "symbols": ["BTC"],
            },
        ),
        BenchmarkCase(
            case_id="equity_1_symbol_7y_1d_dca_monthly",
            label="1 symbol, 7 years, 1D, equity, DCA monthly",
            request={
                **base_equity,
                "strategy_type": "dca_accumulation",
                "symbol": "AAPL",
                "symbols": ["AAPL"],
                "capital_amount": 500,
                "cadence": "monthly",
            },
        ),
        BenchmarkCase(
            case_id="equity_1_symbol_7y_1d_dca_weekly",
            label="1 symbol, 7 years, 1D, equity, DCA weekly",
            request={
                **base_equity,
                "strategy_type": "dca_accumulation",
                "symbol": "AAPL",
                "symbols": ["AAPL"],
                "capital_amount": 125,
                "cadence": "weekly",
            },
        ),
        BenchmarkCase(
            case_id="equity_1_symbol_7y_1d_rsi_threshold",
            label="1 symbol, 7 years, 1D, equity, RSI threshold",
            request={
                **base_equity,
                "strategy_type": "indicator_threshold",
                "symbol": "TSLA",
                "symbols": ["TSLA"],
                "entry_rule": {
                    "indicator": "rsi",
                    "operator": "below",
                    "threshold": 30,
                    "period": 14,
                },
                "exit_rule": {
                    "indicator": "rsi",
                    "operator": "above",
                    "threshold": 55,
                    "period": 14,
                },
            },
        ),
        BenchmarkCase(
            case_id="equity_1_symbol_7y_1d_ma_crossover",
            label="1 symbol, 7 years, 1D, equity, moving-average crossover",
            request={
                **base_equity,
                "strategy_type": "signal_strategy",
                "symbol": "TSLA",
                "symbols": ["TSLA"],
                "entry_rule": {
                    "type": "moving_average_crossover",
                    "fast_period": 50,
                    "slow_period": 200,
                    "direction": "bullish",
                },
                "exit_rule": {
                    "type": "moving_average_crossover",
                    "fast_period": 50,
                    "slow_period": 200,
                    "direction": "bearish",
                },
            },
        ),
    ]


def run_backpressure_smoke() -> dict[str, Any]:
    from argus.api.chat.backtest_jobs import (
        BacktestJobBackpressureLimits,
        _backpressure_reason,
    )

    limits = BacktestJobBackpressureLimits(
        user_running=1,
        user_queued=2,
        global_running=5,
        global_queued=10,
    )

    class CountingGateway:
        def __init__(self, counts: dict[tuple[str, str | None], int]) -> None:
            self.counts = counts

        def count_backtest_jobs(
            self,
            *,
            status: str,
            user_id: str | None = None,
            limit: int = 100,
        ) -> int:
            return min(self.counts.get((status, user_id), 0), limit)

    def check(name: str, counts: dict[tuple[str, str | None], int]) -> dict[str, Any]:
        reason = _backpressure_reason(
            gateway=CountingGateway(counts),
            user_id="user-1",
            limits=limits,
        )
        return {
            "name": name,
            "admitted": reason is None,
            "reason": reason,
            "counts": {
                f"{status}:{user or 'global'}": count
                for (status, user), count in counts.items()
            },
        }

    return {
        "limits": {
            "user_running": limits.user_running,
            "user_queued": limits.user_queued,
            "global_running": limits.global_running,
            "global_queued": limits.global_queued,
        },
        "checks": [
            check("under_limits", {}),
            check("user_running_limit", {("running", "user-1"): 1}),
            check("user_queued_limit", {("queued", "user-1"): 2}),
            check("global_running_limit", {("running", None): 5}),
            check("global_queued_limit", {("queued", None): 10}),
        ],
    }


def run_api_import_probe(repo_root: Path) -> dict[str, Any]:
    return _run_json_child(
        repo_root,
        ["__api_import_probe"],
        timeout_seconds=60,
        env_patch=_base_probe_env(repo_root),
    )


def run_workflow_import_probe(repo_root: Path) -> dict[str, Any]:
    return _run_json_child(
        repo_root,
        ["__workflow_import_probe"],
        timeout_seconds=90,
        env_patch=_base_probe_env(repo_root),
    )


def run_workflow_case_probe(
    repo_root: Path,
    case: BenchmarkCase,
    *,
    provider_mode: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    env_patch = _base_probe_env(repo_root)
    env_patch.update(
        {
            "ARGUS_MARKET_DATA_PROVIDER_MODE": provider_mode,
            "ENABLE_MARKET_DATA_CACHE": "false",
        }
    )
    return _run_json_child(
        repo_root,
        ["__workflow_case_probe", case.case_id],
        timeout_seconds=timeout_seconds,
        env_patch=env_patch,
    )


def _run_json_child(
    repo_root: Path,
    args: list[str],
    *,
    timeout_seconds: float,
    env_patch: dict[str, str],
) -> dict[str, Any]:
    env = os.environ.copy()
    env.update(env_patch)
    command = [sys.executable, str(Path(__file__).resolve()), *args]
    started = time.perf_counter()
    with (
        tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stdout_file,
        tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stderr_file,
    ):
        process = subprocess.Popen(
            command,
            cwd=repo_root,
            env=env,
            stdout=stdout_file,
            stderr=stderr_file,
            text=True,
        )
        peak_rss = 0
        ps_process = psutil.Process(process.pid)
        deadline = time.perf_counter() + timeout_seconds
        while process.poll() is None:
            peak_rss = max(peak_rss, _rss_for_process_tree(ps_process))
            if time.perf_counter() > deadline:
                process.kill()
                process.wait()
                stdout_file.seek(0)
                stderr_file.seek(0)
                stdout = stdout_file.read()
                stderr = stderr_file.read()
                raise RuntimeError(
                    f"benchmark child timed out after {timeout_seconds:.1f}s: "
                    f"{' '.join(args)}\n{stdout}\n{stderr}"
                )
            time.sleep(0.02)

        peak_rss = max(peak_rss, _rss_for_process_tree(ps_process))
        stdout_file.seek(0)
        stderr_file.seek(0)
        stdout = stdout_file.read()
        stderr = stderr_file.read()
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    if process.returncode != 0:
        raise RuntimeError(
            f"benchmark child failed with exit {process.returncode}: "
            f"{' '.join(args)}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
        )
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"benchmark child did not emit JSON: {' '.join(args)}\n"
            f"STDOUT:\n{stdout}\nSTDERR:\n{stderr}"
        ) from exc
    payload["subprocess"] = {
        "elapsed_ms": round(elapsed_ms, 3),
        "peak_rss_mb": _bytes_to_mb(peak_rss),
        "stderr": stderr.strip(),
    }
    return payload


def _rss_for_process_tree(process: psutil.Process) -> int:
    total = 0
    try:
        total += process.memory_info().rss
        for child in process.children(recursive=True):
            try:
                total += child.memory_info().rss
            except psutil.Error:
                continue
    except psutil.Error:
        return 0
    return total


def _base_probe_env(repo_root: Path) -> dict[str, str]:
    pythonpath_entries = [str(repo_root / "src"), str(repo_root)]
    existing_pythonpath = os.environ.get("PYTHONPATH")
    if existing_pythonpath:
        pythonpath_entries.append(existing_pythonpath)
    return {
        "PYTHONPATH": os.pathsep.join(pythonpath_entries),
        "CUADRAO_PERSISTENCE_MODE": "memory",
        "CUADRAO_CHECKPOINTER_MODE": "memory",
        "ARGUS_DEV_MEMORY_FALLBACK": "true",
        "CUADRAO_MOCK_AUTH": "true",
        "ARGUS_BACKTEST_JOBS_SHADOW_ENABLED": "true",
        "ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED": "true",
        "ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED": "true",
        "ARGUS_MARKET_DATA_PROVIDER_MODE": "synthetic_unit_fixture",
        "CUADRAO_OPS_TOKEN": "benchmark-token",
    }


def _child_api_import_probe() -> None:
    baseline = _rss_mb()
    before_import = time.perf_counter()
    from argus.api import state as api_state
    from argus.api.main import app

    after_import_ms = (time.perf_counter() - before_import) * 1000.0
    after_import = _rss_mb()
    from fastapi.testclient import TestClient

    before_health = time.perf_counter()
    with TestClient(app) as client:
        response = client.get("/health")
        health_status_code = response.status_code
        health_body = response.json()
    health_ms = (time.perf_counter() - before_health) * 1000.0
    after_health = _rss_mb()
    forbidden_after_health = _forbidden_loaded()

    before_readiness = time.perf_counter()
    with TestClient(app) as client:
        readiness_response = client.get(
            "/internal/readiness?force=true",
            headers={"Authorization": "Bearer benchmark-token"},
        )
        readiness_status_code = readiness_response.status_code
        readiness_body = readiness_response.json()
    readiness_ms = (time.perf_counter() - before_readiness) * 1000.0
    forbidden_after_readiness = _forbidden_loaded()

    workflow = api_state.get_agent_runtime_workflow()
    workflow_loaded = workflow is not None
    forbidden_after_workflow = _forbidden_loaded()

    _emit_json(
        {
            "rss_mb": {
                "baseline": baseline,
                "after_import": after_import,
                "after_health": after_health,
                "ru_maxrss": _rss_mb(),
            },
            "timings_ms": {
                "api_main_import": round(after_import_ms, 3),
                "health": round(health_ms, 3),
                "readiness": round(readiness_ms, 3),
            },
            "health_status_code": health_status_code,
            "health_body": health_body,
            "readiness_status_code": readiness_status_code,
            "readiness_body": readiness_body,
            "workflow_loaded": workflow_loaded,
            "forbidden_loaded": forbidden_after_health,
            "forbidden_after_readiness": forbidden_after_readiness,
            "forbidden_after_workflow": forbidden_after_workflow,
        }
    )


def _child_workflow_import_probe() -> None:
    baseline = _rss_mb()
    before_workflow_import = time.perf_counter()
    import workflows.backtest_job  # noqa: F401

    workflow_import_ms = (time.perf_counter() - before_workflow_import) * 1000.0
    after_workflow_module = _rss_mb()
    before_tool_import = time.perf_counter()
    from argus.agent_runtime.tools.real_backtest import RealBacktestTool

    tool_import_ms = (time.perf_counter() - before_tool_import) * 1000.0
    tool = RealBacktestTool()
    after_backtest_tool = _rss_mb()
    del tool

    _emit_json(
        {
            "rss_mb": {
                "baseline": baseline,
                "after_workflow_module": after_workflow_module,
                "after_backtest_tool": after_backtest_tool,
                "ru_maxrss": _rss_mb(),
            },
            "timings_ms": {
                "workflow_module_import": round(workflow_import_ms, 3),
                "backtest_tool_import": round(tool_import_ms, 3),
            },
            "heavy_modules_loaded": _heavy_loaded(),
        }
    )


def _child_workflow_case_probe(case_id: str) -> None:
    case_by_id = {case.case_id: case for case in benchmark_cases()}
    if case_id not in case_by_id:
        raise SystemExit(f"unknown benchmark case: {case_id}")
    case = case_by_id[case_id]
    provider_mode = os.getenv("ARGUS_MARKET_DATA_PROVIDER_MODE", "synthetic_unit_fixture")

    from argus.agent_runtime.tools.real_backtest import RealBacktestTool

    from workflows import backtest_job as workflow_module
    from workflows.backtest_job import REAL_BACKTEST_JOB_KIND, run_backtest_job

    recorder = _PhaseRecorder()
    _install_phase_instrumentation(recorder=recorder, provider_mode=provider_mode)
    workflow_module.result_readout_with_metadata_from_backtest_payload = (
        lambda **_: SimpleNamespace(
            text=None,
            source="benchmark_skipped",
            fallback_used=False,
            failure_mode=None,
        )
    )

    job_id = str(uuid4())
    gateway = _BenchmarkGateway(
        {
            "id": job_id,
            "user_id": "benchmark-user",
            "conversation_id": "benchmark-conversation",
            "status": "queued",
            "attempts": 0,
            "launch_payload": {
                "kind": REAL_BACKTEST_JOB_KIND,
                "schema_version": "backtest_job_launch/v1",
                "request": case.request,
            },
            "execution_metadata": {"benchmark": {"case_id": case.case_id}},
            "result_run_id": None,
        },
        recorder=recorder,
    )

    started = time.perf_counter()
    result = run_backtest_job(
        gateway,
        job_id=job_id,
        backtest_tool=RealBacktestTool(),
        workflow_run_id="local-benchmark",
    )
    wall_ms = (time.perf_counter() - started) * 1000.0

    provider_fetch_ms = recorder.provider_fetch_ms
    compute_total_ms = recorder.timings_ms.get("engine_compute_total", 0.0)
    chart_total_ms = recorder.timings_ms.get("chart_build_total", 0.0)
    _emit_json(
        {
            "case_id": case.case_id,
            "label": case.label,
            "provider_mode": provider_mode,
            "status": result.get("status"),
            "result_run_id": result.get("result_run_id"),
            "failure_code": result.get("failure_code"),
            "timings_ms": {
                "workflow_execution_wall": round(wall_ms, 3),
                "provider_fetch_total": round(provider_fetch_ms, 3),
                "provider_fetch_during_compute": round(
                    recorder.provider_fetch_by_phase.get("engine_compute", 0.0),
                    3,
                ),
                "provider_fetch_during_chart": round(
                    recorder.provider_fetch_by_phase.get("chart_build", 0.0),
                    3,
                ),
                "engine_compute_total": round(compute_total_ms, 3),
                "engine_compute_net": round(
                    max(
                        compute_total_ms
                        - recorder.provider_fetch_by_phase.get("engine_compute", 0.0),
                        0.0,
                    ),
                    3,
                ),
                "chart_build_total": round(chart_total_ms, 3),
                "chart_build_net": round(
                    max(
                        chart_total_ms
                        - recorder.provider_fetch_by_phase.get("chart_build", 0.0),
                        0.0,
                    ),
                    3,
                ),
                "result_card_build": round(
                    recorder.timings_ms.get("result_card_build", 0.0),
                    3,
                ),
                "fake_persistence": round(recorder.persistence_ms, 3),
            },
            "provider_fetch": {
                "calls": recorder.provider_fetch_calls,
                "rows": recorder.provider_fetch_rows,
                "by_phase_ms": {
                    phase: round(value, 3)
                    for phase, value in recorder.provider_fetch_by_phase.items()
                },
            },
            "persistence": {
                "backend": "in_memory_fake_gateway",
                "operations": recorder.persistence_operations,
            },
            "rss_mb": {"ru_maxrss": _rss_mb()},
        }
    )


class _PhaseRecorder:
    def __init__(self) -> None:
        self.active_phase = "outside"
        self.provider_fetch_ms = 0.0
        self.provider_fetch_calls = 0
        self.provider_fetch_rows = 0
        self.provider_fetch_by_phase: dict[str, float] = {}
        self.timings_ms: dict[str, float] = {}
        self.persistence_ms = 0.0
        self.persistence_operations: list[dict[str, Any]] = []

    def add_provider_fetch(self, *, elapsed_ms: float, rows: int) -> None:
        self.provider_fetch_ms += elapsed_ms
        self.provider_fetch_calls += 1
        self.provider_fetch_rows += rows
        self.provider_fetch_by_phase[self.active_phase] = (
            self.provider_fetch_by_phase.get(self.active_phase, 0.0) + elapsed_ms
        )

    def add_timing(self, name: str, elapsed_ms: float) -> None:
        self.timings_ms[name] = self.timings_ms.get(name, 0.0) + elapsed_ms

    def add_persistence(self, operation: str, elapsed_ms: float) -> None:
        self.persistence_ms += elapsed_ms
        self.persistence_operations.append(
            {"operation": operation, "elapsed_ms": round(elapsed_ms, 3)}
        )


def _install_phase_instrumentation(
    *,
    recorder: _PhaseRecorder,
    provider_mode: str,
) -> None:
    from datetime import date

    import argus.domain.engine as engine
    import argus.domain.engine_launch.adapter as adapter

    original_compute = adapter.compute_alpha_metrics
    original_chart = adapter.build_result_chart
    original_card = adapter.build_result_card

    if provider_mode == "synthetic_unit_fixture":

        def fetch_ohlcv(
            symbol: str,
            asset_class: str,
            start_date: date,
            end_date: date,
            timeframe: str,
        ):
            started = time.perf_counter()
            frame = _synthetic_ohlcv(
                symbol=symbol,
                asset_class=asset_class,
                start_date=start_date,
                end_date=end_date,
                timeframe=timeframe,
            )
            recorder.add_provider_fetch(
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
                rows=len(frame),
            )
            return frame

        def fetch_price_series(
            symbol: str,
            asset_class: str,
            start_date: date,
            end_date: date,
            timeframe: str,
        ):
            return fetch_ohlcv(
                symbol=symbol,
                asset_class=asset_class,
                start_date=start_date,
                end_date=end_date,
                timeframe=timeframe,
            )["close"].copy()

    else:
        original_fetch_ohlcv = engine.fetch_ohlcv
        original_fetch_price_series = engine.fetch_price_series

        def fetch_ohlcv(
            symbol: str,
            asset_class: str,
            start_date: date,
            end_date: date,
            timeframe: str,
        ):
            started = time.perf_counter()
            frame = original_fetch_ohlcv(
                symbol=symbol,
                asset_class=asset_class,
                start_date=start_date,
                end_date=end_date,
                timeframe=timeframe,
            )
            recorder.add_provider_fetch(
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
                rows=len(frame),
            )
            return frame

        def fetch_price_series(
            symbol: str,
            asset_class: str,
            start_date: date,
            end_date: date,
            timeframe: str,
        ):
            started = time.perf_counter()
            series = original_fetch_price_series(
                symbol=symbol,
                asset_class=asset_class,
                start_date=start_date,
                end_date=end_date,
                timeframe=timeframe,
            )
            recorder.add_provider_fetch(
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
                rows=len(series),
            )
            return series

    engine.fetch_ohlcv = fetch_ohlcv
    engine.fetch_price_series = fetch_price_series
    adapter.fetch_ohlcv = fetch_ohlcv
    adapter.fetch_price_series = fetch_price_series

    def timed_compute(config: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        previous = recorder.active_phase
        recorder.active_phase = "engine_compute"
        started = time.perf_counter()
        try:
            return original_compute(config, **kwargs)
        finally:
            recorder.add_timing(
                "engine_compute_total",
                (time.perf_counter() - started) * 1000.0,
            )
            recorder.active_phase = previous

    def timed_chart(config: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        previous = recorder.active_phase
        recorder.active_phase = "chart_build"
        started = time.perf_counter()
        try:
            return original_chart(config, **kwargs)
        finally:
            recorder.add_timing(
                "chart_build_total",
                (time.perf_counter() - started) * 1000.0,
            )
            recorder.active_phase = previous

    def timed_card(
        config: dict[str, Any],
        metrics: dict[str, Any],
        language: str = "en",
        chart: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            return original_card(config, metrics, language=language, chart=chart)
        finally:
            recorder.add_timing(
                "result_card_build",
                (time.perf_counter() - started) * 1000.0,
            )

    adapter.compute_alpha_metrics = timed_compute
    adapter.build_result_chart = timed_chart
    adapter.build_result_card = timed_card


def _synthetic_ohlcv(
    *,
    symbol: str,
    asset_class: str,
    start_date: Any,
    end_date: Any,
    timeframe: str,
):
    import pandas as pd

    freq = {
        "1D": "D",
        "1d": "D",
        "1h": "1h",
        "2h": "2h",
        "4h": "4h",
        "6h": "6h",
        "12h": "12h",
    }[timeframe]
    index = pd.date_range(
        start=start_date.isoformat(),
        end=f"{end_date.isoformat()} 23:59:59",
        freq=freq,
        tz="UTC",
    )
    if len(index) == 0:
        raise ValueError("market_data_unavailable")

    seed = sum(ord(char) for char in symbol) + (17 if asset_class == "crypto" else 0)
    base = 50.0 + float(seed % 175)
    slope = 0.015 + float(seed % 11) * 0.001
    values = [
        base
        + (idx * slope)
        + ((((idx + seed) % 31) - 15) * 0.08)
        + ((((idx // 23) + seed) % 9) * 0.04)
        for idx in range(len(index))
    ]
    close = pd.Series(values, index=index, dtype=float)
    return pd.DataFrame(
        {
            "open": close * 0.999,
            "high": close * 1.003,
            "low": close * 0.997,
            "close": close,
            "volume": 10_000.0 + float(seed % 1000),
        },
        index=index,
    )


class _BenchmarkGateway:
    def __init__(self, row: dict[str, Any], *, recorder: _PhaseRecorder) -> None:
        self.row = dict(row)
        self.recorder = recorder

    def fetch_job(self, job_id: str) -> dict[str, Any] | None:
        if self.row["id"] != job_id:
            return None
        return dict(self.row)

    def mark_backtest_job_running(
        self,
        *,
        user_id: str,
        job_id: str,
        execution_metadata: dict[str, Any],
        started_at: str | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        self.row.update(
            {
                "status": "running",
                "started_at": started_at,
                "attempts": int(self.row.get("attempts") or 0) + 1,
                "execution_metadata": execution_metadata,
            }
        )
        self.recorder.add_persistence(
            "mark_backtest_job_running",
            (time.perf_counter() - started) * 1000.0,
        )
        return dict(self.row)

    def merge_backtest_job_execution_metadata(
        self,
        *,
        user_id: str,
        job_id: str,
        execution_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        del user_id, job_id
        started = time.perf_counter()
        metadata = dict(self.row.get("execution_metadata") or {})
        metadata.update(execution_metadata)
        self.row["execution_metadata"] = metadata
        self.recorder.add_persistence(
            "merge_backtest_job_execution_metadata",
            (time.perf_counter() - started) * 1000.0,
        )
        return dict(self.row)

    def create_backtest_run(self, *, user_id: str, run: Any) -> Any:
        started = time.perf_counter()
        self.row["created_run_id"] = run.id
        self.recorder.add_persistence(
            "create_backtest_run",
            (time.perf_counter() - started) * 1000.0,
        )
        return run

    def link_backtest_job_result(
        self,
        *,
        user_id: str,
        job_id: str,
        result_run_id: str,
        execution_metadata: dict[str, Any] | None = None,
        mark_succeeded: bool = False,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        self.row.update(
            {
                "status": "succeeded" if mark_succeeded else self.row.get("status"),
                "result_run_id": result_run_id,
                "execution_metadata": execution_metadata or {},
            }
        )
        self.recorder.add_persistence(
            "link_backtest_job_result",
            (time.perf_counter() - started) * 1000.0,
        )
        return dict(self.row)

    def mark_backtest_job_failed(
        self,
        *,
        user_id: str,
        job_id: str,
        failure_code: str,
        failure_detail: str,
        retryable: bool,
        execution_metadata: dict[str, Any] | None = None,
        finished_at: str | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        self.row.update(
            {
                "status": "failed",
                "failure_code": failure_code,
                "failure_detail": failure_detail,
                "retryable": retryable,
                "finished_at": finished_at,
                "execution_metadata": execution_metadata or {},
            }
        )
        self.recorder.add_persistence(
            "mark_backtest_job_failed",
            (time.perf_counter() - started) * 1000.0,
        )
        return dict(self.row)


def _forbidden_loaded() -> list[str]:
    loaded = []
    for name in sys.modules:
        for prefix in FORBIDDEN_BACKTEST_COMPUTE_MODULE_PREFIXES:
            if name == prefix or name.startswith(prefix + "."):
                loaded.append(name)
                break
    return sorted(loaded)


def _heavy_loaded() -> list[str]:
    heavy_prefixes = (
        "numpy",
        "pandas",
        "vectorbt",
        "numba",
        "scipy",
        "argus.domain.engine",
        "argus.domain.backtesting",
    )
    loaded = []
    for name in sys.modules:
        for prefix in heavy_prefixes:
            if name == prefix or name.startswith(prefix + "."):
                loaded.append(name)
                break
    return sorted(loaded)


def _rss_mb() -> float:
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if raw > 10_000_000:
        return round(raw / (1024 * 1024), 3)
    return round(raw / 1024, 3)


def _bytes_to_mb(value: int) -> float:
    return round(value / (1024 * 1024), 3)


def _emit_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, sort_keys=True))


def _selected_cases(case_ids: list[str] | None) -> list[BenchmarkCase]:
    cases = benchmark_cases()
    if not case_ids:
        return cases
    case_by_id = {case.case_id: case for case in cases}
    missing = [case_id for case_id in case_ids if case_id not in case_by_id]
    if missing:
        raise ValueError(f"unknown benchmark case(s): {', '.join(missing)}")
    return [case_by_id[case_id] for case_id in case_ids]


def _assert_provider_mode_allowed(provider_mode: str) -> None:
    if provider_mode not in LOCAL_PROVIDER_MODES:
        raise ValueError(f"unsupported provider mode: {provider_mode}")
    if provider_mode == "live_provider":
        enabled = os.getenv("ARGUS_BENCHMARK_LIVE_PROVIDER", "").strip().lower()
        if enabled not in {"1", "true", "yes", "on"}:
            raise RuntimeError(
                "live_provider benchmark mode requires "
                "ARGUS_BENCHMARK_LIVE_PROVIDER=true."
            )


def run_benchmark(
    *,
    repo_root: Path,
    output_dir: Path,
    case_ids: list[str] | None,
    provider_mode: str,
    timeout_seconds: float,
    api_only: bool,
) -> dict[str, Any]:
    _assert_provider_mode_allowed(provider_mode)
    started = datetime.now(timezone.utc)
    cases = _selected_cases(case_ids)
    report: dict[str, Any] = {
        "schema_version": "argus_backtest_infra_benchmark/v1",
        "generated_at": started.isoformat(),
        "repo_root": str(repo_root),
        "provider_mode": provider_mode,
        "live_provider_enabled": provider_mode == "live_provider",
        "output": {},
        "api_import": run_api_import_probe(repo_root),
        "workflow_import": run_workflow_import_probe(repo_root),
        "workflow_cases": [],
        "queue_backpressure_smoke": run_backpressure_smoke(),
        "caveats": [
            "Local synthetic provider mode measures Argus compute shape without live provider latency.",
            "Fake persistence timings are in-process smoke timings, not Supabase write latency.",
            "Render Workflow cold start and task RSS must be refreshed on Render standard compute before tier decisions.",
        ],
    }
    if not api_only:
        for case in cases:
            report["workflow_cases"].append(
                run_workflow_case_probe(
                    repo_root,
                    case,
                    provider_mode=provider_mode,
                    timeout_seconds=timeout_seconds,
                )
            )

    paths = write_outputs(report=report, output_dir=output_dir)
    report["output"] = {key: str(value) for key, value in paths.items()}
    return report


def write_outputs(*, report: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = (
        str(report["generated_at"]).replace(":", "-").replace("+", "-").replace(".", "-")
    )
    json_path = output_dir / f"backtest-infra-{stamp}.json"
    markdown_path = output_dir / f"backtest-infra-{stamp}.md"
    latest_json = output_dir / "latest.json"
    latest_markdown = output_dir / "latest.md"

    serialized = json.dumps(report, indent=2, sort_keys=True)
    json_path.write_text(serialized + "\n", encoding="utf-8")
    latest_json.write_text(serialized + "\n", encoding="utf-8")

    markdown = render_markdown_summary(report)
    markdown_path.write_text(markdown, encoding="utf-8")
    latest_markdown.write_text(markdown, encoding="utf-8")
    return {
        "json": json_path,
        "markdown": markdown_path,
        "latest_json": latest_json,
        "latest_markdown": latest_markdown,
    }


def render_markdown_summary(report: dict[str, Any]) -> str:
    lines = [
        "# Argus Backtest Infrastructure Benchmark",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Provider mode: `{report['provider_mode']}`",
        f"- API import peak RSS: {report['api_import']['subprocess']['peak_rss_mb']:.1f} MB",
        f"- Workflow import peak RSS: {report['workflow_import']['subprocess']['peak_rss_mb']:.1f} MB",
        "",
        "## API Import",
        "",
        "| Probe | Value |",
        "| --- | ---: |",
        f"| baseline RSS | {report['api_import']['rss_mb']['baseline']:.1f} MB |",
        f"| after `argus.api.main` | {report['api_import']['rss_mb']['after_import']:.1f} MB |",
        f"| after `/health` | {report['api_import']['rss_mb']['after_health']:.1f} MB |",
        f"| forbidden heavy modules | {len(report['api_import']['forbidden_loaded'])} |",
        "",
        "## Workflow Import",
        "",
        "| Probe | Value |",
        "| --- | ---: |",
        f"| baseline RSS | {report['workflow_import']['rss_mb']['baseline']:.1f} MB |",
        f"| after workflow module | {report['workflow_import']['rss_mb']['after_workflow_module']:.1f} MB |",
        f"| after backtest tool import | {report['workflow_import']['rss_mb']['after_backtest_tool']:.1f} MB |",
        f"| workflow module import | {report['workflow_import']['timings_ms']['workflow_module_import']:.1f} ms |",
        f"| backtest tool import | {report['workflow_import']['timings_ms']['backtest_tool_import']:.1f} ms |",
        "",
        "## Workflow Cases",
        "",
        "| Case | Status | Wall ms | Peak RSS MB | Provider ms | Engine net ms | Chart net ms | Fake persistence ms |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for case in report.get("workflow_cases", []):
        timings = case["timings_ms"]
        lines.append(
            "| "
            f"{case['case_id']} | "
            f"{case.get('status')} | "
            f"{timings['workflow_execution_wall']:.1f} | "
            f"{case['subprocess']['peak_rss_mb']:.1f} | "
            f"{timings['provider_fetch_total']:.1f} | "
            f"{timings['engine_compute_net']:.1f} | "
            f"{timings['chart_build_net']:.1f} | "
            f"{timings['fake_persistence']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Backpressure Smoke",
            "",
            "| Check | Admitted | Reason |",
            "| --- | --- | --- |",
        ]
    )
    for check in report["queue_backpressure_smoke"]["checks"]:
        lines.append(
            f"| {check['name']} | {check['admitted']} | {check['reason'] or ''} |"
        )
    lines.extend(["", "## Caveats", ""])
    for caveat in report["caveats"]:
        lines.append(f"- {caveat}")
    lines.append("")
    return "\n".join(lines)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Argus private-alpha backtest infrastructure benchmarks.",
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="case_ids",
        help="Run only one benchmark case id. May be passed multiple times.",
    )
    parser.add_argument(
        "--provider-mode",
        choices=sorted(LOCAL_PROVIDER_MODES),
        default="synthetic_unit_fixture",
        help="Market data provider mode. live_provider requires ARGUS_BENCHMARK_LIVE_PROVIDER=true.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory. Defaults to temp/benchmarks/backtest-infra.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=120.0,
        help="Timeout for each child execution case.",
    )
    parser.add_argument(
        "--api-only",
        action="store_true",
        help="Run import probes and backpressure smoke without execution cases.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "__api_import_probe":
        _child_api_import_probe()
        return 0
    if argv and argv[0] == "__workflow_import_probe":
        _child_workflow_import_probe()
        return 0
    if argv and argv[0] == "__workflow_case_probe":
        if len(argv) != 2:
            raise SystemExit("__workflow_case_probe requires a case id")
        _child_workflow_case_probe(argv[1])
        return 0

    args = _parse_args(argv)
    repo_root = Path(__file__).resolve().parents[2]
    output_dir = args.output_dir or default_output_dir(repo_root)
    report = run_benchmark(
        repo_root=repo_root,
        output_dir=output_dir,
        case_ids=args.case_ids,
        provider_mode=args.provider_mode,
        timeout_seconds=args.timeout_seconds,
        api_only=args.api_only,
    )
    print("Argus backtest infrastructure benchmark complete")
    print(f"JSON: {report['output']['json']}")
    print(f"Markdown: {report['output']['markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
