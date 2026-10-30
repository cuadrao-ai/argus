from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from argus.domain.existing_account_email import (
    render_existing_account_email,
    send_existing_account_notice,
)
from faker import Faker

fake = Faker()
ROOT = Path(__file__).resolve().parents[1]
APP_ORIGIN = "https://app.example.test"
ASSET_ORIGIN = "https://assets.example.test"


def _catalog(language: str) -> dict[str, object]:
    path = ROOT / "web" / "public" / "locales" / language / "common.json"
    return json.loads(path.read_text())["account_email"]["existing_account"]


@pytest.mark.parametrize("language", ["es-419", "en"])
def test_render_uses_the_approved_copy_and_the_app_sign_in_link(language: str) -> None:
    copy = _catalog(language)

    message = render_existing_account_email(
        language=language, app_origin=APP_ORIGIN, asset_origin=ASSET_ORIGIN
    )

    assert message["subject"] == copy["subject"]
    for paragraph in copy["paragraphs"]:
        assert paragraph in message["text"]
    assert copy["after_action"] in message["text"]
    assert f"{APP_ORIGIN}/?auth=login" in message["text"]
    assert f'href="{APP_ORIGIN}/?auth=login"' in message["html"]
    assert f"{ASSET_ORIGIN}/email/wordmark-light.png" in message["html"]
    assert ".invalid" not in message["html"] + message["text"]
    assert "—" not in message["html"] + message["text"]


def test_render_refuses_a_non_https_origin() -> None:
    with pytest.raises(ValueError):
        render_existing_account_email(
            language="es-419",
            app_origin="http://app.example.test",
            asset_origin=ASSET_ORIGIN,
        )


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    messages: list[dict[str, object]] = []
    monkeypatch.setenv("CUADRAO_APP_ORIGIN", APP_ORIGIN)
    monkeypatch.setattr(
        "argus.domain.resend_email.send_resend_email",
        lambda **message: messages.append(message) or "accepted",
    )
    return messages


def test_one_key_per_address_per_hour(sent: list[dict[str, object]]) -> None:
    email = fake.email()
    hour = datetime(2026, 10, 28, 14, 5, tzinfo=timezone.utc)

    send_existing_account_notice(recipient=email, language="es-419", sent_at=hour)
    send_existing_account_notice(
        recipient=email.upper(), language="en", sent_at=hour + timedelta(minutes=50)
    )
    send_existing_account_notice(
        recipient=email, language="es-419", sent_at=hour + timedelta(hours=1)
    )
    send_existing_account_notice(
        recipient=fake.unique.email(), language="es-419", sent_at=hour
    )

    keys = [message["idempotency_key"] for message in sent]
    assert keys[0] == keys[1]
    assert len({keys[0], keys[2], keys[3]}) == 3
    assert email not in "".join(str(key) for key in keys)


def test_missing_origin_sends_nothing_and_does_not_raise(
    sent: list[dict[str, object]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CUADRAO_APP_ORIGIN")
    monkeypatch.delenv("ARGUS_APP_ORIGIN", raising=False)

    send_existing_account_notice(recipient=fake.email(), language="es-419")

    assert sent == []
