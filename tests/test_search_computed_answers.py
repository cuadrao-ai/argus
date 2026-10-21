"""A computed answer gets a dossier beside the run dossier, and counts under its asset."""

from __future__ import annotations

from typing import Any

import pytest
from argus.api import state as api_state
from argus.api.main import app
from argus.api.message_store import create_message
from argus.domain.computation_marker import computation_from_tool_card
from argus.domain.owner_scope import PERSONAL
from argus.domain.store import utcnow
from faker import Faker
from fastapi.testclient import TestClient

from tests.domain.calculations.support import run_calculation

fake = Faker()
APPLE = {
    "currency": "USD",
    "symbol": "AAPL",
    "price": 150,
    "per_share": 6,
    "multiple": None,
}


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/api/v1/dev/reset")
    return client


def _computed_answer(
    client: TestClient,
    conversation_id: str,
    *,
    arguments: dict[str, Any] = APPLE,
    question: str = "Is Apple expensive at this P/E?",
) -> tuple[str, dict[str, Any]]:
    owner = client.get("/api/v1/me").json()["user"]["id"]
    create_message(
        user_id=owner, conversation_id=conversation_id, role="user", content=question
    )
    card = run_calculation("price_multiple", arguments).model_copy(
        update={"artifact_id": fake.uuid4()}
    )
    message = create_message(
        user_id=owner,
        conversation_id=conversation_id,
        role="assistant",
        content="Apple trades at 25 times earnings.",
        metadata={
            "tool_result_cards": [card.model_dump(mode="json")],
            "computation": computation_from_tool_card(card).model_dump(mode="json"),
        },
    )
    return message.id, card.model_dump(mode="json")


def test_search_carries_the_answer_dossier_beside_an_unchanged_run_dossier() -> None:
    client = _client()
    conversation = client.post(
        "/api/v1/conversations", json={"title": "Apple valuation"}
    ).json()["conversation"]
    message_id, card = _computed_answer(client, conversation["id"])

    response = client.get("/api/v1/search", params={"q": "apple"})

    assert response.status_code == 200, response.text
    rows = [item for item in response.json()["items"] if item["type"] == "conversation"]
    assert len(rows) == 1
    item = rows[0]
    assert item["dossier"] is None and item["total_runs"] == 0
    dossier = item["answer_dossier"]
    assert dossier["message_id"] == message_id
    assert dossier["conversation_id"] == conversation["id"]
    assert dossier["asked"] == "Is Apple expensive at this P/E?"
    assert dossier["cards"][0]["tool_name"] == "price_multiple"
    assert dossier["symbols"] == ["AAPL"]
    assert dossier["cards"] == [card]
    assert dossier["decision"] is None
    assert dossier["actions"] == [
        {
            "type": "answer_decision",
            "availability": "available",
            "message_id": message_id,
            "decision_state": None,
            "note": None,
        }
    ]


def test_a_decided_answer_shows_its_decision_and_the_asset_row_counts_the_result() -> (
    None
):
    client = _client()
    conversation = client.post("/api/v1/conversations", json={"title": "Apple"}).json()[
        "conversation"
    ]
    message_id, _ = _computed_answer(client, conversation["id"])
    decided = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages/{message_id}/decision",
        json={"decision_state": "watching", "note": "Wait for earnings."},
    )
    assert decided.status_code == 200, decided.text

    by_symbol = client.get("/api/v1/search", params={"q": "AAPL"})

    assert by_symbol.status_code == 200, by_symbol.text
    rollup = next(
        item for item in by_symbol.json()["items"] if item["type"] == "asset_rollup"
    )
    assert rollup["symbol"] == "AAPL"
    assert rollup["run_count"] == 0
    assert rollup["result_count"] == 1
    assert rollup["decision_counts"] == {
        "promising": 0,
        "watching": 1,
        "rejected": 0,
        "revisit_later": 0,
    }
    response = client.get("/api/v1/search", params={"q": "apple"})
    items = response.json()["items"]
    row = next(item for item in items if item["type"] == "conversation")
    assert row["answer_dossier"]["decision"] == {
        "state": "watching",
        "note": "Wait for earnings.",
        "run_label": None,
    }
    assert row["answer_dossier"]["decision_id"] == decided.json()["decision"]["id"]
    assert row["answer_dossier"]["actions"][0]["decision_state"] == "watching"
    assert "watching" in row["decision_states"]


def test_the_latest_computed_answer_wins_and_a_prefix_resolves_the_asset() -> None:
    client = _client()
    conversation = client.post(
        "/api/v1/conversations", json={"title": "Two answers"}
    ).json()["conversation"]
    _computed_answer(client, conversation["id"])
    later_id, later_card = _computed_answer(
        client,
        conversation["id"],
        arguments={**APPLE, "price": 180},
        question="And at 180?",
    )
    prefix = client.get("/api/v1/search", params={"q": "AAP"}).json()["items"]
    assert (
        next(item for item in prefix if item["type"] == "asset_rollup")["result_count"]
        == 2
    )
    items = client.get("/api/v1/search", params={"q": "180"}).json()["items"]
    row = next(item for item in items if item["type"] == "conversation")
    assert row["answer_dossier"]["message_id"] == later_id
    assert row["answer_dossier"]["asked"] == "And at 180?"
    assert row["answer_dossier"]["cards"][0]["arguments"]["price"] == 180


def test_an_answer_without_a_marker_or_with_a_disagreeing_card_has_no_dossier() -> None:
    client = _client()
    owner = client.get("/api/v1/me").json()["user"]["id"]
    conversation = client.post("/api/v1/conversations", json={"title": "Plain"}).json()[
        "conversation"
    ]
    card = run_calculation("price_multiple", APPLE).model_copy(
        update={"artifact_id": fake.uuid4()}
    )
    create_message(
        user_id=owner,
        conversation_id=conversation["id"],
        role="assistant",
        content="No marker.",
        metadata={"tool_result_cards": [card.model_dump(mode="json")]},
    )
    create_message(
        user_id=owner,
        conversation_id=conversation["id"],
        role="assistant",
        content="Marker disagrees.",
        metadata={
            "tool_result_cards": [card.model_dump(mode="json")],
            "computation": {
                "kind": "price_multiple",
                "inputs": {**card.arguments, "price": 1},
            },
        },
    )
    response = client.get("/api/v1/search", params={"q": "plain"})
    row = next(
        item for item in response.json()["items"] if item["type"] == "conversation"
    )
    assert row["answer_dossier"] is None
    assert not [
        item for item in response.json()["items"] if item["type"] == "asset_rollup"
    ]


def test_recompute_from_search_returns_the_new_result_beside_an_untouched_answer() -> (
    None
):
    client = _client()
    conversation = client.post("/api/v1/conversations", json={}).json()["conversation"]
    message_id, card = _computed_answer(client, conversation["id"])
    path = f"/api/v1/conversations/{conversation['id']}/messages/{message_id}/computation/rerun"

    changed = client.post(path, json={"inputs": {"price": 300}})

    assert changed.status_code == 200, changed.text
    body = changed.json()
    assert body["computation"]["inputs"] == card["arguments"]
    assert body["reruns"][0]["status"] == "computed"
    assert body["reruns"][0]["inputs"]["price"] == 300
    assert body["reruns"][0]["result"]["presentation"]["answer"][
        "value"
    ] == pytest.approx(50.0)
    stored = api_state.store.messages[conversation["id"]][-1].metadata
    assert stored["tool_result_cards"][0]["arguments"]["price"] == 150
    assert stored["computation"]["inputs"]["price"] == 150
    same = client.post(path, json={"inputs": {}})
    assert same.json()["reruns"][0]["result"]["presentation"]["answer"][
        "value"
    ] == pytest.approx(25.0)
    unknown = client.post(path, json={"inputs": {"multiple": 30}})
    assert unknown.status_code == 422
    foreign = client.post(path.replace(message_id, fake.uuid4()), json={"inputs": {}})
    assert foreign.status_code == 404


def test_a_guest_sees_only_its_own_workspace_results() -> None:
    from argus.api.schemas import Conversation
    from argus.api.search_computed import with_computed_results

    client = _client()
    owner = client.get("/api/v1/me").json()["user"]["id"]
    now = utcnow()
    workspace_id = fake.uuid4()
    other_id = fake.uuid4()
    for conversation_id in (workspace_id, other_id):
        api_state.store.conversations[conversation_id] = Conversation(
            id=conversation_id,
            title="Guest",
            created_at=now,
            updated_at=now,
            language="en",
        )
        api_state.store.conversation_owners[conversation_id] = owner
        _computed_answer(client, conversation_id)
    user = api_state.store.get_or_create_dev_user()

    scoped = with_computed_results(
        None, scope=PERSONAL, user=user, query="aapl", guest_conversation_id=workspace_id
    )
    everything = with_computed_results(
        None, scope=PERSONAL, user=user, query="aapl", guest_conversation_id=None
    )

    assert scoped is not None and scoped.result_count == 1
    assert everything is not None and everything.result_count == 2
    assert (
        with_computed_results(
            None, scope=PERSONAL, user=user, query="tsla", guest_conversation_id=None
        )
        is None
    )
