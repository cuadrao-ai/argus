"""Offline checks for measurement credential selection and redaction."""

import os

from faker import Faker

from scripts.documents.scoped_measurement import _redact_api_key, require_api_key


def test_measurement_uses_policy_key(monkeypatch):
    secret = Faker().uuid4()
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("CUADRAO_OPENROUTER_API_KEY_DEV", secret)
    require_api_key()
    assert secret not in _redact_api_key(f"provider rejected {secret}")


def test_qa_key_file_uses_policy(monkeypatch, tmp_path):
    from scripts.qa.jose_demo_rehearsal import configure_model_key_file

    secret = Faker().uuid4()
    path = tmp_path / "keys.env"
    path.write_text(f"CUADRAO_OPENROUTER_API_KEY_DEV={secret}\n")
    monkeypatch.setenv("APP_ENV", "test")
    configure_model_key_file(path)
    require_api_key()
    assert _redact_api_key(secret) == ""


def test_qa_key_file_changes_only_model_credentials(monkeypatch, tmp_path):
    from scripts.qa.jose_demo_rehearsal import configure_model_key_file

    secret = Faker().uuid4()
    path = tmp_path / "keys.env"
    path.write_text(
        f"CUADRAO_OPENROUTER_API_KEY_DEV={secret}\n"
        "SYNTHETIC_UNRELATED_SETTING=false\n"
        "APP_ENV=production\n"
    )
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SYNTHETIC_UNRELATED_SETTING", "true")
    configure_model_key_file(path)
    assert os.environ["SYNTHETIC_UNRELATED_SETTING"] == "true"
    assert os.environ["APP_ENV"] == "test"
    assert _redact_api_key(secret) == ""


def test_hermetic_commands_blank_the_local_credential():
    from pathlib import Path

    from argus.llm.openrouter_key_policy import (
        MODEL_CREDENTIAL_ENV_NAMES,
        model_credential_env_name,
    )

    from tests.conftest import PROVIDER_CREDENTIAL_ENV_VARS

    assert set(MODEL_CREDENTIAL_ENV_NAMES) <= set(PROVIDER_CREDENTIAL_ENV_VARS)
    for document in ("AGENTS.md", "scripts/qa/README.md"):
        assert f"{model_credential_env_name('local')}= " in Path(document).read_text()
