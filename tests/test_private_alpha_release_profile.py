from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / ".github" / "private-alpha-release-profile.json"
PROFILE_UTILITY = ROOT / ".github" / "private-alpha-release-profile.py"
# Founder decision, 2026-09-13 (#614): the canary checks exactly these, in order.
FOUNDER_CANARY_CHECKS = [
    "services_same_commit",
    "signed_in_chat_answer",
    "backtest_completes",
    "research_answer_with_sources",
]


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


def test_invite_code_surfaces_are_declared_off_by_default() -> None:
    from argus.domain.household.invite_codes import CODE_FLAGS

    env = _profile()["services"]["api"]["env"]
    for flag in CODE_FLAGS:
        assert env[flag] == "false"


def test_release_profile_is_non_secret_and_defines_the_fixed_canary() -> None:
    profile = _profile()
    serialized = json.dumps(profile).lower()

    assert profile["release_mode"] == "real-workflow"
    assert set(profile["services"]) == {"api", "web", "workflow"}
    assert profile["services"]["api"]["name"] == "argus-api"
    assert profile["services"]["web"]["name"] == "argus-app"
    assert profile["services"]["workflow"]["name"] == "argus-backtests"
    # Founder decision, 2026-09-13 (#614): deploys are manual on all three.
    for surface in ("api", "web", "workflow"):
        assert profile["services"][surface]["auto_deploy_trigger"] == "off"
    assert profile["services"]["api"]["env"]["ARGUS_APP_ORIGIN"] == (
        "https://arguschat.ai"
    )
    assert profile["services"]["api"]["env"]["ARGUS_CORS_ALLOW_ORIGINS"] == (
        "https://argus-app-suz5.onrender.com,https://arguschat.ai,"
        "https://www.arguschat.ai"
    )
    assert "ARGUS_CORS_ALLOW_ORIGINS" not in profile["services"]["api"][
        "required_present"
    ]
    assert profile["services"]["web"]["env"]["ARGUS_APP_ORIGIN"] == (
        "https://arguschat.ai"
    )
    assert profile["workflow"]["real_task"] == "argus-backtests/run_backtest_job"
    assert profile["locales"]["supported"] == ["en", "es-419"]
    assert profile["locales"]["required_static_keys"] == [
        "chat.confirmation.actions.run_backtest"
    ]
    assert profile["capabilities"]["omnisearch"] is True

    canary = profile["canary"]
    assert set(canary) == {
        "language",
        "chat_prompt",
        "backtest_prompt",
        "research_prompt",
        "required_steps",
    }
    assert canary["language"] == "es-419"
    assert canary["required_steps"] == FOUNDER_CANARY_CHECKS
    assert canary["required_steps"] == list(_profile_module().CANARY_CHECKS)
    for field in ("chat_prompt", "backtest_prompt", "research_prompt"):
        assert canary[field].strip()
        assert "—" not in canary[field]

    assert "candidate_sha" not in serialized
    assert "eyjhb" not in serialized
    assert "bearer " not in serialized
    assert "sk-" not in serialized
    assert "ARGUS_GUEST_ACCESS_ENABLED" not in profile["services"]["api"]["env"]
    assert (
        profile["services"]["api"]["env"]["ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED"]
        == "true"
    )
    assert "NEXT_PUBLIC_GUEST_ACCESS_ENABLED" not in profile["services"]["web"]["env"]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda profile: profile["services"]["workflow"].update(
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
        (
            lambda profile: profile["canary"]["required_steps"].append(
                "decision_note"
            ),
            "required_steps must be exactly",
        ),
        (
            lambda profile: profile["canary"]["required_steps"].reverse(),
            "required_steps must be exactly",
        ),
        (
            lambda profile: profile["canary"].update(research_prompt=" "),
            "research_prompt must be a non-empty string",
        ),
    ],
)
def test_profile_validation_rejects_split_autodeploy_and_feature_checks(
    mutate: Callable[[dict[str, Any]], None], message: str
) -> None:
    module = _profile_module()
    profile = _profile()
    mutate(profile)

    with pytest.raises(module.ProfileValidationError, match=message):
        module.validate_profile(profile)


def test_profile_validation_lets_the_deploy_decision_change_in_the_profile() -> None:
    module = _profile_module()
    profile = _profile()
    for service in profile["services"].values():
        service["auto_deploy_trigger"] = "checksPass"

    module.validate_profile(profile)


def test_public_account_access_is_open_in_every_release_contract() -> None:
    profile = _profile()
    render_config = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    render_api = next(
        service
        for service in render_config["services"]
        if service["name"] == "argus-api"
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
    backend_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert render_api_env["ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED"] == "true"
    assert (
        profile["services"]["api"]["env"]["ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED"]
        == "true"
    )
    assert "ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED" in env_contract
    assert "ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED=true" in backend_example


def test_guest_and_public_account_access_are_open_in_env_templates() -> None:
    """Env templates only. Prose claims are owned by the doc-sync suite.

    The former name promised documentation coverage it never had, which is how
    the docs drifted unnoticed while this stayed green.
    """
    backend_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    web_example = (ROOT / "web" / ".env.local.example").read_text(encoding="utf-8")

    assert "ARGUS_GUEST_ACCESS_ENABLED=true" in backend_example
    assert "ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED=true" in backend_example
    assert "NEXT_PUBLIC_GUEST_ACCESS_ENABLED=true" in backend_example
    assert "ARGUS_VISITOR_KEY_SECRET=replace_with_a_unique_random_secret" in (
        backend_example
    )
    assert "ARGUS_DISCOVERY_GLOBAL_DAILY_CEILING=500" in backend_example
    assert "NEXT_PUBLIC_GUEST_ACCESS_ENABLED=true" in web_example


def test_profile_utility_validates_hashes_and_emits_expected_pairs() -> None:
    validate = _profile_utility("validate")
    assert validate.returncode == 0, validate.stderr
    assert validate.stdout.strip() == "profile_status=ready"

    profile_hash = _profile_utility("hash")
    assert profile_hash.returncode == 0, profile_hash.stderr
    assert re.fullmatch(r"[0-9a-f]{64}", profile_hash.stdout.strip())

    api_pairs = _profile_utility("env-pairs", "api")
    assert api_pairs.returncode == 0, api_pairs.stderr
    assert "ARGUS_PERSISTENCE_MODE=supabase" in api_pairs.stdout
    assert "ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED=true" in api_pairs.stdout

    workflow_pairs = _profile_utility("env-pairs", "workflow")
    assert workflow_pairs.returncode == 0, workflow_pairs.stderr
    assert "ARGUS_MARKET_DATA_PROVIDER_MODE=live_provider" in workflow_pairs.stdout

    workflow_provider_mode = _profile_utility(
        "env-value", "workflow", "ARGUS_MARKET_DATA_PROVIDER_MODE"
    )
    assert workflow_provider_mode.returncode == 0, workflow_provider_mode.stderr
    assert workflow_provider_mode.stdout.strip() == "live_provider"

    allowed_keys = _profile_utility("allowed-keys", "web")
    assert allowed_keys.returncode == 0, allowed_keys.stderr
    assert "NEXT_PUBLIC_POSTHOG_KEY" in allowed_keys.stdout

    workflow_autodeploy = _profile_utility("auto-deploy-trigger", "workflow")
    assert workflow_autodeploy.returncode == 0, workflow_autodeploy.stderr
    assert workflow_autodeploy.stdout.strip() == "off"

    canary_checks = _profile_utility("canary-checks")
    assert canary_checks.returncode == 0, canary_checks.stderr
    assert canary_checks.stdout.splitlines() == FOUNDER_CANARY_CHECKS


def test_profile_utility_resolves_the_canary_static_labels() -> None:
    result = _profile_utility("static-key-values", "es-419")

    assert result.returncode == 0, result.stderr
    values = json.loads(result.stdout)
    assert set(values) == {"chat.confirmation.actions.run_backtest"}
    assert values["chat.confirmation.actions.run_backtest"]


def test_profile_utility_exposes_only_the_canary_check_inputs() -> None:
    for field in ("language", "chat_prompt", "backtest_prompt", "research_prompt"):
        result = _profile_utility("canary-value", field)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip()
    for removed in ("prompt", "decision_state", "decision_note", "search_query"):
        assert _profile_utility("canary-value", removed).returncode != 0


def test_render_blueprint_matches_the_authoritative_nonsecret_profile() -> None:
    profile = _profile()
    render_blueprint = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    render_services = {
        service["name"]: {entry["key"]: entry for entry in service.get("envVars", [])}
        for service in render_blueprint["services"]
    }

    for surface in ("api", "web"):
        service_profile = profile["services"][surface]
        rendered_service = next(
            service
            for service in render_blueprint["services"]
            if service["name"] == service_profile["name"]
        )
        assert rendered_service["autoDeployTrigger"] == service_profile[
            "auto_deploy_trigger"
        ]
        rendered_env = render_services[service_profile["name"]]
        expected_keys = set(service_profile["env"])
        expected_keys.update(service_profile["required_present"])
        expected_keys.update(service_profile["optional"])
        assert set(rendered_env) == expected_keys

        for key, value in service_profile["env"].items():
            assert str(rendered_env[key].get("value")) == value
        for key in service_profile["required_present"]:
            assert rendered_env[key].get("sync") is False or rendered_env[key].get(
                "value"
            )
        for key in service_profile["optional"]:
            assert rendered_env[key].get("sync") is False


def test_api_and_app_share_a_registrable_domain() -> None:
    """The handoff cookie is SameSite=Lax, which only carries first-party.

    Guest conversion broke for every iOS browser on 2026-08-13 because the API
    sat on a different registrable domain and the cookie was third-party. Move
    it off arguschat.ai again and every browser silently stops returning it.
    """

    blueprint = (ROOT / "render.yaml").read_text(encoding="utf-8")
    app_origin = re.search(
        r"key: ARGUS_APP_ORIGIN\s*\n\s*value: (\S+)", blueprint
    )
    api_url = re.search(
        r"key: NEXT_PUBLIC_ARGUS_API_URL\s*\n\s*value: (\S+)", blueprint
    )
    assert app_origin and api_url, "render.yaml must declare both hosts"

    def registrable(url: str) -> str:
        host = urlparse(url).hostname or ""
        return ".".join(host.split(".")[-2:])

    assert registrable(app_origin.group(1)) == registrable(api_url.group(1)), (
        "The API must share a registrable domain with the app, or the guest "
        "handoff cookie becomes third-party and every browser drops it."
    )
