from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from argus.api import state as api_state
from argus.api.guest_access import (
    guest_account_context,
    registered_account_context,
    store_account_context,
)
from argus.api.main import app
from argus.api.routers import auth as auth_router
from argus.api.schemas import (
    GuestAccountSignupRequest,
    GuestHandoffCreateRequest,
    GuestPendingAction,
    OnboardingState,
    User,
)
from argus.domain.guest_workspaces import GuestWorkspace
from argus.domain.store import utcnow
from argus.domain.supabase_gateway import SupabaseGateway
from argus.domain.username_signup import GuestSignupPrevalidation
from fastapi import Request
from fastapi.testclient import TestClient

GUEST_ID = "00000000-0000-0000-0000-000000000301"
REGISTERED_ID = "00000000-0000-0000-0000-000000000302"
CONVERSATION_ID = "00000000-0000-0000-0000-000000000303"
HANDOFF_ID = "00000000-0000-0000-0000-000000000304"


def _profile(*, user_id: str, email: str | None) -> User:
    now = utcnow()
    return User(
        id=user_id,
        email=email,
        username=None,
        display_name=None,
        language="en",
        locale="en-US",
        is_admin=False,
        onboarding=OnboardingState(),
        created_at=now,
        updated_at=now,
    )


def _workspace() -> GuestWorkspace:
    now = utcnow()
    return GuestWorkspace(
        user_id=GUEST_ID,
        conversation_id=CONVERSATION_ID,
        status="active",
        created_at=now,
        expires_at=now + timedelta(days=7),
        claimed_by=None,
        claimed_at=None,
        updated_at=now,
    )


@pytest.fixture(autouse=True)
def _conversion_environment(monkeypatch: pytest.MonkeyPatch):
    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("ARGUS_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("ARGUS_MOCK_AUTH", "false")
    monkeypatch.delenv("ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED", raising=False)
    yield
    auth_router.reset_auth_attempt_limiter_for_tests()


def _guest_dependency(request: Request) -> User:
    profile = _profile(user_id=GUEST_ID, email=None)
    store_account_context(request, guest_account_context(_workspace()))
    return profile


def _registered_dependency(request: Request) -> User:
    profile = _profile(user_id=REGISTERED_ID, email="member@example.com")
    store_account_context(request, registered_account_context(REGISTERED_ID))
    return profile


def test_conversion_contract_rejects_untyped_or_cross_conversation_actions() -> None:
    request = GuestHandoffCreateRequest.model_validate(
        {
            "destination_email": "member@example.com",
            "source_conversation_id": CONVERSATION_ID,
            "pending_action": {
                "reason": "save_decision",
                "conversation_id": CONVERSATION_ID,
                "artifact_id": "00000000-0000-0000-0000-000000000305",
                "action_id": "decision-action-1",
            },
        }
    )
    assert request.pending_action is not None
    assert request.pending_action.reason == "save_decision"

    with pytest.raises(ValueError):
        GuestHandoffCreateRequest.model_validate(
            {
                "destination_email": "member@example.com",
                "source_conversation_id": CONVERSATION_ID,
                "pending_action": {
                    "reason": "invented_action",
                    "conversation_id": CONVERSATION_ID,
                    "action_id": "bad-action",
                },
            }
        )
    with pytest.raises(ValueError):
        GuestHandoffCreateRequest.model_validate(
            {
                "destination_email": "member@example.com",
                "source_conversation_id": CONVERSATION_ID,
                "pending_action": {
                    "reason": "keep_history",
                    "conversation_id": REGISTERED_ID,
                    "action_id": "cross-conversation",
                },
            }
        )


def test_guest_account_signup_contract_requires_a_real_email_and_strong_password() -> (
    None
):
    request = GuestAccountSignupRequest(
        age_confirmed_at="2026-01-01T00:00:00Z",
        email="new-member@example.com",
        password="strong-password",
        captcha_token="captcha-proof",
        language="es-419",
    )
    assert request.email == "new-member@example.com"
    assert request.language == "es-419"

    with pytest.raises(ValueError):
        GuestAccountSignupRequest(
            age_confirmed_at="2026-01-01T00:00:00Z",
            email="not-an-email",
            password="strong-password",
            captcha_token="captcha-proof",
        )
    with pytest.raises(ValueError):
        GuestAccountSignupRequest(
            age_confirmed_at="2026-01-01T00:00:00Z",
            email="new-member@example.com",
            password="short",
            captcha_token="captcha-proof",
        )


def test_guest_creates_http_only_email_bound_handoff_without_account_oracle() -> None:
    gateway = MagicMock(spec=SupabaseGateway)
    gateway.create_guest_workspace_handoff.return_value = {
        "id": HANDOFF_ID,
        "expires_at": utcnow() + timedelta(minutes=10),
        "opaque_secret": "opaque-cookie-secret",
    }
    app.dependency_overrides.clear()
    from argus.api.dependencies import current_user

    app.dependency_overrides[current_user] = _guest_dependency
    try:
        with (
            patch.object(api_state, "supabase_gateway", gateway),
            TestClient(app, base_url="http://localhost:3000") as client,
        ):
            response = client.post(
                "/api/v1/auth/guest/handoffs",
                json={
                    "destination_email": "member@example.com",
                    "source_conversation_id": CONVERSATION_ID,
                    "pending_action": {
                        "reason": "keep_history",
                        "conversation_id": CONVERSATION_ID,
                        "action_id": "new-chat-1",
                    },
                },
                headers={
                    "Authorization": "Bearer guest-token",
                    "origin": "http://localhost:3000",
                    "x-forwarded-proto": "https",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["handoff_id"] == HANDOFF_ID
    assert "secret" not in response.json()
    set_cookie = response.headers["set-cookie"]
    assert "argus-guest-handoff=" in set_cookie
    assert "argus-guest-handoff-id=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    # Lax only carries this cookie because the API shares a registrable domain
    # with the app. test_api_and_app_share_a_registrable_domain pins that.
    assert "SameSite=lax" in set_cookie
    assert "Secure" in set_cookie
    gateway.create_guest_workspace_handoff.assert_called_once()
    call = gateway.create_guest_workspace_handoff.call_args.kwargs
    assert call["source_user_id"] == GUEST_ID
    assert call["destination_email"] == "member@example.com"
    assert call["source_conversation_id"] == CONVERSATION_ID
    assert call["handoff_kind"] == "existing_account"
    assert "secret" not in call["pending_action"]


def test_guest_prepares_signup_handoff_before_provider_mutation() -> None:
    gateway = MagicMock(spec=SupabaseGateway)
    gateway.create_guest_workspace_handoff.return_value = {
        "id": HANDOFF_ID,
        "expires_at": utcnow() + timedelta(days=7),
        "opaque_secret": "opaque-signup-secret",
    }
    app.dependency_overrides.clear()
    from argus.api.dependencies import current_user

    app.dependency_overrides[current_user] = _guest_dependency
    try:
        with (
            patch.object(api_state, "supabase_gateway", gateway),
            TestClient(app, base_url="http://localhost:3000") as client,
        ):
            response = client.post(
                "/api/v1/auth/guest/handoffs",
                json={
                    "handoff_kind": "new_account_signup",
                    "destination_email": "new-member@example.com",
                    "source_conversation_id": CONVERSATION_ID,
                    "pending_action": {
                        "reason": "keep_history",
                        "conversation_id": CONVERSATION_ID,
                        "action_id": "signup-1",
                    },
                },
                headers={
                    "Authorization": "Bearer guest-token",
                    "origin": "http://localhost:3000",
                    "x-forwarded-proto": "https",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    gateway.create_guest_workspace_handoff.assert_called_once()
    assert (
        gateway.create_guest_workspace_handoff.call_args.kwargs["handoff_kind"]
        == "new_account_signup"
    )
    max_ages = [
        int(part.split("=", 1)[1])
        for value in response.headers.get_list("set-cookie")
        for part in value.split("; ")
        if part.startswith("Max-Age=")
    ]
    assert len(max_ages) == 2
    assert all(value > 600 for value in max_ages)


def test_login_reconciles_cookie_bound_handoff_before_returning_session() -> None:
    gateway = MagicMock(spec=SupabaseGateway)
    gateway.private_alpha_email_allowed.return_value = True
    gateway.login.return_value = {
        "user": {
            "id": REGISTERED_ID,
            "email": "member@example.com",
            "is_anonymous": False,
        },
        "session": {
            "access_token": "registered-access-token",
            "refresh_token": "registered-refresh-token",
            "expires_in": 3600,
        },
    }
    gateway.claim_guest_workspace_handoff.return_value = {
        "source_user_id": GUEST_ID,
        "destination_user_id": REGISTERED_ID,
        "conversation_id": CONVERSATION_ID,
        "pending_action": {
            "reason": "keep_history",
            "conversation_id": CONVERSATION_ID,
            "action_id": "new-chat-1",
        },
    }
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        TestClient(app, base_url="http://localhost:3000") as client,
    ):
        client.cookies.set("argus-guest-handoff-id", HANDOFF_ID)
        client.cookies.set("argus-guest-handoff", "opaque-cookie-secret")
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "member@example.com",
                "password": "strong-password",
                "captcha_token": "captcha-proof",
            },
        )

    assert response.status_code == 200
    assert response.json()["guest_claim"] == {
        "conversation_id": CONVERSATION_ID,
        "pending_action": GuestPendingAction(
            reason="keep_history",
            conversation_id=CONVERSATION_ID,
            action_id="new-chat-1",
        ).model_dump(mode="json"),
    }
    gateway.claim_guest_workspace_handoff.assert_called_once_with(
        handoff_id=HANDOFF_ID,
        opaque_secret="opaque-cookie-secret",
        destination_user_id=REGISTERED_ID,
        allow_same_destination_replay=True,
    )
    gateway.get_or_create_profile_for_auth_user.assert_called_once_with(
        gateway.login.return_value["user"]
    )
    assert "Max-Age=0" in response.headers["set-cookie"]


def test_login_handoff_reconciliation_does_not_duplicate_completion_events() -> None:
    gateway = MagicMock(spec=SupabaseGateway)
    gateway.private_alpha_email_allowed.return_value = True
    gateway.login.return_value = {
        "user": {
            "id": REGISTERED_ID,
            "email": "member@example.com",
            "is_anonymous": False,
        },
        "session": {
            "access_token": "registered-access-token",
            "refresh_token": "registered-refresh-token",
        },
    }
    gateway.claim_guest_workspace_handoff.return_value = {
        "source_user_id": GUEST_ID,
        "destination_user_id": REGISTERED_ID,
        "conversation_id": CONVERSATION_ID,
        "pending_action": None,
        "replayed": True,
    }
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.routers.auth.emit_verified_guest_funnel_event") as emit,
        TestClient(app) as client,
    ):
        client.cookies.set("argus-guest-handoff-id", HANDOFF_ID)
        client.cookies.set("argus-guest-handoff", "opaque-cookie-secret")
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "member@example.com",
                "password": "strong-password",
                "captcha_token": "captcha-proof",
            },
        )

    assert response.status_code == 200
    emit.assert_not_called()


@pytest.mark.parametrize(
    ("handoff_error", "expected_status"),
    [
        ("guest_handoff_invalid", 400),
        ("guest_handoff_expired", 410),
        ("guest_handoff_consumed", 409),
        ("guest_handoff_wrong_destination", 403),
    ],
)
def test_terminal_login_handoff_failure_keeps_login_and_clears_stale_cookies(
    handoff_error: str,
    expected_status: int,
) -> None:
    gateway = MagicMock(spec=SupabaseGateway)
    gateway.private_alpha_email_allowed.return_value = True
    gateway.login.return_value = {
        "user": {
            "id": REGISTERED_ID,
            "email": "member@example.com",
            "is_anonymous": False,
        },
        "session": {
            "access_token": "registered-access-token",
            "refresh_token": "registered-refresh-token",
            "expires_in": 3600,
        },
    }
    gateway.claim_guest_workspace_handoff.side_effect = RuntimeError(handoff_error)

    with (
        patch.object(api_state, "supabase_gateway", gateway),
        TestClient(app, base_url="http://localhost:3000") as client,
    ):
        client.cookies.set("argus-guest-handoff-id", HANDOFF_ID)
        client.cookies.set("argus-guest-handoff", "opaque-cookie-secret")
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "member@example.com",
                "password": "strong-password",
                "captcha_token": "captcha-proof",
            },
        )

    assert response.status_code == expected_status
    assert response.json()["code"] == handoff_error
    set_cookie = response.headers.get_list("set-cookie")
    assert any(value.startswith("sb-auth-token=") for value in set_cookie)
    assert any(value.startswith("sb-refresh-token=") for value in set_cookie)
    assert any(
        value.startswith("argus-guest-handoff=") and "Max-Age=0" in value
        for value in set_cookie
    )
    assert any(
        value.startswith("argus-guest-handoff-id=") and "Max-Age=0" in value
        for value in set_cookie
    )
    assert "guest_claim" not in response.json()


def test_retryable_login_handoff_failure_keeps_login_and_handoff_cookie() -> None:
    gateway = MagicMock(spec=SupabaseGateway)
    gateway.private_alpha_email_allowed.return_value = True
    gateway.login.return_value = {
        "user": {
            "id": REGISTERED_ID,
            "email": "member@example.com",
            "is_anonymous": False,
        },
        "session": {
            "access_token": "registered-access-token",
            "refresh_token": "registered-refresh-token",
            "expires_in": 3600,
        },
    }
    gateway.claim_guest_workspace_handoff.side_effect = RuntimeError(
        "guest_handoff_claim_unavailable"
    )

    with (
        patch.object(api_state, "supabase_gateway", gateway),
        TestClient(app, base_url="http://localhost:3000") as client,
    ):
        client.cookies.set("argus-guest-handoff-id", HANDOFF_ID)
        client.cookies.set("argus-guest-handoff", "opaque-cookie-secret")
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "member@example.com",
                "password": "strong-password",
                "captcha_token": "captcha-proof",
            },
        )

    assert response.status_code == 503
    assert response.json()["code"] == "guest_handoff_claim_unavailable"
    set_cookie = response.headers.get_list("set-cookie")
    assert any(value.startswith("sb-auth-token=") for value in set_cookie)
    assert any(value.startswith("sb-refresh-token=") for value in set_cookie)
    assert not any(
        value.startswith("argus-guest-handoff=") and "Max-Age=0" in value
        for value in set_cookie
    )
    assert "guest_claim" not in response.json()


def test_registered_claim_uses_cookie_secret_and_returns_the_bound_pending_action() -> (
    None
):
    gateway = MagicMock(spec=SupabaseGateway)
    gateway.claim_guest_workspace_handoff.return_value = {
        "source_user_id": GUEST_ID,
        "destination_user_id": REGISTERED_ID,
        "conversation_id": CONVERSATION_ID,
        "pending_action": {
            "reason": "save_decision",
            "conversation_id": CONVERSATION_ID,
            "artifact_id": "00000000-0000-0000-0000-000000000305",
            "action_id": "decision-action-1",
        },
    }
    app.dependency_overrides.clear()
    from argus.api.dependencies import current_user

    app.dependency_overrides[current_user] = _registered_dependency
    try:
        with (
            patch.object(api_state, "supabase_gateway", gateway),
            TestClient(app, base_url="http://localhost:3000") as client,
        ):
            client.cookies.set("argus-guest-handoff", "opaque-cookie-secret")
            response = client.post(
                f"/api/v1/auth/guest/handoffs/{HANDOFF_ID}/claim",
                headers={
                    "origin": "http://localhost:3000",
                    "x-forwarded-proto": "https",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["conversation_id"] == CONVERSATION_ID
    assert response.json()["pending_action"]["action_id"] == "decision-action-1"
    gateway.claim_guest_workspace_handoff.assert_called_once_with(
        handoff_id=HANDOFF_ID,
        opaque_secret="opaque-cookie-secret",
        destination_user_id=REGISTERED_ID,
        allow_same_destination_replay=False,
    )
    assert "Max-Age=0" in response.headers["set-cookie"]


def test_terminal_direct_handoff_claim_clears_stale_cookies() -> None:
    gateway = MagicMock(spec=SupabaseGateway)
    gateway.claim_guest_workspace_handoff.side_effect = RuntimeError(
        "guest_handoff_expired"
    )
    app.dependency_overrides.clear()
    from argus.api.dependencies import current_user

    app.dependency_overrides[current_user] = _registered_dependency
    try:
        with (
            patch.object(api_state, "supabase_gateway", gateway),
            TestClient(app, base_url="http://localhost:3000") as client,
        ):
            client.cookies.set("argus-guest-handoff", "opaque-cookie-secret")
            client.cookies.set("argus-guest-handoff-id", HANDOFF_ID)
            response = client.post(
                f"/api/v1/auth/guest/handoffs/{HANDOFF_ID}/claim",
                headers={
                    "origin": "http://localhost:3000",
                    "x-forwarded-proto": "https",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 410
    assert response.json()["code"] == "guest_handoff_expired"
    set_cookie = response.headers.get_list("set-cookie")
    assert any(
        value.startswith("argus-guest-handoff=") and "Max-Age=0" in value
        for value in set_cookie
    )
    assert any(
        value.startswith("argus-guest-handoff-id=") and "Max-Age=0" in value
        for value in set_cookie
    )


def _signup_handoff(*, destination_user_id: str | None) -> dict[str, object]:
    return {
        "id": HANDOFF_ID,
        "source_user_id": GUEST_ID,
        "destination_user_id": destination_user_id,
        "source_conversation_id": CONVERSATION_ID,
        "pending_action": {
            "reason": "keep_history",
            "conversation_id": CONVERSATION_ID,
            "action_id": "signup-1",
        },
        "handoff_kind": "new_account_signup",
        "status": "pending",
        "expires_at": utcnow() + timedelta(days=7),
        "proof": "a" * 64,
    }


def _signup_auth_user(*, confirmed: bool = False) -> dict[str, object]:
    return {
        "id": REGISTERED_ID,
        "email": "approved@example.com",
        "is_anonymous": False,
        "email_confirmed_at": utcnow().isoformat() if confirmed else None,
        "identities": [{"provider": "email"}],
    }


def _post_guest_signup(gateway: MagicMock) -> object:
    app.dependency_overrides.clear()
    from argus.api.dependencies import current_user

    app.dependency_overrides[current_user] = _guest_dependency
    try:
        with (
            patch.object(api_state, "supabase_gateway", gateway),
            patch.object(api_state, "DATABASE_URL", "postgresql://test"),
            TestClient(app, base_url="http://localhost:3000") as client,
        ):
            client.cookies.set("argus-guest-handoff-id", HANDOFF_ID)
            client.cookies.set("argus-guest-handoff", "opaque-signup-secret")
            return client.post(
                "/api/v1/auth/guest/signup",
                json={
                    "age_confirmed_at": "2026-01-01T00:00:00Z",
                    "email": "approved@example.com",
                    "password": "strong-password",
                    "captcha_token": "captcha-proof",
                    "display_name": "Alex",
                    "language": "es-419",
                },
                headers={"Authorization": "Bearer guest-token"},
            )
    finally:
        app.dependency_overrides.clear()


def test_guest_signup_creates_a_distinct_account_and_keeps_pending_handoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED", "false")
    gateway = MagicMock(spec=SupabaseGateway)
    gateway.private_alpha_email_allowed.return_value = True
    gateway.get_guest_signup_handoff.side_effect = [
        _signup_handoff(destination_user_id=None),
        _signup_handoff(destination_user_id=REGISTERED_ID),
    ]
    gateway.signup.return_value = {
        "user": _signup_auth_user(),
        "session": None,
    }
    gateway.get_or_create_profile_for_auth_user.return_value = _profile(
        user_id=REGISTERED_ID,
        email="approved@example.com",
    )

    with patch("argus.api.routers.auth.serialized_guest_signup") as serialized:
        serialized.return_value.__enter__.return_value = GuestSignupPrevalidation(
            auth_user_id=None,
            auth_user_confirmed=False,
            username_available=True,
        )
        response = _post_guest_signup(gateway)

    assert response.status_code == 200
    assert response.json()["session"] is None
    assert response.json()["user"]["id"] == REGISTERED_ID
    gateway.signup.assert_called_once_with(
        age_confirmed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        email="approved@example.com",
        password="strong-password",
        captcha_token="captcha-proof",
        display_name="Alex",
        username=None,
        language="es-419",
        guest_signup_handoff={
            "handoff_id": HANDOFF_ID,
            "proof": "a" * 64,
        },
    )
    gateway.claim_guest_workspace_handoff.assert_not_called()


def test_guest_signup_immediate_session_claims_the_complete_graph() -> None:
    gateway = MagicMock(spec=SupabaseGateway)
    gateway.private_alpha_email_disabled.return_value = False
    gateway.get_guest_signup_handoff.side_effect = [
        _signup_handoff(destination_user_id=None),
        _signup_handoff(destination_user_id=REGISTERED_ID),
    ]
    gateway.signup.return_value = {
        "user": _signup_auth_user(),
        "session": {
            "access_token": "registered-access-token",
            "refresh_token": "registered-refresh-token",
            "expires_in": 3600,
        },
    }
    gateway.get_or_create_profile_for_auth_user.return_value = _profile(
        user_id=REGISTERED_ID,
        email="approved@example.com",
    )
    gateway.claim_guest_workspace_handoff.return_value = {
        "source_user_id": GUEST_ID,
        "destination_user_id": REGISTERED_ID,
        "conversation_id": CONVERSATION_ID,
        "pending_action": _signup_handoff(destination_user_id=None)["pending_action"],
        "replayed": False,
    }

    with patch("argus.api.routers.auth.serialized_guest_signup") as serialized:
        serialized.return_value.__enter__.return_value = GuestSignupPrevalidation(
            auth_user_id=None,
            auth_user_confirmed=False,
            username_available=True,
        )
        response = _post_guest_signup(gateway)

    assert response.status_code == 200
    assert response.json()["user"]["id"] == REGISTERED_ID
    assert response.json()["user"]["id"] != GUEST_ID
    assert response.json()["guest_claim"]["conversation_id"] == CONVERSATION_ID
    gateway.claim_guest_workspace_handoff.assert_called_once_with(
        handoff_id=HANDOFF_ID,
        opaque_secret="opaque-signup-secret",
        destination_user_id=REGISTERED_ID,
        allow_same_destination_replay=True,
    )
    set_cookie = response.headers.get_list("set-cookie")
    assert any(value.startswith("sb-auth-token=") for value in set_cookie)
    assert any(
        value.startswith("argus-guest-handoff=") and "Max-Age=0" in value
        for value in set_cookie
    )


def test_guest_signup_retry_resends_only_for_same_bound_unconfirmed_account() -> None:
    gateway = MagicMock(spec=SupabaseGateway)
    gateway.private_alpha_email_disabled.return_value = False
    gateway.get_guest_signup_handoff.return_value = _signup_handoff(
        destination_user_id=REGISTERED_ID
    )
    gateway.get_auth_user_by_id.return_value = _signup_auth_user()
    gateway.get_or_create_profile_for_auth_user.return_value = _profile(
        user_id=REGISTERED_ID,
        email="approved@example.com",
    )

    with patch("argus.api.routers.auth.serialized_guest_signup") as serialized:
        serialized.return_value.__enter__.return_value = GuestSignupPrevalidation(
            auth_user_id=REGISTERED_ID,
            auth_user_confirmed=False,
            username_available=True,
        )
        response = _post_guest_signup(gateway)

    assert response.status_code == 200
    assert response.json()["session"] is None
    assert response.json()["reconciled"] is True
    gateway.resend_signup_confirmation.assert_called_once_with(
        email="approved@example.com",
        captcha_token="captcha-proof",
    )
    gateway.signup.assert_not_called()


def test_guest_signup_retry_logs_in_same_bound_confirmed_account_and_claims() -> None:
    gateway = MagicMock(spec=SupabaseGateway)
    gateway.private_alpha_email_disabled.return_value = False
    gateway.get_guest_signup_handoff.return_value = _signup_handoff(
        destination_user_id=REGISTERED_ID
    )
    gateway.login.return_value = {
        "user": _signup_auth_user(confirmed=True),
        "session": {
            "access_token": "registered-access-token",
            "refresh_token": "registered-refresh-token",
            "expires_in": 3600,
        },
    }
    gateway.get_or_create_profile_for_auth_user.return_value = _profile(
        user_id=REGISTERED_ID,
        email="approved@example.com",
    )
    gateway.claim_guest_workspace_handoff.return_value = {
        "source_user_id": GUEST_ID,
        "destination_user_id": REGISTERED_ID,
        "conversation_id": CONVERSATION_ID,
        "pending_action": _signup_handoff(destination_user_id=None)["pending_action"],
        "handoff_kind": "new_account_signup",
        "replayed": False,
    }

    with patch("argus.api.routers.auth.serialized_guest_signup") as serialized:
        serialized.return_value.__enter__.return_value = GuestSignupPrevalidation(
            auth_user_id=REGISTERED_ID,
            auth_user_confirmed=True,
            username_available=True,
        )
        response = _post_guest_signup(gateway)

    assert response.status_code == 200
    assert response.json()["reconciled"] is True
    assert response.json()["guest_claim"]["conversation_id"] == CONVERSATION_ID
    gateway.login.assert_called_once_with(
        email="approved@example.com",
        password="strong-password",
        captcha_token="captcha-proof",
    )
    gateway.claim_guest_workspace_handoff.assert_called_once_with(
        handoff_id=HANDOFF_ID,
        opaque_secret="opaque-signup-secret",
        destination_user_id=REGISTERED_ID,
        allow_same_destination_replay=True,
    )
    gateway.signup.assert_not_called()
    gateway.resend_signup_confirmation.assert_not_called()


def test_guest_signup_replays_consumed_handoff_after_lost_claim_response() -> None:
    gateway = MagicMock(spec=SupabaseGateway)
    gateway.private_alpha_email_disabled.return_value = False
    gateway.get_guest_signup_handoff.return_value = {
        **_signup_handoff(destination_user_id=REGISTERED_ID),
        "status": "consumed",
    }
    gateway.login.return_value = {
        "user": _signup_auth_user(confirmed=True),
        "session": {
            "access_token": "registered-access-token",
            "refresh_token": "registered-refresh-token",
            "expires_in": 3600,
        },
    }
    gateway.get_or_create_profile_for_auth_user.return_value = _profile(
        user_id=REGISTERED_ID,
        email="approved@example.com",
    )
    gateway.claim_guest_workspace_handoff.return_value = {
        "source_user_id": GUEST_ID,
        "destination_user_id": REGISTERED_ID,
        "conversation_id": CONVERSATION_ID,
        "pending_action": _signup_handoff(destination_user_id=None)["pending_action"],
        "handoff_kind": "new_account_signup",
        "replayed": True,
    }

    with (
        patch("argus.api.routers.auth.serialized_guest_signup") as serialized,
        patch("argus.api.routers.auth.emit_verified_guest_funnel_event") as emit,
    ):
        serialized.return_value.__enter__.return_value = GuestSignupPrevalidation(
            auth_user_id=REGISTERED_ID,
            auth_user_confirmed=True,
            username_available=True,
        )
        response = _post_guest_signup(gateway)

    assert response.status_code == 200
    assert response.json()["reconciled"] is True
    assert response.json()["guest_claim"]["conversation_id"] == CONVERSATION_ID
    gateway.claim_guest_workspace_handoff.assert_called_once_with(
        handoff_id=HANDOFF_ID,
        opaque_secret="opaque-signup-secret",
        destination_user_id=REGISTERED_ID,
        allow_same_destination_replay=True,
    )
    emit.assert_not_called()


def test_guest_signup_confirmed_retry_with_wrong_password_keeps_account_separate() -> (
    None
):
    gateway = MagicMock(spec=SupabaseGateway)
    gateway.private_alpha_email_disabled.return_value = False
    gateway.get_guest_signup_handoff.return_value = _signup_handoff(
        destination_user_id=REGISTERED_ID
    )
    gateway.login.side_effect = RuntimeError("invalid credentials")

    with patch("argus.api.routers.auth.serialized_guest_signup") as serialized:
        serialized.return_value.__enter__.return_value = GuestSignupPrevalidation(
            auth_user_id=REGISTERED_ID,
            auth_user_confirmed=True,
            username_available=True,
        )
        response = _post_guest_signup(gateway)

    assert response.status_code == 409
    assert response.json()["code"] == "account_exists_use_login"
    gateway.claim_guest_workspace_handoff.assert_not_called()
    gateway.signup.assert_not_called()


@pytest.mark.parametrize(
    ("bound_user_id", "auth_user_id", "confirmed"),
    [
        (None, REGISTERED_ID, False),
        (REGISTERED_ID, "00000000-0000-0000-0000-000000000399", False),
    ],
)
def test_guest_signup_refuses_foreign_or_confirmed_existing_accounts(
    bound_user_id: str | None,
    auth_user_id: str,
    confirmed: bool,
) -> None:
    gateway = MagicMock(spec=SupabaseGateway)
    gateway.private_alpha_email_disabled.return_value = False
    gateway.get_guest_signup_handoff.return_value = _signup_handoff(
        destination_user_id=bound_user_id
    )

    with patch("argus.api.routers.auth.serialized_guest_signup") as serialized:
        serialized.return_value.__enter__.return_value = GuestSignupPrevalidation(
            auth_user_id=auth_user_id,
            auth_user_confirmed=confirmed,
            username_available=True,
        )
        response = _post_guest_signup(gateway)

    assert response.status_code == 409
    assert response.json()["code"] == "account_exists_use_login"
    gateway.signup.assert_not_called()
    gateway.resend_signup_confirmation.assert_not_called()


def test_guest_signup_requires_prepared_cookie_and_old_link_route_is_removed() -> None:
    gateway = MagicMock(spec=SupabaseGateway)
    gateway.private_alpha_email_disabled.return_value = False
    app.dependency_overrides.clear()
    from argus.api.dependencies import current_user

    app.dependency_overrides[current_user] = _guest_dependency
    try:
        with (
            patch.object(api_state, "supabase_gateway", gateway),
            TestClient(app) as client,
        ):
            signup = client.post(
                "/api/v1/auth/guest/signup",
                json={
                    "age_confirmed_at": "2026-01-01T00:00:00Z",
                    "email": "approved@example.com",
                    "password": "strong-password",
                    "captcha_token": "captcha-proof",
                },
            )
            old_link = client.post(
                "/api/v1/auth/guest/link",
                json={
                    "email": "approved@example.com",
                    "password": "strong-password",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert signup.status_code == 400
    assert signup.json()["code"] == "guest_handoff_invalid"
    assert old_link.status_code == 404
    gateway.signup.assert_not_called()
