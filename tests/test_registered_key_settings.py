from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml
from argus.llm.openrouter_key_policy import (
    MODEL_CREDENTIAL_ENV_NAMES,
    RETIRED_MODEL_CREDENTIAL_ENV_NAMES,
    model_credential_env_name,
    openrouter_traffic_class,
    resolve_openrouter_api_key,
    validate_hosted_openrouter_configuration,
)
from loguru import logger

import scripts.ops.staging_env as staging_env

ROOT = Path(__file__).resolve().parents[1]
DEV, STG, PROD = MODEL_CREDENTIAL_ENV_NAMES
LOCAL_APP_ENVS = ("development", "local", "dev", "test", "local-smoke", "")
HOSTED = (("staging", STG), ("preview", STG), ("production", PROD))
KEY_NAME = re.compile(r"[A-Z0-9_]*OPENROUTER_API_KEY[A-Z0-9_]*")
DECLARATION_FILES = (
    "render.yaml",
    ".env.example",
    "scripts/ops/staging_env_manifest.json",
    ".github/workflows/ci.yml",
    ".github/private-alpha-release-profile.json",
    "tests/conftest.py",
    "AGENTS.md",
)


@pytest.fixture(autouse=True)
def isolated_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        *MODEL_CREDENTIAL_ENV_NAMES,
        *RETIRED_MODEL_CREDENTIAL_ENV_NAMES,
        "RENDER",
        "RENDER_SERVICE_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("APP_ENV", "development")


def _set_every_name_except(monkeypatch: pytest.MonkeyPatch, own: str) -> None:
    for name in (*MODEL_CREDENTIAL_ENV_NAMES, *RETIRED_MODEL_CREDENTIAL_ENV_NAMES):
        if name != own:
            monkeypatch.setenv(name, f"synthetic-{name}")


def test_owner_accepts_exactly_one_name_per_environment() -> None:
    assert MODEL_CREDENTIAL_ENV_NAMES == (
        "CUADRAO_OPENROUTER_API_KEY_DEV",
        "CUADRAO_OPENROUTER_API_KEY_STG",
        "CUADRAO_OPENROUTER_API_KEY_PROD",
    )
    assert not set(MODEL_CREDENTIAL_ENV_NAMES) & set(RETIRED_MODEL_CREDENTIAL_ENV_NAMES)


@pytest.mark.parametrize(
    ("environment", "name"),
    [*((environment, DEV) for environment in LOCAL_APP_ENVS), *HOSTED, (" Production ", PROD)],
)
def test_each_environment_reads_only_its_own_name(
    monkeypatch: pytest.MonkeyPatch, environment: str, name: str
) -> None:
    monkeypatch.setenv("APP_ENV", environment)
    _set_every_name_except(monkeypatch, name)
    with pytest.raises(RuntimeError, match=name):
        resolve_openrouter_api_key("registered")
    monkeypatch.setenv(name, "  synthetic-own  ")
    with openrouter_traffic_class("registered"):
        assert resolve_openrouter_api_key() == "synthetic-own"


@pytest.mark.parametrize("environment", LOCAL_APP_ENVS)
def test_local_reads_only_the_dev_name(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    monkeypatch.setenv("APP_ENV", environment)
    _set_every_name_except(monkeypatch, DEV)
    assert resolve_openrouter_api_key() == ""
    with pytest.raises(RuntimeError, match=DEV):
        resolve_openrouter_api_key("registered")
    validate_hosted_openrouter_configuration()


@pytest.mark.parametrize(("environment", "name"), HOSTED)
def test_hosted_service_starts_with_only_its_own_key(
    monkeypatch: pytest.MonkeyPatch, environment: str, name: str
) -> None:
    monkeypatch.setenv("APP_ENV", environment)
    monkeypatch.setenv(name, "synthetic-own")
    for other in set(MODEL_CREDENTIAL_ENV_NAMES) - {name}:
        monkeypatch.setenv(other, "  ")
    validate_hosted_openrouter_configuration()


@pytest.mark.parametrize(("environment", "name"), HOSTED)
@pytest.mark.parametrize("old_name", RETIRED_MODEL_CREDENTIAL_ENV_NAMES)
def test_hosted_service_with_only_an_old_name_refuses_to_start(
    monkeypatch: pytest.MonkeyPatch, environment: str, name: str, old_name: str
) -> None:
    monkeypatch.setenv("APP_ENV", environment)
    monkeypatch.setenv(old_name, "synthetic-old")
    with pytest.raises(RuntimeError, match=name) as error:
        validate_hosted_openrouter_configuration()
    assert "synthetic-old" not in str(error.value)


@pytest.mark.parametrize(
    ("environment", "name", "foreign"),
    [
        (environment, name, foreign)
        for environment, name in HOSTED
        for foreign in MODEL_CREDENTIAL_ENV_NAMES
        if foreign != name
    ],
)
def test_hosted_service_holding_another_key_name_refuses_to_start(
    monkeypatch: pytest.MonkeyPatch, environment: str, name: str, foreign: str
) -> None:
    monkeypatch.setenv("APP_ENV", environment)
    monkeypatch.setenv(name, "synthetic-own")
    monkeypatch.setenv(foreign, "synthetic-foreign")
    with pytest.raises(RuntimeError, match=foreign) as error:
        validate_hosted_openrouter_configuration()
    assert "synthetic" not in str(error.value)


@pytest.mark.parametrize(("environment", "name"), HOSTED)
def test_hosted_service_ignores_a_leftover_old_name_and_says_to_delete_it(
    monkeypatch: pytest.MonkeyPatch, environment: str, name: str
) -> None:
    monkeypatch.setenv("APP_ENV", environment)
    monkeypatch.setenv(name, "synthetic-own")
    for old_name in RETIRED_MODEL_CREDENTIAL_ENV_NAMES:
        monkeypatch.setenv(old_name, "synthetic-old")
    warnings: list[str] = []
    sink = logger.add(
        lambda message: warnings.append(message.record["message"]), level="WARNING"
    )
    try:
        validate_hosted_openrouter_configuration()
    finally:
        logger.remove(sink)
    assert warnings == [
        f"retired_model_credential_setting{{name={old_name}}}"
        for old_name in sorted(RETIRED_MODEL_CREDENTIAL_ENV_NAMES)
    ]
    assert not any("synthetic" in line for line in warnings)
    with openrouter_traffic_class("registered"):
        assert resolve_openrouter_api_key() == "synthetic-own"


@pytest.mark.parametrize(("environment", "name"), HOSTED)
def test_hosted_call_needs_a_traffic_class(
    monkeypatch: pytest.MonkeyPatch, environment: str, name: str
) -> None:
    monkeypatch.setenv("APP_ENV", environment)
    monkeypatch.setenv(name, "synthetic-own")
    with pytest.raises(RuntimeError, match="traffic class"):
        resolve_openrouter_api_key()


def test_unknown_environment_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "prodution")
    monkeypatch.setenv(DEV, "synthetic-dev")
    with pytest.raises(RuntimeError, match="APP_ENV"):
        resolve_openrouter_api_key("registered")
    with pytest.raises(RuntimeError, match="APP_ENV"):
        validate_hosted_openrouter_configuration()


@pytest.mark.parametrize("marker", ["RENDER", "RENDER_SERVICE_ID"])
def test_hosted_marker_cannot_select_dev(
    monkeypatch: pytest.MonkeyPatch, marker: str
) -> None:
    monkeypatch.setenv(marker, "true")
    monkeypatch.setenv(DEV, "synthetic-dev")
    with pytest.raises(RuntimeError, match="APP_ENV"):
        resolve_openrouter_api_key("registered")
    with pytest.raises(RuntimeError, match="APP_ENV"):
        validate_hosted_openrouter_configuration()


def _key_names(text: str) -> set[str]:
    return set(KEY_NAME.findall(text))


def test_declarations_name_only_keys_the_owner_accepts() -> None:
    for relative in DECLARATION_FILES:
        unknown = _key_names((ROOT / relative).read_text()) - set(
            MODEL_CREDENTIAL_ENV_NAMES
        )
        assert not unknown, f"{relative} names {sorted(unknown)}"


def test_local_and_ci_declare_only_the_dev_name() -> None:
    example = (ROOT / ".env.example").read_text()
    assert _key_names(example) == {DEV}
    assert f"\n{DEV}=your_openrouter_api_key_here\n" in example
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    declared = {
        name: value
        for job in workflow["jobs"].values()
        for name, value in (job.get("env") or {}).items()
        if KEY_NAME.fullmatch(name)
    }
    assert declared == {DEV: ""}


def _render_key_names() -> dict[str, set[str]]:
    blueprint = yaml.safe_load((ROOT / "render.yaml").read_text())
    expected: dict[str, set[str]] = {}
    for service in blueprint["services"]:
        entries = {entry["key"]: entry for entry in service.get("envVars", [])}
        declared = {name for name in entries if KEY_NAME.fullmatch(name)}
        environment = "staging" if service["name"].endswith("-staging") else "production"
        assert entries.get("APP_ENV", {}).get("value", environment) == environment
        expected[service["name"]] = (
            {model_credential_env_name(environment)} if "APP_ENV" in entries else set()
        )
        assert declared == expected[service["name"]], service["name"]
        for name in declared:
            assert entries[name] == {"key": name, "sync": False}
    return expected


def test_each_render_service_declares_only_its_environment_key() -> None:
    expected = _render_key_names()
    assert expected["cuadrao-api"] == expected["cuadrao-documents-worker"] == {PROD}
    assert (
        expected["cuadrao-api-staging"]
        == expected["cuadrao-documents-worker-staging"]
        == {STG}
    )


def _manifest_key_names(service: dict, environment: str) -> set[str]:
    return {
        entry["name"]
        for entry in staging_env.entries_for(service, environment)
        if KEY_NAME.fullmatch(entry["name"])
        and not entry.get(environment, {}).get("not_set")
    }


def test_settings_manifest_declares_each_key_for_its_environment_only() -> None:
    render_names = _render_key_names()
    manifest = json.loads((ROOT / "scripts/ops/staging_env_manifest.json").read_text())
    staging_env.validate_manifest(manifest)
    staged = staging_env.staging_services(manifest)
    assert "documents_worker" in staged
    for label, service in manifest["services"].items():
        reads_a_key = bool(render_names[service["production"]["service_name"]])
        assert _manifest_key_names(service, "production") == (
            {PROD} if reads_a_key else set()
        ), label
        assert _manifest_key_names(service, "local") == (
            {DEV} if label == "api" else set()
        ), label
        if label in staged:
            assert _manifest_key_names(service, "staging") == (
                {STG} if reads_a_key else set()
            ), label


def test_provider_free_fixture_blocks_inherited_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.conftest import provider_free_env

    monkeypatch.delenv("ARGUS_RUN_LIVE_EVALS", raising=False)
    for name in (*MODEL_CREDENTIAL_ENV_NAMES, *RETIRED_MODEL_CREDENTIAL_ENV_NAMES):
        monkeypatch.setenv(name, "synthetic-inherited-key")
    provider_free_env.__wrapped__(monkeypatch)
    assert resolve_openrouter_api_key() == ""
    for environment, name in HOSTED:
        monkeypatch.setenv("APP_ENV", environment)
        with pytest.raises(RuntimeError, match=name):
            validate_hosted_openrouter_configuration()
