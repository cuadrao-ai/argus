from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
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


def test_api_startup_health_does_not_import_backtest_compute_stack() -> None:
    result = _run_import_probe()
    assert result["health_status_code"] == 200
    assert result["health_body"]["status"] == "healthy"
    assert result["forbidden_loaded"] == []


def test_api_real_workflow_build_does_not_import_backtest_compute_stack() -> None:
    result = _run_import_probe()
    assert result["workflow_loaded"] is True
    assert result["forbidden_after_workflow"] == []


def test_api_readiness_warms_lazy_workflow_without_backtest_compute_stack() -> None:
    result = _run_import_probe()
    readiness = result["readiness_body"]
    checks = {
        str(check.get("name")): check
        for check in readiness.get("checks", [])
        if isinstance(check, dict)
    }

    assert checks["agent_runtime_workflow"]["status"] == "ready"
    assert result["forbidden_after_readiness"] == []


def test_runtime_uses_lightweight_workflow_contract_for_shared_runtime_names() -> None:
    runtime_path = REPO_ROOT / "src" / "argus" / "agent_runtime" / "runtime.py"
    tree = ast.parse(runtime_path.read_text(encoding="utf-8"))

    imports_contract = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "argus.agent_runtime.workflow_contract"
        for node in ast.walk(tree)
    )
    assert imports_contract

    forbidden_local_assignments = {
        "OFFLINE_CLARIFICATION_FALLBACK",
        "TOKEN_STREAM_NODES",
        "WORKFLOW_NODE_NAMES",
    }
    assigned_names = {
        target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign | ast.AnnAssign)
        for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        if isinstance(target, ast.Name)
    }
    assert forbidden_local_assignments.isdisjoint(assigned_names)

    workflow_contract_path = (
        REPO_ROOT / "src" / "argus" / "agent_runtime" / "workflow_contract.py"
    )
    assert "OFFLINE_CLARIFICATION_FALLBACK" not in workflow_contract_path.read_text(
        encoding="utf-8"
    )


def test_api_import_probe_reports_memory_smoke() -> None:
    result = _run_import_probe()
    rss = result["rss_mb"]

    assert rss["baseline"] > 0
    assert rss["after_import"] >= rss["baseline"]
    assert rss["after_health"] >= rss["after_import"]

    print(
        "api import rss smoke: "
        f"baseline={rss['baseline']:.1f} MB "
        f"after_import={rss['after_import']:.1f} MB "
        f"after_health={rss['after_health']:.1f} MB"
    )


def _run_import_probe() -> dict[str, Any]:
    env = os.environ.copy()
    env.update(
        {
            "CUADRAO_PERSISTENCE_MODE": "memory",
            "CUADRAO_CHECKPOINTER_MODE": "memory",
            "ARGUS_DEV_MEMORY_FALLBACK": "true",
            "CUADRAO_MOCK_AUTH": "true",
            "ARGUS_BACKTEST_JOBS_SHADOW_ENABLED": "true",
            "ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED": "true",
            "ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED": "true",
            "ARGUS_MARKET_DATA_PROVIDER_MODE": "synthetic_unit_fixture",
            "CUADRAO_OPS_TOKEN": "test-token",
            "PYTHONPATH": str(REPO_ROOT / "src"),
        }
    )
    completed = subprocess.run(
        [sys.executable, "-c", _IMPORT_PROBE_SCRIPT],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


_IMPORT_PROBE_SCRIPT = textwrap.dedent(
    f"""
    import json
    import resource
    import sys


    FORBIDDEN_MODULE_PREFIXES = {FORBIDDEN_BACKTEST_COMPUTE_MODULE_PREFIXES!r}


    def rss_mb():
        raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if raw > 10_000_000:
            return raw / (1024 * 1024)
        return raw / 1024


    def forbidden_loaded():
        loaded = []
        for name in sys.modules:
            for prefix in FORBIDDEN_MODULE_PREFIXES:
                if name == prefix or name.startswith(prefix + "."):
                    loaded.append(name)
                    break
        return sorted(loaded)


    baseline = rss_mb()
    from argus.api.main import app
    from argus.api import state as api_state

    after_import = rss_mb()
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        response = client.get("/health")
        health_status_code = response.status_code
        health_body = response.json()

    after_health = rss_mb()
    forbidden_after_health = forbidden_loaded()

    with TestClient(app) as client:
        readiness_response = client.get(
            "/internal/readiness?force=true",
            headers={{"Authorization": "Bearer test-token"}},
        )
        readiness_status_code = readiness_response.status_code
        readiness_body = readiness_response.json()

    forbidden_after_readiness = forbidden_loaded()
    workflow = api_state.get_agent_runtime_workflow()
    workflow_loaded = workflow is not None
    forbidden_after_workflow = forbidden_loaded()

    print(
        json.dumps(
            {{
                "rss_mb": {{
                    "baseline": baseline,
                    "after_import": after_import,
                    "after_health": after_health,
                }},
                "health_status_code": health_status_code,
                "health_body": health_body,
                "readiness_status_code": readiness_status_code,
                "readiness_body": readiness_body,
                "workflow_loaded": workflow_loaded,
                "forbidden_loaded": forbidden_after_health,
                "forbidden_after_readiness": forbidden_after_readiness,
                "forbidden_after_workflow": forbidden_after_workflow,
            }},
            sort_keys=True,
        )
    )
    """
)
