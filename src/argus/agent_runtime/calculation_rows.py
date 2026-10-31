"""The calculation offer under a research answer.

A research answer whose calculation needs figures only the reader knows offers
it as its first row; tapping it asks for those figures and keeps the cited ones.
"""

from __future__ import annotations

from typing import Any

from argus.agent_runtime.next_experiments import (
    NEXT_EXPERIMENTS_ROW_CAP,
    NEXT_EXPERIMENTS_VERSION,
)

CALCULATION_OFFER_KIND = "calculation_offer"
_OFFER_LABEL_KEY = "chat.next_experiments.labels.calculation_offer"
_OFFER_LABELS = {
    "en": "Work it out with your own figures",
    "es-419": "Calcúlalo con tus propios números",
}


def with_calculation_offer(
    rows: dict[str, Any] | None, *, language: str
) -> dict[str, Any]:
    """The offer first among an answer's rows, within the row bound."""
    label = _OFFER_LABELS["es-419" if str(language or "").startswith("es") else "en"]
    offer = {
        "kind": CALCULATION_OFFER_KIND,
        "label": label,
        "label_key": _OFFER_LABEL_KEY,
        "send_text": label,
    }
    offered = [offer, *((rows or {}).get("rows") or [])]
    return {
        **(rows or {"version": NEXT_EXPERIMENTS_VERSION}),
        "rows": offered[:NEXT_EXPERIMENTS_ROW_CAP],
    }
