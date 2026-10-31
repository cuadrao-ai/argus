from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL_SMOKE = ROOT / ".github" / "local-smoke.sh"


def _source(path: Path = LOCAL_SMOKE) -> str:
    return path.read_text(encoding="utf-8")


def _run_local_smoke_contract(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("RENDER_API_KEY", None)
    return subprocess.run(
        [str(LOCAL_SMOKE), "--contract-only", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _verify_readiness_payload(
    tmp_path: Path,
    payload: dict[str, object],
) -> subprocess.CompletedProcess[str]:
    payload_path = tmp_path / "readiness.json"
    payload_path.write_text(json.dumps(payload), encoding="utf-8")
    return subprocess.run(
        [
            "bash",
            "-c",
            (
                "set -euo pipefail; "
                "ARGUS_LOCAL_SMOKE_SOURCE_ONLY=true "
                "source .github/local-smoke.sh; "
                f"verify_readiness_payload {payload_path}"
            ),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_local_smoke_script_is_disposable_predeploy_gate() -> None:
    source = _source()
    mode = LOCAL_SMOKE.stat().st_mode

    assert mode & stat.S_IXUSR
    assert "Private Alpha local smoke" in source
    assert 'source "$SCRIPT_DIR/argus-env.sh"' in source
    assert "argus_export_dev_mode" in source
    assert "mktemp -d" in source
    assert "cleanup()" in source
    assert "trap cleanup EXIT INT TERM" in source
    assert "poetry run uvicorn argus.api.main:app" in source
    assert "cd web && bun run dev" in source
    assert "/health" in source
    assert "/internal/readiness?force=true" in source
    assert "Authorization: Bearer ${CUADRAO_OPS_TOKEN}" in source
    assert "allowed_degraded_readiness" in source
    assert "gateway_unavailable" in source
    assert "unexpected degraded readiness checks" in source
    assert "readiness failed" in source
    assert "workflow_probe=ready" in source
    assert "workflows.trigger_proof" in source
    assert "argus.api.chat import backtest_jobs" in source
    assert "ARGUS_LOCAL_SMOKE_SOURCE_ONLY" in source
    assert 'for pid in "${PIDS[@]}"' in source
    assert 'kill -0 "$pid"' in source
    assert "Background process" in source
    assert 'tail -80 "$API_LOG"' in source
    assert 'tail -80 "$WEB_LOG"' in source

    assert "https://api.render.com" not in source
    assert "api-real-workflow-on" not in source
    assert "warmup-render.sh" not in source
    assert "delete_render_env" not in source
    assert "put_render_env" not in source


def test_local_smoke_contract_reports_sha_flags_mode_and_fingerprint() -> None:
    expected_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
    ).strip()

    result = _run_local_smoke_contract("--expected-sha", expected_sha)

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"candidate_sha={expected_sha}" in result.stdout
    assert "workflow_mode=proof-shadow" in result.stdout
    assert "feature_flags=" in result.stdout
    assert '"NEXT_PUBLIC_OMNISEARCH_ENABLED":"true"' in result.stdout
    assert "runtime_mode=" in result.stdout
    assert '"CUADRAO_PERSISTENCE_MODE":"memory"' in result.stdout
    assert '"ARGUS_MARKET_DATA_PROVIDER_MODE":"synthetic_unit_fixture"' in (
        result.stdout
    )
    assert '"CUADRAO_CHECKPOINTER_MODE":"memory"' in result.stdout
    assert '"CUADRAO_MOCK_AUTH":"true"' in result.stdout
    assert "env_fingerprint=" in result.stdout
    assert "verification_status=ready" in result.stdout


def test_local_smoke_contract_rejects_sha_or_real_workflow_mismatch() -> None:
    sha_result = _run_local_smoke_contract("--expected-sha", "deadbeef")

    assert sha_result.returncode == 1
    assert "expected_sha=deadbeef" in sha_result.stdout
    assert "verification_status=drift" in sha_result.stdout

    mode_result = _run_local_smoke_contract("--workflow-mode", "real-workflow")

    assert mode_result.returncode == 2
    assert "real-workflow mode is not allowed for local smoke" in mode_result.stdout


def test_local_smoke_allows_only_memory_supabase_readiness_degradation(
    tmp_path: Path,
) -> None:
    result = _verify_readiness_payload(
        tmp_path,
        {
            "status": "degraded",
            "checks": [
                {"name": "agent_runtime_workflow", "status": "ready"},
                {
                    "name": "supabase",
                    "status": "degraded",
                    "reason": "gateway_unavailable",
                },
                {"name": "asset_universe", "status": "ready"},
            ],
        },
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "readiness_status=degraded" in result.stdout


def test_local_smoke_rejects_unexpected_readiness_degradation(
    tmp_path: Path,
) -> None:
    result = _verify_readiness_payload(
        tmp_path,
        {
            "status": "degraded",
            "checks": [
                {"name": "agent_runtime_workflow", "status": "ready"},
                {
                    "name": "supabase",
                    "status": "degraded",
                    "reason": "timeout",
                },
                {"name": "asset_universe", "status": "ready"},
            ],
        },
    )

    assert result.returncode == 1
    assert "unexpected degraded readiness checks" in result.stderr
