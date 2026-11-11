from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from tests.test_environment_scripts import (
    _render_env_payload,
    _run_render_release_audit,
    _source,
)


@pytest.mark.parametrize("provisioned", [False, True])
def test_release_audit_preserves_optional_registered_keys_without_disclosure(
    tmp_path: Path, provisioned: bool
) -> None:
    key = "CUADRAO_OPENROUTER_API_KEY_PROD"
    value = "synthetic-hosted-PROD"
    result = _run_render_release_audit(
        tmp_path,
        api_env_json=_render_env_payload(
            "cuadrao-api",
            omit=set() if provisioned else {key},
            overrides={key: value},
        ),
        web_env_json=_render_env_payload("cuadrao-marketing"),
        isolate=True,
    )
    output = result.stdout + result.stderr
    assert value not in output
    assert result.returncode == 0, output
    assert "status=ready" in result.stdout
    assert "-X PUT" not in (tmp_path / "curl-requests.log").read_text()


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
