from __future__ import annotations

from typing import Any

from argus.domain.crossover_mirror import (
    mirrored_moving_average_crossover_rule as _opposite_moving_average_crossover_rule,
)

from .models import RuleSpec
from .validation import validate_rule_spec


def rule_spec_from_moving_average_crossover_rules(
    *,
    entry_rule: dict[str, Any] | None,
    exit_rule: dict[str, Any] | None,
) -> RuleSpec | None:
    if not entry_rule:
        return None
    exit_rule = exit_rule or _opposite_moving_average_crossover_rule(entry_rule)
    if not exit_rule:
        return None
    rule_spec: RuleSpec = {
        "entry": {"conditions": [_moving_average_crossover_condition(entry_rule)]},
        "exit": {"conditions": [_moving_average_crossover_condition(exit_rule)]},
    }
    validate_rule_spec(rule_spec)
    return rule_spec


def rule_spec_from_signal_rule(rule: dict[str, Any] | None) -> RuleSpec | None:
    if not rule:
        return None
    signal_type = str(rule.get("type") or "").lower()
    if signal_type == "macd_crossover":
        return _macd_crossover_rule_spec(rule)
    return None


def _moving_average_crossover_condition(rule: dict[str, Any]) -> dict[str, Any]:
    if str(rule.get("type") or "").lower() != "moving_average_crossover":
        raise ValueError("missing_rule_group")

    direction = str(rule.get("direction") or "bullish").lower()
    if direction in {"bullish", "above", "cross_above", "golden_cross"}:
        operator = "cross_above"
    elif direction in {"bearish", "below", "cross_below", "death_cross"}:
        operator = "cross_below"
    else:
        raise ValueError("unsupported_rule_operator")

    return {
        "left": {
            "kind": "indicator",
            "key": str(rule.get("fast_indicator") or "sma"),
            "period": int(rule.get("fast_period") or 20),
        },
        "operator": operator,
        "right": {
            "kind": "indicator",
            "key": str(rule.get("slow_indicator") or "sma"),
            "period": int(rule.get("slow_period") or 50),
        },
    }


def _macd_crossover_rule_spec(rule: dict[str, Any]) -> RuleSpec:
    direction = str(rule.get("direction") or "bullish").lower()
    if direction in {"bullish", "above", "cross_above"}:
        entry_operator = "cross_above"
        exit_operator = "cross_below"
    elif direction in {"bearish", "below", "cross_below"}:
        entry_operator = "cross_below"
        exit_operator = "cross_above"
    else:
        raise ValueError("unsupported_rule_operator")

    rule_spec: RuleSpec = {
        "entry": {
            "conditions": [
                {
                    "left": _macd_ref(output="macd", rule=rule),
                    "operator": entry_operator,
                    "right": _macd_ref(output="signal", rule=rule),
                }
            ]
        },
        "exit": {
            "conditions": [
                {
                    "left": _macd_ref(output="macd", rule=rule),
                    "operator": exit_operator,
                    "right": _macd_ref(output="signal", rule=rule),
                }
            ]
        },
    }
    validate_rule_spec(rule_spec)
    return rule_spec


def _macd_ref(*, output: str, rule: dict[str, Any]) -> dict[str, Any]:
    parameters = {
        "fast": int(rule.get("fast_period") or rule.get("fast") or 12),
        "slow": int(rule.get("slow_period") or rule.get("slow") or 26),
        "signal": int(rule.get("signal_period") or rule.get("signal") or 9),
    }
    return {
        "kind": "indicator",
        "key": "macd",
        "output": output,
        "parameters": parameters,
    }
