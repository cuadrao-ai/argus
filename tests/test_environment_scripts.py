from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ENV_CONTRACT = ROOT / ".github" / "argus-env.sh"


def _source(path: str) -> str:
    return (ROOT / path).read_text()


def _render_env(service_name: str) -> dict[str, dict[str, str | bool]]:
    render_config = yaml.safe_load(_source("render.yaml"))

    for service in render_config["services"]:
        if service["name"] == service_name:
            return {env["key"]: env for env in service["envVars"]}

    raise AssertionError(f"{service_name} service missing from render.yaml")


def _render_env_payload(
    service_name: str,
    *,
    omit: set[str] | None = None,
    extra: dict[str, str] | None = None,
    overrides: dict[str, str] | None = None,
) -> str:
    omitted = omit or set()
    extra = extra or {}
    overrides = overrides or {}
    rows: list[dict[str, dict[str, str]]] = []

    for key, env in _render_env(service_name).items():
        if key in omitted:
            continue
        value = overrides.get(key)
        if value is None:
            value = str(env.get("value", ""))
            if not value and key != "NEXT_PUBLIC_POSTHOG_KEY":
                value = f"fake-secret-{key.lower()}"
        rows.append({"envVar": {"key": key, "value": value}})

    for key, value in extra.items():
        rows.append({"envVar": {"key": key, "value": value}})

    return json.dumps(rows)


def _workflow_env_payload(
    *,
    omit: set[str] | None = None,
    extra: dict[str, str] | None = None,
    overrides: dict[str, str] | None = None,
) -> str:
    omitted = omit or set()
    extra = extra or {}
    overrides = overrides or {}
    values = {
        "ARGUS_WORKFLOW_DATABASE_URL": "postgres://workflow-db.example/argus",
        "APP_ENV": "production",
        "ARGUS_RENDER_WORKFLOW_PROOF_TASK": "argus-backtests/workflow_proof",
        "ARGUS_WORKFLOW_PROOF_PLAN": "starter",
        "POETRY_VERSION": "2.1.3",
        "ARGUS_BACKTEST_WORKFLOW_TIMEOUT_SECONDS": "300",
        "ARGUS_MARKET_DATA_PROVIDER_MODE": "live_provider",
        "ENABLE_MARKET_DATA_CACHE": "false",
        "ALPACA_API_KEY": "fake-alpaca-key",
        "ALPACA_SECRET_KEY": "fake-alpaca-secret",
        "ALPACA_PAPER_TRADING": "true",
        "ARGUS_PROD_OPENROUTER_API_KEY": "fake-registered-openrouter-key",
        "ARGUS_GUEST_ACCESS_OPENROUTER_API_KEY": "fake-guest-openrouter-key",
        "ARGUS_UTILITY_MODEL": "google/gemini-2.5-flash-lite",
        "ARGUS_UTILITY_FALLBACK_MODEL": "qwen/qwen3.5-9b",
        "ARGUS_CHAT_MODEL": "deepseek/deepseek-v4-flash",
        "ARGUS_CHAT_FALLBACK_MODEL": "qwen/qwen3.5-9b",
        "ARGUS_OPENROUTER_RESULT_SUMMARY_TIMEOUT_SECONDS": "30",
        "ARGUS_STRUCTURED_MODEL": "x-ai/grok-4.3",
        "ARGUS_STRUCTURED_FALLBACK_MODEL": "anthropic/claude-haiku-4.5",
        "ARGUS_CONTEXT_MODEL": "openai/gpt-oss-120b",
        "ARGUS_CONTEXT_FALLBACK_MODEL": "deepseek/deepseek-v4-flash",
        "ARGUS_READOUT_MODEL": "openai/gpt-5.6-luna",
        "ARGUS_READOUT_FALLBACK_MODEL": "openai/gpt-5.6-luna",
    }
    rows: list[dict[str, dict[str, str]]] = []

    for key, default_value in values.items():
        if key in omitted:
            continue
        rows.append({"envVar": {"key": key, "value": overrides.get(key, default_value)}})

    for key, value in extra.items():
        rows.append({"envVar": {"key": key, "value": value}})

    return json.dumps(rows)


def _run_render_release_audit(
    tmp_path: Path,
    *,
    api_env_json: str,
    web_env_json: str,
    workflow_env_json: str | None = None,
    api_service_json: str | None = None,
    web_service_json: str | None = None,
    workflow_service_json: str | None = None,
    expect_mode: str = "safe-off",
    isolate: bool = False,
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    request_log = tmp_path / "curl-requests.log"
    fake_curl = bin_dir / "curl"
    fake_curl.write_text(
        """#!/bin/bash
printf "%s\\n" "$*" >> "$FAKE_CURL_REQUEST_LOG"
case "$*" in
  *"/services/$FAKE_API_SERVICE_ID/env-vars"*)
    printf "%s" "$FAKE_API_ENV_JSON"
    ;;
  *"/services/$FAKE_WEB_SERVICE_ID/env-vars"*)
    printf "%s" "$FAKE_WEB_ENV_JSON"
    ;;
  *"/services/$FAKE_WORKFLOW_SERVICE_ID/env-vars"*)
    printf "%s" "$FAKE_WORKFLOW_ENV_JSON"
    ;;
  *"/services/$FAKE_API_SERVICE_ID"*) printf "%s" "$FAKE_API_SERVICE_JSON" ;;
  *"/services/$FAKE_WEB_SERVICE_ID"*) printf "%s" "$FAKE_WEB_SERVICE_JSON" ;;
  *"/workflows/$FAKE_WORKFLOW_SERVICE_ID"*) printf "%s" "$FAKE_WORKFLOW_SERVICE_JSON" ;;
  *)
    echo "unexpected curl request: $*" >&2
    exit 9
    ;;
esac
""",
    )
    fake_curl.chmod(0o755)

    profile = json.loads(_source(".github/private-alpha-release-profile.json"))
    profile_triggers = {
        surface: json.dumps(
            {"autoDeployTrigger": profile["services"][surface]["auto_deploy_trigger"]}
        )
        for surface in ("api", "web", "workflow")
    }
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "RENDER_API_KEY": "fake-render-token",
            "FAKE_API_SERVICE_ID": "srv-d78tanmuk2gs73e17nn0",
            "FAKE_WEB_SERVICE_ID": "srv-d7ap6bmslomc73eqp8m0",
            "ARGUS_RENDER_WORKFLOW_SERVICE_ID": "wfl-fake-backtests",
            "FAKE_WORKFLOW_SERVICE_ID": "wfl-fake-backtests",
            "FAKE_API_ENV_JSON": api_env_json,
            "FAKE_WEB_ENV_JSON": web_env_json,
            "FAKE_WORKFLOW_ENV_JSON": workflow_env_json or _workflow_env_payload(),
            "FAKE_API_SERVICE_JSON": api_service_json or profile_triggers["api"],
            "FAKE_WEB_SERVICE_JSON": web_service_json or profile_triggers["web"],
            "FAKE_WORKFLOW_SERVICE_JSON": workflow_service_json
            or profile_triggers["workflow"],
            "FAKE_CURL_REQUEST_LOG": str(request_log),
        }
    )

    script = ".github/render-env-sync.sh"
    cwd = str(ROOT)
    if isolate:
        # Mirror the scripts into a root with no .env so argus_load_root_env is a
        # no-op, then scrub workflow secrets from the process env. This reproduces
        # the daily-gate warmup step, which exports neither .env nor the workflow
        # secrets (ALPACA_*/segmented OpenRouter keys) it audits.
        github_dir = tmp_path / ".github"
        github_dir.mkdir()
        for name in (
            "render-env-sync.sh",
            "argus-env.sh",
            "private-alpha-release-profile.py",
            "private-alpha-release-profile.json",
        ):
            copied = github_dir / name
            shutil.copy(ROOT / ".github" / name, copied)
            copied.chmod(0o755)
        for secret in (
            "ALPACA_API_KEY",
            "ALPACA_SECRET_KEY",
            "ARGUS_PROD_OPENROUTER_API_KEY",
            "ARGUS_GUEST_ACCESS_OPENROUTER_API_KEY",
            "OPENROUTER_API_KEY",
            "ARGUS_WORKFLOW_DATABASE_URL",
        ):
            env.pop(secret, None)
        script = str(github_dir / "render-env-sync.sh")
        cwd = str(tmp_path)

    return subprocess.run(
        [
            script,
            "release-config-audit",
            "--expect-mode",
            expect_mode,
        ],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _real_workflow_api_env_payload() -> str:
    return _render_env_payload(
        "argus-api",
        overrides={
            "ARGUS_BACKTEST_JOBS_SHADOW_ENABLED": "true",
            "ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED": "true",
            "ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED": "true",
            "RENDER_API_KEY": "fake-render-token",
        },
    )


def _contract_array(name: str) -> list[str]:
    result = subprocess.run(
        [
            "bash",
            "-c",
            f'source .github/argus-env.sh; printf "%s\\n" "${{{name}[@]}}"',
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.splitlines()


def test_env_example_uses_typed_supabase_postgres_urls() -> None:
    env_example = (ROOT / ".env.example").read_text()

    assert "SUPABASE_POSTGRES_DIRECT_URL=" in env_example
    assert "SUPABASE_POSTGRES_SESSION_POOLER_URL=" in env_example
    assert "SUPABASE_POSTGRES_TRANSACTION_POOLER_URL=" in env_example
    assert "\nDATABASE_URL=" not in env_example
    assert "DATABASE_URL values" not in env_example


def test_qa_script_derives_internal_database_url_from_session_pooler() -> None:
    qa_script = _source(".github/qa.sh")
    env_contract = ENV_CONTRACT.read_text()
    combined = qa_script + "\n" + env_contract

    assert "SUPABASE_POSTGRES_SESSION_POOLER_URL" in env_contract
    assert 'argus_require_env "$name"' in env_contract
    assert 'require_env "DATABASE_URL"' not in combined
    assert 'export DATABASE_URL="$SUPABASE_POSTGRES_SESSION_POOLER_URL"' in env_contract
    assert "SUPABASE_POSTGRES_DIRECT_URL" in combined
    assert "Session Pooler -> internal DATABASE_URL" in qa_script


def test_dev_script_ignores_database_urls_even_when_env_contains_them() -> None:
    dev_script = _source(".github/dev.sh")
    env_contract = ENV_CONTRACT.read_text()
    combined = dev_script + "\n" + env_contract

    assert "unset DATABASE_URL" in env_contract
    assert "SUPABASE_POSTGRES_SESSION_POOLER_URL" in combined
    assert "Database URLs: Ignored" in dev_script


def test_dev_script_disables_disk_market_data_cache_for_stable_memory_qa() -> None:
    dev_script = _source(".github/dev.sh")
    env_contract = ENV_CONTRACT.read_text()

    assert "Synthetic fixtures (no API calls)" in dev_script
    assert "Disk market-data cache: Disabled" in dev_script
    assert "export ENABLE_MARKET_DATA_CACHE=false" in env_contract


def test_dev_and_qa_scripts_source_shared_env_contract() -> None:
    assert ENV_CONTRACT.exists()
    assert 'source "$SCRIPT_DIR/argus-env.sh"' in _source(".github/dev.sh")
    assert 'source "$SCRIPT_DIR/argus-env.sh"' in _source(".github/qa.sh")


def test_shared_env_contract_requires_unset_indirect_env_under_nounset() -> None:
    result = subprocess.run(
        [
            "bash",
            "-c",
            "set -euo pipefail; "
            "source .github/argus-env.sh; "
            "unset OPENROUTER_API_KEY; "
            "argus_require_env OPENROUTER_API_KEY",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "OPENROUTER_API_KEY is required" in result.stdout
    assert "bad substitution" not in result.stderr
    assert "unbound variable" not in result.stderr


def test_render_blueprint_uses_current_env_contract_names_only() -> None:
    render_yaml = _source("render.yaml")
    contract = set(_contract_array("ARGUS_RENDER_API_ENV")) | set(
        _contract_array("ARGUS_RENDER_WEB_ENV")
    )

    for key in (
        "ARGUS_PERSISTENCE_MODE",
        "POETRY_VERSION",
        "ARGUS_DEV_MEMORY_FALLBACK",
        "ARGUS_MARKET_DATA_PROVIDER_MODE",
        "ARGUS_RUNTIME_EVENT_TIMEOUT_SECONDS",
        "ARGUS_RUNTIME_EVENT_KEEPALIVE_SECONDS",
        "ARGUS_CHECKPOINTER_MODE",
        "ARGUS_MOCK_AUTH",
        "ARGUS_CORS_ALLOW_ORIGINS",
        "ARGUS_BACKTEST_JOBS_SHADOW_ENABLED",
        "ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED",
        "ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED",
        "ARGUS_BACKTEST_WORKFLOW_TASK",
        "ARGUS_BACKTEST_REAL_WORKFLOW_TASK",
        "ARGUS_BACKTEST_JOBS_USER_RUNNING_LIMIT",
        "ARGUS_BACKTEST_JOBS_USER_QUEUED_LIMIT",
        "ARGUS_BACKTEST_JOBS_GLOBAL_RUNNING_LIMIT",
        "ARGUS_BACKTEST_JOBS_GLOBAL_QUEUED_LIMIT",
        "NEXT_PUBLIC_ENABLE_SPANISH",
        "NEXT_PUBLIC_ARGUS_API_URL",
        "NEXT_PUBLIC_MOCK_AUTH",
    ):
        assert key in contract
        assert key in render_yaml

    for legacy_key in (
        "NEXT_PUBLIC_API_URL",
        "NEXT_PUBLIC_MOCK_API",
        "AGENT_MODEL",
        "AGENT_FALLBACK_MODEL",
    ):
        assert legacy_key not in render_yaml


def test_render_workflow_task_slug_is_single_current_default() -> None:
    env_example = _source(".env.example")
    env_contract = ENV_CONTRACT.read_text()
    trigger_proof = _source("workflows/trigger_proof.py")

    assert (
        'ARGUS_BACKTEST_WORKFLOW_TASK_DEFAULT="argus-backtests/workflow_proof"'
        in env_contract
    )
    assert (
        'ARGUS_BACKTEST_REAL_WORKFLOW_TASK_DEFAULT="argus-backtests/run_backtest_job"'
        in env_contract
    )
    assert "ARGUS_BACKTEST_WORKFLOW_TASK=argus-backtests/workflow_proof" in env_example
    assert (
        "ARGUS_BACKTEST_REAL_WORKFLOW_TASK=argus-backtests/run_backtest_job"
        in env_example
    )
    assert (
        "ARGUS_RENDER_WORKFLOW_PROOF_TASK=argus-backtests/workflow_proof" in env_example
    )
    assert 'or "argus-backtests/workflow_proof"' in trigger_proof
    assert "argus-render-workflow-proof" not in env_example
    assert "argus-render-workflow-proof" not in trigger_proof


def test_render_python_builds_use_managed_poetry() -> None:
    render_yaml = _source("render.yaml")
    env_contract = ENV_CONTRACT.read_text()
    env_example = _source(".env.example")

    assert 'ARGUS_RENDER_POETRY_VERSION="2.1.3"' in env_contract
    assert "POETRY_VERSION=2.1.3" in env_example
    assert "pip install poetry" not in render_yaml
    assert "pip install poetry" not in env_contract
    assert (
        'ARGUS_RENDER_API_BUILD_COMMAND="poetry config virtualenvs.create false '
        '&& poetry install --only main --no-interaction"'
    ) in env_contract
    assert (
        'ARGUS_RENDER_API_START_COMMAND="poetry run uvicorn argus.api.main:app '
        '--host 0.0.0.0 --port \\$PORT"'
    ) in env_contract
    assert (
        'ARGUS_RENDER_WORKFLOW_BUILD_COMMAND="poetry config virtualenvs.create false '
        '&& poetry install --only main,workflows --no-interaction"'
    ) in env_contract


def test_env_example_declares_render_api_key_once() -> None:
    env_example = _source(".env.example")

    assert env_example.count("\nRENDER_API_KEY=") == 1
    assert "Reuse the RENDER_API_KEY declared" in env_example


def test_render_blueprint_declares_shared_render_env_contract_vars() -> None:
    assert set(_contract_array("ARGUS_RENDER_API_ENV")) == set(_render_env("argus-api"))
    assert set(_contract_array("ARGUS_RENDER_WEB_ENV")) == set(_render_env("argus-app"))
    render_config = yaml.safe_load(_source("render.yaml"))
    services = {service["name"]: service for service in render_config["services"]}
    assert set(services) == {
        "argus-api", "argus-app", "cuadrao-web-staging", "cuadrao-marketing-staging",
    }
    stage = _render_env("cuadrao-web-staging")
    manifest = json.loads(_source("scripts/ops/staging_env_manifest.json"))
    entries = manifest["services"]["web"]["entries"]
    held = {entry["name"] for entry in manifest["services"]["web"]["hold"]}
    assert set(stage) == {entry["name"] for entry in entries} | held | {
        "NEXT_PUBLIC_APP_ENV", "NEXT_PUBLIC_MOCK_AUTH",
    }
    for entry in entries:
        if "value" in entry:
            assert stage[entry["name"]]["value"] == entry["value"]
    marketing = services["cuadrao-marketing-staging"]
    assert (marketing["plan"], marketing["autoDeployTrigger"]) == ("free", "off")
    assert marketing["envVars"] == [
        {"key": "CUADRAO_SITE_INDEXING", "value": "private"}
    ]


def test_render_web_declares_exact_server_only_https_app_origin() -> None:
    api_env = _render_env("argus-api")
    web_env = _render_env("argus-app")
    env_contract = ENV_CONTRACT.read_text()

    transition_origins = (
        "https://argus-app-suz5.onrender.com,https://arguschat.ai,"
        "https://www.arguschat.ai"
    )
    assert api_env["ARGUS_APP_ORIGIN"]["value"] == "https://arguschat.ai"
    assert api_env["ARGUS_CORS_ALLOW_ORIGINS"]["value"] == transition_origins
    assert web_env["ARGUS_APP_ORIGIN"]["value"] == "https://arguschat.ai"
    assert web_env["NEXT_PUBLIC_ARGUS_API_URL"]["value"] == (
        "https://api.arguschat.ai/api/v1"
    )
    assert "ARGUS_APP_ORIGIN" in _contract_array("ARGUS_RENDER_WEB_ENV")
    assert 'ARGUS_PRIVATE_LAUNCH_APP_URL="https://arguschat.ai"' in env_contract
    assert 'ARGUS_PRIVATE_LAUNCH_API_URL="https://api.arguschat.ai"' in env_contract
    assert f'ARGUS_PRIVATE_LAUNCH_CORS_ORIGINS="{transition_origins}"' in env_contract
    assert "NEXT_PUBLIC_ARGUS_APP_ORIGIN" not in env_contract


def test_render_blueprint_syncs_public_supabase_coordinates() -> None:
    api_env = _render_env("argus-api")
    web_env = _render_env("argus-app")

    for env, public_keys in (
        (api_env, ("SUPABASE_URL", "SUPABASE_ANON_KEY")),
        (web_env, ("NEXT_PUBLIC_SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_ANON_KEY")),
    ):
        for key in public_keys:
            assert "value" in env[key]
            assert env[key].get("sync") is not False
            assert "YOUR_" not in str(env[key]["value"])
            assert "your_" not in str(env[key]["value"])


def test_render_blueprint_syncs_non_secret_model_routing() -> None:
    api_env = _render_env("argus-api")

    for key in (
        "ARGUS_UTILITY_MODEL",
        "ARGUS_UTILITY_FALLBACK_MODEL",
        "ARGUS_CHAT_MODEL",
        "ARGUS_CHAT_FALLBACK_MODEL",
        "ARGUS_STRUCTURED_MODEL",
        "ARGUS_STRUCTURED_FALLBACK_MODEL",
        "ARGUS_CONTEXT_MODEL",
        "ARGUS_CONTEXT_FALLBACK_MODEL",
        "ARGUS_READOUT_MODEL",
        "ARGUS_READOUT_FALLBACK_MODEL",
    ):
        assert "value" in api_env[key]
        assert api_env[key].get("sync") is not False
        assert "YOUR_" not in str(api_env[key]["value"])
        assert "your_" not in str(api_env[key]["value"])


def test_render_blueprint_keeps_true_secrets_manual() -> None:
    api_env = _render_env("argus-api")

    for key in (
        "DATABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_JWT_SECRET",
        "RENDER_API_KEY",
        "ARGUS_PROD_OPENROUTER_API_KEY",
        "ARGUS_GUEST_ACCESS_OPENROUTER_API_KEY",
        "ALPACA_API_KEY",
        "ALPACA_SECRET_KEY",
        "ARGUS_OPS_TOKEN",
        "ARGUS_APPROVAL_EMAIL_SMTP_PASSWORD",
    ):
        assert api_env[key] == {"key": key, "sync": False}
    assert "OPENROUTER_API_KEY" not in api_env


def test_workflow_proof_env_contract_is_documented_but_not_blueprinted() -> None:
    env_example = _source(".env.example")
    env_contract = ENV_CONTRACT.read_text()
    render_config = yaml.safe_load(_source("render.yaml"))

    assert "ARGUS_RENDER_WORKFLOW_PROOF_TASK=" in env_example
    assert (
        "ARGUS_WORKFLOW_DATABASE_URL=${SUPABASE_POSTGRES_TRANSACTION_POOLER_URL}"
        in env_example
    )
    assert "ARGUS_WORKFLOW_PROOF_PLAN=" in env_example
    assert "POETRY_VERSION=2.1.3" in env_example
    assert "ARGUS_BACKTEST_WORKFLOW_TIMEOUT_SECONDS=300" in env_example
    assert "ARGUS_OPENROUTER_RESULT_SUMMARY_TIMEOUT_SECONDS=30" in env_example
    assert "ARGUS_RENDER_WORKFLOW_PROOF_ENV=(" in env_contract
    assert "APP_ENV" in env_contract
    assert "ARGUS_WORKFLOW_DATABASE_URL" in env_contract
    assert "ARGUS_RENDER_WORKFLOW_PROOF_TASK" in env_contract
    assert "ARGUS_WORKFLOW_PROOF_PLAN" in env_contract
    assert "POETRY_VERSION" in env_contract
    assert "ARGUS_BACKTEST_WORKFLOW_TIMEOUT_SECONDS" in env_contract
    assert "ARGUS_MARKET_DATA_PROVIDER_MODE" in env_contract
    assert "ENABLE_MARKET_DATA_CACHE" in env_contract
    assert "ALPACA_API_KEY" in env_contract
    assert "ALPACA_SECRET_KEY" in env_contract
    assert "ALPACA_PAPER_TRADING" in env_contract
    assert "ARGUS_PROD_OPENROUTER_API_KEY" in env_contract
    assert "ARGUS_GUEST_ACCESS_OPENROUTER_API_KEY" in env_contract
    assert "ARGUS_UTILITY_MODEL" in env_contract
    assert "ARGUS_UTILITY_FALLBACK_MODEL" in env_contract
    assert "ARGUS_CHAT_MODEL" in env_contract
    assert "ARGUS_CHAT_FALLBACK_MODEL" in env_contract
    assert "ARGUS_OPENROUTER_RESULT_SUMMARY_TIMEOUT_SECONDS" in env_contract
    assert "ARGUS_STRUCTURED_MODEL" in env_contract
    assert "ARGUS_STRUCTURED_FALLBACK_MODEL" in env_contract
    assert "ARGUS_CONTEXT_MODEL" in env_contract
    assert "ARGUS_CONTEXT_FALLBACK_MODEL" in env_contract
    assert "ARGUS_READOUT_MODEL" in env_contract
    assert "ARGUS_READOUT_FALLBACK_MODEL" in env_contract
    workflow_env_section = env_contract.split(
        "ARGUS_RENDER_WORKFLOW_PROOF_ENV=(",
        maxsplit=1,
    )[1].split("\n)", maxsplit=1)[0]
    assert "RENDER_API_KEY" not in workflow_env_section
    render_sync = _source(".github/render-env-sync.sh")
    assert "workflow_render_env_value()" in render_sync
    assert 'release_profile_env_value workflow "$key"' in render_sync
    assert all(service["type"] != "workflow" for service in render_config["services"])


def test_workflow_proof_seed_usage_reuses_stable_proof_principal() -> None:
    proof_script = _source(".github/workflow-proof.sh")

    assert ".github/workflow-proof.sh seed [--user-id <uuid>]" in proof_script
    assert "Seed reuses a stable proof auth/profile by default" in proof_script
    assert "operation_scope=workflows.proof and no conversation" in proof_script
    assert "--conversation-id" not in proof_script
    assert "local or preview Supabase database" in proof_script


def test_render_env_sync_uses_shared_contract_and_single_var_updates() -> None:
    source = _source(".github/render-env-sync.sh")
    env_contract = ENV_CONTRACT.read_text()

    assert 'source "$SCRIPT_DIR/argus-env.sh"' in source
    assert "ARGUS_BACKTEST_WORKFLOW_TASK_DEFAULT" in source
    assert "ARGUS_RENDER_WORKFLOW_BUILD_COMMAND" in env_contract
    assert "ARGUS_RENDER_API_BUILD_COMMAND" in env_contract
    assert "ARGUS_RENDER_API_START_COMMAND" in env_contract
    assert "ARGUS_RENDER_WORKFLOW_START_COMMAND" in env_contract
    assert "/v1/services/${service_id}/env-vars/${key}" in source
    assert "ARGUS_BACKTEST_JOBS_SHADOW_ENABLED true" in source
    assert "ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED true" in source
    assert "ARGUS_BACKTEST_JOBS_USER_RUNNING_LIMIT" in source
    assert "ARGUS_BACKTEST_JOBS_GLOBAL_QUEUED_LIMIT" in source


def test_render_env_sync_pushes_workflow_llm_readout_env() -> None:
    source = _source(".github/render-env-sync.sh")
    workflow_block = source.split("sync_workflow_proof() {", maxsplit=1)[1].split(
        "\n}",
        maxsplit=1,
    )[0]

    for key in (
        "ARGUS_PROD_OPENROUTER_API_KEY",
        "ARGUS_GUEST_ACCESS_OPENROUTER_API_KEY",
        "ARGUS_UTILITY_MODEL",
        "ARGUS_UTILITY_FALLBACK_MODEL",
        "ARGUS_CHAT_MODEL",
        "ARGUS_CHAT_FALLBACK_MODEL",
        "ARGUS_STRUCTURED_MODEL",
        "ARGUS_STRUCTURED_FALLBACK_MODEL",
        "ARGUS_CONTEXT_MODEL",
        "ARGUS_CONTEXT_FALLBACK_MODEL",
        "ARGUS_READOUT_MODEL",
        "ARGUS_READOUT_FALLBACK_MODEL",
    ):
        assert f"require_local_env {key}" in workflow_block
        assert 'release_profile_env_value workflow "$key"' in source
    assert 'for key in "${ARGUS_RENDER_WORKFLOW_PROOF_ENV[@]}"; do' in workflow_block
    assert (
        'put_render_env "$WORKFLOW_SERVICE_ID" "$key" '
        '"$(workflow_render_env_value "$key")"'
    ) in workflow_block
    assert 'release_profile_env_value workflow "$key"' in source
    assert "ARGUS_WORKFLOW_DATABASE_URL" in source
    assert "require_local_env ALPACA_API_KEY" in source
    assert "require_local_env ALPACA_SECRET_KEY" in source


def test_render_env_sync_can_release_workflow_after_env_updates() -> None:
    source = _source(".github/render-env-sync.sh")

    assert ".github/render-env-sync.sh workflow-release [commit]" in source
    assert ".github/render-env-sync.sh workflow-version-status" in source
    assert "sync_workflow_release()" in source
    assert "print_workflow_version_status()" in source
    assert 'render workflows versions release "$WORKFLOW_SERVICE_ID"' in source
    assert 'render workflows versions list "$WORKFLOW_SERVICE_ID"' in source
    assert "ARGUS_RENDER_WORKFLOW_RELEASE_COMMIT" not in source
    assert "ARGUS_RENDER_WORKFLOW_RELEASE_VERSION_ID" not in source
    assert '"commit=\\(.name // "<missing>")"' in source
    assert "--wait" in source
    assert "--confirm" in source
    assert 'for key in "${ARGUS_RENDER_WORKFLOW_PROOF_ENV[@]}"; do' in source
    assert 'workflow_render_env_value "$key"' in source
    for key in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY"):
        assert key in source
    assert 'release_profile_env_value workflow "$key"' in source
    assert "workflow-runtime" in source
    assert "https://api.render.com/v1/workflows/${WORKFLOW_SERVICE_ID}" in source
    assert "render_workflow_json" in source
    assert "release_profile_auto_deploy_trigger workflow" in source
    assert "autoDeployTrigger: $auto_deploy_trigger" in source
    assert 'autoDeployTrigger: "off"' not in source


def test_render_env_sync_workflow_proof_uses_the_profile_live_provider_mode() -> None:
    source = _source(".github/render-env-sync.sh")

    value_block = source.split("workflow_render_env_value() {", maxsplit=1)[1].split(
        "\n}",
        maxsplit=1,
    )[0]
    assert 'release_profile_env_value workflow "$key"' in value_block
    assert 'echo "${ARGUS_MARKET_DATA_PROVIDER_MODE:-live_provider}"' not in value_block


def test_render_env_sync_prints_api_deploy_status_without_mutation() -> None:
    source = _source(".github/render-env-sync.sh")

    assert ".github/render-env-sync.sh api-deploy-status" in source
    assert "print_api_deploy_status()" in source
    assert "/v1/services/${service_id}/deploys?limit=1" in source
    assert 'print_deploy_status "$API_SERVICE_ID" "argus-api"' in source
    assert "commit_short" in source
    assert "deploy_id" in source

    deploy_status_block = source.split(
        "print_api_deploy_status() {",
        maxsplit=1,
    )[1].split("\n}", maxsplit=1)[0]

    assert "put_render_env" not in deploy_status_block
    assert "delete_render_env" not in deploy_status_block


def test_render_env_sync_prints_web_deploy_status_without_mutation() -> None:
    env_contract = ENV_CONTRACT.read_text()
    source = _source(".github/render-env-sync.sh")

    assert 'ARGUS_PRIVATE_LAUNCH_WEB_SERVICE_ID="srv-d7ap6bmslomc73eqp8m0"' in (
        env_contract
    )
    assert ".github/render-env-sync.sh web-deploy-status" in source
    assert "WEB_SERVICE_ID" in source
    assert "print_web_deploy_status()" in source
    assert "/v1/services/${service_id}/deploys?limit=1" in source
    assert 'print_deploy_status "$WEB_SERVICE_ID" "argus-app"' in source

    deploy_status_block = source.split(
        "print_web_deploy_status() {",
        maxsplit=1,
    )[1].split("\n}", maxsplit=1)[0]

    assert "put_render_env" not in deploy_status_block
    assert "delete_render_env" not in deploy_status_block


def test_render_env_sync_can_sync_api_runtime_config() -> None:
    source = _source(".github/render-env-sync.sh")

    assert ".github/render-env-sync.sh api-runtime" in source
    api_runtime_block = source.split("sync_api_runtime() {", maxsplit=1)[1].split(
        "sync_workflow_proof() {", maxsplit=1
    )[0]
    assert "https://api.render.com/v1/services/${API_SERVICE_ID}" in api_runtime_block
    assert "envSpecificDetails" in api_runtime_block
    assert "buildCommand: $build_command" in api_runtime_block
    assert "startCommand: $start_command" in api_runtime_block
    assert 'put_render_env "$API_SERVICE_ID" POETRY_VERSION' in api_runtime_block
    assert ".buildConfig + {buildCommand: $build_command}" in source
    assert "ARGUS_RENDER_WORKFLOW_BUILD_COMMAND" in source
    assert "ARGUS_RENDER_WORKFLOW_START_COMMAND" in source
    assert "set -x" not in source


def test_env_example_separates_shadow_jobs_from_workflow_dispatch() -> None:
    env_example = _source(".env.example")
    shadow_block = env_example.split("# Backtest jobs shadow mode", maxsplit=1)[1].split(
        "# Backtest jobs workflow dispatch",
        maxsplit=1,
    )[0]
    dispatch_block = env_example.split(
        "# Backtest jobs workflow dispatch",
        maxsplit=1,
    )[1].split("# Collections", maxsplit=1)[0]

    assert "workflow dispatch" not in shadow_block.lower()
    assert "durable" in shadow_block
    assert "ARGUS_BACKTEST_JOBS_SHADOW_ENABLED=false" in shadow_block
    assert "ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED=false" in dispatch_block
    assert "ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED=false" in dispatch_block
    assert "ARGUS_BACKTEST_WORKFLOW_TASK=argus-backtests/workflow_proof" in dispatch_block
    assert (
        "ARGUS_BACKTEST_REAL_WORKFLOW_TASK=argus-backtests/run_backtest_job"
        in dispatch_block
    )
    assert "still returns the current in-process result" in dispatch_block


def test_render_env_sync_can_inspect_and_safely_disable_dispatch() -> None:
    source = _source(".github/render-env-sync.sh")
    dispatch_off_block = source.split("sync_api_safe_off() {", maxsplit=1)[1].split(
        "\n}",
        maxsplit=1,
    )[0]

    assert ".github/render-env-sync.sh api-status" in source
    assert ".github/render-env-sync.sh api-safe-off" in source
    assert ".github/render-env-sync.sh api-proof-shadow-on" in source
    assert ".github/render-env-sync.sh api-real-workflow-on" in source
    assert "print_api_status()" in source
    assert "<redacted-present>" in source
    assert "<missing-or-empty>" in source
    assert 'if [ "$status" = "404" ]' in source
    assert "already absent ${service_id}:${key}" in source
    assert "ARGUS_BACKTEST_JOBS_SHADOW_ENABLED false" in dispatch_off_block
    assert "ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED false" in dispatch_off_block
    assert "ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED false" in dispatch_off_block
    assert "ARGUS_BACKTEST_WORKFLOW_TASK" in dispatch_off_block
    assert "ARGUS_BACKTEST_REAL_WORKFLOW_TASK" in dispatch_off_block
    assert 'delete_render_env "$API_SERVICE_ID" RENDER_API_KEY' in dispatch_off_block


def test_mode_scripts_pin_render_workflow_dispatch_off() -> None:
    env_contract = ENV_CONTRACT.read_text()
    dev_block = env_contract.split("argus_export_dev_mode() {", maxsplit=1)[1].split(
        "\n}",
        maxsplit=1,
    )[0]
    qa_block = env_contract.split("argus_export_qa_mode() {", maxsplit=1)[1].split(
        "\n}",
        maxsplit=1,
    )[0]

    # Dev mode: hard-off. Local iteration must never spend on Render.
    assert "export ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED=false" in dev_block
    assert "export ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED=false" in dev_block

    # QA mode: default-off; ceremony runs opt in by exporting before qa.sh.
    assert (
        "ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED="
        '"${ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED:-false}"' in qa_block
    )
    assert (
        "ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED="
        '"${ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED:-false}"' in qa_block
    )


def test_render_env_sync_separates_proof_and_real_api_modes() -> None:
    source = _source(".github/render-env-sync.sh")
    proof_block = source.split("sync_api_proof_shadow_on() {", maxsplit=1)[1].split(
        "\n}",
        maxsplit=1,
    )[0]
    real_block = source.split("sync_api_real_workflow_on() {", maxsplit=1)[1].split(
        "\n}",
        maxsplit=1,
    )[0]

    assert "ARGUS_BACKTEST_JOBS_SHADOW_ENABLED true" in proof_block
    assert "ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED true" in proof_block
    assert "ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED false" in proof_block
    assert (
        'ARGUS_BACKTEST_WORKFLOW_TASK "$ARGUS_BACKTEST_WORKFLOW_TASK_DEFAULT"'
        in proof_block
    )
    assert (
        'ARGUS_BACKTEST_REAL_WORKFLOW_TASK "$ARGUS_BACKTEST_REAL_WORKFLOW_TASK_DEFAULT"'
        in proof_block
    )
    assert (
        'put_render_env "$API_SERVICE_ID" RENDER_API_KEY "$RENDER_API_KEY"' in proof_block
    )

    assert "ARGUS_BACKTEST_JOBS_SHADOW_ENABLED" in real_block
    assert "ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED" in real_block
    assert "ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED" in real_block
    assert 'release_profile_env_value api "$key"' in real_block
    assert (
        'put_render_env "$API_SERVICE_ID" RENDER_API_KEY "$RENDER_API_KEY"' in real_block
    )


def test_render_env_sync_can_audit_release_config_without_mutation() -> None:
    source = _source(".github/render-env-sync.sh")

    assert ".github/render-env-sync.sh release-config-audit" in source
    assert "--expect-mode <safe-off|proof-shadow|real-workflow>" in source
    assert "audit_release_config()" in source
    assert "audit_render_service_config" in source
    assert "release_profile_env_pairs" in source
    assert "release_profile_required_present" in source
    assert "release_profile_allowed_keys" in source
    assert "ARGUS_RENDER_WORKFLOW_PROOF_ENV" in source
    assert "workflow_expected_env_pairs" in source
    assert "ARGUS_FORBIDDEN_LEGACY_ENV" in source
    assert "render_env_fingerprint" in source
    assert "workflow_env_fingerprint=" in source
    assert "workflow_env_status=" in source
    assert "env_fingerprint=" in source
    assert "status=ready" in source
    assert "ARGUS_BACKTEST_WORKFLOW_TASK" in source
    assert "ARGUS_BACKTEST_REAL_WORKFLOW_TASK" in source
    assert "<redacted-present>" in source
    assert "<missing-or-empty>" in source

    audit_block = source.split("audit_release_config() {", maxsplit=1)[1].split(
        "\n}",
        maxsplit=1,
    )[0]
    assert "put_render_env" not in audit_block
    assert "delete_render_env" not in audit_block
    assert "curl -fsS" not in audit_block


def test_render_env_sync_audit_uses_large_render_env_page(
    tmp_path: Path,
) -> None:
    result = _run_render_release_audit(
        tmp_path,
        api_env_json=_render_env_payload(
            "argus-api",
            overrides={
                "RENDER_API_KEY": "",
                "ARGUS_BACKTEST_JOBS_SHADOW_ENABLED": "false",
                "ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED": "false",
                "ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED": "false",
            },
        ),
        web_env_json=_render_env_payload("argus-app"),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    request_log = tmp_path / "curl-requests.log"
    assert "env-vars?limit=100" in request_log.read_text()


def test_render_env_sync_audit_includes_workflow_env_parity(
    tmp_path: Path,
) -> None:
    result = _run_render_release_audit(
        tmp_path,
        expect_mode="real-workflow",
        api_env_json=_real_workflow_api_env_payload(),
        web_env_json=_render_env_payload("argus-app"),
        workflow_env_json=_workflow_env_payload(),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "ok argus-backtests:ARGUS_MARKET_DATA_PROVIDER_MODE=live_provider" in (
        result.stdout
    )
    assert "ok argus-backtests:ARGUS_WORKFLOW_DATABASE_URL=<redacted-present>" in (
        result.stdout
    )
    assert "ok argus-api:ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED=true" in result.stdout
    assert "workflow_env_status=ready" in result.stdout
    assert "autodeploy_status=ready" in result.stdout
    assert "status=ready" in result.stdout
    assert "postgres://workflow-db.example/argus" not in result.stdout


def test_render_env_sync_audit_accepts_required_turnstile_site_key(
    tmp_path: Path,
) -> None:
    result = _run_render_release_audit(
        tmp_path,
        expect_mode="real-workflow",
        api_env_json=_real_workflow_api_env_payload(),
        web_env_json=_render_env_payload(
            "argus-app",
            extra={
                "NEXT_PUBLIC_ARGUS_TURNSTILE_SITE_KEY": "fake-public-site-key",
            },
        ),
        workflow_env_json=_workflow_env_payload(),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "ok argus-app:NEXT_PUBLIC_ARGUS_TURNSTILE_SITE_KEY=<present>" in result.stdout
    assert "status=ready" in result.stdout


def test_render_env_sync_skips_workflow_env_gate_outside_real_workflow_mode(
    tmp_path: Path,
) -> None:
    result = _run_render_release_audit(
        tmp_path,
        expect_mode="safe-off",
        api_env_json=_render_env_payload(
            "argus-api",
            overrides={
                "RENDER_API_KEY": "",
                "ARGUS_BACKTEST_JOBS_SHADOW_ENABLED": "false",
                "ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED": "false",
                "ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED": "false",
            },
        ),
        web_env_json=_render_env_payload("argus-app"),
        workflow_env_json=_workflow_env_payload(
            overrides={"ARGUS_MARKET_DATA_PROVIDER_MODE": "synthetic_unit_fixture"},
            omit={
                "ARGUS_PROD_OPENROUTER_API_KEY",
                "ARGUS_GUEST_ACCESS_OPENROUTER_API_KEY",
            },
        ),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "workflow_env_status=skipped" in result.stdout
    assert "status=ready" in result.stdout
    assert "drift argus-backtests:" not in result.stdout


def test_render_env_sync_audit_workflow_secrets_ready_without_local_secrets(
    tmp_path: Path,
) -> None:
    # Regression for the daily-gate warmup step: it audits the workflow service
    # without exporting workflow secrets (Alpaca/segmented OpenRouter) or a .env.
    # The audit must verify those secrets are present on Render, not in the audit
    # runner's local env, so it stays ready even when the runner has none of them.
    result = _run_render_release_audit(
        tmp_path,
        expect_mode="real-workflow",
        api_env_json=_real_workflow_api_env_payload(),
        web_env_json=_render_env_payload("argus-app"),
        workflow_env_json=_workflow_env_payload(),
        isolate=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    for secret in (
        "ALPACA_API_KEY",
        "ALPACA_SECRET_KEY",
        "ARGUS_PROD_OPENROUTER_API_KEY",
        "ARGUS_GUEST_ACCESS_OPENROUTER_API_KEY",
    ):
        assert f"ok argus-backtests:{secret}=<redacted-present>" in result.stdout
        assert f"drift argus-backtests:{secret}" not in result.stdout
    assert "ok argus-backtests:ARGUS_WORKFLOW_DATABASE_URL=<redacted-present>" in (
        result.stdout
    )
    assert "workflow_env_status=ready" in result.stdout
    assert "status=ready" in result.stdout


def test_render_env_sync_audit_flags_workflow_secret_missing_on_render(
    tmp_path: Path,
) -> None:
    # The unconditional <redacted-present> expectation must still catch a secret
    # that is genuinely absent on the Render workflow service.
    result = _run_render_release_audit(
        tmp_path,
        expect_mode="real-workflow",
        api_env_json=_real_workflow_api_env_payload(),
        web_env_json=_render_env_payload("argus-app"),
        workflow_env_json=_workflow_env_payload(
            omit={"ARGUS_GUEST_ACCESS_OPENROUTER_API_KEY"}
        ),
        isolate=True,
    )

    assert result.returncode == 1
    assert (
        "drift argus-backtests:ARGUS_GUEST_ACCESS_OPENROUTER_API_KEY "
        "expected=<redacted-present> actual=<missing-or-empty>"
    ) in result.stdout
    assert "workflow_env_status=drift" in result.stdout


def test_render_env_sync_audit_fails_when_workflow_provider_mode_is_not_live(
    tmp_path: Path,
) -> None:
    result = _run_render_release_audit(
        tmp_path,
        expect_mode="real-workflow",
        api_env_json=_real_workflow_api_env_payload(),
        web_env_json=_render_env_payload("argus-app"),
        workflow_env_json=_workflow_env_payload(
            overrides={"ARGUS_MARKET_DATA_PROVIDER_MODE": "synthetic_unit_fixture"},
        ),
    )

    assert result.returncode == 1
    assert (
        "drift argus-backtests:ARGUS_MARKET_DATA_PROVIDER_MODE "
        "expected=live_provider actual=synthetic_unit_fixture"
    ) in result.stdout
    assert "workflow_env_status=drift" in result.stdout
    assert "status=drift" in result.stdout
    assert "fake-alpaca-secret" not in result.stdout


def test_render_env_sync_audit_rejects_render_api_key_on_workflow_runtime(
    tmp_path: Path,
) -> None:
    result = _run_render_release_audit(
        tmp_path,
        expect_mode="real-workflow",
        api_env_json=_real_workflow_api_env_payload(),
        web_env_json=_render_env_payload("argus-app"),
        workflow_env_json=_workflow_env_payload(
            extra={"RENDER_API_KEY": "fake-render-token"},
        ),
    )

    assert result.returncode == 1
    assert "forbidden argus-backtests:RENDER_API_KEY unexpected_live_env" in (
        result.stdout
    )
    assert "fake-render-token" not in result.stdout
    assert "workflow_env_status=drift" in result.stdout


def test_render_env_sync_audit_fails_when_contract_key_is_missing(
    tmp_path: Path,
) -> None:
    result = _run_render_release_audit(
        tmp_path,
        api_env_json=_render_env_payload(
            "argus-api",
            omit={"MARKET_DATA_CACHE_TTL"},
            overrides={"RENDER_API_KEY": ""},
        ),
        web_env_json=_render_env_payload("argus-app"),
    )

    assert result.returncode == 1
    assert "drift argus-api:MARKET_DATA_CACHE_TTL" in result.stdout
    assert "status=drift" in result.stdout


def test_render_env_sync_audit_rejects_frontend_secrets_and_legacy_keys(
    tmp_path: Path,
) -> None:
    result = _run_render_release_audit(
        tmp_path,
        api_env_json=_render_env_payload(
            "argus-api",
            overrides={"RENDER_API_KEY": ""},
        ),
        web_env_json=_render_env_payload(
            "argus-app",
            extra={
                "SUPABASE_SERVICE_ROLE_KEY": "leaked-service-role",
                "NEXT_PUBLIC_API_URL": "https://legacy.example.test",
            },
        ),
    )

    assert result.returncode == 1
    assert "forbidden argus-app:SUPABASE_SERVICE_ROLE_KEY" in result.stdout
    assert "forbidden argus-app:NEXT_PUBLIC_API_URL" in result.stdout
    assert "status=drift" in result.stdout


def test_render_env_sync_audit_declares_mode_specific_render_key_contract() -> None:
    source = _source(".github/render-env-sync.sh")

    assert "expected_api_mode_pairs()" in source
    assert "safe-off)" in source
    assert "proof-shadow)" in source
    assert "real-workflow)" in source
    assert "RENDER_API_KEY=<missing-or-empty>" in source
    assert "RENDER_API_KEY=<redacted-present>" in source


def test_render_blueprint_preserves_optional_posthog_key() -> None:
    env_contract = _contract_array("ARGUS_RENDER_WEB_ENV")
    web_env = _render_env("argus-app")

    assert "NEXT_PUBLIC_POSTHOG_KEY" in env_contract
    assert web_env["NEXT_PUBLIC_POSTHOG_KEY"] == {
        "key": "NEXT_PUBLIC_POSTHOG_KEY",
        "sync": False,
    }


def test_warmup_script_defaults_to_private_launch_render_urls() -> None:
    warmup = _source(".github/warmup-render.sh")
    env_contract = ENV_CONTRACT.read_text()

    assert 'ARGUS_PRIVATE_LAUNCH_APP_URL="https://arguschat.ai"' in env_contract
    assert "https://api.arguschat.ai" in env_contract
    assert "ARGUS_PRIVATE_LAUNCH_APP_URL" in warmup
    assert "ARGUS_PRIVATE_LAUNCH_API_URL" in warmup
    assert "/health" in warmup
    assert "Argus product path is ready for testers" in warmup


def test_warmup_script_checks_product_readiness_endpoint() -> None:
    warmup = _source(".github/warmup-render.sh")

    assert 'source "$SCRIPT_DIR/argus-env.sh"' in warmup
    assert "argus_load_root_env" in warmup
    assert "/internal/readiness" in warmup
    assert "ARGUS_OPS_TOKEN" in warmup
    assert "Authorization: Bearer ${OPS_TOKEN}" in warmup


def test_warmup_script_can_assert_expected_api_mode_without_mutating_render() -> None:
    warmup = _source(".github/warmup-render.sh")

    assert "--expect-mode <safe-off|proof-shadow|real-workflow>" in warmup
    assert "assert_api_mode()" in warmup
    assert '"$SCRIPT_DIR/render-env-sync.sh" release-config-audit' in warmup
    assert '--expect-mode "$mode"' in warmup
    assert 'if ! status="$(' in warmup
    assert 'printf "%s\\n" "$status"' in warmup
    assert "env_fingerprint=" in warmup
    assert "workflow_env_fingerprint=" in warmup
    assert "workflow_env_status=ready" in warmup
    assert "status=ready" in warmup
    assert "put_render_env" not in warmup
    assert "delete_render_env" not in warmup


def test_warmup_script_runs_remote_workflow_proof_for_real_workflow_mode() -> None:
    warmup = _source(".github/warmup-render.sh")

    assert "run_workflow_runtime_proof()" in warmup
    assert 'if [ "$mode" != "real-workflow" ]; then' in warmup
    assert '.github/workflow-proof.sh seed --nonce "$nonce"' in warmup
    assert '.github/workflow-proof.sh remote --job-id "$job_id" --nonce "$nonce"' in (
        warmup
    )
    assert (
        '.github/workflow-proof.sh verify --job-id "$job_id" '
        '--expect-nonce "$nonce" --expect-provider-mode live_provider'
    ) in warmup
    assert "workflow_runtime_provider_mode=live_provider" in warmup
    assert "workflow_runtime_proof=ready" in warmup


def test_warmup_script_runs_stale_job_scan_when_supabase_verifier_env_exists() -> None:
    warmup = _source(".github/warmup-render.sh")

    assert ".github/stale-backtest-jobs.sh" in warmup
    assert "ARGUS_STALE_JOBS_SUPABASE_URL" in warmup
    assert "ARGUS_STALE_JOBS_SUPABASE_SERVICE_ROLE_KEY" in warmup
    assert "Skipping stale backtest job scan" in warmup
    assert "set -x" not in warmup


def test_private_launch_runbook_uses_real_workflow_readiness_gate() -> None:
    runbook = _source("docs/PRIVATE_LAUNCH_RUNBOOK.md")
    before_sessions = runbook.split("## Before Tester Sessions", maxsplit=1)[1].split(
        "## Backtest Workflow Modes", maxsplit=1
    )[0]
    normalized_before_sessions = " ".join(before_sessions.split())

    assert ".github/render-env-sync.sh api-real-workflow-on" in before_sessions
    assert ".github/render-env-sync.sh api-deploy-status" in before_sessions
    assert ".github/render-env-sync.sh web-deploy-status" in before_sessions
    assert ".github/render-env-sync.sh workflow-version-status" in before_sessions
    assert "argus-api" in before_sessions
    assert "argus-app" in before_sessions
    assert "argus-backtests" in before_sessions
    assert "`argus-api`, then `argus-app`, then **`argus-backtests`**" in (
        before_sessions
    )
    assert "workflow_commit_mismatch" in before_sessions
    assert "argus-maintenance" not in runbook
    assert "cron-deploy-status" not in runbook
    assert ".github/warmup-render.sh --expect-mode real-workflow" in before_sessions
    assert ".github/canary-render.sh" in before_sessions
    assert (
        "API deploy-status, app deploy-status, workflow version status, local smoke, warmup, both "
        "canary surfaces, and the release manifest" in normalized_before_sessions
    )
    assert "both scripts pass" not in before_sessions
    assert ".github/stale-backtest-jobs.sh" in runbook
    assert "api-safe-off` is the default private-alpha tester mode" not in runbook
    assert "NEXT_PUBLIC_POSTHOG_KEY" in runbook


def test_private_launch_runbook_smoke_matches_three_action_card_and_dark_drawers() -> (
    None
):
    runbook = _source("docs/PRIVATE_LAUNCH_RUNBOOK.md")
    smoke_test = runbook.split("## Smoke Test", maxsplit=1)[1].split(
        "## Supabase Persistence Check",
        maxsplit=1,
    )[0]
    normalized_smoke_test = " ".join(smoke_test.split())

    for expected in (
        "Cold-start starter chips are visible",
        "do not reference 2024",
        "Spanish prompt",
        "exactly three card-scoped, structured actions",
        "Run backtest",
        "Change assumptions",
        "Cancel",
        "`Change dates` and `Change asset` do not render as separate actions",
        "ARGUS_IN_PLACE_CARD_EDITS_ENABLED=false",
        "the capital and dates drawers do not render",
        "Quick take",
        "Explain result",
        "Retry",
        "Reloading the page preserves the conversation, job state, and result",
        "Feedback can be submitted",
    ):
        assert expected in normalized_smoke_test

    assert (
        "`Change dates` updates the confirmation/result period"
        not in normalized_smoke_test
    )
    assert "`Change asset` preserves the explicit period" not in normalized_smoke_test
