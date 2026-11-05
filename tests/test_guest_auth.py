from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from argus.api import state as api_state
from argus.api.guest_access import registered_account_context
from argus.api.main import app
from argus.api.routers import auth as auth_router
from argus.api.schemas import OnboardingState, User
from argus.domain.guest_workspaces import GuestWorkspace
from argus.domain.store import utcnow
from argus.domain.supabase_gateway import SupabaseGateway
from fastapi import HTTPException
from fastapi.testclient import TestClient

USER_ID = "00000000-0000-0000-0000-000000000041"


def _profile() -> User:
    now = utcnow()
    return User(
        id=USER_ID,
        email=None,
        username=None,
        display_name=None,
        language="en",
        locale="en-US",
        is_admin=False,
        onboarding=OnboardingState(),
        created_at=now,
        updated_at=now,
    )


def _workspace(profile: User) -> GuestWorkspace:
    return GuestWorkspace(
        user_id=profile.id,
        conversation_id=None,
        status="active",
        created_at=profile.created_at,
        expires_at=profile.created_at + timedelta(days=7),
        claimed_by=None,
        claimed_at=None,
        updated_at=profile.created_at,
    )


@pytest.fixture(autouse=True)
def _guest_auth_environment(monkeypatch: pytest.MonkeyPatch):
    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    monkeypatch.delenv("CUADRAO_GUEST_ACCESS_ENABLED", raising=False)
    monkeypatch.delenv("CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED", raising=False)
    monkeypatch.delenv("NEXT_PUBLIC_GUEST_ACCESS_ENABLED", raising=False)


@pytest.fixture
def gateway() -> MagicMock:
    gateway = MagicMock(spec=SupabaseGateway)
    profile = _profile()
    workspace = _workspace(profile)
    gateway.sign_in_anonymously.return_value = {
        "user": {
            "id": USER_ID,
            "email": None,
            "is_anonymous": True,
            "user_metadata": {"language": "en"},
        },
        "session": {
            "access_token": "guest-access-token",
            "refresh_token": "guest-refresh-token",
            "expires_in": 3600,
        },
    }
    gateway.get_or_create_profile_for_auth_user.return_value = profile
    gateway.create_guest_workspace.return_value = workspace
    gateway.get_active_guest_workspace.return_value = workspace
    gateway.get_user.return_value = profile
    return gateway


def _enable_guest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_GUEST_ACCESS_ENABLED", "true")


def test_guest_flag_off_creates_no_anonymous_auth_user(
    gateway,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_ENABLED", "false")
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        TestClient(app) as client,
    ):
        response = client.post(
            "/api/v1/auth/guest",
            json={
                "age_confirmed_at": "2026-01-01T00:00:00Z",
                "captcha_token": "captcha-proof",
                "language": "en",
            },
        )

    assert response.status_code == 403
    assert response.json()["code"] == "guest_access_unavailable"
    gateway.sign_in_anonymously.assert_not_called()


def test_guest_flag_off_drains_an_existing_verified_guest_session(
    gateway,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_ENABLED", "false")
    gateway.get_auth_user_from_token.return_value = (
        gateway.sign_in_anonymously.return_value["user"]
    )
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
        TestClient(app) as client,
    ):
        response = client.get(
            "/api/v1/me",
            headers={"Authorization": "Bearer existing-guest-token"},
        )

    assert response.status_code == 200
    assert response.json()["account_kind"] == "guest"
    assert response.json()["user"]["id"] == USER_ID
    gateway.sign_in_anonymously.assert_not_called()


def test_claimed_guest_workspace_is_recoverable_only_on_signup_retry(
    gateway,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_guest(monkeypatch)
    gateway.get_auth_user_from_token.return_value = (
        gateway.sign_in_anonymously.return_value["user"]
    )
    gateway.get_active_guest_workspace.return_value = None
    claimed_workspace = _workspace(_profile()).model_copy(
        update={
            "status": "claimed",
            "claimed_by": "00000000-0000-0000-0000-000000000099",
            "claimed_at": utcnow(),
        }
    )
    gateway.get_guest_workspace_for_signup_retry.return_value = claimed_workspace

    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
        TestClient(app) as client,
    ):
        ordinary = client.get(
            "/api/v1/me",
            headers={"Authorization": "Bearer claimed-guest-token"},
        )
        signup_retry = client.post(
            "/api/v1/auth/guest/signup",
            json={
                "age_confirmed_at": "2026-01-01T00:00:00Z",
                "email": "retry@example.com",
                "password": "strong-password",
                "captcha_token": "captcha-proof",
            },
            headers={"Authorization": "Bearer claimed-guest-token"},
        )

    assert ordinary.status_code == 403
    assert ordinary.json()["code"] == "guest_session_expired"
    assert signup_retry.status_code == 400
    assert signup_retry.json()["code"] == "guest_handoff_invalid"
    gateway.get_guest_workspace_for_signup_retry.assert_called_once()


def test_guest_bootstrap_creates_real_anonymous_identity_profile_and_workspace(
    gateway,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_guest(monkeypatch)
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        TestClient(app) as client,
    ):
        response = client.post(
            "/api/v1/auth/guest",
            json={
                "age_confirmed_at": "2026-01-01T00:00:00Z",
                "captcha_token": "captcha-proof",
                "language": "en",
            },
            headers={"origin": "http://localhost:3000"},
        )

    assert response.status_code == 200
    assert response.json()["renewed_after_expiry"] is False
    assert response.json()["public_account_access_enabled"] is False
    assert response.cookies.get("sb-auth-token") == "guest-access-token"
    assert response.cookies.get("sb-refresh-token") == "guest-refresh-token"
    gateway.sign_in_anonymously.assert_called_once_with(
        captcha_token="captcha-proof",
        language="en",
    )
    auth_user = gateway.sign_in_anonymously.return_value["user"]
    gateway.get_or_create_profile_for_auth_user.assert_called_once_with(auth_user)
    gateway.create_guest_workspace.assert_called_once_with(
        user_id=USER_ID,
        created_at=gateway.get_or_create_profile_for_auth_user.return_value.created_at,
    )
    gateway.private_alpha_email_allowed.assert_not_called()


def test_guest_bootstrap_rolls_back_new_auth_user_on_workspace_failure(
    gateway,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_guest(monkeypatch)
    gateway.create_guest_workspace.side_effect = RuntimeError("database unavailable")
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        TestClient(app) as client,
    ):
        response = client.post(
            "/api/v1/auth/guest",
            json={
                "age_confirmed_at": "2026-01-01T00:00:00Z",
                "captcha_token": "captcha-proof",
                "language": "en",
            },
            headers={"origin": "http://localhost:3000"},
        )

    assert response.status_code == 503
    assert response.json()["code"] == "guest_bootstrap_failed"
    gateway.delete_auth_user.assert_called_once_with(USER_ID)


def test_valid_guest_cookie_reuses_identity_across_reload(
    gateway,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_guest(monkeypatch)
    gateway.get_auth_user_from_token.return_value = (
        gateway.sign_in_anonymously.return_value["user"]
    )
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
        TestClient(app) as client,
    ):
        client.cookies.set("sb-auth-token", "existing-guest-token")
        response = client.post(
            "/api/v1/auth/guest",
            json={
                "age_confirmed_at": "2026-01-01T00:00:00Z",
                "captcha_token": "captcha-proof",
                "language": "en",
            },
        )

    assert response.status_code == 200
    assert response.json()["reused"] is True
    assert response.json()["renewed_after_expiry"] is False
    assert response.json()["public_account_access_enabled"] is False
    assert response.json()["user"]["id"] == USER_ID
    assert "avatar_theme" not in response.json()["user"]
    gateway.sign_in_anonymously.assert_not_called()
    gateway.create_guest_workspace.assert_not_called()


def test_guest_auth_session_omits_registered_avatar_preferences(
    gateway,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_guest(monkeypatch)
    gateway.get_auth_user_from_token.return_value = (
        gateway.sign_in_anonymously.return_value["user"]
    )

    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
        TestClient(app) as client,
    ):
        response = client.get(
            "/api/v1/auth/session",
            headers={"Authorization": "Bearer verified-guest-token"},
        )

    assert response.status_code == 200
    assert response.json()["authenticated"] is True
    assert "avatar_theme" not in response.json()["user"]


def test_expired_verified_guest_session_mints_a_fresh_anonymous_identity(
    gateway,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_guest(monkeypatch)
    expired = HTTPException(
        status_code=403,
        detail={
            "code": "guest_session_expired",
            "detail": "This temporary guest session is no longer available.",
        },
    )
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch.object(auth_router, "current_user", side_effect=expired),
        TestClient(app) as client,
    ):
        response = client.post(
            "/api/v1/auth/guest",
            json={
                "age_confirmed_at": "2026-01-01T00:00:00Z",
                "captcha_token": "captcha-proof",
                "language": "en",
            },
        )

    assert response.status_code == 200
    assert response.json()["reused"] is False
    assert response.json()["renewed_after_expiry"] is True
    assert response.json()["user"]["email"] is None
    gateway.sign_in_anonymously.assert_called_once()
    gateway.create_guest_workspace.assert_called_once()


def test_guest_bootstrap_preserves_unrelated_forbidden_session_failure(
    gateway,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_guest(monkeypatch)
    denied = HTTPException(
        status_code=403,
        detail={
            "code": "private_alpha_access_required",
            "detail": "Private alpha access is required.",
        },
    )
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch.object(auth_router, "current_user", side_effect=denied),
        TestClient(app) as client,
    ):
        response = client.post(
            "/api/v1/auth/guest",
            json={
                "age_confirmed_at": "2026-01-01T00:00:00Z",
                "captcha_token": "captcha-proof",
                "language": "en",
            },
        )

    assert response.status_code == 403
    assert response.json()["code"] == "private_alpha_access_required"
    gateway.sign_in_anonymously.assert_not_called()


def test_guest_bootstrap_never_replaces_a_registered_session(
    gateway,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_guest(monkeypatch)
    registered = _profile().model_copy(
        update={"email": "registered@example.com", "is_admin": False}
    )
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch.object(auth_router, "current_user", return_value=registered),
        patch.object(
            auth_router,
            "account_context",
            return_value=registered_account_context(registered.id),
        ),
        TestClient(app) as client,
    ):
        response = client.post(
            "/api/v1/auth/guest",
            json={
                "age_confirmed_at": "2026-01-01T00:00:00Z",
                "captcha_token": "captcha-proof",
                "language": "en",
            },
        )

    assert response.status_code == 409
    assert response.json()["code"] == "account_already_registered"
    gateway.sign_in_anonymously.assert_not_called()


def test_guest_feedback_success_uses_shared_sanitized_telemetry(
    gateway,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_guest(monkeypatch)
    secret_feedback = "feedback-secret-that-must-not-be-logged"
    gateway.get_auth_user_from_token.return_value = (
        gateway.sign_in_anonymously.return_value["user"]
    )
    gateway.create_feedback_settling_usage.return_value = {
        "decision": "accepted",
        "replayed": False,
    }
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
        patch("argus.api.routers.feedback.logger.info") as log_info,
        TestClient(app) as client,
    ):
        response = client.post(
            "/api/v1/feedback",
            json={
                "type": "general",
                "message": secret_feedback,
                "context": {
                    "source": "settings",
                    "raw_prompt": "transcript-secret",
                },
            },
            headers={"Authorization": "Bearer existing-guest-token"},
        )

    assert response.status_code == 200
    log_info.assert_called_once_with(
        "Feedback submitted",
        feedback_type="general",
        feedback_source="settings",
        message_len=len(secret_feedback),
    )
    assert secret_feedback not in repr(log_info.call_args)
    assert "transcript-secret" not in repr(log_info.call_args)


def test_guest_ip_limit_runs_before_anonymous_auth_creation(
    gateway,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_guest(monkeypatch)
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        TestClient(app) as client,
    ):
        responses = []
        for _ in range(auth_router.AUTH_GUEST_ATTEMPT_LIMIT + 1):
            responses.append(
                client.post(
                    "/api/v1/auth/guest",
                    json={
                        "age_confirmed_at": "2026-01-01T00:00:00Z",
                        "captcha_token": "captcha-proof",
                        "language": "en",
                    },
                    headers={"CF-Connecting-IP": "203.0.113.41"},
                )
            )
            client.cookies.clear()

    assert responses[-1].status_code == 429
    assert gateway.sign_in_anonymously.call_count == auth_router.AUTH_GUEST_ATTEMPT_LIMIT


def test_guest_captcha_token_is_bounded_before_provider_call(
    gateway,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_guest(monkeypatch)
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        TestClient(app) as client,
    ):
        response = client.post(
            "/api/v1/auth/guest",
            json={
                "age_confirmed_at": "2026-01-01T00:00:00Z",
                "captcha_token": "x" * 4097,
                "language": "en",
            },
        )

    assert response.status_code == 422
    gateway.sign_in_anonymously.assert_not_called()


def test_public_account_mode_allows_unlisted_signup_without_role_elevation(
    gateway,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED", "true")
    gateway.private_alpha_email_disabled.return_value = False
    gateway.signup.return_value = {"user": {"id": "ordinary-user"}, "session": None}
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        TestClient(app) as client,
    ):
        response = client.post(
            "/api/v1/auth/signup",
            json={
                "age_confirmed_at": "2026-01-01T00:00:00Z",
                "email": "ordinary@example.com",
                "password": "password-strong",
                "captcha_token": "captcha-proof",
                "language": "en",
            },
        )

    assert response.status_code == 200
    gateway.signup.assert_called_once()
    gateway.private_alpha_email_allowed.assert_not_called()


def test_public_account_mode_still_blocks_explicitly_disabled_identity(
    gateway,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED", "true")
    gateway.private_alpha_email_disabled.return_value = True
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        TestClient(app) as client,
    ):
        response = client.post(
            "/api/v1/auth/signup",
            json={
                "age_confirmed_at": "2026-01-01T00:00:00Z",
                "email": "disabled@example.com",
                "password": "password-strong",
                "captcha_token": "captcha-proof",
                "language": "en",
            },
        )

    assert response.status_code == 400
    assert response.json()["code"] == "auth_signup_failed"
    gateway.signup.assert_not_called()
