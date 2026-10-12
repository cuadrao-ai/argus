from __future__ import annotations

import pytest
from argus.domain.ingestion.whatsapp.config import load_whatsapp_settings

NAMES = (
    "AGENT_ENABLED",
    "NUMBER_ID",
    "INTAKE_ENABLED",
    "OUTBOUND_ENABLED",
    "VERIFY_TOKEN",
    "APP_SECRET",
    "ACCESS_TOKEN",
    "SENDER_KEY",
    "PHONE_NUMBER_ID",
    "DISPLAY_PHONE_NUMBER",
    "GRAPH_API_VERSION",
)


@pytest.fixture(autouse=True)
def clean(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in NAMES:
        for prefix in ("CUADRAO", "ARGUS"):
            monkeypatch.delenv(f"{prefix}_WHATSAPP_{name}", raising=False)
    for name in ("CUADRAO_APP_ORIGIN", "ARGUS_APP_ORIGIN"):
        monkeypatch.delenv(name, raising=False)


def set_all(monkeypatch: pytest.MonkeyPatch, prefix: str, tag: str) -> None:
    values = {
        "INTAKE_ENABLED": "true",
        "OUTBOUND_ENABLED": "true",
        "VERIFY_TOKEN": f"verify-{tag}",
        "APP_SECRET": f"secret-{tag}",
        "ACCESS_TOKEN": f"token-{tag}",
        "SENDER_KEY": f"key-{tag}",
        "PHONE_NUMBER_ID": f"123{len(tag)}",
        "DISPLAY_PHONE_NUMBER": f"+1 555 {tag}",
        "GRAPH_API_VERSION": "v24.0" if tag == "new" else "v23.0",
    }
    for name, value in values.items():
        monkeypatch.setenv(f"{prefix}_WHATSAPP_{name}", value)


def test_the_cuadrao_names_work_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    set_all(monkeypatch, "CUADRAO", "new")
    monkeypatch.setenv("CUADRAO_APP_ORIGIN", "https://cuadrao.example")
    settings = load_whatsapp_settings()
    assert settings.intake_ready and settings.outbound_enabled
    assert settings.access_token.get_secret_value() == "token-new"
    assert settings.graph_api_version == "v24.0"
    assert settings.app_origin == "https://cuadrao.example"


def test_the_old_argus_names_still_work_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    set_all(monkeypatch, "ARGUS", "old")
    monkeypatch.setenv("ARGUS_APP_ORIGIN", "https://argus.example")
    settings = load_whatsapp_settings()
    assert settings.intake_ready
    assert settings.app_secret.get_secret_value() == "secret-old"
    assert settings.app_origin == "https://argus.example"


def test_the_cuadrao_name_wins_when_both_are_set(monkeypatch: pytest.MonkeyPatch) -> None:
    set_all(monkeypatch, "ARGUS", "old")
    set_all(monkeypatch, "CUADRAO", "new")
    monkeypatch.setenv("ARGUS_APP_ORIGIN", "https://argus.example")
    monkeypatch.setenv("CUADRAO_APP_ORIGIN", "https://cuadrao.example")
    settings = load_whatsapp_settings()
    assert settings.verify_token.get_secret_value() == "verify-new"
    assert settings.sender_key.get_secret_value() == "key-new"
    assert settings.graph_api_version == "v24.0"
    assert settings.app_origin == "https://cuadrao.example"


def test_each_setting_falls_back_on_its_own(monkeypatch: pytest.MonkeyPatch) -> None:
    set_all(monkeypatch, "ARGUS", "old")
    monkeypatch.setenv("CUADRAO_WHATSAPP_ACCESS_TOKEN", "token-new")
    settings = load_whatsapp_settings()
    assert settings.access_token.get_secret_value() == "token-new"
    assert settings.app_secret.get_secret_value() == "secret-old"
    assert settings.intake_ready


def test_nothing_set_keeps_intake_off() -> None:
    settings = load_whatsapp_settings()
    assert not settings.intake_ready and settings.app_origin is None


def test_the_number_id_name_wins_and_each_older_name_still_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARGUS_WHATSAPP_PHONE_NUMBER_ID", "argus-id")
    assert load_whatsapp_settings().phone_number_id == "argus-id"
    monkeypatch.setenv("CUADRAO_WHATSAPP_PHONE_NUMBER_ID", "phone-id")
    assert load_whatsapp_settings().phone_number_id == "phone-id"
    monkeypatch.setenv("CUADRAO_WHATSAPP_NUMBER_ID", "number-id")
    assert load_whatsapp_settings().phone_number_id == "number-id"


def test_the_agent_is_off_by_default_and_reads_both_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert load_whatsapp_settings().agent_enabled is False
    monkeypatch.setenv("ARGUS_WHATSAPP_AGENT_ENABLED", "true")
    assert load_whatsapp_settings().agent_enabled is True
    monkeypatch.setenv("CUADRAO_WHATSAPP_AGENT_ENABLED", "false")
    assert load_whatsapp_settings().agent_enabled is False
