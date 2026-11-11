from __future__ import annotations

from typing import Any


def mirrored_moving_average_crossover_rule(
    rule: dict[str, Any],
) -> dict[str, Any] | None:
    if str(rule.get("type") or "").lower() != "moving_average_crossover":
        return None
    opposite = dict(rule)
    direction = str(rule.get("direction") or "bullish").lower()
    opposite["direction"] = (
        "bearish"
        if direction in {"bullish", "above", "cross_above", "golden_cross"}
        else "bullish"
    )
    return opposite
