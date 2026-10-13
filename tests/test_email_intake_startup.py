"""At startup, email intake says by name which condition kept it from starting
or from carrying a receiving provider, so the logs answer "why 404" without
anyone reading a value."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from argus.api import email_intake as intake
from argus.api import state as api_state
from loguru import logger

FLAGS = {
    "CUADRAO_BUSINESS_EMAIL_CAPTURE_ENABLED": "true",
    "CUADRAO_BUSINESS_PILOT_ENABLED": "true",
    "CUADRAO_INGESTION_ENABLED": "true",
    "CUADRAO_DOCUMENT_EXTRACTION_ENABLED": "true",
    "CUADRAO_BUSINESS_EMAIL_INTAKE_ENABLED": "true",
    "CUADRAO_RESEND_WEBHOOK_SECRET": "whsec_test_only",
    "RESEND_BUSINESS_API_KEY": "re_test_only",
}


@pytest.fixture
def world(monkeypatch):  # noqa: ANN001
    for name, value in FLAGS.items():
        monkeypatch.setenv(name, value)
    for name in ("ARGUS_BUSINESS_EMAIL_CAPTURE_ENABLED", "ARGUS_RESEND_WEBHOOK_SECRET"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(api_state, "PERSISTENCE_MODE", "supabase")
    monkeypatch.setattr(intake, "documents_service", lambda: Mock())
    monkeypatch.setattr(intake, "PostgresEmailStore", lambda pool: Mock())
    monkeypatch.setattr(intake, "grant_route_authority", lambda pool: Mock())
    monkeypatch.setattr(
        intake, "EmailCapture", lambda *args: SimpleNamespace(provider=args[3])
    )
    monkeypatch.setattr(intake.asyncio, "create_task", lambda coro: coro.close())
    records: list = []
    sink = logger.add(lambda message: records.append(message.record), level="INFO")
    app = SimpleNamespace(state=SimpleNamespace(financial_accounts_pool=Mock()))
    yield app, records
    logger.remove(sink)
    intake.configure_email_intake(None)


def _logged(records):  # noqa: ANN001
    return [
        (r["message"], r["extra"].get("missing"))
        for r in records
        if "Email intake" in r["message"]
    ]


def test_everything_present_starts_with_the_provider(world):  # noqa: ANN001
    app, records = world
    intake.start_email_intake(app)
    assert intake.email_intake().provider is not None
    assert _logged(records) == [
        ("Email intake started with the receiving provider", None)
    ]


def test_a_missing_secret_starts_without_a_provider_and_names_it(world, monkeypatch):  # noqa: ANN001
    app, records = world
    monkeypatch.setenv("CUADRAO_RESEND_WEBHOOK_SECRET", "")
    intake.start_email_intake(app)
    assert intake.email_intake().provider is None
    [(message, missing)] = _logged(records)
    assert message.startswith("Email intake started without a receiving provider")
    assert missing == ["webhook_secret_present"]


def test_a_missing_runtime_piece_names_every_missing_condition(world, monkeypatch):  # noqa: ANN001
    app, records = world
    monkeypatch.setattr(intake, "documents_service", lambda: None)
    monkeypatch.setenv("CUADRAO_BUSINESS_PILOT_ENABLED", "True ")  # accepted
    monkeypatch.setenv("CUADRAO_DOCUMENT_EXTRACTION_ENABLED", "enabled")  # not accepted
    intake.start_email_intake(app)
    assert intake.email_intake() is None
    assert _logged(records) == [
        ("Email intake did not start", ["document_extraction_flag", "documents_service"])
    ]


def test_capture_off_stays_silent(world, monkeypatch):  # noqa: ANN001
    app, records = world
    monkeypatch.setenv("CUADRAO_BUSINESS_EMAIL_CAPTURE_ENABLED", "false")
    intake.start_email_intake(app)
    assert intake.email_intake() is None
    assert _logged(records) == []
