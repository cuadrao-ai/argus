from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from tests.test_environment_scripts import (
    _contract_array,
    _render_env,
    _render_env_payload,
    _run_render_release_audit,
)
from tests.test_staging_default_off_flags import APPROVED_STAGING_OVERRIDES

ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


BLUEPRINT_DECLARES_STAGING_OVERRIDE = {
    "CUADRAO_BUSINESS_ACTIVITY_ENABLED",
    "CUADRAO_BUSINESS_BANK_MATCHING_ENABLED",
    "CUADRAO_BUSINESS_EMAIL_CAPTURE_ENABLED",
    "CUADRAO_BUSINESS_EMAIL_INTAKE_ENABLED",
    "CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED",
    "CUADRAO_WHATSAPP_INTAKE_ENABLED",
    "CUADRAO_WHATSAPP_OUTBOUND_ENABLED",
}


def _blueprint_env_item(entry: dict) -> dict:
    item = {"key": entry["name"]}
    if "value" not in entry:
        item["sync"] = False
        return item
    value = entry["value"]
    if (
        entry["name"] in APPROVED_STAGING_OVERRIDES
        and entry["name"] not in BLUEPRINT_DECLARES_STAGING_OVERRIDE
    ):
        value = "false"
    item["value"] = value
    return item


def test_render_config_audit_reads_settings_from_the_manifest() -> None:
    source = _source(".github/render-env-sync.sh")
    contract = _source(".github/argus-env.sh")

    assert "private-alpha-release-profile.py" in source
    assert 'print production "$surface"' in source
    assert 'names production "$surface" required' in source
    assert 'ARGUS_SETTINGS_TOOL="${BASH_SOURCE[0]%/*}/../scripts/ops/staging_env.py"' in (
        contract
    )
    assert "private-alpha-release-profile.py" not in contract
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
    assert "cron-deploy-status" not in env_sync
    assert (ROOT / "scripts" / "ops" / "scheduled_maintenance.py").is_file()


def test_release_docs_name_the_live_services_without_a_cron_surface() -> None:
    runbook = _source("docs/PRIVATE_LAUNCH_RUNBOOK.md")
    data_model = _source("docs/DATA_MODEL.md")
    release_contract = _source("docs/specs/private-alpha-ci-cd-sota.md")
    manifest = _source("docs/release-manifests/TEMPLATE.md")
    profile = json.loads(_source(".github/private-alpha-release-profile.json"))

    for service in profile["services"].values():
        assert f"`{service['name']}`" in runbook
    for retired in ("`argus-api`", "`argus-app`", "`argus-backtests`", "`cuadrao-web`"):
        assert retired not in runbook
    assert "cuadrao-dgii-rnc-staging" not in runbook
    for source in (runbook, data_model, release_contract, manifest):
        assert "argus-maintenance" not in source
        assert "cron-deploy-status" not in source
    assert "scripts/ops/scheduled_maintenance.py" in runbook
    assert "operator-run" in runbook


def test_release_contract_keeps_every_service_on_manual_deploys() -> None:
    profile = json.loads(_source(".github/private-alpha-release-profile.json"))
    render_config = yaml.safe_load(_source("render.yaml"))
    render_by_name = {service["name"]: service for service in render_config["services"]}
    runbook = _source("docs/PRIVATE_LAUNCH_RUNBOOK.md")

    # Founder decision, 2026-09-13 (#614): a Blueprint sync must not enable
    # autodeploy, so render.yaml carries the quoted string rather than YAML false.
    for service in profile["services"].values():
        assert service["auto_deploy_trigger"] == "off"
        assert render_by_name[service["name"]]["autoDeployTrigger"] == "off"
    assert all(
        service["autoDeployTrigger"] == "off" for service in render_by_name.values()
    )
    assert "argus-backtests" not in render_by_name
    assert "`autoDeployTrigger: off`" in runbook


def test_blueprint_matches_the_live_dashboard_service_shape() -> None:
    render_config = yaml.safe_load(_source("render.yaml"))
    services = {service["name"]: service for service in render_config["services"]}
    web = services["cuadrao-marketing"]
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
        "off",
        "poetry install",
    )
    manifest = json.loads(_source("scripts/ops/staging_env_manifest.json"))
    declared = {item["key"]: item for item in stage_api["envVars"]}
    assert declared == {
        entry["name"]: _blueprint_env_item(entry)
        for entry in manifest["services"]["api"]["entries"]
        if not entry.get("production_only") and not entry.get("local_only")
    }
    assert services["cuadrao-marketing-staging"]["branch"] == "main"
    assert "NEXT_PUBLIC_CUADRAO_API_URL" in _contract_array("ARGUS_RENDER_WEB_ENV")
    assert "NEXT_PUBLIC_CUADRAO_API_URL" in _render_env("cuadrao-app")


def test_argus_api_disables_the_default_render_subdomain() -> None:
    render_config = yaml.safe_load(_source("render.yaml"))
    render_by_name = {service["name"]: service for service in render_config["services"]}
    runbook = _source("docs/PRIVATE_LAUNCH_RUNBOOK.md")
    waitlist_floor = runbook.split("### Waitlist rollback floor", 1)[1]

    assert render_by_name["cuadrao-api"]["renderSubdomainPolicy"] == "disabled"
    assert "renderSubdomainPolicy" not in render_by_name["cuadrao-marketing"]
    assert render_by_name["cuadrao-api-staging"]["renderSubdomainPolicy"] == "enabled"
    assert "https://argus-ohr5.onrender.com" in waitlist_floor
    assert "HTTP `404`" in waitlist_floor
    assert "Cloudflare Worker" in waitlist_floor
    assert "CF-Connecting-IP" in waitlist_floor
    assert "#674" in waitlist_floor
    assert "release-config-audit` does not read this setting" in waitlist_floor
    assert "serviceDetails.renderSubdomainPolicy=disabled" in waitlist_floor
    assert "#694" in waitlist_floor


@pytest.mark.parametrize(
    ("surface", "argument"),
    [
        ("api", "api_service_json"),
        ("marketing", "web_service_json"),
        ("web", "app_service_json"),
        ("documents_worker", "worker_service_json"),
    ],
)
def test_render_env_sync_audit_reports_a_service_that_leaves_manual_deploys(
    tmp_path: Path, surface: str, argument: str
) -> None:
    profile = json.loads(_source(".github/private-alpha-release-profile.json"))
    service = profile["services"][surface]

    result = _run_render_release_audit(
        tmp_path,
        api_env_json=_render_env_payload("cuadrao-api"),
        web_env_json=_render_env_payload("cuadrao-marketing"),
        **{argument: json.dumps({"autoDeployTrigger": "checksPass"})},
    )

    assert result.returncode == 1
    assert (
        f"drift {service['name']}:autoDeployTrigger "
        f"expected={service['auto_deploy_trigger']} actual=checksPass" in result.stdout
    )
    assert "autodeploy_status=drift" in result.stdout
    assert "status=drift" in result.stdout


def test_render_env_sync_audit_accepts_manual_deploys_on_the_audited_services(
    tmp_path: Path,
) -> None:
    manual = json.dumps({"autoDeployTrigger": "off"})

    result = _run_render_release_audit(
        tmp_path,
        api_env_json=_render_env_payload("cuadrao-api"),
        web_env_json=_render_env_payload("cuadrao-marketing"),
        api_service_json=manual,
        web_service_json=manual,
        app_service_json=manual,
        worker_service_json=manual,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    for service in (
        "cuadrao-api",
        "cuadrao-marketing",
        "cuadrao-app",
        "cuadrao-documents-worker",
    ):
        assert f"ok {service}:autoDeployTrigger=off" in result.stdout
    assert "autodeploy_status=ready" in result.stdout
    assert "status=ready" in result.stdout


def test_render_env_sync_audit_flags_open_public_account_access(
    tmp_path: Path,
) -> None:
    result = _run_render_release_audit(
        tmp_path,
        api_env_json=_render_env_payload(
            "cuadrao-api",
            overrides={"CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED": "true"},
        ),
        web_env_json=_render_env_payload("cuadrao-marketing"),
    )

    assert result.returncode == 1
    assert (
        "drift cuadrao-api:CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED expected=false actual=true"
        in result.stdout
    )
    assert "status=drift" in result.stdout


def test_render_env_sync_audit_flags_a_live_name_production_must_not_set(
    tmp_path: Path,
) -> None:
    result = _run_render_release_audit(
        tmp_path,
        api_env_json=_render_env_payload(
            "cuadrao-api", extra={"CUADRAO_INGESTION_SECRET_KEY": "fake-key"}
        ),
        web_env_json=_render_env_payload("cuadrao-marketing"),
    )

    assert result.returncode == 1
    assert (
        "forbidden cuadrao-api:CUADRAO_INGESTION_SECRET_KEY unexpected_live_env"
        in result.stdout
    )
    assert "fake-key" not in result.stdout


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
