from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / ".github" / "private-alpha-release-profile.json"
PROFILE_UTILITY = ROOT / ".github" / "private-alpha-release-profile.py"
MANIFEST_PATH = ROOT / "scripts" / "ops" / "staging_env_manifest.json"
SETTINGS_TOOL = ROOT / "scripts" / "ops" / "staging_env.py"


def _profile_utility(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PROFILE_UTILITY), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _profile_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "private_alpha_release_profile", PROFILE_UTILITY
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _profile() -> dict[str, Any]:
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def _production(label: str) -> dict[str, dict[str, Any]]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {
        entry["name"]: entry["production"]
        for entry in manifest["services"][label]["entries"]
        if not entry.get("local_only")
    }


def _settings_tool(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SETTINGS_TOOL), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_invite_code_surfaces_are_declared_off_by_default() -> None:
    from argus.domain.household.invite_codes import CODE_FLAGS

    production = _production("api")
    for flag in CODE_FLAGS:
        assert production[flag] == {"value": "false"}


def test_release_profile_is_non_secret_and_holds_no_environment() -> None:
    profile = _profile()
    serialized = json.dumps(profile).lower()

    assert set(profile) == {"schema_version", "services", "capabilities", "locales"}
    assert set(profile["services"]) == {"api", "web", "marketing", "documents_worker"}
    assert profile["services"]["api"]["name"] == "cuadrao-api"
    assert profile["services"]["web"]["name"] == "cuadrao-app"
    assert profile["services"]["marketing"]["name"] == "cuadrao-marketing"
    assert profile["services"]["documents_worker"]["name"] == "cuadrao-documents-worker"
    for surface in profile["services"]:
        assert set(profile["services"][surface]) == {"name", "auto_deploy_trigger"}
        assert profile["services"][surface]["auto_deploy_trigger"] == "off"
    assert "staging_only" not in profile
    assert "real_workflow_execution" not in profile["capabilities"]
    assert profile["locales"]["supported"] == ["en", "es-419"]
    assert profile["capabilities"]["omnisearch"] is True

    assert "canary" not in profile

    assert "candidate_sha" not in serialized
    assert "eyjhb" not in serialized
    assert "bearer " not in serialized
    assert "sk-" not in serialized
    assert "CUADRAO_GUEST_ACCESS_ENABLED" not in _production("api")
    assert "NEXT_PUBLIC_GUEST_ACCESS_ENABLED" not in _production("web")


def test_profile_validation_rejects_environment_settings() -> None:
    module = _profile_module()
    profile = _profile()
    profile["services"]["api"]["env"] = {"APP_ENV": "production"}

    with pytest.raises(module.ProfileValidationError, match="staging_env_manifest.json"):
        module.validate_profile(profile)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda profile: profile["services"]["documents_worker"].update(
                auto_deploy_trigger="checksPass"
            ),
            "share one auto_deploy_trigger",
        ),
        (
            lambda profile: profile["services"]["api"].update(
                auto_deploy_trigger="commit"
            ),
            "auto_deploy_trigger must be one of",
        ),
    ],
)
def test_profile_validation_rejects_split_autodeploy(
    mutate: Callable[[dict[str, Any]], None], message: str
) -> None:
    module = _profile_module()
    profile = _profile()
    mutate(profile)

    with pytest.raises(module.ProfileValidationError, match=message):
        module.validate_profile(profile)


def test_profile_lists_each_live_render_service_in_the_blueprint() -> None:
    profile = _profile()
    render_config = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    declared = {service["name"]: service for service in render_config["services"]}

    for service in profile["services"].values():
        assert declared[service["name"]]["branch"] == "main"
        assert declared[service["name"]]["autoDeployTrigger"] == service[
            "auto_deploy_trigger"
        ]
        assert declared[f"{service['name']}-staging"]["autoDeployTrigger"] == "off"
    assert declared["cuadrao-documents-worker"]["type"] == "worker"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda profile: profile["services"].update(
                workflow={"name": "argus-backtests", "auto_deploy_trigger": "off"}
            ),
            "services must define api, web, marketing, and documents_worker",
        ),
        (
            lambda profile: profile["services"]["api"].update(name="argus-api"),
            "services.api.name must be cuadrao-api",
        ),
    ],
)
def test_profile_validation_rejects_retired_service_names(
    mutate: Callable[[dict[str, Any]], None], message: str
) -> None:
    module = _profile_module()
    profile = _profile()
    mutate(profile)

    with pytest.raises(module.ProfileValidationError, match=message):
        module.validate_profile(profile)


@pytest.mark.parametrize(
    ("surface", "retired_name"),
    [
        ("api", "argus-api"),
        ("web", "cuadrao-web-staging"),
        ("marketing", "cuadrao-web"),
        ("documents_worker", "argus-backtests"),
    ],
)
def test_profile_validation_pins_each_surface_to_its_live_service_name(
    surface: str, retired_name: str
) -> None:
    module = _profile_module()
    profile = _profile()
    profile["services"][surface]["name"] = retired_name

    with pytest.raises(module.ProfileValidationError, match=f"services.{surface}.name"):
        module.validate_profile(profile)


def test_profile_validation_lets_the_deploy_decision_change_in_the_profile() -> None:
    module = _profile_module()
    profile = _profile()
    for service in profile["services"].values():
        service["auto_deploy_trigger"] = "checksPass"

    module.validate_profile(profile)


def test_production_account_access_is_invite_only_in_every_release_contract() -> None:
    # Closed, permanent_account_access_allowed admits only active allowlist rows.
    render_config = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    render_api = next(
        service
        for service in render_config["services"]
        if service["name"] == "cuadrao-api"
    )
    render_api_env = {
        item["key"]: item.get("value") for item in render_api["envVars"]
    }
    env_contract = subprocess.run(
        [
            "bash",
            "-euc",
            'source .github/argus-env.sh; printf "%s\\n" "${ARGUS_RENDER_API_ENV[@]}"',
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()

    assert render_api_env["CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED"] == "false"
    assert _production("api")["CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED"] == {
        "value": "false"
    }
    assert "CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED" in env_contract


def test_guest_and_public_account_access_are_open_in_env_templates() -> None:
    """Env templates only. Prose claims are owned by the doc-sync suite.

    The former name promised documentation coverage it never had, which is how
    the docs drifted unnoticed while this stayed green.
    """
    backend_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    web_example = (ROOT / "web" / ".env.local.example").read_text(encoding="utf-8")

    assert "CUADRAO_GUEST_ACCESS_ENABLED=true" in backend_example
    assert "CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED=true" in backend_example
    assert "NEXT_PUBLIC_GUEST_ACCESS_ENABLED=true" in backend_example
    assert "CUADRAO_VISITOR_KEY_SECRET=replace_with_a_unique_random_secret" in (
        backend_example
    )
    assert "ARGUS_DISCOVERY_GLOBAL_DAILY_CEILING=500" in backend_example
    assert "NEXT_PUBLIC_GUEST_ACCESS_ENABLED=true" in web_example


def test_profile_utility_validates_and_hashes_the_profile_with_the_manifest() -> None:
    validate = _profile_utility("validate")
    assert validate.returncode == 0, validate.stderr
    assert validate.stdout.strip() == "profile_status=ready"

    profile_hash = _profile_utility("hash")
    assert profile_hash.returncode == 0, profile_hash.stderr
    assert profile_hash.stdout.strip() == hashlib.sha256(
        PROFILE_PATH.read_bytes() + MANIFEST_PATH.read_bytes()
    ).hexdigest()

    for retired in ("env-pairs", "env-value", "required-present", "allowed-keys"):
        assert _profile_utility(retired, "api").returncode != 0

    worker_autodeploy = _profile_utility("auto-deploy-trigger", "documents_worker")
    assert worker_autodeploy.returncode == 0, worker_autodeploy.stderr
    assert worker_autodeploy.stdout.strip() == "off"
    assert _profile_utility("auto-deploy-trigger", "workflow").returncode != 0


def test_settings_tool_emits_the_production_pairs_the_audit_reads() -> None:
    api_pairs = _settings_tool("print", "production", "api")
    assert api_pairs.returncode == 0, api_pairs.stderr
    assert "CUADRAO_PERSISTENCE_MODE=supabase" in api_pairs.stdout.splitlines()
    assert "ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED" not in api_pairs.stdout

    worker_pairs = _settings_tool("print", "production", "documents_worker")
    assert worker_pairs.returncode == 0, worker_pairs.stderr
    assert worker_pairs.stdout.splitlines() == [
        "CUADRAO_DOCUMENT_JOBS_DRAIN_SECONDS=210",
        "CUADRAO_DOCUMENT_JOBS_MAX_READS=3",
    ]
    assert _settings_tool("print", "production", "workflow").returncode != 0

    allowed = _settings_tool("names", "production", "web", "allowed")
    assert allowed.returncode == 0, allowed.stderr
    assert "NEXT_PUBLIC_POSTHOG_KEY" not in allowed.stdout.splitlines()
    assert "NEXT_PUBLIC_CUADRAO_API_URL" in allowed.stdout.splitlines()


def test_render_blueprint_production_api_matches_the_manifest() -> None:
    profile = _profile()
    render_blueprint = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    services = {service["name"]: service for service in render_blueprint["services"]}

    marketing = services["cuadrao-marketing"]
    assert marketing["rootDir"] == "marketing"
    assert "envVars" not in marketing
    assert marketing["autoDeployTrigger"] == profile["services"]["marketing"][
        "auto_deploy_trigger"
    ]
    api = services["cuadrao-api"]
    assert api["autoDeployTrigger"] == profile["services"]["api"]["auto_deploy_trigger"]
    expected = {
        name: {"key": name, "value": rule["value"]}
        if "value" in rule
        else {"key": name, "sync": False}
        for name, rule in _production("api").items()
        if "not_set" not in rule
    }
    assert {
        item["key"]: {**item, "value": str(item["value"])} if "value" in item else item
        for item in api["envVars"]
    } == expected


def test_render_blueprint_production_worker_matches_the_manifest() -> None:
    render_blueprint = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    services = {service["name"]: service for service in render_blueprint["services"]}
    expected = {
        name: {"key": name, "value": rule["value"]}
        for name, rule in _production("documents_worker").items()
    }

    for name in ("cuadrao-documents-worker", "cuadrao-documents-worker-staging"):
        worker = services[name]
        assert worker["startCommand"] == "poetry run python -m workflows.document_worker"
        assert {item["key"]: item for item in worker["envVars"]} == expected
    for name in ("cuadrao-api", "cuadrao-api-staging"):
        keys = {item["key"] for item in services[name]["envVars"]}
        assert not {key for key in keys if key.startswith("CUADRAO_DOCUMENT_JOBS_")}
