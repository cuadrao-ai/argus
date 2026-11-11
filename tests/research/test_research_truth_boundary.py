"""The truth boundary, with the same standing as the S10 memory lock.

Research informs the reader; Argus providers execute the simulation. These
locks prove no finance_search number can reach a backtest:

1. A research stage patch may only carry prose, sidecars, and rows; it can
   never write strategy, confirmation, or execution state.
2. A test launched from a research answer re-grounds through Argus market
   data: a sentinel price planted in the provider packet appears nowhere in
   the confirmation payload, whose figures come from the provider fixture.
3. The research domain package never imports the engine or backtest stack,
   and the engine-launch stack never imports research (source-level scan,
   same mechanism as tests/test_spine_guardrails.py).
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest
from argus.agent_runtime import research_answer as ra
from argus.agent_runtime import research_grounded as grounded
from argus.agent_runtime.research_basket import peer_added_confirmation_preparation
from argus.agent_runtime.stages.interpret_types import StructuredInterpretation
from argus.agent_runtime.state.models import RunState, StrategySummary, UserState
from argus.domain.research.perplexity_agent import PerplexityAgentClient

from tests.money_assertions import _assert_no_money_properties
from tests.research.conftest import RecordingTransport, agent_response

REPO_ROOT = Path(__file__).resolve().parents[2]

SENTINEL_PRICE = "987654.32"


def _assert_no_price_in_text(payload: object) -> None:
    if isinstance(payload, dict):
        for value in payload.values():
            _assert_no_price_in_text(value)
    elif isinstance(payload, list | tuple):
        for value in payload:
            _assert_no_price_in_text(value)
    elif isinstance(payload, str):
        assert re.search(rf"(?<![\w.]){re.escape(SENTINEL_PRICE)}(?!\w)", payload) is None


@pytest.mark.parametrize("field", ["send_text", "label"])
@pytest.mark.parametrize("punctuation", ["", "."])
def test_research_price_check_rejects_a_price_in_nested_text(
    field: str, punctuation: str
) -> None:
    with pytest.raises(AssertionError):
        _assert_no_price_in_text(
            {"rows": [{field: f"Test buying AAPL at ${SENTINEL_PRICE}{punctuation}"}]}
        )


@pytest.mark.parametrize("text", ["hash987654.32abc", "987654.321", "1987654.32"])
def test_research_price_check_ignores_longer_values(text: str) -> None:
    _assert_no_price_in_text({"rows": [{"send_text": text}]})


# The full set of keys a research turn may write. Anything outside this set,
# especially pending_strategy / confirmation_payload / execute state, is a
# truth-boundary breach. Peers ride the research sidecar; the transcript is
# their only cross-turn home. The absorbed find operation adds the discovery
# sidecar pair and typed recovery: still prose, sidecars, and rows only.
ALLOWED_RESEARCH_PATCH_KEYS = {
    "assistant_response",
    "research",
    "research_job_request",
    "next_experiments",
    "next_steps",
    "discovery",
    "discovery_usage",
    "recovery",
}


def _interpretation() -> StructuredInterpretation:
    return StructuredInterpretation(
        intent="unsupported_or_out_of_scope",
        task_relation="new_task",
        user_goal_summary="question",
        semantic_turn_act="educational_question",
        requires_clarification=False,
        candidate_strategy_draft=StrategySummary(),
    )


def _run_with_sentinel(monkeypatch: pytest.MonkeyPatch):
    transport = RecordingTransport(
        [
            agent_response(
                text=f"Netflix is trading at ${SENTINEL_PRICE} right now.",
                tickers=["NFLX"],
                lookup_rows=[("Microsoft", "MSFT", "Microsoft Corporation")],
            )
        ]
    )
    monkeypatch.setattr(
        grounded, "_client", lambda: PerplexityAgentClient("k", transport=transport)
    )
    state = RunState.new(
        current_user_message="What is Netflix at?", recent_thread_history=[]
    )
    return asyncio.run(
        ra.research_answer_stage_result(
            interpretation=_interpretation().model_copy(
                update={
                    "research_query": ra.ResearchQueryExtraction(
                        question_kind="live_quote", symbols=["NFLX"]
                    )
                }
            ),
            state=state,
            user=UserState(user_id="tb", language_preference="en"),
        )
    )


def test_research_patch_writes_no_strategy_or_execution_state(monkeypatch) -> None:
    result = _run_with_sentinel(monkeypatch)
    assert result is not None
    assert set(result.stage_patch.keys()) <= ALLOWED_RESEARCH_PATCH_KEYS
    # The decision carries an empty draft: research never shapes a strategy.
    assert result.decision.candidate_strategy_draft == StrategySummary()


def test_research_launched_test_regrounds_in_argus_providers(monkeypatch) -> None:
    result = _run_with_sentinel(monkeypatch)
    assert result is not None
    # The sentinel is quoted to the reader (informing is encouraged)...
    assert SENTINEL_PRICE in result.stage_patch["assistant_response"]

    # ...but the runnable ask carries symbols and a window, never a figure.
    rows = result.stage_patch["next_experiments"]["rows"]
    for row in rows:
        _assert_no_money_properties(row, SENTINEL_PRICE)
        _assert_no_price_in_text(row)

    # Growing a real confirmation with the researched peer re-validates
    # through provider-backed preflight; no packet number can enter it.
    source_payload = {
        "strategy": {
            "strategy_type": "buy_and_hold",
            "asset_universe": ["NFLX"],
            "asset_class": "equity",
            "timeframe": "1D",
            "date_range": {"start": "2023-01-02", "end": "2023-06-30"},
            "sizing_mode": "capital_amount",
            "capital_amount": 10000,
        },
        "optional_parameters": {},
        "launch_payload": {
            "strategy_type": "buy_and_hold",
            "symbol": "NFLX",
            "symbols": ["NFLX"],
            "asset_class": "equity",
            "timeframe": "1D",
            "date_range": {"start": "2023-01-02", "end": "2023-06-30"},
            "sizing_mode": "capital_amount",
            "capital_amount": 10000,
            "parameters": {},
            "risk_rules": [],
            "benchmark_symbol": "SPY",
            "language": "en",
        },
    }
    peers = result.stage_patch["research"]["peers"]
    assert peers and peers[0]["symbol"] == "MSFT"
    preparation = peer_added_confirmation_preparation(
        source_payload, added=peers, language="en"
    )
    assert preparation.confirmation_payload is not None
    _assert_no_money_properties(preparation.confirmation_payload, SENTINEL_PRICE)
    _assert_no_price_in_text(preparation.confirmation_payload)
    assert preparation.confirmation_payload["strategy"]["asset_universe"] == [
        "NFLX",
        "MSFT",
    ]
    # Coverage truth was recomputed from Argus's own provider stack.
    assert "coverage_preflight" in preparation.confirmation_payload["launch_payload"]


RESEARCH_SOURCES = [
    REPO_ROOT / "src" / "argus" / "domain" / "research",
    REPO_ROOT / "src" / "argus" / "agent_runtime" / "research_answer.py",
    REPO_ROOT / "src" / "argus" / "agent_runtime" / "research_grounded.py",
    REPO_ROOT / "src" / "argus" / "agent_runtime" / "research_find.py",
    REPO_ROOT / "src" / "argus" / "agent_runtime" / "research_rows.py",
]
# Simulation entry points research code must never touch. fetch_price_series
# is deliberately allowed: quoting Argus's own data to the reader is the
# honest degradation path, not a boundary breach.
FORBIDDEN_IN_RESEARCH = (
    "run_backtest",
    "backtest_service",
    "engine_launch",
    "execute_stage",
    "BacktestTool",
    "fetch_ohlcv",
)


def _python_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    return sorted(target.rglob("*.py"))


@pytest.mark.parametrize("symbol", FORBIDDEN_IN_RESEARCH)
def test_research_sources_never_touch_simulation_entry_points(symbol: str) -> None:
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for target in RESEARCH_SOURCES
        for path in _python_files(target)
        if symbol in path.read_text(encoding="utf-8")
    ]
    assert not offenders, (
        f"research code references simulation entry point {symbol!r}: {offenders}; "
        "research informs, Argus providers execute (truth boundary)"
    )


def test_engine_launch_stack_never_imports_research() -> None:
    engine_roots = [
        REPO_ROOT / "src" / "argus" / "domain" / "engine_launch",
        REPO_ROOT / "src" / "argus" / "domain" / "backtesting",
        REPO_ROOT / "src" / "argus" / "api" / "backtest_service.py",
    ]
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for root in engine_roots
        if root.exists()
        for path in _python_files(root)
        if "argus.domain.research" in path.read_text(encoding="utf-8")
        or "research_answer" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, (
        f"simulation code imports research surfaces: {offenders}; the engine "
        "must be unable to see finance_search output by construction"
    )
