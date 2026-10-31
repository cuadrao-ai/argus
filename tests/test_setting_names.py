"""Cuadrao setting names win; the Argus names still work alone."""

from __future__ import annotations

import base64

import pytest
from argus.api.financial_accounts import financial_accounts_enabled
from argus.api.ingestion import ingestion_enabled
from argus.domain.business.config import (
    business_bank_matching_enabled,
    business_chat_enabled,
    business_pilot_enabled,
)
from argus.domain.ingestion.documents.config import (
    load_document_extraction_settings,
    load_document_job_settings,
)
from argus.domain.ingestion.email_intake.config import EmailIntakeSettings
from argus.domain.ingestion.secrets import SecretBox, SecretBoxUnavailable
from argus.llm.openrouter_model_env import TIER_PRIMARY_ENV
from argus.settings_names import setting_aliases, setting_names, setting_value

NAMES = (
    "BUSINESS_BANK_MATCHING_ENABLED",
    "BUSINESS_PILOT_ENABLED",
    "BUSINESS_CHAT_ENABLED",
    "INGESTION_ENABLED",
    "INGESTION_SECRET_KEY",
    "DOCUMENT_EXTRACTION_ENABLED",
    "DOCUMENT_EXTRACTION_MAX_BYTES",
    "DOCUMENT_EXTRACTION_MAX_PAGES",
    "DOCUMENT_JOBS_ENABLED",
    "DOCUMENT_JOBS_WORKFLOW_TASK",
    "DOCUMENT_JOBS_SWEEP_SECONDS",
    "VISION_MODEL",
    "FINANCIAL_ACCOUNTS_ENABLED",
    "BUSINESS_EMAIL_CAPTURE_ENABLED",
    "BUSINESS_EMAIL_INTAKE_ENABLED",
    "BUSINESS_EMAIL_PENDING_SENDERS_ENABLED",
    "BUSINESS_EMAIL_DOMAIN",
    "RESEND_WEBHOOK_SECRET",
    "APP_ORIGIN",
)


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in NAMES:
        for candidate in setting_names(name):
            monkeypatch.delenv(candidate, raising=False)


def test_the_shared_reader_prefers_the_cuadrao_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert setting_names("APP_ORIGIN") == ("CUADRAO_APP_ORIGIN", "ARGUS_APP_ORIGIN")
    assert setting_value("APP_ORIGIN") is None
    assert setting_value("APP_ORIGIN", "fallback") == "fallback"
    monkeypatch.setenv("ARGUS_APP_ORIGIN", "https://argus.test")
    assert setting_value("APP_ORIGIN") == "https://argus.test"
    monkeypatch.setenv("CUADRAO_APP_ORIGIN", "https://cuadrao.test")
    assert setting_value("APP_ORIGIN") == "https://cuadrao.test"
    assert list(setting_aliases("APP_ORIGIN").choices) == [
        "CUADRAO_APP_ORIGIN",
        "ARGUS_APP_ORIGIN",
    ]
    assert TIER_PRIMARY_ENV["vision"] == ("CUADRAO_VISION_MODEL", "ARGUS_VISION_MODEL")


@pytest.mark.parametrize(
    ("name", "read"),
    [
        ("INGESTION_ENABLED", ingestion_enabled),
        ("FINANCIAL_ACCOUNTS_ENABLED", financial_accounts_enabled),
        ("BUSINESS_PILOT_ENABLED", business_pilot_enabled),
        (
            "DOCUMENT_EXTRACTION_ENABLED",
            lambda: load_document_extraction_settings().enabled,
        ),
        ("DOCUMENT_JOBS_ENABLED", lambda: load_document_job_settings().enabled),
        ("BUSINESS_EMAIL_CAPTURE_ENABLED", lambda: EmailIntakeSettings().capture_enabled),
        (
            "BUSINESS_EMAIL_INTAKE_ENABLED",
            lambda: EmailIntakeSettings().receiving_enabled,
        ),
        (
            "BUSINESS_EMAIL_PENDING_SENDERS_ENABLED",
            lambda: EmailIntakeSettings().pending_senders_enabled,
        ),
    ],
)
def test_each_flag_reads_both_names_and_the_cuadrao_name_wins(
    name: str, read, monkeypatch: pytest.MonkeyPatch
) -> None:  # noqa: ANN001
    assert read() is False
    monkeypatch.setenv(f"ARGUS_{name}", "true")
    assert read() is True
    monkeypatch.setenv(f"CUADRAO_{name}", "false")
    assert read() is False
    monkeypatch.setenv(f"CUADRAO_{name}", "true")
    monkeypatch.setenv(f"ARGUS_{name}", "false")
    assert read() is True


def test_business_bank_matching_stays_inside_the_pilot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CUADRAO_BUSINESS_BANK_MATCHING_ENABLED", "true")
    assert business_bank_matching_enabled() is False
    monkeypatch.setenv("ARGUS_BUSINESS_PILOT_ENABLED", "true")
    assert business_bank_matching_enabled() is True


def test_business_chat_stays_inside_the_pilot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUADRAO_BUSINESS_CHAT_ENABLED", "true")
    assert business_chat_enabled() is False
    monkeypatch.setenv("ARGUS_BUSINESS_PILOT_ENABLED", "true")
    assert business_chat_enabled() is True


def test_valued_settings_follow_the_same_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARGUS_DOCUMENT_EXTRACTION_MAX_PAGES", "5")
    monkeypatch.setenv("ARGUS_DOCUMENT_JOBS_WORKFLOW_TASK", "argus-task")
    monkeypatch.setenv("ARGUS_BUSINESS_EMAIL_DOMAIN", "recibos.argus.test")
    monkeypatch.setenv("ARGUS_RESEND_WEBHOOK_SECRET", "whsec_argus")
    assert load_document_extraction_settings().max_pages == 5
    assert load_document_job_settings().workflow_task == "argus-task"
    intake = EmailIntakeSettings()
    assert (intake.receiving_domain, intake.webhook_secret.get_secret_value()) == (
        "recibos.argus.test",
        "whsec_argus",
    )
    monkeypatch.setenv("CUADRAO_DOCUMENT_EXTRACTION_MAX_PAGES", "3")
    monkeypatch.setenv("CUADRAO_DOCUMENT_JOBS_WORKFLOW_TASK", "cuadrao-task")
    monkeypatch.setenv("CUADRAO_BUSINESS_EMAIL_DOMAIN", "recibos.cuadrao.test")
    monkeypatch.setenv("CUADRAO_RESEND_WEBHOOK_SECRET", "whsec_cuadrao")
    assert load_document_extraction_settings().max_pages == 3
    assert load_document_job_settings().workflow_task == "cuadrao-task"
    intake = EmailIntakeSettings()
    assert (intake.receiving_domain, intake.webhook_secret.get_secret_value()) == (
        "recibos.cuadrao.test",
        "whsec_cuadrao",
    )


def test_the_secret_box_key_reads_both_names(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SecretBoxUnavailable):
        SecretBox.from_env()
    monkeypatch.setenv("ARGUS_INGESTION_SECRET_KEY", base64.b64encode(b"a" * 32).decode())
    argus_key = SecretBox.from_env().key_id
    monkeypatch.setenv(
        "CUADRAO_INGESTION_SECRET_KEY", base64.b64encode(b"c" * 32).decode()
    )
    cuadrao_key = SecretBox.from_env().key_id
    assert argus_key != cuadrao_key
    monkeypatch.delenv("ARGUS_INGESTION_SECRET_KEY")
    assert SecretBox.from_env().key_id == cuadrao_key
