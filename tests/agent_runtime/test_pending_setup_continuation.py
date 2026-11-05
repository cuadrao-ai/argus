"""A reply to the runtime's own question keeps every fact the user stated before.

Recorded 2026-09-10: after a transport error, the fallback read of the second
turn carried no asset and no dates, and the runtime asked for both again even
though the pending setup already held them. The runtime asked the question, so
the reply continues that setup whatever label the interpreter put on it, and a
question asks only for what is actually missing.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from argus.agent_runtime.interpreter.shared import (
    PENDING_REPLY_ASSUMED_REASON,
    repaired_turn_act,
)
from argus.agent_runtime.llm_interpreter_types import (
    LLMInterpretationResponse,
    LLMStrategyDraft,
)
from argus.agent_runtime.stages.interpret import (
    StructuredInterpretation,
    interpret_stage,
)
from argus.agent_runtime.stages.interpret_types import InterpretationRequest
from argus.agent_runtime.state.models import (
    RunState,
    StrategySummary,
    TaskSnapshot,
    UserState,
)

DATE_RANGE = {"start": "2024-01-02", "end": "2024-12-31"}
COSTS = {"fee_rate": 0.001, "slippage": 0.0005}
COST_PROVENANCE = {"fee_rate": "explicit_user", "slippage": "explicit_user"}

REPLIES = {
    "en": (
        "Use $1,000 as starting capital only. There is no contribution cap. Add "
        "$100 monthly after the initial investment. Keep the dates, SPY benchmark, "
        "10 bps fee and 5 bps slippage."
    ),
    "es-419": (
        "Usa $1,000 solo como capital inicial. No hay tope de aportes. Agrega $100 "
        "cada mes después de la inversión inicial. Mantén las fechas, el benchmark "
        "SPY, 10 pb de comisión y 5 pb de slippage."
    ),
}

# The previous turn awaited the user without naming one field, which is the
# shape of an unsupported-recovery question (the recorded turn) and of any
# multi-field question.
AWAITING_REPLY_WITHOUT_FIELD = {
    "last_stage_outcome": "await_user_reply",
    "response_intent": {
        "kind": "unsupported_recovery",
        "semantic_needs": ["simplification_choice"],
        "requested_fields": [],
    },
}
AWAITING_APPROVAL = {"last_stage_outcome": "await_approval"}


def _pending(family: str) -> StrategySummary:
    if family == "dca_accumulation":
        return StrategySummary(
            strategy_type="dca_accumulation",
            strategy_thesis="Monthly DCA into AAPL with a seed.",
            asset_universe=["AAPL"],
            asset_class="equity",
            cadence="monthly",
            date_range=dict(DATE_RANGE),
            capital_amount=100.0,
            comparison_baseline="SPY",
            extra_parameters={
                "recurring_contribution": 100.0,
                "recurring_cadence": "monthly",
                "initial_capital": 1000.0,
                **COSTS,
                "field_provenance": {
                    "capital_amount": "recurring_contribution",
                    "recurring_contribution": "explicit_user",
                    "initial_capital": "explicit_user",
                    "cadence": "explicit_user",
                    **COST_PROVENANCE,
                },
            },
        )
    if family == "buy_and_hold":
        return StrategySummary(
            strategy_type="buy_and_hold",
            strategy_thesis="Buy and hold AAPL.",
            asset_universe=["AAPL"],
            asset_class="equity",
            date_range=dict(DATE_RANGE),
            capital_amount=10000.0,
            comparison_baseline="SPY",
            extra_parameters={
                **COSTS,
                "field_provenance": {
                    "capital_amount": "starting_capital",
                    **COST_PROVENANCE,
                },
            },
        )
    return StrategySummary(
        strategy_type="indicator_threshold",
        strategy_thesis="Buy AAPL when RSI is oversold.",
        asset_universe=["AAPL"],
        asset_class="equity",
        date_range=dict(DATE_RANGE),
        capital_amount=10000.0,
        comparison_baseline="SPY",
        entry_logic="Buy when RSI(14) drops to 30 or below",
        exit_logic="Sell when RSI(14) rises to 70 or above",
        extra_parameters={
            "indicator": "rsi",
            "indicator_parameters": {
                "indicator": "rsi",
                "indicator_period": 14,
                "entry_threshold": 30,
                "exit_threshold": 70,
            },
            **COSTS,
            "field_provenance": {
                "capital_amount": "starting_capital",
                **COST_PROVENANCE,
            },
        },
    )


def _reply_draft(pending: StrategySummary, dropped: str) -> StrategySummary:
    """The interpreter's read of the reply, missing what the model did not restate."""

    draft = pending.model_copy(deep=True)
    extra = dict(draft.extra_parameters)
    provenance = dict(extra.get("field_provenance") or {})
    if dropped in {"asset", "asset_and_dates"}:
        draft.asset_universe = []
        draft.asset_class = None
    if dropped in {"dates", "asset_and_dates"}:
        draft.date_range = None
    if dropped == "money":
        draft.capital_amount = None
        for key in ("recurring_contribution", "initial_capital", "capital_amount"):
            extra.pop(key, None)
            provenance.pop(key, None)
    if dropped == "cadence":
        draft.cadence = None
        extra.pop("recurring_cadence", None)
        provenance.pop("cadence", None)
    if dropped == "benchmark":
        draft.comparison_baseline = None
    if dropped == "costs":
        for key in COSTS:
            extra.pop(key, None)
            provenance.pop(key, None)
    if dropped == "rule":
        draft.entry_logic = None
        draft.exit_logic = None
        extra.pop("indicator", None)
        extra.pop("indicator_parameters", None)
    extra["field_provenance"] = provenance
    draft.extra_parameters = extra
    return draft


class _Interpreter:
    def __init__(self, response: StructuredInterpretation) -> None:
        self.response = response
        self.last_status = "unused"

    def __call__(self, request: Any) -> StructuredInterpretation:
        self.last_status = "used"
        return self.response


def _run(
    *,
    message: str,
    language: str,
    pending: StrategySummary,
    response: StructuredInterpretation,
    thread_metadata: dict[str, Any],
):
    return interpret_stage(
        state=RunState.new(current_user_message=message, recent_thread_history=[]),
        user=UserState(user_id="u1", language_preference=language),
        latest_task_snapshot=TaskSnapshot(
            latest_task_type="strategy_drafting",
            completed=False,
            pending_strategy_summary=pending,
        ),
        selected_thread_metadata=thread_metadata,
        structured_interpreter=_Interpreter(response),
    )


def _assert_pending_facts_survived(
    strategy: StrategySummary, pending: StrategySummary
) -> None:
    assert strategy.asset_universe == pending.asset_universe
    assert strategy.date_range == pending.date_range
    assert strategy.capital_amount == pending.capital_amount
    assert strategy.comparison_baseline == pending.comparison_baseline
    assert strategy.cadence == pending.cadence
    for key in ("fee_rate", "slippage", "recurring_contribution", "initial_capital"):
        assert strategy.extra_parameters.get(key) == pending.extra_parameters.get(
            key
        ), key
    if pending.strategy_type == "indicator_threshold":
        assert strategy.extra_parameters["indicator_parameters"]["entry_threshold"] == 30
        assert strategy.extra_parameters["indicator_parameters"]["exit_threshold"] == 70


DROPPED_BY_FAMILY = {
    "dca_accumulation": [
        "asset",
        "dates",
        "asset_and_dates",
        "money",
        "cadence",
        "benchmark",
        "costs",
    ],
    "buy_and_hold": ["asset", "dates", "asset_and_dates", "money", "benchmark", "costs"],
    "indicator_threshold": [
        "asset",
        "dates",
        "asset_and_dates",
        "money",
        "benchmark",
        "costs",
        "rule",
    ],
}


@pytest.mark.parametrize("language", sorted(REPLIES))
@pytest.mark.parametrize(
    ("semantic_turn_act", "task_relation"),
    [("answer_pending_need", "continue"), ("new_idea", "continue")],
)
@pytest.mark.parametrize(
    ("family", "dropped"),
    [
        (family, dropped)
        for family, dropped_fields in DROPPED_BY_FAMILY.items()
        for dropped in dropped_fields
    ],
)
def test_reply_to_runtime_question_keeps_every_earlier_fact(
    family: str,
    dropped: str,
    semantic_turn_act: str,
    task_relation: str,
    language: str,
) -> None:
    pending = _pending(family)
    reply = _reply_draft(pending, dropped)
    response = StructuredInterpretation(
        intent="strategy_drafting",
        task_relation=task_relation,
        requires_clarification=dropped in {"asset", "dates", "asset_and_dates"},
        user_goal_summary="Continue the pending setup.",
        candidate_strategy_draft=reply,
        missing_required_fields=(
            {"asset": ["asset_universe"], "dates": ["date_range"]}.get(
                dropped,
                ["asset_universe", "date_range"] if dropped == "asset_and_dates" else [],
            )
        ),
        semantic_turn_act=semantic_turn_act,
    )

    result = _run(
        message=REPLIES[language],
        language=language,
        pending=pending,
        response=response,
        thread_metadata=dict(AWAITING_REPLY_WITHOUT_FIELD),
    )

    assert result.outcome == "ready_for_confirmation", result.decision.reason_codes
    assert result.decision.missing_required_fields == []
    _assert_pending_facts_survived(result.decision.candidate_strategy_draft, pending)
    if semantic_turn_act == "new_idea":
        # The runtime kept the setup a mixed read called new; that is recorded.
        assert "pending_setup_continuation_merged" in result.decision.reason_codes


def test_reply_while_a_card_awaits_approval_keeps_the_card_facts() -> None:
    pending = _pending("dca_accumulation")
    response = StructuredInterpretation(
        intent="strategy_drafting",
        task_relation="continue",
        requires_clarification=True,
        user_goal_summary="Restate the money only.",
        candidate_strategy_draft=_reply_draft(pending, "asset_and_dates"),
        missing_required_fields=["asset_universe", "date_range"],
        semantic_turn_act="answer_pending_need",
    )

    result = _run(
        message=REPLIES["en"],
        language="en",
        pending=pending,
        response=response,
        thread_metadata=dict(AWAITING_APPROVAL),
    )

    assert result.outcome == "ready_for_confirmation"
    assert result.decision.missing_required_fields == []
    _assert_pending_facts_survived(result.decision.candidate_strategy_draft, pending)


def test_a_new_idea_about_another_asset_does_not_inherit_the_pending_setup() -> None:
    pending = _pending("dca_accumulation")
    response = StructuredInterpretation(
        intent="backtest_execution",
        task_relation="new_task",
        requires_clarification=False,
        user_goal_summary="Buy and hold NVDA in 2023 with $2,000.",
        candidate_strategy_draft=StrategySummary(
            strategy_type="buy_and_hold",
            strategy_thesis="Buy and hold NVDA in 2023.",
            asset_universe=["NVDA"],
            asset_class="equity",
            date_range={"start": "2023-01-03", "end": "2023-12-29"},
            capital_amount=2000.0,
            extra_parameters={"field_provenance": {"capital_amount": "starting_capital"}},
        ),
        semantic_turn_act="new_idea",
    )

    result = _run(
        message="new idea: buy and hold NVDA in 2023 with $2,000",
        language="en",
        pending=pending,
        response=response,
        thread_metadata=dict(AWAITING_REPLY_WITHOUT_FIELD),
    )

    strategy = result.decision.candidate_strategy_draft
    assert strategy.asset_universe == ["NVDA"]
    assert strategy.strategy_type == "buy_and_hold"
    assert strategy.capital_amount == 2000.0
    assert strategy.cadence is None
    assert "fee_rate" not in strategy.extra_parameters
    assert "pending_setup_continuation_merged" not in result.decision.reason_codes


# --- The recorded two turns, replayed through the real workflow --------------

TURN_1 = (
    "Test monthly dollar-cost averaging in AAPL from January 2, 2024 through "
    "December 31, 2024. Start with $1,000 of starting capital, then contribute "
    "$100 every month. The $1,000 is starting capital, not a total contribution "
    "cap. Compare with SPY. Model a 10 basis point fee and 5 basis points "
    "slippage per trade."
)


class _ScriptedProvider:
    """Answers each structured call from a per-schema queue; the last entry repeats."""

    def __init__(self, entries: dict[str, list[Any]]) -> None:
        self.entries = {key: list(value) for key, value in entries.items()}
        self.calls: list[str] = []

    async def __call__(self, *, schema_model: Any, schema_name: str, **_: Any) -> Any:
        self.calls.append(schema_name)
        queue = self.entries.get(schema_name)
        if not queue:
            return None
        entry = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(entry, Exception):
            raise entry
        return schema_model.model_validate(entry)


def _mentions(*mentions: tuple[str, str]) -> dict[str, Any]:
    return {
        "all_traded_asset_mentions_included": True,
        "asset_mentions": [
            {"raw_text": raw, "role": role, "mention_kind": "ticker", "confidence": 0.9}
            for raw, role in mentions
        ],
    }


def _recorded_turn_1() -> dict[str, list[Any]]:
    return {
        "LLMAssetMentionExtraction": [
            _mentions(("AAPL", "traded_asset"), ("SPY", "benchmark"))
        ],
        "LLMInterpretationResponse": [
            {
                "intent": "strategy_drafting",
                "task_relation": "new_task",
                "requires_clarification": False,
                "user_goal_summary": TURN_1,
                "semantic_turn_act": "new_idea",
                "confidence": 0.95,
                "candidate_strategy_draft": {
                    "raw_user_phrasing": TURN_1,
                    "language": "en",
                    "strategy_type": "dca_accumulation",
                    "asset_universe": ["AAPL"],
                    "asset_class": "equity",
                    "cadence": "monthly",
                    "date_range": dict(DATE_RANGE),
                    "date_range_intent": {"kind": "explicit_range", **DATE_RANGE},
                    "initial_capital": 1000,
                    "recurring_contribution": 100,
                    "comparison_baseline": "SPY",
                    "field_provenance": {
                        "asset_universe": "explicit_user",
                        "date_range": "explicit_user",
                        "initial_capital": "explicit_user",
                        "recurring_contribution": "explicit_user",
                        "cadence": "explicit_user",
                        "comparison_baseline": "explicit_user",
                    },
                    "extra_parameters": dict(COSTS),
                },
            }
        ],
        "StatedRunFieldFidelityAudit": [
            {
                "capital_amount": 1000,
                "recurring_contribution_amount": 100,
                "cadence": "monthly",
                "date_range": dict(DATE_RANGE),
                "comparison_baseline": "SPY",
                "fee": {"rate": 0.001, "evidence_span": "10 basis point fee"},
                "slippage": {"rate": 0.0005, "evidence_span": "5 basis points slippage"},
                "confidence": 0.8,
            }
        ],
        # The recorded read: the audit typed the seed as a budget.
        "DcaContractAudit": [
            {
                "is_recurring_buy_request": True,
                "recurring_contribution_amount": 100,
                "cadence": "monthly",
                "total_budget_amount": 1000,
                "total_budget_source": "starting_capital",
                "confidence": 0.95,
            }
        ],
        "DcaContributionRoleAudit": [
            {
                "recurring_contribution_explicit": True,
                "total_budget_not_recurring": True,
                "confidence": 0.9,
            }
        ],
        "AssetGroundingAudit": [{"grounded_symbols": ["AAPL"], "confidence": 0.9}],
    }


def _recorded_turn_2() -> dict[str, list[Any]]:
    fallback = {
        "intent": "strategy_drafting",
        "task_relation": "continue",
        "requires_clarification": False,
        "user_goal_summary": (
            "Run the monthly DCA in AAPL from January 2, 2024 through December 31, "
            "2024 with $1,000 starting capital and $100 monthly buys."
        ),
        "semantic_turn_act": "answer_pending_need",
        "confidence": 0.9,
        "candidate_strategy_draft": {
            "raw_user_phrasing": REPLIES["en"],
            "language": "en",
            "strategy_type": "dca_accumulation",
            "cadence": "monthly",
            "initial_capital": 1000,
            "recurring_contribution": 100,
            "comparison_baseline": "SPY",
            "field_provenance": {
                "initial_capital": "explicit_user",
                "recurring_contribution": "explicit_user",
                "cadence": "explicit_user",
                "comparison_baseline": "explicit_user",
            },
            "extra_parameters": dict(COSTS),
        },
    }
    return {
        "LLMAssetMentionExtraction": [_mentions(("SPY", "benchmark"))],
        "LLMInterpretationResponse": [httpx.ReadTimeout("transport error"), fallback],
        "FocusedStrategyExtraction": [
            {
                "is_testable_strategy": True,
                "requires_clarification": True,
                "user_goal_summary": "Monthly DCA with a $1,000 seed and $100 monthly buys.",
                "strategy_type": "dca_accumulation",
                "asset_universe": [],
                "date_range": None,
                "capital_amount": 1000,
                "recurring_contribution": 100,
                "cadence": "monthly",
                "comparison_baseline": "SPY",
                "missing_required_fields": ["asset_universe", "date_range"],
                "confidence": 0.9,
            }
        ],
        "FocusedDateWindowExtraction": [{"has_date_window": False, "confidence": 0.9}],
        "StatedRunFieldFidelityAudit": [
            {
                "capital_amount": 1000,
                "recurring_contribution_amount": 100,
                "cadence": "monthly",
                "comparison_baseline": "SPY",
                "fee": {"rate": 0.001, "evidence_span": "10 bps fee"},
                "slippage": {"rate": 0.0005, "evidence_span": "5 bps slippage"},
                "confidence": 0.8,
            }
        ],
        "DcaContractAudit": [
            {
                "is_recurring_buy_request": True,
                "recurring_contribution_amount": 100,
                "cadence": "monthly",
                "confidence": 0.95,
            }
        ],
        "DcaContributionRoleAudit": [
            {
                "recurring_contribution_explicit": True,
                "total_budget_not_recurring": False,
                "confidence": 0.9,
            }
        ],
        "AssetGroundingAudit": [{"grounded_symbols": [], "confidence": 0.9}],
        "PendingResponseOptionSelectionAudit": [
            {"is_selection": False, "confidence": 0.9}
        ],
    }


def _install_provider(
    monkeypatch: pytest.MonkeyPatch, provider: _ScriptedProvider
) -> None:
    import argus.agent_runtime.artifact_edit_planner as artifact_edit_planner
    import argus.agent_runtime.llm_clarifier as llm_clarifier
    import argus.agent_runtime.llm_interpreter as llm_interpreter
    import argus.agent_runtime.signal_rule_repair as signal_rule_repair

    for module in (llm_interpreter, artifact_edit_planner, signal_rule_repair):
        monkeypatch.setattr(module, "invoke_openrouter_json_schema", provider)

    async def _clarify(self: Any, request: Any) -> str:
        return "Which direction should we go?"

    monkeypatch.setattr(
        llm_clarifier.OpenRouterClarificationGenerator, "ainvoke", _clarify
    )


@pytest.mark.asyncio
async def test_recorded_two_turns_reach_the_card_with_every_fact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.agent_runtime.runtime import run_agent_turn
    from argus.agent_runtime.stages import confirm as confirm_module
    from argus.agent_runtime.turn_execution import turn_execution_scope
    from argus.api.state import (
        build_agent_runtime_checkpointer,
        build_agent_runtime_workflow,
    )

    monkeypatch.setattr(confirm_module, "fetch_alpaca_market_clock", lambda: None)
    monkeypatch.setenv("CUADRAO_STRUCTURED_MODEL", "scripted/primary")
    monkeypatch.setenv("CUADRAO_STRUCTURED_FALLBACK_MODEL", "scripted/fallback")
    monkeypatch.setenv("ARGUS_RESEARCH_RAIL_ENABLED", "false")
    monkeypatch.setenv("ARGUS_CONTEXT_PACKETS_ENABLED", "false")
    workflow = build_agent_runtime_workflow(
        checkpointer=build_agent_runtime_checkpointer()
    )
    user = UserState(user_id="replay", language_preference="en")
    thread_id = "recorded-2026-09-10"
    history: list[dict[str, str]] = []
    launches: list[dict[str, Any]] = []
    for message, script in (
        (TURN_1, _recorded_turn_1()),
        (REPLIES["en"], _recorded_turn_2()),
    ):
        provider = _ScriptedProvider(script)
        _install_provider(monkeypatch, provider)
        with turn_execution_scope(entry_state={}):
            payload = await run_agent_turn(
                workflow=workflow,
                user=user,
                thread_id=thread_id,
                message=message,
                recent_thread_history=list(history),
            )
        state = await workflow.aget_state({"configurable": {"thread_id": thread_id}})
        run_state = state.values["run_state"]
        assert payload.get("stage_outcome") == "await_approval", (
            payload.get("assistant_prompt"),
            run_state.semantic_turn_act,
            run_state.task_relation,
            state.values.get("selected_thread_metadata"),
            state.values.get("reason_codes"),
            (
                state.values.get("latest_task_snapshot") or TaskSnapshot()
            ).pending_strategy_summary,
            run_state.missing_required_fields,
            run_state.optional_parameter_status.get("unsupported_constraints"),
            run_state.candidate_strategy_draft.model_dump(mode="json"),
            provider.calls,
        )
        launches.append(
            (payload.get("confirmation_payload") or {}).get("launch_payload") or {}
        )
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": "[confirmation card]"})

    for launch in launches:
        assert launch["symbols"] == ["AAPL"]
        assert launch["starting_capital"] == 1000.0
        assert launch["recurring_contribution"] == 100.0
        assert launch["cadence"] == "monthly"
        assert launch["date_range"] == DATE_RANGE
        assert launch["benchmark_symbol"] == "SPY"
        assert launch["_execution_realism"]["fee_bps"] == 10.0
        assert launch["_execution_realism"]["slippage_bps"] == 5.0


# --- Codex round 1 on PR #591 -------------------------------------------------


@pytest.mark.parametrize(
    ("semantic_turn_act", "task_relation", "message"),
    [
        ("new_idea", "new_task", "Actually test $SPY instead"),
        (
            "refine_current_idea",
            "refine",
            "Use $SPY instead of AAPL, keep everything else",
        ),
    ],
)
def test_an_explicit_switch_to_the_benchmark_symbol_trades_that_symbol(
    semantic_turn_act: str, task_relation: str, message: str
) -> None:
    # Benchmark identity never overrides explicit traded-asset evidence.
    pending = _pending("dca_accumulation")
    response = StructuredInterpretation(
        intent="strategy_drafting",
        task_relation=task_relation,
        requires_clarification=False,
        user_goal_summary="Trade SPY instead.",
        candidate_strategy_draft=StrategySummary(
            strategy_type="dca_accumulation",
            asset_universe=["SPY"],
            asset_class="equity",
            extra_parameters={"field_provenance": {"asset_universe": "explicit_user"}},
        ),
        semantic_turn_act=semantic_turn_act,
    )

    result = _run(
        message=message,
        language="en",
        pending=pending,
        response=response,
        thread_metadata=dict(AWAITING_REPLY_WITHOUT_FIELD),
    )

    strategy = result.decision.candidate_strategy_draft
    assert strategy.asset_universe == ["SPY"]
    assert strategy.strategy_type == "dca_accumulation"
    if task_relation == "refine":
        # An edit keeps the rest of the setup; a new idea starts clean.
        assert strategy.date_range == pending.date_range
        assert strategy.cadence == "monthly"


def test_a_benchmark_the_repair_misread_as_the_asset_does_not_replace_the_pending_asset() -> (
    None
):
    # The interpreter's benchmark-misplacement repair filled the asset
    # universe from the benchmark mention and left its receipt; the reply
    # named no traded asset, so the setup keeps AAPL.
    pending = _pending("dca_accumulation")
    draft = _reply_draft(pending, "asset_and_dates")
    draft.asset_universe = ["SPY"]
    draft.asset_class = "equity"
    draft.comparison_baseline = None
    response = StructuredInterpretation(
        intent="strategy_drafting",
        task_relation="continue",
        requires_clarification=True,
        user_goal_summary="Restate the money.",
        candidate_strategy_draft=draft,
        missing_required_fields=["date_range"],
        semantic_turn_act="answer_pending_need",
        reason_codes=["misplaced_benchmark_asset_recovered"],
    )

    result = _run(
        message=REPLIES["en"],
        language="en",
        pending=pending,
        response=response,
        thread_metadata=dict(AWAITING_REPLY_WITHOUT_FIELD),
    )

    assert result.outcome == "ready_for_confirmation", result.decision.reason_codes
    _assert_pending_facts_survived(result.decision.candidate_strategy_draft, pending)


# --- Codex round 2 on PR #591 -------------------------------------------------


@pytest.mark.parametrize(
    ("language", "message"),
    [
        ("en", "New idea: DCA $200 monthly into AAPL during 2025"),
        ("es-419", "Nueva idea: DCA de $200 mensuales en AAPL durante 2025"),
    ],
)
def test_an_explicit_fresh_task_on_the_same_asset_does_not_inherit_the_pending_setup(
    language: str, message: str
) -> None:
    # The interpreter read a complete new task; asset equality must not turn
    # it into a continuation that inherits the pending seed, fees and slippage.
    pending = _pending("dca_accumulation")
    response = StructuredInterpretation(
        intent="backtest_execution",
        task_relation="new_task",
        requires_clarification=False,
        user_goal_summary="DCA $200 monthly into AAPL during 2025.",
        candidate_strategy_draft=StrategySummary(
            strategy_type="dca_accumulation",
            strategy_thesis="DCA $200 monthly into AAPL during 2025.",
            asset_universe=["AAPL"],
            asset_class="equity",
            cadence="monthly",
            date_range={"start": "2025-01-02", "end": "2025-12-31"},
            capital_amount=200.0,
            extra_parameters={
                "recurring_contribution": 200.0,
                "field_provenance": {
                    "asset_universe": "explicit_user",
                    "date_range": "explicit_user",
                    "capital_amount": "recurring_contribution",
                    "recurring_contribution": "explicit_user",
                    "cadence": "explicit_user",
                },
            },
        ),
        semantic_turn_act="new_idea",
    )

    result = _run(
        message=message,
        language=language,
        pending=pending,
        response=response,
        thread_metadata=dict(AWAITING_REPLY_WITHOUT_FIELD),
    )

    strategy = result.decision.candidate_strategy_draft
    assert result.outcome == "ready_for_confirmation", result.decision.reason_codes
    assert strategy.asset_universe == ["AAPL"]
    assert strategy.date_range == {"start": "2025-01-02", "end": "2025-12-31"}
    assert strategy.capital_amount == 200.0
    assert strategy.extra_parameters.get("initial_capital") is None
    assert "fee_rate" not in strategy.extra_parameters
    assert "slippage" not in strategy.extra_parameters
    assert "pending_setup_continuation_merged" not in result.decision.reason_codes


# --- Codex round 4 on PR #591 -------------------------------------------------


@pytest.mark.parametrize(
    ("language", "message"),
    [
        ("en", "New idea: DCA $200 monthly into AAPL"),
        ("es-419", "Nueva idea: DCA de $200 mensuales en AAPL"),
    ],
)
def test_a_partial_fresh_task_read_stays_fresh_and_asks_for_what_it_lacks(
    language: str, message: str
) -> None:
    # The interpreter read a new idea and a new task without dates. It stays
    # a new idea: nothing is copied from the pending setup, and the missing
    # dates are asked for rather than inherited.
    pending = _pending("dca_accumulation")
    response = StructuredInterpretation(
        intent="strategy_drafting",
        task_relation="new_task",
        requires_clarification=True,
        user_goal_summary="DCA $200 monthly into AAPL.",
        candidate_strategy_draft=StrategySummary(
            strategy_type="dca_accumulation",
            strategy_thesis="DCA $200 monthly into AAPL.",
            asset_universe=["AAPL"],
            asset_class="equity",
            cadence="monthly",
            capital_amount=200.0,
            extra_parameters={
                "recurring_contribution": 200.0,
                "field_provenance": {
                    "asset_universe": "explicit_user",
                    "capital_amount": "recurring_contribution",
                    "recurring_contribution": "explicit_user",
                    "cadence": "explicit_user",
                },
            },
        ),
        missing_required_fields=["date_range"],
        semantic_turn_act="new_idea",
    )

    result = _run(
        message=message,
        language=language,
        pending=pending,
        response=response,
        thread_metadata=dict(AWAITING_REPLY_WITHOUT_FIELD),
    )

    strategy = result.decision.candidate_strategy_draft
    assert result.outcome == "needs_clarification", result.decision.reason_codes
    assert "date_range" in result.decision.missing_required_fields
    assert strategy.asset_universe == ["AAPL"]
    assert strategy.date_range in (None, "", {})
    assert strategy.capital_amount == 200.0
    assert strategy.extra_parameters.get("initial_capital") is None
    assert "fee_rate" not in strategy.extra_parameters
    assert "slippage" not in strategy.extra_parameters
    assert "pending_setup_continuation_merged" not in result.decision.reason_codes


@pytest.mark.parametrize(
    ("base_act", "base_relation", "metadata", "pending", "expected"),
    [
        # A known act is the model's read and stays, whatever is pending.
        (
            "new_idea",
            "new_task",
            {"last_stage_outcome": "await_user_reply"},
            True,
            ("new_task", "new_idea", False, ()),
        ),
        (
            "answer_pending_need",
            "continue",
            {"last_stage_outcome": "await_user_reply"},
            True,
            ("continue", "answer_pending_need", True, ()),
        ),
        # Only new_idea with new_task is a fresh task; new_idea that continues
        # answers what is pending, as the stage predicate already holds.
        (
            "new_idea",
            "continue",
            {"last_stage_outcome": "await_user_reply"},
            True,
            ("continue", "new_idea", True, ()),
        ),
        # An act the repair replaces is decided by the runtime's own question,
        # and the assumption is recorded.
        (
            "unsupported_request",
            "new_task",
            {"last_stage_outcome": "await_user_reply"},
            True,
            ("continue", "answer_pending_need", True, (PENDING_REPLY_ASSUMED_REASON,)),
        ),
        (
            None,
            None,
            {"requested_field": "capital_amount"},
            True,
            ("continue", "answer_pending_need", True, (PENDING_REPLY_ASSUMED_REASON,)),
        ),
        # Nothing pending, or nothing asked: a replaced act is a fresh idea.
        (
            "unsupported_request",
            "new_task",
            {"last_stage_outcome": "await_user_reply"},
            False,
            ("new_task", "new_idea", False, ()),
        ),
        (None, None, {}, True, ("new_task", "new_idea", False, ())),
    ],
)
def test_a_repair_keeps_a_known_act_and_decides_a_replaced_one_from_the_pending_state(
    base_act: str | None,
    base_relation: str | None,
    metadata: dict[str, Any],
    pending: bool,
    expected: tuple[str, str, bool, tuple[str, ...]],
) -> None:
    request = InterpretationRequest(
        current_user_message="$500",
        recent_thread_history=[],
        latest_task_snapshot=(
            TaskSnapshot(pending_strategy_summary=_pending("dca_accumulation"))
            if pending
            else None
        ),
        selected_thread_metadata=metadata,
        user=UserState(user_id="u1"),
    )

    turn = repaired_turn_act(
        base_act=base_act, base_relation=base_relation, request=request
    )

    assert tuple(turn) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("language", "message"),
    [
        ("en", "New idea: DCA $200 monthly into AAPL"),
        ("es-419", "Nueva idea: DCA de $200 mensuales en AAPL"),
    ],
)
async def test_a_focused_repair_of_a_partial_fresh_task_does_not_fill_it_from_the_pending_setup(
    monkeypatch: pytest.MonkeyPatch, language: str, message: str
) -> None:
    # The runtime asked for the capital of a pending AAPL setup; the reply is
    # an explicit fresh task that lacks its dates. The focused re-read may fill
    # the fresh draft from the turn itself, never from the pending setup.
    from argus.agent_runtime import llm_interpreter as interpreter_module

    async def focused_stub(**kwargs: Any) -> Any:
        schema_name = kwargs["schema_name"]
        if schema_name == "FocusedStrategyExtraction":
            return interpreter_module.FocusedStrategyExtraction(
                is_testable_strategy=True,
                requires_clarification=True,
                user_goal_summary=message,
                language=language,
                strategy_type="dca_accumulation",
                asset_universe=["AAPL"],
                capital_amount=200,
                recurring_contribution=200,
                cadence="monthly",
                missing_required_fields=["date_range"],
                confidence=0.9,
                evidence_spans={
                    "asset_universe": "AAPL",
                    "recurring_contribution": "$200",
                },
            )
        raise AssertionError(f"Unexpected schema {schema_name}")

    monkeypatch.setattr(interpreter_module, "invoke_openrouter_json_schema", focused_stub)
    failed_response = LLMInterpretationResponse(
        intent="strategy_drafting",
        task_relation="new_task",
        requires_clarification=True,
        user_goal_summary=message,
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing=message,
            strategy_thesis=message,
            language=language,
        ),
        missing_required_fields=["date_range"],
        semantic_turn_act="new_idea",
    )
    request = InterpretationRequest(
        current_user_message=message,
        recent_thread_history=[],
        latest_task_snapshot=TaskSnapshot(
            pending_strategy_summary=_pending("dca_accumulation")
        ),
        selected_thread_metadata={
            "last_stage_outcome": "await_user_reply",
            "requested_field": "capital_amount",
        },
        user=UserState(user_id="u1", language_preference=language),
    )

    repaired = await interpreter_module._repair_incomplete_strategy_extraction(
        failed_response=failed_response,
        preferred_model="test-model",
        request=request,
    )

    assert repaired is not None
    assert repaired.semantic_turn_act == "new_idea"
    assert repaired.task_relation == "new_task"
    draft = repaired.candidate_strategy_draft
    assert draft.asset_universe == ["AAPL"]
    assert draft.recurring_contribution == 200
    assert draft.date_range in (None, {}, [])
    assert draft.initial_capital is None
    assert not set(draft.extra_parameters) & set(COSTS)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("language", "message"),
    [
        ("en", "Use 2023 instead"),
        ("es-419", "Usa 2023 en su lugar"),
    ],
)
async def test_a_focused_repair_of_a_date_only_reply_read_as_a_continuing_new_idea_keeps_the_pending_setup(
    monkeypatch: pytest.MonkeyPatch, language: str, message: str
) -> None:
    # The runtime asked for the capital of a pending AAPL DCA; the reply gives
    # only a year and the model labels it new_idea with task_relation continue.
    # The pair continues at the stage, so the focused re-read must keep the
    # pending family and facts rather than fall to unsupported recovery.
    from argus.agent_runtime import llm_interpreter as interpreter_module

    async def focused_stub(**kwargs: Any) -> Any:
        schema_name = kwargs["schema_name"]
        if schema_name == "FocusedStrategyExtraction":
            return interpreter_module.FocusedStrategyExtraction(
                is_testable_strategy=True,
                requires_clarification=False,
                user_goal_summary=message,
                language=language,
                date_range={"start": "2023-01-01", "end": "2023-12-31"},
                confidence=0.9,
                evidence_spans={"date_range": "2023"},
            )
        if schema_name == "StatedRunFieldFidelityAudit":
            return interpreter_module.StatedRunFieldFidelityAudit(confidence=0.9)
        raise AssertionError(f"Unexpected schema {schema_name}")

    monkeypatch.setattr(interpreter_module, "invoke_openrouter_json_schema", focused_stub)
    failed_response = LLMInterpretationResponse(
        intent="strategy_drafting",
        task_relation="continue",
        requires_clarification=True,
        user_goal_summary=message,
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing=message,
            strategy_thesis=message,
            language=language,
        ),
        missing_required_fields=["strategy_type"],
        semantic_turn_act="new_idea",
    )
    request = InterpretationRequest(
        current_user_message=message,
        recent_thread_history=[],
        latest_task_snapshot=TaskSnapshot(
            pending_strategy_summary=_pending("dca_accumulation")
        ),
        selected_thread_metadata={
            "last_stage_outcome": "await_user_reply",
            "requested_field": "capital_amount",
        },
        user=UserState(user_id="u1", language_preference=language),
    )

    repaired = await interpreter_module._repair_incomplete_strategy_extraction(
        failed_response=failed_response,
        preferred_model="test-model",
        request=request,
    )

    assert repaired is not None
    assert repaired.intent != "unsupported_or_out_of_scope"
    draft = repaired.candidate_strategy_draft
    assert draft.strategy_type == "dca_accumulation"
    assert draft.asset_universe == ["AAPL"]
    assert draft.date_range == {"start": "2023-01-01", "end": "2023-12-31"}
    assert draft.initial_capital == 1000.0
