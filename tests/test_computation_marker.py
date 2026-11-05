"""One marker: metadata.computation is derived from the card and never disagrees."""

from __future__ import annotations

import pytest
from argus.api import state as api_state
from argus.api.main import app
from argus.api.message_store import create_message
from argus.domain.capability_registry import get_tool_catalog
from argus.domain.computation_marker import (
    computation_from_tool_card,
    computation_from_tool_cards,
    symbols_from_arguments,
)
from argus.domain.tool_contracts import ToolCall, ToolOutcome
from faker import Faker
from fastapi.testclient import TestClient

from tests.domain.calculations.support import run_calculation

fake = Faker()

LOAN = {
    "direction": "borrow",
    "currency": "USD",
    "present_value": 200_000,
    "payment": None,
    "future_value": 0,
    "annual_rate_pct": 6,
    "periods": 360,
}


def test_a_calculation_card_declares_its_kind_inputs_and_symbols() -> None:
    card = run_calculation(
        "price_multiple",
        {
            "currency": "USD",
            "symbol": "aapl",
            "price": 150,
            "per_share": 6,
            "multiple": None,
        },
    )
    computation = computation_from_tool_card(card)
    assert computation is not None
    assert computation.kinds == ["price_multiple"]
    assert computation.calculations[0].inputs == card.arguments
    assert computation.symbols == ["AAPL"]
    assert computation_from_tool_cards([card]) == computation


def test_backtest_and_research_cards_declare_no_marker() -> None:
    catalog = get_tool_catalog(include_unavailable=True)
    research = catalog.get("balanced_lookup")
    assert research is not None
    call = ToolCall(tool_name="balanced_lookup", call_id="c", arguments={"request": "x"})
    outcome = ToolOutcome(
        status="unavailable", failure={"code": "research_unavailable", "fields": []}
    )
    card = research.result_card(call=call, outcome=outcome, artifact_id="a")
    assert computation_from_tool_card(card, catalog=catalog) is None
    assert computation_from_tool_cards([], catalog=catalog) is None


def test_symbols_come_only_from_typed_symbol_inputs() -> None:
    assert symbols_from_arguments({"symbol": " msft "}) == ["MSFT"]
    assert symbols_from_arguments(
        {"items": [{"symbol": "a"}, {"symbol": "b"}, {"label": "no symbol"}]}
    ) == ["A", "B"]
    assert symbols_from_arguments({"request": "AAPL P/E"}) == []
    assert (
        len(symbols_from_arguments({"items": [{"symbol": str(i)} for i in range(9)]}))
        == 5
    )


@pytest.fixture
def surface():
    client = TestClient(app)
    client.post("/api/v1/dev/reset")
    owner = client.get("/api/v1/me").json()["user"]["id"]
    conversation = client.post("/api/v1/conversations", json={}).json()["conversation"]
    card = run_calculation("time_value", LOAN).model_copy(
        update={"artifact_id": fake.uuid4()}
    )
    message = create_message(
        user_id=owner,
        conversation_id=conversation["id"],
        role="assistant",
        content="",
        metadata={
            "tool_result_cards": [card.model_dump(mode="json")],
            "computation": computation_from_tool_card(card).model_dump(mode="json"),
        },
    )
    return client, conversation["id"], message, card


def test_recompute_then_decide_stores_the_recomputed_inputs(surface) -> None:
    client, conversation_id, message, card = surface
    recomputed = client.post(
        f"/api/v1/conversations/{conversation_id}/tool-results/{card.artifact_id}/recompute",
        json={
            "message_id": message.id,
            "input_revision": 0,
            "arguments": {"present_value": 150_000},
        },
    )
    assert recomputed.status_code == 200, recomputed.text
    metadata = recomputed.json()["message"]["metadata"]
    revised = metadata["tool_result_cards"][0]
    assert revised["arguments"]["present_value"] == 150_000
    assert revised["presentation"]["answer"]["value"] == pytest.approx(899.33)
    # The marker is the card's arguments, edited input marked as stated.
    assert metadata["computation"]["kind"] == "time_value"
    assert metadata["computation"]["inputs"] == revised["arguments"]
    assert revised["arguments"]["sources"]["present_value"] == {"kind": "user"}

    decided = client.post(
        f"/api/v1/conversations/{conversation_id}/messages/{message.id}/decision",
        json={"decision_state": "promising"},
    )
    assert decided.status_code == 200, decided.text
    stored = decided.json()["decision"]["computation"]
    assert stored["inputs"]["present_value"] == 150_000
    assert stored["inputs"] == revised["arguments"]

    opened = client.get(f"/api/v1/decisions/{decided.json()['decision']['id']}")
    assert opened.status_code == 200
    rerun = opened.json()["reruns"][0]
    assert rerun["status"] == "computed"
    assert rerun["result"]["kind"] == "tool_result"
    assert rerun["result"]["presentation"]["answer"]["value"] == pytest.approx(899.33)
    assert api_state.store.decision_notes


def test_the_marker_reads_the_same_as_the_card_after_a_failed_recompute(surface) -> None:
    client, conversation_id, message, card = surface
    # Zero periods is rejected by the typed model; the route answers 422 and
    # neither the card nor the marker moves.
    rejected = client.post(
        f"/api/v1/conversations/{conversation_id}/tool-results/{card.artifact_id}/recompute",
        json={"message_id": message.id, "input_revision": 0, "arguments": {"periods": 0}},
    )
    assert rejected.status_code == 422
    stored = api_state.store.messages[conversation_id][0].metadata
    assert stored["computation"]["inputs"] == stored["tool_result_cards"][0]["arguments"]

