from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCANNER = ROOT / "scripts/check_config_credentials.py"


def jwt_fixture() -> str:
    def encoded(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")
    return ".".join([encoded({"alg": "HS256", "typ": "JWT"}), encoded({"role": "anon", "ref": "synthetic"}), "synthetic_signature"])


def run_scan(root: Path):
    return subprocess.run([sys.executable, str(SCANNER), "--root", str(root)], capture_output=True, text=True)


@pytest.fixture
def repository(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


@pytest.mark.parametrize("name", ["render.yaml", "deployment.yml", "config.json", "settings.toml", ".env.example"])
@pytest.mark.parametrize("key", [jwt_fixture(), "sb_" + "publishable_" + "synthetic" * 4, "sb_" + "secret_" + "synthetic" * 4])
def test_scan_rejects_tracked_config_without_echoing_value(repository, name, key):
    (repository / name).write_text("key=" + key + "\n")
    subprocess.run(["git", "add", name], cwd=repository, check=True)
    result = run_scan(repository)
    assert result.returncode == 1
    assert f"{name}:1:" in result.stderr
    assert key not in result.stdout + result.stderr


def test_scan_allows_environment_injection_and_ignores_untracked_env(repository):
    (repository / "render.yaml").write_text("key: SUPABASE_ANON_KEY\nsync: false\n")
    (repository / ".env").write_text("key=" + jwt_fixture())
    subprocess.run(["git", "add", "render.yaml"], cwd=repository, check=True)
    assert run_scan(repository).returncode == 0


def test_repository_config_has_no_credential_literals():
    result = run_scan(ROOT)
    assert result.returncode == 0, result.stderr


def test_ci_runs_config_scan_in_the_required_ownership_gate():
    import yaml
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    job = workflow["jobs"]["ownership-gate"]
    assert "ownership-gate" in workflow["jobs"]["ci"]["needs"]
    assert any(step.get("run") == "python scripts/check_config_credentials.py" for step in job["steps"])
