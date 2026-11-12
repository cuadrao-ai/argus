"""Business conversation routes use the existing durable gateway, never memory."""

from __future__ import annotations

import psycopg
from argus.api import state as api_state

from tests.test_conversation_surfaces_postgres import DSN, Rig, pytestmark, rig

_ = rig, pytestmark


def test_create_then_read_uses_the_database_after_memory_is_cleared(rig: Rig) -> None:
    response = rig.client.post(
        "/api/v1/conversations",
        json={"title": "Durable ledger", "surface": "business"},
        headers=rig.alice.headers,
    )
    assert response.status_code == 200, response.text
    conversation_id = response.json()["conversation"]["id"]
    gateway = api_state.supabase_gateway
    assert gateway is not None
    stored = gateway.get_conversation(
        user_id=rig.alice.id, conversation_id=conversation_id
    )
    assert stored is not None and stored.title == "Durable ledger"
    assert conversation_id not in api_state.store.conversations
    with psycopg.connect(DSN) as database:
        assert database.execute(
            "select user_id::text, owner_space_id::text from public.conversations where id = %s",
            (conversation_id,),
        ).fetchone() == (rig.alice.id, rig.alice.space_id)
        database.execute(
            "insert into public.messages (conversation_id, user_id, role, content) "
            "values (%s, %s, 'user', 'A durable ledger message')",
            (conversation_id, rig.alice.id),
        )
    api_state.store.reset()
    for path, params in (
        ("/api/v1/conversations", {"surface": "business"}),
        ("/api/v1/history", {"surface": "business"}),
        ("/api/v1/search", {"surface": "business", "q": "durable"}),
    ):
        page = rig.client.get(path, params=params, headers=rig.alice.headers)
        assert page.status_code == 200, page.text
        assert conversation_id in {
            item.get("conversation_id") or item["id"] for item in page.json()["items"]
        }
    messages = rig.client.get(
        f"/api/v1/conversations/{conversation_id}/messages", headers=rig.alice.headers
    )
    assert messages.status_code == 200, messages.text
    assert [item["content"] for item in messages.json()["items"]] == [
        "A durable ledger message"
    ]
    refused = rig.client.get(
        f"/api/v1/conversations/{conversation_id}/messages", headers=rig.bob.headers
    )
    assert refused.status_code == 404


def test_database_pages_patch_and_delete_preserve_owner_and_message_boundaries(
    rig: Rig,
) -> None:
    conversation_id = rig.alice.business[0]
    for method in ("patch", "delete"):
        refused = rig.client.request(
            method,
            f"/api/v1/conversations/{conversation_id}",
            json={"title": "Not yours"} if method == "patch" else None,
            headers=rig.bob.headers,
        )
        assert refused.status_code == 404
    renamed = rig.client.patch(
        f"/api/v1/conversations/{conversation_id}",
        json={"title": "Renamed ledger", "pinned": True},
        headers=rig.alice.headers,
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["conversation"]["title_source"] == "user_renamed"
    with psycopg.connect(DSN) as database:
        assert database.execute(
            "select title, title_source, pinned from public.conversations where id = %s",
            (conversation_id,),
        ).fetchone() == ("Renamed ledger", "user_renamed", True)
        for content in ("Second saved message", "Third saved message"):
            database.execute(
                "insert into public.messages (conversation_id, user_id, role, content) "
                "values (%s, %s, 'assistant', %s)",
                (conversation_id, rig.alice.id, content),
            )
    seen, cursor = [], None
    for _ in range(4):
        response = rig.client.get(
            f"/api/v1/conversations/{conversation_id}/messages",
            params={"limit": 1, **({"cursor": cursor} if cursor else {})},
            headers=rig.alice.headers,
        )
        assert response.status_code == 200, response.text
        page = response.json()
        seen.extend(item["id"] for item in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert len(seen) == len(set(seen)) == 3
    anchored = rig.client.get(
        f"/api/v1/conversations/{conversation_id}/messages",
        params={"limit": 2, "anchor_message_id": seen[1]},
        headers=rig.alice.headers,
    )
    assert anchored.status_code == 200, anchored.text
    assert [item["id"] for item in anchored.json()["items"]] == seen[1:]
    foreign_anchor = rig.client.get(
        f"/api/v1/conversations/{rig.alice.personal[0]}/messages",
        params={"anchor_message_id": seen[0]},
        headers=rig.alice.headers,
    )
    assert foreign_anchor.status_code == 404
    removed = rig.client.delete(
        f"/api/v1/conversations/{conversation_id}",
        headers=rig.alice.headers,
    )
    assert removed.status_code == 200, removed.text
    missing = rig.client.get(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=rig.alice.headers,
    )
    assert missing.status_code == 404
    gateway = api_state.supabase_gateway
    assert gateway is not None
    stored = gateway.get_conversation(
        user_id=rig.alice.id, conversation_id=conversation_id
    )
    assert stored is not None and stored.deleted_at is not None


def test_database_read_pages_keep_cursors_and_surface_scope(rig: Rig) -> None:
    for path in ("/api/v1/conversations", "/api/v1/history", "/api/v1/search"):
        seen, cursor = [], None
        for _ in range(4):
            page = rig.client.get(
                path,
                params={
                    "surface": "business",
                    "q": "ledger",
                    "limit": 1,
                    **({"cursor": cursor} if cursor else {}),
                },
                headers=rig.alice.headers,
            )
            assert page.status_code == 200, page.text
            body = page.json()
            seen.extend(
                item.get("conversation_id") or item["id"] for item in body["items"]
            )
            cursor = body["next_cursor"]
            if cursor is None:
                break
        assert sorted(seen) == sorted(rig.alice.business)
        personal = rig.client.get(
            path,
            params={"surface": "personal", "q": "ledger"},
            headers=rig.alice.headers,
        )
        assert personal.status_code == 404, personal.text
        invalid = rig.client.get(
            path,
            params={"surface": "business", "q": "ledger", "cursor": "bad"},
            headers=rig.alice.headers,
        )
        assert invalid.status_code == 400, invalid.text
    recall = rig.client.get(
        "/api/v1/search",
        params={"surface": "business", "q": "", "conversation_id": rig.alice.business},
        headers=rig.alice.headers,
    )
    assert recall.status_code == 200, recall.text
    assert [item["id"] for item in recall.json()["items"]] == rig.alice.business
    refused = rig.client.get(
        "/api/v1/search",
        params={"surface": "business", "q": "", "conversation_id": rig.alice.business},
        headers=rig.bob.headers,
    )
    assert refused.status_code == 200 and refused.json()["items"] == []
