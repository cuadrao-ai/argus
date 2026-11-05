"""A webhook secret or API key pasted with a stray newline or spaces is the
credential; one made only of whitespace is absent. Without trimming, a
trailing newline made every Resend signature fail (401), never a 404."""

from __future__ import annotations

from argus.domain.ingestion.email_intake.config import EmailIntakeSettings
from fastapi.testclient import TestClient

from tests.business.test_business_email_api import (  # noqa: F401
    SECRET,
    WEBHOOK,
    event,
    runtime,
    signed,
)


def test_a_pasted_newline_or_spaces_are_not_part_of_the_credential(monkeypatch):  # noqa: ANN001
    monkeypatch.setenv("CUADRAO_RESEND_WEBHOOK_SECRET", "whsec_abc\n")
    monkeypatch.setenv("RESEND_BUSINESS_API_KEY", "  re_abc \n")
    settings = EmailIntakeSettings()
    assert settings.webhook_secret.get_secret_value() == "whsec_abc"
    assert settings.api_key.get_secret_value() == "re_abc"
    monkeypatch.setenv("CUADRAO_RESEND_WEBHOOK_SECRET", "   ")
    monkeypatch.setenv("RESEND_BUSINESS_API_KEY", "\n")
    blank = EmailIntakeSettings()
    assert (
        blank.webhook_secret.get_secret_value(),
        blank.api_key.get_secret_value(),
    ) == ("", "")


def test_a_secret_pasted_with_a_trailing_newline_still_verifies_the_webhook(
    client: TestClient,  # noqa: F811
    runtime,  # noqa: ANN001, F811
    monkeypatch,  # noqa: ANN001
) -> None:
    monkeypatch.setenv("ARGUS_RESEND_WEBHOOK_SECRET", SECRET + "\n")
    body = event()
    response = client.post(WEBHOOK, content=body, headers=signed(body))
    assert response.status_code == 202, response.text
