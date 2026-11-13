"""Offline checks for measurement credential selection and redaction."""

import pytest
from faker import Faker

from scripts.documents.scoped_measurement import _redact_api_key, require_api_key


@pytest.mark.parametrize(
    "key_name", ["CUADRAO_OPENROUTER_API_KEY_DEV", "OPENROUTER_API_KEY"]
)
def test_measurement_uses_policy_key(monkeypatch, key_name):
    secret = Faker().uuid4()
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv(key_name, secret)
    require_api_key()
    assert secret not in _redact_api_key(f"provider rejected {secret}")


def test_measurement_prefers_dev_key(monkeypatch):
    fake = Faker()
    selected, legacy = fake.uuid4(), fake.uuid4()
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("CUADRAO_OPENROUTER_API_KEY_DEV", selected)
    monkeypatch.setenv("OPENROUTER_API_KEY", legacy)
    assert _redact_api_key(selected) == ""


def test_qa_key_file_uses_policy(monkeypatch, tmp_path):
    from scripts.qa.jose_demo_rehearsal import configure_model_key_file

    secret = Faker().uuid4()
    path = tmp_path / "keys.env"
    path.write_text(f"CUADRAO_OPENROUTER_API_KEY_DEV={secret}\n")
    monkeypatch.setenv("APP_ENV", "test")
    configure_model_key_file(path)
    require_api_key()
    assert _redact_api_key(secret) == ""


def test_hermetic_commands_blank_every_policy_credential():
    from pathlib import Path

    from argus.llm.openrouter_key_policy import _KeySettings
    from pydantic import SecretStr

    from tests.conftest import PROVIDER_CREDENTIAL_ENV_VARS

    for field in _KeySettings.model_fields.values():
        if field.annotation is not SecretStr:
            continue
        name = field.validation_alias
        assert name in PROVIDER_CREDENTIAL_ENV_VARS
        for document in ("AGENTS.md", "scripts/qa/README.md"):
            assert f"{name}= " in Path(document).read_text()
