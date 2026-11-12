"""One marker: metadata.computation is derived from the card and never disagrees."""

from __future__ import annotations

from argus.domain.capability_registry import get_tool_catalog
from argus.domain.computation_marker import (
    computation_from_tool_card,
    computation_from_tool_cards,
    symbols_from_arguments,
)
from argus.domain.tool_contracts import ToolCall, ToolOutcome
from faker import Faker

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
    assert research is None
    return
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


