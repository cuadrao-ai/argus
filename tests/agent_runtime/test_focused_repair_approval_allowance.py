"""#928: a focused repair and the audit that approves it are funded together.

The #600 prebaked-chip journeys run through /api/v1/chat/stream under the
production turn allowance. Only the model transport is scripted; the route
opens the real turn scope and the interpreter, audits, repairs and clarifier
stay real.
"""

from __future__ import annotations

import asyncio
import copy
import json
import socket
from typing import Any, Literal

import httpx
import pytest
from argus.agent_runtime import llm_interpreter, turn_execution
from argus.api import state as api_state
from argus.api.main import app
from argus.api.routers import agent as agent_router
from argus.domain.market_data import assets
from argus.llm import openrouter

from tests.evals.measurement_eval_harness import EvalCase, load_eval_cases
from tests.test_chat_stream_contract import _data_events
from tests.test_confirmation_direct_edit import _client, _conversation

PESOS = "dca_capital_semantics_prebaked_chip_spanish_pesos_reaches_ready_to_run"
BARE = "dca_capital_semantics_prebaked_chip_bare_amount_reaches_ready_to_run"
Script = Literal["authored", "recorded"]


def _card(contribution: str) -> list[list[str]]:
    return [
        ["strategy", "Recurring Buys"],
        ["assets", "KO"],
        ["period", "August 19, 2021 - August 19, 2026"],
        ["starting_capital", "$0"],
        ["contribution", contribution],
    ]


def _scripted_post(case: EvalCase, script: Script, audit_role: str) -> Any:
    """authored: the follow-up's primary read is underfilled, then repaired.

    recorded: the follow-up's primary times out and the fallback reads the
    whole answer; the first contract audit cannot settle the amount.
    """
    amount = case.expected.capital_amount
    pending = case.snapshot.pending_strategy_summary.model_dump(mode="json")
    draft = {
        "strategy_type": "dca_accumulation",
        "asset_universe": list(case.expected.assets),
        "asset_class": "equity",
        "capital_amount": amount,
        "initial_capital": None,
        "cadence": case.expected.contribution_period,
        "date_range": pending.get("date_range"),
    }
    focused = {
        **draft,
        "is_testable_strategy": True,
        "requires_clarification": False,
        "language": case.user_language,
        "user_goal_summary": case.followup_prompt,
        "confidence": 0.9,
        "comparison_baseline": "SPY",
    }
    turn = {"followup": False, "primary": 0, "followup_primary": 0, "followup_dca": 0}

    async def post(*, client, api_key, payload, retry_attempt):
        schema = retry_attempt[4]
        messages = payload["messages"]
        human = [m["content"] for m in messages if m["role"] == "user"]
        followup = turn["followup"]
        if schema == "LLMAssetMentionExtraction":
            followup = turn["followup"] = bool(
                human and case.followup_prompt in human[-1]
            )
            mentions = [
                {
                    "raw_text": draft["asset_universe"][0],
                    "role": "traded_asset",
                    "mention_kind": "ticker",
                    "confidence": 0.9,
                }
            ]
            result = {
                "all_traded_asset_mentions_included": True,
                "asset_mentions": [] if followup else mentions,
            }
        elif schema == "LLMInterpretationResponse":
            turn["primary"] += 1
            turn["followup_primary"] += followup
            if turn["primary"] == 1 or (
                script == "recorded" and followup and turn["followup_primary"] == 1
            ):
                raise asyncio.TimeoutError()
            result = {
                "intent": "backtest_execution",
                "task_relation": "continue" if followup else "new_task",
                "semantic_turn_act": "answer_pending_need" if followup else "new_idea",
                "requires_clarification": not followup,
                "missing_required_fields": [] if followup else ["capital_amount"],
                "user_goal_summary": case.followup_prompt if followup else case.prompt,
                "candidate_strategy_draft": copy.deepcopy(draft),
            }
            if not followup:
                result["candidate_strategy_draft"]["capital_amount"] = None
            elif script == "authored":
                result["candidate_strategy_draft"]["date_range"] = None
        elif schema == "FocusedStrategyExtraction":
            result = copy.deepcopy(focused)
        elif schema == "DcaContractAudit":
            turn["followup_dca"] += followup
            settles = followup and not (
                script == "recorded" and turn["followup_dca"] == 1
            )
            result = {
                "is_recurring_buy_request": True,
                "cadence": draft["cadence"],
                "recurring_contribution_amount": amount if settles else None,
                "confidence": 0.9 if settles or not followup else 0.3,
            }
        elif schema == "StrategyFamilyContinuityAudit":
            result = {"should_rebind_strategy_family": False, "confidence": 0.9}
        elif schema == "DcaContributionRoleAudit":
            result = {
                "recurring_contribution_explicit": True,
                "total_budget_not_recurring": False,
                "confidence": 0.9,
            }
        elif schema == "FocusedDateWindowExtraction":
            result = {"has_date_window": False, "confidence": 0.9}
        elif schema == "StatedRunFieldFidelityAudit":
            role = (
                "capital_amount"
                if audit_role == "starting"
                else "recurring_contribution_amount"
            )
            result = {role: amount if followup else None, "confidence": 0.9}
        elif schema == "ClarificationResponse":
            context = next(
                json.loads(m["content"])
                for m in messages
                if m["role"] == "system" and m["content"].startswith("{")
            )
            result = {
                "question": "¿Qué supuesto quieres usar?"
                if followup
                else "¿Cuánto debería usar?",
                "direct_question": "¿Cuánto debería usar?",
                "question_targets": context["expected_question_targets"],
                "directly_asks_user": True,
                "detail_targets": context["expected_detail_targets"],
            }
        else:
            raise AssertionError(f"unexpected_schema:{schema}")
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(result)}}]}
        )

    return post


def _replay(
    monkeypatch: pytest.MonkeyPatch,
    *,
    case_id: str,
    script: Script,
    audit_role: str,
    allowance: Literal["production", "off"],
) -> dict[str, Any]:
    case = next(c for c in load_eval_cases() if c.id == case_id)
    for key in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY", "PERPLEXITY_API_KEY"):
        monkeypatch.setenv(key, "")
    for key, value in dict(
        OPENROUTER_API_KEY="hermetic-test-key",
        ARGUS_ASSET_PROVIDER_MODE="synthetic_unit_fixture",
        ARGUS_MARKET_DATA_PROVIDER_MODE="synthetic_unit_fixture",
        ARGUS_STRUCTURED_MODEL="x-ai/grok-4.3",
        ARGUS_STRUCTURED_FALLBACK_MODEL="anthropic/claude-haiku-4.5",
        ARGUS_CHAT_MODEL="deepseek/deepseek-v4-flash",
        ARGUS_CHAT_FALLBACK_MODEL="qwen/qwen3.5-9b",
        ARGUS_RESEARCH_RAIL_ENABLED="false",
        ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED="false",
        ARGUS_RUNTIME_STREAM_WORKER="false",
        ARGUS_ENABLE_SPANISH="true",
    ).items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("ARGUS_TURN_CALL_ALLOWANCE", raising=False)
    if allowance == "off":
        monkeypatch.setattr(turn_execution, "_turn_call_allowance", lambda: 10_000)

    def no_network(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("network_forbidden")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(
        openrouter,
        "_post_openrouter_json_schema",
        _scripted_post(case, script, audit_role),
    )
    monkeypatch.setattr(
        "argus.agent_runtime.stages.confirm.fetch_alpaca_market_clock", lambda: None
    )
    monkeypatch.setitem(assets.SYNTHETIC_UNIT_ASSETS, "KO", ("equity", "Coca-Cola", "KO"))
    monkeypatch.setattr(assets, "_ASSET_ALIAS_MAP", None)
    if script == "recorded":
        # The measurement's eighth call was a field-fidelity audit; its trigger
        # depends on reply bodies the measurement did not keep.
        real_needs = llm_interpreter._response_needs_stated_run_field_fidelity_audit

        def needs(*, response: Any, request: Any = None) -> bool:
            if (
                request is not None
                and case.followup_prompt in request.current_user_message
            ):
                return True
            return real_needs(response=response, request=request)

        monkeypatch.setattr(
            llm_interpreter, "_response_needs_stated_run_field_fidelity_audit", needs
        )
    persisted: list[dict[str, Any]] = []
    real_persist = agent_router.persist_route_receipts

    def capture(**kwargs: Any) -> None:
        persisted.append(kwargs)
        real_persist(**kwargs)

    monkeypatch.setattr(agent_router, "persist_route_receipts", capture)

    client = _client()
    api_state.reset_agent_runtime_workflow(app)
    conversation = _conversation(client)
    finals = []
    for message in (case.prompt, case.followup_prompt):
        response = client.post(
            "/api/v1/chat/stream",
            json={
                "conversation_id": conversation["id"],
                "message": message,
                "ui_language": case.ui_language,
            },
        )
        assert response.status_code == 200
        events = _data_events(response.text)
        assert not [e for e in events if e.get("type") == "error"]
        finals.append(next(e["payload"] for e in events if e.get("type") == "final"))
    final = finals[-1]
    receipts = persisted[-1]["receipts"]
    return {
        "stage_outcome": final.get("stage_outcome"),
        "card": [
            [row["key"], row["value"]]
            for row in (final.get("confirmation") or {}).get("rows", [])
        ],
        "turn_execution": persisted[-1]["metadata"]["turn_execution"],
        "receipts": [
            (r.task, r.schema_name, r.outcome, r.failure_mode) for r in receipts
        ],
    }


@pytest.mark.parametrize("audit_role", ["starting", "recurring"])
@pytest.mark.parametrize("allowance", ["production", "off"])
def test_an_underfilled_answer_repaired_on_the_last_permit_reaches_the_card(
    monkeypatch: pytest.MonkeyPatch,
    allowance: Literal["production", "off"],
    audit_role: str,
) -> None:
    result = _replay(
        monkeypatch,
        case_id=PESOS,
        script="authored",
        audit_role=audit_role,
        allowance=allowance,
    )

    assert result["stage_outcome"] == "await_approval"
    assert result["card"] == _card("$13,000 monthly")
    fidelity = [r for r in result["receipts"] if r[0] == "field_fidelity"]
    summary = result["turn_execution"]
    if allowance == "production":
        # The repair takes the seventh permit; its approval draws from the
        # repair pool and the post-repair audit is still refused, on record.
        assert fidelity == [
            ("field_fidelity", "StatedRunFieldFidelityAudit", "succeeded", None),
            (
                "field_fidelity",
                "StatedRunFieldFidelityAudit",
                "skipped",
                "turn_call_allowance_exhausted",
            ),
        ]
        assert summary["calls_reserved"] == 8
        assert summary["call_allowance"] == 7
        assert summary["repair_approval_grant_used"] == 1
        assert summary["last_resort_repair_grant_used"] == 1
        assert summary["call_allowance_exhausted"] is True
    else:
        assert [r[2] for r in fidelity] == ["succeeded", "succeeded"]
        assert summary["calls_reserved"] == 9
        assert summary["repair_approval_grant_used"] == 0
    assert not any(r[0] == "clarification" for r in result["receipts"])


@pytest.mark.parametrize("audit_role", ["starting", "recurring"])
def test_the_recorded_bare_amount_turn_keeps_its_card_and_its_seven_permits(
    monkeypatch: pytest.MonkeyPatch, audit_role: str
) -> None:
    result = _replay(
        monkeypatch,
        case_id=BARE,
        script="recorded",
        audit_role=audit_role,
        allowance="production",
    )

    assert result["stage_outcome"] == "await_approval"
    assert result["card"] == _card("$200 monthly")
    assert [r for r in result["receipts"] if r[0] == "field_fidelity"] == [
        (
            "field_fidelity",
            "StatedRunFieldFidelityAudit",
            "skipped",
            "turn_call_allowance_exhausted",
        )
    ]
    assert not any(r[0] == "interpretation_repair" for r in result["receipts"])
    summary = result["turn_execution"]
    assert summary["calls_reserved"] == 7
    assert summary["repair_approval_grant_used"] == 0
    assert summary["last_resort_repair_grant_used"] == 0
