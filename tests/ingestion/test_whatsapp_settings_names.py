from __future__ import annotations

import pytest
from argus.domain.ingestion.whatsapp.config import load_whatsapp_settings
from pydantic import SecretStr

# Field, canonical suffix, synthetic environment value, parsed value, default.
SETTINGS = (
    ("intake_enabled", "INTAKE_ENABLED", "true", True, False),
    ("agent_enabled", "AGENT_ENABLED", "true", True, False),
    ("outbound_enabled", "OUTBOUND_ENABLED", "true", True, False),
    ("verify_token", "VERIFY_TOKEN", "synthetic-verify", "synthetic-verify", None),
    ("app_secret", "APP_SECRET", "synthetic-app", "synthetic-app", None),
    ("access_token", "ACCESS_TOKEN", "synthetic-access", "synthetic-access", None),
    ("sender_key", "SENDER_KEY", "synthetic-sender", "synthetic-sender", None),
    ("phone_number_id", "NUMBER_ID", "100000000000001", "100000000000001", None),
    (
        "display_phone_number",
        "DISPLAY_PHONE_NUMBER",
        "+1 555 010 0001",
        "+1 555 010 0001",
        None,
    ),
    ("graph_api_version", "GRAPH_API_VERSION", "v24.0", "v24.0", "v23.0"),
    ("reply_group_wait_seconds", "REPLY_GROUP_WAIT_SECONDS", "180", 180, 120),
    ("reply_daily_limit", "REPLY_DAILY_LIMIT", "15", 15, 10),
)


def env_name(prefix: str, suffix: str) -> str:
    return f"{prefix}_WHATSAPP_{suffix}"


@pytest.fixture(autouse=True)
def clean(monkeypatch: pytest.MonkeyPatch) -> None:
    for suffix in [row[1] for row in SETTINGS] + ["PHONE_NUMBER_ID"]:
        for prefix in ("CUADRAO", "ARGUS"):
            monkeypatch.delenv(env_name(prefix, suffix), raising=False)
    for name in ("CUADRAO_APP_ORIGIN", "ARGUS_APP_ORIGIN"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("field,suffix,value,expected,default", SETTINGS)
def test_each_cuadrao_name_works_alone(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    suffix: str,
    value: str,
    expected: object,
    default: object,
) -> None:
    monkeypatch.setenv(env_name("CUADRAO", suffix), value)
    actual = getattr(load_whatsapp_settings(), field)
    if isinstance(actual, SecretStr):
        actual = actual.get_secret_value()
    assert actual == expected


@pytest.mark.parametrize("field,suffix,value,expected,default", SETTINGS)
def test_the_old_argus_names_are_ignored_alone(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    suffix: str,
    value: str,
    expected: object,
    default: object,
) -> None:
    monkeypatch.setenv(env_name("ARGUS", suffix), value)
    settings = load_whatsapp_settings()
    assert not settings.intake_ready
    assert getattr(settings, field) == default


@pytest.mark.parametrize("prefix", ["ARGUS", "CUADRAO"])
def test_old_phone_number_alias_is_ignored(
    monkeypatch: pytest.MonkeyPatch, prefix: str
) -> None:
    monkeypatch.setenv(env_name(prefix, "PHONE_NUMBER_ID"), "100000000000002")
    settings = load_whatsapp_settings()
    assert settings.phone_number_id is None
    assert not settings.intake_ready


def test_the_cuadrao_names_work_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    for _, suffix, value, _, _ in SETTINGS:
        monkeypatch.setenv(env_name("CUADRAO", suffix), value)
    settings = load_whatsapp_settings()
    assert settings.intake_ready and settings.replies_ready


def test_old_credentials_cannot_complete_canonical_intake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for _, suffix, value, _, _ in SETTINGS:
        monkeypatch.setenv(env_name("ARGUS", suffix), value)
    monkeypatch.setenv(env_name("ARGUS", "PHONE_NUMBER_ID"), "100000000000002")
    monkeypatch.setenv("CUADRAO_WHATSAPP_INTAKE_ENABLED", "true")
    settings = load_whatsapp_settings()
    assert not settings.intake_ready
    assert not settings.replies_ready
    assert settings.verify_token is None
    assert settings.phone_number_id is None


def test_nothing_set_keeps_intake_off() -> None:
    settings = load_whatsapp_settings()
    assert not settings.intake_ready and settings.app_origin is None


def test_app_origin_keeps_its_existing_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARGUS_APP_ORIGIN", "https://legacy.example")
    assert load_whatsapp_settings().app_origin == "https://legacy.example"
    monkeypatch.setenv("CUADRAO_APP_ORIGIN", "https://cuadrao.example")
    assert load_whatsapp_settings().app_origin == "https://cuadrao.example"
