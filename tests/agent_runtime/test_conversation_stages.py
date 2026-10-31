from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from argus.agent_runtime.artifacts import ArtifactPatch, apply_artifact_patch
from argus.agent_runtime.capabilities.contract import build_default_capability_contract
from argus.agent_runtime.coverage_recovery import (
    PRESERVED_OPTIONAL_PARAMETER_STATUS_FACT,
)
from argus.agent_runtime.llm_clarifier import (
    ClarificationRequest,
    ClarificationResponse,
    OpenRouterClarificationGenerator,
    _render_clarification_response,
)
from argus.agent_runtime.stages.clarify import clarify_stage
from argus.agent_runtime.stages.confirm import confirm_stage
from argus.agent_runtime.state.models import RunState, StrategySummary
from argus.llm import openrouter


class RecordingClarifier:
    def __init__(self, question: str | None) -> None:
        self.question = question
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        return self.question


def test_clarify_uses_generator_for_missing_required_fields() -> None:
    state = RunState.new(current_user_message="Backtest Tesla", recent_thread_history=[])
    state.intent = "strategy_drafting"
    state.missing_required_fields = ["asset_universe", "date_range"]
    state.candidate_strategy_draft = StrategySummary(strategy_type="buy_and_hold")
    clarifier = RecordingClarifier("Which asset and period should I use?")

    result = clarify_stage(
        state=state,
        contract=build_default_capability_contract(),
        clarification_generator=clarifier,
        language="en",
    )

    assert result.outcome == "await_user_reply"
    assert result.patch["assistant_prompt"] == "Which asset and period should I use?"
    assert result.patch["requested_fields"] == ["asset_universe", "date_range"]
    assert clarifier.requests[0].missing_required_fields == [
        "asset_universe",
        "date_range",
    ]
    assert clarifier.requests[0].language == "en"
    assert "asset_universe" not in result.patch["assistant_prompt"]
    assert result.patch["clarification"]["prompt_source"] == "llm_generated"
    assert result.patch["clarification"]["requested_fields"] == [
        "asset_universe",
        "date_range",
    ]


def test_clarify_confirmation_action_period_uses_llm_voice_in_spanish() -> None:
    state = RunState.new(current_user_message="Cambiar fechas", recent_thread_history=[])
    state.intent = "strategy_drafting"
    state.requested_field = "date_range"
    state.missing_required_fields = ["date_range"]
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="buy_and_hold",
        asset_universe=["AAPL"],
        asset_class="equity",
        date_range={"start": "2025-06-14", "end": "2026-06-12"},
        capital_amount=100000,
    )
    clarifier = RecordingClarifier("Claro. ¿Qué nuevo rango quieres usar para AAPL?")

    result = clarify_stage(
        state=state,
        contract=build_default_capability_contract(),
        clarification_generator=clarifier,
        language="es-419",
    )

    assert result.outcome == "await_user_reply"
    assert result.patch["assistant_prompt"] == (
        "Claro. ¿Qué nuevo rango quieres usar para AAPL?"
    )
    assert clarifier.requests[0].language == "es-419"
    assert clarifier.requests[0].response_intent["semantic_needs"] == ["period"]
    assert clarifier.requests[0].response_intent["facts"]["language"] == "es-419"
    assert "Which date" not in result.patch["assistant_prompt"]
    assert result.patch["clarification"]["prompt_source"] == "llm_generated"
    assert result.patch["clarification"]["requested_field"] == "date_range"


def test_clarify_offline_fallback_uses_product_language() -> None:
    state = RunState.new(current_user_message="Cambiar fechas", recent_thread_history=[])
    state.intent = "strategy_drafting"
    state.requested_field = "date_range"
    state.missing_required_fields = ["date_range"]
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="buy_and_hold",
        asset_universe=["AAPL"],
        asset_class="equity",
        date_range={"start": "2025-06-14", "end": "2026-06-12"},
        capital_amount=100000,
    )

    result = clarify_stage(
        state=state,
        contract=build_default_capability_contract(),
        clarification_generator=None,
        language="es-419",
    )

    assert result.outcome == "await_user_reply"
    assert result.patch["assistant_prompt"]
    assert result.patch["response_intent"]["kind"] == "clarification"
    assert result.patch["response_intent"]["semantic_needs"] == ["period"]
    clarification = result.patch["clarification"]
    assert clarification["kind"] == "clarification"
    assert clarification["reason_code"] == "missing_period"
    assert clarification["requested_field"] == "date_range"
    assert clarification["semantic_needs"] == ["period"]
    assert clarification["payload"]["strategy"]["asset_universe"] == ["AAPL"]
    assert clarification["options"] == []


def test_clarify_empty_llm_response_uses_intent_fallback() -> None:
    state = RunState.new(current_user_message="Change dates", recent_thread_history=[])
    state.intent = "strategy_drafting"
    state.requested_field = "date_range"
    state.missing_required_fields = ["date_range"]
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="buy_and_hold",
        asset_universe=["AAPL"],
        asset_class="equity",
        date_range={"start": "2025-06-14", "end": "2026-06-12"},
        capital_amount=100000,
    )
    clarifier = RecordingClarifier(None)

    result = clarify_stage(
        state=state,
        contract=build_default_capability_contract(),
        clarification_generator=clarifier,
        language="en",
    )

    assert result.outcome == "await_user_reply"
    assert result.patch["assistant_prompt"] == "What date window should I use for AAPL?"
    assert clarifier.requests
    assert "I could not phrase" not in result.patch["assistant_prompt"]
    clarification = result.patch["clarification"]
    assert clarification["kind"] == "clarification"
    assert clarification["reason_code"] == "missing_period"
    assert clarification["requested_field"] == "date_range"


def test_clarify_dca_total_budget_expands_to_execution_details() -> None:
    state = RunState.new(
        current_user_message=(
            "I would like to invest in LYFT over 5 years feb 2020-feb 2025, "
            "$200,000 of capital"
        ),
        recent_thread_history=[],
    )
    state.intent = "strategy_drafting"
    state.missing_required_fields = ["capital_amount"]
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="dca_accumulation",
        asset_universe=["LYFT"],
        asset_class="equity",
        date_range={"start": "2020-02-01", "end": "2025-02-28"},
        extra_parameters={"initial_capital": 200000},
    )
    clarifier = RecordingClarifier(
        "How much should each recurring purchase be, and how often should it happen?"
    )

    result = clarify_stage(
        state=state,
        contract=build_default_capability_contract(),
        clarification_generator=clarifier,
    )

    assert result.outcome == "await_user_reply"
    assert result.patch["response_intent"]["semantic_needs"] == [
        "sizing_amount",
        "schedule",
    ]
    request = clarifier.requests[0]
    assert set(request.response_intent["semantic_needs"]) == {
        "sizing_amount",
        "schedule",
    }


def test_clarify_dca_missing_execution_fields_win_over_total_budget_constraint() -> None:
    state = RunState.new(
        current_user_message=(
            "I would like to invest in LYFT over 5 years feb 2020-feb 2025, "
            "$200,000 of capital"
        ),
        recent_thread_history=[],
    )
    state.intent = "strategy_drafting"
    state.missing_required_fields = ["capital_amount", "cadence"]
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="dca_accumulation",
        asset_universe=["LYFT"],
        asset_class="equity",
        date_range={"start": "2020-02-01", "end": "2025-02-28"},
        extra_parameters={"total_capital": 200000},
    )
    state.optional_parameter_status = {
        "unsupported_constraints": [
            {
                "category": "unsupported_dca_contribution_ceiling",
                "raw_value": "$200,000 starting principal",
                "explanation": (
                    "The current DCA backtest can only execute the recurring "
                    "contribution."
                ),
                "simplification_options": [
                    {"label": "Run recurring buys only"},
                    {"label": "Adjust recurring contribution"},
                    {"label": "Use buy and hold with starting capital"},
                ],
            }
        ]
    }
    clarifier = RecordingClarifier(
        "How much should each recurring purchase be, and how often should it happen?"
    )

    result = clarify_stage(
        state=state,
        contract=build_default_capability_contract(),
        clarification_generator=clarifier,
    )

    assert result.outcome == "await_user_reply"
    assert result.patch["response_intent"]["kind"] == "clarification"
    assert result.patch["response_intent"]["semantic_needs"] == [
        "sizing_amount",
        "schedule",
    ]
    assert result.patch["requested_fields"] == ["capital_amount", "cadence"]
    assert clarifier.requests[0].unsupported_constraints == []


def test_clarify_dca_missing_period_wins_over_total_budget_constraint() -> None:
    state = RunState.new(
        current_user_message="I want to DCA $100 into ETH with a $5,000 cap.",
        recent_thread_history=[],
    )
    state.intent = "strategy_drafting"
    state.missing_required_fields = ["date_range"]
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="dca_accumulation",
        asset_universe=["ETH"],
        asset_class="crypto",
        capital_amount=100,
        cadence="weekly",
        extra_parameters={"total_capital": 5000},
    )
    state.optional_parameter_status = {
        "unsupported_constraints": [
            {
                "category": "unsupported_dca_contribution_ceiling",
                "raw_value": "$5,000 contribution cap",
                "explanation": (
                    "The current DCA backtest can only execute the recurring "
                    "contribution."
                ),
                "simplification_options": [
                    {"label": "Run recurring buys only"},
                    {"label": "Adjust recurring contribution"},
                ],
            }
        ]
    }
    clarifier = RecordingClarifier("What period should I use?")

    result = clarify_stage(
        state=state,
        contract=build_default_capability_contract(),
        clarification_generator=clarifier,
    )

    assert result.outcome == "await_user_reply"
    assert result.patch["response_intent"]["kind"] == "clarification"
    assert result.patch["response_intent"]["semantic_needs"] == ["period"]
    assert result.patch["requested_field"] == "date_range"
    assert clarifier.requests[0].unsupported_constraints == []


def test_dca_amount_and_cadence_contract_routes_total_budget_context_to_llm() -> None:
    state = RunState.new(
        current_user_message=(
            "I would like to invest in LYFT over 5 years feb 2020-feb 2025, "
            "$200,000 of capital"
        ),
        recent_thread_history=[],
    )
    state.intent = "strategy_drafting"
    state.missing_required_fields = ["cadence", "capital_amount"]
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="dca_accumulation",
        asset_universe=["LYFT"],
        asset_class="equity",
        date_range={"start": "2020-02-01", "end": "2025-02-28"},
        extra_parameters={"total_capital": 200000},
    )
    clarifier = RecordingClarifier(
        "How much should each recurring purchase be, and how often should it happen?"
    )

    result = clarify_stage(
        state=state,
        contract=build_default_capability_contract(),
        clarification_generator=clarifier,
    )

    assert result.outcome == "await_user_reply"
    assert result.patch["assistant_prompt"] == clarifier.question
    request = clarifier.requests[0]
    assert set(request.response_intent["semantic_needs"]) == {
        "sizing_amount",
        "schedule",
    }
    assert request.response_intent["facts"]["strategy"]["extra_parameters"] == {
        "total_capital": 200000
    }


def test_ambiguous_asset_clarification_preserves_requested_field_context() -> None:
    state = RunState.new(current_user_message="google", recent_thread_history=[])
    state.intent = "strategy_drafting"
    state.requested_field = "asset_universe"
    state.missing_required_fields = []
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="buy_and_hold",
        strategy_thesis="Buy and hold Apple.",
        asset_universe=["AAPL"],
        asset_class="equity",
        date_range={"start": "2024-01-01", "end": "2024-12-31"},
    )
    state.optional_parameter_status = {
        "ambiguous_fields": [
            {
                "field_name": "asset_universe[0]",
                "raw_value": "google",
                "reason_code": "ambiguous_asset",
            }
        ]
    }
    clarifier = RecordingClarifier("Do you mean GOOGL or GOOG?")

    result = clarify_stage(
        state=state,
        contract=build_default_capability_contract(),
        clarification_generator=clarifier,
    )

    assert result.outcome == "await_user_reply"
    assert result.patch["requested_field"] == "asset_universe"
    assert result.patch["ambiguous_fields"][0]["field_name"] == "asset_universe[0]"
    assert result.patch["response_intent"]["semantic_needs"] == ["asset_target"]
    assert clarifier.requests[0].response_intent["semantic_needs"] == ["asset_target"]


def test_dca_full_setup_uses_llm_clarifier_with_all_missing_fields() -> None:
    state = RunState.new(
        current_user_message="Walk me through a DCA",
        recent_thread_history=[],
    )
    state.intent = "strategy_drafting"
    state.missing_required_fields = [
        "asset_universe",
        "date_range",
        "capital_amount",
        "cadence",
    ]
    state.candidate_strategy_draft = StrategySummary(strategy_type="dca_accumulation")
    clarifier = RecordingClarifier(
        "Pick an asset, a time window, an amount per purchase, and a cadence."
    )

    result = clarify_stage(
        state=state,
        contract=build_default_capability_contract(),
        clarification_generator=clarifier,
    )

    assert result.outcome == "await_user_reply"
    assert result.patch["assistant_prompt"] == clarifier.question
    assert clarifier.requests[0].missing_required_fields == [
        "asset_universe",
        "date_range",
        "capital_amount",
        "cadence",
    ]
    assert clarifier.requests[0].response_intent["semantic_needs"] == [
        "asset_target",
        "period",
        "sizing_amount",
        "schedule",
    ]


def test_clarify_uses_generator_for_unsupported_recovery() -> None:
    state = RunState.new(
        current_user_message="Backtest Tesla and Bitcoin together",
        recent_thread_history=[],
    )
    state.intent = "strategy_drafting"
    state.optional_parameter_status = {
        "unsupported_constraints": [
            {
                "category": "unsupported_asset_mix",
                "raw_value": "TSLA, BTC",
                "explanation": "Mixed asset classes are not supported.",
                "simplification_options": [
                    {"label": "Run separate tests", "replacement_values": {}}
                ],
            }
        ]
    }
    clarifier = RecordingClarifier("Should I run those as separate tests?")

    result = clarify_stage(
        state=state,
        contract=build_default_capability_contract(),
        clarification_generator=clarifier,
    )

    assert result.outcome == "await_user_reply"
    assert result.patch["assistant_prompt"] == "Should I run those as separate tests?"
    assert result.patch["response_intent"]["kind"] == "unsupported_recovery"
    assert clarifier.requests[0].unsupported_constraints[0]["category"] == (
        "unsupported_asset_mix"
    )


def test_clarify_unsupported_recovery_llm_failure_uses_structured_fallback() -> None:
    state = RunState.new(
        current_user_message="Test TSLA with an ATR 14 trading rule",
        recent_thread_history=[],
    )
    state.intent = "strategy_drafting"
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="signal_strategy",
        asset_universe=["TSLA"],
        asset_class="equity",
        entry_logic="ATR 14 trading rule",
    )
    state.optional_parameter_status = {
        "unsupported_constraints": [
            {
                "category": "unsupported_strategy_logic",
                "raw_value": "ATR 14",
                "explanation": (
                    "ATR 14 is a volatility indicator, but it does not define "
                    "when to buy or sell."
                ),
                "simplification_options": [
                    {
                        "label": "Use a supported RSI threshold rule",
                        "replacement_values": {
                            "strategy_type": "signal_strategy",
                            "entry_rule": {
                                "type": "rsi_threshold",
                                "operator": "<=",
                                "threshold": 30,
                                "period": 14,
                            },
                            "exit_rule": {
                                "type": "rsi_threshold",
                                "operator": ">=",
                                "threshold": 70,
                                "period": 14,
                            },
                        },
                    },
                    {
                        "label": "Compare with buy and hold",
                        "replacement_values": {
                            "strategy_type": "buy_and_hold",
                            "entry_rule": None,
                            "exit_rule": None,
                        },
                    },
                    {
                        "label": "Use a moving-average crossover",
                        "replacement_values": {
                            "strategy_type": "signal_strategy",
                            "entry_rule": {
                                "type": "moving_average_crossover",
                                "fast_window": 50,
                                "slow_window": 200,
                            },
                        },
                    },
                ],
            }
        ]
    }
    clarifier = RecordingClarifier(None)

    result = clarify_stage(
        state=state,
        contract=build_default_capability_contract(),
        clarification_generator=clarifier,
    )

    prompt = result.patch["assistant_prompt"]
    assert result.outcome == "await_user_reply"
    assert result.patch["response_intent"]["kind"] == "unsupported_recovery"
    assert "could not phrase" not in prompt
    assert "ATR 14" not in prompt
    assert "that rule" in prompt
    assert "TSLA" in prompt
    assert "Use a supported RSI threshold rule" in prompt
    assert "Compare with buy and hold" in prompt
    assert "Use a supported moving-average crossover" in prompt


def test_clarify_spanish_unsupported_recovery_fallback_uses_structured_options() -> None:
    state = RunState.new(
        current_user_message="Prueba TSLA con una regla ATR 14",
        recent_thread_history=[],
    )
    state.intent = "strategy_drafting"
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="signal_strategy",
        asset_universe=["TSLA"],
        asset_class="equity",
        entry_logic="regla ATR 14",
    )
    state.optional_parameter_status = {
        "unsupported_constraints": [
            {
                "category": "unsupported_strategy_logic",
                "raw_value": "ATR 14",
                "explanation": "ATR 14 no define cuándo comprar o vender.",
                "simplification_options": [
                    {
                        "label": "Use a supported RSI threshold rule",
                        "replacement_values": {"simplify_logic": "rsi_only"},
                    },
                    {
                        "label": "Compare with buy and hold",
                        "replacement_values": {"strategy_type": "buy_and_hold"},
                    },
                    {
                        "label": "Use a moving-average crossover",
                        "replacement_values": {
                            "strategy_type": "signal_strategy",
                            "rule_family": "moving_average_crossover",
                        },
                    },
                ],
            }
        ]
    }
    clarifier = RecordingClarifier(None)

    result = clarify_stage(
        state=state,
        contract=build_default_capability_contract(),
        clarification_generator=clarifier,
        language="es-419",
    )

    assert result.patch["assistant_prompt"]
    assert result.patch["response_intent"]["kind"] == "unsupported_recovery"
    clarification = result.patch["clarification"]
    assert clarification["kind"] == "unsupported_recovery"
    assert clarification["reason_code"] == "unsupported_strategy_logic"
    assert clarification["requested_field"] == "unsupported_constraints"
    assert clarification["payload"]["raw_value"] == "ATR 14"
    assert clarification["payload"]["strategy"]["asset_universe"] == ["TSLA"]
    assert [option["id"] for option in clarification["options"]] == [
        "rsi_threshold",
        "buy_and_hold",
        "moving_average_crossover",
    ]
    assert [option["id"] for option in result.patch["response_intent"]["options"]] == [
        "rsi_threshold",
        "buy_and_hold",
        "moving_average_crossover",
    ]
    assert clarification["options"][0]["replacement_values"] == {
        "simplify_logic": "rsi_only"
    }


def test_clarify_uses_generator_for_dca_cap_recovery_after_execution_fields_are_known() -> (
    None
):
    state = RunState.new(
        current_user_message=(
            "what if I bought $125 of BTC every two weeks from 2022 through "
            "2023 with a $3000 cap?"
        ),
        recent_thread_history=[],
    )
    state.intent = "strategy_drafting"
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="dca_accumulation",
        asset_universe=["BTC"],
        asset_class="crypto",
        date_range={"start": "2022-01-01", "end": "2023-12-31"},
        capital_amount=125,
        cadence="biweekly",
        extra_parameters={"total_budget": 3000},
    )
    state.optional_parameter_status = {
        "unsupported_constraints": [
            {
                "category": "unsupported_dca_contribution_ceiling",
                "raw_value": "$3,000 contribution cap",
                "explanation": (
                    "I understand $3,000 as a contribution cap, but the current "
                    "DCA backtest can only execute the recurring contribution."
                ),
                "simplification_options": [
                    {"label": "Run recurring buys only"},
                    {"label": "Adjust recurring contribution"},
                    {"label": "Use buy and hold with starting capital"},
                ],
            }
        ]
    }
    clarifier = RecordingClarifier(
        "I can keep the recurring-buy run and ignore the cap, change the recurring "
        "amount, or switch to buy-and-hold with the starting capital. Which path "
        "should I use?"
    )

    result = clarify_stage(
        state=state,
        contract=build_default_capability_contract(),
        clarification_generator=clarifier,
    )

    assert result.outcome == "await_user_reply"
    assert result.patch["response_intent"]["kind"] == "unsupported_recovery"
    assert result.patch["assistant_prompt"] == clarifier.question
    assert len(clarifier.requests) == 1
    assert clarifier.requests[0].unsupported_constraints[0]["category"] == (
        "unsupported_dca_contribution_ceiling"
    )
    prompt = result.patch["assistant_prompt"]
    assert "recurring-buy" in prompt
    assert "starting capital" in prompt


def test_clarify_routes_interpreter_prefill_through_target_aware_generator() -> None:
    state = RunState.new(
        current_user_message="Run the MACD part only",
        recent_thread_history=[],
    )
    state.intent = "strategy_drafting"
    state.missing_required_fields = ["entry_logic"]
    assistant_prompt = (
        "I can run the MACD crossover now, but the volume jump needs a definition."
    )
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="signal_strategy",
        strategy_thesis="Test BTC when MACD turns bullish and volume jumps.",
        asset_universe=["BTC"],
        date_range="last 6 months",
    )
    clarifier = RecordingClarifier("Generic fallback question")

    result = clarify_stage(
        state=state,
        contract=build_default_capability_contract(),
        clarification_generator=clarifier,
        prefilled_assistant_prompt=assistant_prompt,
    )

    assert result.outcome == "await_user_reply"
    assert result.patch["assistant_prompt"] == clarifier.question
    assert result.patch["requested_field"] == "entry_logic"
    assert clarifier.requests[0].missing_required_fields == ["entry_logic"]


def test_beginner_guidance_uses_interpreter_prefill_without_second_llm() -> None:
    state = RunState.new(
        current_user_message="I want to create a new strategy.",
        recent_thread_history=[],
    )
    state.intent = "beginner_guidance"
    assistant_prompt = (
        "Happy to start there. Pick an asset and a rough timeframe, or choose "
        "buy-and-hold, recurring buys, RSI, or a moving-average crossover."
    )
    clarifier = RecordingClarifier("This should not be used.")

    result = clarify_stage(
        state=state,
        contract=build_default_capability_contract(),
        clarification_generator=clarifier,
        prefilled_assistant_prompt=assistant_prompt,
    )

    assert result.outcome == "await_user_reply"
    assert result.patch["assistant_prompt"] == assistant_prompt
    assert result.patch["response_intent"]["kind"] == "beginner_guidance"
    assert clarifier.requests == []


def test_beginner_guidance_without_prefill_uses_llm_clarifier() -> None:
    state = RunState.new(
        current_user_message="I want to create a new strategy.",
        recent_thread_history=[],
    )
    state.intent = "beginner_guidance"
    clarifier = RecordingClarifier(
        "Start with an asset and a rough window, and I can shape it into a test."
    )

    result = clarify_stage(
        state=state,
        contract=build_default_capability_contract(),
        clarification_generator=clarifier,
    )

    assert result.outcome == "await_user_reply"
    assert result.patch["assistant_prompt"] == clarifier.question
    assert clarifier.requests[0].response_intent["kind"] == "beginner_guidance"


def test_rule_clarification_preserves_known_asset_context() -> None:
    state = RunState.new(
        current_user_message=(
            "Can you test Nvidia using MACD and RSI together and only buy if volume "
            "is above average?"
        ),
        recent_thread_history=[],
    )
    strategy = StrategySummary(
        strategy_type="signal_strategy",
        strategy_thesis="Test Nvidia using MACD and RSI with volume confirmation.",
        asset_universe=["NVDA"],
        asset_class="equity",
        entry_logic="MACD, RSI, and volume confirmation",
    )
    state.intent = "strategy_drafting"
    state.missing_required_fields = ["entry_logic"]
    state.candidate_strategy_draft = strategy
    clarifier = RecordingClarifier(
        "NVDA is the anchor. Which supported rule should I test?"
    )

    result = clarify_stage(
        state=state,
        contract=build_default_capability_contract(),
        clarification_generator=clarifier,
    )

    assert result.outcome == "await_user_reply"
    assert result.patch["assistant_prompt"] == clarifier.question
    assert clarifier.requests[0].candidate_strategy_draft.asset_universe == ["NVDA"]
    assert clarifier.requests[0].response_intent["semantic_needs"] == ["rule_definition"]


def test_multi_field_signal_clarification_uses_plain_language() -> None:
    state = RunState.new(
        current_user_message="buy when the 50 crosses the 200",
        recent_thread_history=[],
    )
    strategy = StrategySummary(
        strategy_type="signal_strategy",
        strategy_thesis="Buy when the 50-day moving average crosses the 200-day.",
        entry_logic="50 crosses 200",
    )
    state.intent = "strategy_drafting"
    state.missing_required_fields = ["asset_universe", "date_range"]
    state.candidate_strategy_draft = strategy
    clarifier = RecordingClarifier("What asset and date range should I use?")

    result = clarify_stage(
        state=state,
        contract=build_default_capability_contract(),
        clarification_generator=clarifier,
    )

    assert result.outcome == "await_user_reply"
    assert result.patch["assistant_prompt"] == clarifier.question
    assert clarifier.requests[0].response_intent["semantic_needs"] == [
        "asset_target",
        "period",
    ]


def test_confirmation_action_assumption_uses_llm_voice_in_spanish() -> None:
    state = RunState.new(
        current_user_message="Ajustar supuestos", recent_thread_history=[]
    )
    state.intent = "strategy_drafting"
    state.requested_field = "assumption"
    state.missing_required_fields = ["assumption"]
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="buy_and_hold",
        asset_universe=["AAPL"],
        asset_class="equity",
    )
    clarifier = RecordingClarifier("¿Qué supuesto quieres ajustar para AAPL?")

    result = clarify_stage(
        state=state,
        contract=build_default_capability_contract(),
        clarification_generator=clarifier,
        language="es-419",
    )

    assert result.outcome == "await_user_reply"
    assert result.patch["assistant_prompt"] == clarifier.question
    assert clarifier.requests[0].language == "es-419"
    assert clarifier.requests[0].response_intent["semantic_needs"] == ["assumption"]


def test_clarify_unsupported_recovery_uses_user_facing_clarifier_voice() -> None:
    state = RunState.new(
        current_user_message="Test Apple when news sentiment turns positive.",
        recent_thread_history=[],
    )
    state.intent = "unsupported_or_out_of_scope"
    state.optional_parameter_status = {
        "unsupported_constraints": [
            {
                "category": "unsupported_strategy_logic",
                "raw_value": "news sentiment turns positive",
                "explanation": "Sentiment/news signals are not executable yet.",
                "simplification_options": [
                    {"label": "Use a supported RSI threshold rule"},
                    {"label": "Compare with buy and hold"},
                ],
            }
        ]
    }
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="signal_strategy",
        strategy_thesis="Buy AAPL when news sentiment turns positive.",
        asset_universe=["AAPL"],
        asset_class="equity",
        capital_amount=10_000,
        date_range={"start": "2022-01-01", "end": "2025-01-01"},
    )
    clarifier = RecordingClarifier(
        "I can't test news sentiment as a trading rule for AAPL yet. I kept your "
        "$10,000 and January 2022 to January 2025 setup. Would you like an RSI "
        "threshold, a moving-average crossover, or buy and hold instead?"
    )
    refusal = (
        "News sentiment is not supported in executable rule specs. It cannot be "
        "converted to a runnable rule_spec for the signal engine."
    )

    result = clarify_stage(
        state=state,
        contract=build_default_capability_contract(),
        clarification_generator=clarifier,
        prefilled_assistant_prompt=refusal,
    )

    assert result.outcome == "await_user_reply"
    assert result.patch["assistant_prompt"] == clarifier.question
    assert len(clarifier.requests) == 1
    request = clarifier.requests[0]
    assert request.candidate_strategy_draft.asset_universe == ["AAPL"]
    assert request.candidate_strategy_draft.capital_amount == 10_000
    assert request.candidate_strategy_draft.date_range == {
        "start": "2022-01-01",
        "end": "2025-01-01",
    }
    assert result.patch["clarification"]["prompt_source"] == "llm_generated"
    assert [option["label"] for option in result.patch["simplification_options"]] == [
        "Use a supported RSI threshold rule",
        "Compare with buy and hold",
    ]

    blank_prefill = clarify_stage(
        state=state,
        contract=build_default_capability_contract(),
        clarification_generator=clarifier,
        prefilled_assistant_prompt="   ",
    )

    assert blank_prefill.patch["assistant_prompt"] == clarifier.question
    assert clarifier.requests[-1].unsupported_constraints[0]["category"] == (
        "unsupported_strategy_logic"
    )


def test_clarify_unsupported_timeframe_persists_typed_actions_with_llm_voice() -> None:
    state = RunState.new(
        current_user_message="Use five-minute bars.",
        recent_thread_history=[],
    )
    state.intent = "unsupported_or_out_of_scope"
    state.requested_field = "timeframe"
    state.missing_required_fields = ["timeframe"]
    state.optional_parameter_status = {
        "initial_capital": 5_000,
        "fees": 0.001,
        "slippage": 0.0005,
        "timeframe": "5m",
        "unsupported_constraints": [
            {
                "category": "unsupported_time_granularity",
                "raw_value": "5m",
                "explanation": "Choose a supported timeframe.",
                "simplification_options": [
                    {
                        "label": "Retry with daily bars",
                        "replacement_values": {"timeframe": "1D"},
                    },
                    {
                        "label": "Retry with 1-hour bars",
                        "replacement_values": {"timeframe": "1h"},
                    },
                ],
            }
        ],
    }
    clarifier = RecordingClarifier(
        "Five-minute bars are not supported. Choose daily or one-hour bars."
    )

    result = clarify_stage(
        state=state,
        contract=build_default_capability_contract(),
        clarification_generator=clarifier,
    )

    assert result.outcome == "await_user_reply"
    assert result.patch["assistant_prompt"] == clarifier.question
    assert result.patch["response_intent"]["facts"][
        PRESERVED_OPTIONAL_PARAMETER_STATUS_FACT
    ] == {
        "initial_capital": 5_000,
        "fees": 0.001,
        "slippage": 0.0005,
        "timeframe": "5m",
    }
    assert [option["id"] for option in result.patch["response_intent"]["options"]] == [
        "option_0",
        "option_1",
    ]
    assert result.patch["clarification"] == {
        "kind": "unsupported_recovery",
        "reason_code": "unsupported_time_granularity",
        "prompt_source": "llm_generated",
        "requested_field": "timeframe",
        "requested_fields": ["timeframe"],
        "semantic_needs": ["simplification_choice"],
        "payload": {
            "strategy": state.candidate_strategy_draft.model_dump(mode="python"),
            "raw_value": "5m",
        },
        "options": [
            {
                "id": "option_0",
                "replacement_values": {"timeframe": "1D"},
                "compatibility_label": "Retry with daily bars",
            },
            {
                "id": "option_1",
                "replacement_values": {"timeframe": "1h"},
                "compatibility_label": "Retry with 1-hour bars",
            },
        ],
    }


@pytest.mark.parametrize("language", ["en", "es-419"])
def test_clarify_unsupported_timeframe_degraded_fallback_is_typed_and_truthful(
    language: str,
) -> None:
    state = RunState.new(
        current_user_message="Use five-minute bars.",
        recent_thread_history=[],
    )
    state.intent = "unsupported_or_out_of_scope"
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="buy_and_hold",
        asset_universe=["AAPL"],
        asset_class="equity",
        timeframe="5m",
    )
    state.requested_field = "timeframe"
    state.missing_required_fields = ["timeframe"]
    state.optional_parameter_status = {
        "timeframe": "5m",
        "unsupported_constraints": [
            {
                "category": "unsupported_time_granularity",
                "raw_value": "5m",
                "explanation": "Choose a supported timeframe.",
                "simplification_options": [
                    {
                        "label": "Retry with daily bars",
                        "replacement_values": {"timeframe": "1D"},
                    },
                    {
                        "label": "Retry with 1-hour bars",
                        "replacement_values": {"timeframe": "1h"},
                    },
                ],
            }
        ],
    }

    result = clarify_stage(
        state=state,
        contract=build_default_capability_contract(),
        clarification_generator=RecordingClarifier(None),
        language=language,
    )

    assert result.outcome == "await_user_reply"
    assert result.patch["assistant_prompt"] == (
        "5m is not a supported bar size. Choose daily or 1-hour bars."
    )
    assert result.patch["clarification"]["prompt_source"] == "degraded_fallback"
    assert result.patch["clarification"]["reason_code"] == (
        "unsupported_time_granularity"
    )
    assert [option["id"] for option in result.patch["response_intent"]["options"]] == [
        option["id"] for option in result.patch["clarification"]["options"]
    ]


def test_clarification_renderer_collapses_adjacent_duplicate_sentences() -> None:
    request = ClarificationRequest(
        current_user_message="Use the supported version.",
        candidate_strategy_draft=StrategySummary(strategy_type="dca_accumulation"),
        response_intent={
            "kind": "unsupported_recovery",
            "semantic_needs": ["simplification_choice"],
        },
    )
    response = ClarificationResponse(
        question=(
            "I can keep the runnable version. I can keep the runnable version. "
            "Which direction should I use?"
        ),
        question_targets=["simplification_choice"],
        directly_asks_user=True,
        detail_targets=["simplification_choice"],
    )

    rendered = _render_clarification_response(response, request=request)

    assert rendered == "I can keep the runnable version. Which direction should I use?"


def test_clarification_renderer_collapses_duplicates_after_direct_question_append() -> (
    None
):
    repeated = (
        "ATR 14 is a volatility indicator, but I need an explicit entry or exit "
        "rule to run a test."
    )
    request = ClarificationRequest(
        current_user_message="Test TSLA with an ATR 14 trading rule",
        candidate_strategy_draft=StrategySummary(
            strategy_type="signal_strategy",
            asset_universe=["TSLA"],
        ),
        response_intent={
            "kind": "unsupported_recovery",
            "semantic_needs": ["simplification_choice"],
        },
    )
    response = ClarificationResponse(
        question=repeated,
        direct_question=(
            f"{repeated} Which direction would you like to go? Use a supported "
            "RSI threshold rule, compare with buy and hold, or use a supported "
            "moving-average crossover?"
        ),
        question_targets=["simplification_choice"],
        directly_asks_user=True,
        detail_targets=["simplification_choice"],
    )

    rendered = _render_clarification_response(response, request=request)

    assert rendered.count(repeated) == 1
    assert rendered == (
        f"{repeated} Which direction would you like to go? Use a supported RSI "
        "threshold rule, compare with buy and hold, or use a supported "
        "moving-average crossover?"
    )


def test_clarification_renderer_collapses_repeated_context_block_before_question() -> (
    None
):
    first = (
        "El ATR 14 es un indicador de volatilidad que aún no podemos ejecutar "
        "como regla de entrada o salida."
    )
    second = "Podemos probar TSLA en 2024 con $1,000 de otras formas."
    direct = (
        "¿Te interesa usar un cruce de medias móviles, una regla de RSI, "
        "o simplemente comparar con comprar y mantener?"
    )
    request = ClarificationRequest(
        current_user_message="Prueba TSLA con ATR 14 durante 2024 con $1,000",
        candidate_strategy_draft=StrategySummary(
            strategy_type="signal_strategy",
            asset_universe=["TSLA"],
        ),
        response_intent={
            "kind": "unsupported_recovery",
            "semantic_needs": ["simplification_choice"],
        },
        language="es-419",
    )
    response = ClarificationResponse(
        question=f"{first} {second} {first} {second} {direct}",
        question_targets=["simplification_choice"],
        directly_asks_user=True,
        detail_targets=["simplification_choice"],
    )

    rendered = _render_clarification_response(response, request=request)

    assert rendered == f"{first} {second} {direct}"


def test_clarifier_system_prompt_enforces_user_language() -> None:
    clarifier = OpenRouterClarificationGenerator()
    request = clarifier.request_model(
        current_user_message="Necesito probar Tesla",
        candidate_strategy_draft=StrategySummary(strategy_type="buy_and_hold"),
        missing_required_fields=["date_range"],
        language="es-419",
    )

    messages = clarifier._messages(request)
    system_prompt = messages[0].content

    assert (
        "Respond in the user's preferred language (e.g., Spanish if language is "
        "'es-419')."
    ) in system_prompt
    assert "es-419" in messages[1].content


def test_clarifier_system_prompt_avoids_stale_fixed_date_examples() -> None:
    clarifier = OpenRouterClarificationGenerator()
    request = clarifier.request_model(
        current_user_message="Cambiar fechas",
        candidate_strategy_draft=StrategySummary(
            strategy_type="buy_and_hold",
            asset_universe=["AAPL"],
        ),
        missing_required_fields=["date_range"],
        response_intent={"kind": "clarification", "semantic_needs": ["period"]},
        language="es-419",
    )

    system_prompt = clarifier._messages(request)[0].content

    assert "avoid arbitrary fixed calendar examples" in system_prompt
    assert "relative or rolling windows" in system_prompt


def test_clarifier_system_prompt_guides_unsupported_recovery_context() -> None:
    clarifier = OpenRouterClarificationGenerator()
    request = clarifier.request_model(
        current_user_message="Test Apple when news sentiment turns positive.",
        candidate_strategy_draft=StrategySummary(
            strategy_thesis="Use sentiment as the entry signal for Apple.",
            asset_universe=["AAPL"],
            date_range="past year",
            entry_logic="news sentiment turns positive",
        ),
        unsupported_constraints=[
            {
                "category": "unsupported_strategy_logic",
                "raw_value": "news sentiment turns positive",
                "explanation": "Sentiment/news signals are not executable yet.",
                "simplification_options": [
                    {"label": "Use a supported RSI threshold rule"},
                    {"label": "Compare with buy and hold"},
                ],
            }
        ],
        response_intent={
            "kind": "unsupported_recovery",
            "facts": {
                "strategy": {
                    "strategy_thesis": "Use sentiment as the entry signal for Apple.",
                    "asset_universe": ["AAPL"],
                    "date_range": "past year",
                    "entry_logic": "news sentiment turns positive",
                },
                "unsupported_constraints": [
                    {
                        "category": "unsupported_strategy_logic",
                        "raw_value": "news sentiment turns positive",
                        "explanation": ("Sentiment/news signals are not executable yet."),
                    }
                ],
            },
        },
    )

    messages = clarifier._messages(request)
    system_prompt = messages[0].content
    context = json.loads(messages[1].content)

    assert "unsupported_recovery" in system_prompt
    assert "typed capability cause" in system_prompt
    assert "simplification_options" in system_prompt
    assert "Do not claim the unsupported part is executable" in system_prompt
    assert context["candidate_strategy_draft"]["asset_universe"] == ["AAPL"]
    assert "strategy_thesis" not in context["candidate_strategy_draft"]
    assert "entry_logic" not in context["candidate_strategy_draft"]
    assert "strategy_thesis" not in context["response_intent"]["facts"]["strategy"]
    assert "entry_logic" not in context["response_intent"]["facts"]["strategy"]
    assert context["unsupported_constraints"][0] == {
        "category": "unsupported_strategy_logic",
        "simplification_options": [
            {"label": "Use a supported RSI threshold rule"},
            {"label": "Compare with buy and hold"},
        ],
    }
    assert context["response_intent"]["facts"]["unsupported_constraints"] == [
        {"category": "unsupported_strategy_logic"}
    ]


def test_clarifier_system_prompt_keeps_vague_ideas_on_supported_proxies() -> None:
    clarifier = OpenRouterClarificationGenerator()
    request = clarifier.request_model(
        current_user_message="What if I bought Tesla when it looked cheap?",
        candidate_strategy_draft=StrategySummary(
            strategy_type="buy_and_hold",
            asset_universe=["TSLA"],
        ),
        missing_required_fields=["date_range"],
        response_intent={"kind": "clarification", "semantic_needs": ["period"]},
    )

    system_prompt = clarifier._messages(request)[0].content

    assert "do not write a numbered requirements list" in system_prompt.lower()
    assert "buy-and-hold baseline" in system_prompt
    assert "supported RSI threshold" in system_prompt
    assert "supported moving average crossover" in system_prompt
    assert "Acknowledge valid finance concepts" in system_prompt
    assert "P/E" in system_prompt
    assert "current engine cannot execute P/E as a rule yet" in system_prompt
    assert "Translate that concept to the closest supported proxy" in system_prompt
    assert "name P/E or valuation as valid context" in system_prompt
    assert "only from asset_history_starts" in system_prompt
    assert "2016" not in system_prompt
    assert "bounded recent-data window" in system_prompt
    assert "do not silently widen the timeframe" in system_prompt
    assert "Do not mention provider names" in system_prompt
    assert "candle counts" in system_prompt
    assert "Do not ask the user to define a moving-average trigger again" in system_prompt
    assert "the 50 crosses the 200" in system_prompt
    assert "Do not use headings or numbered lists" in system_prompt


def test_openrouter_clarifier_uses_structured_response_contract(monkeypatch) -> None:
    observed = {}
    openrouter.clear_openrouter_route_receipts()
    monkeypatch.setenv("CUADRAO_CHAT_MODEL", "chat/primary")
    monkeypatch.setenv("CUADRAO_CHAT_FALLBACK_MODEL", "chat/fallback")

    async def fake_json_schema(
        *, task, messages, schema_model, schema_name, model_name=None
    ):
        observed["task"] = task
        observed["messages"] = messages
        observed["schema_model"] = schema_model
        observed["schema_name"] = schema_name
        observed["model_name"] = model_name
        openrouter.record_openrouter_route_receipt(
            task=task,
            model_name=model_name,
            mode="json_schema",
            schema_name=schema_name,
            latency_ms=42,
            outcome="succeeded",
            token_usage={"input_tokens": 21, "output_tokens": 16},
        )
        return ClarificationResponse(
            question=(
                "Cheap can mean valuation, like P/E. For TSLA, I can use the "
                "closest runnable proxy: buy-and-hold over a window you care "
                "about. What period should I test?"
            ),
            question_targets=["period"],
            directly_asks_user=True,
        )

    monkeypatch.setattr(
        "argus.agent_runtime.llm_clarifier.invoke_openrouter_json_schema",
        fake_json_schema,
    )

    clarifier = OpenRouterClarificationGenerator()
    question = clarifier(
        clarifier.request_model(
            current_user_message="What if I bought Tesla when it looked cheap?",
            candidate_strategy_draft=StrategySummary(
                strategy_type="buy_and_hold",
                asset_universe=["TSLA"],
            ),
            missing_required_fields=["date_range"],
            response_intent={
                "kind": "clarification",
                "semantic_needs": ["period"],
            },
            language="en",
        )
    )

    assert question is not None
    assert "TSLA" in question
    assert "P/E" in question
    assert "period" in question.lower()
    assert "missing_required_fields" not in question
    assert observed["task"] == "clarification"
    assert observed["schema_model"] is ClarificationResponse
    assert observed["schema_name"] == "ClarificationResponse"
    assert observed["model_name"] is None
    assert any("P/E" in message["content"] for message in observed["messages"])
    receipts = openrouter.get_openrouter_route_receipts()
    assert receipts[-1].task == "clarification"
    assert receipts[-1].tier == "chat"
    assert receipts[-1].outcome == "succeeded"
    assert receipts[-1].token_usage == {"input_tokens": 21, "output_tokens": 16}


def test_openrouter_clarifier_rejects_questions_outside_runtime_needs(
    monkeypatch,
) -> None:
    openrouter.clear_openrouter_route_receipts()
    monkeypatch.setenv("CUADRAO_CHAT_MODEL", "chat/primary")
    monkeypatch.setenv("CUADRAO_CHAT_FALLBACK_MODEL", "chat/fallback")
    calls: list[str | None] = []

    async def fake_json_schema(
        *, task, messages, schema_model, schema_name, model_name=None
    ):
        del task, messages, schema_model, schema_name
        calls.append(model_name)
        if model_name is None:
            return ClarificationResponse(
                question=(
                    "Could you specify the exact trigger for the crossover before "
                    "I test it?"
                ),
                question_targets=["rule_definition"],
                directly_asks_user=True,
            )
        return ClarificationResponse(
            question=(
                "That crossover is clear enough to test. What asset should I use, "
                "and what date window should I use?"
            ),
            question_targets=["asset_target", "period"],
            directly_asks_user=True,
        )

    monkeypatch.setattr(
        "argus.agent_runtime.llm_clarifier.invoke_openrouter_json_schema",
        fake_json_schema,
    )

    clarifier = OpenRouterClarificationGenerator()
    question = clarifier(
        clarifier.request_model(
            current_user_message="buy when the 50 crosses the 200",
            candidate_strategy_draft=StrategySummary(
                strategy_type="signal_strategy",
                entry_logic="50-day SMA crosses above 200-day SMA",
                exit_logic="50-day SMA crosses below 200-day SMA",
                entry_rule={
                    "type": "moving_average_crossover",
                    "fast_indicator": "sma",
                    "fast_period": 50,
                    "slow_indicator": "sma",
                    "slow_period": 200,
                    "direction": "bullish",
                },
            ),
            missing_required_fields=["asset_universe", "date_range"],
            response_intent={
                "kind": "clarification",
                "semantic_needs": ["asset_target", "period"],
            },
        )
    )

    assert question is not None
    assert "What asset" in question
    assert "date window" in question
    assert calls == [None, "chat/fallback"]
    receipts = openrouter.get_openrouter_route_receipts()
    assert receipts[-1].model == "chat/primary"
    assert receipts[-1].failure_mode == "contract_violation"


def test_openrouter_clarifier_rejects_vague_dca_detail_response(
    monkeypatch,
) -> None:
    openrouter.clear_openrouter_route_receipts()
    monkeypatch.setenv("CUADRAO_CHAT_MODEL", "chat/primary")
    monkeypatch.setenv("CUADRAO_CHAT_FALLBACK_MODEL", "chat/fallback")
    calls: list[str | None] = []

    async def fake_json_schema(
        *, task, messages, schema_model, schema_name, model_name=None
    ):
        del task, messages, schema_model, schema_name
        calls.append(model_name)
        if model_name is None:
            return ClarificationResponse(
                question=(
                    "I can test recurring buys for LYFT. I need one more detail "
                    "before I can turn this into a backtest."
                ),
                question_targets=["sizing_amount", "schedule"],
                directly_asks_user=True,
            )
        return ClarificationResponse(
            question=(
                "I can test recurring buys for LYFT. How much should each recurring "
                "purchase be, and how often should those buys happen?"
            ),
            direct_question=(
                "How much should each recurring purchase be, and how often should "
                "those buys happen?"
            ),
            question_targets=["sizing_amount", "schedule"],
            directly_asks_user=True,
            detail_targets=["recurring_purchase_amount", "purchase_cadence"],
        )

    monkeypatch.setattr(
        "argus.agent_runtime.llm_clarifier.invoke_openrouter_json_schema",
        fake_json_schema,
    )

    clarifier = OpenRouterClarificationGenerator()
    question = clarifier(
        clarifier.request_model(
            current_user_message=(
                "I would like to invest in LYFT over 5 years feb 2020-feb 2025, "
                "$200,000 of capital"
            ),
            candidate_strategy_draft=StrategySummary(
                strategy_type="dca_accumulation",
                asset_universe=["LYFT"],
                asset_class="equity",
                date_range={"start": "2020-02-01", "end": "2025-02-28"},
                extra_parameters={"initial_capital": 200000},
            ),
            missing_required_fields=["capital_amount"],
            response_intent={
                "kind": "clarification",
                "semantic_needs": ["sizing_amount", "schedule"],
            },
        )
    )

    assert question is not None
    assert "recurring purchase" in question
    assert "how often" in question.lower()
    assert calls == [None, "chat/fallback"]
    receipts = openrouter.get_openrouter_route_receipts()
    assert receipts[-1].model == "chat/primary"
    assert receipts[-1].failure_mode == "contract_violation"


def test_openrouter_clarifier_renders_dca_model_direct_question(monkeypatch) -> None:
    async def fake_json_schema(
        *, task, messages, schema_model, schema_name, model_name=None
    ):
        del task, messages, schema_model, schema_name, model_name
        return ClarificationResponse(
            question=(
                "Got it — LYFT, $200k total, from Feb 2020 to Feb 2025. "
                "To set up the DCA, I need the recurring purchase amount and cadence."
            ),
            direct_question=(
                "How much should each recurring purchase be, and how often should "
                "those purchases happen?"
            ),
            question_targets=["sizing_amount", "schedule"],
            directly_asks_user=True,
            detail_targets=["recurring_purchase_amount", "purchase_cadence"],
        )

    monkeypatch.setattr(
        "argus.agent_runtime.llm_clarifier.invoke_openrouter_json_schema",
        fake_json_schema,
    )

    clarifier = OpenRouterClarificationGenerator()
    question = clarifier(
        clarifier.request_model(
            current_user_message=(
                "I would like to invest in LYFT over 5 years feb 2020-feb 2025, "
                "$200,000 of capital"
            ),
            candidate_strategy_draft=StrategySummary(
                strategy_type="dca_accumulation",
                asset_universe=["LYFT"],
                asset_class="equity",
                date_range={"start": "2020-02-01", "end": "2025-02-28"},
                extra_parameters={"initial_capital": 200000},
            ),
            missing_required_fields=["capital_amount", "cadence"],
            response_intent={
                "kind": "clarification",
                "semantic_needs": ["sizing_amount", "schedule"],
            },
        )
    )

    assert question is not None
    assert question.startswith("Got it")
    assert "How much should each recurring purchase be" in question
    assert "how often should those purchases happen" in question
    assert question.lower().count("how often") == 1


def test_openrouter_clarifier_preserves_localized_dca_detail_question(
    monkeypatch,
) -> None:
    async def fake_json_schema(
        *, task, messages, schema_model, schema_name, model_name=None
    ):
        del task, messages, schema_model, schema_name, model_name
        return ClarificationResponse(
            question=(
                "Entiendo: DCA para ETH. Para hacerlo ejecutable, necesito el monto "
                "de cada compra y la frecuencia."
            ),
            direct_question=(
                "¿Cuánto quieres comprar en cada operación recurrente y con qué "
                "frecuencia?"
            ),
            question_targets=["sizing_amount", "schedule"],
            directly_asks_user=True,
            detail_targets=["recurring_purchase_amount", "purchase_cadence"],
        )

    monkeypatch.setattr(
        "argus.agent_runtime.llm_clarifier.invoke_openrouter_json_schema",
        fake_json_schema,
    )

    clarifier = OpenRouterClarificationGenerator()
    question = clarifier(
        clarifier.request_model(
            current_user_message="Compra ETH de forma recurrente desde 2022",
            candidate_strategy_draft=StrategySummary(
                strategy_type="dca_accumulation",
                asset_universe=["ETH"],
                asset_class="crypto",
                date_range={"start": "2022-01-01", "end": "today"},
            ),
            missing_required_fields=["capital_amount", "cadence"],
            response_intent={
                "kind": "clarification",
                "semantic_needs": ["sizing_amount", "schedule"],
            },
            language="es-419",
        )
    )

    assert question is not None
    assert "¿Cuánto quieres comprar" in question
    assert "con qué frecuencia" in question
    assert "How much should each recurring purchase be" not in question


def test_openrouter_clarifier_preserves_initial_dca_setup_question(
    monkeypatch,
) -> None:
    async def fake_json_schema(
        *, task, messages, schema_model, schema_name, model_name=None
    ):
        del task, messages, schema_model, schema_name, model_name
        return ClarificationResponse(
            question=(
                "Which asset should I use, what date range should I test, how much "
                "should each recurring purchase be, and how often should purchases happen?"
            ),
            direct_question=(
                "Which asset should I use, what date range should I test, how much "
                "should each recurring purchase be, and how often should purchases happen?"
            ),
            question_targets=[
                "asset_target",
                "period",
                "sizing_amount",
                "schedule",
            ],
            directly_asks_user=True,
            detail_targets=[
                "asset",
                "date_window",
                "recurring_purchase_amount",
                "purchase_cadence",
            ],
        )

    monkeypatch.setattr(
        "argus.agent_runtime.llm_clarifier.invoke_openrouter_json_schema",
        fake_json_schema,
    )

    clarifier = OpenRouterClarificationGenerator()
    question = clarifier(
        clarifier.request_model(
            current_user_message="Walk me through a DCA",
            candidate_strategy_draft=StrategySummary(
                strategy_type="dca_accumulation",
            ),
            missing_required_fields=[
                "asset_universe",
                "date_range",
                "capital_amount",
                "cadence",
            ],
            response_intent={
                "kind": "clarification",
                "semantic_needs": [
                    "asset_target",
                    "period",
                    "sizing_amount",
                    "schedule",
                ],
            },
        )
    )

    assert question is not None
    assert "Which asset" in question
    assert "date range" in question
    assert "recurring purchase" in question
    assert "how often" in question.lower()


def test_openrouter_clarifier_deduplicates_embedded_direct_question(
    monkeypatch,
) -> None:
    async def fake_json_schema(
        *, task, messages, schema_model, schema_name, model_name=None
    ):
        del task, messages, schema_model, schema_name, model_name
        return ClarificationResponse(
            question=(
                "Sure. I need four things: the asset, date range, recurring purchase "
                "amount, and cadence. What asset are you thinking of, and what time "
                "period should we look at."
            ),
            direct_question=(
                "What asset are you thinking of, and what time period should we look at?"
            ),
            question_targets=["asset_target", "period"],
            directly_asks_user=True,
            detail_targets=["asset", "date_window"],
        )

    monkeypatch.setattr(
        "argus.agent_runtime.llm_clarifier.invoke_openrouter_json_schema",
        fake_json_schema,
    )

    clarifier = OpenRouterClarificationGenerator()
    question = clarifier(
        clarifier.request_model(
            current_user_message="Walk me through a DCA",
            candidate_strategy_draft=StrategySummary(
                strategy_type="dca_accumulation",
            ),
            missing_required_fields=["asset_universe", "date_range"],
            response_intent={
                "kind": "clarification",
                "semantic_needs": ["asset_target", "period"],
            },
        )
    )

    assert question is not None
    assert question.lower().count("what asset") == 1
    assert question.endswith("what time period should we look at?")


def test_openrouter_clarifier_deduplicates_identical_direct_question(
    monkeypatch,
) -> None:
    repeated = (
        "¿Qué período prefieres para la prueba de AAPL? Por ejemplo, dime un "
        "rango de fechas concreto o una ventana como últimos 3 años."
    )

    async def fake_json_schema(
        *, task, messages, schema_model, schema_name, model_name=None
    ):
        del task, messages, schema_model, schema_name, model_name
        return ClarificationResponse(
            question=repeated,
            direct_question=repeated,
            question_targets=["period"],
            directly_asks_user=True,
            detail_targets=["date_window"],
        )

    monkeypatch.setattr(
        "argus.agent_runtime.llm_clarifier.invoke_openrouter_json_schema",
        fake_json_schema,
    )

    clarifier = OpenRouterClarificationGenerator()
    question = clarifier(
        clarifier.request_model(
            current_user_message="Cambiar fechas",
            candidate_strategy_draft=StrategySummary(
                strategy_type="buy_and_hold",
                asset_universe=["AAPL"],
            ),
            missing_required_fields=["date_range"],
            response_intent={
                "kind": "clarification",
                "semantic_needs": ["period"],
            },
            language="es-419",
        )
    )

    assert question == repeated


def test_openrouter_clarifier_deduplicates_repeated_question_paragraph(
    monkeypatch,
) -> None:
    repeated = (
        "¿Qué período prefieres para la prueba de AAPL? Por ejemplo, dime un "
        "rango de fechas concreto o una ventana como últimos 3 años."
    )

    async def fake_json_schema(
        *, task, messages, schema_model, schema_name, model_name=None
    ):
        del task, messages, schema_model, schema_name, model_name
        return ClarificationResponse(
            question=f"{repeated} {repeated}",
            question_targets=["period"],
            directly_asks_user=True,
            detail_targets=["date_window"],
        )

    monkeypatch.setattr(
        "argus.agent_runtime.llm_clarifier.invoke_openrouter_json_schema",
        fake_json_schema,
    )

    clarifier = OpenRouterClarificationGenerator()
    question = clarifier(
        clarifier.request_model(
            current_user_message="Cambiar fechas",
            candidate_strategy_draft=StrategySummary(
                strategy_type="buy_and_hold",
                asset_universe=["AAPL"],
            ),
            missing_required_fields=["date_range"],
            response_intent={
                "kind": "clarification",
                "semantic_needs": ["period"],
            },
            language="es-419",
        )
    )

    assert question == repeated


def test_openrouter_clarifier_does_not_append_embedded_direct_question(
    monkeypatch,
) -> None:
    question_text = (
        "¿Qué período prefieres para la prueba de AAPL? Puedes darme fechas "
        "concretas o un rango como últimos 6 meses."
    )

    async def fake_json_schema(
        *, task, messages, schema_model, schema_name, model_name=None
    ):
        del task, messages, schema_model, schema_name, model_name
        return ClarificationResponse(
            question=question_text,
            direct_question="¿Qué período prefieres para la prueba de AAPL?",
            question_targets=["period"],
            directly_asks_user=True,
            detail_targets=["date_window"],
        )

    monkeypatch.setattr(
        "argus.agent_runtime.llm_clarifier.invoke_openrouter_json_schema",
        fake_json_schema,
    )

    clarifier = OpenRouterClarificationGenerator()
    rendered = clarifier(
        clarifier.request_model(
            current_user_message="Cambiar fechas",
            candidate_strategy_draft=StrategySummary(
                strategy_type="buy_and_hold",
                asset_universe=["AAPL"],
            ),
            missing_required_fields=["date_range"],
            response_intent={
                "kind": "clarification",
                "semantic_needs": ["period"],
            },
            language="es-419",
        )
    )

    assert rendered == question_text


def test_openrouter_clarifier_keeps_abbreviations_when_deduplicating_question(
    monkeypatch,
) -> None:
    async def fake_json_schema(
        *, task, messages, schema_model, schema_name, model_name=None
    ):
        del task, messages, schema_model, schema_name, model_name
        return ClarificationResponse(
            question=(
                "Happy to walk through a DCA plan. To set it up, I need the asset, "
                "date range, recurring purchase amount, and cadence (e.g., monthly). "
                "Which asset, date range, recurring purchase amount, and purchase "
                "cadence should I use for your DCA test?"
            ),
            direct_question=(
                "Which asset, date range, recurring purchase amount, and purchase "
                "cadence should I use for your DCA test?"
            ),
            question_targets=[
                "asset_target",
                "period",
                "sizing_amount",
                "schedule",
            ],
            directly_asks_user=True,
            detail_targets=[
                "asset",
                "date_window",
                "recurring_purchase_amount",
                "purchase_cadence",
            ],
        )

    monkeypatch.setattr(
        "argus.agent_runtime.llm_clarifier.invoke_openrouter_json_schema",
        fake_json_schema,
    )

    clarifier = OpenRouterClarificationGenerator()
    question = clarifier(
        clarifier.request_model(
            current_user_message="Walk me through a DCA",
            candidate_strategy_draft=StrategySummary(
                strategy_type="dca_accumulation",
            ),
            missing_required_fields=[
                "asset_universe",
                "date_range",
                "capital_amount",
                "cadence",
            ],
            response_intent={
                "kind": "clarification",
                "semantic_needs": [
                    "asset_target",
                    "period",
                    "sizing_amount",
                    "schedule",
                ],
            },
        )
    )

    assert question is not None
    assert "(e.g., monthly)." in question
    assert "e. g." not in question
    assert question.count("Which asset") == 1


def test_openrouter_clarifier_keeps_decimal_and_abbreviation_in_contract_context(
    monkeypatch,
) -> None:
    async def fake_json_schema(
        *, task, messages, schema_model, schema_name, model_name=None
    ):
        del task, messages, schema_model, schema_name, model_name
        return ClarificationResponse(
            question=(
                "Got it — LYFT with a $200.00 total budget, e.g., your planned "
                "cap. I need one more detail before this is runnable."
            ),
            direct_question=(
                "How much should each recurring purchase be, and how often should "
                "those purchases happen?"
            ),
            question_targets=["sizing_amount", "schedule"],
            directly_asks_user=True,
            detail_targets=["recurring_purchase_amount", "purchase_cadence"],
        )

    monkeypatch.setattr(
        "argus.agent_runtime.llm_clarifier.invoke_openrouter_json_schema",
        fake_json_schema,
    )

    clarifier = OpenRouterClarificationGenerator()
    question = clarifier(
        clarifier.request_model(
            current_user_message=(
                "I would like to invest in LYFT over 5 years feb 2020-feb 2025, "
                "$200.00 of capital"
            ),
            candidate_strategy_draft=StrategySummary(
                strategy_type="dca_accumulation",
                asset_universe=["LYFT"],
                asset_class="equity",
                date_range={"start": "2020-02-01", "end": "2025-02-28"},
                extra_parameters={"initial_capital": 200},
            ),
            missing_required_fields=["capital_amount", "cadence"],
            response_intent={
                "kind": "clarification",
                "semantic_needs": ["sizing_amount", "schedule"],
            },
        )
    )

    assert question is not None
    assert "$200.00 total budget" in question
    assert "e.g., your planned cap." in question
    assert "How much should each recurring purchase be" in question


def test_openrouter_clarifier_does_not_duplicate_dca_direct_question_when_first(
    monkeypatch,
) -> None:
    async def fake_json_schema(
        *, task, messages, schema_model, schema_name, model_name=None
    ):
        del task, messages, schema_model, schema_name, model_name
        return ClarificationResponse(
            question=(
                "How much should each recurring purchase be, and how often should "
                "those purchases happen? I can use that to make the DCA runnable."
            ),
            direct_question=(
                "How much should each recurring purchase be, and how often should "
                "those purchases happen?"
            ),
            question_targets=["sizing_amount", "schedule"],
            directly_asks_user=True,
            detail_targets=["recurring_purchase_amount", "purchase_cadence"],
        )

    monkeypatch.setattr(
        "argus.agent_runtime.llm_clarifier.invoke_openrouter_json_schema",
        fake_json_schema,
    )

    clarifier = OpenRouterClarificationGenerator()
    question = clarifier(
        clarifier.request_model(
            current_user_message=(
                "I would like to invest in LYFT over 5 years feb 2020-feb 2025, "
                "$200.00 of capital"
            ),
            candidate_strategy_draft=StrategySummary(
                strategy_type="dca_accumulation",
                asset_universe=["LYFT"],
                asset_class="equity",
                date_range={"start": "2020-02-01", "end": "2025-02-28"},
                extra_parameters={"initial_capital": 200},
            ),
            missing_required_fields=["capital_amount", "cadence"],
            response_intent={
                "kind": "clarification",
                "semantic_needs": ["sizing_amount", "schedule"],
            },
        )
    )

    assert question is not None
    assert question.count("How much should each recurring purchase be") == 1


def test_openrouter_clarifier_uses_missing_fields_for_dca_amount_and_cadence(
    monkeypatch,
) -> None:
    monkeypatch.setenv("CUADRAO_CHAT_MODEL", "chat/primary")
    monkeypatch.setenv("CUADRAO_CHAT_FALLBACK_MODEL", "chat/fallback")
    calls: list[str | None] = []

    async def fake_json_schema(
        *, task, messages, schema_model, schema_name, model_name=None
    ):
        del task, messages, schema_model, schema_name
        calls.append(model_name)
        if model_name is None:
            return ClarificationResponse(
                question=(
                    "Great, a 5-year DCA plan for LYFT. You mentioned a total budget. "
                    "How often would you like to make purchases?"
                ),
                direct_question="How often would you like to make purchases?",
                question_targets=["schedule"],
                directly_asks_user=True,
                detail_targets=["purchase_cadence"],
            )
        return ClarificationResponse(
            question=(
                "Great, a 5-year DCA plan for LYFT. You mentioned a total budget. "
                "I need the recurring purchase amount and cadence."
            ),
            direct_question=(
                "How much should each recurring purchase be, and how often should "
                "those purchases happen?"
            ),
            question_targets=["sizing_amount", "schedule"],
            directly_asks_user=True,
            detail_targets=["recurring_purchase_amount", "purchase_cadence"],
        )

    monkeypatch.setattr(
        "argus.agent_runtime.llm_clarifier.invoke_openrouter_json_schema",
        fake_json_schema,
    )

    clarifier = OpenRouterClarificationGenerator()
    question = clarifier(
        clarifier.request_model(
            current_user_message=(
                "I would like to invest in LYFT over 5 years feb 2020-feb 2025, "
                "$200,000 of capital"
            ),
            candidate_strategy_draft=StrategySummary(
                strategy_type="dca_accumulation",
                asset_universe=["LYFT"],
                asset_class="equity",
                date_range={"start": "2020-02-01", "end": "2025-02-28"},
            ),
            missing_required_fields=["cadence", "capital_amount"],
            response_intent={
                "kind": "clarification",
                "semantic_needs": ["schedule"],
            },
        )
    )

    assert question is not None
    assert "How much should each recurring purchase be" in question
    assert "how often should those purchases happen" in question
    assert calls == [None, "chat/fallback"]


def test_openrouter_clarifier_renders_dca_direct_question_when_wrapper_is_vague(
    monkeypatch,
) -> None:
    monkeypatch.setenv("CUADRAO_CHAT_MODEL", "chat/primary")
    monkeypatch.setenv("CUADRAO_CHAT_FALLBACK_MODEL", "chat/fallback")

    async def fake_json_schema(
        *, task, messages, schema_model, schema_name, model_name=None
    ):
        del task, messages, schema_model, schema_name, model_name
        return ClarificationResponse(
            question=(
                "I can test recurring buys for LYFT. I need one more detail before "
                "I can turn this into a backtest. How much would you like to invest "
                "each month?"
            ),
            direct_question="How much would you like to invest each month?",
            question_targets=["sizing_amount"],
            directly_asks_user=True,
            detail_targets=["recurring_purchase_amount"],
        )

    monkeypatch.setattr(
        "argus.agent_runtime.llm_clarifier.invoke_openrouter_json_schema",
        fake_json_schema,
    )

    clarifier = OpenRouterClarificationGenerator()
    question = clarifier(
        clarifier.request_model(
            current_user_message="what detail?",
            candidate_strategy_draft=StrategySummary(
                strategy_type="dca_accumulation",
                asset_universe=["LYFT"],
                cadence="monthly",
            ),
            missing_required_fields=["capital_amount"],
            response_intent={
                "kind": "clarification",
                "semantic_needs": ["sizing_amount"],
            },
        )
    )

    assert question is not None
    assert "How much would you like to invest each month?" in question
    assert question.count("How much would you like to invest each month?") == 1


def test_default_unsupported_strategy_options_are_concrete() -> None:
    contract = build_default_capability_contract()

    options = contract.get_simplification_options("unsupported_strategy_logic")
    labels = [option.label for option in options]

    assert labels == [
        "Use a supported RSI threshold rule",
        "Compare with buy and hold",
        "Use a supported moving-average crossover",
    ]


def test_clarify_stage_does_not_contain_slot_prompt_strings() -> None:
    source = Path("src/argus/agent_runtime/stages/clarify.py").read_text().lower()
    forbidden = [
        "what should trigger the buy",
        "which asset should i test",
        "what time period should i test",
        "how much should each recurring purchase be",
        "should i keep working on the current idea",
    ]
    for phrase in forbidden:
        assert phrase not in source


def test_confirm_stage_still_builds_confirmation_card() -> None:
    state = RunState.new(
        current_user_message="Backtest Tesla RSI",
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="indicator_threshold",
        strategy_thesis="Backtest Tesla RSI.",
        asset_universe=["TSLA"],
        asset_class="equity",
        date_range="last year",
        entry_logic="RSI drops below 30",
        exit_logic="RSI rises above 55",
        extra_parameters={
            "indicator": "rsi",
            "indicator_parameters": {"indicator": "rsi"},
        },
    )

    result = confirm_stage(state=state, contract=build_default_capability_contract())

    assert result.outcome == "await_approval"
    assert result.patch["assistant_prompt"] is None
    assert result.patch["confirmation_payload"]["strategy"]["asset_universe"] == ["TSLA"]
    assert result.patch["confirmation_payload"]["strategy"]["entry_logic"] == (
        "RSI drops below 30"
    )
    # #508: the confirm stage passes `assumptions` through untouched; the
    # confirmation card owns the visible strip via typed display facts.
    assert result.patch["candidate_strategy_draft"]["assumptions"] == []
    assert result.patch["confirmation_payload"]["strategy"]["assumptions"] == []


def test_confirm_stage_reconciles_effective_window_before_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.domain import market_data

    def fake_fetch(symbol: str, **_: object) -> pd.DataFrame:
        days = (
            ["2024-01-03", "2024-01-04", "2024-01-05"]
            if symbol == "AAPL"
            else [
                "2024-01-01",
                "2024-01-02",
                "2024-01-03",
                "2024-01-04",
                "2024-01-05",
            ]
        )
        index = pd.to_datetime(days, utc=True)
        close = pd.Series(range(100, 100 + len(index)), index=index, dtype=float)
        return pd.DataFrame(
            {
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1_000.0,
            },
            index=index,
        )

    monkeypatch.setattr(market_data, "fetch_ohlcv", fake_fetch)
    state = RunState.new(
        current_user_message="Hold AAPL from January 1 through January 5, 2024.",
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="buy_and_hold",
        strategy_thesis="Buy and hold AAPL.",
        asset_universe=["AAPL"],
        asset_class="equity",
        capital_amount=10_000,
        date_range={"start": "2024-01-01", "end": "2024-01-05"},
    )

    result = confirm_stage(state=state, contract=build_default_capability_contract())

    assert result.outcome == "await_approval"
    confirmation = result.patch["confirmation_payload"]
    assert confirmation["strategy"]["date_range"] == {
        "start": "2024-01-03",
        "end": "2024-01-05",
    }
    assert confirmation["launch_payload"]["requested_date_range"] == {
        "start": "2024-01-01",
        "end": "2024-01-05",
    }
    assert confirmation["launch_payload"]["date_range"] == {
        "start": "2024-01-03",
        "end": "2024-01-05",
    }
    assert confirmation["launch_payload"]["coverage_preflight"]["outcome"] == (
        "adjusted_coverage"
    )
    assert confirmation["validation"]["date_adjusted"] is True


def test_confirm_stage_preserves_requested_window_after_non_date_edit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.agent_runtime.stages import confirm as confirm_module
    from argus.agent_runtime.stages.execute import _launch_payload
    from argus.domain import market_data

    def fake_fetch(symbol: str, **_: object) -> pd.DataFrame:  # noqa: ARG001
        index = pd.to_datetime(
            ["2024-01-03", "2024-01-04", "2024-01-05"],
            utc=True,
        )
        close = pd.Series([100.0, 101.0, 102.0], index=index)
        return pd.DataFrame(
            {
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1_000.0,
            },
            index=index,
        )

    monkeypatch.setattr(market_data, "fetch_ohlcv", fake_fetch)
    monkeypatch.setattr(confirm_module, "_market_clock_for_strategy", lambda _: None)
    first_state = RunState.new(
        current_user_message="Hold AAPL from January 1 through January 5, 2024.",
        recent_thread_history=[],
    )
    first_state.candidate_strategy_draft = StrategySummary(
        strategy_type="buy_and_hold",
        strategy_thesis="Buy and hold AAPL.",
        asset_universe=["AAPL"],
        asset_class="equity",
        capital_amount=10_000,
        date_range={"start": "2024-01-01", "end": "2024-01-05"},
    )
    first = confirm_stage(
        state=first_state,
        contract=build_default_capability_contract(),
    )
    edited = apply_artifact_patch(
        StrategySummary.model_validate(first.patch["candidate_strategy_draft"]),
        ArtifactPatch(source="user_patch", capital_amount=20_000),
    )
    second_state = RunState.new(
        current_user_message="Use $20,000 instead.",
        recent_thread_history=[],
    )
    second_state.candidate_strategy_draft = edited

    second = confirm_stage(
        state=second_state,
        contract=build_default_capability_contract(),
    )

    assert second.outcome == "await_approval"
    confirmation = second.patch["confirmation_payload"]
    assert confirmation["launch_payload"]["requested_date_range"] == {
        "start": "2024-01-01",
        "end": "2024-01-05",
    }
    assert confirmation["launch_payload"]["date_range"] == {
        "start": "2024-01-03",
        "end": "2024-01-05",
    }
    second_state.confirmation_payload = confirmation
    assert _launch_payload(second_state)["requested_date_range"] == {
        "start": "2024-01-01",
        "end": "2024-01-05",
    }

    date_edited = apply_artifact_patch(
        StrategySummary.model_validate(first.patch["candidate_strategy_draft"]),
        ArtifactPatch(
            source="user_patch",
            date_range={"start": "2024-01-04", "end": "2024-01-05"},
        ),
    )
    date_edit_state = RunState.new(
        current_user_message="Use January 4 through January 5 instead.",
        recent_thread_history=[],
    )
    date_edit_state.candidate_strategy_draft = date_edited

    date_edit_result = confirm_stage(
        state=date_edit_state,
        contract=build_default_capability_contract(),
    )

    assert date_edit_result.patch["confirmation_payload"]["launch_payload"][
        "requested_date_range"
    ] == {"start": "2024-01-04", "end": "2024-01-05"}


def test_confirm_stage_returns_typed_recovery_without_runnable_card_when_no_common_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.domain import market_data

    def fake_fetch(symbol: str, **_: object) -> pd.DataFrame:
        days = (
            ["2024-01-01", "2024-01-02"]
            if symbol == "AAPL"
            else ["2024-01-04", "2024-01-05"]
        )
        index = pd.to_datetime(days, utc=True)
        close = pd.Series(range(100, 100 + len(index)), index=index, dtype=float)
        return pd.DataFrame(
            {
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1_000.0,
            },
            index=index,
        )

    monkeypatch.setattr(market_data, "fetch_ohlcv", fake_fetch)
    state = RunState.new(
        current_user_message="Hold AAPL from January 1 through January 5, 2024.",
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="buy_and_hold",
        strategy_thesis="Buy and hold AAPL.",
        asset_universe=["AAPL"],
        asset_class="equity",
        capital_amount=10_000,
        date_range={"start": "2024-01-01", "end": "2024-01-05"},
    )
    state.optional_parameter_status = {"fees": 0.001, "slippage": 0.0005}

    result = confirm_stage(state=state, contract=build_default_capability_contract())

    assert result.outcome == "needs_clarification"
    assert "confirmation_payload" not in result.patch
    assert "unsupported_constraints" not in result.patch["optional_parameter_status"]
    assert result.patch["optional_parameter_status"]["fees"] == 0.001
    assert result.patch["optional_parameter_status"]["slippage"] == 0.0005
    recovery = result.patch["optional_parameter_status"]["coverage_recovery"]
    assert recovery == {
        "code": "no_common_data_window",
        "requested_date_range": {
            "start": "2024-01-01",
            "end": "2024-01-05",
        },
        "asset_universe": ["AAPL"],
        "benchmark_symbol": "SPY",
    }

    clarify_state = state.model_copy(update=result.patch)
    clarifier = RecordingClarifier(
        "The shared history is not usable. Which part should we change?"
    )
    clarified = clarify_stage(
        state=clarify_state,
        contract=build_default_capability_contract(),
        clarification_generator=clarifier,
        language="en",
    )

    assert clarified.outcome == "await_user_reply"
    assert clarified.patch["assistant_prompt"] == (
        "The shared history is not usable. Which part should we change?"
    )
    response_intent = clarified.patch["response_intent"]
    clarification = clarified.patch["clarification"]
    assert clarification["kind"] == "coverage_recovery"
    assert clarification["prompt_source"] == "llm_generated"
    assert clarification["options"] == response_intent["options"]
    assert response_intent["kind"] == "coverage_recovery"
    assert response_intent["facts"]["coverage"] == recovery
    assert response_intent["facts"]["preserved_optional_parameter_status"] == {
        "fees": 0.001,
        "slippage": 0.0005,
    }
    assert response_intent["options"] == [
        {
            "id": "change_dates",
            "replacement_values": {"requested_field": "date_range"},
        },
        {
            "id": "change_asset",
            "replacement_values": {"requested_field": "asset_universe"},
        },
        {
            "id": "change_benchmark",
            "replacement_values": {"requested_field": "comparison_baseline"},
        },
    ]
    assert all("label" not in option for option in response_intent["options"])
    assert clarifier.requests[0].unsupported_constraints == []


def test_confirm_stage_fails_closed_when_live_equity_calendar_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.agent_runtime.stages import confirm as confirm_module
    from argus.domain.engine_launch import adapter
    from argus.domain.market_data import capabilities, provider

    monkeypatch.setenv("ARGUS_MARKET_DATA_PROVIDER_MODE", "live_provider")
    dates = [
        "2024-12-24",
        "2024-12-26",
        "2024-12-27",
        "2024-12-30",
        "2024-12-31",
        "2025-01-02",
    ]
    index = pd.to_datetime(dates, utc=True)
    close = pd.Series(range(100, 106), index=index, dtype=float)
    bars = pd.DataFrame(
        {
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1_000.0,
        },
        index=index,
    )
    calendar_calls = 0

    def unavailable_calendar(**_: object):
        nonlocal calendar_calls
        calendar_calls += 1
        raise ValueError("calendar unavailable")

    monkeypatch.setattr(provider, "_fetch_bars_with_ttl", lambda **_: bars.copy())
    monkeypatch.setattr(
        capabilities,
        "fetch_alpaca_market_calendar",
        unavailable_calendar,
    )
    monkeypatch.setattr(confirm_module, "_market_clock_for_strategy", lambda _: None)
    monkeypatch.setattr(
        adapter,
        "validate_request_symbols",
        lambda _: adapter.RequestSymbolValidationResult(
            outcome="resolved",
            symbols=("AAPL",),
            asset_class="equity",
        ),
    )
    monkeypatch.setattr(
        adapter,
        "validate_request_benchmark",
        lambda *_, **__: adapter.BenchmarkSymbolValidationResult(
            outcome="resolved",
            benchmark_symbol="SPY",
            asset_class="equity",
        ),
    )
    state = RunState.new(
        current_user_message="Hold AAPL across the 2024 year-end holidays.",
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="buy_and_hold",
        strategy_thesis="Buy and hold AAPL.",
        asset_universe=["AAPL"],
        asset_class="equity",
        capital_amount=10_000,
        date_range={"start": dates[0], "end": dates[-1]},
    )

    result = confirm_stage(state=state, contract=build_default_capability_contract())

    assert result.outcome == "needs_clarification"
    assert "confirmation_payload" not in result.patch
    assert result.patch["optional_parameter_status"]["coverage_recovery"]["code"] == (
        "market_data_unavailable"
    )
    assert calendar_calls == 1


def test_confirm_stage_returns_coverage_recovery_for_sparse_common_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.domain import market_data

    def fake_fetch(symbol: str, **_: object) -> pd.DataFrame:  # noqa: ARG001
        index = pd.to_datetime(["2024-01-01", "2024-01-10"], utc=True)
        close = pd.Series([100.0, 101.0], index=index)
        return pd.DataFrame(
            {
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1_000.0,
            },
            index=index,
        )

    monkeypatch.setattr(market_data, "fetch_ohlcv", fake_fetch)
    state = RunState.new(
        current_user_message="Hold AAPL from January 1 through January 10, 2024.",
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="buy_and_hold",
        strategy_thesis="Buy and hold AAPL.",
        asset_universe=["AAPL"],
        asset_class="equity",
        capital_amount=10_000,
        date_range={"start": "2024-01-01", "end": "2024-01-10"},
    )

    result = confirm_stage(state=state, contract=build_default_capability_contract())

    assert result.outcome == "needs_clarification"
    assert "confirmation_payload" not in result.patch
    assert result.patch["optional_parameter_status"]["coverage_recovery"]["code"] == (
        "insufficient_common_data"
    )


def test_degraded_coverage_recovery_emits_typed_localizable_sidecar() -> None:
    state = RunState.new(
        current_user_message="Prueba AAPL en ese periodo.",
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="buy_and_hold",
        asset_universe=["AAPL"],
        asset_class="equity",
        date_range={"start": "2024-01-01", "end": "2024-01-05"},
    )
    state.optional_parameter_status = {
        "coverage_recovery": {
            "code": "no_common_data_window",
            "requested_date_range": {
                "start": "2024-01-01",
                "end": "2024-01-05",
            },
            "asset_universe": ["AAPL"],
            "benchmark_symbol": "SPY",
        }
    }

    result = clarify_stage(
        state=state,
        contract=build_default_capability_contract(),
        clarification_generator=None,
        language="es-419",
    )

    assert result.outcome == "await_user_reply"
    assert result.patch["clarification"] == {
        "kind": "coverage_recovery",
        "reason_code": "no_common_data_window",
        "prompt_source": "degraded_fallback",
        "requested_field": None,
        "requested_fields": [
            "date_range",
            "asset_universe",
            "comparison_baseline",
        ],
        "semantic_needs": ["simplification_choice"],
        "payload": {
            "strategy": state.candidate_strategy_draft.model_dump(mode="python"),
            "coverage": state.optional_parameter_status["coverage_recovery"],
        },
        "options": [
            {
                "id": "change_dates",
                "replacement_values": {"requested_field": "date_range"},
            },
            {
                "id": "change_asset",
                "replacement_values": {"requested_field": "asset_universe"},
            },
            {
                "id": "change_benchmark",
                "replacement_values": {"requested_field": "comparison_baseline"},
            },
        ],
    }


def test_confirm_stage_revalidates_strategy_viability_after_window_adjustment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.agent_runtime.stages import confirm as confirm_module
    from argus.domain import market_data

    def fake_fetch(symbol: str, **_: object) -> pd.DataFrame:
        days = (
            [f"2024-01-{day:02d}" for day in range(22, 32)]
            if symbol == "AAPL"
            else [f"2024-01-{day:02d}" for day in range(1, 32)]
        )
        index = pd.to_datetime(days, utc=True)
        close = pd.Series(range(100, 100 + len(index)), index=index, dtype=float)
        return pd.DataFrame(
            {
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1_000.0,
            },
            index=index,
        )

    monkeypatch.setattr(market_data, "fetch_ohlcv", fake_fetch)
    monkeypatch.setattr(confirm_module, "_market_clock_for_strategy", lambda _: None)
    state = RunState.new(
        current_user_message="Test AAPL RSI during January 2024.",
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="indicator_threshold",
        strategy_thesis="Test AAPL when RSI drops below 30.",
        asset_universe=["AAPL"],
        asset_class="equity",
        capital_amount=10_000,
        date_range={"start": "2024-01-01", "end": "2024-01-31"},
        entry_logic="RSI drops below 30",
        exit_logic="RSI rises above 55",
        extra_parameters={
            "indicator": "rsi",
            "indicator_parameters": {"indicator": "rsi", "indicator_period": 14},
        },
    )

    result = confirm_stage(state=state, contract=build_default_capability_contract())

    assert result.outcome == "needs_clarification"
    assert "confirmation_payload" not in result.patch
    assert result.patch["requested_field"] == "date_range"
    constraint = result.patch["optional_parameter_status"]["unsupported_constraints"][0]
    assert constraint["category"] == "data_window_too_short_for_rule"


def test_confirm_stage_preserves_explicit_benchmark_as_typed_baseline() -> None:
    state = RunState.new(
        current_user_message=(
            "If I bought AAPL at the start of 2024 through the end of 2024, "
            "how did it compare with QQQ?"
        ),
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="buy_and_hold",
        strategy_thesis="Compare Apple buy and hold with QQQ.",
        asset_universe=["AAPL"],
        asset_class="equity",
        comparison_baseline="QQQ",
        date_range={"start": "2024-01-01", "end": "2024-12-31"},
    )

    result = confirm_stage(state=state, contract=build_default_capability_contract())

    assert result.outcome == "await_approval"
    draft = result.patch["candidate_strategy_draft"]
    assert draft["comparison_baseline"] == "QQQ"
    assert result.patch["confirmation_payload"]["launch_payload"]["benchmark_symbol"] == (
        "QQQ"
    )


def test_confirm_stage_persists_default_benchmark_in_strategy_payload() -> None:
    state = RunState.new(
        current_user_message=(
            "Let's test holding AAPL, MSFT, and TSLA from 2023 to date with 100k."
        ),
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="buy_and_hold",
        strategy_thesis="Buy and hold a large-cap tech basket.",
        asset_universe=["AAPL", "MSFT", "TSLA"],
        asset_class="equity",
        date_range={"start": "2023-01-01", "end": "2026-06-19"},
        capital_amount=100000,
    )

    result = confirm_stage(state=state, contract=build_default_capability_contract())

    assert result.outcome == "await_approval"
    confirmation_payload = result.patch["confirmation_payload"]
    strategy = confirmation_payload["strategy"]
    assert strategy["asset_universe"] == ["AAPL", "MSFT", "TSLA"]
    assert strategy["comparison_baseline"] == "SPY"
    assert confirmation_payload["launch_payload"]["benchmark_symbol"] == "SPY"


def test_confirm_stage_persists_runtime_language_in_launch_payload() -> None:
    state = RunState.new(
        current_user_message="Prueba comprar y mantener AMZN y NFLX desde 2023.",
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="buy_and_hold",
        strategy_thesis="Comprar y mantener AMZN y NFLX.",
        asset_universe=["AMZN", "NFLX"],
        asset_class="equity",
        date_range={"start": "2023-01-01", "end": "2026-06-19"},
        capital_amount=100000,
        comparison_baseline="SPY",
    )

    result = confirm_stage(
        state=state,
        contract=build_default_capability_contract(),
        language="es-419",
    )

    strategy = result.patch["confirmation_payload"]["strategy"]
    launch_payload = result.patch["confirmation_payload"]["launch_payload"]
    assert result.outcome == "await_approval"
    assert strategy["extra_parameters"]["language"] == "es-419"
    assert launch_payload["language"] == "es-419"


def test_confirm_stage_resolves_structured_month_range_into_launch_payload() -> None:
    state = RunState.new(
        current_user_message=(
            "Can you set a strategy where I buy AAPL GOOG at $200 every month "
            "for Jan 2021-Jan 2024?"
        ),
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        raw_user_phrasing=state.current_user_message,
        strategy_type="dca_accumulation",
        strategy_thesis="Accumulate AAPL and GOOG monthly over the specified period.",
        asset_universe=["AAPL", "GOOG"],
        asset_class="equity",
        capital_amount=200,
        cadence="monthly",
        date_range={"start": "2021-01", "end": "2024-01"},
    )

    result = confirm_stage(state=state, contract=build_default_capability_contract())

    assert result.outcome == "await_approval"
    confirmation_payload = result.patch["confirmation_payload"]
    assert confirmation_payload["launch_payload"]["date_range"] == {
        "start": "2021-01-01",
        "end": "2024-01-31",
    }
    assert confirmation_payload["validation"]["status"] == "ready_to_run"


def test_confirm_stage_marks_daily_today_endpoint_as_latest_complete_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import datetime

    from argus.agent_runtime.stages import confirm as confirm_module
    from argus.domain.market_data.capabilities import MarketClockSnapshot

    monkeypatch.setattr(
        confirm_module,
        "_today",
        lambda: date(2026, 6, 3),
        raising=False,
    )
    monkeypatch.setattr(
        confirm_module,
        "_market_clock_for_strategy",
        lambda _: MarketClockSnapshot(
            provider="alpaca",
            timestamp=datetime(2026, 6, 3, 8, 0),
            is_open=False,
            next_open=datetime(2026, 6, 3, 9, 30),
            next_close=datetime(2026, 6, 3, 16, 0),
            is_market_day=True,
        ),
        raising=False,
    )
    state = RunState.new(
        current_user_message=(
            "Let's see what an investment of 500 in NU could have made this "
            "year so far."
        ),
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        raw_user_phrasing=state.current_user_message,
        strategy_type="buy_and_hold",
        strategy_thesis="Buy and hold NU this year so far.",
        asset_universe=["NU"],
        asset_class="equity",
        capital_amount=5000,
        date_range={"start": "2026-01-01", "end": "2026-06-03"},
    )

    result = confirm_module.confirm_stage(
        state=state,
        contract=build_default_capability_contract(),
    )

    assert result.outcome == "await_approval"
    confirmation_payload = result.patch["confirmation_payload"]
    strategy = confirmation_payload["strategy"]
    launch_payload = confirmation_payload["launch_payload"]

    assert strategy["date_range"] == {"start": "2026-01-01", "end": "2026-06-02"}
    assert launch_payload["date_range"] == {
        "start": "2026-01-01",
        "end": "2026-06-02",
    }
    assert launch_payload["requested_date_range"] == {
        "start": "2026-01-01",
        "end": "2026-06-03",
    }
    assert launch_payload["coverage_preflight"]["requested_date_range"] == {
        "start": "2026-01-01",
        "end": "2026-06-03",
    }
    assert launch_payload["coverage_preflight"]["effective_date_range"] == {
        "start": "2026-01-01",
        "end": "2026-06-02",
    }
    adjustment = strategy["extra_parameters"]["data_availability_adjustment"]
    assert adjustment == {
        "kind": "latest_complete_daily_data",
        "original_end": "2026-06-03",
        "provider": "alpaca",
        "through": "2026-06-02",
        "timeframe": "1D",
    }
    assert confirmation_payload["validation"]["status"] == "ready_to_run"
    assert confirmation_payload["validation"]["date_adjusted"] is True


def test_confirm_stage_clears_stale_latest_complete_data_adjustment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.agent_runtime.stages import confirm as confirm_module

    monkeypatch.setattr(
        confirm_module,
        "_today",
        lambda: date(2026, 6, 3),
        raising=False,
    )
    state = RunState.new(
        current_user_message="Adjust the end date to June 1, 2026.",
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="buy_and_hold",
        strategy_thesis="Buy and hold NU this year so far.",
        asset_universe=["NU"],
        asset_class="equity",
        capital_amount=5000,
        date_range={"start": "2026-01-01", "end": "2026-06-01"},
        extra_parameters={
            "data_availability_adjustment": {
                "kind": "latest_complete_daily_data",
                "original_end": "2026-06-03",
                "provider": "alpaca",
                "through": "2026-06-02",
                "timeframe": "1D",
            },
        },
    )

    result = confirm_module.confirm_stage(
        state=state,
        contract=build_default_capability_contract(),
    )

    assert result.outcome == "await_approval"
    confirmation_payload = result.patch["confirmation_payload"]
    strategy = confirmation_payload["strategy"]

    assert strategy["date_range"] == {"start": "2026-01-01", "end": "2026-06-01"}
    assert "data_availability_adjustment" not in strategy.get("extra_parameters", {})
    assert confirmation_payload["validation"]["date_adjusted"] is False


def test_confirm_stage_blocks_far_future_date_instead_of_latest_data_clamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.agent_runtime.stages import confirm as confirm_module

    monkeypatch.setattr(
        confirm_module,
        "_today",
        lambda: date(2026, 6, 3),
        raising=False,
    )
    state = RunState.new(
        current_user_message="Backtest NU through 2035.",
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        raw_user_phrasing=state.current_user_message,
        strategy_type="buy_and_hold",
        strategy_thesis="Buy and hold NU through 2035.",
        asset_universe=["NU"],
        asset_class="equity",
        capital_amount=5000,
        date_range={"start": "2026-01-01", "end": "2035-12-31"},
    )

    result = confirm_module.confirm_stage(
        state=state,
        contract=build_default_capability_contract(),
    )

    assert result.outcome == "needs_clarification"
    assert "confirmation_payload" not in result.patch
    constraint = result.patch["optional_parameter_status"]["unsupported_constraints"][0]
    assert constraint["category"] == "future_date_window"
    assert "latest available data" in constraint["explanation"]


def test_confirm_stage_blocks_carried_dca_cap_before_ready_card() -> None:
    state = RunState.new(
        current_user_message=(
            "what if I bought $125 of BTC every two weeks from 2022 through "
            "2023 with a $3000 cap?"
        ),
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="dca_accumulation",
        strategy_thesis="Recurring buys for BTC with a budget cap.",
        asset_universe=["BTC"],
        asset_class="crypto",
        date_range={"start": "2022-01-01", "end": "2023-12-31"},
        capital_amount=125,
        cadence="biweekly",
        extra_parameters={
            "recurring_contribution": 125,
            "total_budget": 3000,
            "field_provenance": {
                "capital_amount": "recurring_contribution",
                "total_capital": "cap",
                "cadence": "explicit_user",
            },
        },
    )
    state.optional_parameter_status = {
        "unsupported_constraints": [
            {
                "category": "unsupported_dca_contribution_ceiling",
                "raw_value": "$3,000 cap",
                "explanation": (
                    "The recurring-buy launch can use the per-buy amount and "
                    "cadence, but it cannot enforce a total cap yet."
                ),
                "simplification_options": [
                    {"label": "Run recurring buys only"},
                    {"label": "Adjust the recurring contribution"},
                ],
            }
        ]
    }

    result = confirm_stage(state=state, contract=build_default_capability_contract())

    assert result.outcome == "needs_clarification"
    assert "confirmation_payload" not in result.patch
    assert result.patch["requested_field"] == "unsupported_constraints"
    constraint = result.patch["optional_parameter_status"]["unsupported_constraints"][0]
    assert constraint["category"] == "unsupported_dca_contribution_ceiling"
    assert any(
        option["label"] == "Run recurring buys only"
        for option in constraint["simplification_options"]
    )


def test_confirm_stage_does_not_require_thesis_for_buy_and_hold() -> None:
    state = RunState.new(
        current_user_message="Backtest buy and hold Apple over the past year.",
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        raw_user_phrasing="Backtest buy and hold Apple over the past year.",
        strategy_type="buy_and_hold",
        strategy_thesis=None,
        asset_universe=["AAPL"],
        asset_class="equity",
        date_range="past year",
    )

    result = confirm_stage(state=state, contract=build_default_capability_contract())

    assert result.outcome == "await_approval"
    assert result.patch["missing_required_fields"] == []
    strategy = result.patch["confirmation_payload"]["strategy"]
    assert strategy["strategy_type"] == "buy_and_hold"
    assert strategy["asset_universe"] == ["AAPL"]


def test_confirm_stage_does_not_require_thesis_for_executable_artifact_patch() -> None:
    state = RunState.new(
        current_user_message="do the date range October 2019 to October 2025",
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="dca_accumulation",
        strategy_thesis=None,
        asset_universe=["AAPL", "GOOG"],
        asset_class="equity",
        timeframe="1D",
        cadence="monthly",
        date_range={"start": "2019-10-01", "end": "2025-10-31"},
        capital_amount=200,
        entry_rule={"type": "periodic_accumulation", "cadence": "monthly"},
        exit_rule={"type": "end_of_period"},
        comparison_baseline="SPY",
        extra_parameters={
            "artifact_patch": {
                "source": "user_patch",
                "changed_fields": ["date_range"],
            }
        },
    )

    result = confirm_stage(state=state, contract=build_default_capability_contract())

    assert result.outcome == "await_approval"
    assert result.patch["missing_required_fields"] == []
    strategy = result.patch["confirmation_payload"]["strategy"]
    assert strategy["asset_universe"] == ["AAPL", "GOOG"]
    assert strategy["date_range"] == {"start": "2019-10-01", "end": "2025-10-31"}
    assert strategy["capital_amount"] == 200


def test_confirm_stage_uses_product_language_for_data_window_limits() -> None:
    from argus.domain.market_data import shared_history_start

    state = RunState.new(
        current_user_message="Backtest Apple since 2015.",
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="buy_and_hold",
        strategy_thesis="Buy and hold Apple.",
        asset_universe=["AAPL"],
        asset_class="equity",
        date_range={"start": "2015-01-01", "end": "2016-01-15"},
    )

    result = confirm_stage(state=state, contract=build_default_capability_contract())

    assert result.outcome == "needs_clarification"
    assert result.patch["assistant_prompt"] is None
    assert result.patch["requested_field"] == "date_range"
    constraint = result.patch["optional_parameter_status"]["unsupported_constraints"][0]
    assert constraint["category"] == "data_window_unavailable"
    assert "provider" not in constraint["explanation"].lower()
    # The provider floor is never offered as the asset's start.
    assert not any(
        "2016" in option["label"] for option in constraint["simplification_options"]
    )
    assert (
        constraint["available_from"]
        == shared_history_start(["AAPL", "SPY"], "equity").isoformat()
    )


def test_confirm_stage_prioritizes_data_window_before_missing_rule_details() -> None:
    state = RunState.new(
        current_user_message="test EUR/USD 1h from Jan 2025 to Feb 2025",
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        strategy_thesis="Test EUR/USD with a long hourly window.",
        asset_universe=["EURUSD"],
        asset_class="currency_pair",
        timeframe="1h",
        date_range={"start": "2025-01-01", "end": "2025-02-15"},
    )

    result = confirm_stage(state=state, contract=build_default_capability_contract())

    assert result.outcome == "needs_clarification"
    assert result.patch["assistant_prompt"] is None
    assert result.patch["requested_field"] == "date_range"
    assert result.patch["missing_required_fields"] == ["date_range"]
    constraints = result.patch["optional_parameter_status"]["unsupported_constraints"]
    assert constraints[0]["category"] == "data_window_unavailable"


def test_confirm_stage_resolves_indicator_from_strategy_type_alias() -> None:
    state = RunState.new(
        current_user_message="Backtest Tesla RSI",
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="rsi_threshold",
        strategy_thesis="Backtest Tesla RSI.",
        asset_universe=["TSLA"],
        asset_class="equity",
        date_range="last year",
        entry_logic="RSI drops below 30",
        exit_logic="RSI rises above 55",
    )

    result = confirm_stage(state=state, contract=build_default_capability_contract())

    launch_payload = result.patch["confirmation_payload"]["launch_payload"]
    assert result.outcome == "await_approval"
    assert launch_payload["strategy_type"] == "indicator_threshold"
    assert launch_payload["entry_rule"]["indicator"] == "rsi"
    assert launch_payload["exit_rule"]["indicator"] == "rsi"


def test_confirm_stage_persists_validated_launch_payload_before_ready() -> None:
    state = RunState.new(
        current_user_message="Backtest Tesla RSI",
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="indicator_threshold",
        strategy_thesis="Backtest Tesla RSI.",
        asset_universe=["TSLA"],
        asset_class="equity",
        date_range="last year",
        entry_logic="RSI(14) <= 20",
        exit_logic="RSI(14) >= 60",
        extra_parameters={
            "indicator": "rsi",
            "indicator_parameters": {
                "indicator": "rsi",
                "entry_threshold": 20,
                "exit_threshold": 60,
            },
        },
    )

    result = confirm_stage(state=state, contract=build_default_capability_contract())

    launch_payload = result.patch["confirmation_payload"]["launch_payload"]
    assert result.outcome == "await_approval"
    assert launch_payload["strategy_type"] == "indicator_threshold"
    assert launch_payload["symbols"] == ["TSLA"]
    assert launch_payload["entry_rule"] == {
        "indicator": "rsi",
        "operator": "below",
        "period": 14,
        "threshold": 20.0,
    }
    assert launch_payload["exit_rule"] == {
        "indicator": "rsi",
        "operator": "above",
        "period": 14,
        "threshold": 60.0,
    }
    assert launch_payload["parameters"] == {}


def test_confirm_stage_preserves_strategy_language_in_launch_payload() -> None:
    state = RunState.new(
        current_user_message=(
            "Compra y mantén ETH de enero de 2024 hasta marzo de 2024 con 100000"
        ),
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="buy_and_hold",
        strategy_thesis="Comprar y mantener ETH.",
        asset_universe=["ETH"],
        asset_class="crypto",
        capital_amount=100000,
        date_range={"start": "2024-01-01", "end": "2024-03-31"},
        extra_parameters={"language": "es-419"},
    )

    result = confirm_stage(state=state, contract=build_default_capability_contract())

    launch_payload = result.patch["confirmation_payload"]["launch_payload"]
    assert result.outcome == "await_approval"
    assert launch_payload["language"] == "es-419"


def test_confirm_stage_prefers_structured_indicator_parameters_for_launch() -> None:
    state = RunState.new(
        current_user_message="Use RSI entry 20 exit 60.",
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="indicator_threshold",
        strategy_thesis="Backtest Tesla RSI.",
        asset_universe=["TSLA"],
        asset_class="equity",
        date_range="last year",
        entry_logic="RSI threshold entry",
        exit_logic="RSI threshold exit",
        extra_parameters={
            "indicator": "rsi",
            "indicator_parameters": {
                "indicator": "rsi",
                "entry_threshold": 20,
                "exit_threshold": 60,
            },
        },
    )

    result = confirm_stage(state=state, contract=build_default_capability_contract())

    launch_payload = result.patch["confirmation_payload"]["launch_payload"]
    assert result.outcome == "await_approval"
    assert launch_payload["entry_rule"] == {
        "indicator": "rsi",
        "operator": "below",
        "period": 14,
        "threshold": 20.0,
    }
    assert launch_payload["exit_rule"] == {
        "indicator": "rsi",
        "operator": "above",
        "period": 14,
        "threshold": 60.0,
    }


def test_confirm_stage_keeps_date_edit_visible_card_and_launch_payload_in_sync() -> None:
    from argus.api.chat.confirmation import runtime_confirmation_card

    state = RunState.new(
        current_user_message=(
            "change the period to show march 2 of 2025 until april 14 of 2026"
        ),
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="buy_and_hold",
        strategy_thesis="Buy and hold selected equities.",
        asset_universe=["AAPL", "GOOG", "TSLA"],
        asset_class="equity",
        date_range={"start": "2024-01-01", "end": "2024-12-31"},
        capital_amount=100000,
        extra_parameters={
            "date_range_intent": {
                "kind": "explicit_range",
                "start": "2025-03-02",
                "end": "2026-04-14",
                "confidence": 1.0,
                "evidence": (
                    "change the period to show march 2 of 2025 " "until april 14 of 2026"
                ),
            },
            "field_provenance": {"date_range": "explicit_user"},
        },
    )

    result = confirm_stage(state=state, contract=build_default_capability_contract())

    confirmation_payload = result.patch["confirmation_payload"]
    assert result.outcome == "await_approval"
    assert confirmation_payload["strategy"]["date_range"] == {
        "start": "2025-03-02",
        "end": "2026-04-14",
    }
    assert confirmation_payload["launch_payload"]["date_range"] == {
        "start": "2025-03-02",
        "end": "2026-04-14",
    }

    card = runtime_confirmation_card(
        {
            "stage_outcome": "await_approval",
            "confirmation_payload": confirmation_payload,
        }
    )
    assert card is not None
    assert card["status"] == "ready_to_run"
    assert any(action["type"] == "run_backtest" for action in card["actions"])
    assert next(row["value"] for row in card["rows"] if row["key"] == "period") == (
        "March 2, 2025 - April 14, 2026"
    )


def test_confirm_stage_clears_stale_rule_spec_after_rsi_threshold_edit() -> None:
    from argus.api.chat.confirmation import runtime_confirmation_card

    stale_rule_spec = {
        "entry": {
            "conditions": [
                {
                    "left": {"kind": "indicator", "key": "rsi", "period": 14},
                    "operator": "lt",
                    "right": {"kind": "constant", "value": 30},
                }
            ]
        },
        "exit": {
            "conditions": [
                {
                    "left": {"kind": "indicator", "key": "rsi", "period": 14},
                    "operator": "gt",
                    "right": {"kind": "constant", "value": 70},
                }
            ]
        },
    }
    state = RunState.new(
        current_user_message="baja la entrada RSI a 20 y la salida a 60",
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="indicator_threshold",
        strategy_thesis="Backtest Tesla RSI.",
        asset_universe=["TSLA"],
        asset_class="equity",
        date_range={"start": "2024-01-01", "end": "2024-12-31"},
        capital_amount=1000,
        entry_logic="Buy when RSI(14) drops to 20 or below",
        exit_logic="Sell when RSI(14) rises to 60 or above",
        rule_spec=stale_rule_spec,
        extra_parameters={
            "indicator": "rsi",
            "indicator_parameters": {
                "indicator": "rsi",
                "indicator_period": 14,
                "entry_threshold": 20,
                "exit_threshold": 60,
            },
            "field_provenance": {
                "entry_threshold": "explicit_user",
                "exit_threshold": "explicit_user",
            },
        },
    )

    result = confirm_stage(state=state, contract=build_default_capability_contract())

    confirmation_payload = result.patch["confirmation_payload"]
    strategy = confirmation_payload["strategy"]
    launch_payload = confirmation_payload["launch_payload"]
    assert result.outcome == "await_approval"
    assert strategy.get("rule_spec") is None
    assert launch_payload["strategy_type"] == "indicator_threshold"
    assert launch_payload["rule_spec"] is None
    assert launch_payload["entry_rule"]["threshold"] == 20.0
    assert launch_payload["exit_rule"]["threshold"] == 60.0

    card = runtime_confirmation_card(
        {
            "stage_outcome": "await_approval",
            "confirmation_payload": confirmation_payload,
        }
    )
    assert card is not None
    assert card["status"] == "ready_to_run"
    assert any(action["type"] == "run_backtest" for action in card["actions"])


def test_confirm_stage_prefers_typed_indicator_overrides_over_default_bundle() -> None:
    state = RunState.new(
        current_user_message="Use RSI entry 20 exit 60.",
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="indicator_threshold",
        strategy_thesis="Backtest Tesla RSI.",
        asset_universe=["TSLA"],
        asset_class="equity",
        date_range="last year",
        entry_logic="RSI threshold entry",
        exit_logic="RSI threshold exit",
        extra_parameters={
            "indicator": "rsi",
            "entry_threshold": 20,
            "exit_threshold": 60,
            "field_provenance": {
                "entry_threshold": "user",
                "exit_threshold": "user",
            },
            "indicator_parameters": {
                "indicator": "rsi",
                "indicator_period": 14,
                "entry_threshold": 30,
                "exit_threshold": 55,
            },
        },
    )

    result = confirm_stage(state=state, contract=build_default_capability_contract())

    launch_payload = result.patch["confirmation_payload"]["launch_payload"]
    assert result.outcome == "await_approval"
    assert launch_payload["entry_rule"] == {
        "indicator": "rsi",
        "operator": "below",
        "period": 14,
        "threshold": 20.0,
    }
    assert launch_payload["exit_rule"] == {
        "indicator": "rsi",
        "operator": "above",
        "period": 14,
        "threshold": 60.0,
    }


def test_confirm_stage_preserves_user_indicator_period_in_launch_payload() -> None:
    state = RunState.new(
        current_user_message="Use RSI 7 entry 20 exit 60.",
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="indicator_threshold",
        strategy_thesis="Backtest Tesla RSI.",
        asset_universe=["TSLA"],
        asset_class="equity",
        date_range="last year",
        entry_logic="RSI(7) threshold entry",
        exit_logic="RSI(7) threshold exit",
        extra_parameters={
            "indicator": "rsi",
            "indicator_parameters": {
                "indicator": "rsi",
                "indicator_period": 7,
                "entry_threshold": 20,
                "exit_threshold": 60,
            },
        },
    )

    result = confirm_stage(state=state, contract=build_default_capability_contract())

    launch_payload = result.patch["confirmation_payload"]["launch_payload"]
    assert result.outcome == "await_approval"
    assert launch_payload["entry_rule"]["period"] == 7
    assert launch_payload["exit_rule"]["period"] == 7


def test_confirm_stage_blocks_unsupported_nonzero_fee_assumption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARGUS_ENABLE_EXECUTION_REALISM", "false")
    state = RunState.new(
        current_user_message="Backtest Tesla with fees.",
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="buy_and_hold",
        strategy_thesis="Backtest Tesla with fees.",
        asset_universe=["TSLA"],
        asset_class="equity",
        date_range="last year",
    )
    state.optional_parameter_status = {"fees": 0.01}

    result = confirm_stage(state=state, contract=build_default_capability_contract())

    assert result.outcome == "needs_clarification"
    assert result.patch["requested_field"] == "fees"
    assert result.patch["assistant_prompt"] is None
    constraint = result.patch["optional_parameter_status"]["unsupported_constraints"][0]
    assert constraint["category"] == "unsupported_execution_assumption"
    assert constraint["raw_value"] == "custom trading fees"


def test_confirm_stage_accepts_nonzero_costs_when_execution_realism_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARGUS_ENABLE_EXECUTION_REALISM", "true")
    state = RunState.new(
        current_user_message="Backtest Tesla with 0.1% fees.",
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="buy_and_hold",
        strategy_thesis="Backtest Tesla with fees.",
        asset_universe=["TSLA"],
        asset_class="equity",
        date_range="last year",
    )
    state.optional_parameter_status = {"fees": 0.001, "slippage": 0.0005}

    result = confirm_stage(state=state, contract=build_default_capability_contract())

    assert result.outcome == "await_approval"
    launch_payload = result.patch["confirmation_payload"]["launch_payload"]
    assert launch_payload["_execution_realism"] == {
        "enabled": True,
        "fee_bps": 10.0,
        "slippage_bps": 5.0,
    }


def test_confirm_stage_clarifies_vague_signal_before_ready_card() -> None:
    state = RunState.new(
        current_user_message="Test buying SPY when it starts rising.",
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="signal_strategy",
        strategy_thesis="Buy SPY when it starts rising.",
        asset_universe=["SPY"],
        asset_class="equity",
        date_range="last month",
        entry_logic="starts rising",
    )

    result = confirm_stage(state=state, contract=build_default_capability_contract())

    assert result.outcome == "needs_clarification"
    assert result.patch["assistant_prompt"] is None
    assert result.patch["missing_required_fields"] == ["entry_logic"]


def test_confirm_stage_clarifies_non_executable_signal_rule_before_date() -> None:
    state = RunState.new(
        current_user_message="Test buying SPY when it starts rising.",
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="signal_strategy",
        strategy_thesis="Buy SPY when it starts rising.",
        asset_universe=["SPY"],
        asset_class="equity",
        entry_logic="starts rising",
        entry_rule={"type": "price_momentum", "direction": "up"},
    )

    result = confirm_stage(state=state, contract=build_default_capability_contract())

    assert result.outcome == "needs_clarification"
    assert result.patch["assistant_prompt"] is None
    assert result.patch["missing_required_fields"] == ["entry_logic"]


def test_confirm_stage_blocks_canonical_signal_window_when_window_cannot_cover_warmup() -> (
    None
):
    state = RunState.new(
        current_user_message=(
            "Test SPY when the 50-day SMA crosses above the 200-day SMA last month."
        ),
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="signal_strategy",
        strategy_thesis="Backtest SPY moving-average crossover.",
        asset_universe=["SPY"],
        asset_class="equity",
        date_range="last month",
        entry_logic="50-day SMA crosses above 200-day SMA",
        exit_logic="50-day SMA crosses below 200-day SMA",
        extra_parameters={
            "date_range_intent": {
                "kind": "rolling_window",
                "count": 1,
                "unit": "month",
                "anchor": "today",
                "confidence": 0.92,
                "evidence": "last month",
            }
        },
        entry_rule={
            "type": "moving_average_crossover",
            "fast_indicator": "sma",
            "fast_period": 50,
            "slow_indicator": "sma",
            "slow_period": 200,
            "direction": "bullish",
        },
    )

    result = confirm_stage(state=state, contract=build_default_capability_contract())

    assert result.outcome == "needs_clarification"
    assert result.patch["assistant_prompt"] is None
    assert result.patch["requested_field"] == "date_range"
    constraint = result.patch["optional_parameter_status"]["unsupported_constraints"][0]
    assert constraint["category"] == "data_window_too_short_for_rule"
    assert any(
        option["label"] == "Use a longer date range"
        for option in constraint["simplification_options"]
    )
