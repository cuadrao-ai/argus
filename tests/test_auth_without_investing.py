"""Authentication regressions retained when investing API coverage is retired."""

from unittest.mock import MagicMock

import pytest
from argus.api import state as api_state
from argus.api.main import app
from argus.api.routers import auth as auth_router
from argus.api.schemas import OnboardingState, User
from argus.domain.store import utcnow
from argus.domain.supabase_gateway import SupabaseGateway
from fastapi.testclient import TestClient

client = TestClient(app)


@pytest.fixture
def mock_gateway(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED", "false")
    gateway = MagicMock(spec=SupabaseGateway)
    gateway.client = MagicMock()
    gateway.login.return_value = {
        "session": {
            "access_token": "access-token-123",
            "refresh_token": "refresh-token-123",
        },
        "user": {"id": "test-user", "email": "disabled@example.com"},
    }
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    auth_router.reset_auth_attempt_limiter_for_tests()
    yield gateway
    auth_router.reset_auth_attempt_limiter_for_tests()


def _mock_profile(*, language: str = "en", stage: str = "ready") -> User:
    now = utcnow()
    return User(
        id="00000000-0000-0000-0000-000000000001",
        email="developer@argus.local",
        username="mock-developer",
        display_name="Mock Developer",
        language=language,  # type: ignore[arg-type]
        locale="es-419" if language == "es-419" else "en-US",
        is_admin=True,
        onboarding=OnboardingState(
            completed=stage == "completed",
            stage=stage,  # type: ignore[arg-type]
            language_confirmed=True,
            primary_goal="test_stock_idea" if stage != "language_selection" else None,
        ),
        created_at=now,
        updated_at=now,
    )


def test_signup_duplicate_obfuscated_user_does_not_create_profile(
    mock_gateway,
    monkeypatch,
):
    from argus.api.routers import auth as auth_router

    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    mock_gateway.private_alpha_email_allowed.return_value = True
    mock_gateway.signup.return_value = {
        "session": None,
        "user": {
            "id": "obfuscated-user-id",
            "email": "existing@example.com",
            "identities": [],
        },
    }

    response = client.post(
        "/api/v1/auth/signup",
        json={
            "age_confirmed_at": "2026-01-01T00:00:00Z",
            "email": "existing@example.com",
            "password": "password123",
            "captcha_token": "captcha-proof",
        },
    )

    assert response.status_code == 200
    mock_gateway.get_or_create_profile_for_auth_user.assert_not_called()


def test_signup_keeps_obfuscated_duplicate_indistinguishable_without_profile(
    mock_gateway,
    monkeypatch,
):
    from argus.api.routers import auth as auth_router

    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    mock_gateway.private_alpha_email_allowed.return_value = True
    fresh_provider_response = {
        "session": None,
        "user": {
            "id": "fresh-user-id",
            "email": "fresh@example.com",
            "identities": [{"id": "fresh-identity-id"}],
        },
    }
    duplicate_provider_response = {
        "session": None,
        "user": {
            "id": "obfuscated-user-id",
            "email": "existing@example.com",
            "identities": [],
        },
    }
    mock_gateway.signup.side_effect = [
        fresh_provider_response,
        duplicate_provider_response,
    ]
    profile_rows: set[str] = set()

    def create_profile(auth_user):
        profile_rows.add(str(auth_user["id"]))
        return _mock_profile().model_copy(update={"id": str(auth_user["id"])})

    mock_gateway.get_or_create_profile_for_auth_user.side_effect = create_profile
    headers = {"CF-Connecting-IP": "203.0.113.92"}

    fresh = client.post(
        "/api/v1/auth/signup",
        json={
            "age_confirmed_at": "2026-01-01T00:00:00Z",
            "email": "fresh@example.com",
            "password": "password123",
            "captcha_token": "captcha-proof",
        },
        headers=headers,
    )
    duplicate = client.post(
        "/api/v1/auth/signup",
        json={
            "age_confirmed_at": "2026-01-01T00:00:00Z",
            "email": "existing@example.com",
            "password": "password123",
            "captcha_token": "captcha-proof",
        },
        headers=headers,
    )

    assert fresh.status_code == duplicate.status_code == 200
    assert fresh.json() == fresh_provider_response
    assert duplicate.json() == duplicate_provider_response
    assert set(fresh.json()) == set(duplicate.json()) == {"session", "user"}
    assert set(fresh.json()["user"]) == set(duplicate.json()["user"])
    assert profile_rows == {"fresh-user-id"}
    mock_gateway.get_or_create_profile_for_auth_user.assert_called_once_with(
        fresh_provider_response["user"]
    )


def test_login_normalizes_private_alpha_access_failures(
    mock_gateway,
    monkeypatch,
):
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    mock_gateway.private_alpha_email_allowed.return_value = False

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "disabled@example.com",
            "password": "password123",
            "captcha_token": "captcha-proof",
        },
    )

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"
    assert response.json()["detail"] == "Invalid email or password."
    assert response.headers.get("set-cookie") is None
    mock_gateway.login.assert_called_once_with(
        email="disabled@example.com",
        password="password123",
        captcha_token="captcha-proof",
    )
    mock_gateway.private_alpha_email_allowed.assert_called_once_with(
        "disabled@example.com"
    )
    assert "mark_private_alpha_login" not in [
        call[0] for call in mock_gateway.method_calls
    ]
