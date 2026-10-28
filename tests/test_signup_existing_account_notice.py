from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from argus.api import state as api_state
from argus.api.main import app
from argus.domain.supabase_gateway import SupabaseGateway
from faker import Faker
from fastapi.testclient import TestClient

client = TestClient(app)
fake = Faker()
APP_ORIGIN = "https://app.example.test"


@pytest.fixture(autouse=True)
def _signup_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    from argus.api.routers import auth

    auth.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("ARGUS_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_APP_ORIGIN", APP_ORIGIN)


@pytest.fixture
def gateway(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    gateway = MagicMock(spec=SupabaseGateway)
    gateway.private_alpha_email_allowed.return_value = True
    gateway.private_alpha_email_disabled.return_value = False
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    return gateway


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    messages: list[dict[str, object]] = []

    def capture(**message: object) -> str:
        messages.append(message)
        return "accepted"

    monkeypatch.setattr("argus.domain.resend_email.send_resend_email", capture)
    return messages


def _provider_user(email: str, *, existing: bool) -> dict[str, object]:
    identities = [] if existing else [{"id": fake.uuid4()}]
    return {
        "session": None,
        "user": {"id": fake.uuid4(), "email": email, "identities": identities},
    }


def _signup(email: str, language: str = "es-419"):
    return client.post(
        "/api/v1/auth/signup",
        json={
            "age_confirmed_at": "2026-01-01T00:00:00Z",
            "email": email,
            "password": fake.password(length=12),
            "captcha_token": "captcha-proof",
            "language": language,
        },
        headers={"CF-Connecting-IP": fake.ipv4_public()},
    )


@pytest.mark.parametrize(
    ("language", "subject"),
    [
        ("es-419", "Ya tienes una cuenta en Cuadrao"),
        ("en", "You already have a Cuadrao account"),
    ],
)
def test_existing_owner_gets_sign_in_email_and_response_stays_identical(
    gateway: MagicMock,
    sent: list[dict[str, object]],
    language: str,
    subject: str,
) -> None:
    fresh_email, existing_email = fake.unique.email(), fake.unique.email()
    fresh_provider = _provider_user(fresh_email, existing=False)
    duplicate_provider = _provider_user(existing_email, existing=True)
    gateway.signup.side_effect = [fresh_provider, duplicate_provider]

    fresh = _signup(fresh_email, language)
    duplicate = _signup(existing_email, language)

    assert fresh.status_code == duplicate.status_code == 200
    assert fresh.json() == fresh_provider
    assert duplicate.json() == duplicate_provider
    assert fresh.headers.keys() == duplicate.headers.keys()
    assert [message["recipient"] for message in sent] == [existing_email.lower()]
    assert sent[0]["subject"] == subject
    assert f"{APP_ORIGIN}/?auth=login" in str(sent[0]["plain_text"])
    assert f"{APP_ORIGIN}/?auth=login" in str(sent[0]["html"])
    assert "—" not in str(sent[0]["plain_text"])


def test_failed_notice_leaves_the_duplicate_response_unchanged(
    gateway: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(**_: object) -> str:
        raise RuntimeError("Resend SMTP delivery was not accepted.")

    monkeypatch.setattr("argus.domain.resend_email.send_resend_email", refuse)
    existing_email = fake.unique.email()
    duplicate_provider = _provider_user(existing_email, existing=True)
    gateway.signup.return_value = duplicate_provider

    response = _signup(existing_email)

    assert response.status_code == 200
    assert response.json() == duplicate_provider


def test_denied_and_failed_signups_send_no_notice(
    gateway: MagicMock,
    sent: list[dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED", "true")
    gateway.private_alpha_email_disabled.return_value = True
    denied = _signup(fake.unique.email())

    gateway.private_alpha_email_disabled.return_value = False
    gateway.signup.side_effect = RuntimeError("provider down")
    failed = _signup(fake.unique.email())

    assert denied.status_code == failed.status_code == 400
    assert sent == []


def test_notice_is_queued_after_the_response_not_sent_inline(
    gateway: MagicMock,
    sent: list[dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.domain.existing_account_email import send_existing_account_notice
    from starlette.background import BackgroundTasks

    queued: list[tuple[object, dict[str, object]]] = []
    monkeypatch.setattr(
        BackgroundTasks,
        "add_task",
        lambda self, func, *args, **kwargs: queued.append((func, kwargs)),
    )
    existing_email = fake.unique.email()
    gateway.signup.return_value = _provider_user(existing_email, existing=True)

    response = _signup(existing_email)

    assert response.status_code == 200
    assert sent == []
    assert queued == [
        (
            send_existing_account_notice,
            {"recipient": existing_email, "language": "es-419"},
        )
    ]
