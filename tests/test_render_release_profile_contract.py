from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import yaml

from tests.test_environment_scripts import (
    _contract_array,
    _real_workflow_api_env_payload,
    _render_env_payload,
    _run_render_release_audit,
    _workflow_env_payload,
)

ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_render_config_audit_uses_the_checked_in_release_profile() -> None:
    source = _source(".github/render-env-sync.sh")

    assert "private-alpha-release-profile.py" in source
    assert "env-pairs" in source
    assert "required-present" in source
    assert "release_profile_hash=" in source
    assert "release_profile_status=ready" in source


def test_warmup_passes_through_release_profile_proof() -> None:
    source = _source(".github/warmup-render.sh")

    assert "release_profile_hash" in source
    assert "release_profile_status=ready" in source


def test_phantom_maintenance_surface_is_absent_but_operator_job_remains() -> None:
    render_yaml = _source("render.yaml")
    env_contract = _source(".github/argus-env.sh")
    env_sync = _source(".github/render-env-sync.sh")

    assert "argus-maintenance" not in render_yaml
    assert "ARGUS_RENDER_CRON_ENV" not in env_contract
    assert "ARGUS_RENDER_MAINTENANCE_SERVICE_NAME" not in env_contract
    assert "cron-deploy-status" not in env_sync
    assert (ROOT / "scripts" / "ops" / "scheduled_maintenance.py").is_file()


def test_release_docs_name_three_live_services_without_a_cron_surface() -> None:
    runbook = _source("docs/PRIVATE_LAUNCH_RUNBOOK.md")
    data_model = _source("docs/DATA_MODEL.md")
    release_contract = _source("docs/specs/private-alpha-ci-cd-sota.md")
    manifest = _source("docs/release-manifests/TEMPLATE.md")

    for service in ("argus-api", "argus-app", "argus-backtests"):
        assert service in runbook
        assert service in release_contract
        assert service in manifest
    for source in (runbook, data_model, release_contract, manifest):
        assert "argus-maintenance" not in source
        assert "cron-deploy-status" not in source
    assert "scripts/ops/scheduled_maintenance.py" in runbook
    assert "operator-run" in runbook


def test_release_contract_keeps_all_three_services_on_manual_deploys() -> None:
    profile = json.loads(_source(".github/private-alpha-release-profile.json"))
    render_config = yaml.safe_load(_source("render.yaml"))
    render_by_name = {service["name"]: service for service in render_config["services"]}
    runbook = _source("docs/PRIVATE_LAUNCH_RUNBOOK.md")

    # Founder decision, 2026-09-13 (#614): a Blueprint sync must not enable
    # autodeploy, so render.yaml carries the quoted string rather than YAML false.
    for surface in ("api", "web", "workflow", "marketing"):
        assert profile["services"][surface]["auto_deploy_trigger"] == "off"
    assert render_by_name["cuadrao-api"]["autoDeployTrigger"] == "off"
    assert render_by_name["cuadrao-web"]["autoDeployTrigger"] == "off"
    assert "argus-backtests" not in render_by_name
    assert "`autoDeployTrigger: off`" in runbook
    assert "argus-api" in runbook
    assert "argus-app" in runbook
    assert "argus-backtests" in runbook


def test_blueprint_matches_the_live_dashboard_service_shape() -> None:
    render_config = yaml.safe_load(_source("render.yaml"))
    services = {service["name"]: service for service in render_config["services"]}
    web = services["cuadrao-web"]
    assert (
        web["rootDir"],
        web["branch"],
        web["buildCommand"],
        web["startCommand"],
    ) == (
        "marketing",
        "main",
        "bun install --frozen-lockfile && bun run build --webpack",
        "bun run start -- -p $PORT",
    )
    assert "envVars" not in web
    stage_api = services["cuadrao-api-staging"]
    assert (
        stage_api["runtime"],
        stage_api["branch"],
        stage_api["plan"],
        stage_api["autoDeployTrigger"],
        stage_api["buildCommand"],
    ) == (
        "python",
        "codex/private-alpha-next",
        "0.5c-512mb",
        "checksPass",
        "poetry install",
    )
    manifest = json.loads(_source("scripts/ops/staging_env_manifest.json"))
    declared = {item["key"]: item for item in stage_api["envVars"]}
    assert declared == {
        entry["name"]: {
            "key": entry["name"],
            **({"value": entry["value"]} if "value" in entry else {"sync": False}),
        }
        for entry in manifest["services"]["api"]["entries"]
    }
    assert services["cuadrao-marketing-staging"]["branch"] == "main"
    assert "NEXT_PUBLIC_ARGUS_API_URL" in _contract_array("ARGUS_RENDER_WEB_ENV")
    assert "NEXT_PUBLIC_ARGUS_API_URL" in {
        item["key"] for item in services["argus-app"]["envVars"]
    }


def test_argus_api_disables_the_default_render_subdomain() -> None:
    render_config = yaml.safe_load(_source("render.yaml"))
    render_by_name = {service["name"]: service for service in render_config["services"]}
    runbook = _source("docs/PRIVATE_LAUNCH_RUNBOOK.md")
    waitlist_floor = runbook.split("### Waitlist rollback floor", 1)[1]

    assert render_by_name["cuadrao-api"]["renderSubdomainPolicy"] == "disabled"
    assert "renderSubdomainPolicy" not in render_by_name["cuadrao-web"]
    assert render_by_name["cuadrao-api-staging"]["renderSubdomainPolicy"] == "enabled"
    assert "https://argus-ohr5.onrender.com" in waitlist_floor
    assert "HTTP `404`" in waitlist_floor
    assert "Cloudflare Worker" in waitlist_floor
    assert "CF-Connecting-IP" in waitlist_floor
    assert "#674" in waitlist_floor
    assert "release-config-audit` does not read this setting" in waitlist_floor
    assert "serviceDetails.renderSubdomainPolicy=disabled" in waitlist_floor
    assert "#694" in waitlist_floor


def test_workflow_version_status_derives_proof_from_ready_version(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_render = bin_dir / "render"
    fake_render.write_text(
        "#!/bin/bash\n"
        'printf \'%s\' \'[{"createdAt":"2026-08-12T15:00:00Z",'
        '"id":"wfv-current","name":"d67cef9",'
        '"status":"ready","workflowId":"wfl-test"}]\'\n',
        encoding="utf-8",
    )
    fake_render.chmod(0o755)
    fake_curl = bin_dir / "curl"
    fake_curl.write_text(
        "#!/bin/bash\n"
        'printf \'%s\' \'[{"envVar":{"key":'
        '"ARGUS_RENDER_WORKFLOW_RELEASE_COMMIT","value":"stale000"}},'
        '{"envVar":{"key":"ARGUS_RENDER_WORKFLOW_RELEASE_VERSION_ID",'
        '"value":"wfv-stale"}}]\'\n',
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "RENDER_API_KEY": "fake-render-token",
            "ARGUS_RENDER_WORKFLOW_SERVICE_ID": "wfl-test",
        }
    )

    result = subprocess.run(
        [str(ROOT / ".github" / "render-env-sync.sh"), "workflow-version-status"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "workflow_version_id=wfv-current" in result.stdout
    assert "status=ready" in result.stdout
    assert "commit=d67cef9" in result.stdout
    assert "stale000" not in result.stdout
    assert "expected_workflow_version_id" not in result.stdout


def test_render_env_sync_audit_reports_a_service_that_leaves_manual_deploys(
    tmp_path: Path,
) -> None:
    profile = json.loads(_source(".github/private-alpha-release-profile.json"))
    expected = profile["services"]["workflow"]["auto_deploy_trigger"]

    result = _run_render_release_audit(
        tmp_path,
        expect_mode="real-workflow",
        api_env_json=_real_workflow_api_env_payload(),
        web_env_json=_render_env_payload("cuadrao-web"),
        workflow_env_json=_workflow_env_payload(),
        workflow_service_json=json.dumps({"autoDeployTrigger": "checksPass"}),
    )

    assert result.returncode == 1
    assert (
        "drift argus-backtests:autoDeployTrigger "
        f"expected={expected} actual=checksPass" in result.stdout
    )
    assert "autodeploy_status=drift" in result.stdout
    assert "status=drift" in result.stdout


def test_render_env_sync_audit_accepts_manual_deploys_on_all_three(
    tmp_path: Path,
) -> None:
    manual = json.dumps({"autoDeployTrigger": "off"})

    result = _run_render_release_audit(
        tmp_path,
        expect_mode="real-workflow",
        api_env_json=_real_workflow_api_env_payload(),
        web_env_json=_render_env_payload("cuadrao-web"),
        workflow_env_json=_workflow_env_payload(),
        api_service_json=manual,
        web_service_json=manual,
        workflow_service_json=manual,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    for service in ("argus-api", "cuadrao-web", "argus-backtests"):
        assert f"ok {service}:autoDeployTrigger=off" in result.stdout
    assert "autodeploy_status=ready" in result.stdout
    assert "status=ready" in result.stdout


def test_render_env_sync_audit_compares_the_transition_cors_allowlist(
    tmp_path: Path,
) -> None:
    result = _run_render_release_audit(
        tmp_path,
        expect_mode="real-workflow",
        api_env_json=_render_env_payload(
            "cuadrao-api",
            overrides={
                "ARGUS_BACKTEST_JOBS_SHADOW_ENABLED": "true",
                "ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED": "true",
                "ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED": "true",
                "RENDER_API_KEY": "fake-render-token",
                "ARGUS_CORS_ALLOW_ORIGINS": "https://argus-app-suz5.onrender.com",
            },
        ),
        web_env_json=_render_env_payload("cuadrao-web"),
        workflow_env_json=_workflow_env_payload(),
    )

    assert result.returncode == 1
    assert "drift argus-api:ARGUS_CORS_ALLOW_ORIGINS" in result.stdout
    assert "status=drift" in result.stdout


def test_supabase_public_keys_are_supplied_by_the_service_environment() -> None:
    config = yaml.safe_load(_source("render.yaml"))
    keys = {"SUPABASE_ANON_KEY", "NEXT_PUBLIC_SUPABASE_ANON_KEY"}
    entries = [
        entry
        for service in config["services"]
        for entry in service.get("envVars", [])
        if entry["key"] in keys
    ]
    assert entries
    assert all(entry == {"key": entry["key"], "sync": False} for entry in entries)
