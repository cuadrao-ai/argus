from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from argus.api import state as api_state
from argus.api.main import app
from argus.api.schemas import Conversation, OnboardingState, User
from argus.domain.guest_workspaces import GuestWorkspace
from argus.domain.owner_scope import PERSONAL
from argus.domain.store import utcnow
from argus.domain.supabase_gateway import SupabaseGateway
from fastapi.testclient import TestClient

USER_ID = "00000000-0000-0000-0000-000000000061"
CONVERSATION_ID = "00000000-0000-0000-0000-000000000062"


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


def _conversation() -> Conversation:
    now = utcnow()
    return Conversation(
        id=CONVERSATION_ID,
        title="Temporary idea",
        title_source="system_default",
        language="en",
        pinned=False,
        archived=False,
        deleted_at=None,
        last_message_preview=None,
        created_at=now,
        updated_at=now,
    )


def _configure_activity_projection(gateway: MagicMock) -> None:
    gateway.reconcile_conversation_activity_turns.return_value = []
    gateway.read_conversation_activity_batch.side_effect = (
        lambda *, user_id, conversation_ids: [
            {
                "conversation_id": conversation_id,
                "sources": [],
                "read_state": None,
            }
            for conversation_id in conversation_ids
        ]
    )


def test_guest_create_conversation_reuses_the_single_bound_conversation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARGUS_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("ARGUS_MOCK_AUTH", "false")
    profile = _profile()
    conversation = _conversation()
    workspace = GuestWorkspace(
        user_id=USER_ID,
        conversation_id=CONVERSATION_ID,
        status="active",
        created_at=profile.created_at,
        expires_at=profile.created_at + timedelta(days=7),
        claimed_by=None,
        claimed_at=None,
        updated_at=profile.created_at,
    )
    gateway = MagicMock(spec=SupabaseGateway)
    gateway.get_auth_user_from_token.return_value = {
        "id": USER_ID,
        "email": None,
        "is_anonymous": True,
    }
    gateway.get_or_create_profile_for_auth_user.return_value = profile
    gateway.get_active_guest_workspace.return_value = workspace
    gateway.get_conversation.return_value = conversation
    gateway.conversation_has_user_message.return_value = False
    _configure_activity_projection(gateway)

    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
        TestClient(app) as client,
    ):
        response = client.post(
            "/api/v1/conversations",
            json={"title": "Ignored second title", "language": "en"},
            headers={"Authorization": "Bearer verified-guest"},
        )

    assert response.status_code == 200
    assert response.json()["conversation"]["id"] == CONVERSATION_ID
    gateway.conversation_has_user_message.assert_called_once_with(
        user_id=USER_ID,
        conversation_id=CONVERSATION_ID,
    )
    gateway.list_messages.assert_not_called()
    gateway.create_conversation.assert_not_called()


def test_guest_direct_durable_conversation_mutations_require_conversion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARGUS_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("ARGUS_MOCK_AUTH", "false")
    profile = _profile()
    conversation = _conversation()
    workspace = GuestWorkspace(
        user_id=USER_ID,
        conversation_id=CONVERSATION_ID,
        status="active",
        created_at=profile.created_at,
        expires_at=profile.created_at + timedelta(days=7),
        claimed_by=None,
        claimed_at=None,
        updated_at=profile.created_at,
    )
    gateway = MagicMock(spec=SupabaseGateway)
    gateway.get_auth_user_from_token.return_value = {
        "id": USER_ID,
        "email": None,
        "is_anonymous": True,
    }
    gateway.get_or_create_profile_for_auth_user.return_value = profile
    gateway.get_active_guest_workspace.return_value = workspace
    gateway.get_conversation.return_value = conversation
    gateway.conversation_has_user_message.return_value = True
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
        TestClient(app) as client,
    ):
        responses = [
            client.post(
                "/api/v1/conversations",
                json={"title": "Second conversation", "language": "en"},
                headers={"Authorization": "Bearer verified-guest"},
            ),
            client.patch(
                f"/api/v1/conversations/{CONVERSATION_ID}",
                json={"title": "Renamed"},
                headers={"Authorization": "Bearer verified-guest"},
            ),
            client.delete(
                f"/api/v1/conversations/{CONVERSATION_ID}",
                headers={"Authorization": "Bearer verified-guest"},
            ),
            client.delete(
                "/api/v1/conversations",
                headers={"Authorization": "Bearer verified-guest"},
            ),
        ]

    assert [response.status_code for response in responses] == [403, 403, 403, 403]
    assert all(
        response.json()["code"] == "account_conversion_required" for response in responses
    )
    gateway.conversation_has_user_message.assert_called_once_with(
        user_id=USER_ID,
        conversation_id=CONVERSATION_ID,
    )
    gateway.list_messages.assert_not_called()
    gateway.create_conversation.assert_not_called()
    gateway.patch_conversation.assert_not_called()
    gateway.soft_delete_conversation.assert_not_called()
    gateway.soft_delete_all_conversations.assert_not_called()


def test_guest_direct_decision_capture_requires_conversion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARGUS_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("ARGUS_MOCK_AUTH", "false")
    profile = _profile()
    workspace = GuestWorkspace(
        user_id=USER_ID,
        conversation_id=CONVERSATION_ID,
        status="active",
        created_at=profile.created_at,
        expires_at=profile.created_at + timedelta(days=7),
        claimed_by=None,
        claimed_at=None,
        updated_at=profile.created_at,
    )
    gateway = MagicMock(spec=SupabaseGateway)
    gateway.get_auth_user_from_token.return_value = {
        "id": USER_ID,
        "email": None,
        "is_anonymous": True,
    }
    gateway.get_or_create_profile_for_auth_user.return_value = profile
    gateway.get_active_guest_workspace.return_value = workspace

    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
        TestClient(app) as client,
    ):
        response = client.post(
            "/api/v1/evidence-artifacts/00000000-0000-0000-0000-000000000065/decision",
            json={"decision_state": "watching", "note": "Guest decision"},
            headers={"Authorization": "Bearer verified-guest"},
        )

    assert response.status_code == 403
    assert response.json()["code"] == "account_conversion_required"


def test_guest_start_over_replaces_the_bound_conversation_in_place(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARGUS_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("ARGUS_MOCK_AUTH", "false")
    profile = _profile()
    replacement = _conversation().model_copy(
        update={"id": "00000000-0000-0000-0000-000000000063"}
    )
    gateway = MagicMock(spec=SupabaseGateway)
    gateway.get_auth_user_from_token.return_value = {
        "id": USER_ID,
        "email": None,
        "is_anonymous": True,
    }
    gateway.get_or_create_profile_for_auth_user.return_value = profile
    gateway.replace_guest_conversation.return_value = replacement
    _configure_activity_projection(gateway)

    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
        TestClient(app) as client,
    ):
        response = client.post(
            "/api/v1/conversations/guest/replace",
            headers={"Authorization": "Bearer verified-guest"},
        )

    assert response.status_code == 200
    assert response.json()["conversation"]["id"] == replacement.id
    gateway.replace_guest_conversation.assert_called_once_with(
        user_id=USER_ID,
        title="New idea",
        title_source="system_default",
        language="en",
    )


def test_history_guest_single_workspace_behavior_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARGUS_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("ARGUS_MOCK_AUTH", "false")
    profile = _profile()
    conversation = _conversation().model_copy(
        update={"last_message_preview": "A truthful preview"}
    )
    workspace = GuestWorkspace(
        user_id=USER_ID,
        conversation_id=CONVERSATION_ID,
        status="active",
        created_at=profile.created_at,
        expires_at=profile.created_at + timedelta(days=7),
        claimed_by=None,
        claimed_at=None,
        updated_at=profile.created_at,
    )
    gateway = MagicMock(spec=SupabaseGateway)
    gateway.get_auth_user_from_token.return_value = {
        "id": USER_ID,
        "email": None,
        "is_anonymous": True,
    }
    gateway.get_or_create_profile_for_auth_user.return_value = profile
    gateway.get_active_guest_workspace.return_value = workspace
    gateway.get_conversation.return_value = conversation
    gateway.read_conversation_preview_messages.return_value = [
        {
            "conversation_id": CONVERSATION_ID,
            "role": "user",
            "content": "A truthful preview",
            "metadata": {},
        }
    ]
    _configure_activity_projection(gateway)

    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
        TestClient(app) as client,
    ):
        response = client.get(
            "/api/v1/history",
            headers={"Authorization": "Bearer verified-guest"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "type": "chat",
                "id": CONVERSATION_ID,
                "title": "Temporary idea",
                "title_source": "system_default",
                "subtitle": "",
                "preview": {
                    "kind": "text",
                    "text": "A truthful preview",
                    "symbols": [],
                    "template": None,
                },
                "pinned": False,
                "created_at": conversation.updated_at.isoformat().replace("+00:00", "Z"),
                "conversation_id": CONVERSATION_ID,
                "expires_at": workspace.expires_at.isoformat().replace("+00:00", "Z"),
                "activity": {
                    "operation": {
                        "status": "idle",
                        "kind": None,
                        "updated_at": None,
                    },
                    "attention": {"status": "none", "cursor": None},
                    "latest_message_id": None,
                },
            }
        ],
        "next_cursor": None,
    }
    gateway.list_history_rows.assert_not_called()
    assert gateway.read_conversation_preview_messages.call_count == 2
    gateway.read_conversation_preview_messages.assert_called_with(
        user_id=USER_ID, conversation_ids=[CONVERSATION_ID]
    )


def test_guest_search_is_limited_to_current_workspace_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARGUS_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("ARGUS_MOCK_AUTH", "false")
    profile = _profile()
    workspace = GuestWorkspace(
        user_id=USER_ID,
        conversation_id=CONVERSATION_ID,
        status="active",
        created_at=profile.created_at,
        expires_at=profile.created_at + timedelta(days=7),
        claimed_by=None,
        claimed_at=None,
        updated_at=profile.created_at,
    )
    gateway = MagicMock(spec=SupabaseGateway)
    gateway.get_auth_user_from_token.return_value = {
        "id": USER_ID,
        "email": None,
        "is_anonymous": True,
    }
    gateway.get_or_create_profile_for_auth_user.return_value = profile
    gateway.get_active_guest_workspace.return_value = workspace
    gateway.search_rows.return_value = {
        "conversations": [
            {
                "id": CONVERSATION_ID,
                "title": "Owned BTC idea",
                "last_message_preview": "BTC result",
                "updated_at": profile.updated_at,
            },
            {
                "id": "00000000-0000-0000-0000-000000000099",
                "title": "Foreign BTC idea",
                "last_message_preview": "BTC leak",
                "updated_at": profile.updated_at,
            },
        ],
        "runs": [
            {
                "id": "00000000-0000-0000-0000-000000000064",
                "conversation_id": CONVERSATION_ID,
                "created_at": profile.updated_at,
                "benchmark_symbol": "BTC",
                "conversation_result_card": {
                    "title": "Owned BTC result",
                    "artifact_type": "backtest",
                },
            },
            {
                "id": "00000000-0000-0000-0000-000000000098",
                "conversation_id": "00000000-0000-0000-0000-000000000099",
                "created_at": profile.updated_at,
                "benchmark_symbol": "BTC",
                "conversation_result_card": {
                    "title": "Foreign BTC result",
                    "artifact_type": "backtest",
                },
            },
        ],
        "strategies": [
            {
                "id": "00000000-0000-0000-0000-000000000065",
                "name": "Guest strategy destination must stay hidden",
                "symbols": ["BTC"],
                "updated_at": profile.updated_at,
            }
        ],
        "collections": [],
        "ideas": [],
        "evidence": [],
        "decisions": [],
    }

    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
        TestClient(app) as client,
    ):
        response = client.get(
            "/api/v1/search?q=BTC&include_ledger_groups=true",
            headers={"Authorization": "Bearer verified-guest"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert [(item["type"], item["id"]) for item in payload["items"]] == [
        ("conversation", CONVERSATION_ID)
    ]
    assert payload["items"][0]["conversation_id"] == CONVERSATION_ID
    assert payload["ledger_groups"] == []
    gateway.search_rows.assert_called_once_with(
        scope=PERSONAL,
        user_id=USER_ID,
        query="btc",
        source_limit=21,
        cursor_updated_at=None,
        cursor_id=None,
        decision_state=None,
        include_ledger_groups=True,
        guest_scope=True,
        guest_conversation_id=CONVERSATION_ID,
    )
