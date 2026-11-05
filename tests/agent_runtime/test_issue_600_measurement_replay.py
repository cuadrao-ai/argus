"""Reconstruct #600 scorecard paths at the transport boundary.

Reply bodies were not retained by the live measurement. These scripts reproduce
its typed outcomes and relevant repair path, not an exact recording of the model.
Only external I/O is replaced; validation, auditing and stages stay real.
"""

from __future__ import annotations

import asyncio
import copy
import json
import socket
from datetime import date, datetime, time
from typing import Any, Literal

import httpx
import pytest
from argus.domain.market_data import assets, capabilities, provider
from argus.llm import openrouter
from loguru import logger

from tests.evals.measurement_eval_harness import EvalCase, load_eval_cases, run_eval_case

PESOS = "dca_capital_semantics_prebaked_chip_spanish_pesos_reaches_ready_to_run"
NVDA = "messy_spanish_future_performance_nvda_cruce_dorado"
ZERO_SEED = "dca_capital_semantics_zero_seed_small_contribution_executable_issue_455"
REPLAY_ENV = dict(
    OPENROUTER_API_KEY="hermetic-test-key",
    ARGUS_RUN_LIVE_EVALS="0",
    ARGUS_ASSET_PROVIDER_MODE="synthetic_unit_fixture",
    ARGUS_MARKET_DATA_PROVIDER_MODE="synthetic_unit_fixture",
    CUADRAO_STRUCTURED_MODEL="x-ai/grok-4.3",
    CUADRAO_STRUCTURED_FALLBACK_MODEL="anthropic/claude-haiku-4.5",
    CUADRAO_CHAT_MODEL="deepseek/deepseek-v4-flash",
    CUADRAO_CHAT_FALLBACK_MODEL="qwen/qwen3.5-9b",
    ARGUS_RESEARCH_RAIL_ENABLED="false",
    ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED="false",
)


def replay_case(
    case: EvalCase,
    monkeypatch: pytest.MonkeyPatch,
    *,
    audit_role: Literal[
        "starting", "recurring", "equal_seed", "distinct_seed"
    ] = "starting",
    unowned_contribution: bool = False,
    audit_zero_seed: bool = False,
    initial_capital: float | None = None,
) -> dict[str, Any]:
    case_id = case.id
    zero_seed = case_id == ZERO_SEED
    dca = case.snapshot is not None or zero_seed
    amount = case.expected.capital_amount if dca else 10000.0
    pending = (
        case.snapshot.pending_strategy_summary.model_dump(mode="json")
        if case.snapshot is not None
        else {"date_range": case.expected.date_range}
    )
    draft = {
        "strategy_type": "dca_accumulation" if dca else "signal_strategy",
        "asset_universe": list(case.expected.assets) if dca else ["NVDA"],
        "asset_class": "equity",
        "capital_amount": amount,
        "initial_capital": initial_capital,
        "cadence": case.expected.contribution_period if dca else None,
        "date_range": pending.get("date_range"),
    }
    focused = {
        **draft,
        "is_testable_strategy": True,
        "requires_clarification": False,
        "language": case.user_language,
        "user_goal_summary": case.followup_prompt or case.prompt,
        "confidence": 0.9,
        "comparison_baseline": "SPY",
    }
    if zero_seed:
        draft.update(initial_capital=case.expected.starting_capital, date_range=None)
        focused.update(
            recurring_contribution=amount,
            comparison_baseline=None,
            date_range_intent={
                "kind": "explicit_range",
                **case.expected.date_range,
                "confidence": 0.9,
            },
        )
    if unowned_contribution:
        # An underfilled primary can carry a typed amount with no owner, while
        # the focused read supplies only the missing non-money fields.
        draft.update(capital_amount=None, recurring_contribution=amount)
        focused["capital_amount"] = None
    if not dca:
        focused.update(
            entry_rule={
                "type": "moving_average_crossover",
                "fast_indicator": "sma",
                "fast_period": 50,
                "slow_indicator": "sma",
                "slow_period": 200,
                "direction": "bullish",
            },
            date_range_intent={
                "kind": "future_window",
                "count": 10,
                "unit": "year",
                "anchor": "today",
                "confidence": 0.9,
                "evidence": "dentro de diez años",
            },
            evidence_spans={"capital_amount": "$10,000"},
        )
    calls = []
    unexpected = []
    guards = []
    primary_count = 0
    current_followup = False

    def log_guard(message):
        extra = message.record["extra"]
        if extra.get("guard") == "focused_strategy_stated_fields":
            guards.append(copy.deepcopy(extra))

    def no_network(*args, **kwargs):
        raise AssertionError("network_forbidden")

    async def no_async_network(*args, **kwargs):
        raise AssertionError("network_forbidden")

    async def post(*, client, api_key, payload, retry_attempt):
        nonlocal primary_count, current_followup
        task, _, _, _, schema, _ = retry_attempt
        calls.append({"schema": schema, "model": payload["model"]})
        messages = payload["messages"]
        human = [m["content"] for m in messages if m["role"] == "user"]
        if schema == "LLMAssetMentionExtraction":
            current_followup = bool(dca and human[-1] == case.followup_prompt)
            result = {
                "all_traded_asset_mentions_included": True,
                "asset_mentions": []
                if current_followup and not unowned_contribution
                else [
                    {
                        "raw_text": draft["asset_universe"][0],
                        "role": "traded_asset",
                        "mention_kind": "ticker",
                        "confidence": 0.9,
                    }
                ],
            }
        elif schema == "LLMInterpretationResponse":
            primary_count += 1
            result = {
                "intent": "backtest_execution",
                "task_relation": "continue" if dca else "new_task",
                "semantic_turn_act": "answer_pending_need" if dca else "new_idea",
                "requires_clarification": dca and not current_followup,
                "missing_required_fields": ["capital_amount"]
                if dca and not current_followup
                else [],
                "user_goal_summary": case.followup_prompt
                if current_followup
                else case.prompt,
                "candidate_strategy_draft": copy.deepcopy(draft),
            }
            if zero_seed:
                result.update(
                    task_relation="new_task",
                    semantic_turn_act="new_idea",
                    requires_clarification=False,
                    missing_required_fields=[],
                )
            elif primary_count == 1:
                raise asyncio.TimeoutError()
            elif not dca:
                result["response_profile_overrides"] = None
            elif not current_followup:
                result["candidate_strategy_draft"]["capital_amount"] = None
            else:
                # Successful but underfilled follow-up, then a focused repair.
                result["candidate_strategy_draft"]["date_range"] = None
                if unowned_contribution:
                    result.update(task_relation="new_task", semantic_turn_act="new_idea")
        elif schema == "FocusedStrategyExtraction":
            result = copy.deepcopy(focused)
        elif schema == "DcaContractAudit":
            result = {
                "is_recurring_buy_request": True,
                "cadence": draft["cadence"],
                "recurring_contribution_amount": amount
                if (current_followup or zero_seed) and not unowned_contribution
                else None,
                "confidence": 0.9,
            }
        elif schema == "StrategyFamilyContinuityAudit":
            result = {"should_rebind_strategy_family": False, "confidence": 0.9}
        elif schema == "DcaContributionRoleAudit":
            result = {
                "recurring_contribution_explicit": not unowned_contribution,
                "total_budget_not_recurring": False,
                "confidence": 0.9,
            }
        elif schema == "FocusedDateWindowExtraction":
            result = {"has_date_window": not dca or zero_seed, "confidence": 0.9}
            if zero_seed:
                result["date_range_intent"] = focused["date_range_intent"]
            elif not dca:
                result.update(
                    date_range_intent=focused["date_range_intent"],
                    date_range_raw_text=focused["date_range_intent"]["evidence"],
                )
        elif schema == "StatedRunFieldFidelityAudit":
            role = (
                "capital_amount"
                if audit_role == "starting"
                else "recurring_contribution_amount"
            )
            result = {
                role: amount if not dca or current_followup else None,
                "confidence": 0.9,
            }
            if current_followup and audit_role in {"equal_seed", "distinct_seed"}:
                result.update(
                    capital_amount=amount * (2 if audit_role == "distinct_seed" else 1),
                    recurring_contribution_amount=amount,
                )
            if zero_seed:
                result = {
                    "recurring_contribution_amount": amount,
                    "capital_amount": case.expected.starting_capital
                    if audit_zero_seed
                    else None,
                    "confidence": 0.9,
                }
        elif schema == "SignalRuleGroundingAudit":
            result = {"outcome": "grounded", "confidence": 0.9}
        elif schema == "ClarificationResponse":
            # Read the real generator's declared needs; only prose is scripted.
            context = next(
                json.loads(m["content"])
                for m in messages
                if m["role"] == "system" and m["content"].startswith("{")
            )
            result = {
                "question": "¿Qué supuesto quieres usar?"
                if current_followup
                else "¿Cuánto debería usar?",
                "direct_question": "¿Cuánto debería usar?",
                "question_targets": context["expected_question_targets"],
                "directly_asks_user": True,
                "detail_targets": context["expected_detail_targets"],
            }
        else:
            unexpected.append(schema)
            raise AssertionError(f"unexpected_schema:{schema}")
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(result)}}]}
        )

    handler = logger.add(log_guard)
    with monkeypatch.context() as mp:
        for key in (
            "OPENROUTER_API_KEY",
            "ALPACA_API_KEY",
            "ALPACA_SECRET_KEY",
            "PERPLEXITY_API_KEY",
        ):
            mp.setenv(key, "")
        for key, value in REPLAY_ENV.items():
            mp.setenv(key, value)
        mp.setattr(socket.socket, "connect", no_network)
        mp.setattr(httpx.Client, "send", no_network)
        mp.setattr(httpx.AsyncClient, "send", no_async_network)
        mp.setattr(openrouter, "_post_openrouter_json_schema", post)
        mp.setattr(
            "argus.agent_runtime.stages.confirm.fetch_alpaca_market_clock", lambda: None
        )
        mp.setitem(assets.SYNTHETIC_UNIT_ASSETS, "KO", ("equity", "Coca-Cola", "KO"))
        mp.setattr(assets, "_ASSET_ALIAS_MAP", None)
        if zero_seed:
            synthetic_bars = provider._synthetic_ohlcv
            window = case.expected.effective_date_range

            def fixture_bars(**kwargs):
                # The synthetic catalog includes holidays. Use this fixture's
                # observed coverage at the provider boundary, keeping the real
                # calendar alignment and confirmation stages in the replay.
                kwargs.pop("asset_class", None)
                frame = synthetic_bars(**kwargs)
                return frame.loc[window["start"] : window["end"]]

            def fixture_calendar(**kwargs):
                # Only endpoint sessions are needed for this coverage replay.
                return tuple(
                    capabilities.EquityMarketSession(
                        provider="fixture",
                        session_date=day,
                        opens_at=datetime.combine(day, time(9, 30), capabilities.EASTERN),
                        closes_at=datetime.combine(day, time(16), capabilities.EASTERN),
                    )
                    for day in (date.fromisoformat(value) for value in window.values())
                    if kwargs["start_date"] <= day <= kwargs["end_date"]
                )

            mp.setenv("ARGUS_MARKET_DATA_PROVIDER_MODE", "live_provider")
            mp.setattr(provider, "_fetch_bars_with_ttl", fixture_bars)
            mp.setattr(capabilities, "fetch_alpaca_market_calendar", fixture_calendar)
        result = run_eval_case(case, run_prose_judge=False)
    logger.remove(handler)
    t = result["typed_outcome"]
    return {
        "id": case_id,
        "reconstruction": "authored_from_typed_outcomes_and_receipts",
        "status": result["status"],
        "failed_check_codes": [s.split(":")[0] for s in result["failed_checks"]],
        "typed": {
            k: t[k]
            for k in [
                "intent",
                "semantic_turn_act",
                "capability_verdict",
                "stage_outcomes",
                "missing_required_fields",
                "requested_field",
                "capital_amount",
                "starting_capital",
                "recurring_contribution",
            ]
        },
        "clarification_code": (t.get("clarification") or {}).get("reason_code"),
        "clarification_kind": (t.get("clarification") or {}).get("kind"),
        "calls": calls,
        "unexpected": unexpected,
        "guards": guards,
        "receipts": [
            {
                k: r.get(k)
                for k in [
                    "task",
                    "schema_name",
                    "model",
                    "outcome",
                    "failure_mode",
                    "repair_effect",
                ]
            }
            for r in result["route_receipts"]
        ],
    }


@pytest.mark.parametrize(
    "case_id",
    [PESOS, "dca_capital_semantics_prebaked_chip_bare_amount_reaches_ready_to_run"],
)
@pytest.mark.parametrize("audit_role", ["starting", "recurring"])
def test_focused_repair_keeps_a_contribution_answer_in_its_owned_role(
    monkeypatch: pytest.MonkeyPatch, case_id: str, audit_role: str
) -> None:
    case = next(case for case in load_eval_cases() if case.id == case_id)
    result = replay_case(case, monkeypatch, audit_role=audit_role)
    assert not result["unexpected"]
    assert result["failed_check_codes"] == []
    assert result["typed"]["stage_outcomes"] == list(case.expected.stage_outcomes)
    assert result["typed"]["recurring_contribution"] == case.expected.capital_amount
    assert result["typed"]["starting_capital"] == 0
    assert any(
        r["schema_name"] == "FocusedStrategyExtraction" for r in result["receipts"]
    )
    assert [
        r["failure_mode"] for r in result["receipts"] if r["outcome"] == "failed"
    ] == ["TimeoutError"]
    assert any(
        guard["contribution_role_preserved"] == (audit_role == "starting")
        for guard in result["guards"]
    )
    repair = next(
        receipt["repair_effect"]
        for receipt in result["receipts"]
        if receipt["schema_name"] == "FocusedStrategyExtraction"
        and receipt["outcome"] == "succeeded"
    )
    assert repair["contribution_role_preserved"] == (audit_role == "starting")


@pytest.mark.parametrize("audit_role", ["equal_seed", "distinct_seed"])
def test_a_separately_audited_deposit_still_requires_an_owned_seed(
    monkeypatch: pytest.MonkeyPatch, audit_role: str
) -> None:
    case = next(case for case in load_eval_cases() if case.id == PESOS)
    result = replay_case(case, monkeypatch, audit_role=audit_role)
    assert not result["unexpected"]
    assert result["typed"]["missing_required_fields"] == ["assumption"]
    assert result["typed"]["stage_outcomes"][-2:] == [
        "needs_clarification",
        "await_user_reply",
    ]
    assert any(
        "focused_repair_stated_fields_unresolved" in guard["reason_codes"]
        and not guard["contribution_role_preserved"]
        for guard in result["guards"]
    )


@pytest.mark.parametrize("initial_capital", [None, 0])
def test_unowned_typed_contribution_does_not_suppress_a_deposit_clarification(
    monkeypatch: pytest.MonkeyPatch,
    initial_capital: float | None,
) -> None:
    case = next(case for case in load_eval_cases() if case.id == PESOS)
    result = replay_case(
        case, monkeypatch, unowned_contribution=True, initial_capital=initial_capital
    )
    assert not result["unexpected"]
    assert result["guards"]
    assert "assumption" in result["typed"]["missing_required_fields"]
    assert result["typed"]["stage_outcomes"][-2:] == [
        "needs_clarification",
        "await_user_reply",
    ]
    assert not any(guard["contribution_role_preserved"] for guard in result["guards"])
    repairs = [
        receipt["repair_effect"]
        for receipt in result["receipts"]
        if receipt["schema_name"] == "FocusedStrategyExtraction"
        and receipt["outcome"] == "succeeded"
    ]
    assert repairs and all(not r["contribution_role_preserved"] for r in repairs)


@pytest.mark.parametrize("audit_zero_seed", [False, True])
def test_focused_repair_does_not_reask_a_zero_starting_deposit(
    monkeypatch: pytest.MonkeyPatch, audit_zero_seed: bool
) -> None:
    case = next(case for case in load_eval_cases() if case.id == ZERO_SEED)
    result = replay_case(case, monkeypatch, audit_zero_seed=audit_zero_seed)
    assert not result["unexpected"]
    assert result["failed_check_codes"] == []
    assert result["typed"]["stage_outcomes"] == list(case.expected.stage_outcomes)
    assert result["typed"]["starting_capital"] == case.expected.starting_capital
    assert result["typed"]["recurring_contribution"] == case.expected.capital_amount
