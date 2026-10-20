from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from argus.api import state as api_state
from argus.api.guest_access import guest_account_context, store_account_context
from argus.api.main import app
from argus.api.routers import auth as auth_router
from argus.api.schemas import OnboardingState, User
from argus.domain.guest_workspaces import GuestWorkspace
from argus.domain.store import utcnow
from argus.domain.supabase_gateway import SupabaseGateway
from argus.domain.supabase_signup import SupabaseSignupMixin
from argus.domain.username_signup import GuestSignupPrevalidation
from fastapi import Request
from fastapi.testclient import TestClient

GUEST_ID = "00000000-0000-0000-0000-000000000311"
REGISTERED_ID = "00000000-0000-0000-0000-000000000312"
CONVERSATION_ID = "00000000-0000-0000-0000-000000000313"
HANDOFF_ID = "00000000-0000-0000-0000-000000000314"
_OMIT_AGE = object()


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
def _guest_signup_environment(monkeypatch: pytest.MonkeyPatch):
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


def _signup_handoff(*, destination_user_id: str | None) -> dict[str, object]:
    return {
        "id": HANDOFF_ID,
        "source_user_id": GUEST_ID,
        "destination_user_id": destination_user_id,
        "source_conversation_id": CONVERSATION_ID,
        "pending_action": {
            "reason": "keep_history",
            "conversation_id": CONVERSATION_ID,
            "action_id": "signup-age",
        },
        "handoff_kind": "new_account_signup",
        "status": "pending",
        "expires_at": utcnow() + timedelta(days=7),
        "proof": "b" * 64,
    }


def _signup_auth_user() -> dict[str, object]:
    return {
        "id": REGISTERED_ID,
        "email": "approved@example.com",
        "is_anonymous": False,
        "email_confirmed_at": None,
        "identities": [{"provider": "email"}],
    }


class _ProfileAgeTable:
    def __init__(self, row: dict[str, object]) -> None:
        self.row = row
        self._payload: dict[str, object] | None = None
        self._user_id: str | None = None

    def table(self, name: str) -> "_ProfileAgeTable":
        assert name == "profiles"
        return self

    def update(self, payload: dict[str, object]) -> "_ProfileAgeTable":
        self._payload = payload
        return self

    def eq(self, column: str, value: str) -> "_ProfileAgeTable":
        assert column == "id"
        self._user_id = value
        return self

    def is_(self, column: str, value: str) -> "_ProfileAgeTable":
        assert column == "age_confirmed_at"
        assert value == "null"
        return self

    def execute(self) -> MagicMock:
        assert self._user_id == self.row["id"]
        assert self._payload is not None
        if self.row["age_confirmed_at"] is None:
            self.row["age_confirmed_at"] = self._payload["age_confirmed_at"]
        return MagicMock()


def _post_guest_signup(gateway: MagicMock, *, age_confirmed_at: object) -> object:
    from argus.api.dependencies import current_user

    app.dependency_overrides[current_user] = _guest_dependency
    payload = {
        "email": "approved@example.com",
        "password": "strong-password",
        "captcha_token": "captcha-proof",
        "display_name": "Alex",
        "language": "es-419",
    }
    if age_confirmed_at is not _OMIT_AGE:
        payload["age_confirmed_at"] = age_confirmed_at
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
                json=payload,
                headers={"Authorization": "Bearer guest-token"},
            )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("age_sent", [True, False])
def test_guest_signup_stores_the_profile_age_through_the_handoff(age_sent: bool) -> None:
    instant = datetime(2026, 1, 1, tzinfo=timezone.utc)
    profile_row = {"id": REGISTERED_ID, "age_confirmed_at": None}
    writer = SupabaseSignupMixin.__new__(SupabaseSignupMixin)
    writer.client = _ProfileAgeTable(profile_row)
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
    gateway.record_age_confirmation.side_effect = writer.record_age_confirmation
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
        response = _post_guest_signup(
            gateway,
            age_confirmed_at=instant.isoformat() if age_sent else _OMIT_AGE,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["id"] == REGISTERED_ID
    assert body["user"]["id"] != GUEST_ID
    assert body["session"]["access_token"] == "registered-access-token"
    assert body["guest_claim"]["conversation_id"] == CONVERSATION_ID
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
    if age_sent:
        assert profile_row["age_confirmed_at"] == instant.isoformat()
        gateway.record_age_confirmation.assert_called_once_with(REGISTERED_ID, instant)
    else:
        assert profile_row["age_confirmed_at"] is None
        gateway.record_age_confirmation.assert_not_called()
