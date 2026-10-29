# ruff: noqa: F403, F405
from tests.agent_runtime._llm_interpreter_common import *


def test_interpreter_facade_reexports_discovery_act_guard() -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module
    from argus.agent_runtime.interpreter.discovery_act_guard import (
        preserve_typed_discovery_act,
    )

    assert interpreter_module.preserve_typed_discovery_act is preserve_typed_discovery_act


@pytest.mark.asyncio
async def test_discovery_payload_restores_missing_semantic_act_without_strategy_audits(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module
    from argus.agent_runtime.stages.interpret_types import AssetDiscoveryRequest

    discovery = AssetDiscoveryRequest(
        relationship="category",
        category_description="cybersecurity stocks",
        asset_class_hint="equity",
        needs_current_facts=False,
    )
    response = LLMInterpretationResponse(
        intent="conversation_followup",
        task_relation="new_task",
        user_goal_summary="Find cybersecurity stocks to test.",
        semantic_turn_act=None,
        asset_discovery=discovery,
    )

    async def audited_response(**_kwargs):
        raise AssertionError("typed discovery must bypass strategy-readiness audits")

    monkeypatch.setattr(
        interpreter_module,
        "_audited_response_ready_for_runtime",
        audited_response,
    )

    repaired = await interpreter_module._response_ready_for_runtime(
        response=response,
        preferred_model="test-model",
        request=InterpretationRequest(
            current_user_message="Find cybersecurity stocks to test.",
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        ),
    )

    assert repaired.semantic_turn_act == "asset_discovery"
    assert repaired.asset_discovery == discovery
    assert "discovery_payload_act_promoted" in repaired.reason_codes


@pytest.mark.asyncio
async def test_missing_discovery_act_does_not_override_a_backtest_response(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module
    from argus.agent_runtime.stages.interpret_types import AssetDiscoveryRequest

    response = LLMInterpretationResponse(
        intent="backtest_execution",
        task_relation="new_task",
        user_goal_summary="Backtest Nvidia over the last year.",
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing="Backtest Nvidia over the last year.",
            strategy_type="buy_and_hold",
            strategy_thesis="Buy and hold Nvidia.",
            asset_universe=["NVDA"],
            asset_class="equity",
            date_range={"start": "2025-08-02", "end": "2026-08-02"},
        ),
        semantic_turn_act=None,
        asset_discovery=AssetDiscoveryRequest(
            relationship="category",
            category_description="semiconductor stocks",
            asset_class_hint="equity",
            needs_current_facts=False,
        ),
    )
    audited = False

    async def audited_response(**kwargs):
        nonlocal audited
        audited = True
        return interpreter_module._normalize_response_for_runtime_context(
            kwargs["response"],
            request=kwargs["request"],
            asset_resolution_context=kwargs["asset_resolution_context"],
        )

    monkeypatch.setattr(
        interpreter_module,
        "_audited_response_ready_for_runtime",
        audited_response,
    )

    repaired = await interpreter_module._response_ready_for_runtime(
        response=response,
        preferred_model="test-model",
        request=InterpretationRequest(
            current_user_message="Backtest Nvidia over the last year.",
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        ),
    )

    assert audited is True
    assert repaired.intent == "backtest_execution"
    assert repaired.semantic_turn_act == "new_idea"
    assert "coerced_missing_turn_act_to_new_idea" in repaired.reason_codes


def test_llm_interpreter_does_not_merge_prior_dca_into_fresh_strategy(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    monkeypatch.setattr(
        interpreter_module,
        "resolve_asset",
        lambda symbol: ResolvedAssetStub(symbol.upper(), "equity"),
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    response = LLMInterpretationResponse(
        intent="strategy_drafting",
        task_relation="new_task",
        user_goal_summary="User wants to define Apple dip buying.",
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing="What if I bought Apple after big drops?",
            strategy_type="indicator_threshold",
            strategy_thesis="Buy Apple after big drops.",
            asset_universe=["AAPL"],
        ),
    )

    result = interpreter._to_runtime_interpretation(
        response,
        request=InterpretationRequest(
            current_user_message="What if I bought Apple after big drops?",
            recent_thread_history=[],
            latest_task_snapshot=TaskSnapshot(
                latest_task_type="strategy_drafting",
                completed=False,
                pending_strategy_summary=StrategySummary(
                    strategy_type="dca_accumulation",
                    strategy_thesis="Buy a fixed amount every month.",
                    cadence="monthly",
                    capital_amount=500,
                ),
            ),
            user=UserState(user_id="u1"),
        ),
    )

    strategy = result.candidate_strategy_draft
    assert strategy.strategy_type == "indicator_threshold"
    assert strategy.asset_universe == ["AAPL"]
    assert strategy.cadence is None
    assert strategy.capital_amount is None


def test_provider_asset_context_resolves_only_llm_identified_mentions(
    monkeypatch,
) -> None:
    import json

    from argus.agent_runtime import llm_interpreter as interpreter_module

    queries: list[str] = []
    assets = {
        "target": ResolvedAssetStub("TGT", "equity", name="Target Corporation"),
        "walmart": ResolvedAssetStub("WMT", "equity", name="Walmart Inc."),
        "costco": ResolvedAssetStub("COST", "equity", name="Costco Wholesale Corp."),
    }

    def resolve_asset(query: str) -> ResolvedAssetStub:
        queries.append(query)
        key = query.strip().casefold()
        if key not in assets:
            raise ValueError("invalid_symbol")
        return assets[key]

    monkeypatch.setattr(interpreter_module, "resolve_asset", resolve_asset)

    context = interpreter_module._provider_asset_resolution_context_from_extraction(
        interpreter_module.LLMAssetMentionExtraction(
            asset_mentions=[
                {"raw_text": "target", "role": "traded_asset", "confidence": 0.9},
                {"raw_text": "Walmart", "role": "traded_asset", "confidence": 0.9},
                {"raw_text": "costco", "role": "traded_asset", "confidence": 0.9},
            ],
            all_traded_asset_mentions_included=True,
        )
    )

    assert queries == ["target", "Walmart", "costco"]
    assert context is not None
    payload = json.loads(context)
    rows = payload["asset_resolution_candidates"]
    assert [row["symbol"] for row in rows] == ["TGT", "WMT", "COST"]
    assert not {"buy", "with", "every", "month", "February"} & set(queries)


def test_provider_asset_context_dedupes_before_the_five_mention_cap(
    monkeypatch,
) -> None:
    import json

    from argus.agent_runtime import llm_interpreter as interpreter_module

    assets = {
        "target": ResolvedAssetStub("TGT", "equity", name="Target Corporation"),
        "walmart": ResolvedAssetStub("WMT", "equity", name="Walmart Inc."),
        "nvidia": ResolvedAssetStub("NVDA", "equity", name="NVIDIA Corporation"),
    }

    def resolve_asset(query: str) -> ResolvedAssetStub:
        key = query.strip().casefold()
        if key not in assets:
            raise ValueError("invalid_symbol")
        return assets[key]

    monkeypatch.setattr(interpreter_module, "resolve_asset", resolve_asset)

    # Duplicates and a blank fill the first five slots; the distinct sixth asset
    # must still survive because dedupe/blank-filtering happen before the cap.
    context = interpreter_module._provider_asset_resolution_context_from_extraction(
        interpreter_module.LLMAssetMentionExtraction(
            asset_mentions=[
                {"raw_text": "target", "role": "traded_asset", "confidence": 0.9},
                {"raw_text": "Target", "role": "traded_asset", "confidence": 0.9},
                {"raw_text": "   ", "role": "traded_asset", "confidence": 0.9},
                {"raw_text": "walmart", "role": "traded_asset", "confidence": 0.9},
                {"raw_text": "Walmart", "role": "traded_asset", "confidence": 0.9},
                {"raw_text": "nvidia", "role": "traded_asset", "confidence": 0.9},
            ],
            all_traded_asset_mentions_included=True,
        )
    )

    assert context is not None
    rows = json.loads(context)["asset_resolution_candidates"]
    assert [row["symbol"] for row in rows] == ["TGT", "WMT", "NVDA"]


def test_provider_asset_context_uses_name_search_for_company_mentions() -> None:
    import json

    from argus.agent_runtime import llm_interpreter as interpreter_module
    from argus.agent_runtime.resolution import AssetResolution

    calls: list[tuple[str, str, str | None]] = []
    target = ResolvedAssetStub("TGT", "equity", name="Target Corporation")

    def resolve_candidate(
        query: str,
        *,
        field: str,
        source: str,
        resolution_mode: str = "auto",
        asset_class_hint: str | None = None,
    ) -> AssetResolution:
        del field, source
        calls.append((query, resolution_mode, asset_class_hint))
        return AssetResolution(
            status="resolved",
            raw_text=query,
            asset=target,
            candidates=(target,),
            provenance=ResolutionProvenance(
                field="asset_universe[0]",
                raw_text=query,
                source="llm_extraction",
                candidate_kind="asset",
                resolution_status="resolved",
                canonical_symbol="TGT",
                asset_class="equity",
                validated_by="provider_catalog",
                confidence="medium",
            ),
        )

    context = interpreter_module.provider_asset_resolution_context_from_extraction(
        interpreter_module.LLMAssetMentionExtraction(
            asset_mentions=[
                {
                    "raw_text": "target",
                    "role": "traded_asset",
                    "mention_kind": "company_name",
                    "confidence": 0.9,
                },
            ],
            all_traded_asset_mentions_included=True,
        ),
        resolve_asset_candidate=resolve_candidate,
    )

    assert calls == [("target", "company_name", None)]
    assert context is not None
    rows = json.loads(context)["asset_resolution_candidates"]
    assert [row["symbol"] for row in rows] == ["TGT"]


def test_provider_asset_context_uses_name_search_for_crypto_name_mentions() -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module
    from argus.agent_runtime.resolution import AssetResolution

    calls: list[tuple[str, str, str | None]] = []
    ethereum = ResolvedAssetStub("ETH", "crypto", name="Ethereum")

    def resolve_candidate(
        query: str,
        *,
        field: str,
        source: str,
        resolution_mode: str = "auto",
        asset_class_hint: str | None = None,
    ) -> AssetResolution:
        del field, source
        calls.append((query, resolution_mode, asset_class_hint))
        return AssetResolution(
            status="resolved",
            raw_text=query,
            asset=ethereum,
            candidates=(ethereum,),
            provenance=ResolutionProvenance(
                field="asset_universe[0]",
                raw_text=query,
                source="llm_extraction",
                candidate_kind="asset",
                resolution_status="resolved",
                canonical_symbol="ETH",
                asset_class="crypto",
                validated_by="provider_catalog",
                confidence="medium",
            ),
        )

    context = interpreter_module.provider_asset_resolution_context_from_extraction(
        interpreter_module.LLMAssetMentionExtraction(
            asset_mentions=[
                {
                    "raw_text": "ethereum",
                    "role": "traded_asset",
                    "mention_kind": "crypto",
                    "confidence": 0.9,
                },
                {
                    "raw_text": "ETH",
                    "role": "traded_asset",
                    "mention_kind": "crypto",
                    "confidence": 0.9,
                },
            ],
            all_traded_asset_mentions_included=True,
        ),
        resolve_asset_candidate=resolve_candidate,
    )

    assert calls == [
        ("ethereum", "company_name", "crypto"),
        ("ETH", "symbol", "crypto"),
    ]
    assert context is not None


def test_provider_context_prevents_wrong_exact_symbol_for_company_name() -> None:
    import json

    from argus.agent_runtime import llm_interpreter as interpreter_module

    context = json.dumps(
        {
            "asset_resolution_candidates": [
                {
                    "raw_text": "target",
                    "role": "traded_asset",
                    "status": "resolved",
                    "symbol": "TGT",
                    "asset_class": "equity",
                    "name": "Target Corporation",
                    "confidence": 0.94,
                },
                {
                    "raw_text": "Walmart",
                    "role": "traded_asset",
                    "status": "resolved",
                    "symbol": "WMT",
                    "asset_class": "equity",
                    "name": "Walmart Inc.",
                    "confidence": 0.94,
                },
                {
                    "raw_text": "costco",
                    "role": "traded_asset",
                    "status": "resolved",
                    "symbol": "COST",
                    "asset_class": "equity",
                    "name": "Costco Wholesale Corporation",
                    "confidence": 0.94,
                },
            ]
        }
    )
    response = LLMInterpretationResponse(
        intent="backtest_execution",
        task_relation="new_task",
        user_goal_summary="User wants monthly recurring buys in Target, Walmart, and Costco.",
        candidate_strategy_draft=LLMStrategyDraft(
            strategy_type="dca_accumulation",
            asset_universe=["TGAAF", "WMT", "COST"],
            asset_class="equity",
            date_range={"start": "2020-02-01", "end": "today"},
            recurring_contribution=500,
            cadence="monthly",
        ),
        semantic_turn_act="new_idea",
    )

    normalized = interpreter_module._normalize_response_for_runtime_context(
        response,
        request=InterpretationRequest(
            current_user_message=(
                "Id like to buy target Walmart and costco evenly with 500 dollars "
                "every month from February 2020 till today"
            ),
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        ),
        asset_resolution_context=context,
    )

    assert normalized.candidate_strategy_draft.asset_universe == [
        "TGT",
        "WMT",
        "COST",
    ]
    assert normalized.candidate_strategy_draft.asset_class == "equity"


@pytest.mark.parametrize("with_unsupported_constraint", [True, False])
def test_unsupported_request_preserves_provider_asset_and_explicit_window(
    with_unsupported_constraint: bool,
) -> None:
    import json

    from argus.agent_runtime import llm_interpreter as interpreter_module

    context = json.dumps(
        {
            "asset_resolution_candidates": [
                {
                    "raw_text": "TSLA",
                    "role": "traded_asset",
                    "status": "resolved",
                    "symbol": "TSLA",
                    "asset_class": "equity",
                    "name": "Tesla, Inc.",
                    "confidence": 0.94,
                }
            ]
        }
    )
    response = LLMInterpretationResponse(
        intent="unsupported_or_out_of_scope",
        task_relation="new_task",
        requires_clarification=True,
        user_goal_summary="User wants to run an options straddle on TSLA.",
        candidate_strategy_draft=LLMStrategyDraft(),
        unsupported_constraints=[
            interpreter_module.LLMUnsupportedConstraint(
                category="unsupported_strategy_logic",
                raw_value="options straddle",
                explanation="Options straddles are not executable yet.",
            )
        ]
        if with_unsupported_constraint
        else [],
        semantic_turn_act="unsupported_request",
    )

    normalized = interpreter_module._normalize_response_for_runtime_context(
        response,
        request=InterpretationRequest(
            current_user_message=(
                "can you run an options straddle on TSLA from 2024-01-01 "
                "through 2024-12-31?"
            ),
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        ),
        asset_resolution_context=context,
    )

    draft = normalized.candidate_strategy_draft
    assert normalized.intent == "unsupported_or_out_of_scope"
    assert normalized.semantic_turn_act == "unsupported_request"
    if with_unsupported_constraint:
        assert normalized.unsupported_constraints[0].category == (
            "unsupported_strategy_logic"
        )
    else:
        # The runtime never invents constraints or displaces the refusal.
        assert normalized.unsupported_constraints == []
    assert draft.asset_universe == ["TSLA"]
    assert draft.asset_class == "equity"
    # date_range is not backfilled: filled run fields would suppress the
    # focused repair of wrongly-refused supported ideas.
    assert not draft.date_range
    assert draft.comparison_baseline == "SPY"


def test_unsupported_recovery_calendar_year_intent_survives_without_bare_year_provenance(
    monkeypatch,
) -> None:
    import asyncio
    import json

    from argus.agent_runtime import llm_interpreter as interpreter_module
    from argus.agent_runtime.llm_interpreter_types import (
        FocusedDateWindowExtraction,
        LLMUnsupportedConstraint,
    )

    async def asset_grounding_passthrough(*, response, **kwargs):
        del kwargs
        return response

    async def schema_stub(*, schema_name: str, **kwargs):
        del kwargs
        if schema_name == "FocusedDateWindowExtraction":
            return FocusedDateWindowExtraction(
                has_date_window=True,
                date_range_intent=LLMDateRangeIntent(
                    kind="calendar_year",
                    year=2024,
                    evidence="2024",
                ),
                date_range_raw_text="2024",
                evidence="2024",
                confidence=0.9,
            )
        return None

    schema_stub.__module__ = "argus.llm.openrouter"
    monkeypatch.setattr(
        interpreter_module,
        "_asset_grounding_audited_response",
        asset_grounding_passthrough,
    )
    monkeypatch.setattr(
        interpreter_module,
        "openrouter_structured_model_candidates",
        lambda *args, **kwargs: ["test-model"],
    )
    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        schema_stub,
    )

    context = json.dumps(
        {
            "asset_resolution_candidates": [
                {
                    "raw_text": "AAPL",
                    "role": "traded_asset",
                    "status": "resolved",
                    "symbol": "AAPL",
                    "asset_class": "equity",
                    "name": "Apple Inc.",
                    "confidence": 0.94,
                }
            ]
        }
    )
    response = LLMInterpretationResponse(
        intent="unsupported_or_out_of_scope",
        task_relation="new_task",
        requires_clarification=True,
        user_goal_summary="User wants weekly options on Apple in 2024.",
        candidate_strategy_draft=LLMStrategyDraft(
            date_range_intent=LLMDateRangeIntent(
                kind="calendar_year",
                year=2024,
            ),
        ),
        unsupported_constraints=[
            LLMUnsupportedConstraint(
                category="unsupported_strategy_logic",
                raw_value="weekly options",
                explanation="Weekly options are not executable yet.",
            )
        ],
        semantic_turn_act="unsupported_request",
    )

    normalized = asyncio.run(
        interpreter_module._response_ready_for_runtime(
            response=response,
            preferred_model="test-model",
            request=InterpretationRequest(
                current_user_message=(
                    "please backtest weekly options on apple during 2024"
                ),
                recent_thread_history=[],
                latest_task_snapshot=None,
                user=UserState(user_id="u1"),
            ),
            asset_resolution_context=context,
        )
    )

    draft = normalized.candidate_strategy_draft
    observed = {
        "assets": draft.asset_universe,
        "date_range": draft.date_range,
    }
    assert normalized.intent == "unsupported_or_out_of_scope"
    assert draft.asset_class == "equity"
    assert draft.comparison_baseline == "SPY"
    assert observed == {
        "assets": ["AAPL"],
        "date_range": {"start": "2024-01-01", "end": "2024-12-31"},
    }


def test_company_name_basket_context_survives_underfilled_repair_to_confirmation(
    monkeypatch,
) -> None:
    import asyncio
    import json

    from argus.agent_runtime import llm_interpreter as interpreter_module
    from argus.agent_runtime.stages.confirm import confirm_stage

    async def asset_grounding_passthrough(*, response, **kwargs):
        del kwargs
        return response

    async def schema_stub(*, schema_name: str, **kwargs):
        del kwargs
        if schema_name == "StatedRunFieldFidelityAudit":
            return interpreter_module.StatedRunFieldFidelityAudit()
        if schema_name == "FocusedStrategyExtraction":
            return FocusedStrategyExtraction(
                is_testable_strategy=True,
                requires_clarification=False,
                user_goal_summary="Plain hold test for Target, Walmart, and Costco.",
                strategy_type="buy_and_hold",
                strategy_thesis="Buy and hold Target, Walmart, and Costco.",
                asset_universe=[],
                asset_class="equity",
                date_range={"start": "2024-01-01", "end": "2024-12-31"},
                confidence=0.9,
            )
        return None

    schema_stub.__module__ = "argus.llm.openrouter"
    monkeypatch.setattr(
        interpreter_module,
        "_asset_grounding_audited_response",
        asset_grounding_passthrough,
    )
    monkeypatch.setattr(
        interpreter_module,
        "openrouter_structured_model_candidates",
        lambda *args, **kwargs: ["test-model"],
    )
    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        schema_stub,
    )

    context = json.dumps(
        {
            "asset_resolution_candidates": [
                {
                    "raw_text": "target",
                    "role": "traded_asset",
                    "status": "resolved",
                    "symbol": "TGT",
                    "asset_class": "equity",
                    "name": "Target Corporation",
                    "confidence": 0.95,
                },
                {
                    "raw_text": "walmart",
                    "role": "traded_asset",
                    "status": "resolved",
                    "symbol": "WMT",
                    "asset_class": "equity",
                    "name": "Walmart Inc.",
                    "confidence": 0.95,
                },
                {
                    "raw_text": "costco",
                    "role": "traded_asset",
                    "status": "resolved",
                    "symbol": "COST",
                    "asset_class": "equity",
                    "name": "Costco Wholesale Corporation",
                    "confidence": 0.95,
                },
            ],
            "all_traded_asset_mentions_accounted_for": True,
        }
    )
    message = (
        "try a plain hold test for target, walmart, and costco from jan 2024 "
        "through dec 2024"
    )
    interpretation = asyncio.run(
        interpreter_module._response_ready_for_runtime(
            response=LLMInterpretationResponse(
                intent="strategy_drafting",
                task_relation="new_task",
                requires_clarification=True,
                user_goal_summary="User wants a plain hold test for retailers.",
                candidate_strategy_draft=LLMStrategyDraft(
                    raw_user_phrasing=message,
                    strategy_thesis=message,
                ),
                semantic_turn_act="new_idea",
            ),
            preferred_model="test-model",
            request=InterpretationRequest(
                current_user_message=message,
                recent_thread_history=[],
                latest_task_snapshot=None,
                user=UserState(user_id="u1"),
            ),
            asset_resolution_context=context,
        )
    )

    strategy = interpretation.candidate_strategy_draft
    ready_for_confirmation = (
        interpretation.intent in {"strategy_drafting", "backtest_execution"}
        and interpretation.requires_clarification is False
        and interpretation.unsupported_constraints == []
        and strategy.strategy_type == "buy_and_hold"
        and bool(strategy.asset_universe)
        and bool(strategy.date_range)
    )
    stage_outcomes = [
        "ready_for_confirmation" if ready_for_confirmation else "needs_clarification"
    ]
    capability_verdict = "unsupported"
    benchmark_symbol = None
    confirmation_card_count = 0
    if ready_for_confirmation:
        confirm_state = RunState.new(
            current_user_message=message,
            recent_thread_history=[],
        )
        confirm_state.candidate_strategy_draft = strategy
        confirm_result = confirm_stage(
            state=confirm_state,
            contract=build_default_capability_contract(),
        )
        stage_outcomes.append(confirm_result.outcome)
        confirmation_payload = confirm_result.patch["confirmation_payload"]
        validation = confirmation_payload["validation"]
        benchmark_symbol = confirmation_payload["launch_payload"]["benchmark_symbol"]
        confirmation_card_count = 1
        if validation.get("executable") is True:
            capability_verdict = "executable"

    observed = {
        "assets": strategy.asset_universe,
        "asset_class": strategy.asset_class,
        "benchmark_symbol": benchmark_symbol,
        "strategy_type": strategy.strategy_type,
        "date_range": strategy.date_range,
        "capability_verdict": capability_verdict,
        "confirmation_card_count": confirmation_card_count,
        "stage_outcomes": stage_outcomes,
    }
    assert observed == {
        "assets": ["TGT", "WMT", "COST"],
        "asset_class": "equity",
        "benchmark_symbol": "SPY",
        "strategy_type": "buy_and_hold",
        "date_range": {"start": "2024-01-01", "end": "2024-12-31"},
        "capability_verdict": "executable",
        "confirmation_card_count": 1,
        "stage_outcomes": ["ready_for_confirmation", "await_approval"],
    }


def test_partial_provider_context_confirms_after_current_message_grounding(
    monkeypatch,
) -> None:
    import json

    from argus.agent_runtime import llm_interpreter as interpreter_module
    from argus.agent_runtime.stages import interpret as interpret_module
    from argus.agent_runtime.stages.confirm import confirm_stage

    assets = {
        "TGT": ResolvedAssetStub("TGT", "equity", name="Target Corporation"),
        "WMT": ResolvedAssetStub("WMT", "equity", name="Walmart Inc."),
        "COST": ResolvedAssetStub(
            "COST",
            "equity",
            name="Costco Wholesale Corporation",
        ),
    }
    aliases = {
        "target": "TGT",
        "walmart": "WMT",
        "costco": "COST",
    }

    def resolve_asset(symbol: str) -> ResolvedAssetStub:
        raw = symbol.strip()
        normalized = aliases.get(raw.casefold(), raw.upper())
        if normalized not in assets:
            raise ValueError("invalid_symbol")
        return assets[normalized]

    monkeypatch.setattr(interpreter_module, "resolve_asset", resolve_asset)
    monkeypatch.setattr(interpret_module, "resolve_asset", resolve_asset)

    message = (
        "try a plain hold test for target, walmart, and costco from jan 2024 "
        "through dec 2024"
    )
    context = json.dumps(
        {
            "asset_resolution_candidates": [
                {
                    "raw_text": "target",
                    "role": "traded_asset",
                    "status": "resolved",
                    "symbol": "TGT",
                    "asset_class": "equity",
                    "name": "Target Corporation",
                    "confidence": 0.95,
                }
            ]
        }
    )
    contract = build_default_capability_contract()

    class PartialContextInterpreter:
        async def ainvoke(self, request):
            response = await interpreter_module._response_ready_for_runtime(
                response=LLMInterpretationResponse(
                    intent="strategy_drafting",
                    task_relation="new_task",
                    requires_clarification=False,
                    user_goal_summary="User wants a plain hold test for retailers.",
                    candidate_strategy_draft=LLMStrategyDraft(
                        raw_user_phrasing=message,
                        strategy_type="buy_and_hold",
                        strategy_thesis=message,
                        asset_universe=["walmart", "costco"],
                        asset_class="equity",
                        date_range={
                            "start": "2024-01-01",
                            "end": "2024-12-31",
                        },
                    ),
                    semantic_turn_act="new_idea",
                ),
                preferred_model="test-model",
                request=request,
                asset_resolution_context=context,
            )
            return OpenRouterStructuredInterpreter(
                contract=contract
            )._to_runtime_interpretation(response, request=request)

    interpret_result = interpret_stage(
        state=RunState.new(
            current_user_message=message,
            recent_thread_history=[],
        ),
        user=UserState(user_id="u1"),
        latest_task_snapshot=None,
        structured_interpreter=PartialContextInterpreter(),
    )

    assert interpret_result.outcome == "ready_for_confirmation"
    assert interpret_result.decision is not None
    strategy = interpret_result.decision.candidate_strategy_draft
    confirm_state = RunState.new(
        current_user_message=message,
        recent_thread_history=[],
    )
    confirm_state.candidate_strategy_draft = strategy
    confirm_result = confirm_stage(
        state=confirm_state,
        contract=contract,
    )

    assert strategy.asset_universe == ["TGT", "WMT", "COST"]
    assert (
        "provider_context_partial_preserved_fuller_draft"
        in interpret_result.decision.reason_codes
    )
    assert (
        "provider_context_partial_grounded_by_current_message"
        in interpret_result.decision.reason_codes
    )
    assert interpret_result.decision.ambiguous_fields == []
    assert confirm_result.outcome == "await_approval"
    assert confirm_result.patch["confirmation_payload"]["validation"][
        "executable"
    ] is True


@pytest.mark.parametrize("audit_available", [True, False])
def test_partial_provider_context_seeds_omitted_grounded_asset_when_extras_fail_audit(
    monkeypatch,
    audit_available: bool,
) -> None:
    import asyncio
    import json

    from argus.agent_runtime import llm_interpreter as interpreter_module
    from argus.agent_runtime.stages import interpret as interpret_module

    assets = {
        "TGT": ResolvedAssetStub("TGT", "equity", name="Target Corporation"),
        "WMT": ResolvedAssetStub("WMT", "equity", name="Walmart Inc."),
        "COST": ResolvedAssetStub(
            "COST",
            "equity",
            name="Costco Wholesale Corporation",
        ),
        "BTC": ResolvedAssetStub("BTC", "crypto", name="Bitcoin"),
    }
    aliases = {
        "target": "TGT",
        "walmart": "WMT",
        "costco": "COST",
        "bitcoin": "BTC",
    }

    def resolve_asset(symbol: str) -> ResolvedAssetStub:
        raw = symbol.strip()
        normalized = aliases.get(raw.casefold(), raw.upper())
        if normalized not in assets:
            raise ValueError("invalid_symbol")
        return assets[normalized]

    async def audit_stub(**kwargs):
        assert kwargs["schema_name"] == "AssetGroundingAudit"
        if not audit_available:
            raise RuntimeError("asset grounding audit unavailable")
        return interpreter_module.AssetGroundingAudit(
            grounded_symbols=[],
            confidence=0.95,
        )

    monkeypatch.setattr(interpreter_module, "resolve_asset", resolve_asset)
    monkeypatch.setattr(interpret_module, "resolve_asset", resolve_asset)
    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        audit_stub,
    )
    context = json.dumps(
        {
            "asset_resolution_candidates": [
                {
                    "raw_text": "target",
                    "role": "traded_asset",
                    "status": "resolved",
                    "symbol": "TGT",
                    "asset_class": "equity",
                    "name": "Target Corporation",
                    "confidence": 0.95,
                }
            ]
        }
    )
    message = "try a plain hold test for target from jan 2024 through dec 2024"
    response = interpreter_module._normalize_response_for_runtime_context(
        LLMInterpretationResponse(
            intent="strategy_drafting",
            task_relation="new_task",
            requires_clarification=False,
            user_goal_summary="User wants a plain hold test for Target.",
            candidate_strategy_draft=LLMStrategyDraft(
                raw_user_phrasing=message,
                strategy_type="buy_and_hold",
                strategy_thesis=message,
                asset_universe=["walmart", "costco", "bitcoin"],
                asset_class="equity",
                date_range={"start": "2024-01-01", "end": "2024-12-31"},
            ),
            semantic_turn_act="new_idea",
        ),
        request=InterpretationRequest(
            current_user_message=message,
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        ),
        asset_resolution_context=context,
    )

    audited = asyncio.run(
        interpreter_module._asset_grounding_audited_response(
            response=response,
            preferred_model="test-model",
            request=InterpretationRequest(
                current_user_message=message,
                recent_thread_history=[],
                latest_task_snapshot=None,
                user=UserState(user_id="u1"),
            ),
        )
    )

    assert audited.requires_clarification is True
    assert audited.candidate_strategy_draft.asset_universe == ["TGT"]
    assert audited.candidate_strategy_draft.asset_class == "equity"
    assert [field.reason_code for field in audited.ambiguous_fields] == [
        "asset_resolution_context_underfilled"
    ]


def test_successful_asset_audit_clears_partial_context_ambiguity() -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module
    from argus.agent_runtime.llm_interpreter_types import LLMAmbiguousField

    response = LLMInterpretationResponse(
        intent="strategy_drafting",
        task_relation="new_task",
        requires_clarification=True,
        user_goal_summary="User wants a plain hold test for three retailers.",
        candidate_strategy_draft=LLMStrategyDraft(
            strategy_type="buy_and_hold",
            asset_universe=["TGT", "WMT", "COST"],
            asset_class="equity",
            date_range={"start": "2024-01-01", "end": "2024-12-31"},
        ),
        reason_codes=["provider_context_partial_preserved_fuller_draft"],
        ambiguous_fields=[
            LLMAmbiguousField(
                field_name="asset_universe",
                raw_value="target",
                candidate_normalized_value=["TGT"],
                reason_code="asset_resolution_context_underfilled",
            )
        ],
        semantic_turn_act="new_idea",
    )

    audited = interpreter_module._response_without_ungrounded_symbols(
        response=response,
        grounded_symbols=["TGT", "WMT", "COST"],
        reason_code="asset_grounding_audit_removed_unsubstantiated_symbols",
    )

    assert audited.requires_clarification is False
    assert audited.candidate_strategy_draft.asset_universe == ["TGT", "WMT", "COST"]
    assert audited.ambiguous_fields == []


def test_partial_provider_context_seeds_symbol_and_defers_name_variation() -> None:
    import json

    from argus.agent_runtime.interpreter import provider_context_assets

    context = json.dumps(
        {
            "asset_resolution_candidates": [
                {
                    "raw_text": "walmart",
                    "role": "traded_asset",
                    "status": "resolved",
                    "symbol": "WMT",
                    "asset_class": "equity",
                    "name": "Walmart Inc.",
                    "confidence": 0.95,
                }
            ]
        }
    )
    response = LLMInterpretationResponse(
        intent="strategy_drafting",
        task_relation="new_task",
        requires_clarification=False,
        user_goal_summary="User wants a plain hold test for two retailers.",
        candidate_strategy_draft=LLMStrategyDraft(
            strategy_type="buy_and_hold",
            asset_universe=["Walmart Inc", "Costco Wholesale"],
            asset_class="equity",
            date_range={"start": "2024-01-01", "end": "2024-12-31"},
        ),
        semantic_turn_act="new_idea",
    )

    normalized = provider_context_assets.response_with_provider_context_assets(
        response,
        asset_resolution_context=context,
    )

    assert normalized.candidate_strategy_draft.asset_universe == [
        "WMT",
        "Walmart Inc",
        "Costco Wholesale",
    ]
    assert normalized.requires_clarification is True
    assert [field.reason_code for field in normalized.ambiguous_fields] == [
        "asset_resolution_context_underfilled"
    ]
    assert "provider_context_partial_preserved_fuller_draft" in (
        normalized.reason_codes
    )


def test_unsupported_turn_with_partial_provider_context_drops_ungrounded_assets(
) -> None:
    import json

    from argus.agent_runtime.interpreter import provider_context_assets

    context = json.dumps(
        {
            "asset_resolution_candidates": [
                {
                    "raw_text": "target",
                    "role": "traded_asset",
                    "status": "resolved",
                    "symbol": "TGT",
                    "asset_class": "equity",
                    "name": "Target Corporation",
                    "confidence": 0.95,
                }
            ]
        }
    )
    response = LLMInterpretationResponse(
        intent="unsupported_or_out_of_scope",
        task_relation="new_task",
        requires_clarification=True,
        user_goal_summary="User asked for unsupported logic on a retailer basket.",
        candidate_strategy_draft=LLMStrategyDraft(
            strategy_type="buy_and_hold",
            asset_universe=["TGT", "FAKE"],
            asset_class="equity",
        ),
        semantic_turn_act="unsupported_request",
    )

    normalized = provider_context_assets.response_with_provider_context_assets(
        response,
        asset_resolution_context=context,
        include_unsupported_request=True,
    )

    assert normalized.intent == "unsupported_or_out_of_scope"
    assert normalized.candidate_strategy_draft.asset_universe == ["TGT"]
    assert (
        "provider_context_partial_preserved_fuller_draft"
        not in normalized.reason_codes
    )


def test_provider_context_asset_class_survives_runtime_validation(monkeypatch) -> None:
    import json

    from argus.agent_runtime import llm_interpreter as interpreter_module

    monkeypatch.setattr(
        interpreter_module,
        "resolve_asset",
        lambda symbol: ResolvedAssetStub(symbol.upper(), "equity", name="Equity ETH"),
    )
    context = json.dumps(
        {
            "asset_resolution_candidates": [
                {
                    "raw_text": "ethereum",
                    "role": "traded_asset",
                    "status": "resolved",
                    "symbol": "ETH",
                    "asset_class": "crypto",
                    "name": "Ethereum",
                    "mention_kind": "crypto",
                    "confidence": 0.94,
                }
            ]
        }
    )
    request = InterpretationRequest(
        current_user_message=(
            "backtest holding ethereum from 2024-01-01 to 2024-03-31 "
            "against the default crypto benchmark"
        ),
        recent_thread_history=[],
        latest_task_snapshot=None,
        user=UserState(user_id="u1"),
    )
    response = LLMInterpretationResponse(
        intent="backtest_execution",
        task_relation="new_task",
        user_goal_summary="User wants to hold Ethereum.",
        candidate_strategy_draft=LLMStrategyDraft(
            strategy_type="buy_and_hold",
            asset_universe=["ETH"],
            asset_class="equity",
            date_range={"start": "2024-01-01", "end": "2024-03-31"},
            comparison_baseline="BTC",
        ),
        semantic_turn_act="new_idea",
    )

    normalized = interpreter_module._normalize_response_for_runtime_context(
        response,
        request=request,
        asset_resolution_context=context,
    )
    result = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )._to_runtime_interpretation(normalized, request=request)

    assert result.candidate_strategy_draft.asset_universe == ["ETH"]
    assert result.candidate_strategy_draft.asset_class == "crypto"


def test_canonical_interpreter_assets_use_draft_asset_class_hint(monkeypatch) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    calls: list[str | None] = []

    def resolve_candidate(
        query: str,
        *,
        field: str,
        source: str,
        resolution_mode: str = "auto",
        asset_class_hint: str | None = None,
    ) -> AssetResolution:
        del resolution_mode
        calls.append(asset_class_hint)
        asset = ResolvedAssetStub(query.upper(), asset_class_hint or "equity")
        return AssetResolution(
            status="resolved",
            raw_text=query,
            asset=asset,
            candidates=(asset,),
            provenance=ResolutionProvenance(
                field=field,
                raw_text=query,
                source=source,
                candidate_kind="asset",
                resolution_status="resolved",
                canonical_symbol=asset.canonical_symbol,
                asset_class=asset.asset_class,
                validated_by="provider_catalog",
                confidence="medium",
            ),
        )

    monkeypatch.setattr(
        interpreter_module,
        "resolve_asset",
        interpreter_module._DEFAULT_RESOLVE_ASSET,
    )
    monkeypatch.setattr(
        interpreter_module,
        "runtime_resolve_asset_candidate",
        resolve_candidate,
    )

    normalized = interpreter_module._response_with_canonical_interpreter_assets(
        LLMInterpretationResponse(
            intent="backtest_execution",
            task_relation="new_task",
            user_goal_summary="User wants to hold Bitcoin.",
            candidate_strategy_draft=LLMStrategyDraft(
                strategy_type="buy_and_hold",
                asset_universe=["BTC"],
                asset_class="crypto",
                date_range={"start": "2024-01-01", "end": "2024-03-31"},
            ),
            semantic_turn_act="new_idea",
        )
    )

    assert calls == ["crypto"]
    assert normalized.candidate_strategy_draft.asset_universe == ["BTC"]
    assert normalized.candidate_strategy_draft.asset_class == "crypto"


@pytest.mark.asyncio
async def test_focused_strategy_repair_applies_provider_asset_context(
    monkeypatch,
) -> None:
    import json

    from argus.agent_runtime import llm_interpreter as interpreter_module

    async def invoke_schema(**kwargs):
        del kwargs
        return FocusedStrategyExtraction(
            is_testable_strategy=True,
            requires_clarification=False,
            user_goal_summary="User wants to hold Bitcoin.",
            strategy_type="buy_and_hold",
            strategy_thesis="Buy and hold Bitcoin.",
            asset_universe=["BTC"],
            asset_class="equity",
            date_range={"start": "2024-01-01", "end": "2024-03-31"},
        )

    monkeypatch.setattr(
        interpreter_module,
        "_unique_repair_models",
        lambda preferred_model, task: ["test-model"],
    )
    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        invoke_schema,
    )

    response = await interpreter_module._repair_incomplete_strategy_extraction(
        failed_response=LLMInterpretationResponse(
            intent="strategy_drafting",
            task_relation="new_task",
            requires_clarification=True,
            user_goal_summary="User wants to hold Bitcoin.",
            candidate_strategy_draft=LLMStrategyDraft(
                raw_user_phrasing="comprar y mantener bitcoin",
                strategy_thesis="comprar y mantener bitcoin",
            ),
            semantic_turn_act="new_idea",
        ),
        preferred_model="test-model",
        request=InterpretationRequest(
            current_user_message="comprar y mantener bitcoin",
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1", language_preference="es-419"),
        ),
        asset_resolution_context=json.dumps(
            {
                "asset_resolution_candidates": [
                    {
                        "raw_text": "bitcoin",
                        "role": "traded_asset",
                        "status": "resolved",
                        "symbol": "BTC",
                        "asset_class": "crypto",
                        "name": "Bitcoin / US Dollar",
                        "raw_symbol": "BTC/USD",
                        "provider": "alpaca",
                        "exchange": "CRYPTO",
                        "mention_kind": "crypto",
                        "confidence": 0.95,
                    }
                ]
            }
        ),
    )

    assert response is not None
    assert response.candidate_strategy_draft.asset_universe == ["BTC"]
    assert response.candidate_strategy_draft.asset_class == "crypto"


def test_llm_interpreter_removes_stale_indicator_limit_when_user_only_said_drops(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    monkeypatch.setattr(
        interpreter_module,
        "resolve_asset",
        lambda symbol: ResolvedAssetStub(symbol.upper(), "equity"),
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    response = LLMInterpretationResponse(
        intent="strategy_drafting",
        task_relation="new_task",
        user_goal_summary="User wants to test Apple after big drops.",
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing="What if I bought Apple after big drops?",
            strategy_type="indicator_threshold",
            strategy_thesis="Buy Apple after big drops.",
            asset_universe=["AAPL"],
        ),
        unsupported_constraints=[
            interpreter_module.LLMUnsupportedConstraint(
                category="unsupported_indicator_rule",
                raw_value="moving-average crossover",
                explanation=(
                    "Argus cannot execute that exact moving-average or "
                    "compound indicator logic yet."
                ),
                simplification_labels=["Compare NVDA with buy and hold"],
            )
        ],
    )

    result = interpreter._to_runtime_interpretation(
        response,
        request=InterpretationRequest(
            current_user_message="What if I bought Apple after big drops?",
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        ),
    )

    assert result.candidate_strategy_draft.strategy_type == "indicator_threshold"
    assert result.candidate_strategy_draft.cadence is None
    assert result.candidate_strategy_draft.capital_amount is None
    assert result.unsupported_constraints == []


def test_llm_interpreter_accepts_structured_date_ranges(monkeypatch) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    monkeypatch.setattr(
        interpreter_module,
        "resolve_asset",
        lambda symbol: ResolvedAssetStub(symbol.upper(), "crypto"),
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    response = LLMInterpretationResponse(
        intent="backtest_execution",
        task_relation="new_task",
        user_goal_summary="Buy and hold Bitcoin from last year to date.",
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing=(
                "let's try a basic buy and hold on BTC from jan first last year to date"
            ),
            strategy_type="buy_and_hold",
            strategy_thesis="Buy and hold Bitcoin from January 1 last year to date.",
            asset_universe=["BTC"],
            date_range={"start": "2025-01-01", "end": "today"},
        ),
    )

    result = interpreter._to_runtime_interpretation(
        response,
        request=InterpretationRequest(
            current_user_message=(
                "let's try a basic buy and hold on BTC from jan first last year to date"
            ),
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        ),
    )

    strategy = result.candidate_strategy_draft
    assert strategy.date_range == {"start": "2025-01-01", "end": "today"}
    assert resolve_date_range(strategy.date_range, today=date(2026, 5, 3)).payload == {
        "start": "2025-01-01",
        "end": "2026-05-03",
    }


def test_llm_interpreter_keeps_relative_date_contract_when_model_invents_dates(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    monkeypatch.setattr(
        interpreter_module,
        "resolve_asset",
        lambda symbol: ResolvedAssetStub(symbol.upper(), "equity"),
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    response = LLMInterpretationResponse(
        intent="backtest_execution",
        task_relation="new_task",
        user_goal_summary="Backtest TSLA with RSI thresholds over the last 5 years.",
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing=(
                "test tsla rsi below 20 and sell above 60 over the last 5 years"
            ),
            strategy_type="indicator_threshold",
            strategy_thesis="Test TSLA with RSI thresholds.",
            asset_universe=["TSLA"],
            indicator="rsi",
            entry_threshold=20,
            exit_threshold=60,
            date_range={"start": "2019-07-29", "end": "2024-07-29"},
            date_range_intent=LLMDateRangeIntent(
                kind="rolling_window",
                count=5,
                unit="year",
                anchor="today",
                evidence="last 5 years",
            ),
        ),
    )

    result = interpreter._to_runtime_interpretation(
        response,
        request=InterpretationRequest(
            current_user_message=(
                "test tsla rsi below 20 and sell above 60 over the last 5 years"
            ),
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        ),
    )

    strategy = result.candidate_strategy_draft
    expected_range = interpreter_module.resolve_date_range_intent(
        LLMDateRangeIntent(
            kind="rolling_window",
            count=5,
            unit="year",
            anchor="today",
        )
    )
    assert expected_range is not None
    assert strategy.date_range == expected_range.payload


def test_llm_interpreter_preserves_user_since_year_when_model_defaults_period(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    monkeypatch.setattr(
        interpreter_module,
        "resolve_asset",
        lambda symbol: ResolvedAssetStub(symbol.upper(), "crypto"),
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    response = LLMInterpretationResponse(
        intent="backtest_execution",
        task_relation="new_task",
        user_goal_summary="Invest $500 in Bitcoin every month since 2021.",
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing="Invest $500 in Bitcoin every month since 2021.",
            strategy_type="dca_accumulation",
            strategy_thesis="Invest $500 in Bitcoin every month since 2021.",
            asset_universe=["BTC"],
            asset_class="crypto",
            date_range="since 2021",
            date_range_intent=LLMDateRangeIntent(
                kind="since",
                year=2021,
                evidence="since 2021",
            ),
            cadence="monthly",
            capital_amount=500,
            evidence_spans={"cadence": "every month"},
            field_provenance={
                "capital_amount": "recurring_contribution",
                "cadence": "explicit_user",
            },
        ),
    )

    result = interpreter._to_runtime_interpretation(
        response,
        request=InterpretationRequest(
            current_user_message="Invest $500 in Bitcoin every month since 2021.",
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        ),
    )

    strategy = result.candidate_strategy_draft
    expected_range = interpreter_module.resolve_date_range_intent(
        LLMDateRangeIntent(kind="since", year=2021)
    )
    assert expected_range is not None
    assert strategy.date_range == expected_range.payload
    assert strategy.capital_amount == 500
    assert strategy.cadence == "monthly"


def test_llm_interpreter_rejects_invented_dca_cadence(monkeypatch) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    monkeypatch.setattr(
        interpreter_module,
        "resolve_asset",
        lambda symbol: ResolvedAssetStub(symbol.upper(), "equity"),
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    response = LLMInterpretationResponse(
        intent="backtest_execution",
        task_relation="continue",
        user_goal_summary="User supplied LYFT, dates, and total budget.",
        requires_clarification=True,
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing=(
                "I would like to invest in LYFT over 5 years feb 2020-feb 2025, "
                "$200,000 of capital"
            ),
            strategy_type="dca_accumulation",
            strategy_thesis="DCA into LYFT.",
            asset_universe=["LYFT"],
            asset_class="equity",
            date_range={"start": "2020-02-01", "end": "2025-02-28"},
            cadence="monthly",
            assumptions=[
                "Invest equal dollar amounts at regular intervals (monthly) over the period."
            ],
        ),
    )

    result = interpreter._to_runtime_interpretation(
        response,
        request=InterpretationRequest(
            current_user_message=(
                "I would like to invest in LYFT over 5 years feb 2020-feb 2025, "
                "$200,000 of capital"
            ),
            recent_thread_history=[],
            latest_task_snapshot=TaskSnapshot(
                pending_strategy_summary=StrategySummary(
                    strategy_type="dca_accumulation",
                    strategy_thesis="DCA setup.",
                )
            ),
            user=UserState(user_id="u1"),
        ),
    )

    strategy = result.candidate_strategy_draft
    assert strategy.cadence is None
    assert strategy.assumptions == []
    assert result.missing_required_fields == ["capital_amount", "cadence"]


def test_llm_interpreter_rejects_invented_dca_contribution_amount(monkeypatch) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    monkeypatch.setattr(
        interpreter_module,
        "resolve_asset",
        lambda symbol: ResolvedAssetStub(symbol.upper(), "equity"),
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    response = LLMInterpretationResponse(
        intent="backtest_execution",
        task_relation="new_task",
        user_goal_summary="Buy Tesla every month.",
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing="What if I bought Tesla every month?",
            strategy_type="dca_accumulation",
            strategy_thesis="Buy Tesla every month.",
            asset_universe=["TSLA"],
            asset_class="equity",
            cadence="monthly",
            capital_amount=10000,
        ),
    )

    result = interpreter._to_runtime_interpretation(
        response,
        request=InterpretationRequest(
            current_user_message="What if I bought Tesla every month?",
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        ),
    )

    strategy = result.candidate_strategy_draft
    assert strategy.strategy_type == "dca_accumulation"
    assert strategy.capital_amount is None


@pytest.mark.asyncio
async def test_dca_contribution_role_audit_demotes_total_budget(monkeypatch) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    async def fake_json_schema(
        *, task, messages, schema_model, schema_name, model_name=None
    ):
        del task, messages, schema_model, model_name
        assert schema_name == "DcaContributionRoleAudit"
        return interpreter_module.DcaContributionRoleAudit(
            recurring_contribution_explicit=False,
            total_budget_not_recurring=True,
            confidence=0.9,
        )

    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        fake_json_schema,
    )
    response = LLMInterpretationResponse(
        intent="backtest_execution",
        task_relation="continue",
        user_goal_summary="User supplied total capital for a DCA setup.",
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing=(
                "I would like to invest in LYFT over 5 years feb 2020-feb 2025, "
                "$200,000 of capital"
            ),
            strategy_type="dca_accumulation",
            strategy_thesis="Recurring buys for LYFT.",
            asset_universe=["LYFT"],
            asset_class="equity",
            date_range={"start": "2020-02-01", "end": "2025-02-28"},
            capital_amount=200000,
            field_provenance={"capital_amount": "recurring_contribution"},
        ),
        semantic_turn_act="answer_pending_need",
    )

    audited = await interpreter_module._dca_contribution_role_audited_response(
        response=response,
        preferred_model="test-model",
        request=InterpretationRequest(
            current_user_message=(
                "I would like to invest in LYFT over 5 years feb 2020-feb 2025, "
                "$200,000 of capital"
            ),
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        ),
    )

    draft = audited.candidate_strategy_draft
    assert audited.requires_clarification is True
    assert draft.capital_amount is None
    assert draft.total_capital == 200000
    assert "capital_amount" in audited.missing_required_fields
    assert "dca_total_budget_role_audited" in audited.reason_codes


@pytest.mark.asyncio
async def test_dca_contribution_role_audit_preserves_recurring_amount_with_cap(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    async def fake_json_schema(
        *, task, messages, schema_model, schema_name, model_name=None
    ):
        del task, messages, schema_model, model_name
        assert schema_name == "DcaContributionRoleAudit"
        return interpreter_module.DcaContributionRoleAudit(
            recurring_contribution_explicit=True,
            total_budget_not_recurring=True,
            confidence=0.9,
        )

    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        fake_json_schema,
    )
    response = LLMInterpretationResponse(
        intent="backtest_execution",
        task_relation="new_task",
        user_goal_summary="User supplied recurring buys with a contribution cap.",
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing=(
                "what if I bought $125 of BTC every two weeks from 2022 "
                "through 2023 with a $3000 cap?"
            ),
            strategy_type="dca_accumulation",
            strategy_thesis="Recurring buys for BTC.",
            asset_universe=["BTC"],
            asset_class="crypto",
            date_range={"start": "2022-01-01", "end": "2023-12-31"},
            capital_amount=125,
            recurring_contribution=125,
            cadence="biweekly",
            total_capital=3000,
            sizing_mode="capital_amount",
            field_provenance={
                "capital_amount": "recurring_contribution",
                "recurring_contribution": "recurring_contribution",
                "total_capital": "cap",
                "cadence": "explicit_user",
            },
            extra_parameters={
                "recurring_contribution": 125,
                "recurring_cadence": "biweekly",
                "total_budget": 3000,
            },
        ),
        semantic_turn_act="new_idea",
    )

    audited = await interpreter_module._dca_contribution_role_audited_response(
        response=response,
        preferred_model="test-model",
        request=InterpretationRequest(
            current_user_message=(
                "what if I bought $125 of BTC every two weeks from 2022 "
                "through 2023 with a $3000 cap?"
            ),
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        ),
    )

    draft = audited.candidate_strategy_draft
    assert audited.requires_clarification is False
    assert audited.intent == "backtest_execution"
    assert draft.capital_amount == 125
    assert draft.recurring_contribution == 125
    assert draft.cadence == "biweekly"
    assert draft.total_capital == 3000
    assert draft.sizing_mode == "capital_amount"
    assert draft.field_provenance["capital_amount"] == "recurring_contribution"
    assert draft.field_provenance["total_capital"] == "cap"
    assert "capital_amount" not in audited.missing_required_fields
    assert "dca_recurring_contribution_grounded_in_current_message" in (
        audited.reason_codes
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "symbol", "amount", "cadence", "budget"),
    [
        (
            "run the recurring buys only",
            "MSFT",
            750,
            "quarterly",
            9000,
        ),
        (
            "just use the scheduled deposits without that budget ceiling",
            "BTC",
            125,
            "biweekly",
            3000,
        ),
    ],
)
async def test_pending_response_option_selection_applies_structured_payload(
    monkeypatch,
    message: str,
    symbol: str,
    amount: float,
    cadence: str,
    budget: float,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    async def fake_json_schema(
        *, task, messages, schema_model, schema_name, model_name=None
    ):
        del task, messages, schema_model, model_name
        assert schema_name == "PendingResponseOptionSelectionAudit"
        return interpreter_module.PendingResponseOptionSelectionAudit(
            is_selection=True,
            selected_option_index=0,
            confidence=0.91,
        )

    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        fake_json_schema,
    )
    response = LLMInterpretationResponse(
        intent="unsupported_or_out_of_scope",
        task_relation="continue",
        requires_clarification=True,
        user_goal_summary="User selected a supported simplification.",
        assistant_response="Which simplification would you like to use?",
        candidate_strategy_draft=LLMStrategyDraft(
            strategy_type="dca_accumulation",
            strategy_thesis=f"Recurring buys for {symbol}.",
            asset_universe=[symbol],
            asset_class="crypto" if symbol == "BTC" else "equity",
            date_range={"start": "2021-01-01", "end": "2023-12-31"},
            capital_amount=amount,
            recurring_contribution=amount,
            cadence=cadence,
            total_capital=budget,
            field_provenance={
                "capital_amount": "recurring_contribution",
                "recurring_contribution": "recurring_contribution",
                "total_capital": "cap",
                "cadence": "explicit_user",
            },
            extra_parameters={"total_budget": budget},
        ),
        semantic_turn_act="unsupported_request",
    )

    audited = await interpreter_module._pending_response_option_selected_response(
        response=response,
        preferred_model="test-model",
        request=InterpretationRequest(
            current_user_message=message,
            recent_thread_history=[],
            latest_task_snapshot=TaskSnapshot(
                pending_strategy_summary=StrategySummary(
                    strategy_type="dca_accumulation",
                    strategy_thesis=f"Recurring buys for {symbol}.",
                    asset_universe=[symbol],
                    asset_class="crypto" if symbol == "BTC" else "equity",
                    date_range={"start": "2021-01-01", "end": "2023-12-31"},
                    capital_amount=amount,
                    cadence=cadence,
                    extra_parameters={
                        "recurring_contribution": amount,
                        "total_budget": budget,
                        "field_provenance": {
                            "capital_amount": "recurring_contribution",
                            "total_capital": "cap",
                            "cadence": "explicit_user",
                        },
                    },
                )
            ),
            selected_thread_metadata={
                "last_stage_outcome": "await_user_reply",
                "response_intent": {
                    "kind": "unsupported_recovery",
                    "semantic_needs": ["simplification_choice"],
                    "options": [
                        {
                            "label": "Run recurring buys only",
                            "replacement_values": {"ignore_initial_capital": True},
                        }
                    ],
                },
            },
            user=UserState(user_id="u1"),
        ),
    )

    draft = audited.candidate_strategy_draft
    assert audited.intent == "backtest_execution"
    assert audited.requires_clarification is False
    assert audited.assistant_response is None
    assert audited.unsupported_constraints == []
    assert draft.strategy_type == "dca_accumulation"
    assert draft.asset_universe == [symbol]
    assert draft.capital_amount == amount
    assert draft.recurring_contribution == amount
    assert draft.cadence == cadence
    assert draft.total_capital is None
    assert draft.initial_capital is None
    assert "total_budget" not in draft.extra_parameters
    assert draft.field_provenance.get("capital_amount") == "recurring_contribution"
    assert "total_capital" not in draft.field_provenance
    assert "pending_response_option_selected" in audited.reason_codes


@pytest.mark.asyncio
async def test_pending_response_option_selection_wins_over_generic_asset_parse(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    async def fake_json_schema(
        *, task, messages, schema_model, schema_name, model_name=None
    ):
        del task, messages, schema_model, model_name
        if schema_name == "LLMInterpretationResponse":
            return LLMInterpretationResponse(
                intent="strategy_drafting",
                task_relation="continue",
                requires_clarification=True,
                user_goal_summary="User answered a pending recovery choice.",
                assistant_response="Ready to go?",
                candidate_strategy_draft=LLMStrategyDraft(
                    strategy_type="dca_accumulation",
                    strategy_thesis="Recurring buys.",
                    asset_universe=["JUST"],
                    asset_class="equity",
                    date_range={"start": "2021-01-01", "end": "2023-12-31"},
                ),
                semantic_turn_act="answer_pending_need",
            )
        assert schema_name == "PendingResponseOptionSelectionAudit"
        return interpreter_module.PendingResponseOptionSelectionAudit(
            is_selection=True,
            selected_option_index=0,
            confidence=0.92,
        )

    monkeypatch.setattr(
        interpreter_module,
        "openrouter_structured_model_candidates",
        lambda **_: ["test-model"],
    )
    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        fake_json_schema,
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )

    result = await interpreter.ainvoke(
        InterpretationRequest(
            current_user_message="just run the scheduled deposits without the budget ceiling",
            recent_thread_history=[],
            latest_task_snapshot=TaskSnapshot(
                pending_strategy_summary=StrategySummary(
                    strategy_type="dca_accumulation",
                    strategy_thesis="Recurring buys for MSFT.",
                    asset_universe=["MSFT"],
                    asset_class="equity",
                    date_range={"start": "2021-01-01", "end": "2023-12-31"},
                    capital_amount=750,
                    cadence="quarterly",
                    extra_parameters={
                        "recurring_contribution": 750,
                        "total_budget": 9000,
                        "field_provenance": {
                            "capital_amount": "recurring_contribution",
                            "total_capital": "cap",
                            "cadence": "explicit_user",
                        },
                    },
                )
            ),
            selected_thread_metadata={
                "last_stage_outcome": "await_user_reply",
                "response_intent": {
                    "kind": "unsupported_recovery",
                    "semantic_needs": ["simplification_choice"],
                    "options": [
                        {
                            "label": "Run recurring buys only",
                            "replacement_values": {"ignore_initial_capital": True},
                        }
                    ],
                },
            },
            user=UserState(user_id="u1"),
        )
    )

    assert result is not None
    assert result.intent == "backtest_execution"
    assert result.requires_clarification is False
    assert result.assistant_response is None
    assert result.candidate_strategy_draft.asset_universe == ["MSFT"]
    assert result.candidate_strategy_draft.capital_amount == 750
    assert result.candidate_strategy_draft.cadence == "quarterly"
    assert (
        result.candidate_strategy_draft.extra_parameters.get("recurring_contribution")
        == 750
    )
    assert "total_budget" not in result.candidate_strategy_draft.extra_parameters
    assert "pending_response_option_selected" in result.reason_codes


@pytest.mark.asyncio
async def test_pending_response_option_selection_handles_approval_like_answer(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    async def fake_json_schema(
        *, task, messages, schema_model, schema_name, model_name=None
    ):
        del task, messages, schema_model, model_name
        if schema_name == "LLMInterpretationResponse":
            return LLMInterpretationResponse(
                intent="backtest_execution",
                task_relation="continue",
                requires_clarification=False,
                user_goal_summary="User approved the pending choice.",
                assistant_response=None,
                candidate_strategy_draft=LLMStrategyDraft(),
                semantic_turn_act="approval",
            )
        assert schema_name == "PendingResponseOptionSelectionAudit"
        return interpreter_module.PendingResponseOptionSelectionAudit(
            is_selection=True,
            selected_option_index=0,
            confidence=0.9,
        )

    monkeypatch.setattr(
        interpreter_module,
        "openrouter_structured_model_candidates",
        lambda **_: ["test-model"],
    )
    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        fake_json_schema,
    )

    result = await OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    ).ainvoke(
        InterpretationRequest(
            current_user_message="yes, run the recurring buys",
            recent_thread_history=[],
            latest_task_snapshot=TaskSnapshot(
                pending_strategy_summary=StrategySummary(
                    strategy_type="dca_accumulation",
                    strategy_thesis="Recurring buys for MSFT.",
                    asset_universe=["MSFT"],
                    asset_class="equity",
                    date_range={"start": "2021-01-01", "end": "2023-12-31"},
                    capital_amount=750,
                    cadence="quarterly",
                    extra_parameters={
                        "recurring_contribution": 750,
                        "total_budget": 9000,
                        "field_provenance": {
                            "capital_amount": "recurring_contribution",
                            "total_capital": "cap",
                            "cadence": "explicit_user",
                        },
                    },
                )
            ),
            selected_thread_metadata={
                "last_stage_outcome": "await_user_reply",
                "response_intent": {
                    "kind": "unsupported_recovery",
                    "semantic_needs": ["simplification_choice"],
                    "options": [
                        {
                            "label": "Run recurring buys only",
                            "replacement_values": {"ignore_initial_capital": True},
                        }
                    ],
                },
            },
            user=UserState(user_id="u1"),
        )
    )

    assert result is not None
    assert result.intent == "backtest_execution"
    assert result.requires_clarification is False
    assert result.candidate_strategy_draft.asset_universe == ["MSFT"]
    assert "total_budget" not in result.candidate_strategy_draft.extra_parameters
    assert "pending_response_option_selected" in result.reason_codes


@pytest.mark.asyncio
async def test_dca_contribution_role_audit_preserves_current_recurring_amount(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    calls: list[str] = []

    async def fake_json_schema(
        *, task, messages, schema_model, schema_name, model_name=None
    ):
        del task, messages, schema_model, model_name
        assert schema_name == "DcaContributionRoleAudit"
        calls.append(schema_name)
        return interpreter_module.DcaContributionRoleAudit(
            recurring_contribution_explicit=True,
            total_budget_not_recurring=False,
            confidence=0.9,
        )

    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        fake_json_schema,
    )
    response = LLMInterpretationResponse(
        intent="backtest_execution",
        task_relation="new_task",
        user_goal_summary="Buy NVDA every week in 2024.",
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing="What if I bought $250 of NVDA every week in 2024?",
            strategy_type="dca_accumulation",
            strategy_thesis="Buy NVDA weekly.",
            asset_universe=["NVDA"],
            asset_class="equity",
            date_range={"end": "2024-12-31"},
            capital_amount=250,
            cadence="weekly",
            field_provenance={"capital_amount": "starting_capital"},
        ),
        requires_clarification=True,
        missing_required_fields=["capital_amount", "cadence", "date_range"],
        semantic_turn_act="new_idea",
    )

    audited = await interpreter_module._dca_contribution_role_audited_response(
        response=response,
        preferred_model="test-model",
        request=InterpretationRequest(
            current_user_message="What if I bought $250 of NVDA every week in 2024?",
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        ),
    )

    draft = audited.candidate_strategy_draft
    assert draft.capital_amount == 250
    assert draft.recurring_contribution == 250
    assert draft.cadence == "weekly"
    assert draft.field_provenance["capital_amount"] == "recurring_contribution"
    assert draft.field_provenance["cadence"] == "explicit_user"
    assert "capital_amount" not in audited.missing_required_fields
    assert "cadence" not in audited.missing_required_fields
    assert "date_range" in audited.missing_required_fields
    assert "dca_recurring_contribution_grounded_in_current_message" in (
        audited.reason_codes
    )
    assert calls == ["DcaContributionRoleAudit"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "message",
        "draft_symbol",
        "draft_date_range",
        "draft_capital_amount",
        "recurring_amount",
        "cadence",
        "total_budget",
        "budget_source",
    ),
    [
        (
            "try buying $750 of MSFT quarterly from 2021 through 2023 with a $9,000 cap",
            "MSFT",
            {"start": "2021-01-01", "end": "2023-12-31"},
            9000,
            750,
            "quarterly",
            9000,
            "cap",
        ),
        (
            "what if I bought $125 of BTC every two weeks from 2022 through 2023 with a $3,000 budget cap",
            "BTC",
            {"start": "2022-01-01", "end": "2023-12-31"},
            3000,
            125,
            "biweekly",
            3000,
            "max_budget",
        ),
    ],
)
async def test_dca_contract_audit_recovers_recurring_buy_shape_before_capability_fallback(
    monkeypatch,
    message,
    draft_symbol,
    draft_date_range,
    draft_capital_amount,
    recurring_amount,
    cadence,
    total_budget,
    budget_source,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    calls: list[str] = []

    async def fake_json_schema(
        *, task, messages, schema_model, schema_name, model_name=None
    ):
        del task, messages, model_name
        calls.append(schema_name)
        if schema_name == "DcaContractAudit":
            return schema_model(
                is_recurring_buy_request=True,
                recurring_contribution_amount=recurring_amount,
                cadence=cadence,
                total_budget_amount=total_budget,
                total_budget_source=budget_source,
                confidence=0.92,
            )
        raise AssertionError(f"unexpected schema: {schema_name}")

    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        fake_json_schema,
    )
    response = LLMInterpretationResponse(
        intent="unsupported_or_out_of_scope",
        task_relation="new_task",
        requires_clarification=False,
        user_goal_summary="User wants recurring buys with a contribution cap.",
        assistant_response=(
            "Recurring buys are not available yet. Try buy and hold instead."
        ),
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing=message,
            strategy_type=None,
            strategy_thesis=message,
            asset_universe=[draft_symbol],
            date_range=draft_date_range,
            capital_amount=draft_capital_amount,
            field_provenance={"capital_amount": budget_source},
        ),
        missing_required_fields=["entry_logic", "exit_logic"],
        semantic_turn_act="unsupported_request",
        capability_question_focus="supported_strategies",
        artifact_target="none",
        reason_codes=["capability_side_question_audit"],
    )
    request = InterpretationRequest(
        current_user_message=message,
        recent_thread_history=[],
        latest_task_snapshot=None,
        user=UserState(user_id="u1"),
    )

    repaired = await interpreter_module._response_ready_for_runtime(
        response=response,
        preferred_model="test-model",
        request=request,
    )

    draft = repaired.candidate_strategy_draft
    assert "DcaContractAudit" in calls
    assert repaired.intent == "backtest_execution"
    assert repaired.semantic_turn_act == "new_idea"
    assert repaired.capability_question_focus is None
    assert repaired.assistant_response is None
    assert draft.strategy_type == "dca_accumulation"
    assert draft.capital_amount == recurring_amount
    assert draft.cadence == cadence
    assert draft.total_capital == total_budget
    assert draft.field_provenance["capital_amount"] == "recurring_contribution"
    assert draft.field_provenance["total_capital"] == budget_source
    assert "capital_amount" not in repaired.missing_required_fields
    assert "cadence" not in repaired.missing_required_fields
    assert "dca_contract_audit" in repaired.reason_codes


@pytest.mark.asyncio
async def test_dca_contract_audit_preserves_optional_cap_on_ready_dca_shape(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    calls: list[str] = []

    async def fake_json_schema(
        *, task, messages, schema_model, schema_name, model_name=None
    ):
        del task, messages, model_name
        calls.append(schema_name)
        if schema_name == "DcaContractAudit":
            return schema_model(
                is_recurring_buy_request=True,
                recurring_contribution_amount=125,
                cadence="biweekly",
                total_budget_amount=3000,
                total_budget_source="cap",
                confidence=0.92,
            )
        if schema_name == "DcaContributionRoleAudit":
            return interpreter_module.DcaContributionRoleAudit(
                recurring_contribution_explicit=True,
                total_budget_not_recurring=True,
                confidence=0.9,
            )
        raise AssertionError(f"unexpected schema: {schema_name}")

    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        fake_json_schema,
    )
    response = LLMInterpretationResponse(
        intent="backtest_execution",
        task_relation="new_task",
        requires_clarification=False,
        user_goal_summary="User wants recurring buys with a contribution cap.",
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing=(
                "what if I bought $125 of BTC every two weeks from 2022 "
                "through 2023 with a $3000 cap?"
            ),
            strategy_type="dca_accumulation",
            strategy_thesis="Recurring buys for BTC.",
            asset_universe=["BTC"],
            asset_class="crypto",
            date_range={"start": "2022-01-01", "end": "2023-12-31"},
            capital_amount=125,
            cadence="biweekly",
            field_provenance={
                "capital_amount": "recurring_contribution",
                "cadence": "explicit_user",
            },
        ),
        semantic_turn_act="new_idea",
        artifact_target="none",
    )
    request = InterpretationRequest(
        current_user_message=(
            "what if I bought $125 of BTC every two weeks from 2022 "
            "through 2023 with a $3000 cap?"
        ),
        recent_thread_history=[],
        latest_task_snapshot=None,
        user=UserState(user_id="u1"),
    )

    repaired = await interpreter_module._response_ready_for_runtime(
        response=response,
        preferred_model="test-model",
        request=request,
    )

    draft = repaired.candidate_strategy_draft
    assert "DcaContractAudit" in calls
    assert repaired.requires_clarification is False
    assert draft.strategy_type == "dca_accumulation"
    assert draft.capital_amount == 125
    assert draft.recurring_contribution == 125
    assert draft.cadence == "biweekly"
    assert draft.total_capital == 3000
    assert draft.field_provenance["capital_amount"] == "recurring_contribution"
    assert draft.field_provenance["total_capital"] == "cap"
    assert draft.extra_parameters["total_budget"] == 3000
    assert "dca_contract_audit" in repaired.reason_codes


def test_llm_interpreter_rejects_invented_initial_capital(monkeypatch) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    monkeypatch.setattr(
        interpreter_module,
        "resolve_asset",
        lambda symbol: ResolvedAssetStub(symbol.upper(), "equity"),
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    response = LLMInterpretationResponse(
        intent="backtest_execution",
        task_relation="new_task",
        user_goal_summary="Test Apple with RSI.",
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing="Simplify it to RSI.",
            strategy_type="indicator_threshold",
            strategy_thesis="Test Apple with RSI.",
            asset_universe=["AAPL"],
            asset_class="equity",
            date_range="last year",
            indicator="rsi",
            initial_capital=100000,
        ),
    )

    result = interpreter._to_runtime_interpretation(
        response,
        request=InterpretationRequest(
            current_user_message="Simplify it to RSI.",
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        ),
    )

    assert "initial_capital" not in result.candidate_strategy_draft.extra_parameters


def test_llm_interpreter_drops_unstated_buy_hold_execution_defaults(monkeypatch) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    monkeypatch.setattr(
        interpreter_module,
        "resolve_asset",
        lambda symbol: ResolvedAssetStub(symbol.upper(), "equity"),
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    response = LLMInterpretationResponse(
        intent="backtest_execution",
        task_relation="continue",
        user_goal_summary="Test TSLA over the past year.",
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing="test the past year",
            strategy_type="buy_and_hold",
            strategy_thesis="Buy and hold Tesla.",
            asset_universe=["TSLA"],
            date_range="past 1 year",
            sizing_mode="fixed",
            capital_amount=10000,
            position_size=1.0,
            risk_rules=[LLMRiskRule(type="max_position_size", value_pct=100.0)],
            field_provenance={"capital_amount": "default_assumption"},
        ),
        semantic_turn_act="answer_pending_need",
    )

    result = interpreter._to_runtime_interpretation(
        response,
        request=InterpretationRequest(
            current_user_message="test the past year",
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        ),
    )

    strategy = result.candidate_strategy_draft
    assert strategy.capital_amount is None
    assert strategy.position_size is None
    assert strategy.sizing_mode is None
    assert strategy.risk_rules == []
    assert "field_provenance" not in strategy.extra_parameters


def test_llm_interpreter_preserves_grounded_initial_capital(monkeypatch) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    monkeypatch.setattr(
        interpreter_module,
        "resolve_asset",
        lambda symbol: ResolvedAssetStub(symbol.upper(), "equity"),
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    response = LLMInterpretationResponse(
        intent="backtest_execution",
        task_relation="new_task",
        user_goal_summary="Test Apple with RSI using $10,000.",
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing="Test Apple with RSI using $10,000.",
            strategy_type="indicator_threshold",
            strategy_thesis="Test Apple with RSI.",
            asset_universe=["AAPL"],
            asset_class="equity",
            date_range="last year",
            indicator="rsi",
            initial_capital=10000,
            field_provenance={"initial_capital": "explicit_user"},
        ),
    )

    result = interpreter._to_runtime_interpretation(
        response,
        request=InterpretationRequest(
            current_user_message="Test Apple with RSI using $10,000.",
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        ),
    )

    assert result.candidate_strategy_draft.extra_parameters["initial_capital"] == 10000
    assert result.candidate_strategy_draft.capital_amount == 10000


def test_llm_interpreter_maps_grounded_total_capital_to_non_dca_starting_capital(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    monkeypatch.setattr(
        interpreter_module,
        "resolve_asset",
        lambda symbol: ResolvedAssetStub(symbol.upper(), "equity"),
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    response = LLMInterpretationResponse(
        intent="backtest_execution",
        task_relation="new_task",
        user_goal_summary="Test Tesla with a 50/200 crossover using $10,000.",
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing=(
                "buy when the 50 crosses the 200 for Tesla from January 2022 "
                "to today with 10k"
            ),
            strategy_type="signal_strategy",
            strategy_thesis="Test Tesla with a 50/200 moving-average crossover.",
            asset_universe=["TSLA"],
            asset_class="equity",
            date_range={"start": "2022-01-01", "end": "today"},
            total_capital=10000,
            field_provenance={"total_capital": "total_capital"},
            entry_rule={
                "type": "moving_average_crossover",
                "fast_indicator": "sma",
                "fast_period": 50,
                "slow_indicator": "sma",
                "slow_period": 200,
                "direction": "bullish",
            },
        ),
    )

    result = interpreter._to_runtime_interpretation(
        response,
        request=InterpretationRequest(
            current_user_message=(
                "buy when the 50 crosses the 200 for Tesla from January 2022 "
                "to today with 10k"
            ),
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        ),
    )

    strategy = result.candidate_strategy_draft
    assert strategy.capital_amount == 10000
    assert strategy.extra_parameters["total_capital"] == 10000
    assert strategy.extra_parameters["field_provenance"]["capital_amount"] == (
        "starting_capital"
    )


def test_pending_signal_parameter_answer_preserves_prior_asset_when_verb_is_ticker(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    monkeypatch.setattr(
        interpreter_module,
        "resolve_asset",
        lambda symbol: ResolvedAssetStub(symbol.upper(), "equity"),
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    response = LLMInterpretationResponse(
        intent="backtest_execution",
        task_relation="continue",
        user_goal_summary="User supplied the moving-average periods.",
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing="usa 50 y 200 dias",
            language="es-419",
            strategy_type="signal_strategy",
            strategy_thesis="Use a 50/200 moving-average crossover.",
            asset_universe=["USA"],
            asset_class="equity",
            date_range={"start": "2024-01-01", "end": "2024-12-31"},
            entry_rule={
                "type": "moving_average_crossover",
                "fast_indicator": "sma",
                "fast_period": 50,
                "slow_indicator": "sma",
                "slow_period": 200,
                "direction": "bullish",
            },
            exit_rule={
                "type": "moving_average_crossover",
                "fast_indicator": "sma",
                "fast_period": 50,
                "slow_indicator": "sma",
                "slow_period": 200,
                "direction": "bearish",
            },
        ),
        semantic_turn_act="answer_pending_need",
    )

    result = interpreter._to_runtime_interpretation(
        response,
        request=InterpretationRequest(
            current_user_message="usa 50 y 200 dias",
            recent_thread_history=[],
            latest_task_snapshot=TaskSnapshot(
                pending_strategy_summary=StrategySummary(
                    strategy_type="signal_strategy",
                    strategy_thesis="Test TSLA with a moving-average crossover.",
                    asset_universe=["TSLA"],
                    asset_class="equity",
                    date_range={"start": "2024-01-01", "end": "2024-12-31"},
                )
            ),
            selected_thread_metadata={
                "last_stage_outcome": "await_user_reply",
                "requested_field": "entry_logic",
            },
            user=UserState(user_id="u1", language_preference="es-419"),
        ),
    )

    strategy = result.candidate_strategy_draft
    assert strategy.asset_universe == ["TSLA"]
    assert strategy.asset_class == "equity"
    assert strategy.entry_rule["fast_period"] == 50
    assert strategy.exit_rule["slow_period"] == 200


def test_pending_signal_parameter_answer_honors_typed_asset_override(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    monkeypatch.setattr(
        interpreter_module,
        "resolve_asset",
        lambda symbol: ResolvedAssetStub(symbol.upper(), "equity"),
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    response = LLMInterpretationResponse(
        intent="backtest_execution",
        task_relation="continue",
        user_goal_summary="User supplied a different asset and the moving-average periods.",
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing="usa $GOOGL con 50 y 200 dias",
            language="es-419",
            strategy_type="signal_strategy",
            strategy_thesis="Use Google with a 50/200 moving-average crossover.",
            asset_universe=["GOOGL"],
            asset_class="equity",
            date_range={"start": "2024-01-01", "end": "2024-12-31"},
            entry_rule={
                "type": "moving_average_crossover",
                "fast_indicator": "sma",
                "fast_period": 50,
                "slow_indicator": "sma",
                "slow_period": 200,
                "direction": "bullish",
            },
            exit_rule={
                "type": "moving_average_crossover",
                "fast_indicator": "sma",
                "fast_period": 50,
                "slow_indicator": "sma",
                "slow_period": 200,
                "direction": "bearish",
            },
            field_provenance={"asset_universe": "explicit_user"},
            evidence_spans={"asset_universe": "$GOOGL"},
        ),
        semantic_turn_act="answer_pending_need",
    )

    result = interpreter._to_runtime_interpretation(
        response,
        request=InterpretationRequest(
            current_user_message="usa $GOOGL con 50 y 200 dias",
            recent_thread_history=[],
            latest_task_snapshot=TaskSnapshot(
                pending_strategy_summary=StrategySummary(
                    strategy_type="signal_strategy",
                    strategy_thesis="Test TSLA with a moving-average crossover.",
                    asset_universe=["TSLA"],
                    asset_class="equity",
                    date_range={"start": "2024-01-01", "end": "2024-12-31"},
                )
            ),
            selected_thread_metadata={
                "last_stage_outcome": "await_user_reply",
                "requested_field": "entry_logic",
            },
            user=UserState(user_id="u1", language_preference="es-419"),
        ),
    )

    strategy = result.candidate_strategy_draft
    assert strategy.asset_universe == ["GOOGL"]
    assert strategy.asset_class == "equity"
    assert strategy.entry_rule["fast_period"] == 50
    assert "pending_non_asset_answer_preserved_prior_asset" not in result.reason_codes


def test_pending_signal_parameter_answer_ignores_lowercase_verb_asset_evidence(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    monkeypatch.setattr(
        interpreter_module,
        "resolve_asset",
        lambda symbol: ResolvedAssetStub(symbol.upper(), "equity"),
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    response = LLMInterpretationResponse(
        intent="backtest_execution",
        task_relation="continue",
        user_goal_summary="User supplied the moving-average periods.",
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing="usa 50 y 200 dias",
            language="es-419",
            strategy_type="signal_strategy",
            strategy_thesis="Use a 50/200 moving-average crossover.",
            asset_universe=["USA"],
            asset_class="equity",
            date_range={"start": "2024-01-01", "end": "2024-12-31"},
            entry_rule={
                "type": "moving_average_crossover",
                "fast_indicator": "sma",
                "fast_period": 50,
                "slow_indicator": "sma",
                "slow_period": 200,
                "direction": "bullish",
            },
            exit_rule={
                "type": "moving_average_crossover",
                "fast_indicator": "sma",
                "fast_period": 50,
                "slow_indicator": "sma",
                "slow_period": 200,
                "direction": "bearish",
            },
            field_provenance={"asset_universe": "explicit_user"},
            evidence_spans={"asset_universe": "usa"},
        ),
        semantic_turn_act="answer_pending_need",
    )

    result = interpreter._to_runtime_interpretation(
        response,
        request=InterpretationRequest(
            current_user_message="usa 50 y 200 dias",
            recent_thread_history=[],
            latest_task_snapshot=TaskSnapshot(
                pending_strategy_summary=StrategySummary(
                    strategy_type="signal_strategy",
                    strategy_thesis="Test TSLA with a moving-average crossover.",
                    asset_universe=["TSLA"],
                    asset_class="equity",
                    date_range={"start": "2024-01-01", "end": "2024-12-31"},
                )
            ),
            selected_thread_metadata={
                "last_stage_outcome": "await_user_reply",
                "requested_field": "entry_logic",
            },
            user=UserState(user_id="u1", language_preference="es-419"),
        ),
    )

    strategy = result.candidate_strategy_draft
    assert strategy.asset_universe == ["TSLA"]
    assert strategy.asset_class == "equity"
    assert strategy.entry_rule["fast_period"] == 50
    assert "pending_non_asset_answer_preserved_prior_asset" in result.reason_codes


def test_pending_signal_parameter_repair_preserves_prior_asset_without_field_metadata(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    monkeypatch.setattr(
        interpreter_module,
        "resolve_asset",
        lambda symbol: ResolvedAssetStub(symbol.upper(), "equity"),
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    response = LLMInterpretationResponse(
        intent="backtest_execution",
        task_relation="continue",
        user_goal_summary="User supplied the moving-average periods.",
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing="usa 50 y 200 dias",
            language="es-419",
            strategy_type="signal_strategy",
            strategy_thesis="Use a 50/200 moving-average crossover.",
            asset_universe=["USA"],
            asset_class="equity",
            date_range={"start": "2024-01-01", "end": "2024-12-31"},
            entry_rule={
                "type": "moving_average_crossover",
                "fast_indicator": "sma",
                "fast_period": 50,
                "slow_indicator": "sma",
                "slow_period": 200,
                "direction": "bullish",
            },
            exit_rule={
                "type": "moving_average_crossover",
                "fast_indicator": "sma",
                "fast_period": 50,
                "slow_indicator": "sma",
                "slow_period": 200,
                "direction": "bearish",
            },
        ),
        semantic_turn_act="new_idea",
    )

    result = interpreter._to_runtime_interpretation(
        response,
        request=InterpretationRequest(
            current_user_message="usa 50 y 200 dias",
            recent_thread_history=[],
            latest_task_snapshot=TaskSnapshot(
                pending_strategy_summary=StrategySummary(
                    strategy_type="signal_strategy",
                    strategy_thesis="Test TSLA with a moving-average crossover.",
                    asset_universe=["TSLA"],
                    asset_class="equity",
                    date_range={"start": "2024-01-01", "end": "2024-12-31"},
                )
            ),
            selected_thread_metadata={"last_stage_outcome": "await_user_reply"},
            user=UserState(user_id="u1", language_preference="es-419"),
        ),
    )

    strategy = result.candidate_strategy_draft
    assert strategy.asset_universe == ["TSLA"]
    assert strategy.asset_class == "equity"
    assert strategy.entry_rule["fast_period"] == 50
    assert "pending_non_asset_answer_preserved_prior_asset" in result.reason_codes


@pytest.mark.asyncio
async def test_latest_result_routing_audit_repairs_capability_misroute(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    calls: list[dict[str, object]] = []

    async def fake_json_schema(**kwargs):
        calls.append(kwargs)
        schema = kwargs["schema_model"]
        return schema(
            targets_latest_result=True,
            focus="next_experiment",
            confidence=0.92,
        )

    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        fake_json_schema,
    )
    snapshot = TaskSnapshot(
        latest_backtest_result_reference=ArtifactReference(
            artifact_kind="backtest_result",
            artifact_id="run-1",
            artifact_status="completed",
            metadata={
                "symbols": ["TSLA"],
                "benchmark_symbol": "SPY",
                "metrics": {
                    "aggregate": {
                        "performance": {
                            "total_return_pct": -32.6,
                            "benchmark_return_pct": 54.9,
                            "delta_vs_benchmark_pct": -87.5,
                        }
                    }
                },
                "config_snapshot": {"template": "signal_strategy"},
            },
        )
    )
    response = LLMInterpretationResponse(
        intent="conversation_followup",
        task_relation="continue",
        requires_clarification=False,
        user_goal_summary="User asks what to try next.",
        semantic_turn_act="educational_question",
        capability_question_focus="supported_strategies",
    )

    repaired = await interpreter_module._response_ready_for_runtime(
        response=response,
        preferred_model="structured/primary",
        request=InterpretationRequest(
            current_user_message="what should I try next?",
            recent_thread_history=[],
            latest_task_snapshot=snapshot,
            user=UserState(user_id="u1"),
        ),
    )

    assert calls
    assert calls[0]["schema_model"] is interpreter_module.LatestResultRoutingAudit
    assert repaired.semantic_turn_act == "result_followup"
    assert repaired.result_followup_focus == "next_experiment"
    assert repaired.capability_question_focus is None
    assert "latest_result_routing_audit" in repaired.reason_codes


@pytest.mark.asyncio
async def test_latest_result_routing_audit_refines_general_followup_focus(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    calls: list[dict[str, object]] = []

    async def fake_json_schema(**kwargs):
        calls.append(kwargs)
        schema = kwargs["schema_model"]
        return schema(
            targets_latest_result=True,
            focus="next_experiment",
            confidence=0.91,
        )

    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        fake_json_schema,
    )
    snapshot = TaskSnapshot(
        latest_backtest_result_reference=ArtifactReference(
            artifact_kind="backtest_result",
            artifact_id="run-1",
            artifact_status="completed",
            metadata={
                "symbols": ["TSLA"],
                "benchmark_symbol": "SPY",
                "metrics": {
                    "aggregate": {
                        "performance": {
                            "total_return_pct": -32.6,
                            "benchmark_return_pct": 54.9,
                            "delta_vs_benchmark_pct": -87.5,
                        }
                    }
                },
                "config_snapshot": {"template": "signal_strategy"},
            },
        )
    )
    response = LLMInterpretationResponse(
        intent="conversation_followup",
        task_relation="continue",
        requires_clarification=False,
        user_goal_summary="User asks what to try next.",
        assistant_response=("Try MACD or a Bollinger Band filter next."),
        semantic_turn_act="result_followup",
        result_followup_focus="general",
    )

    repaired = await interpreter_module._response_ready_for_runtime(
        response=response,
        preferred_model="structured/primary",
        request=InterpretationRequest(
            current_user_message="what should I try next?",
            recent_thread_history=[],
            latest_task_snapshot=snapshot,
            user=UserState(user_id="u1"),
        ),
    )

    assert calls
    assert calls[0]["schema_model"] is interpreter_module.LatestResultRoutingAudit
    assert repaired.semantic_turn_act == "result_followup"
    assert repaired.result_followup_focus == "next_experiment"
    assert repaired.assistant_response is None
    assert "latest_result_routing_audit" in repaired.reason_codes


@pytest.mark.asyncio
async def test_latest_result_routing_audit_marks_save_request(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    async def fake_json_schema(**kwargs):
        schema = kwargs["schema_model"]
        return schema(
            targets_latest_result=True,
            save_requested=True,
            focus="general",
            confidence=0.92,
        )

    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        fake_json_schema,
    )
    snapshot = TaskSnapshot(
        latest_backtest_result_reference=ArtifactReference(
            artifact_kind="backtest_result",
            artifact_id="run-1",
            artifact_status="completed",
            metadata={
                "symbols": ["AAPL"],
                "benchmark_symbol": "SPY",
                "metrics": {
                    "aggregate": {
                        "performance": {
                            "total_return_pct": 35.0,
                            "benchmark_return_pct": 24.0,
                            "delta_vs_benchmark_pct": 11.0,
                        }
                    }
                },
                "config_snapshot": {"template": "buy_and_hold"},
            },
        )
    )
    response = LLMInterpretationResponse(
        intent="results_explanation",
        task_relation="continue",
        requires_clarification=False,
        user_goal_summary="User asks to save the latest result.",
        assistant_response="I can explain the latest result.",
        semantic_turn_act="result_followup",
        result_followup_focus="general",
    )

    repaired = await interpreter_module._response_ready_for_runtime(
        response=response,
        preferred_model="structured/primary",
        request=InterpretationRequest(
            current_user_message="save this",
            recent_thread_history=[],
            latest_task_snapshot=snapshot,
            user=UserState(user_id="u1"),
        ),
    )

    assert repaired.artifact_target == "latest_result"
    assert repaired.assistant_response is None
    assert "latest_result_routing_audit" in repaired.reason_codes
    assert "latest_result_save_requested" in repaired.reason_codes


@pytest.mark.asyncio
async def test_latest_result_save_audit_can_mark_general_routing(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    calls: list[type] = []

    async def fake_json_schema(**kwargs):
        schema = kwargs["schema_model"]
        calls.append(schema)
        if schema is interpreter_module.LatestResultRoutingAudit:
            return schema(
                targets_latest_result=True,
                save_requested=False,
                focus="general",
                confidence=0.92,
            )
        return schema(save_requested=True, confidence=0.94)

    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        fake_json_schema,
    )
    snapshot = TaskSnapshot(
        latest_backtest_result_reference=ArtifactReference(
            artifact_kind="backtest_result",
            artifact_id="run-1",
            artifact_status="completed",
            metadata={
                "symbols": ["AAPL"],
                "benchmark_symbol": "SPY",
                "metrics": {
                    "aggregate": {
                        "performance": {
                            "total_return_pct": 35.0,
                            "benchmark_return_pct": 24.0,
                            "delta_vs_benchmark_pct": 11.0,
                        }
                    }
                },
                "config_snapshot": {"template": "buy_and_hold"},
            },
        )
    )
    response = LLMInterpretationResponse(
        intent="conversation_followup",
        task_relation="continue",
        requires_clarification=False,
        user_goal_summary="User asks to save the latest result.",
        assistant_response="I can explain the latest result.",
        semantic_turn_act="result_followup",
        result_followup_focus="general",
    )

    repaired = await interpreter_module._response_ready_for_runtime(
        response=response,
        preferred_model="structured/primary",
        request=InterpretationRequest(
            current_user_message="save this",
            recent_thread_history=[],
            latest_task_snapshot=snapshot,
            user=UserState(user_id="u1"),
        ),
    )

    assert calls == [
        interpreter_module.LatestResultRoutingAudit,
        interpreter_module.LatestResultSaveAudit,
    ]
    assert "latest_result_save_requested" in repaired.reason_codes


@pytest.mark.asyncio
async def test_latest_result_save_audit_runs_after_non_general_result_focus(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    calls: list[type] = []

    async def fake_json_schema(**kwargs):
        schema = kwargs["schema_model"]
        calls.append(schema)
        if schema is interpreter_module.LatestResultRoutingAudit:
            return schema(
                targets_latest_result=True,
                save_requested=False,
                focus="why_underperformed",
                confidence=0.9,
            )
        return schema(save_requested=True, confidence=0.94)

    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        fake_json_schema,
    )
    snapshot = TaskSnapshot(
        latest_backtest_result_reference=ArtifactReference(
            artifact_kind="backtest_result",
            artifact_id="run-save-focus",
            artifact_status="completed",
            metadata={
                "symbols": ["AAPL"],
                "benchmark_symbol": "SPY",
                "metrics": {
                    "aggregate": {
                        "performance": {
                            "total_return_pct": 103.0,
                            "benchmark_return_pct": 47.0,
                            "delta_vs_benchmark_pct": 56.0,
                        }
                    }
                },
                "config_snapshot": {"template": "buy_and_hold"},
            },
        )
    )
    response = LLMInterpretationResponse(
        intent="conversation_followup",
        task_relation="continue",
        requires_clarification=False,
        user_goal_summary="User asks to save the latest result.",
        assistant_response="I can explain what happened.",
        semantic_turn_act="result_followup",
        result_followup_focus="why_underperformed",
    )

    repaired = await interpreter_module._response_ready_for_runtime(
        response=response,
        preferred_model="structured/primary",
        request=InterpretationRequest(
            current_user_message="save this",
            recent_thread_history=[],
            latest_task_snapshot=snapshot,
            user=UserState(user_id="u1"),
        ),
    )

    assert calls == [
        interpreter_module.LatestResultRoutingAudit,
        interpreter_module.LatestResultSaveAudit,
    ]
    assert repaired.result_followup_focus == "why_underperformed"
    assert "latest_result_save_requested" in repaired.reason_codes


@pytest.mark.asyncio
async def test_latest_result_routing_audit_repairs_copied_underfilled_strategy(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    calls: list[dict[str, object]] = []

    async def fake_json_schema(**kwargs):
        calls.append(kwargs)
        schema = kwargs["schema_model"]
        return schema(
            targets_latest_result=True,
            focus="why_underperformed",
            confidence=0.9,
        )

    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        fake_json_schema,
    )
    snapshot = TaskSnapshot(
        latest_backtest_result_reference=ArtifactReference(
            artifact_kind="backtest_result",
            artifact_id="run-1",
            artifact_status="completed",
            metadata={
                "symbols": ["TSLA"],
                "benchmark_symbol": "SPY",
                "metrics": {
                    "aggregate": {
                        "performance": {
                            "total_return_pct": -32.6,
                            "benchmark_return_pct": 54.9,
                            "delta_vs_benchmark_pct": -87.5,
                        }
                    }
                },
                "config_snapshot": {"template": "signal_strategy"},
            },
        )
    )
    response = LLMInterpretationResponse(
        intent="strategy_drafting",
        task_relation="continue",
        requires_clarification=True,
        missing_required_fields=["entry_logic"],
        user_goal_summary="User asks why the latest result happened.",
        assistant_response=(
            "The strategy likely missed the rally because the signal lagged."
        ),
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing="why did that happen?",
            strategy_type="signal_strategy",
            strategy_thesis="why did that happen?",
            asset_universe=["TSLA"],
            date_range="2022-01-01 to 2026-05-20",
            timeframe="1D",
        ),
        semantic_turn_act="new_idea",
    )

    repaired = await interpreter_module._response_ready_for_runtime(
        response=response,
        preferred_model="structured/primary",
        request=InterpretationRequest(
            current_user_message="why did that happen?",
            recent_thread_history=[],
            latest_task_snapshot=snapshot,
            user=UserState(user_id="u1"),
        ),
    )

    assert calls
    assert calls[0]["schema_model"] is interpreter_module.LatestResultRoutingAudit
    assert repaired.semantic_turn_act == "result_followup"
    assert repaired.result_followup_focus == "why_underperformed"
    assert repaired.assistant_response is None
    assert repaired.missing_required_fields == []
    assert "latest_result_routing_audit" in repaired.reason_codes


@pytest.mark.asyncio
async def test_latest_result_routing_audit_refines_what_tested_when_user_asks_benchmark_why(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    calls: list[dict[str, object]] = []

    async def fake_json_schema(**kwargs):
        calls.append(kwargs)
        schema = kwargs["schema_model"]
        return schema(
            targets_latest_result=True,
            focus="why_underperformed",
            confidence=0.88,
        )

    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        fake_json_schema,
    )
    snapshot = TaskSnapshot(
        latest_backtest_result_reference=ArtifactReference(
            artifact_kind="backtest_result",
            artifact_id="run-1",
            artifact_status="completed",
            metadata={
                "symbols": ["BTC"],
                "benchmark_symbol": "BTC",
                "metrics": {
                    "aggregate": {
                        "performance": {
                            "total_return_pct": 75.5,
                            "benchmark_return_pct": 75.5,
                            "delta_vs_benchmark_pct": 0.0,
                        }
                    }
                },
                "config_snapshot": {"template": "buy_and_hold"},
            },
        )
    )
    response = LLMInterpretationResponse(
        intent="conversation_followup",
        task_relation="continue",
        requires_clarification=False,
        user_goal_summary="User asks why the result matched the benchmark.",
        assistant_response="I tested BTC buy and hold against BTC.",
        semantic_turn_act="result_followup",
        result_followup_focus="what_tested",
    )

    repaired = await interpreter_module._response_ready_for_runtime(
        response=response,
        preferred_model="structured/primary",
        request=InterpretationRequest(
            current_user_message="so why did it match BTC exactly?",
            recent_thread_history=[],
            latest_task_snapshot=snapshot,
            user=UserState(user_id="u1"),
        ),
    )

    assert calls
    assert repaired.semantic_turn_act == "result_followup"
    assert repaired.result_followup_focus == "why_underperformed"
    assert repaired.assistant_response is None
    assert "latest_result_routing_audit" in repaired.reason_codes


@pytest.mark.asyncio
async def test_latest_result_routing_audit_checks_copied_executable_result_shape(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    calls: list[dict[str, object]] = []

    async def fake_json_schema(**kwargs):
        calls.append(kwargs)
        schema = kwargs["schema_model"]
        return schema(
            targets_latest_result=True,
            focus="why_underperformed",
            confidence=0.9,
        )

    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        fake_json_schema,
    )
    snapshot = TaskSnapshot(
        latest_backtest_result_reference=ArtifactReference(
            artifact_kind="backtest_result",
            artifact_id="run-1",
            artifact_status="completed",
            metadata={
                "symbols": ["BTC"],
                "benchmark_symbol": "BTC",
                "metrics": {
                    "aggregate": {
                        "performance": {
                            "total_return_pct": 75.1,
                            "benchmark_return_pct": 75.1,
                            "delta_vs_benchmark_pct": 0.0,
                        }
                    }
                },
                "config_snapshot": {
                    "template": "buy_and_hold",
                    "resolved_strategy": {
                        "strategy_type": "buy_and_hold",
                        "asset_universe": ["BTC"],
                    },
                },
            },
        )
    )
    response = LLMInterpretationResponse(
        intent="backtest_execution",
        task_relation="continue",
        requires_clarification=False,
        user_goal_summary="User asks why the latest BTC run matched BTC.",
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing="why did it match BTC exactly?",
            strategy_type="buy_and_hold",
            strategy_thesis="Explain why the BTC run matched BTC.",
            asset_universe=["BTC"],
            asset_class="crypto",
            date_range={"start": "2024-01-01", "end": "2026-05-20"},
            timeframe="1D",
        ),
        semantic_turn_act="new_idea",
    )

    repaired = await interpreter_module._response_ready_for_runtime(
        response=response,
        preferred_model="structured/primary",
        request=InterpretationRequest(
            current_user_message="why did it match BTC exactly?",
            recent_thread_history=[],
            latest_task_snapshot=snapshot,
            user=UserState(user_id="u1"),
        ),
    )

    assert calls
    assert calls[0]["schema_model"] is interpreter_module.LatestResultRoutingAudit
    assert repaired.semantic_turn_act == "result_followup"
    assert repaired.result_followup_focus == "why_underperformed"
    assert repaired.assistant_response is None
    assert "latest_result_routing_audit" in repaired.reason_codes


@pytest.mark.asyncio
async def test_latest_result_routing_audit_checks_new_idea_peak_date_misroute(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    calls: list[dict[str, object]] = []

    async def fake_json_schema(**kwargs):
        calls.append(kwargs)
        schema = kwargs["schema_model"]
        return schema(
            targets_latest_result=True,
            focus="peak_date",
            fact_key="peak_date",
            confidence=0.91,
        )

    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        fake_json_schema,
    )
    snapshot = TaskSnapshot(
        latest_backtest_result_reference=ArtifactReference(
            artifact_kind="backtest_result",
            artifact_id="run-1",
            artifact_status="completed",
            metadata={
                "symbols": ["AAPL"],
                "benchmark_symbol": "SPY",
                "metrics": {
                    "aggregate": {
                        "performance": {
                            "total_return_pct": 22.1,
                            "benchmark_return_pct": 18.2,
                            "delta_vs_benchmark_pct": 3.9,
                        }
                    }
                },
                "config_snapshot": {
                    "template": "buy_and_hold",
                    "date_range": {"start": "2024-01-01", "end": "2024-12-31"},
                },
            },
        )
    )
    response = LLMInterpretationResponse(
        intent="strategy_drafting",
        task_relation="new_task",
        requires_clarification=False,
        user_goal_summary="User asks what date the latest result peaked.",
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing="what date did this peak?",
            strategy_type="buy_and_hold",
            strategy_thesis="AAPL buy and hold",
            asset_universe=["AAPL"],
            asset_class="equity",
            date_range={"start": "2024-01-01", "end": "2024-12-31"},
            timeframe="1D",
        ),
        semantic_turn_act="new_idea",
    )

    repaired = await interpreter_module._response_ready_for_runtime(
        response=response,
        preferred_model="structured/primary",
        request=InterpretationRequest(
            current_user_message="what date did this peak?",
            recent_thread_history=[],
            latest_task_snapshot=snapshot,
            user=UserState(user_id="u1"),
        ),
    )

    assert calls
    assert calls[0]["schema_model"] is interpreter_module.LatestResultRoutingAudit
    assert repaired.semantic_turn_act == "result_followup"
    assert repaired.result_followup_focus == "peak_date"
    assert repaired.result_followup_fact_key == "peak_date"
    assert repaired.artifact_target == "latest_result"
    assert repaired.assistant_response is None
    assert "latest_result_routing_audit" in repaired.reason_codes


def test_llm_interpreter_honors_explicit_buy_and_hold_over_entry_like_phrase(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    monkeypatch.setattr(
        interpreter_module,
        "resolve_asset",
        lambda symbol: ResolvedAssetStub(symbol.upper(), "crypto"),
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    response = LLMInterpretationResponse(
        intent="backtest_execution",
        task_relation="new_task",
        user_goal_summary="Buy and hold Bitcoin from January 1 last year.",
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing=(
                "let's try a basic buy and hold on BTC from jan first last year to date"
            ),
            strategy_type="buy_and_hold",
            strategy_thesis="Buy and hold Bitcoin from January 1 last year.",
            asset_universe=["BTC"],
            date_range={"start": "2024-01-01", "end": "today"},
        ),
    )

    result = interpreter._to_runtime_interpretation(
        response,
        request=InterpretationRequest(
            current_user_message=(
                "let's try a basic buy and hold on BTC from jan first last year to date"
            ),
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        ),
    )

    strategy = result.candidate_strategy_draft
    assert strategy.strategy_type == "buy_and_hold"
    assert strategy.entry_logic is None
    assert strategy.exit_logic is None
    assert result.requires_clarification is False


def test_llm_interpreter_preserves_actual_user_phrasing_when_model_rewrites_it(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    monkeypatch.setattr(
        interpreter_module,
        "resolve_asset",
        lambda symbol: ResolvedAssetStub(symbol.upper(), "crypto"),
    )

    user_message = (
        "let's try a basic buy and hold on BTC from jan first last year to date"
    )
    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    response = LLMInterpretationResponse(
        intent="strategy_drafting",
        task_relation="new_task",
        user_goal_summary="Buy and hold BTC.",
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing="buy and hold on BTC from jan first last 1 year to date",
            strategy_type="buy_and_hold",
            asset_universe=["BTC"],
            date_range={"start": "2025-01-01", "end": "today"},
            capital_amount=10000,
            comparison_baseline="BTC",
        ),
    )

    result = interpreter._to_runtime_interpretation(
        response,
        request=InterpretationRequest(
            current_user_message=user_message,
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        ),
    )

    strategy = result.candidate_strategy_draft
    assert strategy.raw_user_phrasing == user_message
    assert strategy.strategy_thesis == user_message
    assert strategy.date_range == {"start": "2025-01-01", "end": "today"}


def test_focused_strategy_repair_prompt_covers_starter_capability_shapes() -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    messages = interpreter_module._focused_strategy_extraction_messages(
        InterpretationRequest(
            current_user_message="What if I bought Bitcoin this year so far?",
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        )
    )
    prompt = messages[0].content

    assert "year_to_date" in prompt
    assert "recurring_contribution" in prompt
    assert "dca_accumulation" in prompt
    assert "supported buy_and_hold simulation" in prompt
    assert "recurring fixed-amount purchase" in prompt


def test_dca_required_fields_accept_resolved_date_range_intent() -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    draft = LLMStrategyDraft(
        strategy_type="dca_accumulation",
        asset_universe=["NVDA"],
        asset_class="equity",
        capital_amount=250,
        recurring_contribution=250,
        cadence="weekly",
        date_range_intent=interpreter_module.LLMDateRangeIntent(
            kind="rolling_window",
            count=1,
            unit="year",
            anchor="today",
        ),
    )

    missing = (
        interpreter_module._capability_required_missing_fields_for_canonical_strategy(
            ["date_range"],
            draft=draft,
        )
    )
    expected_range = interpreter_module.resolve_date_range_intent(
        interpreter_module.LLMDateRangeIntent(
            kind="rolling_window",
            count=1,
            unit="year",
            anchor="today",
        )
    )

    assert expected_range is not None
    assert missing == []
    assert draft.date_range == expected_range.payload


@pytest.mark.asyncio
async def test_complete_absolute_run_skips_optional_runtime_readiness_audits(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    def resolve_asset(query: str) -> ResolvedAssetStub:
        normalized = query.strip().upper()
        if normalized not in {"AAPL", "MSFT"}:
            raise ValueError("invalid_symbol")
        return ResolvedAssetStub(normalized, "equity", name=normalized)

    async def fail_optional_audit(**_kwargs):
        raise AssertionError("optional readiness audit should not run")

    async def fail_schema_audit(**_kwargs):
        raise AssertionError("structured audit should not run")

    monkeypatch.setattr(interpreter_module, "resolve_asset", resolve_asset)
    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        fail_schema_audit,
    )
    for name in (
        "_pending_response_option_selected_response",
        "_requested_asset_answer_candidate_audited_response",
        "_latest_result_routing_audited_response",
        "_asset_grounding_audited_response",
        "_capability_side_question_audited_response",
        "_context_question_audited_response",
        "_dca_contract_audited_response",
        "_strategy_family_continuity_audited_response",
        "_dca_contribution_role_audited_response",
        "_audit_supported_strategy_capability_conflict",
        "_focused_date_window_audited_response",
        "_supported_date_gap_schema_repaired_response",
        "_repair_incomplete_strategy_extraction",
        "_audit_stated_run_fields",
        "_audit_executable_strategy_grounding",
    ):
        monkeypatch.setattr(interpreter_module, name, fail_optional_audit)

    message = (
        "Prueba una estrategia de comprar y mantener AAPL y MSFT con pesos "
        "iguales desde el 1 de enero de 2025 hasta el 5 de junio de 2026 "
        "con 10000 dolares"
    )
    response = LLMInterpretationResponse(
        intent="backtest_execution",
        task_relation="new_task",
        requires_clarification=False,
        user_goal_summary=message,
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing=message,
            language="es-419",
            strategy_type="buy_and_hold",
            strategy_thesis="Comprar y mantener AAPL y MSFT con pesos iguales.",
            asset_universe=["AAPL", "MSFT"],
            asset_class="equity",
            date_range={"start": "2025-01-01", "end": "2026-06-05"},
            capital_amount=10000,
            comparison_baseline="SPY",
            field_provenance={"capital_amount": "starting_capital"},
        ),
        semantic_turn_act="new_idea",
        artifact_target="none",
    )
    request = InterpretationRequest(
        current_user_message=message,
        recent_thread_history=[],
        latest_task_snapshot=None,
        user=UserState(user_id="u1", language_preference="es-419"),
    )

    assert interpreter_module._response_can_skip_optional_runtime_readiness_audits(
        response=response,
        request=request,
    )

    ready_response = await interpreter_module._response_ready_for_runtime(
        response=response,
        preferred_model="test-model",
        request=request,
    )

    assert ready_response.candidate_strategy_draft.date_range == {
        "start": "2025-01-01",
        "end": "2026-06-05",
    }
    assert ready_response.candidate_strategy_draft.asset_universe == [
        "AAPL",
        "MSFT",
    ]
    assert ready_response.candidate_strategy_draft.comparison_baseline == "SPY"
    assert ready_response.candidate_strategy_draft.capital_amount == 10000


@pytest.mark.asyncio
async def test_missing_starting_capital_rechecks_before_optional_runtime_audits(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    def resolve_asset(query: str) -> ResolvedAssetStub:
        normalized = query.strip().upper()
        if normalized not in {"AAPL", "MSFT"}:
            raise ValueError("invalid_symbol")
        return ResolvedAssetStub(normalized, "equity", name=normalized)

    async def fail_optional_audit(**_kwargs):
        raise AssertionError("optional readiness audit should not run")

    calls: list[str] = []

    async def audit_stub(**kwargs):
        schema_name = kwargs["schema_name"]
        calls.append(schema_name)
        if schema_name == "StatedStartingCapitalAudit":
            return interpreter_module.StatedStartingCapitalAudit(
                starting_capital=10000,
            )
        raise AssertionError(f"Unexpected schema {schema_name}")

    monkeypatch.setattr(interpreter_module, "resolve_asset", resolve_asset)
    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        audit_stub,
    )
    for name in (
        "_pending_response_option_selected_response",
        "_requested_asset_answer_candidate_audited_response",
        "_latest_result_routing_audited_response",
        "_asset_grounding_audited_response",
        "_capability_side_question_audited_response",
        "_context_question_audited_response",
        "_dca_contract_audited_response",
        "_strategy_family_continuity_audited_response",
        "_dca_contribution_role_audited_response",
        "_audit_supported_strategy_capability_conflict",
        "_focused_date_window_audited_response",
        "_supported_date_gap_schema_repaired_response",
        "_repair_incomplete_strategy_extraction",
        "_audit_stated_run_fields",
        "_audit_executable_strategy_grounding",
    ):
        monkeypatch.setattr(interpreter_module, name, fail_optional_audit)

    message = (
        "Prueba una estrategia de comprar y mantener AAPL y MSFT con pesos "
        "iguales desde el 1 de enero de 2025 hasta el 5 de junio de 2026 "
        "con 10000 dolares"
    )
    response = LLMInterpretationResponse(
        intent="backtest_execution",
        task_relation="new_task",
        requires_clarification=False,
        user_goal_summary=message,
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing=message,
            language="es-419",
            strategy_type="buy_and_hold",
            strategy_thesis="Comprar y mantener AAPL y MSFT con pesos iguales.",
            asset_universe=["AAPL", "MSFT"],
            asset_class="equity",
            date_range={"start": "2025-01-01", "end": "2026-06-05"},
            comparison_baseline="SPY",
        ),
        semantic_turn_act="new_idea",
        artifact_target="none",
    )
    request = InterpretationRequest(
        current_user_message=message,
        recent_thread_history=[],
        latest_task_snapshot=None,
        user=UserState(user_id="u1", language_preference="es-419"),
    )

    assert (
        interpreter_module._optional_runtime_readiness_audit_blocker(
            response=response,
            request=request,
        )
        == "stated_starting_capital_recheck"
    )

    ready_response = await interpreter_module._response_ready_for_runtime(
        response=response,
        preferred_model="test-model",
        request=request,
    )

    assert calls == ["StatedStartingCapitalAudit"]
    assert ready_response.candidate_strategy_draft.date_range == {
        "start": "2025-01-01",
        "end": "2026-06-05",
    }
    assert ready_response.candidate_strategy_draft.asset_universe == [
        "AAPL",
        "MSFT",
    ]
    assert ready_response.candidate_strategy_draft.comparison_baseline == "SPY"
    assert ready_response.candidate_strategy_draft.capital_amount == 10000
    assert (
        ready_response.candidate_strategy_draft.field_provenance["capital_amount"]
        == "starting_capital"
    )
    assert "stated_starting_capital_recheck" in ready_response.reason_codes
    assert "stated_run_field_fidelity_audit" in ready_response.reason_codes


@pytest.mark.asyncio
async def test_failed_capital_recheck_uses_focused_strategy_repair_before_baseline(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    def resolve_asset(query: str) -> ResolvedAssetStub:
        normalized = query.strip().upper()
        if normalized not in {"AAPL", "MSFT"}:
            raise ValueError("invalid_symbol")
        return ResolvedAssetStub(normalized, "equity", name=normalized)

    async def fail_baseline_audit(**_kwargs):
        raise AssertionError("baseline audit should not run before focused repair")

    calls: list[str] = []

    async def audit_stub(**kwargs):
        schema_name = kwargs["schema_name"]
        calls.append(schema_name)
        if schema_name == "StatedRunFieldFidelityAudit":
            return interpreter_module.StatedRunFieldFidelityAudit()
        if schema_name == "StatedStartingCapitalAudit":
            return interpreter_module.StatedStartingCapitalAudit(
                starting_capital=None,
                confidence=0.9,
            )
        if schema_name == "FocusedStrategyExtraction":
            return interpreter_module.FocusedStrategyExtraction(
                is_testable_strategy=True,
                requires_clarification=False,
                user_goal_summary="Comprar y mantener AAPL y MSFT.",
                language="es-419",
                strategy_type="buy_and_hold",
                strategy_thesis="Comprar y mantener AAPL y MSFT con pesos iguales.",
                asset_universe=["AAPL", "MSFT"],
                asset_class="equity",
                date_range={"start": "2025-01-01", "end": "2026-06-05"},
                capital_amount=10000,
                confidence=0.92,
                evidence_spans={
                    "asset_universe": "AAPL y MSFT",
                    "capital_amount": "10000 dolares",
                    "date_range": "1 de enero de 2025 hasta el 5 de junio de 2026",
                    "strategy_type": "comprar y mantener",
                },
            )
        raise AssertionError(f"Unexpected schema {schema_name}")

    monkeypatch.setattr(interpreter_module, "resolve_asset", resolve_asset)
    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        audit_stub,
    )
    for name in (
        "_pending_response_option_selected_response",
        "_requested_asset_answer_candidate_audited_response",
        "_latest_result_routing_audited_response",
        "_asset_grounding_audited_response",
        "_capability_side_question_audited_response",
        "_context_question_audited_response",
        "_dca_contract_audited_response",
        "_strategy_family_continuity_audited_response",
        "_dca_contribution_role_audited_response",
    ):
        monkeypatch.setattr(interpreter_module, name, fail_baseline_audit)

    message = (
        "Prueba una estrategia de comprar y mantener AAPL y MSFT con pesos "
        "iguales desde el 1 de enero de 2025 hasta el 5 de junio de 2026 "
        "con 10000 dolares"
    )
    response = LLMInterpretationResponse(
        intent="strategy_drafting",
        task_relation="new_task",
        requires_clarification=False,
        user_goal_summary=message,
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing=message,
            language="es-419",
            strategy_type="buy_and_hold",
            strategy_thesis="Comprar y mantener AAPL y MSFT con pesos iguales.",
            asset_universe=["AAPL", "MSFT"],
            asset_class="equity",
            date_range={"start": "2025-01-01", "end": "2026-06-05"},
            comparison_baseline="SPY",
            date_range_raw_text="1 de enero de 2025 hasta el 5 de junio de 2026",
            date_range_intent=interpreter_module.LLMDateRangeIntent(
                kind="explicit_range",
                start="2025-01-01",
                end="2026-06-05",
                evidence="1 de enero de 2025 hasta el 5 de junio de 2026",
            ),
        ),
        semantic_turn_act="new_idea",
        artifact_target="none",
    )
    request = InterpretationRequest(
        current_user_message=message,
        recent_thread_history=[],
        latest_task_snapshot=None,
        user=UserState(user_id="u1", language_preference="es-419"),
    )

    ready_response = await interpreter_module._response_ready_for_runtime(
        response=response,
        preferred_model="test-model",
        request=request,
    )

    assert calls == ["StatedStartingCapitalAudit", "FocusedStrategyExtraction", "StatedRunFieldFidelityAudit"]
    assert ready_response.candidate_strategy_draft.capital_amount == 10000
    assert (
        ready_response.candidate_strategy_draft.field_provenance["capital_amount"]
        == "starting_capital"
    )
    assert "focused_strategy_extraction_repair" in ready_response.reason_codes


@pytest.mark.asyncio
async def test_focused_strategy_repair_canonicalizes_interpreter_identified_assets(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    resolved_queries: list[str] = []

    def resolve_asset(query: str) -> ResolvedAssetStub:
        resolved_queries.append(query)
        normalized = query.strip().upper()
        if normalized not in {"AAPL", "MSFT"}:
            raise ValueError("invalid_symbol")
        return ResolvedAssetStub(normalized, "equity", name=normalized)

    calls: list[str] = []

    async def audit_stub(**kwargs):
        schema_name = kwargs["schema_name"]
        calls.append(schema_name)
        if schema_name == "StatedRunFieldFidelityAudit":
            return interpreter_module.StatedRunFieldFidelityAudit()
        if schema_name == "FocusedStrategyExtraction":
            return interpreter_module.FocusedStrategyExtraction(
                is_testable_strategy=True,
                requires_clarification=False,
                user_goal_summary="Comprar y mantener AAPL y MSFT.",
                language="es-419",
                strategy_type="buy_and_hold",
                strategy_thesis=(
                    "Comprar y mantener AAPL y MSFT con pesos iguales y " "10000 dólares."
                ),
                asset_universe=["AAPL", "MSFT"],
                date_range={"start": "2025-01-01", "end": "2026-06-05"},
                capital_amount=10000,
                confidence=0.9,
                evidence_spans={
                    "date_range": "1 de enero de 2025 hasta el 5 de junio de 2026",
                    "strategy_type": "comprar y mantener",
                },
            )
        raise AssertionError(f"Unexpected schema {schema_name}")

    monkeypatch.setattr(interpreter_module, "resolve_asset", resolve_asset)
    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        audit_stub,
    )

    message = (
        "Prueba una estrategia de comprar y mantener AAPL y MSFT con pesos "
        "iguales desde el 1 de enero de 2025 hasta el 5 de junio de 2026 "
        "con 10000 dolares"
    )
    seed_response = LLMInterpretationResponse(
        intent="strategy_drafting",
        task_relation="new_task",
        requires_clarification=False,
        user_goal_summary=message,
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing=message,
            strategy_type="buy_and_hold",
            strategy_thesis=message,
        ),
        semantic_turn_act="new_idea",
    )
    request = InterpretationRequest(
        current_user_message=message,
        recent_thread_history=[],
        latest_task_snapshot=None,
        user=UserState(user_id="u1", language_preference="es-419"),
    )

    repaired = await interpreter_module._repair_incomplete_strategy_extraction(
        failed_response=seed_response,
        preferred_model="test-model",
        request=request,
    )

    assert calls == ["FocusedStrategyExtraction", "StatedRunFieldFidelityAudit"]
    assert repaired is not None
    assert repaired.candidate_strategy_draft.asset_universe == ["AAPL", "MSFT"]
    assert repaired.candidate_strategy_draft.asset_class == "equity"
    assert {"AAPL", "MSFT"}.issubset(resolved_queries)
    assert set(resolved_queries) <= {"AAPL", "MSFT"}
    assert "focused_strategy_extraction_repair" in repaired.reason_codes
    assert "provider_catalog_asset_recovery" not in repaired.reason_codes
    assert interpreter_module._response_can_skip_optional_runtime_readiness_audits(
        response=repaired,
        request=request,
    )


@pytest.mark.asyncio
async def test_missing_turn_act_underfilled_strategy_repairs_before_baseline_audits(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    def resolve_asset(query: str) -> ResolvedAssetStub:
        normalized = query.strip().upper()
        if normalized not in {"AAPL", "MSFT"}:
            raise ValueError("invalid_symbol")
        return ResolvedAssetStub(normalized, "equity", name=normalized)

    async def fail_baseline_audit(**_kwargs):
        raise AssertionError("baseline audit should not run before focused repair")

    calls: list[str] = []

    async def audit_stub(**kwargs):
        schema_name = kwargs["schema_name"]
        calls.append(schema_name)
        if schema_name == "FocusedStrategyExtraction":
            return interpreter_module.FocusedStrategyExtraction(
                is_testable_strategy=True,
                requires_clarification=False,
                user_goal_summary="Comprar y mantener AAPL y MSFT.",
                language="es-419",
                strategy_type="buy_and_hold",
                strategy_thesis="Comprar y mantener AAPL y MSFT con pesos iguales.",
                asset_universe=["AAPL", "MSFT"],
                asset_class="equity",
                date_range={"start": "2025-01-01", "end": "2026-06-05"},
                capital_amount=10000,
                confidence=0.92,
                evidence_spans={
                    "asset_universe": "AAPL y MSFT",
                    "capital_amount": "10000 dolares",
                    "date_range": "1 de enero de 2025 hasta el 5 de junio de 2026",
                    "strategy_type": "comprar y mantener",
                },
            )
        if schema_name == "FocusedDateWindowExtraction":
            return interpreter_module.FocusedDateWindowExtraction(
                has_date_window=False,
                confidence=0.1,
            )
        if schema_name == "StatedRunFieldFidelityAudit":
            return interpreter_module.StatedRunFieldFidelityAudit(confidence=0.9)
        if schema_name == "StatedStartingCapitalAudit":
            return interpreter_module.StatedStartingCapitalAudit(
                starting_capital=None,
                confidence=0.9,
            )
        if schema_name == "SupportedStrategyCapabilityConflictAudit":
            return interpreter_module.SupportedStrategyCapabilityConflictAudit(
                selected_strategy_type=None,
                confidence=0.2,
            )
        raise AssertionError(f"Unexpected schema {schema_name}")

    monkeypatch.setattr(interpreter_module, "resolve_asset", resolve_asset)
    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        audit_stub,
    )
    for name in (
        "_capability_side_question_audited_response",
        "_context_question_audited_response",
        "_dca_contract_audited_response",
        "_strategy_family_continuity_audited_response",
        "_dca_contribution_role_audited_response",
    ):
        monkeypatch.setattr(interpreter_module, name, fail_baseline_audit)

    message = (
        "Prueba una estrategia de comprar y mantener AAPL y MSFT con pesos "
        "iguales desde el 1 de enero de 2025 hasta el 5 de junio de 2026 "
        "con 10000 dolares"
    )
    response = LLMInterpretationResponse(
        intent="strategy_drafting",
        task_relation="new_task",
        requires_clarification=False,
        user_goal_summary=message,
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing=message,
            language="es-419",
            strategy_type="buy_and_hold",
            strategy_thesis="Comprar y mantener AAPL y MSFT con pesos iguales.",
            asset_universe=["AAPL", "MSFT"],
            asset_class="equity",
            comparison_baseline="SPY",
        ),
        semantic_turn_act=None,
        artifact_target="none",
    )
    request = InterpretationRequest(
        current_user_message=message,
        recent_thread_history=[],
        latest_task_snapshot=None,
        user=UserState(user_id="u1", language_preference="es-419"),
    )

    ready_response = await interpreter_module._response_ready_for_runtime(
        response=response,
        preferred_model="test-model",
        request=request,
    )

    assert calls[0] == "FocusedStrategyExtraction"
    assert ready_response.semantic_turn_act == "new_idea"
    assert "coerced_missing_turn_act_to_new_idea" in ready_response.reason_codes
    assert ready_response.candidate_strategy_draft.date_range == {
        "start": "2025-01-01",
        "end": "2026-06-05",
    }
    assert ready_response.candidate_strategy_draft.capital_amount == 10000


def test_unprovenanced_non_default_benchmark_blocks_runtime_fast_path(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    def resolve_asset(query: str) -> ResolvedAssetStub:
        normalized = query.strip().upper()
        if normalized not in {"AAPL"}:
            raise ValueError("invalid_symbol")
        return ResolvedAssetStub(normalized, "equity", name=normalized)

    monkeypatch.setattr(interpreter_module, "resolve_asset", resolve_asset)

    response = LLMInterpretationResponse(
        intent="backtest_execution",
        task_relation="new_task",
        requires_clarification=False,
        user_goal_summary="Test AAPL from January 1, 2025 to June 5, 2026.",
        candidate_strategy_draft=LLMStrategyDraft(
            strategy_type="buy_and_hold",
            asset_universe=["AAPL"],
            asset_class="equity",
            date_range={"start": "2025-01-01", "end": "2026-06-05"},
            capital_amount=10000,
            comparison_baseline="QQQ",
        ),
        semantic_turn_act="new_idea",
        artifact_target="none",
    )
    request = InterpretationRequest(
        current_user_message="Test AAPL from January 1, 2025 to June 5, 2026.",
        recent_thread_history=[],
        latest_task_snapshot=None,
        user=UserState(user_id="u1", language_preference="en"),
    )

    assert (
        interpreter_module._optional_runtime_readiness_audit_blocker(
            response=response,
            request=request,
        )
        == "unprovenanced_benchmark"
    )
    assert not interpreter_module._response_can_skip_optional_runtime_readiness_audits(
        response=response,
        request=request,
    )


def test_relative_window_evidence_blocks_optional_readiness_fast_path() -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    message = "Compra y mantén AAPL durante los últimos 2 años con 10000 dolares."
    response = LLMInterpretationResponse(
        intent="backtest_execution",
        task_relation="new_task",
        requires_clarification=False,
        user_goal_summary=message,
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing=message,
            language="es-419",
            strategy_type="buy_and_hold",
            strategy_thesis=message,
            asset_universe=["AAPL"],
            asset_class="equity",
            date_range={"start": "2024-01-01", "end": "2026-01-01"},
            capital_amount=10000,
        ),
        semantic_turn_act="new_idea",
        artifact_target="none",
    )
    request = InterpretationRequest(
        current_user_message=message,
        recent_thread_history=[],
        latest_task_snapshot=None,
        user=UserState(user_id="u1", language_preference="es-419"),
    )

    assert interpreter_module._current_turn_has_relative_window_evidence(request)
    assert interpreter_module._response_needs_temporal_runtime_repair(
        response=response,
        request=request,
    )
    assert not interpreter_module._response_can_skip_optional_runtime_readiness_audits(
        response=response,
        request=request,
    )


@pytest.mark.asyncio
async def test_dca_repair_uses_focused_date_audit_from_bounded_evidence_span(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    calls: list[str] = []

    async def audit_stub(**kwargs):
        schema_name = kwargs["schema_name"]
        calls.append(schema_name)
        if schema_name == "StatedRunFieldFidelityAudit":
            return interpreter_module.StatedRunFieldFidelityAudit()
        if schema_name == "FocusedStrategyExtraction":
            return interpreter_module.FocusedStrategyExtraction(
                is_testable_strategy=True,
                requires_clarification=False,
                user_goal_summary="Probar compras recurrentes de Nvidia.",
                language="es-419",
                strategy_type="dca_accumulation",
                strategy_thesis="Comprar $250 de Nvidia cada semana.",
                asset_universe=["NVDA"],
                asset_class="equity",
                capital_amount=250,
                recurring_contribution=250,
                cadence="weekly",
                confidence=0.91,
                evidence_spans={"date_range_intent": "durante el último año"},
            )
        if schema_name == "FocusedDateWindowExtraction":
            return interpreter_module.FocusedDateWindowExtraction(
                has_date_window=True,
                date_range_raw_text="durante el último año",
                date_range_intent=interpreter_module.LLMDateRangeIntent(
                    kind="rolling_window",
                    count=1,
                    unit="year",
                    anchor="today",
                    confidence=0.92,
                    evidence="durante el último año",
                ),
                confidence=0.92,
                evidence="durante el último año",
            )
        raise AssertionError(f"Unexpected schema {schema_name}")

    async def no_conflict_audit(**_kwargs):
        return None

    async def passthrough_response(**kwargs):
        return kwargs["response"]

    monkeypatch.setattr(
        interpreter_module,
        "_asset_grounding_audited_response",
        passthrough_response,
    )
    monkeypatch.setattr(
        interpreter_module,
        "_capability_side_question_audited_response",
        passthrough_response,
    )
    monkeypatch.setattr(
        interpreter_module,
        "_context_question_audited_response",
        passthrough_response,
    )
    monkeypatch.setattr(
        interpreter_module,
        "_audit_supported_strategy_capability_conflict",
        no_conflict_audit,
    )
    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        audit_stub,
    )

    message = (
        "¿Qué habría pasado si compraba $250 de Nvidia cada semana durante el último año?"
    )
    response = LLMInterpretationResponse(
        intent="unsupported_or_out_of_scope",
        task_relation="new_task",
        requires_clarification=True,
        user_goal_summary=message,
        assistant_response="Las compras recurrentes no están disponibles.",
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing=message,
            strategy_thesis=message,
            asset_universe=["NVDA"],
            asset_class="equity",
        ),
        unsupported_constraints=[
            interpreter_module.LLMUnsupportedConstraint(
                category="unsupported_strategy_logic",
                raw_value=message,
                explanation="The model over-routed a supported DCA request.",
                simplification_labels=["Compare with buy and hold"],
            )
        ],
        missing_required_fields=["entry_logic", "exit_logic", "date_range"],
        semantic_turn_act="unsupported_request",
        artifact_target="none",
    )
    request = InterpretationRequest(
        current_user_message=message,
        recent_thread_history=[],
        latest_task_snapshot=None,
        user=UserState(user_id="u1", language_preference="es-419"),
    )

    ready_response = await interpreter_module._response_ready_for_runtime(
        response=response,
        preferred_model="test-model",
        request=request,
    )
    expected_range = interpreter_module.resolve_date_range_intent(
        interpreter_module.LLMDateRangeIntent(
            kind="rolling_window",
            count=1,
            unit="year",
            anchor="today",
        )
    )

    assert "FocusedStrategyExtraction" in calls
    assert "FocusedDateWindowExtraction" in calls
    assert calls.index("FocusedStrategyExtraction") < calls.index(
        "FocusedDateWindowExtraction"
    )
    assert expected_range is not None
    assert ready_response.intent == "backtest_execution"
    assert ready_response.unsupported_constraints == []
    assert ready_response.missing_required_fields == []
    assert ready_response.candidate_strategy_draft.date_range == expected_range.payload


@pytest.mark.asyncio
async def test_counterfactual_bitcoin_ytd_starter_gets_focused_repair(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    def resolve_asset(query: str) -> ResolvedAssetStub:
        normalized = query.strip().upper()
        if normalized in {"BITCOIN", "BTC"}:
            return ResolvedAssetStub(
                "BTC",
                "crypto",
                name="Bitcoin",
                raw_symbol=query,
            )
        raise ValueError("invalid_symbol")

    calls: list[str] = []

    async def audit_stub(**kwargs):
        schema_name = kwargs["schema_name"]
        calls.append(schema_name)
        if schema_name == "StatedRunFieldFidelityAudit":
            return interpreter_module.StatedRunFieldFidelityAudit()
        if schema_name == "FocusedStrategyExtraction":
            return interpreter_module.FocusedStrategyExtraction(
                is_testable_strategy=True,
                requires_clarification=False,
                user_goal_summary="Probar Bitcoin en lo que va del año.",
                language="es-419",
                strategy_type="buy_and_hold",
                strategy_thesis="Comprar Bitcoin en lo que va del año.",
                asset_universe=["Bitcoin"],
                asset_class="crypto",
                date_range_raw_text="en lo que va del año",
                date_range_intent=interpreter_module.LLMDateRangeIntent(
                    kind="year_to_date",
                    confidence=0.93,
                    evidence="en lo que va del año",
                ),
                confidence=0.91,
                evidence_spans={
                    "strategy_type": "compraba Bitcoin",
                    "asset_universe": "Bitcoin",
                    "date_range": "en lo que va del año",
                },
            )
        raise AssertionError(f"Unexpected schema {schema_name}")

    monkeypatch.setattr(interpreter_module, "resolve_asset", resolve_asset)
    monkeypatch.setattr(
        interpreter_module,
        "_request_current_turn_has_material_execution_evidence",
        lambda _request: False,
    )
    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        audit_stub,
    )

    response = LLMInterpretationResponse(
        intent="unsupported_or_out_of_scope",
        task_relation="new_task",
        requires_clarification=True,
        user_goal_summary="¿Qué habría pasado si compraba Bitcoin en lo que va del año?",
        assistant_response="Esa idea necesita una regla de entrada y salida.",
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing=(
                "¿Qué habría pasado si compraba Bitcoin en lo que va del año?"
            ),
            strategy_thesis=(
                "¿Qué habría pasado si compraba Bitcoin en lo que va del año?"
            ),
        ),
        unsupported_constraints=[
            interpreter_module.LLMUnsupportedConstraint(
                category="unsupported_strategy_logic",
                raw_value="¿Qué habría pasado si compraba Bitcoin en lo que va del año?",
                explanation="The model over-routed a supported counterfactual purchase.",
                simplification_labels=["Compare with buy and hold"],
            )
        ],
        missing_required_fields=["entry_logic", "asset_universe", "exit_logic"],
        semantic_turn_act="unsupported_request",
        artifact_target="none",
    )

    request = InterpretationRequest(
        current_user_message=(
            "¿Qué habría pasado si compraba Bitcoin en lo que va del año?"
        ),
        recent_thread_history=[],
        latest_task_snapshot=None,
        user=UserState(user_id="u1", language_preference="es-419"),
    )

    ready_response = await interpreter_module._response_ready_for_runtime(
        response=response,
        preferred_model="test-model",
        request=request,
    )

    assert "FocusedStrategyExtraction" in calls
    assert ready_response.intent == "backtest_execution"
    assert ready_response.requires_clarification is False
    assert ready_response.assistant_response is None
    assert ready_response.unsupported_constraints == []
    draft = ready_response.candidate_strategy_draft
    expected_range = interpreter_module.resolve_date_range_intent(
        interpreter_module.LLMDateRangeIntent(kind="year_to_date")
    )
    assert expected_range is not None
    assert draft.strategy_type == "buy_and_hold"
    assert draft.asset_universe == ["BTC"]
    assert draft.asset_class == "crypto"
    assert draft.date_range == expected_range.payload

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    result = interpreter._to_runtime_interpretation(ready_response, request=request)
    assert result.candidate_strategy_draft.asset_universe == ["BTC"]


@pytest.mark.asyncio
async def test_weekly_nvidia_dca_starter_gets_focused_repair(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    def resolve_asset(query: str) -> ResolvedAssetStub:
        normalized = query.strip().upper()
        if normalized in {"NVIDIA", "NVDA"}:
            return ResolvedAssetStub(
                "NVDA",
                "equity",
                name="NVIDIA Corporation",
                raw_symbol=query,
            )
        raise ValueError("invalid_symbol")

    calls: list[str] = []

    async def audit_stub(**kwargs):
        schema_name = kwargs["schema_name"]
        calls.append(schema_name)
        if schema_name == "StatedRunFieldFidelityAudit":
            return interpreter_module.StatedRunFieldFidelityAudit()
        if schema_name == "FocusedStrategyExtraction":
            return interpreter_module.FocusedStrategyExtraction(
                is_testable_strategy=True,
                requires_clarification=False,
                user_goal_summary="Probar compras recurrentes de Nvidia.",
                language="es-419",
                strategy_type="dca_accumulation",
                strategy_thesis="Comprar $250 de Nvidia cada semana.",
                asset_universe=["NVDA"],
                asset_class="equity",
                capital_amount=250,
                recurring_contribution=250,
                cadence="weekly",
                date_range_raw_text="durante el último año",
                date_range_intent=interpreter_module.LLMDateRangeIntent(
                    kind="rolling_window",
                    count=1,
                    unit="year",
                    anchor="today",
                    confidence=0.92,
                    evidence="durante el último año",
                ),
                confidence=0.91,
                evidence_spans={
                    "asset_universe": "Nvidia",
                    "recurring_contribution": "$250",
                    "cadence": "cada semana",
                    "date_range": "durante el último año",
                },
            )
        raise AssertionError(f"Unexpected schema {schema_name}")

    monkeypatch.setattr(interpreter_module, "resolve_asset", resolve_asset)
    monkeypatch.setattr(
        interpreter_module,
        "_request_current_turn_has_material_execution_evidence",
        lambda _request: False,
    )
    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        audit_stub,
    )

    response = LLMInterpretationResponse(
        intent="unsupported_or_out_of_scope",
        task_relation="new_task",
        requires_clarification=True,
        user_goal_summary=(
            "¿Qué habría pasado si compraba $250 de Nvidia cada semana durante el último año?"
        ),
        assistant_response="Las compras recurrentes no están disponibles.",
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing=(
                "¿Qué habría pasado si compraba $250 de Nvidia cada semana durante el último año?"
            ),
            strategy_thesis=(
                "¿Qué habría pasado si compraba $250 de Nvidia cada semana durante el último año?"
            ),
            asset_universe=["NVDA"],
            asset_class="equity",
            date_range={"start": "2025-06-13", "end": "2026-06-13"},
        ),
        unsupported_constraints=[
            interpreter_module.LLMUnsupportedConstraint(
                category="unsupported_strategy_logic",
                raw_value=(
                    "¿Qué habría pasado si compraba $250 de Nvidia cada semana durante el último año?"
                ),
                explanation="The model over-routed a supported DCA request.",
                simplification_labels=["Compare with buy and hold"],
            )
        ],
        missing_required_fields=["entry_logic", "asset_universe", "exit_logic"],
        semantic_turn_act="unsupported_request",
        artifact_target="none",
    )

    ready_response = await interpreter_module._response_ready_for_runtime(
        response=response,
        preferred_model="test-model",
        request=InterpretationRequest(
            current_user_message=(
                "¿Qué habría pasado si compraba $250 de Nvidia cada semana durante el último año?"
            ),
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1", language_preference="es-419"),
        ),
    )

    assert "FocusedStrategyExtraction" in calls
    assert ready_response.intent == "backtest_execution"
    assert ready_response.requires_clarification is False
    assert ready_response.assistant_response is None
    assert ready_response.unsupported_constraints == []
    draft = ready_response.candidate_strategy_draft
    expected_range = interpreter_module.resolve_date_range_intent(
        interpreter_module.LLMDateRangeIntent(
            kind="rolling_window",
            count=1,
            unit="year",
            anchor="today",
        )
    )
    assert expected_range is not None
    assert draft.strategy_type == "dca_accumulation"
    assert draft.asset_universe == ["NVDA"]
    assert draft.asset_class == "equity"
    assert draft.recurring_contribution == 250
    assert draft.capital_amount == 250
    assert draft.cadence == "weekly"
    assert draft.date_range == expected_range.payload
    assert draft.field_provenance["capital_amount"] == "recurring_contribution"
    assert draft.field_provenance["recurring_contribution"] == "explicit_user"
    assert draft.field_provenance["cadence"] == "explicit_user"


@pytest.mark.asyncio
async def test_dca_capability_conflict_repair_does_not_stop_underfilled(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    def resolve_asset(query: str) -> ResolvedAssetStub:
        normalized = query.strip().upper()
        if normalized in {"NVIDIA", "NVDA"}:
            return ResolvedAssetStub(
                "NVDA",
                "equity",
                name="NVIDIA Corporation",
                raw_symbol=query,
            )
        raise ValueError("invalid_symbol")

    calls: list[str] = []

    async def audit_stub(**kwargs):
        schema_name = kwargs["schema_name"]
        calls.append(schema_name)
        if schema_name == "StatedRunFieldFidelityAudit":
            return interpreter_module.StatedRunFieldFidelityAudit()
        if schema_name == "DcaContractAudit":
            return interpreter_module.DcaContractAudit(
                is_recurring_buy_request=False,
                confidence=0.92,
            )
        if schema_name == "SupportedStrategyCapabilityConflictAudit":
            return interpreter_module.SupportedStrategyCapabilityConflictAudit(
                selected_strategy_type="dca_accumulation",
                drop_unsupported_strategy_logic=True,
                keep_unsupported_strategy_logic=False,
                confidence=0.92,
            )
        if schema_name == "FocusedStrategyExtraction":
            return interpreter_module.FocusedStrategyExtraction(
                is_testable_strategy=True,
                requires_clarification=False,
                user_goal_summary="Probar compras recurrentes de Nvidia.",
                language="es-419",
                strategy_type="dca_accumulation",
                strategy_thesis="Comprar $250 de Nvidia cada semana.",
                asset_universe=["NVDA"],
                asset_class="equity",
                capital_amount=250,
                recurring_contribution=250,
                cadence="weekly",
                date_range_raw_text="durante el último año",
                date_range_intent=interpreter_module.LLMDateRangeIntent(
                    kind="rolling_window",
                    count=1,
                    unit="year",
                    anchor="today",
                    confidence=0.92,
                    evidence="durante el último año",
                ),
                confidence=0.91,
                evidence_spans={
                    "asset_universe": "Nvidia",
                    "recurring_contribution": "$250",
                    "cadence": "cada semana",
                    "date_range": "durante el último año",
                },
            )
        raise AssertionError(f"Unexpected schema {schema_name}")

    monkeypatch.setattr(interpreter_module, "resolve_asset", resolve_asset)
    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        audit_stub,
    )

    response = LLMInterpretationResponse(
        intent="unsupported_or_out_of_scope",
        task_relation="new_task",
        requires_clarification=True,
        user_goal_summary=(
            "¿Qué habría pasado si compraba $250 de Nvidia cada semana durante el último año?"
        ),
        assistant_response="Las compras recurrentes no están disponibles.",
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing=(
                "¿Qué habría pasado si compraba $250 de Nvidia cada semana durante el último año?"
            ),
            strategy_thesis=(
                "¿Qué habría pasado si compraba $250 de Nvidia cada semana durante el último año?"
            ),
            asset_universe=["NVDA"],
            asset_class="equity",
            date_range={"start": "2025-06-13", "end": "2026-06-13"},
        ),
        unsupported_constraints=[
            interpreter_module.LLMUnsupportedConstraint(
                category="unsupported_strategy_logic",
                raw_value=(
                    "¿Qué habría pasado si compraba $250 de Nvidia cada semana durante el último año?"
                ),
                explanation="The model over-routed a supported DCA request.",
                simplification_labels=["dca_accumulation"],
            )
        ],
        missing_required_fields=["entry_logic", "asset_universe", "exit_logic"],
        semantic_turn_act="unsupported_request",
        artifact_target="none",
    )

    ready_response = await interpreter_module._response_ready_for_runtime(
        response=response,
        preferred_model="test-model",
        request=InterpretationRequest(
            current_user_message=(
                "¿Qué habría pasado si compraba $250 de Nvidia cada semana durante el último año?"
            ),
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1", language_preference="es-419"),
        ),
    )

    assert "SupportedStrategyCapabilityConflictAudit" in calls
    assert "FocusedStrategyExtraction" in calls
    assert calls.index("SupportedStrategyCapabilityConflictAudit") < calls.index(
        "FocusedStrategyExtraction"
    )
    assert ready_response.intent == "backtest_execution"
    assert ready_response.requires_clarification is False
    assert ready_response.assistant_response is None
    assert ready_response.missing_required_fields == []
    draft = ready_response.candidate_strategy_draft
    assert draft.strategy_type == "dca_accumulation"
    assert draft.asset_universe == ["NVDA"]
    assert draft.recurring_contribution == 250
    assert draft.capital_amount == 250
    assert draft.cadence == "weekly"


@pytest.mark.asyncio
async def test_vague_guidance_does_not_preempt_focused_strategy_extraction(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    def resolve_asset(query: str) -> ResolvedAssetStub:
        normalized = query.strip().upper()
        if normalized in {"NVIDIA", "NVDA"}:
            return ResolvedAssetStub(
                "NVDA",
                "equity",
                name="NVIDIA Corporation",
                raw_symbol=query,
            )
        raise ValueError("invalid_symbol")

    calls: list[str] = []

    async def audit_stub(**kwargs):
        schema_name = kwargs["schema_name"]
        calls.append(schema_name)
        if schema_name == "FocusedStrategyExtraction":
            return interpreter_module.FocusedStrategyExtraction(
                is_testable_strategy=True,
                requires_clarification=False,
                user_goal_summary="Probar compras recurrentes de Nvidia.",
                language="es-419",
                strategy_type="dca_accumulation",
                strategy_thesis="Comprar $250 de Nvidia cada semana.",
                asset_universe=["NVDA"],
                asset_class="equity",
                capital_amount=250,
                recurring_contribution=250,
                cadence="weekly",
                date_range_raw_text="durante el último año",
                date_range_intent=interpreter_module.LLMDateRangeIntent(
                    kind="rolling_window",
                    count=1,
                    unit="year",
                    anchor="today",
                    confidence=0.92,
                    evidence="durante el último año",
                ),
                confidence=0.91,
                evidence_spans={
                    "asset_universe": "Nvidia",
                    "recurring_contribution": "$250",
                    "cadence": "cada semana",
                    "date_range": "durante el último año",
                },
            )
        raise AssertionError(f"Unexpected schema {schema_name}")

    monkeypatch.setattr(interpreter_module, "resolve_asset", resolve_asset)
    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        audit_stub,
    )

    response = LLMInterpretationResponse(
        intent="strategy_drafting",
        task_relation="new_task",
        requires_clarification=False,
        user_goal_summary="El usuario quiere probar una idea de inversión.",
        candidate_strategy_draft=LLMStrategyDraft(
            raw_user_phrasing=(
                "¿Qué habría pasado si compraba $250 de Nvidia cada semana durante el último año?"
            ),
            strategy_thesis=(
                "¿Qué habría pasado si compraba $250 de Nvidia cada semana durante el último año?"
            ),
        ),
        missing_required_fields=[],
        semantic_turn_act="new_idea",
        artifact_target="none",
    )

    ready_response = await interpreter_module._response_ready_for_runtime(
        response=response,
        preferred_model="test-model",
        request=InterpretationRequest(
            current_user_message=(
                "¿Qué habría pasado si compraba $250 de Nvidia cada semana durante el último año?"
            ),
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1", language_preference="es-419"),
        ),
    )

    assert "FocusedStrategyExtraction" in calls
    assert "vague_strategy_start_guidance" not in ready_response.reason_codes
    assert ready_response.intent == "backtest_execution"
    draft = ready_response.candidate_strategy_draft
    assert draft.strategy_type == "dca_accumulation"
    assert draft.asset_universe == ["NVDA"]
    assert draft.recurring_contribution == 250
    assert draft.cadence == "weekly"


@pytest.mark.asyncio
async def test_explicit_model_timeout_churn_does_not_invent_strategy_ownership(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    class TimeoutStructuredModel:
        async def ainvoke(self, _messages):
            raise TimeoutError("structured model timed out")

    class TimeoutChatModel:
        def with_structured_output(self, _schema):
            return TimeoutStructuredModel()

    build_calls: list[str] = []
    repair_calls: list[str] = []

    def build_model(_task, *, model_name=None):
        build_calls.append(str(model_name))
        return TimeoutChatModel()

    def resolve_model(model_name=None, fallback=False, *, task=None):
        del task
        if model_name:
            return str(model_name)
        return "fallback/model" if fallback else "primary/model"

    def resolve_asset(query: str) -> ResolvedAssetStub:
        normalized = query.strip().upper()
        if normalized in {"NVIDIA", "NVDA"}:
            return ResolvedAssetStub(
                "NVDA",
                "equity",
                name="NVIDIA Corporation",
                raw_symbol=query,
            )
        raise ValueError("invalid_symbol")

    async def repair_schema(**kwargs):
        repair_calls.append(kwargs["schema_name"])
        raise AssertionError("An unread turn must not enter focused strategy repair")

    monkeypatch.setenv("CUADRAO_STRUCTURED_MODEL", "primary/model")
    monkeypatch.setenv("CUADRAO_STRUCTURED_FALLBACK_MODEL", "fallback/model")
    monkeypatch.setattr(interpreter_module, "build_openrouter_model", build_model)
    monkeypatch.setattr(interpreter_module, "resolve_asset", resolve_asset)
    monkeypatch.setattr(
        "argus.llm.openrouter.resolve_openrouter_model",
        resolve_model,
    )
    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        repair_schema,
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract(),
        model_name="primary/model",
    )
    result = await interpreter.ainvoke(
        InterpretationRequest(
            current_user_message=(
                "What if I bought $250 of Nvidia every week during the last year?"
            ),
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        )
    )

    assert build_calls == ["primary/model", "fallback/model"]
    assert repair_calls == []
    assert result is None
    assert interpreter.last_status == "failed"


@pytest.mark.asyncio
async def test_explicit_model_timeout_churn_does_not_repair_nonmaterial_refinement(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter as interpreter_module

    class TimeoutStructuredModel:
        async def ainvoke(self, _messages):
            raise TimeoutError("structured model timed out")

    class TimeoutChatModel:
        def with_structured_output(self, _schema):
            return TimeoutStructuredModel()

    repair_calls: list[str] = []

    def build_model(_task, *, model_name=None):
        del model_name
        return TimeoutChatModel()

    def resolve_model(model_name=None, fallback=False, *, task=None):
        del task
        if model_name:
            return str(model_name)
        return "fallback/model" if fallback else "primary/model"

    async def repair_schema(**kwargs):
        repair_calls.append(kwargs["schema_name"])
        raise AssertionError("non-material refinement should not reach repair schema")

    monkeypatch.setenv("CUADRAO_STRUCTURED_MODEL", "primary/model")
    monkeypatch.setenv("CUADRAO_STRUCTURED_FALLBACK_MODEL", "fallback/model")
    monkeypatch.setattr(interpreter_module, "build_openrouter_model", build_model)
    monkeypatch.setattr(
        "argus.llm.openrouter.resolve_openrouter_model",
        resolve_model,
    )
    monkeypatch.setattr(
        interpreter_module,
        "invoke_openrouter_json_schema",
        repair_schema,
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract(),
        model_name="primary/model",
    )
    result = await interpreter.ainvoke(
        InterpretationRequest(
            current_user_message="Actually make it Nvidia.",
            recent_thread_history=[],
            latest_task_snapshot=TaskSnapshot(
                pending_strategy_summary=StrategySummary(
                    raw_user_phrasing="Test buying and holding Apple over the past year.",
                    strategy_type="buy_and_hold",
                    strategy_thesis="Test buying and holding Apple over the past year.",
                    asset_universe=["AAPL"],
                    asset_class="equity",
                    date_range="last 1 year",
                )
            ),
            user=UserState(user_id="u1"),
        )
    )

    assert result is None
    assert repair_calls == []
    assert interpreter.last_status == "failed"
