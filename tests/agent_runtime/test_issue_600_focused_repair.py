"""Repair fidelity from #600, behind typed test ownership and real validation."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

import httpx
import pytest
from argus.agent_runtime.capabilities.contract import build_default_capability_contract
from argus.agent_runtime.graph.workflow import _apply_stage_result, _patched_run_state
from argus.agent_runtime.llm_interpreter import OpenRouterStructuredInterpreter
from argus.agent_runtime.stages.clarify import clarify_stage_async
from argus.agent_runtime.stages.confirm import confirm_stage
from argus.agent_runtime.stages.interpret import interpret_stage_async
from argus.agent_runtime.state.models import RunState, UserState
from argus.agent_runtime.turn_execution import turn_execution_scope
from argus.api.chat.confirmation import runtime_confirmation_card
from argus.domain.market_data import assets
from argus.llm import openrouter
from faker import Faker

SEED = 1000.0
CONTRIBUTION = 100.0
FEE_BPS = 5.0
SLIPPAGE_BPS = 10.0
DATE_RANGE = {"start": "2023-09-01", "end": "today"}
MESSAGES = {
    "en": (
        f"Invest ${SEED:,.0f} in DOCN in September 2023 and then buy "
        f"${CONTRIBUTION:,.0f} more each month, with fees of {FEE_BPS:g} bps and "
        f"slippage of {SLIPPAGE_BPS:g} bps per trade, compared with SPY."
    ),
    "es-419": (
        f"Invierte ${SEED:,.0f} en DOCN en septiembre de 2023 y luego compra "
        f"${CONTRIBUTION:,.0f} más cada mes, con comisiones de {FEE_BPS:g} bps y "
        f"deslizamiento de {SLIPPAGE_BPS:g} bps por operación, comparado con SPY."
    ),
}


def _costs(language: str) -> dict[str, Any]:
    fee, slippage = (
        (f"fees of {FEE_BPS:g} bps", f"slippage of {SLIPPAGE_BPS:g} bps")
        if language == "en"
        else (
            f"comisiones de {FEE_BPS:g} bps",
            f"deslizamiento de {SLIPPAGE_BPS:g} bps",
        )
    )
    return {
        "fee": {"rate": FEE_BPS / 10000, "evidence_span": fee},
        "slippage": {"rate": SLIPPAGE_BPS / 10000, "evidence_span": slippage},
    }


def _focused_payload(language: str) -> dict[str, Any]:
    # The live repair returned these two distinct amounts in these slots.
    # The focused schema has no initial_capital or modeled-cost fields.
    return {
        "is_testable_strategy": True,
        "requires_clarification": False,
        "user_goal_summary": MESSAGES[language],
        "language": language,
        "strategy_type": "dca_accumulation",
        "asset_universe": ["DOCN"],
        "asset_class": "equity",
        "date_range": DATE_RANGE,
        "date_range_raw_text": (
            "September 2023" if language == "en" else "septiembre de 2023"
        ),
        "date_range_intent": {
            "kind": "explicit_range",
            **DATE_RANGE,
            "confidence": 0.9,
            "evidence": "September 2023" if language == "en" else "septiembre de 2023",
        },
        "comparison_baseline": "SPY",
        "capital_amount": SEED,
        "recurring_contribution": CONTRIBUTION,
        "cadence": "monthly",
        "confidence": 0.9,
        "evidence_spans": {
            "capital_amount": f"${SEED:,.0f}",
            "recurring_contribution": f"${CONTRIBUTION:,.0f}",
            "comparison_baseline": "SPY",
        },
    }


def _primary_payload(language: str) -> dict[str, Any]:
    draft = _focused_payload(language)
    for field in (
        "is_testable_strategy",
        "requires_clarification",
        "user_goal_summary",
        "confidence",
    ):
        draft.pop(field)
    costs = _costs(language)
    draft.update(
        capital_amount=CONTRIBUTION,
        initial_capital=SEED,
        extra_parameters={
            "fee_rate": costs["fee"]["rate"],
            "slippage": costs["slippage"]["rate"],
        },
        field_provenance={
            "initial_capital": "starting_capital",
            "capital_amount": "recurring_contribution",
            "recurring_contribution": "explicit_user",
            "cadence": "explicit_user",
            "comparison_baseline": "explicit_user",
        },
    )
    draft["evidence_spans"].update(
        fee_rate=costs["fee"]["evidence_span"],
        slippage=costs["slippage"]["evidence_span"],
    )
    return {
        "intent": "backtest_execution",
        "task_relation": "new_task",
        "requires_clarification": False,
        "user_goal_summary": MESSAGES[language],
        "candidate_strategy_draft": draft,
        "semantic_turn_act": "new_idea",
    }


@pytest.fixture
def replay_transport(monkeypatch: pytest.MonkeyPatch) -> Callable[[str, str], None]:
    """Replace only external I/O; Argus owns parsing, receipts, and routing."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "hermetic-test-key")
    monkeypatch.setenv("ARGUS_ASSET_PROVIDER_MODE", "synthetic_unit_fixture")
    monkeypatch.setenv("ARGUS_ENABLE_EXECUTION_REALISM", "true")
    monkeypatch.setenv("ARGUS_STRUCTURED_MODEL", "x-ai/grok-4.3")
    monkeypatch.setenv("ARGUS_STRUCTURED_FALLBACK_MODEL", "anthropic/claude-haiku-4.5")
    monkeypatch.setenv("ARGUS_TURN_CALL_ALLOWANCE", "7")
    monkeypatch.setenv("ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED", "false")
    monkeypatch.setitem(
        assets.SYNTHETIC_UNIT_ASSETS, "DOCN", ("equity", "DigitalOcean", "DOCN")
    )
    monkeypatch.setattr(assets, "_ASSET_ALIAS_MAP", None)
    monkeypatch.setattr(
        "argus.agent_runtime.stages.confirm.fetch_alpaca_market_clock", lambda: None
    )

    async def no_network(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Hermetic replay attempted network I/O")

    monkeypatch.setattr(httpx.AsyncClient, "send", no_network)

    def install(language: str, mode: str) -> None:
        mode, _, continuation = mode.partition(":")
        relation, _, route = continuation.partition(":")
        followup_intent, _, followup_act = route.partition("/")
        if mode == "repair_on_exhausted_corridor":
            monkeypatch.setenv("ARGUS_TURN_CALL_ALLOWANCE", "4")

        async def post(
            *,
            client: Any,
            api_key: str,
            payload: dict[str, Any],
            retry_attempt: tuple[Any, ...],
        ) -> httpx.Response:
            task, _, _, _, schema, _ = retry_attempt
            if schema == "LLMInterpretationResponse":
                if mode == "control" or mode.startswith("followup_"):
                    result = _primary_payload(language)
                    if mode.startswith("followup_"):
                        result.update(
                            task_relation=relation or "continue",
                            intent=followup_intent or "backtest_execution",
                            semantic_turn_act=followup_act or "answer_pending_need",
                        )
                        draft = result["candidate_strategy_draft"]
                        draft["extra_parameters"] = {}
                        if mode == "followup_no_progress":
                            draft.pop("initial_capital")
                            draft["field_provenance"].pop("initial_capital")
                else:
                    # Repair owns a typed test request, not an unread outage.
                    # Keep the money/cost repair matrix behind that ownership.
                    result = {
                        "intent": "strategy_drafting",
                        "task_relation": "new_task",
                        "requires_clarification": True,
                        "user_goal_summary": MESSAGES[language],
                        "semantic_turn_act": "new_idea",
                        "candidate_strategy_draft": {
                            "raw_user_phrasing": MESSAGES[language],
                            "strategy_thesis": MESSAGES[language],
                            "asset_universe": ["DOCN"],
                        },
                    }
            elif schema == "LLMAssetMentionExtraction":
                result = {
                    "all_traded_asset_mentions_included": True,
                    "asset_mentions": [
                        {
                            "raw_text": symbol,
                            "role": role,
                            "mention_kind": "ticker",
                            "confidence": 0.9,
                        }
                        for symbol, role in (
                            ("DOCN", "traded_asset"),
                            ("SPY", "benchmark"),
                        )
                    ],
                }
            elif schema == "FocusedStrategyExtraction":
                result = _focused_payload(language)
            elif schema == "FocusedDateWindowExtraction":
                focused = _focused_payload(language)
                result = {
                    "has_date_window": True,
                    "date_range_raw_text": focused["date_range_raw_text"],
                    "date_range_intent": focused["date_range_intent"],
                    "confidence": 0.9,
                }
            elif schema == "DcaContractAudit":
                result = {
                    "is_recurring_buy_request": True,
                    "recurring_contribution_amount": CONTRIBUTION,
                    "cadence": "monthly",
                    "total_budget_amount": None
                    if mode == "followup_no_progress"
                    else SEED,
                    "total_budget_source": "starting_capital",
                    "confidence": 0.9,
                }
            elif schema == "StrategyFamilyContinuityAudit":
                result = {"should_rebind_strategy_family": False, "confidence": 0.9}
            elif schema == "ArtifactAssumptionEditPlan":
                result = {"outcome": "ready_to_confirm", "confidence": 0.9}
            elif schema == "DcaContributionRoleAudit":
                result = {
                    "recurring_contribution_explicit": True,
                    "total_budget_not_recurring": False,
                    "confidence": 0.9,
                }
            elif schema == "StatedRunFieldFidelityAudit":
                if mode == "audit_unavailable":
                    raise asyncio.TimeoutError()
                result = {
                    "capital_amount": SEED,
                    "recurring_contribution_amount": CONTRIBUTION,
                    "cadence": "monthly",
                    "date_range": DATE_RANGE,
                    "comparison_baseline": "SPY",
                    "confidence": 0.9,
                    **_costs(language),
                }
                if mode.startswith("followup_"):
                    result = {"confidence": 0.9}
                if mode == "audit_omits_seed":
                    result["capital_amount"] = None
                if mode in {"audit_bad_fee_span", "audit_bad_slippage_span"}:
                    field = "fee" if mode == "audit_bad_fee_span" else "slippage"
                    result[field]["evidence_span"] = "not present in this message"
            else:
                raise AssertionError(f"Unexpected provider call: {task}/{schema}")
            return httpx.Response(
                200, json={"choices": [{"message": {"content": json.dumps(result)}}]}
            )

        monkeypatch.setattr(openrouter, "_post_openrouter_json_schema", post)

    return install


@pytest.mark.asyncio
@pytest.mark.parametrize("language", MESSAGES)
@pytest.mark.parametrize(
    "mode",
    [
        "repair",
        "audit_unavailable",
        "repair_on_exhausted_corridor",
        "audit_omits_seed",
        "audit_bad_fee_span",
        "audit_bad_slippage_span",
        "control",
    ],
)
async def test_focused_repair_delivers_stated_money_and_costs_or_asks(
    replay_transport: Callable[[str, str], None], language: str, mode: str
) -> None:
    replay_transport(language, mode)
    contract = build_default_capability_contract()
    user = UserState(user_id=Faker().uuid4(), language_preference=language)
    state = RunState.new(
        current_user_message=MESSAGES[language], recent_thread_history=[]
    )
    capture = openrouter.begin_openrouter_route_receipt_capture()
    try:
        with turn_execution_scope(entry_state={}) as execution:
            interpreted = await interpret_stage_async(
                state=state,
                user=user,
                latest_task_snapshot=None,
                selected_thread_metadata={"ui_language": language},
                structured_interpreter=OpenRouterStructuredInterpreter(contract=contract),
            )
            state = _patched_run_state(run_state=state, patch=interpreted.patch)
            if mode.startswith("audit_"):
                assert interpreted.outcome == "needs_clarification"
                pending = state.candidate_strategy_draft
                assert pending.capital_amount == CONTRIBUTION
                assert pending.extra_parameters["recurring_contribution"] == CONTRIBUTION
                if mode in {"audit_unavailable", "audit_omits_seed"}:
                    assert pending.extra_parameters.get("initial_capital") is None
                    candidates = [
                        field.candidate_normalized_value
                        for field in interpreted.decision.ambiguous_fields
                    ]
                    assert {"initial_capital": SEED} in candidates
                clarified = await clarify_stage_async(
                    state=state, contract=contract, language=language
                )
                assert clarified.outcome == "await_user_reply"
                assert (
                    "assumption" in clarified.patch["clarification"]["requested_fields"]
                )
                assert clarified.patch["clarification"]
                assert not interpreted.patch.get("confirmation_payload")
                assert {
                    "focused_repair_stated_fields_unresolved",
                    "execution_cost_evidence_unresolved",
                }.intersection(interpreted.decision.reason_codes)
            else:
                assert interpreted.outcome == "ready_for_confirmation"
                confirmed = await asyncio.to_thread(
                    confirm_stage, state=state, contract=contract, language=language
                )
                assert confirmed.outcome == "await_approval"
                payload = confirmed.patch["confirmation_payload"]
                launch = payload["launch_payload"]
                assert launch["starting_capital"] == SEED
                assert launch["recurring_contribution"] == CONTRIBUTION
                assert launch["cadence"] == "monthly"
                for field, value in (("fees", FEE_BPS), ("slippage", SLIPPAGE_BPS)):
                    assert payload["optional_parameters"][field][
                        "value"
                    ] == pytest.approx(value / 10000)
                    assert payload["optional_parameters"][field]["source"] == "user"
                card = runtime_confirmation_card(
                    {"stage_outcome": confirmed.outcome, **confirmed.patch},
                    language=language,
                )
                assert card is not None
                facts = card["display_facts"]
                assert facts["starting_capital"] == SEED
                assert facts["recurring_contribution"] == CONTRIBUTION
                assert facts["fees"] == pytest.approx(FEE_BPS / 10000)
                assert facts["slippage"] == pytest.approx(SLIPPAGE_BPS / 10000)
    finally:
        receipts = openrouter.end_openrouter_route_receipt_capture(capture)

    if mode != "control":
        assert any(
            r.task == "interpretation" and r.outcome == "succeeded" for r in receipts
        )
        assert any(
            r.schema_name == "FocusedStrategyExtraction" and r.outcome == "succeeded"
            for r in receipts
        )
    assert not any(r.failure_mode == "AssertionError" for r in receipts)
    # The repair's approval is funded even after the corridor is spent (#928).
    assert execution.repair_approval_grant_used == (
        1 if mode == "repair_on_exhausted_corridor" else 0
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("language", MESSAGES)
@pytest.mark.parametrize("mode", ["followup_no_progress", "followup_confirmed"])
@pytest.mark.parametrize("relation", ["continue", "ambiguous"])
@pytest.mark.parametrize(
    "route",
    [
        "backtest_execution/answer_pending_need",
        "conversation_followup/answer_pending_need",
        "conversation_followup/approval",
    ],
)
async def test_pending_deposit_survives_a_short_followup(
    replay_transport: Callable[[str, str], None],
    language: str,
    mode: str,
    relation: str,
    route: str,
) -> None:
    replay_transport(language, "audit_omits_seed")
    contract = build_default_capability_contract()
    interpreter = OpenRouterStructuredInterpreter(contract=contract)
    user = UserState(user_id=Faker().uuid4(), language_preference=language)
    state = RunState.new(
        current_user_message=MESSAGES[language], recent_thread_history=[]
    )
    workflow = {"run_state": state, "user": user, "artifact_references": []}
    with turn_execution_scope(entry_state={}):
        interpreted = await interpret_stage_async(
            state=state,
            user=user,
            latest_task_snapshot=None,
            selected_thread_metadata={"ui_language": language},
            structured_interpreter=interpreter,
        )
        workflow = _apply_stage_result(workflow, interpreted)
        clarified = await clarify_stage_async(
            state=workflow["run_state"], contract=contract, language=language
        )
        workflow = _apply_stage_result(workflow, clarified)
    metadata = json.loads(json.dumps(workflow["selected_thread_metadata"]))
    fields = metadata["response_intent"]["facts"]["ambiguous_fields"]
    assert any(
        field["candidate_normalized_value"] == {"initial_capital": SEED}
        for field in fields
    )
    pending = workflow["latest_task_snapshot"].pending_strategy_summary
    assert pending.capital_amount == CONTRIBUTION
    assert pending.extra_parameters.get("initial_capital") is None

    replay_transport(language, f"{mode}:{relation}:{route}")
    followup = RunState.new(
        current_user_message="Yes" if language == "en" else "Sí",
        recent_thread_history=[
            {"role": "user", "content": MESSAGES[language]},
            {"role": "assistant", "content": clarified.patch["assistant_prompt"]},
        ],
    )
    with turn_execution_scope(entry_state={}):
        result = await interpret_stage_async(
            state=followup,
            user=user,
            latest_task_snapshot=workflow["latest_task_snapshot"],
            selected_thread_metadata=metadata,
            structured_interpreter=interpreter,
        )
        followup = _patched_run_state(run_state=followup, patch=result.patch)
        assert "dca_capital_role_conflict" not in result.decision.reason_codes
        assert followup.candidate_strategy_draft.capital_amount == CONTRIBUTION
        if mode == "followup_no_progress":
            if result.outcome == "needs_clarification":
                repeated = await clarify_stage_async(
                    state=followup, contract=contract, language=language
                )
                assert repeated.outcome == "await_user_reply"
                response_intent = repeated.patch["response_intent"]
            else:
                # The existing no-progress owner can ask within interpret.
                assert result.outcome == "ready_to_respond"
                response_intent = result.patch["response_intent"]
                assert response_intent["facts"]["progress_outcome"] == "no_progress"
                assert result.decision.requires_clarification
                assert "confirmation_payload" not in result.patch
            assert response_intent["kind"] == "clarification"
            assert "assumption" in response_intent["requested_fields"]
            retained = response_intent["facts"]["ambiguous_fields"]
            assert any(
                field["candidate_normalized_value"] == {"initial_capital": SEED}
                for field in retained
            )
        else:
            assert result.outcome == "ready_for_confirmation"
            confirmed = await asyncio.to_thread(
                confirm_stage, state=followup, contract=contract, language=language
            )
            assert confirmed.outcome == "await_approval"
            launch = confirmed.patch["confirmation_payload"]["launch_payload"]
            assert launch["starting_capital"] == SEED
            assert launch["recurring_contribution"] == CONTRIBUTION
