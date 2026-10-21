"""Business chat stays off until Business turns have their own tool restrictions.

With ``ARGUS_BUSINESS_CHAT_ENABLED`` off no Business conversation is created and
no turn, continuation or card action runs on one, while reading and deleting
the ones that exist keeps working. Personal chat is untouched.
"""

from __future__ import annotations

import pytest
from argus.api.main import app
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from tests.test_conversation_surfaces import (  # noqa: F401
    ALICE,
    _as,
    _create,
    _start_space,
    client,
)

UNAVAILABLE = (404, "business_chat_unavailable")
ID = "00000000-0000-4000-8000-000000000001"


def _code(response) -> tuple[int, str | None]:  # noqa: ANN001
    return response.status_code, response.json().get("code")


def _turns(
    client: TestClient,  # noqa: F811
    conversation_id: str,
    *,
    with_body_routes: bool = True,
) -> list[tuple[int, str | None]]:
    """Each way a chat turn or card action reaches a conversation. The body
    routes run a turn or a backtest when admitted, so only a refused side
    may be sent them."""

    base = f"/api/v1/conversations/{conversation_id}"
    body_routes = (
        ("/api/v1/chat/stream", {"conversation_id": conversation_id, "message": "hi"}),
        (
            "/api/v1/backtests/run",
            {"conversation_id": conversation_id, "symbols": ["SPY"]},
        ),
    )
    path_routes = (
        (f"{base}/messages/{ID}/continue", None),
        (f"{base}/messages/{ID}/computation/refresh", None),
        (
            f"{base}/tool-results/{ID}/recompute",
            {"message_id": ID, "input_revision": 0, "arguments": {"a": 1}},
        ),
        (f"{base}/confirmations/{ID}/peer-assets", {}),
        (f"{base}/confirmations/{ID}/direct-edit", {}),
    )
    calls = (body_routes if with_body_routes else ()) + path_routes
    return [
        _code(
            client.post(
                path,
                json=body,
                headers={**_as(ALICE), "Idempotency-Key": "business-chat-off"},
            )
        )
        for path, body in calls
    ]


def test_business_chat_off_refuses_every_turn_but_keeps_reading_and_deleting(
    client: TestClient,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _start_space(ALICE)
    business = _create(client, ALICE, "Shop ledger", surface="business")
    personal = _create(client, ALICE, "Household ledger")
    monkeypatch.setenv("ARGUS_BUSINESS_CHAT_ENABLED", "false")

    started = client.post(
        "/api/v1/conversations", json={"surface": "business"}, headers=_as(ALICE)
    )
    assert _code(started) == UNAVAILABLE
    assert _turns(client, business) == [UNAVAILABLE] * 7
    assert UNAVAILABLE not in _turns(client, personal, with_body_routes=False)

    listed = client.get(
        "/api/v1/conversations", params={"surface": "business"}, headers=_as(ALICE)
    )
    assert [item["id"] for item in listed.json()["items"]] == [business]
    messages = client.get(
        f"/api/v1/conversations/{business}/messages", headers=_as(ALICE)
    )
    assert [item["content"] for item in messages.json()["items"]] == [
        "Shop ledger question"
    ]
    assert (
        client.post("/api/v1/conversations", json={}, headers=_as(ALICE)).status_code
        == 200
    )
    removed = client.delete(f"/api/v1/conversations/{business}", headers=_as(ALICE))
    assert removed.status_code == 200, removed.text


def test_business_chat_is_nested_inside_the_pilot(
    client: TestClient,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _start_space(ALICE)
    business = _create(client, ALICE, "Shop ledger", surface="business")
    monkeypatch.delenv("ARGUS_BUSINESS_PILOT_ENABLED")

    started = client.post(
        "/api/v1/conversations", json={"surface": "business"}, headers=_as(ALICE)
    )
    assert _code(started) == (404, "business_unavailable")
    assert _turns(client, business) == [UNAVAILABLE] * 7


def test_every_conversation_write_route_names_its_side() -> None:
    """A new POST under a conversation must declare which side it serves."""
    from argus.api.conversation_surface import (
        require_open_business_chat,
        require_personal_conversation,
    )

    guards = {require_open_business_chat, require_personal_conversation}
    unguarded = [
        route.path
        for route in app.routes
        if isinstance(route, APIRoute)
        and "POST" in route.methods
        and "{conversation_id}" in route.path
        and not guards & {dependency.call for dependency in route.dependant.dependencies}
    ]
    assert unguarded == []


def test_every_route_naming_a_conversation_in_its_body_is_refused_while_off() -> None:
    """Body-keyed writers refuse inline; a new one must join the behavior test."""

    body_keyed = sorted(
        route.path
        for route in app.routes
        if isinstance(route, APIRoute)
        and "POST" in route.methods
        and any(
            "conversation_id" in getattr(param.field_info.annotation, "model_fields", {})
            for param in route.dependant.body_params
        )
    )
    assert body_keyed == ["/api/v1/backtests/run", "/api/v1/chat/stream"]
