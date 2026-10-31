from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from argus.domain.household.invite_codes import InviteCodeSecretSettings
from argus.domain.recording.money_transfers import TransferSettings
from argus.llm import openrouter, openrouter_model_env


@pytest.mark.parametrize("task", sorted(openrouter_model_env.CANONICAL_TIMEOUT_TASKS))
def test_timeout_reads_the_new_name_without_a_legacy_fallback(task, monkeypatch):
    suffix = f"OPENROUTER_{task.upper()}_TIMEOUT_SECONDS"
    current = f"CUADRAO_{suffix}"
    legacy = f"ARGUS_{suffix}"
    monkeypatch.delenv(current, raising=False)
    monkeypatch.delenv(legacy, raising=False)
    default = openrouter.openrouter_task_timeout_seconds(task)
    monkeypatch.setenv(legacy, "987")
    assert openrouter.openrouter_task_timeout_seconds(task) == default
    monkeypatch.setenv(current, "47")
    assert openrouter.openrouter_task_timeout_seconds(task) == 47


def test_transfer_setting_ignores_the_removed_prefix(monkeypatch):
    suffix = "CROSS_CURRENCY_TRANSFERS_ENABLED"
    monkeypatch.delenv(f"CUADRAO_{suffix}", raising=False)
    monkeypatch.setenv(f"ARGUS_{suffix}", "true")
    assert TransferSettings().cross_currency_transfers_enabled is False
    monkeypatch.setenv(f"CUADRAO_{suffix}", "true")
    assert TransferSettings().cross_currency_transfers_enabled is True


@pytest.mark.parametrize("field", ["secret", "secret_previous"])
def test_invite_secret_ignores_the_removed_prefix(field, monkeypatch, faker):
    suffix = f"INVITE_CODE_{field.upper()}"
    value = faker.password(length=40)
    monkeypatch.delenv(f"CUADRAO_{suffix}", raising=False)
    monkeypatch.setenv(f"ARGUS_{suffix}", value)
    assert getattr(InviteCodeSecretSettings(), field) is None
    monkeypatch.setenv(f"CUADRAO_{suffix}", value)
    assert getattr(InviteCodeSecretSettings(), field).get_secret_value() == value


def test_graveyard_settings_are_grouped_and_not_hosted():
    root = Path(__file__).resolve().parents[1]
    example = (root / ".env.example").read_text()
    header = "# Graveyard: retained local code settings; never declare on hosted services."
    assert example.count(header) == 1
    group = example.split(header)[1]
    names = {line.split("=", 1)[0] for line in group.splitlines() if "=" in line}
    assert names == {
        'ARGUS_TITLE_AUTOGEN_ENABLED',
        'ARGUS_TITLE_AUTOGEN_TIMEOUT_MS',
        'GOOGLE_OAUTH_CLIENT_ID',
        'GOOGLE_OAUTH_CLIENT_SECRET',
        'GOOGLE_OAUTH_REDIRECT_URI',
        'PLAID_CLIENT_ID',
        'PLAID_COUNTRY_CODES',
        'PLAID_CREDENTIALS_INJECTED',
        'PLAID_ENV',
        'PLAID_SECRET',
        'PLAID_WEBHOOK_URL',
    }
    for name in names:
        assert example.count(f"\n{name}=") == 1
    blueprint = yaml.safe_load((root / "render.yaml").read_text())
    for service in blueprint["services"]:
        assert not names.intersection(entry["key"] for entry in service.get("envVars", []))
    for filename in (".github/private-alpha-release-profile.json", "scripts/ops/staging_env_manifest.json"):
        assert not any(name in json.dumps(json.loads((root / filename).read_text())) for name in names)


def test_waitlist_captcha_is_marketing_only_and_not_a_blueprint_declaration():
    root = Path(__file__).resolve().parents[1]
    names = {"CUADRAO_WAITLIST_TURNSTILE_SECRET", "CUADRAO_WAITLIST_TURNSTILE_SITE_KEY"}
    profile = json.loads((root / ".github/private-alpha-release-profile.json").read_text())
    for surface, service in profile["services"].items():
        declared = set(service["env"]) | set(service["required_present"]) | set(service["optional"])
        assert names <= declared if surface == "marketing" else not names.intersection(declared)
    blueprint = (root / "render.yaml").read_text()
    assert not any(name in blueprint for name in names)
