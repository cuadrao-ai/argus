from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from argus.llm.openrouter_key_policy import (
    MODEL_CREDENTIAL_ENV_NAMES,
    RETIRED_MODEL_CREDENTIAL_ENV_NAMES,
)

from tests.test_environment_scripts import (
    _render_env_payload,
    _run_render_release_audit,
    _source,
)


@pytest.mark.parametrize("provisioned", [False, True])
def test_release_audit_requires_the_production_key_without_disclosure(
    tmp_path: Path, provisioned: bool
) -> None:
    key = MODEL_CREDENTIAL_ENV_NAMES[2]
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
    assert result.returncode == (0 if provisioned else 1), output
    assert ("\nstatus=ready" in result.stdout) is provisioned
    assert (f"drift cuadrao-api:{key}" in result.stdout) is not provisioned
    assert "-X PUT" not in (tmp_path / "curl-requests.log").read_text()


@pytest.mark.parametrize(
    "key", (*MODEL_CREDENTIAL_ENV_NAMES, *RETIRED_MODEL_CREDENTIAL_ENV_NAMES)
)
@pytest.mark.parametrize("value", ["", 'synthetic-value-with-"quotes"\nand-newline'])
def test_model_key_status_is_always_redacted(key: str, value: str) -> None:
    source = _source(".github/render-env-sync.sh")
    functions = []
    for name in (
        "is_secret_render_env_key",
        "render_env_raw_value",
        "render_env_status_value",
    ):
        body = source.split(f"{name}() {{", 1)[1].split("\n}", 1)[0]
        functions.append(f"{name}() {{{body}\n}}")
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
