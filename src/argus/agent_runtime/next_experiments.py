"""Stage-0 Try next selection: typed, result-aware, capped experiment rows.

The stacked rows are the one Try next surface (`next_experiments` in
docs/API_CONTRACT.md). Selection here is a
deterministic policy over the supported experiment set for the strategy
family that actually ran; smarter layers (telemetry ordering, an LLM
selector) arrive later behind the same contract and may reorder rows but
never mint them."""

from __future__ import annotations

from typing import Any

from argus.agent_runtime.next_experiments_contract import (
    _LABEL_KEY_PREFIX,
    CONTINUITY_NEXT_EXPERIMENT_KINDS,
    NEXT_EXPERIMENT_ACTION_LABELS,
    NEXT_EXPERIMENT_SHORT_LABELS,
    NEXT_EXPERIMENTS_ROW_CAP,
    NEXT_EXPERIMENTS_VERSION,
    continuity_next_experiment_kind,
    continuity_next_experiment_label_key,
    detect_next_experiment_acceptance,
    next_experiment_label_key,
    next_experiment_short_label_key,
    offered_kinds_from_thread_metadata,
)
from argus.agent_runtime.presentation_i18n import runtime_locale
from argus.domain.benchmark_comparison import (
    BenchmarkComparison,
    benchmark_comparison_from_delta,
)
from argus.domain.display_figure import display_figure
from argus.domain.engine_launch.result_facts import structured_next_experiments

# Composing a row set is the backtest-shaped half; the row contract itself is
# general and lives in `next_experiments_contract`. Its names are re-exported
# here so every caller keeps one import path for the whole surface.
__all__ = [
    "CONTINUITY_NEXT_EXPERIMENT_KINDS",
    "NEXT_EXPERIMENTS_ROW_CAP",
    "NEXT_EXPERIMENTS_VERSION",
    "NEXT_EXPERIMENT_ACTION_LABELS",
    "NEXT_EXPERIMENT_SHORT_LABELS",
    "continuity_next_experiment_kind",
    "continuity_next_experiment_label_key",
    "detect_next_experiment_acceptance",
    "next_experiment_label_key",
    "next_experiment_short_label_key",
    "next_experiments_sidecar",
    "offered_kinds_from_thread_metadata",
]

_REFINEMENT_KINDS = frozenset(
    {
        "recurring_monthly_buys",
        "adjust_indicator_thresholds",
        "adjust_signal_periods",
        "adjust_contribution_cadence",
        "supported_rsi_threshold",
        "supported_ma_crossover",
        "supported_rsi_or_ma_rule",
        "compare_buy_and_hold",
    }
)
_EXPLORATION_KINDS = frozenset(
    {"change_date_range", "same_setup_peer_asset", "same_rule_peer_asset"}
)
_DEEP_DRAWDOWN_THRESHOLD_PCT = -15.0

_PEER_ASSETS: dict[str, str] = {
    "AAPL": "MSFT",
    "MSFT": "AAPL",
    "NVDA": "AMD",
    "AMD": "NVDA",
    "GOOGL": "META",
    "META": "GOOGL",
    "AMZN": "AAPL",
    "TSLA": "NVDA",
    "SPY": "QQQ",
    "QQQ": "SPY",
    "COST": "TGT",
    "TGT": "COST",
    "NFLX": "DIS",
    "DIS": "NFLX",
    "BTC": "ETH",
    "ETH": "BTC",
}

_SEND_TEMPLATES: dict[str, dict[str, str]] = {
    "en": {
        "same_setup_peer_asset": (
            "Test the same buy and hold setup on {peer} from {start} to "
            "{end} with ${capital}."
        ),
        "recurring_monthly_buys": (
            "Try monthly recurring buys of {symbol} from {start} to {end} "
            "with ${capital} each month."
        ),
    },
    "es-419": {
        "same_setup_peer_asset": (
            "Probar el mismo enfoque de comprar y mantener con {peer} de "
            "{start} a {end} con ${capital}."
        ),
        "recurring_monthly_buys": (
            "Probar compras mensuales recurrentes de {symbol} de {start} a "
            "{end} con ${capital} cada mes."
        ),
    },
}


def next_experiments_sidecar(
    result_facts: dict[str, Any],
    *,
    benchmark_delta: float | None = None,
    max_drawdown: float | None = None,
    recent_user_messages: list[str] | None = None,
    previously_offered_kinds: list[str] | None = None,
    language: str = "en",
    prebake_probe: Any | None = None,
    source_run_id: str | None = None,
) -> dict[str, Any] | None:
    options = structured_next_experiments(result_facts)
    if not options:
        return None
    # Ran or ignored, a kind from the previous offer is spent (spec §4.3);
    # restraint prefers fewer rows over repeated ones.
    already_asked = _kinds_already_asked(recent_user_messages) | set(
        previously_offered_kinds or []
    )
    # benchmark_delta is the gap shown_benchmark_gap states; the sidecar never
    # derives a comparison of its own.
    comparison = benchmark_comparison_from_delta(benchmark_delta)
    why = _row_reason(
        comparison=comparison,
        benchmark_delta=benchmark_delta,
        max_drawdown=max_drawdown,
    )
    ordered = _ordered_kinds(
        [
            str(option["kind"])
            for option in options
            if str(option["kind"]) not in already_asked
        ],
        lost=comparison.claim == "lagged_benchmark",
        max_drawdown=max_drawdown,
    )
    labels = {str(option["kind"]): str(option["label"]) for option in options}
    english = NEXT_EXPERIMENT_ACTION_LABELS["en"]
    prebake_params = _prebake_params(result_facts)
    rows = []
    for kind in ordered[:NEXT_EXPERIMENTS_ROW_CAP]:
        label_key = next_experiment_label_key(kind)
        short_label = NEXT_EXPERIMENT_SHORT_LABELS["en"].get(kind)
        row: dict[str, Any] = {
            "kind": kind,
            "label": english.get(label_key) or labels[kind],
            "label_key": label_key,
        }
        if short_label:
            row["label_short"] = short_label
            row["label_short_key"] = next_experiment_short_label_key(kind)
        prebaked = _prebaked_row_fields(
            kind,
            params=prebake_params,
            language=language,
            prebake_probe=prebake_probe,
        )
        if prebaked:
            row.update(prebaked)
        if why is not None:
            row["why"] = why
        rows.append(row)
    if not rows:
        return None
    sidecar: dict[str, Any] = {"version": NEXT_EXPERIMENTS_VERSION, "rows": rows}
    if source_run_id:
        # Rows on a message without a result card still name their run, so a
        # continuity row's typed action anchors on the same result (#590).
        sidecar["source_run_id"] = source_run_id
    return sidecar


def _kinds_already_asked(recent_user_messages: list[str] | None) -> set[str]:
    """A row whose label the user already sent this conversation is spent;
    re-offering it is the padding the spec forbids."""
    if not recent_user_messages:
        return set()
    normalized = {
        message.strip().casefold()
        for message in recent_user_messages
        if isinstance(message, str) and message.strip()
    }
    if not normalized:
        return set()
    spent: set[str] = set()
    for labels in NEXT_EXPERIMENT_ACTION_LABELS.values():
        for label_key, label in labels.items():
            if label.strip().casefold() in normalized:
                spent.add(label_key.removeprefix(_LABEL_KEY_PREFIX))
    return spent


def _ordered_kinds(
    kinds: list[str],
    *,
    lost: bool,
    max_drawdown: float | None,
) -> list[str]:
    """Result-aware order: a losing or high-drawdown run leads with
    refinement, a winning run leads with exploration; ties keep the
    family's own order."""
    deep_drawdown = (
        max_drawdown is not None and max_drawdown <= _DEEP_DRAWDOWN_THRESHOLD_PCT
    )
    prefer_refinement = lost or deep_drawdown

    def sort_key(index_kind: tuple[int, str]) -> tuple[int, int]:
        index, kind = index_kind
        refinement = kind in _REFINEMENT_KINDS
        preferred = refinement if prefer_refinement else kind in _EXPLORATION_KINDS
        return (0 if preferred else 1, index)

    return [kind for _, kind in sorted(enumerate(kinds), key=sort_key)]


def _row_reason(
    *,
    comparison: BenchmarkComparison,
    benchmark_delta: float | None,
    max_drawdown: float | None,
) -> dict[str, Any] | None:
    # Params are display figures: rounded once here, printed verbatim by the
    # client with locale separators, the same digits the result card shows.
    if max_drawdown is not None and max_drawdown <= _DEEP_DRAWDOWN_THRESHOLD_PCT:
        return {
            "code": "deep_drawdown",
            "params": {"drawdown": display_figure(max_drawdown)},
        }
    if benchmark_delta is None or comparison.claim not in {
        "beat_benchmark",
        "lagged_benchmark",
    }:
        return None
    code = (
        "beat_benchmark" if comparison.claim == "beat_benchmark" else "lost_to_benchmark"
    )
    return {"code": code, "params": {"points": display_figure(abs(benchmark_delta))}}


def _prebake_params(result_facts: dict[str, Any]) -> dict[str, Any] | None:
    """Accepts both fact shapes: the persisted config_snapshot and the
    engine envelope with resolved_* at the top level."""
    config = result_facts.get("config_snapshot")
    config = config if isinstance(config, dict) else {}
    resolved_params = config.get("resolved_parameters") or result_facts.get(
        "resolved_parameters"
    )
    resolved_params = resolved_params if isinstance(resolved_params, dict) else {}
    resolved_strategy = config.get("resolved_strategy") or result_facts.get(
        "resolved_strategy"
    )
    resolved_strategy = resolved_strategy if isinstance(resolved_strategy, dict) else {}
    template = str(
        config.get("template")
        or config.get("strategy_type")
        or resolved_strategy.get("strategy_type")
        or ""
    )
    if template != "buy_and_hold":
        return None
    symbols = (
        config.get("symbols")
        or result_facts.get("symbols")
        or resolved_strategy.get("asset_universe")
        or ([resolved_strategy["symbol"]] if resolved_strategy.get("symbol") else None)
    )
    symbol = (
        str(symbols[0]).strip().upper() if isinstance(symbols, list) and symbols else ""
    )
    date_range = config.get("date_range") or resolved_params.get("date_range")
    start = end = ""
    if isinstance(date_range, dict):
        start = str(date_range.get("start") or "").strip()
        end = str(date_range.get("end") or "").strip()
    if not start or not end:
        start = str(config.get("start_date") or "").strip()
        end = str(config.get("end_date") or "").strip()
    capital = (
        config.get("initial_capital")
        or config.get("capital_amount")
        or resolved_params.get("capital_amount")
        or resolved_params.get("initial_capital")
    )
    if not symbol or not start or not end or not isinstance(capital, (int, float)):
        return None
    asset_class = str(
        config.get("asset_class") or resolved_strategy.get("asset_class") or "equity"
    )
    return {
        "symbol": symbol,
        "start": start,
        "end": end,
        "capital": int(capital) if float(capital).is_integer() else capital,
        "asset_class": asset_class,
    }


def _prebaked_row_fields(
    kind: str,
    *,
    params: dict[str, Any] | None,
    language: str,
    prebake_probe: Any | None,
) -> dict[str, Any] | None:
    """A prebaked row's tap sends a fully specified ask: nothing is missing,
    so the normal lifecycle answers with the next confirmation card and no
    questions. Prebaking only happens when the grounding chain agrees."""
    if params is None or kind not in {"same_setup_peer_asset", "recurring_monthly_buys"}:
        return None
    templates = _SEND_TEMPLATES[runtime_locale(language)]
    template = templates.get(kind)
    if template is None:
        return None
    fields = dict(params)
    if kind == "same_setup_peer_asset":
        peer = _PEER_ASSETS.get(params["symbol"])
        if not peer or not _peer_is_grounded(
            peer,
            asset_class=params["asset_class"],
            start=params["start"],
            end=params["end"],
            prebake_probe=prebake_probe,
        ):
            return None
        fields["peer"] = peer
        return {"detail": peer, "send_text": template.format(**fields)}
    return {"send_text": template.format(**fields)}


_PREBAKE_PROBE_BUDGET_SECONDS = 2.0


def _peer_is_grounded(
    peer: str,
    *,
    asset_class: str,
    start: str,
    end: str,
    prebake_probe: Any | None,
) -> bool:
    """Result-paints-first: the optional row may never delay the completed
    result, so grounding runs under a hard budget and degrades to the
    generic row when the provider is slow."""

    def _probe() -> bool:
        if prebake_probe is not None:
            return bool(prebake_probe(peer))
        from datetime import date, timedelta

        from argus.agent_runtime.resolution import resolve_asset_candidate
        from argus.domain import market_data

        resolution = resolve_asset_candidate(
            peer,
            field="next_experiments.peer",
            source="llm_extraction",
            asset_class_hint=asset_class,
        )
        resolved = resolution.asset
        if (
            resolution.status != "resolved"
            or resolved is None
            or resolved.canonical_symbol.upper() != peer
            or resolved.asset_class != asset_class
        ):
            return False
        # One owner decides whether a tap gets bars; this probe only adds the
        # window-tail question on top of it.
        if not market_data.tradable_history(peer, asset_class).is_tradable:
            return False
        # Coverage probe over the window's tail; a mid-window gap surfaces
        # at run time through the ordinary coverage recovery.
        end_date = date.fromisoformat(end)
        probe_start = max(date.fromisoformat(start), end_date - timedelta(days=14))
        bars = market_data.fetch_ohlcv(
            symbol=peer,
            asset_class=asset_class,
            start_date=probe_start,
            end_date=end_date,
            timeframe="1D",
        )
        return bars is not None and len(bars) > 0

    from concurrent.futures import ThreadPoolExecutor

    executor = ThreadPoolExecutor(max_workers=1)
    try:
        return bool(executor.submit(_probe).result(timeout=_PREBAKE_PROBE_BUDGET_SECONDS))
    except Exception:
        return False
    finally:
        executor.shutdown(wait=False, cancel_futures=False)
