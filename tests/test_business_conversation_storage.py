"""Configured durable storage must never fall back to the memory store."""

from __future__ import annotations

import pytest
from argus.api import state as api_state

from tests.test_conversation_surfaces import ALICE, _as, _create, _start_space, client

_ = client


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("post", "/conversations", {"surface": "business"}),
        ("get", "/conversations?surface=business", None),
        ("delete", "/conversations?surface=business", None),
        ("get", "/conversations/{id}/messages", None),
        ("patch", "/conversations/{id}", {"title": "Should not change"}),
        ("delete", "/conversations/{id}", None),
        ("get", "/history?surface=business", None),
        ("get", "/search?surface=business&q=ledger", None),
    ],
)
def test_unavailable_durable_store_refuses_instead_of_using_memory(
    client, monkeypatch: pytest.MonkeyPatch, method: str, path: str, payload: dict | None
) -> None:
    _start_space(ALICE)
    conversation_id = _create(client, ALICE, "Saved ledger", surface="business")
    before = api_state.store.conversations.copy()
    monkeypatch.setattr(api_state, "PERSISTENCE_MODE", "supabase")
    monkeypatch.setenv("ARGUS_DEV_MEMORY_FALLBACK", "true")
    response = client.request(
        method,
        "/api/v1" + path.format(id=conversation_id),
        json=payload,
        headers=_as(ALICE),
    )
    assert response.status_code == 503, response.text
    assert api_state.store.conversations == before
