"""Keep required checks attached to complete, isolated shard executions."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOW = yaml.safe_load(
    (Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml").read_text()
)
JOBS = WORKFLOW["jobs"]


@pytest.mark.parametrize("suite", ["backend", "database"])
def test_shard_count_matches_every_matrix_index(suite: str) -> None:
    job = JOBS[f"{suite}-shards"]
    count = int(job["env"]["CI_SHARD_COUNT"])
    assert count > 1
    assert job["strategy"]["fail-fast"] is False
    assert job["strategy"]["matrix"]["shard"] == list(range(count))
    assert job["env"]["CI_SHARD_INDEX"] == "${{ matrix.shard }}"
    runs = "\n".join(step.get("run", "") for step in job["steps"])
    assert '--ci-shard-index "${CI_SHARD_INDEX}"' in runs
    assert '--ci-shard-count "${CI_SHARD_COUNT}"' in runs


@pytest.mark.parametrize("suite", ["backend", "database"])
def test_required_gate_rejects_failed_cancelled_or_missing_shards(suite: str) -> None:
    gate = JOBS[f"{suite}-checks"]
    assert gate["needs"] == ["docs-change-gate", f"{suite}-shards"]
    assert gate["if"].startswith("always() && ")
    assert f"needs.docs-change-gate.outputs.run_{suite} == 'true'" not in gate["if"]
    check = next(step for step in gate["steps"] if step.get("name") == f"Require every {suite} shard")
    assert check["if"] == f"needs.docs-change-gate.outputs.run_{suite} == 'true'"
    assert check["env"]["SHARDS_RESULT"] == "${{ needs." + suite + "-shards.result }}"
    for state in ["success", "failure", "cancelled", "skipped", ""]:
        result = subprocess.run(
            ["bash", "-e", "-c", check["run"]],
            env={**os.environ, "SHARDS_RESULT": state},
            capture_output=True,
            check=False,
        )
        assert (result.returncode == 0) == (state == "success")


@pytest.mark.parametrize("suite", ["backend", "database"])
def test_required_gate_verifies_union_after_all_shards_succeed(suite: str) -> None:
    gate = JOBS[f"{suite}-checks"]
    proofs = [s for s in gate["steps"] if "test_shards.py" in s.get("run", "")]
    assert proofs
    assert "--output temp/ci-proof/" in proofs[0]["run"]
    assert "*.json" in proofs[0]["run"]
    assert proofs[0]["if"] == f"needs.docs-change-gate.outputs.run_{suite} == 'true'"
    assert not any(s.get("continue-on-error") for s in gate["steps"])
    download = next(s for s in gate["steps"] if "download-artifact@" in s.get("uses", ""))
    assert (
        "${{ github.run_id }}-*" in download["with"]["pattern"]
    )
    assert download["with"]["merge-multiple"] is True
    upload = gate["steps"][-1]
    assert upload["with"]["if-no-files-found"] == "error"
    assert f"{suite}-checks" in JOBS["ci"]["needs"]


def test_database_workers_each_own_a_disposable_database_and_auth_runs_once() -> None:
    job = JOBS["database-shards"]
    assert job["runs-on"] == "ubuntu-latest"
    assert job["needs"] == "docs-change-gate"
    start = next(
        s for s in job["steps"] if s["name"] == "Start disposable local Supabase"
    )
    assert "if" not in start
    assert "supabase start " in start["run"]
    assert "supabase status -o env" in start["run"]
    assert "ARGUS_DISPOSABLE_DATABASE_URL=$DB_URL" in start["run"]
    assert "ARGUS_DISPOSABLE_DATABASE_URL" not in WORKFLOW["env"]
    auth = next(
        s for s in job["steps"] if s["name"] == "Run required local anonymous Auth matrix"
    )
    assert auth["if"] == "matrix.supabase-cli == 'pinned' && matrix.shard == 0"
    assert "scripts/qa/assert_pytest_gate.py" in auth["run"]
    assert "--ci-shard-index" not in auth["run"]
    gate = JOBS["database-checks"]
    assert (
        gate["strategy"]["matrix"]["supabase-cli"]
        == job["strategy"]["matrix"]["supabase-cli"]
    )
    proofs = [s for s in gate["steps"] if "test_shards.py" in s.get("run", "")]
    assert len(proofs) == 2
    assert all("--require-passed" in s["run"] for s in proofs)
    assert proofs[1]["if"] == "matrix.supabase-cli == 'pinned' && needs.docs-change-gate.outputs.run_database == 'true'"
    assert "auth.json" in proofs[1]["run"]
    assert WORKFLOW["permissions"] == {"contents": "read"}


def test_artifacts_cannot_overwrite_another_shards_inventory() -> None:
    for suite in ["backend", "database"]:
        job = JOBS[f"{suite}-shards"]
        upload = next(s for s in job["steps"] if s["name"].startswith("Retain "))
        assert upload["if"] == "always()"
        assert upload["with"]["name"].endswith(
            "${{ github.run_id }}-${{ matrix.shard }}"
        )
        assert upload["with"]["if-no-files-found"] == "error"
        assert upload["with"]["overwrite"] is True
        assert "github.run_attempt" not in upload["with"]["name"]
        runs = "\n".join(s.get("run", "") for s in job["steps"])
        stem = "backend" if suite == "backend" else "postgres"
        assert f"--ci-inventory=temp/ci-inventory/{stem}-${{CI_SHARD_INDEX}}.json" in runs
    assert (
        "${{ matrix.supabase-cli }}"
        in JOBS["database-shards"]["steps"][-1]["with"]["name"]
    )
