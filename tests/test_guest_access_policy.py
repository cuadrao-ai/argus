from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from argus.api import state as api_state
from argus.api.guest_access import (
    account_context,
    guest_access_enabled,
    public_account_access_enabled,
)
from argus.api.main import app
from argus.api.schemas import OnboardingState, User
from argus.domain.guest_workspaces import GuestWorkspace
from argus.domain.store import utcnow
from argus.domain.supabase_gateway import SupabaseGateway
from fastapi.testclient import TestClient

client = TestClient(app)
USER_ID = "00000000-0000-0000-0000-000000000031"
CONVERSATION_ID = "00000000-0000-0000-0000-000000000032"


def _profile(*, email: str | None) -> User:
    now = utcnow()
    return User(
        id=USER_ID,
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
    created_at = utcnow()
    return GuestWorkspace(
        user_id=USER_ID,
        conversation_id=CONVERSATION_ID,
        status="active",
        created_at=created_at,
        expires_at=created_at + timedelta(days=7),
        claimed_by=None,
        claimed_at=None,
        updated_at=created_at,
    )


@pytest.fixture(autouse=True)
def _clear_flags(monkeypatch: pytest.MonkeyPatch):
    for name in (
        "CUADRAO_GUEST_ACCESS_ENABLED",
        "CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED",
        "NEXT_PUBLIC_GUEST_ACCESS_ENABLED",
        "NEXT_PUBLIC_MOCK_AUTH",
        "CUADRAO_MOCK_AUTH",
    ):
        monkeypatch.delenv(name, raising=False)


def test_guest_access_defaults_on_while_public_account_access_defaults_off() -> None:
    assert guest_access_enabled() is True
    assert public_account_access_enabled() is False


def test_explicit_server_guest_kill_switch_disables_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_ENABLED", "false")

    assert guest_access_enabled() is False


def test_explicit_client_server_guest_flag_mismatch_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_GUEST_ACCESS_ENABLED", "false")

    assert guest_access_enabled() is False


def test_verified_anonymous_auth_truth_owns_guest_status_and_capabilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_GUEST_ACCESS_ENABLED", "true")
    gateway = MagicMock(spec=SupabaseGateway)
    profile = _profile(email=None)
    workspace = _workspace()
    gateway.get_auth_user_from_token.return_value = {
        "id": USER_ID,
        "email": None,
        "is_anonymous": True,
        "user_metadata": {"is_anonymous": False},
    }
    gateway.get_or_create_profile_for_auth_user.return_value = profile
    gateway.get_user.return_value = profile
    gateway.get_active_guest_workspace.return_value = workspace

    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
    ):
        response = client.get(
            "/api/v1/me",
            headers={"Authorization": "Bearer verified-guest-token"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["account_kind"] == "guest"
    assert payload["user"]["email"] is None
    assert "avatar_theme" not in payload["user"]
    assert payload["guest"] == {
        "expires_at": workspace.expires_at.isoformat().replace("+00:00", "Z"),
        "conversation_id": CONVERSATION_ID,
        "conversation_limit": 1,
        "simulation_limit": 2,
        "feedback_limit": 5,
    }
    assert payload["public_account_access_enabled"] is False
    assert payload["capabilities"] == {
        "can_create_additional_conversation": False,
        "can_manage_conversation": False,
        "can_save_decision": False,
        "can_manage_account": False,
        "can_use_omnisearch": True,
        "can_search_current_workspace": True,
        "can_use_grounded_discovery": True,
        "can_submit_feedback": True,
    }
    gateway.private_alpha_email_allowed.assert_not_called()


def test_registered_auth_truth_ignores_editable_anonymous_metadata() -> None:
    gateway = MagicMock(spec=SupabaseGateway)
    profile = _profile(email="member@example.com")
    gateway.get_auth_user_from_token.return_value = {
        "id": USER_ID,
        "email": "member@example.com",
        "is_anonymous": False,
        "user_metadata": {"is_anonymous": True},
    }
    gateway.private_alpha_email_allowed.return_value = True
    gateway.get_or_create_profile_for_auth_user.return_value = profile
    gateway.get_user.return_value = profile

    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
        patch("argus.api.routers.profile._apple_identity", return_value=None) as identity,
    ):
        response = client.get(
            "/api/v1/me",
            headers={"Authorization": "Bearer verified-member-token"},
        )

    identity.assert_called_once()
    assert identity.call_args.args[1] == USER_ID
    assert response.status_code == 200
    assert response.json()["account_kind"] == "registered"
    assert response.json()["guest"] is None
    capabilities = response.json()["capabilities"]
    # Both classes can discover; guests are metered, not blocked. Reporting
    # False told guests discovery was unavailable while it worked.
    assert capabilities["can_use_grounded_discovery"] is True
    assert all(capabilities.values())


def test_account_context_requires_current_user_to_establish_verified_truth() -> None:
    request = MagicMock()
    request.state = MagicMock(spec=[])

    with pytest.raises(RuntimeError, match="not established"):
        account_context(request)


def test_persisted_message_limit_handoff_still_claims() -> None:
    # No client creates message_limit any more, but a handoff persisted by an
    # earlier bundle can carry it; the claim path re-validates the stored
    # action after the RPC consumed the handoff, so it must still parse.
    from argus.api.schemas import GuestPendingAction

    action = GuestPendingAction.model_validate(
        {
            "reason": "message_limit",
            "conversation_id": "00000000-0000-0000-0000-000000000101",
            "action_id": "message-11",
        }
    )

    assert action.reason == "message_limit"
    assert action.artifact_id is None
