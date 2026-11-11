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
