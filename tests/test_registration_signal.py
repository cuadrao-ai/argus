from __future__ import annotations

from pathlib import Path

from argus.api.routers import auth as auth_router
from argus.api.schemas import OnboardingState, User
from argus.domain.store import utcnow

from tests.test_alpha_api_supabase import client, mock_gateway  # noqa: F401


def test_signup_does_not_emit_a_retired_product_event(
    mock_gateway,  # noqa: F811
    monkeypatch,
):

    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    mock_gateway.private_alpha_email_allowed.return_value = True
    now = utcnow()
    mock_gateway.signup.return_value = {
        "session": {
            "access_token": "access-token-123",
            "refresh_token": "refresh-token-123",
            "expires_in": 3600,
        },
        "user": {
            "id": "user-1",
            "email": "beta@example.com",
            "identities": [{"id": "identity-id"}],
        },
    }
    mock_gateway.get_or_create_profile_for_auth_user.return_value = User(
        id="user-1",
        email="beta@example.com",
        username="beta",
        display_name="Beta",
        language="en",
        locale="en-US",
        is_admin=False,
        onboarding=OnboardingState(
            completed=True,
            stage="ready",
            language_confirmed=True,
            primary_goal="test_stock_idea",
        ),
        created_at=now,
        updated_at=now,
    )

    response = client.post(
        "/api/v1/auth/signup",
        json={
            "age_confirmed_at": "2026-01-01T00:00:00Z",
            "email": "beta@example.com",
            "password": "password123",
            "captcha_token": "captcha-proof",
        },
    )

    assert response.status_code == 200
    assert response.json()["user"]["id"] == "user-1"
    assert "capture_product_event" not in Path(
        __file__
    ).resolve().parents[1].joinpath("src/argus/api/routers/auth.py").read_text(
        encoding="utf-8"
    )


def test_signup_source_does_not_name_retired_funnel_surfaces():
    source = (
        Path(__file__).resolve().parents[1] / "src/argus/api/routers/auth.py"
    ).read_text(encoding="utf-8")

    assert "capture_product_event" not in source
    assert "emit_verified_guest_funnel_event" not in source
    assert 'surface="auth_signup"' not in source
