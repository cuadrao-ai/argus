"""The one marker a computed answer carries, derived from its tool cards.

``metadata.computation`` and the cards can never disagree because nothing
writes the marker by hand: every writer, the chat turn and the recompute
route alike, derives it here from every card the declarations produced, in
order. A decision saved on the answer stores exactly these inputs.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from argus.api.decision_contract import (
    MAX_COMPUTATION_CALCULATIONS,
    DecisionCalculation,
    DecisionComputation,
)
from argus.domain.calculations import is_free_calculation
from argus.domain.calculations._shared import SYMBOL_FIELD
from argus.domain.tool_contracts import ToolResultCard
from argus.domain.tool_declaration import ToolCatalog

MAX_MARKER_SYMBOLS = 5


def computation_from_tool_card(
    card: ToolResultCard, *, catalog: ToolCatalog | None = None
) -> DecisionComputation | None:
    """The marker one card declares on its own, or ``None``."""
    return computation_from_tool_cards([card], catalog=catalog)


def computation_from_tool_cards(
    cards: Iterable[ToolResultCard], *, catalog: ToolCatalog | None = None
) -> DecisionComputation | None:
    """One marker per answer: every card that is a free calculation, in order.

    A backtest card derives its computation from its evidence artifact and a
    research card has no kernel, so neither is a calculation here.
    """
    if catalog is None:
        from argus.domain.personal_tool_catalog import personal_tool_catalog

        catalog = personal_tool_catalog(include_unavailable=True)
    declared = [
        card for card in cards if _calculation(card, catalog=catalog) is not None
    ][:MAX_COMPUTATION_CALCULATIONS]
    if not declared:
        return None
    symbols: list[str] = []
    for card in declared:
        for symbol in symbols_from_arguments(card.arguments):
            if symbol not in symbols and len(symbols) < MAX_MARKER_SYMBOLS:
                symbols.append(symbol)
    return DecisionComputation(
        calculations=[
            DecisionCalculation(kind=card.tool_name, inputs=dict(card.arguments))
            for card in declared
        ],
        symbols=symbols,
    )


def _calculation(card: ToolResultCard, *, catalog: ToolCatalog) -> str | None:
    declaration = catalog.get(card.tool_name)
    if declaration is None or not is_free_calculation(declaration):
        return None
    if (declaration.card.card_type, declaration.card.version) != (
        card.card_type,
        card.card_version,
    ):
        return None
    return card.tool_name


def symbols_from_arguments(arguments: Mapping[str, Any]) -> list[str]:
    """The assets a calculation is about, from its typed ``symbol`` inputs."""
    found: list[str] = []

    def add(value: object) -> None:
        if isinstance(value, str) and value.strip():
            symbol = value.strip().upper()
            if symbol not in found and len(found) < MAX_MARKER_SYMBOLS:
                found.append(symbol)

    add(arguments.get(SYMBOL_FIELD))
    items = arguments.get("items")
    if isinstance(items, list):
        for item in items:
            if isinstance(item, Mapping):
                add(item.get(SYMBOL_FIELD))
    return found
