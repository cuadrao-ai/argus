from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Literal

from argus.domain.backtesting.date_window import validate_backtest_date_window
from argus.domain.backtesting.rules import validate_rule_spec
from argus.domain.capability_registry import ALLOWED_TEMPLATES
from argus.domain.dca_capital import MAX_STARTING_CAPITAL as MAX_STARTING_CAPITAL
from argus.domain.indicators import normalize_indicator_parameters
from argus.domain.market_data import resolve_asset
from argus.domain.market_data.capabilities import validate_market_data_window
from argus.domain.market_data.new_york_clock import new_york_today
from argus.domain.strategy_capabilities import STRATEGY_CAPABILITIES

AssetClass = Literal["equity", "crypto", "currency_pair"]

# ALLOWED_TEMPLATES is derived from the canonical capability registry (executable
# templates + the signal_strategy execution template); draft templates have no path.
# Re-exported via argus.domain.engine for existing importers.

ALLOWED_TIMEFRAMES = {"1h", "2h", "4h", "6h", "12h", "1D"}

STABLECOINS = {"USDC", "USDT", "DAI", "BUSD", "TUSD"}

# The accepted-value envelope for a runnable configuration. Every layer that
# admits a value the engine will execute reads these names: the run-time
# validator below, the edit resolver's cost gate, the confirm preflight, the
# card's advertised edit constraints, and the capability contract's capital
# range. A card may never promise a run these bounds refuse.
MIN_STARTING_CAPITAL = 10.0
# Slippage above five percent per trade stops modeling anything real; fees
# ride the same ceiling until the founder retunes it.
MAX_FEE_RATE = 0.05
MAX_SLIPPAGE_RATE = 0.05

_COST_RATE_CAPS = {
    "fee_bps": MAX_FEE_RATE * 10000,
    "slippage_bps": MAX_SLIPPAGE_RATE * 10000,
}


@dataclass(frozen=True)
class SymbolAsset:
    symbol: str
    asset_class: AssetClass


def classify_symbol(symbol: str, *, resolve_asset_func=resolve_asset) -> SymbolAsset:
    resolved = resolve_asset_func(symbol)
    return SymbolAsset(symbol=resolved.canonical_symbol, asset_class=resolved.asset_class)


def default_benchmark(asset_class: AssetClass, symbols: list[str] | None = None) -> str:
    if asset_class == "equity":
        return "SPY"
    if asset_class == "currency_pair":
        return symbols[0] if symbols else "EURUSD"
    return "BTC"


def normalize_timeframe(timeframe: str | None) -> str:
    if timeframe is None:
        return "1D"
    normalized = timeframe.strip().lower()
    mapping = {
        "1d": "1D",
        "1day": "1D",
        "1h": "1h",
        "1hour": "1h",
        "2h": "2h",
        "2hour": "2h",
        "4h": "4h",
        "4hour": "4h",
        "6h": "6h",
        "6hour": "6h",
        "12h": "12h",
        "12hour": "12h",
    }
    if normalized not in mapping:
        raise ValueError("unsupported_timeframe")
    return mapping[normalized]


def _to_date(value: str | date | datetime) -> date:
    if isinstance(value, str):
        return date.fromisoformat(value)
    if isinstance(value, datetime):
        return value.date()
    return value


def _vbt_freq(timeframe: str) -> str:
    mapping = {
        "1D": "1D",
        "1h": "1h",
        "2h": "2h",
        "4h": "4h",
        "6h": "6h",
        "12h": "12h",
    }
    return mapping[timeframe]


def _execution_realism_feature_enabled() -> bool:
    # On by default; the env var is a kill switch. Costs stay opt-in per idea,
    # so runs without stated costs remain idealized either way.
    return os.getenv("ARGUS_ENABLE_EXECUTION_REALISM", "").strip().lower() not in {
        "false",
        "0",
        "off",
        "no",
    }


def _coerce_execution_realism_enabled(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _coerce_execution_realism_bps(source: dict[str, Any], key: str) -> float:
    try:
        value = float(source.get(key, 0.0))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid_execution_realism_{key}") from exc
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"invalid_execution_realism_{key}")
    if value > _COST_RATE_CAPS[key]:
        raise ValueError(f"invalid_execution_realism_{key}")
    return value


def _normalize_execution_realism(raw: Any) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    enabled = _coerce_execution_realism_enabled(source.get("enabled", False))
    if not enabled:
        return {
            "enabled": False,
            "fee_bps": 0.0,
            "slippage_bps": 0.0,
        }
    return {
        "enabled": True,
        "fee_bps": _coerce_execution_realism_bps(source, "fee_bps"),
        "slippage_bps": _coerce_execution_realism_bps(source, "slippage_bps"),
    }


def _validate_config_capital(config: dict[str, Any]) -> None:
    """One capital gate. A DCA run's floor is its plan, not the bankroll band.

    The bankroll band answers "is this a fundable one-time position", which a
    recurring plan seeded at $0 is not; the plan's own rules answer it instead.
    """
    from argus.domain.dca_capital import dca_capital_plan_from_config

    if config["template"] == "dca_accumulation":
        dca_capital_plan_from_config(config)
        return
    if (
        not MIN_STARTING_CAPITAL
        <= float(config["starting_capital"])
        <= MAX_STARTING_CAPITAL
    ):
        raise ValueError("invalid_starting_capital")


def normalize_backtest_config(
    payload: dict[str, Any],
    *,
    classify_symbol_func=classify_symbol,
    default_benchmark_func=default_benchmark,
) -> dict[str, Any]:
    today = new_york_today()
    end_default = today - timedelta(days=1)
    end = _to_date(payload.get("end_date") or end_default)
    start = _to_date(payload.get("start_date") or (end - timedelta(days=365)))
    requested_asset_class = payload.get("asset_class")
    classified = [classify_symbol_func(s) for s in payload["symbols"]]

    actual_classes = {c.asset_class for c in classified}
    if len(actual_classes) > 1:
        raise ValueError("mixed_asset_not_supported")

    inferred_class = next(iter(actual_classes)) if actual_classes else "equity"
    asset_class = requested_asset_class or inferred_class

    if asset_class != inferred_class:
        raise ValueError("asset_class_conflict")

    symbols = [c.symbol for c in classified]
    timeframe = normalize_timeframe(payload.get("timeframe"))

    benchmark_input = payload.get("benchmark_symbol")
    if benchmark_input:
        benchmark_asset = classify_symbol_func(benchmark_input)
        if benchmark_asset.asset_class != asset_class:
            raise ValueError("invalid_benchmark_symbol")
        benchmark_symbol = benchmark_asset.symbol
    else:
        benchmark_symbol = default_benchmark_func(asset_class, symbols)

    config = {
        "template": payload["template"],
        "asset_class": asset_class,
        "symbols": symbols,
        "timeframe": timeframe,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "side": payload.get("side") or "long",
        # A stated amount, zero included, reaches the capital gate; only an
        # omitted one takes the default.
        "starting_capital": 1000
        if payload.get("starting_capital") is None
        else payload["starting_capital"],
        "allocation_method": payload.get("allocation_method") or "equal_weight",
        "benchmark_symbol": benchmark_symbol,
        "parameters": payload.get("parameters") or {},
    }
    if _execution_realism_feature_enabled():
        config["_execution_realism"] = _normalize_execution_realism(
            payload.get("_execution_realism")
        )

    if config["template"] == "dca_accumulation":
        from argus.domain.dca_capital import (
            build_dca_capital_plan,
            dca_capital_config_fields,
        )

        cadence = (payload.get("parameters") or {}).get("dca_cadence") or "weekly"
        config["parameters"]["dca_cadence"] = cadence.lower()
        # This request shape has one money field, and for DCA it has always
        # meant the per-period contribution; the seed enters through the
        # launch path's declared plan instead.
        plan = build_dca_capital_plan(
            starting_capital=0.0,
            contribution=config.pop("starting_capital"),
            period=config["parameters"]["dca_cadence"],
        )
        config.update(dca_capital_config_fields(plan))

    return config


def validate_backtest_config(config: dict[str, Any]) -> None:
    if config["template"] not in ALLOWED_TEMPLATES:
        raise ValueError("unsupported_template")
    if config["side"] != "long":
        raise ValueError("unsupported_side")
    if config["allocation_method"] != "equal_weight":
        raise ValueError("unsupported_allocation_method")
    _validate_config_capital(config)
    if len(config["symbols"]) < 1 or len(config["symbols"]) > 5:
        raise ValueError("invalid_symbol_count")
    if config["timeframe"] not in ALLOWED_TIMEFRAMES:
        raise ValueError("unsupported_timeframe")

    start = date.fromisoformat(config["start_date"])
    end = date.fromisoformat(config["end_date"])
    validate_backtest_date_window(start=start, end=end)
    validate_market_data_window(
        asset_class=config["asset_class"],
        timeframe=config["timeframe"],
        start_date=start,
        end_date=end,
    )

    if any(symbol in STABLECOINS for symbol in config["symbols"]):
        raise ValueError("stablecoin_not_supported")

    # Registry-driven parameter validation (Task 10)
    params = dict(config.get("parameters") or {})
    template_name = config["template"]
    if template_name == "rsi_mean_reversion":
        rule_spec = params.pop("rule_spec", None)
        params = normalize_indicator_parameters(
            str(params.get("indicator") or "rsi"),
            params,
        )
        if rule_spec is not None:
            validate_rule_spec(rule_spec)
            params["rule_spec"] = rule_spec
        config["parameters"] = params
    if template_name == "signal_strategy":
        validate_rule_spec(params.get("rule_spec"))
        config["parameters"] = params
        return
    capability = STRATEGY_CAPABILITIES[template_name]

    allowed_params = set(capability.parameters.keys()) | {"rule_spec"}
    unknown = set(params.keys()) - allowed_params
    if unknown:
        raise ValueError("unsupported_parameters")

    for key, value in params.items():
        if key == "rule_spec":
            continue
        spec = capability.parameters[key]
        if spec.allowed_values and value not in spec.allowed_values:
            raise ValueError(f"unsupported_parameter_value_{key}")
