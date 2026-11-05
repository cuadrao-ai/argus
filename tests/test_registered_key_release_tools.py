from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from tests.test_environment_scripts import (
    _real_workflow_api_env_payload,
    _render_env_payload,
    _run_isolated_sync,
    _run_render_release_audit,
    _source,
    _workflow_env_payload,
)


@pytest.mark.parametrize("provisioned", [False, True])
def test_release_audit_preserves_optional_registered_keys_without_disclosure(
    tmp_path: Path, provisioned: bool
) -> None:
    keys = {
        f"CUADRAO_OPENROUTER_API_KEY_{suffix}": f"synthetic-hosted-{suffix}"
        for suffix in ("DEV", "STG", "PROD")
    }
    result = _run_render_release_audit(
        tmp_path,
        expect_mode="real-workflow",
        api_env_json=_real_workflow_api_env_payload(),
        web_env_json=_render_env_payload("cuadrao-web"),
        workflow_env_json=_workflow_env_payload(extra=keys if provisioned else {}),
        isolate=True,
    )
    output = result.stdout + result.stderr
    assert all(value not in output for value in keys.values())
    assert "Unsupported workflow env key" not in output
    assert result.returncode == 0, output
    assert "workflow_env_status=ready" in result.stdout
    assert "status=ready" in result.stdout
    assert "-X PUT" not in (tmp_path / "curl-requests.log").read_text()


@pytest.mark.parametrize("exported", [False, True])
def test_workflow_sync_leaves_manually_provisioned_optional_keys_untouched(
    tmp_path: Path, exported: bool
) -> None:
    keys = {
        f"CUADRAO_OPENROUTER_API_KEY_{suffix}": f"synthetic-manual-{suffix}"
        for suffix in ("DEV", "STG", "PROD")
    }
    values = {
        "RENDER_API_KEY": "synthetic-token",
        "CUADRAO_PROD_OPENROUTER_API_KEY": "synthetic-registered",
        "CUADRAO_GUEST_ACCESS_OPENROUTER_API_KEY": "synthetic-guest",
        **(keys if exported else {}),
    }
    result, requests = _run_isolated_sync(tmp_path, "workflow-proof", values)
    assert result.returncode == 0, result.stdout + result.stderr
    assert requests
    assert all(name not in request for name in keys for request in requests)
    assert all(value not in result.stdout + result.stderr for value in keys.values())
    assert "Unsupported workflow env key" not in result.stderr


@pytest.mark.parametrize("suffix", ["DEV", "STG", "PROD"])
@pytest.mark.parametrize("value", ["", 'synthetic-value-with-"quotes"\nand-newline'])
def test_registered_key_status_is_always_redacted(suffix: str, value: str) -> None:
    source = _source(".github/render-env-sync.sh")
    functions = []
    for name in (
        "is_secret_render_env_key",
        "render_env_raw_value",
        "render_env_status_value",
    ):
        body = source.split(f"{name}() {{", 1)[1].split("\n}", 1)[0]
        functions.append(f"{name}() {{{body}\n}}")
    key = f"CUADRAO_OPENROUTER_API_KEY_{suffix}"
    result = subprocess.run(
        [
            "bash",
            "-c",
            "\n".join(functions)
            + '\nrender_env_status_value "$TEST_ENV_JSON" "$TEST_KEY"',
        ],
        env={
            "PATH": os.environ["PATH"],
            "TEST_KEY": key,
            "TEST_ENV_JSON": json.dumps([{"envVar": {"key": key, "value": value}}]),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == ("<redacted-present>\n" if value else "<missing-or-empty>\n")
