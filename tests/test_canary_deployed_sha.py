from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / ".github" / "canary-deployed-sha.py"
RESOLVER_PATH = ROOT / ".github" / "canary-resolve-deployed.sh"
FULL_SHA = "d67cef9" + ("a" * 33)


def _load_module():
    spec = importlib.util.spec_from_file_location("canary_deployed_sha", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _same_commit_check() -> str:
    profile = json.loads(
        (ROOT / ".github" / "private-alpha-release-profile.json").read_text(
            encoding="utf-8"
        )
    )
    return profile["canary"]["required_steps"][0]


def _service_status(*, status: str = "live", commit: str = FULL_SHA) -> str:
    return f"status={status}\ncommit={commit}\n"


def _workflow_status(
    *, status: str = "ready", commit: str = "d67cef9", version_id: str = "wfv-current"
) -> str:
    return (
        f"workflow_version_id={version_id}\n"
        f"status={status}\n"
        f"commit={commit}\n"
    )


def test_resolver_accepts_render_workflow_git_prefix() -> None:
    module = _load_module()

    assert module.resolve_deployed_sha(
        api_status=_service_status(),
        web_status=_service_status(),
        workflow_status=_workflow_status(),
    ) == FULL_SHA


@pytest.mark.parametrize(
    ("workflow_status", "reason"),
    [
        (_workflow_status(commit="abcdef0"), "workflow_commit_mismatch"),
        (_workflow_status(commit="not-a-sha"), "workflow_commit_mismatch"),
        (_workflow_status(version_id=""), "workflow_version_id_missing"),
    ],
)
def test_resolver_fails_closed_on_invalid_workflow_version_proof(
    workflow_status: str, reason: str
) -> None:
    module = _load_module()

    with pytest.raises(ValueError, match=reason):
        module.resolve_deployed_sha(
            api_status=_service_status(),
            web_status=_service_status(),
            workflow_status=workflow_status,
        )


def test_resolver_keeps_the_marketing_commit_off_the_candidate() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            "--api-status",
            _service_status(),
            "--web-status",
            _service_status(commit="b" * 40),
            "--workflow-status",
            _workflow_status(),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert _same_commit_check() == "services_same_commit"
    assert result.returncode == 0
    assert result.stdout.strip() == FULL_SHA
    assert result.stderr == ""


def test_resolver_script_names_the_same_commit_check_for_every_status_read() -> None:
    resolver = RESOLVER_PATH.read_text(encoding="utf-8")

    assert (
        f'echo "ERROR: canary failed at {_same_commit_check()}: $1" >&2' in resolver
    )
    for reason in (
        "api_deploy_status_failed",
        "web_deploy_status_failed",
        "workflow_version_status_failed",
    ):
        assert f'same_commit_failure "{reason}"' in resolver
