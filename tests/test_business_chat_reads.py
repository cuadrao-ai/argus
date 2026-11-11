"""Business chat reads keep the shapes the web app already parses.

getConversationMessages, receipt follow-up paging, listHistory and searchGlobal
all read these routes. The keys are the ones the base memory handlers return.
"""

from __future__ import annotations

from argus.api.message_store import create_message

from tests.test_conversation_surfaces import (
    ALICE,
    _as,
    _create,
    _start_space,
    client,
)

_ = client


def test_business_messages_history_and_search_match_the_base_shape(client) -> None:
    _start_space(ALICE)
    conversation_id = _create(client, ALICE, "Shop ledger", surface="business")
    create_message(
        user_id=ALICE,
        conversation_id=conversation_id,
        role="assistant",
        content="Anotado.",
    )

    messages = client.get(
        f"/api/v1/conversations/{conversation_id}/messages",
        params={"limit": 1},
        headers=_as(ALICE),
    )
    assert messages.status_code == 200, messages.text
    page = messages.json()
    assert set(page) == {"items", "next_cursor", "surface"}
    assert page["surface"] == "business"
    assert set(page["items"][0]) == {
        "id",
        "conversation_id",
        "role",
        "content",
        "created_at",
        "metadata",
    }
    assert page["next_cursor"]
    follow = client.get(
        f"/api/v1/conversations/{conversation_id}/messages",
        params={"limit": 1, "cursor": page["next_cursor"]},
        headers=_as(ALICE),
    )
    assert follow.status_code == 200, follow.text
    assert follow.json()["next_cursor"] is None
    assert len(follow.json()["items"]) == 1

    history = client.get(
        "/api/v1/history", params={"limit": 50, "surface": "business"}, headers=_as(ALICE)
    )
    assert history.status_code == 200, history.text
    body = history.json()
    assert set(body) == {"items", "next_cursor"}
    assert body["next_cursor"] is None
    item = body["items"][0]
    assert item["type"] == "chat"
    assert item["id"] == conversation_id
    assert set(item) >= {
        "type",
        "id",
        "title",
        "title_source",
        "subtitle",
        "pinned",
        "created_at",
        "conversation_id",
        "expires_at",
        "activity",
        "preview",
    }
    assert set(item["activity"]) == {"operation", "attention", "latest_message_id"}
    assert set(item["preview"]) >= {"kind", "text", "symbols"}

    search = client.get(
        "/api/v1/search",
        params={"q": "ledger", "limit": 20, "surface": "business"},
        headers=_as(ALICE),
    )
    assert search.status_code == 200, search.text
    found = search.json()
    assert set(found) == {"items", "next_cursor", "ledger_groups"}
    assert found["next_cursor"] is None
    assert found["ledger_groups"] is None
    hit = found["items"][0]
    assert hit["type"] == "conversation"
    assert hit["conversation_id"] == conversation_id
    assert set(hit) >= {
        "type",
        "id",
        "title",
        "archived",
        "matched_text",
        "preview",
        "updated_at",
        "conversation_id",
        "match",
        "dossier",
        "total_runs",
        "decided_runs",
    }
    assert set(hit["match"]) >= {"layer", "fragment", "count"}

    activity = client.get(
        f"/api/v1/conversations/{conversation_id}/activity", headers=_as(ALICE)
    )
    assert activity.status_code == 200, activity.text
    assert activity.json()["attention"]["status"] == "none"
    unread = client.patch(
        f"/api/v1/conversations/{conversation_id}/activity",
        json={"action": "mark_unread"},
        headers=_as(ALICE),
    )
    assert unread.status_code == 200, unread.text
    assert unread.json()["attention"]["status"] == "manual_unread"
