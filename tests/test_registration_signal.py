"""Registration signal, kept out of the alpha API suite for its budget.

Argus emits one acquisition event whose surface separates a guest converting
from a cold signup. Counting them together answers neither funnel question.
"""

from __future__ import annotations

from pathlib import Path

from argus.api.routers import auth as auth_router
from argus.api.schemas import OnboardingState, User
from argus.domain.store import utcnow

from tests.test_alpha_api_supabase import client, mock_gateway  # noqa: F401


def test_signup_emits_product_event_for_public_registration(
    mock_gateway,  # noqa: F811
    monkeypatch,
):

    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("ARGUS_MOCK_AUTH", "false")
    captured_events: list[tuple[str, dict[str, object]]] = []

    def fake_capture_product_event(kind: str, **payload: object) -> None:
        captured_events.append((kind, dict(payload)))

    monkeypatch.setattr(
        "argus.api.routers.auth.capture_product_event",
        fake_capture_product_event,
    )
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
    assert captured_events == [
        (
            "account_registration_completed",
            {
                "user_id": "user-1",
                "attributes": {
                    "surface": "direct_signup",
                    "language": "en",
                },
            },
        ),
    ]
    kind, payload = captured_events[0]
    assert kind == "account_registration_completed"
    assert set(payload.keys()) == {"user_id", "attributes"}
    assert payload["attributes"]["language"] == "en"
    assert payload["attributes"]["surface"] == "direct_signup"
    assert set(payload["attributes"].keys()) == {
        "surface",
        "language",
    }
    assert not set(payload["attributes"]).intersection(
        {
            "assistant_prose",
            "prompt",
            "message_history",
            "capital",
            "account_balance",
            "holdings",
            "email",
        }
    )

def test_registration_surfaces_distinguish_guest_conversion_from_direct_signup():
    """A guest converting and a cold signup are different funnel events.

    Collapsing them to one surface loses the only thing the signal is for:
    knowing whether the guest path is working.
    """

    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "argus"
        / "api"
        / "routers"
        / "auth.py"
    ).read_text(encoding="utf-8")

    assert 'surface="guest_conversion"' in source
    assert 'surface="direct_signup"' in source
    assert 'surface="auth_signup"' not in source
