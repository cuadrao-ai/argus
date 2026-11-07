from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from argus.llm.openrouter_key_policy import (
    openrouter_traffic_class,
    resolve_openrouter_api_key,
    validate_hosted_openrouter_configuration,
)

NEW_NAMES = tuple(
    f"CUADRAO_OPENROUTER_API_KEY_{suffix}" for suffix in ("DEV", "STG", "PROD")
)
LEGACY_NAMES = (
    "OPENROUTER_API_KEY",
    "CUADRAO_PROD_OPENROUTER_API_KEY",
    "CUADRAO_GUEST_ACCESS_OPENROUTER_API_KEY",
)


@pytest.fixture(autouse=True)
def isolated_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (*NEW_NAMES, *LEGACY_NAMES, "RENDER", "RENDER_SERVICE_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("APP_ENV", "development")


@pytest.mark.parametrize(
    ("environment", "suffix"),
    [
        ("development", "DEV"),
        ("local", "DEV"),
        ("dev", "DEV"),
        ("test", "DEV"),
        ("local-smoke", "DEV"),
        ("", "DEV"),
        ("staging", "STG"),
        ("preview", "STG"),
        ("production", "PROD"),
        (" Production ", "PROD"),
    ],
)
def test_registered_selects_environment_before_legacy(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    suffix: str,
) -> None:
    monkeypatch.setenv("APP_ENV", environment)
    for name in NEW_NAMES:
        monkeypatch.setenv(name, f"synthetic-{name}")
    for name in LEGACY_NAMES:
        monkeypatch.setenv(name, "synthetic-legacy")
    with openrouter_traffic_class("registered"):
        assert (
            resolve_openrouter_api_key()
            == f"synthetic-CUADRAO_OPENROUTER_API_KEY_{suffix}"
        )


@pytest.mark.parametrize(
    "environment", ["development", "staging", "preview", "production"]
)
@pytest.mark.parametrize("blank", ["", "   "])
def test_registered_fallback_is_class_appropriate(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    blank: str,
) -> None:
    monkeypatch.setenv("APP_ENV", environment)
    for name in NEW_NAMES:
        monkeypatch.setenv(name, blank)
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-local")
    monkeypatch.setenv("CUADRAO_PROD_OPENROUTER_API_KEY", "synthetic-hosted")
    expected = "synthetic-local" if environment == "development" else "synthetic-hosted"
    assert resolve_openrouter_api_key("registered") == expected


@pytest.mark.parametrize(
    "environment", ["development", "staging", "preview", "production"]
)
def test_guest_ignores_registered_environment_keys(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
) -> None:
    monkeypatch.setenv("APP_ENV", environment)
    for name in NEW_NAMES:
        monkeypatch.setenv(name, "synthetic-registered")
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-local-guest")
    monkeypatch.setenv(
        "CUADRAO_GUEST_ACCESS_OPENROUTER_API_KEY", "synthetic-hosted-guest"
    )
    expected = (
        "synthetic-local-guest"
        if environment == "development"
        else "synthetic-hosted-guest"
    )
    with openrouter_traffic_class("guest"):
        assert resolve_openrouter_api_key() == expected


@pytest.mark.parametrize(
    ("environment", "suffix"),
    [("staging", "STG"), ("preview", "STG"), ("production", "PROD")],
)
def test_hosted_never_uses_wrong_environment_or_local_fallback(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    suffix: str,
) -> None:
    monkeypatch.setenv("APP_ENV", environment)
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-local")
    for name in NEW_NAMES:
        if not name.endswith(suffix):
            monkeypatch.setenv(name, "synthetic-wrong-environment")
    with pytest.raises(RuntimeError, match=f"CUADRAO_OPENROUTER_API_KEY_{suffix}"):
        resolve_openrouter_api_key("registered")


@pytest.mark.parametrize(
    ("environment", "suffix"),
    [("staging", "STG"), ("preview", "STG"), ("production", "PROD")],
)
def test_startup_rejects_selected_key_shared_with_guest(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    suffix: str,
) -> None:
    monkeypatch.setenv("APP_ENV", environment)
    monkeypatch.setenv(f"CUADRAO_OPENROUTER_API_KEY_{suffix}", "synthetic-shared")
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_OPENROUTER_API_KEY", "synthetic-shared")
    monkeypatch.setenv("CUADRAO_PROD_OPENROUTER_API_KEY", "synthetic-distinct-legacy")
    with pytest.raises(RuntimeError, match="distinct") as error:
        validate_hosted_openrouter_configuration()
    assert "synthetic-shared" not in str(error.value)


@pytest.mark.parametrize("environment", ["staging", "preview", "production"])
def test_new_registered_key_does_not_satisfy_missing_guest(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
) -> None:
    monkeypatch.setenv("APP_ENV", environment)
    for name in NEW_NAMES:
        monkeypatch.setenv(name, "synthetic-registered")
    with pytest.raises(RuntimeError, match="CUADRAO_GUEST_ACCESS_OPENROUTER_API_KEY"):
        validate_hosted_openrouter_configuration()


def test_registered_local_missing_key_fails_clearly() -> None:
    with pytest.raises(RuntimeError, match="CUADRAO_OPENROUTER_API_KEY_DEV"):
        resolve_openrouter_api_key("registered")


def test_unscoped_local_probe_and_guest_stay_optional() -> None:
    assert resolve_openrouter_api_key() == ""
    assert resolve_openrouter_api_key("guest") == ""


def test_unscoped_local_probe_uses_dev_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(NEW_NAMES[0], "  synthetic-dev  ")
    assert resolve_openrouter_api_key() == "synthetic-dev"


def test_unknown_registered_environment_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "prodution")
    monkeypatch.setenv(NEW_NAMES[0], "synthetic-dev")
    with pytest.raises(RuntimeError, match="APP_ENV"):
        resolve_openrouter_api_key("registered")


@pytest.mark.parametrize("marker", ["RENDER", "RENDER_SERVICE_ID"])
def test_hosted_marker_cannot_select_dev(
    monkeypatch: pytest.MonkeyPatch, marker: str
) -> None:
    monkeypatch.setenv(marker, "true")
    monkeypatch.setenv(NEW_NAMES[0], "synthetic-dev")
    with pytest.raises(RuntimeError, match="APP_ENV"):
        resolve_openrouter_api_key("registered")


def test_declarations_are_optional_and_server_only() -> None:
    root = Path(__file__).resolve().parents[1]
    example = (root / ".env.example").read_text()
    for name in NEW_NAMES:
        assert f"{name}=your_registered_key_here" in example
    # Production reads only the _PROD key (openrouter_key_policy.registered).
    read_in_production = "CUADRAO_OPENROUTER_API_KEY_PROD"
    blueprint = yaml.safe_load((root / "render.yaml").read_text())
    for service in blueprint["services"]:
        entries = {entry["key"]: entry for entry in service.get("envVars", [])}
        if service["name"] == "cuadrao-api":
            assert entries[read_in_production] == {"key": read_in_production, "sync": False}
            assert not (set(NEW_NAMES) - {read_in_production}) & entries.keys()
        elif "CUADRAO_PROD_OPENROUTER_API_KEY" in entries:
            for name in NEW_NAMES:
                assert entries[name] == {"key": name, "sync": False}
        else:
            assert not set(NEW_NAMES) & entries.keys()
    manifest = json.loads((root / "scripts/ops/staging_env_manifest.json").read_text())
    entries = {entry["name"]: entry for entry in manifest["services"]["api"]["entries"]}
    for name in NEW_NAMES:
        staging = {
            k: v for k, v in entries[name].items() if k not in {"production", "local"}
        }
        assert entries[name].get("local") == (
            {"enter": "the selected local store", "optional": True}
            if name == "CUADRAO_OPENROUTER_API_KEY_DEV"
            else None
        )
        assert staging == {
            "name": name,
            "kind": "secret",
            "keep_current": True,
            "optional": True,
        }
        production = entries[name]["production"]
        if name == read_in_production:
            assert production["optional"] is True and "enter" in production
        else:
            assert production == {"not_set": True}
    workflow = {
        entry["name"]: entry["production"]
        for entry in manifest["services"]["workflow"]["entries"]
    }
    for name in NEW_NAMES:
        assert workflow[name]["optional"] is True
    for label in ("web", "marketing"):
        names = {entry["name"] for entry in manifest["services"][label]["entries"]}
        assert not set(NEW_NAMES) & names


@pytest.mark.parametrize(
    ("environment", "suffix"),
    [("staging", "STG"), ("preview", "STG"), ("production", "PROD")],
)
def test_startup_accepts_distinct_selected_keys_without_registered_fallback(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    suffix: str,
) -> None:
    monkeypatch.setenv("APP_ENV", environment)
    monkeypatch.setenv(f"CUADRAO_OPENROUTER_API_KEY_{suffix}", "synthetic-registered")
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_OPENROUTER_API_KEY", "synthetic-guest")
    validate_hosted_openrouter_configuration()


def test_explicit_guest_overrides_registered_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(NEW_NAMES[2], "synthetic-registered")
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_OPENROUTER_API_KEY", "synthetic-guest")
    with openrouter_traffic_class("registered"):
        assert resolve_openrouter_api_key("guest") == "synthetic-guest"
    with openrouter_traffic_class("guest"):
        assert resolve_openrouter_api_key("registered") == "synthetic-registered"


def test_provider_free_fixture_blocks_inherited_environment_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.conftest import provider_free_env

    monkeypatch.delenv("ARGUS_RUN_LIVE_EVALS", raising=False)
    for name in NEW_NAMES:
        monkeypatch.setenv(name, "synthetic-inherited-key")
    provider_free_env.__wrapped__(monkeypatch)
    assert resolve_openrouter_api_key() == ""
    for environment in ("staging", "preview", "production"):
        monkeypatch.setenv("APP_ENV", environment)
        with pytest.raises(RuntimeError, match="required"):
            resolve_openrouter_api_key("registered")
