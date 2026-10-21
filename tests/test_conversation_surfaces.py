"""Personal (/chat) and Business (/biz) chat histories stay apart, in memory mode.

The client names a surface and never a space. One person's Personal and
Business conversations appear only on their own surface in Recents, search and
History, and delete-all on one surface leaves the other alone. Another person
sees neither. The artifact routes answer 404 for a Business conversation, and a
Business turn never recalls memory.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import patch

import pytest
from argus.api import state as api_state
from argus.api.business_spaces import business_spaces, configure_business_spaces
from argus.api.chat.memory_recall import memory_recalls_for_turn
from argus.api.dependencies import current_user
from argus.api.guest_access import registered_account_context, store_account_context
from argus.api.main import app
from argus.api.message_store import create_message
from argus.api.personalization_memory import configure_memory_service
from argus.api.schemas import EvidenceArtifact, OnboardingState, User
from argus.domain.business.spaces import InMemorySpaceStore
from argus.memory.service import MemoryService
from fastapi import Request
from fastapi.testclient import TestClient

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
    monkeypatch.setenv("ARGUS_BUSINESS_PILOT_ENABLED", "true")
    monkeypatch.setenv("ARGUS_BUSINESS_CHAT_ENABLED", "true")
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
    create_message(
        user_id=person,
        conversation_id=conversation_id,
        role="user",
        content=f"{title} question",
    )
    return conversation_id


def _listed(client: TestClient, person: str, path: str, **params: str) -> list[str]:
    response = client.get(path, params=params, headers=_as(person))
    assert response.status_code == 200, response.text
    return sorted(
        item.get("conversation_id") or item["id"]
        for item in response.json()["items"]
        if item.get("type", "chat") in {"chat", "conversation"}
    )


def _surfaces(
    client: TestClient, person: str, surfaces: tuple[str, ...] = ("personal", "business")
) -> dict[str, dict[str, list[str]]]:
    return {
        surface: {
            "recents": _listed(client, person, "/api/v1/conversations", surface=surface),
            "search": _listed(
                client, person, "/api/v1/search", q="ledger", surface=surface
            ),
            "history": _listed(client, person, "/api/v1/history", surface=surface),
        }
        for surface in surfaces
    }


def test_one_person_sees_each_chat_only_on_its_own_surface(client: TestClient) -> None:
    _start_space(ALICE)
    personal = _create(client, ALICE, "Household ledger")
    business = _create(client, ALICE, "Shop ledger", surface="business")

    assert _surfaces(client, ALICE) == {
        "personal": {
            "recents": [personal],
            "search": [personal],
            "history": [personal],
        },
        "business": {
            "recents": [business],
            "search": [business],
            "history": [business],
        },
    }
    assert _listed(client, ALICE, "/api/v1/conversations") == [personal]


def test_delete_all_on_one_surface_leaves_the_other(client: TestClient) -> None:
    _start_space(ALICE)
    personal = _create(client, ALICE, "Household ledger")
    business = _create(client, ALICE, "Shop ledger", surface="business")

    cleared = client.delete("/api/v1/conversations", headers=_as(ALICE))
    assert cleared.json() == {"success": True, "deleted_count": 1}
    assert _surfaces(client, ALICE)["business"]["recents"] == [business]
    assert _surfaces(client, ALICE)["personal"]["recents"] == []

    personal_again = _create(client, ALICE, "Household ledger again")
    cleared = client.delete(
        "/api/v1/conversations", params={"surface": "business"}, headers=_as(ALICE)
    )
    assert cleared.json() == {"success": True, "deleted_count": 1}
    assert _surfaces(client, ALICE)["personal"]["recents"] == [personal_again]
    assert _surfaces(client, ALICE)["business"]["recents"] == []
    assert personal != personal_again


def test_another_person_sees_none_of_them(client: TestClient) -> None:
    _start_space(ALICE)
    _start_space(BOB)
    _create(client, ALICE, "Household ledger")
    _create(client, ALICE, "Shop ledger", surface="business")

    empty = {"recents": [], "search": [], "history": []}
    assert _surfaces(client, BOB) == {"personal": empty, "business": empty}


def test_business_surface_needs_the_flag_and_a_started_space(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = (
        ("post", "/api/v1/conversations", {"json": {"surface": "business"}}),
        ("get", "/api/v1/conversations", {"params": {"surface": "business"}}),
        ("get", "/api/v1/search", {"params": {"q": "x", "surface": "business"}}),
        ("get", "/api/v1/history", {"params": {"surface": "business"}}),
        ("delete", "/api/v1/conversations", {"params": {"surface": "business"}}),
    )

    def codes() -> list[tuple[int, str]]:
        answers = []
        for method, path, kwargs in calls:
            response = client.request(method, path, headers=_as(ALICE), **kwargs)
            answers.append((response.status_code, response.json()["code"]))
        return answers

    assert codes() == [(404, "business_space_missing")] * len(calls)
    monkeypatch.delenv("ARGUS_BUSINESS_PILOT_ENABLED")
    _start_space(ALICE)
    assert codes() == [(404, "business_unavailable")] * len(calls)
    personal = client.post("/api/v1/conversations", json={}, headers=_as(ALICE))
    assert personal.status_code == 200
    assert api_state.store.conversation_spaces == {}


def test_a_business_chat_is_kept_after_the_flag_turns_off(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _start_space(ALICE)
    personal = _create(client, ALICE, "Household ledger")
    _create(client, ALICE, "Shop ledger", surface="business")
    monkeypatch.delenv("ARGUS_BUSINESS_PILOT_ENABLED")

    assert _surfaces(client, ALICE, ("personal",))["personal"] == {
        "recents": [personal],
        "search": [personal],
        "history": [personal],
    }


def test_artifact_routes_answer_404_for_a_business_conversation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ARGUS_EVIDENCE_RECEIPT_SHARING_ENABLED", "true")
    _start_space(ALICE)
    business = _create(client, ALICE, "Shop ledger", surface="business")
    personal = _create(client, ALICE, "Household ledger")
    artifacts = {}
    for side, conversation_id in (("business", business), ("personal", personal)):
        artifact = EvidenceArtifact(
            id=f"evidence-{side}",
            idea_id="idea",
            idea_version_id="idea-version",
            source_conversation_id=conversation_id,
            title="Saved result",
            digest="digest",
            payload={},
            created_at=NOW,
            updated_at=NOW,
        )
        api_state.store.evidence_artifacts[artifact.id] = artifact
        api_state.store.evidence_artifact_owners[artifact.id] = ALICE
        artifacts[side] = artifact.id

    def answers(side: str, conversation_id: str) -> list[tuple[int, str | None]]:
        artifact_id = artifacts[side]
        calls = (
            ("post", f"/conversations/{conversation_id}/messages/m-1/decision", {}),
            (
                "post",
                f"/conversations/{conversation_id}/messages/m-1/computation/rerun",
                {},
            ),
            ("post", f"/evidence-artifacts/{artifact_id}/decision", {}),
            ("post", f"/evidence-artifacts/{artifact_id}/public-excerpt", {}),
            ("get", f"/conversations/{conversation_id}/public-excerpt-candidates", None),
            ("post", f"/conversations/{conversation_id}/public-excerpt-preview", {}),
            ("post", f"/conversations/{conversation_id}/public-excerpt", {}),
        )
        found = []
        for method, path, body in calls:
            response = client.request(
                method, "/api/v1" + path, json=body, headers=_as(ALICE)
            )
            found.append((response.status_code, response.json().get("detail")))
        return found

    assert answers("business", business) == [(404, "Conversation not found.")] * 7
    assert (404, "Conversation not found.") not in answers("personal", personal)


def _user_object(person: str) -> User:
    return User(
        id=person,
        email=None,
        username=None,
        display_name=None,
        language="en",
        locale="en-US",
        is_admin=False,
        onboarding=OnboardingState(),
        created_at=NOW,
        updated_at=NOW,
    )


class _CountingMemoryService:
    def __init__(self) -> None:
        self.calls = 0

    def retrieve(self, *args: object, **kwargs: object) -> list[object]:
        self.calls += 1
        return []


def test_a_business_turn_recalls_no_memory(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ARGUS_ENABLE_PERSONALIZATION_MEMORY", "true")
    service = _CountingMemoryService()
    configure_memory_service(cast(MemoryService, service))
    try:
        _start_space(ALICE)
        business = _create(client, ALICE, "Shop ledger", surface="business")
        personal = _create(client, ALICE, "Household ledger")

        def recall(conversation_id: str) -> object:
            return memory_recalls_for_turn(
                user=_user_object(ALICE),
                account=registered_account_context(ALICE),
                conversation_id=conversation_id,
                user_message="what did I decide?",
                memory_opt_out=False,
            )

        assert recall(business) is None
        assert service.calls == 0
        assert recall(personal) is None
        assert service.calls == 1
    finally:
        configure_memory_service(None)


def test_every_conversation_response_names_its_surface(client: TestClient) -> None:
    _start_space(ALICE)
    personal = _create(client, ALICE, "Household ledger")
    business = _create(client, ALICE, "Shop ledger", surface="business")

    def surfaces(surface: str) -> dict[str, str]:
        listed = client.get(
            "/api/v1/conversations", params={"surface": surface}, headers=_as(ALICE)
        ).json()["items"]
        return {item["id"]: item["surface"] for item in listed}

    assert surfaces("personal") == {personal: "personal"}
    assert surfaces("business") == {business: "business"}
    for conversation_id, surface in ((personal, "personal"), (business, "business")):
        messages = client.get(
            f"/api/v1/conversations/{conversation_id}/messages", headers=_as(ALICE)
        )
        assert messages.json()["surface"] == surface
        patched = client.patch(
            f"/api/v1/conversations/{conversation_id}",
            json={"pinned": True},
            headers=_as(ALICE),
        )
        assert patched.json()["conversation"]["surface"] == surface
