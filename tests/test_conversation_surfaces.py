"""Business conversations remain scoped; Personal conversation access is retired."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

import pytest
from argus.api import state as api_state
from argus.api.business_spaces import business_spaces, configure_business_spaces
from argus.api.dependencies import current_user
from argus.api.guest_access import registered_account_context, store_account_context
from argus.api.main import app
from argus.api.schemas import OnboardingState, User
from argus.domain.business.spaces import InMemorySpaceStore
from fastapi import Request
from fastapi.testclient import TestClient

from tests.conversation_fixtures import seed_message

ALICE = "00000000-0000-4000-8000-00000000a11c"
BOB = "00000000-0000-4000-8000-0000000000b0"
NOW = datetime(2026, 10, 8, tzinfo=timezone.utc)


def _user(request: Request) -> User:
    person = request.headers["x-test-person"]
    store_account_context(request, registered_account_context(person))
    return User(
        id=person,
        email=f"{person[-4:]}@example.test",
        username=None,
        display_name=None,
        language="en",
        locale="en-US",
        is_admin=False,
        onboarding=OnboardingState(),
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("CUADRAO_BUSINESS_PILOT_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_BUSINESS_CHAT_ENABLED", "true")
    previous_spaces = business_spaces()
    api_state.store.reset()
    app.dependency_overrides[current_user] = _user
    try:
        with (
            patch.object(api_state, "supabase_gateway", None),
            TestClient(app) as test_client,
        ):
            configure_business_spaces(InMemorySpaceStore())
            yield test_client
    finally:
        app.dependency_overrides.clear()
        configure_business_spaces(previous_spaces)
        api_state.store.reset()


def _as(person: str) -> dict[str, str]:
    return {"x-test-person": person}


def _start_space(person: str) -> str:
    spaces = business_spaces()
    assert spaces is not None
    space, _ = spaces.create(person, "Mi negocio")
    return space.id


def _create(client: TestClient, person: str, title: str, surface: str | None = None):
    body: dict[str, Any] = {"title": title}
    if surface is not None:
        body["surface"] = surface
    created = client.post("/api/v1/conversations", json=body, headers=_as(person))
    assert created.status_code == 200, created.text
    conversation_id = created.json()["conversation"]["id"]
    seed_message(
        conversation_id=conversation_id,
        role="user",
        content=f"{title} question",
    )
    return conversation_id


def _listed(client: TestClient, person: str, path: str, **params: str) -> list[str]:
    response = client.get(path, params=params or None, headers=_as(person))
    assert response.status_code == 200, response.text
    return sorted(
        item.get("conversation_id") or item["id"]
        for item in response.json()["items"]
        if item.get("type", "chat") in {"chat", "conversation"}
    )


def _personal_record() -> str:
    from argus.api.schemas import Conversation

    item = Conversation(
        id=api_state.store.new_id(),
        title="Household ledger",
        created_at=NOW,
        updated_at=NOW,
        surface="personal",
    )
    api_state.store.conversations[item.id] = item
    api_state.store.conversation_owners[item.id] = ALICE
    api_state.store.messages[item.id] = []
    return item.id


@pytest.mark.parametrize("path", ["/conversations", "/history", "/search?q=ledger"])
def test_business_is_the_default_and_personal_rows_stay_hidden(client, path):
    _start_space(ALICE)
    personal = _personal_record()
    business = _create(client, ALICE, "Shop ledger", surface="business")
    assert _listed(client, ALICE, "/api/v1" + path) == [business]
    assert personal in api_state.store.conversations


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("POST", "/conversations", {"surface": "personal"}),
        ("GET", "/conversations?surface=personal", None),
        ("DELETE", "/conversations?surface=personal", None),
        ("GET", "/history?surface=personal", None),
        ("GET", "/search?q=ledger&surface=personal", None),
    ],
)
def test_personal_surface_is_retired(client, method, path, body):
    _start_space(ALICE)
    personal = _personal_record()
    response = client.request(method, "/api/v1" + path, json=body, headers=_as(ALICE))
    assert response.status_code == 404, response.text
    assert api_state.store.conversations[personal].deleted_at is None


@pytest.mark.parametrize(
    "method,suffix,body",
    [
        ("GET", "/messages", None),
        ("GET", "/activity", None),
        ("PATCH", "/activity", {"action": "mark_unread"}),
        ("PATCH", "", {"title": "Changed"}),
        ("DELETE", "", None),
        ("POST", "/messages", {"content": "Hello"}),
    ],
)
def test_personal_id_cannot_bypass_retirement(client, method, suffix, body):
    _start_space(ALICE)
    personal = _personal_record()
    response = client.request(
        method,
        f"/api/v1/conversations/{personal}{suffix}",
        json=body,
        headers=_as(ALICE),
    )
    assert response.status_code == 404, response.text
    assert api_state.store.conversations[personal].title == "Household ledger"
    assert api_state.store.conversations[personal].deleted_at is None


def test_default_creation_and_deletion_are_business_only(client):
    _start_space(ALICE)
    personal = _personal_record()
    business = _create(client, ALICE, "Shop ledger")
    assert api_state.store.conversations[business].surface == "business"
    response = client.delete("/api/v1/conversations", headers=_as(ALICE))
    assert response.json() == {"success": True, "deleted_count": 1}
    assert api_state.store.conversations[personal].deleted_at is None


def test_another_person_cannot_read_business_conversations(client):
    _start_space(ALICE)
    _start_space(BOB)
    business = _create(client, ALICE, "Shop ledger", surface="business")
    for path in ("/conversations", "/history", "/search?q=ledger"):
        assert _listed(client, BOB, "/api/v1" + path) == []
    assert (
        client.get(
            f"/api/v1/conversations/{business}/messages", headers=_as(BOB)
        ).status_code
        == 404
    )


def test_business_surface_needs_flag_and_started_space(client, monkeypatch):
    calls = (
        ("POST", "/conversations", {}),
        ("GET", "/conversations", None),
        ("GET", "/search?q=ledger", None),
        ("GET", "/history", None),
        ("DELETE", "/conversations", None),
    )
    for method, path, body in calls:
        response = client.request(method, "/api/v1" + path, json=body, headers=_as(ALICE))
        assert response.status_code == 404
        assert response.json()["code"] == "business_space_missing"
    _start_space(ALICE)
    monkeypatch.delenv("CUADRAO_BUSINESS_PILOT_ENABLED")
    for method, path, body in calls:
        response = client.request(method, "/api/v1" + path, json=body, headers=_as(ALICE))
        assert response.status_code == 404
        assert response.json()["code"] == "business_unavailable"


def test_business_transcript_and_updates_keep_surface(client):
    _start_space(ALICE)
    business = _create(client, ALICE, "Shop ledger", surface="business")
    messages = client.get(
        f"/api/v1/conversations/{business}/messages", headers=_as(ALICE)
    )
    assert messages.json()["surface"] == "business"
    patched = client.patch(
        f"/api/v1/conversations/{business}", json={"pinned": True}, headers=_as(ALICE)
    )
    assert patched.json()["conversation"]["surface"] == "business"


def test_business_record_is_kept_when_business_turns_off(client, monkeypatch):
    _start_space(ALICE)
    business = _create(client, ALICE, "Shop ledger", surface="business")
    monkeypatch.setenv("CUADRAO_BUSINESS_PILOT_ENABLED", "false")
    response = client.get(
        f"/api/v1/conversations/{business}/messages", headers=_as(ALICE)
    )
    assert response.status_code == 404
    assert business in api_state.store.conversations
    assert api_state.store.conversations[business].deleted_at is None


@pytest.mark.parametrize(
    "suffix",
    [
        "/messages/m-1/decision",
        "/messages/m-1/computation/rerun",
        "/public-excerpt-preview",
        "/public-excerpt",
    ],
)
def test_retired_artifact_actions_stay_closed_for_business(client, suffix):
    _start_space(ALICE)
    business = _create(client, ALICE, "Shop ledger", surface="business")
    response = client.post(
        f"/api/v1/conversations/{business}{suffix}", json={}, headers=_as(ALICE)
    )
    assert response.status_code == 404
