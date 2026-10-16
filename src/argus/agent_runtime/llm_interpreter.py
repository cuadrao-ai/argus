# ruff: noqa: F401, I001
# This module is now a thin facade over argus.agent_runtime.interpreter.*; it
# re-exports relocated symbols and preserves its full original import surface so
# external callers/tests that access ``llm_interpreter.<name>`` keep working.
from __future__ import annotations

import asyncio
import json
import time

from argus.agent_runtime.business.interpreter import BusinessInterpreterMethods
from datetime import date
from functools import partial
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from loguru import logger

from argus.domain.market_data.new_york_clock import new_york_today
from argus.agent_runtime.history import select_thread_history
from argus.agent_runtime.artifact_edit_planner import (  # noqa: F401
    _apply_legacy_flat_edit_fields,
    _edit_plan_reshapes_non_recurring_strategy,
    plan_artifact_assumption_edit,
)
from argus.agent_runtime.discovery.prompt_guidance import DISCOVERY_ACT_GUIDANCE
from argus.agent_runtime.interpreter.discovery_act_guard import (
    discovery_response_ready_for_runtime,
    preserve_typed_discovery_act,
    response_without_unroutable_discovery_payload,
)
from argus.agent_runtime.interpreter.discovery_focused_read import (
    focused_discovery_payload_response,
)
from argus.agent_runtime.interpreter.research_routing import primary_research_query
from argus.agent_runtime.interpreter.repair_observability import (
    repair_effect_metadata,
)
from argus.domain.research.config import research_rail_enabled
from argus.agent_runtime.interpreter.benchmark_prompt_guidance import (
    BENCHMARK_LANGUAGE_GUIDANCE,
)
from argus.agent_runtime.asset_text_grounding import (
    grounded_asset_mention_has_name_support,
    grounded_asset_mentions_from_text,
)
from argus.agent_runtime.benchmark_evidence import (
    current_message_has_extra_provider_asset_for_benchmark,
    provider_ticker_assets_from_text,
)
from argus.agent_runtime.capabilities.contract import CapabilityContract
from argus.agent_runtime.interpreter.artifact_assumption_edit import (  # noqa: F401
    ARTIFACT_EDIT_PENDING_FIELDS,
    _apply_resolved_edit_to_draft,
    _current_artifact_asset_universe,
    _current_artifact_strategy,
    _normalized_ticker_symbol,
    _request_targets_pending_artifact_assumption_edit,
    _scoped_date_reply_carries_broader_edit,
    _request_targets_post_result_artifact_edit,
    _required_edit_targets_from_primary_draft,
    _response_from_artifact_assumption_edit_plan,
    asset_edit_symbol_resolver as _asset_edit_symbol_resolver,
    materialized_artifact_edit_targets,
)
from argus.agent_runtime.interpreter.edit_completion import stated_edit_operations
from argus.agent_runtime.interpreter.asset_grounding import (  # noqa: F401
    _artifact_target_from_response,
    _comparison_baseline_has_trusted_provenance,
    _context_inheritable_asset_symbols,
    _normalized_extracted_symbol,
    _normalized_extracted_symbols,
    _prior_strategy_symbols,
    _provider_exact_ticker_supports_extracted_symbol,
    _requested_asset_answer_candidate_audit_messages,
)
from argus.agent_runtime.interpreter.asset_resolution_context import (
    provider_asset_resolution_context_for_request,
    provider_asset_resolution_context_from_extraction,
)
from argus.agent_runtime.interpreter.audits import (  # noqa: F401
    AssetAnswerCandidateAudit,
    AssetGroundingAudit,
    CapabilitySideQuestionAudit,
    ContextQuestionAudit,
    DcaContractAudit,
    DcaContributionRoleAudit,
    ExecutableStrategyGroundingAudit,
    LatestResultRoutingAudit,
    LatestResultSaveAudit,
    PendingResponseOptionSelectionAudit,
    StatedRunFieldFidelityAudit,
    StatedStartingCapitalAudit,
    StrategyFamilyContinuityAudit,
    SupportedStrategyCapabilityConflictAudit,
)
from argus.agent_runtime.interpreter.capability_context_audits import (  # noqa: F401
    _capability_side_question_audit_messages,
    _context_question_audit_messages,
    _response_had_unsubstantiated_asset_removed,
    _response_needs_context_question_audit,
)
from argus.agent_runtime.interpreter.date_window_repair import (  # noqa: F401
    _clear_auto_simplified_strategy_when_rule_is_ambiguous,
    _response_with_latest_result_window_bound,
    _current_turn_has_relative_window_evidence,
    _date_range_from_current_turn_message,
    _date_range_intent_can_safely_suppress_focused_repair,
    _draft_complete_date_range_matches_current_turn_date_evidence,
    _draft_has_supported_capability_shape_for_date_repair,
    _focused_date_window_extraction_messages,
    _pending_supported_execution_date_answer_can_use_focused_audit,
    _post_result_dateless_execution_draft,
    _response_with_post_result_window_inherited,
    _request_has_pending_date_answer_context,
    _response_from_focused_date_window_extraction,
    _response_has_ambiguous_rule_fields,
    _complete_date_range_matches_resolved_intent,
    _complete_date_range_needs_current_turn_date_audit,
    _response_has_repairable_current_turn_date_gap,
    _response_has_repairable_recovery_date_gap,
    _response_needs_temporal_runtime_repair,
    response_with_recovery_intent_window_materialized,
)
from argus.agent_runtime.interpreter.dca_audits import (  # noqa: F401
    _capability_required_missing_fields_for_canonical_strategy,
    _dca_contract_audit_messages,
    _dca_contract_missing_fields,
    _dca_contribution_role_audit_messages,
    _dca_draft_has_recurring_amount,
    _dca_total_budget_source,
    _move_dca_total_budget_out_of_recurring_amount,
    total_budget_audited_response,
    _response_from_dca_contract_audit,
    _response_needs_dca_contribution_role_audit,
    _response_needs_strategy_family_continuity_audit,
    _strategy_family_continuity_audit_messages,
)
from argus.agent_runtime.interpreter.draft_shape import (  # noqa: F401
    _elapsed_ms,
    _refinement_reply_needs_full_interpretation,
    strategy_has_execution_evidence,
    _llm_signal_strategy_is_underfilled,
    _llm_strategy_draft_has_executable_shape,
    _llm_strategy_draft_has_structural_execution_fields,
    _llm_strategy_draft_has_structured_rule_or_indicator_fields,
    _llm_strategy_draft_has_supported_artifact_assumption_edit,
    _llm_strategy_draft_has_unstructured_strategy_text,
    _material_strategy_updates_from_draft,
    _normalized_material_date_range_payload,
    _normalized_material_strategy_value,
    _request_has_active_strategy_context,
    _request_has_failed_action_launch_payload,
    _request_has_latest_result,
    _response_replays_prior_strategy_without_current_turn_update,
    _response_underfills_active_artifact_assumption_edit,
    _response_underfills_active_artifact_rule_edit,
    _response_underfills_pending_result_refinement,
    _structured_strategy_missing_fields_can_clarify,
)
from argus.agent_runtime.interpreter.executable_grounding import (  # noqa: F401
    _draft_has_non_executable_timeframe_label,
    _draft_uses_launch_default_window,
    _executable_strategy_grounding_messages,
    _response_from_executable_strategy_grounding_audit,
    _response_needs_executable_strategy_grounding_audit,
    _response_needs_launch_field_fidelity_repair,
)
from argus.agent_runtime.interpreter.focused_extraction import (  # noqa: F401
    focused_stated_field_audit_guard,
    retain_pending_focused_seed,
    response_from_focused_strategy_extraction,
    strategy_extraction_repair_is_allowed,
    _base_response_was_unsupported,
    _comparison_baseline_provenance,
    _focused_artifact_edit_messages,
    _focused_extraction_field_provenance,
    _focused_strategy_extraction_messages,
    _merge_focused_repair_with_base,
    _openrouter_wire_messages,
)
from argus.agent_runtime.interpreter.execution_cost_capability import (
    execution_cost_capability_clause,
    has_execution_cost_candidate,
)
from argus.agent_runtime.interpreter.unsupported_admission import (
    future_test_window_capability_clause,
    requested_strategy_template_capability_clause,
)
from argus.agent_runtime.interpreter.pending_option import (  # noqa: F401
    _apply_pending_response_option_replacement,
    _clear_dca_recurring_fields,
    _clear_dca_total_budget_fields,
    _llm_draft_from_strategy_summary,
    _missing_fields_after_pending_option,
    _pending_response_intent_options,
    _pending_response_option_selection_audit_messages,
    _pending_strategy_draft_from_request_or_response,
    _response_from_pending_response_option_selection_audit,
    _response_needs_pending_response_option_selection_audit,
)
from argus.agent_runtime.interpreter import asset_grounding, provider_context_assets
from argus.agent_runtime.interpreter import (
    requested_asset_answer as _requested_asset_answer,
)
from argus.agent_runtime.interpreter.readiness_helpers import (  # noqa: F401
    _active_artifact_asset_universe_operation_needs_planner,
    _asset_universe_operation_clarification_response,
    _bare_asset_answer_without_unevidenced_operation,
    _log_runtime_readiness_step,
    _plain_requested_asset_answer_can_use_provider_resolution,
)
from argus.agent_runtime.interpreter.run_field_audits import (  # noqa: F401
    _clear_rule_or_indicator_fields,
    _date_evidence_tokens_from_text,
    _dca_response_needs_semantic_field_audit,
    _draft_capital_needs_stated_run_field_audit,
    _draft_contains_structured_capital_context,
    _draft_date_evidence_tokens,
    _draft_date_range_has_unstated_current_endpoint,
    _draft_date_range_needs_stated_run_field_audit,
    _draft_has_non_money_execution_anchor,
    _draft_has_timeframe_evidence_for_audit,
    _draft_has_unprovenanced_benchmark,
    _draft_non_capital_numeric_evidence_tokens,
    _explicit_benchmark_ticker_queries,
    _focused_repair_capital_needs_stated_run_field_audit,
    _latest_result_fact_bank_for_routing,
    _latest_result_routing_audit_messages,
    _pending_dca_assumption_reply_needs_stated_run_field_audit,
    _resolved_runtime_date_range_from_draft,
    _response_from_current_message_run_field_contract,
    _response_from_stated_run_field_fidelity_audit,
    _response_has_pending_base_field,
    _response_needs_current_message_date_repair,
    _response_needs_latest_result_routing_audit,
    _response_needs_missing_benchmark_fidelity_audit,
    _response_needs_supported_strategy_capability_conflict_audit,
    _response_targets_latest_result_followup,
    _response_with_executable_fields_preferred_over_clarification_prose,
    _response_with_resolved_runtime_date_range,
    _response_with_supported_strategy_capability_conflict_removed,
    _stated_run_field_audit_omitted_expected_fields,
    _stated_run_field_fidelity_messages,
    _structured_draft_context_text,
    _structured_supported_strategy_capability_conflict_fallback,
    _supported_strategy_capability_conflict_messages,
    _text_contains_capital_audit_signal,
)
from argus.agent_runtime.interpreter.shared import (  # noqa: F401
    _COMPARISON_BASELINE_EVIDENCE_KEYS,
    _DATE_EVIDENCE_SPAN_KEYS,
    _EXECUTABLE_TIMEFRAMES,
    _RECURRING_CAPITAL_SOURCES,
    _TOTAL_CAPITAL_SOURCES,
    _bounded_date_evidence_candidates,
    _capital_source,
    _date_range_audit_has_partial_endpoint,
    _date_range_from_bounded_evidence,
    _date_range_from_intent_or_bounded_evidence,
    _date_range_with_fidelity_audit,
    _date_value_is_less_specific,
    _draft_has_comparison_baseline_evidence,
    _draft_has_semantic_date_window_evidence,
    _draft_semantic_evidence_spans,
    _field_path_base,
    _has_complete_date_range_payload,
    _llm_strategy_draft_has_concrete_execution_target,
    _llm_strategy_draft_has_extractable_fields,
    _llm_strategy_draft_has_rule_or_indicator_fields,
    _llm_value_is_empty,
    _natural_time_language_candidates_from_hints,
    _normalized_stated_field,
    _latest_result_date_window,
    _selected_requested_field_base,
    _supported_dca_cadence_value,
    repaired_turn_act,
)
from argus.agent_runtime.interpreter.signal_rule import (  # noqa: F401
    _asset_recovery_query_is_explicit_ticker,
    crossover_shorthand_prompt_clause,
    _audit_signal_rule_grounding_if_needed,
    _llm_draft_executable_indicator_spec,
    _llm_strategy_draft_has_non_asset_strategy_anchor,
    _pending_signal_rule_planning_response,
    _prior_strategy_payload,
    _request_targets_pending_signal_rule,
    _response_from_signal_grounding_audit,
    _response_from_signal_rule_plan,
    _response_has_signal_rule_shape,
    _response_needs_indicator_default_grounding_repair,
    _response_needs_indicator_parameter_repair,
    _response_needs_signal_rule_grounding_audit,
    _response_needs_signal_rule_plan,
    _response_needs_supported_signal_rule_recovery,
    _signal_rule_plan_raw_value,
    _signal_rule_planning_context_from_prior,
    _supported_signal_rule_planning_response,
)
from argus.agent_runtime.interpreter import simplification_options as _options
from argus.agent_runtime.interpreter.latest_result_context import latest_result_interpreter_context
from argus.agent_runtime.interpreter.starting_capital import (  # noqa: F401
    _draft_has_grounded_non_dca_starting_capital,
    _focused_strategy_extraction_has_material_fields,
    _response_from_stated_starting_capital_audit,
    _response_needs_stated_starting_capital_recheck,
    _starting_capital_prose_evidence_payload,
    _stated_starting_capital_messages,
)
from argus.agent_runtime.interpreter.strategy_builder import (  # noqa: F401
    _apply_executable_indicator_defaults,
    _apply_signal_strategy_defaults,
    _clean_date_range_intent_payload,
    _clean_evidence_spans,
    _clean_optional_text,
    _compact_asset_evidence_token,
    _dca_amount_has_user_provenance,
    _dca_cadence_has_user_provenance,
    _dedupe_resolution_provenance,
    _ensure_dca_missing_execution_fields,
    _evidence_backed_field_provenance,
    _field_owned_indicator_asset_candidate,
    _ground_strategy_in_current_turn,
    _grounded_initial_capital,
    _grounded_recurring_contribution,
    _grounded_total_capital,
    _humanize_simplification_label,
    _indicator_key_from_strategy,
    _indicator_parameters_from_strategy,
    _merge_prior_strategy,
    _message_has_cashtag_for_asset,
    _non_dca_starting_capital_from_total_fields,
    _normalize_llm_domain_slots,
    _remove_stale_indicator_constraints,
    _remove_unstated_model_defaults,
    _risk_rule_is_unstated_full_position_default,
    _strategy_from_llm,
    _strategy_has_executable_rule_semantics,
    _strategy_has_explicit_asset_evidence,
    _strategy_has_indicator_parameters,
    _strategy_has_rule_semantics,
    _strategy_uses_rule_or_indicator_context,
    _unsupported_from_llm,
    _validate_indicator_rule_support,
)
from argus.agent_runtime.interpreter.strategy_routing import STRATEGY_TURN_ACTS, route_owner
from argus.agent_runtime.interpreter.strategy_repair_predicates import (  # noqa: F401
    _is_vague_strategy_start,
    _is_vague_strategy_start_guidance,
    _llm_strategy_draft_has_semantic_execution_anchor,
    _response_needs_artifact_context_repair,
    _response_needs_structured_strategy_repair,
    _supported_partial_draft_has_repairable_shape,
    _vague_strategy_start_as_guidance,
)
from argus.agent_runtime.interpreter import contract_recovery
from argus.agent_runtime.llm_interpreter_types import (
    FocusedDateWindowExtraction,
    FocusedStrategyExtraction,
    LLMAssetMentionExtraction,
    LLMAmbiguousField,
    LLMDateRangeIntent,
    LLMInterpretationResponse,
    LLMRiskRule,
    LLMStrategyDraft,
    LLMUnsupportedConstraint,
)
from argus.agent_runtime.presentation_i18n import (
    asset_universe_operation_clarification_message,
)
from argus.agent_runtime.resolution import AssetResolution, callable_accepts_keyword
from argus.agent_runtime.resolution import (
    resolve_asset_candidate as runtime_resolve_asset_candidate,
)
from argus.agent_runtime.run_field_contract import (
    current_message_execution_context_tokens,
    field_fidelity_tokens,
)
from argus.agent_runtime.signal_rule_repair import repair_signal_rule_plan
from argus.agent_runtime.stages.interpret_types import (
    InterpretationRequest,
    StructuredInterpretation,
)
from argus.agent_runtime.state.models import (
    AmbiguousField,
    ResolutionProvenance,
    ResolutionSource,
    StrategySummary,
)
from argus.agent_runtime.strategy_contract import (
    SUPPORTED_STRATEGY_TYPES,
    canonical_strategy_type,
    executable_strategy_type,
    has_partial_explicit_date_range,
    normalize_date_range_candidate,
    resolve_date_range,
    safe_conflict_strategy_type,
)
from argus.agent_runtime import turn_execution
from argus.agent_runtime.semantic_integrity import (
    UNSUPPORTED_DCA_CONTRIBUTION_CEILING,
)
from argus.agent_runtime.turn_execution_evidence import (
    current_turn_has_material_execution_evidence,
)
from argus.domain.market_data import is_ticker_like_query, resolve_asset
from argus.llm.openrouter_retention import OpenRouterZDRUnavailableError
from argus.llm.openrouter import (
    OpenRouterTask,
    annotate_latest_openrouter_route_receipt,
    build_openrouter_model,
    invoke_openrouter_json_schema,
    log_openrouter_failure,
    openrouter_structured_model_candidates,
    openrouter_task_timeout_seconds,
    record_openrouter_route_receipt,
)
from argus.nlp.natural_time import (
    resolve_date_range_intent,
    resolve_date_range_text,
    resolve_rolling_window_intent_text,
)

_carry_asset_blocker = provider_context_assets.carry_incomplete_asset_blocker
_DEFAULT_RESOLVE_ASSET = resolve_asset
_INTERPRETATION_REPAIR_TASK: OpenRouterTask = "interpretation_repair"


def _annotate_interpretation_repair(
    *,
    schema_name: str,
    before: LLMInterpretationResponse,
    after: LLMInterpretationResponse,
    trigger_reason: str,
    repair_applied: bool,
    no_op_reason: str | None = None,
) -> None:
    annotate_latest_openrouter_route_receipt(
        task=_INTERPRETATION_REPAIR_TASK,
        schema_name=schema_name,
        repair_effect=repair_effect_metadata(
            before=before,
            after=after,
            trigger_reason=trigger_reason,
            repair_applied=repair_applied,
            no_op_reason=no_op_reason,
        ),
    )


def _selected_thread_metadata_context(metadata: dict[str, Any]) -> str:
    if not metadata:
        return "none"
    context_keys = (
        "last_stage_outcome",
        "requested_field",
        "requested_fields",
        "artifact_target",
        "chat_action",
        "source_result_run_id",
        "failed_action",
        "response_intent",
    )
    context = {key: metadata[key] for key in context_keys if key in metadata}
    if not context:
        return "none"
    return json.dumps(context, sort_keys=True, default=str)


class OpenRouterStructuredInterpreter(BusinessInterpreterMethods):
    def __init__(
        self,
        *,
        contract: CapabilityContract,
        model_name: str | None = None,
    ) -> None:
        self.contract = contract
        self.model_name = model_name
        self.last_status: str | None = None
        self.last_failure_kind: str | None = None

    def __call__(self, request: InterpretationRequest) -> StructuredInterpretation | None:
        return asyncio.run(self.ainvoke(request))

    async def ainvoke(
        self, request: InterpretationRequest
    ) -> StructuredInterpretation | None:
        self.last_failure_kind, self.correction_attempted = None, False
        candidate_models: list[str] | None = None
        if self.model_name is None:
            candidate_models = openrouter_structured_model_candidates()
            context_model_name = candidate_models[0] if candidate_models else ""
        else:
            context_model_name = self.model_name
        asset_resolution_context = await provider_asset_resolution_context_for_request(
            request=request,
            preferred_model=context_model_name,
            invoke_schema=invoke_openrouter_json_schema,
            resolve_asset_candidate=_resolve_asset_candidate,
        )
        messages = self._messages(
            request,
            asset_resolution_context=asset_resolution_context,
        )
        # The last raw interpretation still names what the user asked to
        # change; the terminal edit-planner fallback needs it so a plan that
        # covers only part of the request cannot be accepted (issue #498).
        last_raw_response: LLMInterpretationResponse | None = None
        if self.model_name is None:
            candidate_models = candidate_models or []
            for index, candidate_model in enumerate(candidate_models):
                try:
                    response = await invoke_openrouter_json_schema(
                        task="interpretation",
                        messages=_openrouter_wire_messages(messages),
                        schema_model=LLMInterpretationResponse,
                        schema_name="LLMInterpretationResponse",
                        model_name=candidate_model,
                    )
                    if not isinstance(response, LLMInterpretationResponse):
                        continue
                    last_raw_response = response.model_copy(deep=True)
                    response = await _response_ready_for_runtime(
                        response=response,
                        preferred_model=candidate_model,
                        request=request,
                        asset_resolution_context=asset_resolution_context,
                    )
                    self.last_status = "used" if index == 0 else "fallback_used"
                    return self._to_runtime_interpretation(response, request=request)
                except OpenRouterZDRUnavailableError:
                    raise
                except Exception as exc:
                    recovered = await contract_recovery.handle_candidate_failure(
                        interpreter=self,
                        exc=exc,
                        is_primary=index == 0,
                        request=request,
                        candidate_model=candidate_model,
                        wire_messages=_openrouter_wire_messages(messages),
                        invoke_schema=invoke_openrouter_json_schema,
                        ready_for_runtime=_response_ready_for_runtime,
                        asset_resolution_context=asset_resolution_context,
                    )
                    if recovered is not None:
                        return recovered
            repaired_response = await _plan_pending_artifact_assumption_edit(
                request=request,
                preferred_model=candidate_models[0] if candidate_models else "",
                require_failure_edit_evidence=True,
                primary_draft=(
                    last_raw_response.candidate_strategy_draft
                    if last_raw_response is not None
                    else None
                ),
            )
            if repaired_response is not None:
                self.last_status = "fallback_used"
                repaired_response = _carry_asset_blocker(
                    repaired_response, asset_resolution_context
                )
                return self._to_runtime_interpretation(repaired_response, request=request)
            repaired_response = await _focused_strategy_repair_after_candidate_failures(
                request=request,
                preferred_model=candidate_models[0] if candidate_models else "",
                asset_resolution_context=asset_resolution_context,
                failed_response=last_raw_response,
            )
            if repaired_response is not None:
                self.last_status = "fallback_used"
                repaired_response = await _stated_run_field_audited_response(
                    response=repaired_response,
                    preferred_model=candidate_models[0] if candidate_models else "",
                    request=request,
                )
                return self._to_runtime_interpretation(repaired_response, request=request)
            self.last_status = "failed"
            return None

        # 1. Try Primary Model
        model = build_openrouter_model("interpretation", model_name=self.model_name)
        if model:
            started_at = time.perf_counter()
            try:
                structured = model.with_structured_output(LLMInterpretationResponse)
                response = await asyncio.wait_for(
                    structured.ainvoke(messages),
                    timeout=openrouter_task_timeout_seconds("interpretation"),
                )
                if isinstance(response, LLMInterpretationResponse):
                    last_raw_response = response.model_copy(deep=True)
                    record_openrouter_route_receipt(
                        task="interpretation",
                        model_name=self.model_name,
                        mode="chat_model",
                        schema_name="LLMInterpretationResponse",
                        latency_ms=_elapsed_ms(started_at),
                        outcome="succeeded",
                    )
                    response = await _response_ready_for_runtime(
                        response=response,
                        preferred_model=self.model_name,
                        request=request,
                        asset_resolution_context=asset_resolution_context,
                    )
                    self.last_status = "used"
                    return self._to_runtime_interpretation(response, request=request)
            except OpenRouterZDRUnavailableError:
                raise
            except Exception as exc:
                contract_recovery.record_legacy_failure(self.model_name, started_at, exc)

        # 2. Try Fallback Model (if primary failed or was unavailable)
        from argus.llm.openrouter import resolve_openrouter_model

        fallback_model_name = resolve_openrouter_model(
            fallback=True, task="interpretation"
        )

        # Don't retry with the same model name if resolve returned the same thing
        primary_model_name = resolve_openrouter_model(
            self.model_name,
            task="interpretation",
        )
        if not fallback_model_name or fallback_model_name == primary_model_name:
            self.last_status = "failed"
            return None

        fallback_model = build_openrouter_model(
            "interpretation", model_name=fallback_model_name
        )
        if fallback_model:
            started_at = time.perf_counter()
            try:
                structured = fallback_model.with_structured_output(
                    LLMInterpretationResponse
                )
                response = await asyncio.wait_for(
                    structured.ainvoke(messages),
                    timeout=openrouter_task_timeout_seconds("interpretation"),
                )
                if isinstance(response, LLMInterpretationResponse):
                    last_raw_response = response.model_copy(deep=True)
                    record_openrouter_route_receipt(
                        task="interpretation",
                        model_name=fallback_model_name,
                        mode="chat_model",
                        schema_name="LLMInterpretationResponse",
                        latency_ms=_elapsed_ms(started_at),
                        outcome="succeeded",
                    )
                    response = await _response_ready_for_runtime(
                        response=response,
                        preferred_model=fallback_model_name,
                        request=request,
                        asset_resolution_context=asset_resolution_context,
                    )
                    self.last_status = "fallback_used"
                    return self._to_runtime_interpretation(response, request=request)
            except OpenRouterZDRUnavailableError:
                raise
            except Exception as exc:
                self.last_status = "failed"
                record_openrouter_route_receipt(
                    task="interpretation",
                    model_name=fallback_model_name,
                    mode="chat_model",
                    schema_name="LLMInterpretationResponse",
                    latency_ms=_elapsed_ms(started_at),
                    outcome="failed",
                    failure_mode=type(exc).__name__,
                )
                log_openrouter_failure(
                    task="interpretation",
                    model_name=fallback_model_name,
                    exc=exc,
                    message="Fallback LLM interpretation failed",
                )

        repaired_response = await _plan_pending_artifact_assumption_edit(
            request=request,
            preferred_model=fallback_model_name or primary_model_name,
            require_failure_edit_evidence=True,
            primary_draft=(
                last_raw_response.candidate_strategy_draft
                if last_raw_response is not None
                else None
            ),
        )
        if repaired_response is not None:
            self.last_status = "fallback_used"
            repaired_response = _carry_asset_blocker(
                repaired_response, asset_resolution_context
            )
            return self._to_runtime_interpretation(repaired_response, request=request)
        repaired_response = await _focused_strategy_repair_after_candidate_failures(
            request=request,
            preferred_model=fallback_model_name or primary_model_name,
            asset_resolution_context=asset_resolution_context,
            failed_response=last_raw_response,
        )
        if repaired_response is not None:
            self.last_status = "fallback_used"
            repaired_response = await _stated_run_field_audited_response(
                response=repaired_response,
                preferred_model=fallback_model_name or primary_model_name,
                request=request,
            )
            return self._to_runtime_interpretation(repaired_response, request=request)
        return None

    def _messages(
        self,
        request: InterpretationRequest,
        *,
        asset_resolution_context: str | None = None,
    ) -> list[BaseMessage]:
        prior_strategy = None
        active_confirmation = None
        latest_result = None
        latest_failed_action = None
        if request.latest_task_snapshot is not None:
            prior_strategy = (
                request.latest_task_snapshot.pending_strategy_summary
                or request.latest_task_snapshot.confirmed_strategy_summary
            )
            if request.latest_task_snapshot.active_confirmation_reference is not None:
                active_confirmation = (
                    request.latest_task_snapshot.active_confirmation_reference.model_dump(
                        mode="json"
                    )
                )
            if request.latest_task_snapshot.latest_backtest_result_reference is not None:
                latest_result = latest_result_interpreter_context(
                    request.latest_task_snapshot.latest_backtest_result_reference
                )
            if request.latest_task_snapshot.latest_failed_action_reference is not None:
                latest_failed_action = request.latest_task_snapshot.latest_failed_action_reference.model_dump(
                    mode="json"
                )
        has_artifact_context = any(
            item is not None
            for item in (
                prior_strategy,
                active_confirmation,
                latest_result,
                latest_failed_action,
            )
        )
        history: list[BaseMessage] = []
        for item in select_thread_history(
            request.recent_thread_history, recent_limit=0 if has_artifact_context else 6
        ):
            content = str(item.content)
            if item.role == "assistant":
                history.append(AIMessage(content=content))
            elif item.role == "user":
                history.append(HumanMessage(content=content))
        asset_context_messages = (
            [
                SystemMessage(
                    content=(
                        "Provider-backed asset resolution context for "
                        "LLM-identified current-message asset candidates. Use this "
                        "only as extraction context: fill asset_universe from the "
                        "resolved traded assets, fill comparison_baseline from "
                        "resolved benchmark assets, and preserve all same-class "
                        "traded assets the user mentioned. If a candidate is "
                        "ambiguous, keep the raw mention in the structured field and "
                        "mark it for clarification instead of guessing. Do not add "
                        "ordinary non-asset words as assets.\n"
                        f"{asset_resolution_context}"
                    )
                )
            ]
            if asset_resolution_context
            else []
        )
        return [
            SystemMessage(content=self._system_prompt()),
            SystemMessage(
                content=(
                    f"User language preference: {request.user.language_preference}.\n"
                    f"Prior strategy JSON, if any: "
                    f"{prior_strategy.model_dump(mode='json') if prior_strategy else 'none'}\n"
                    f"Active confirmation reference JSON, if any: "
                    f"{active_confirmation if active_confirmation else 'none'}\n"
                    f"Latest result fact bank JSON, if any: "
                    f"{json.dumps(latest_result, sort_keys=True) if latest_result else 'none'}\n"
                    + (
                        "When the current message reuses the latest result's "
                        "window ('same time period', 'mismo periodo', 'same "
                        "dates as before', any language), set "
                        "date_range_intent.kind=same_as_latest_result with the "
                        "reference phrase as evidence and leave start/end "
                        "empty; do not copy dates and do not ask for dates. "
                        'Example: "try QQQ at $300 a month from the same time '
                        'period" means date_range_intent={"kind": '
                        '"same_as_latest_result", "evidence": "from the same '
                        'time period"} plus the asset and contribution '
                        "changes.\n"
                        if latest_result
                        else ""
                    )
                    + f"Latest failed action JSON, if any: "
                    f"{latest_failed_action if latest_failed_action else 'none'}\n"
                    f"Selected thread metadata JSON, if any: "
                    f"{_selected_thread_metadata_context(request.selected_thread_metadata)}"
                )
            ),
            *asset_context_messages,
            *history,
            HumanMessage(content=request.current_user_message),
        ]

    def _system_prompt(self) -> str:
        return (
            "You are Argus's conversational interpretation layer for an AI-first "
            "investing idea validation product. Interpret the user's natural language "
            "and return structured JSON only through the schema. Do not execute. "
            "Do not invent support. Preserve the user's raw phrasing and normalized "
            "meaning. Use prior strategy state for corrections like 'weekly instead', "
            "'use Nvidia instead', 'keep everything else', and 'sell all'.\n\n"
            "Language-agnostic contract: users may speak English, Spanish, or another "
            "language. Always return canonical internal values for executable fields "
            "such as strategy_type, asset_class, cadence, timeframe, indicator, "
            "semantic_turn_act, artifact_target, and result_followup_focus; do not "
            "translate those machine fields. Put the detected user language in "
            "detected_user_language for every turn and in candidate_strategy_draft.language when "
            "a strategy draft is present. Put the exact bounded date/window phrase in candidate_strategy_draft.date_range_raw_text. For relative "
            "or semantic time windows, also fill candidate_strategy_draft."
            "date_range_intent with canonical fields: kind=rolling_window with "
            "count/unit where count keeps a stated fractional quantity exactly "
            "(the last 8.5 months means count=8.5, never 8 or 5), "
            "kind=year_to_date with optional year, kind=calendar_year "
            "with year, kind=since with start/year, kind=explicit_range with "
            "ISO start/end, kind=endpoint_patch with endpoint plus ISO date or "
            "anchor=today and day_offset for relative day edits, or "
            "kind=future_window with count/unit or year when the period points "
            "forward from today. When the user "
            "asks for the same window as the latest completed test, in any "
            "language ('same time period', 'mismo periodo', 'same dates as "
            "before'), set kind=same_as_latest_result with the reference phrase "
            "as evidence and leave start/end empty; the runtime binds the dates "
            "from the canonical result. Do not translate "
            "these machine fields. A user-stated relative lookback anchored to the "
            "present is already a complete temporal constraint; do not ask for "
            "calendar endpoints only because the user used natural language instead "
            "of ISO dates. Also record "
            "short evidence_spans for extracted fields such as strategy_type, "
            "asset_universe, date_range, capital_amount, cadence, and "
            "comparison_baseline. Use date_range for canonical dates only when you "
            "are confident; deterministic date parsing, intent date math, and validation run after this "
            "schema. Write assistant_response in the resolved product language "
            "from the user language preference unless the user explicitly asks "
            "to switch languages. Detected input language is metadata for "
            "interpretation, not the rendering contract. Treat short, "
            "messy, or grammatically imperfect follow-ups as normal user input, not "
            "malformed requests; extract supported strategy intent, asset evidence, "
            "date/window intent, and language when those facts are visible.\n\n"
            + requested_strategy_template_capability_clause()
            + "Supported execution truth for Alpha: long-only backtests; buy_and_hold, "
            "dca_accumulation, registry-backed indicator threshold rules, and "
            "schema-backed signal strategies are executable. RSI is executable with "
            "user-specified thresholds from 0 to 100, a default period of 14, a "
            "default entry threshold of 30, and a default exit threshold of 55 when "
            "the user leaves one side unspecified. SMA and EMA crossovers, MACD "
            "crossing signal, price versus SMA/EMA/Bollinger Bands, and simple "
            "volume-above-volume-SMA confirmations are executable when you provide a "
            "complete rule_spec. Incomplete indicator ideas and indicators without an "
            "executable registry spec can be understood and drafted, but are not "
            "runnable until the missing entry and exit semantics are supplied. "
            "Same asset class only; max 5 symbols; equity benchmark is SPY; crypto benchmark is BTC; "
            "currency pairs are supported through Kraken; currency pair benchmark is the tested "
            "pair itself. "
            + execution_cost_capability_clause()
            + BENCHMARK_LANGUAGE_GUIDANCE
            + "When the user gives exact start/end dates, "
            "preserve them as date_range {'start':'YYYY-MM-DD','end':'YYYY-MM-DD'}; "
            "never replace them with past year, last year, or another default period. "
            f"The current runtime date is {new_york_today().isoformat()}; if the user "
            "says today, now, or current, preserve that endpoint as 'today' or the "
            "current runtime date, not a stale model date.\n\n"
            + crossover_shorthand_prompt_clause()
            + "Do not turn vague momentum language such as 'starts rising', 'big drops', "
            "'breaks out', or 'looks strong' into a moving-average crossover or any "
            "other executable signal by yourself. If the user does not name the "
            "indicator, threshold, crossover, or price rule, mark the entry rule as "
            "missing or ask for the executable definition.\n\n"
            + future_test_window_capability_clause()
            + "Valuation and fundamental language is valid investing intent, not user "
            "error. Whether a stock is cheap, expensive or fairly valued, and what "
            "its P/E, earnings, revenue, margins or fundamentals say, is a research "
            "question: fill research_query and let it be answered; do not steer it "
            "toward a backtest. Only when the user wants to test a rule built on "
            "valuation or fundamentals (buy when the P/E is under 15) does the "
            "engine boundary apply: it cannot execute valuation or fundamental data "
            "as entry/exit rules, so preserve the meaning, say so in product "
            "language, and offer a supported proxy such as buy-and-hold, DCA, an RSI "
            "threshold, or a moving-average/signal rule over the period they care about.\n\n"
            "Use data-availability allowances as deterministic capability truth. "
            "Do not invent a history limit or a start year for any asset, such as a "
            "3-year limit for equities; deterministic validation owns each asset's "
            "available window. Currency-pair "
            "intraday history has a bounded recent-data window, and this launch path "
            "supports 1h, 4h, or 1D for currency-pair tests. Let deterministic "
            "validation decide the exact runnable window. If the user asks for an "
            "hourly/intraday timeframe or a long historical window, preserve those "
            "requested fields in the structured draft; do not silently widen the "
            "timeframe, shorten the dates, or reshape the request to make it runnable. "
            "Validation and recovery will ask for an available window when needed. "
            "Keep provider names, "
            "candle counts, and provider plumbing out of user-facing language; "
            "translate those facts into product capability wording.\n\n"
            "NLU ownership: you are the only intent and extraction layer. "
            "Extract symbols, company names, crypto assets, and currency pairs, date ranges, "
            "DCA cadence, recurring contribution amount, entry logic, exit logic, and "
            "refinement targets from the user message and thread context. Do not rely on "
            "backend text-pattern extraction. If the user writes a company name like Tesla or "
            "Bitcoin, put that text or the ticker in asset_universe; the deterministic "
            "validator will canonicalize it with the market data resolver. When the "
            "user lists several company or asset names as things to buy, hold, test, "
            "or include, preserve every mentioned traded asset in asset_universe; "
            "do not collapse a same-class basket to only the last or most familiar "
            "name. This applies to buy_and_hold, recurring buys, indicator ideas, "
            "and supported signal strategies. "
            "For any strategy_drafting or backtest_execution request, always include "
            "candidate_strategy_draft and fill the extractable fields you can see: "
            "strategy_type, strategy_thesis, asset_universe, date_range, entry_logic, "
            "exit_logic, and structured indicator or rule fields when present. "
            "Do not return an empty candidate_strategy_draft for a testable investing "
            "idea. Normal curiosity such as 'what if I bought/held/owned a company, "
            "ticker, crypto asset, or currency pair' is a testable investing idea, "
            "not a capability or education question; classify it as new_idea and "
            "extract the asset and strategy draft before asking only for truly missing "
            "run facts. "
            "For indicator threshold rules, put the indicator key in indicator, "
            "the lookback in indicator_period when supplied, and numeric threshold "
            "overrides in entry_threshold and exit_threshold. Also preserve readable "
            "entry_logic and exit_logic, but do not rely on prose alone for executable "
            "indicator parameters. If the user says 'RSI entry at 20 and exit at 60', "
            "set indicator='rsi', entry_threshold=20, exit_threshold=60, and leave "
            "indicator_period null unless the user gave a period. "
            "For executable signal strategies, populate rule_spec when the user gives "
            "a complete generic condition group. A rule_spec has entry and exit groups, "
            "each with conditions using left/operator/right operands. Use it for MACD "
            "crossing signal, Bollinger Band touches, price versus indicator, and "
            "volume confirmation. For moving-average crossovers you may also populate "
            "entry_rule and exit_rule as typed JSON. Moving-average crossovers must use "
            "{'type':'moving_average_crossover','fast_indicator':'sma'|'ema',"
            "'fast_period':number,'slow_indicator':'sma'|'ema','slow_period':number,"
            "'direction':'bullish'|'bearish'}. If the user leaves exit unspecified, "
            "you may omit exit_rule and deterministic validation will derive the "
            "opposite crossover from entry_rule. "
            "For non-recurring buy-and-hold or backtest requests, any explicit "
            "cash amount that the user says to use, test, invest, allocate, or "
            "start with belongs in capital_amount as the starting capital, "
            "normalized as a number, with field_provenance.capital_amount="
            "'starting_capital'. This is language-agnostic: phrases equivalent "
            "to 'with 10000 dollars' or 'con 10000 dolares' are complete capital "
            "evidence for a buy_and_hold request. Do not leave capital_amount "
            "null or put this amount only in total_capital/initial_capital for "
            "non-DCA runs. "
            "For natural periods, return date_range as a normalized string when exact dates "
            "are not available, or as {'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD'} when the "
            "user provides exact dates. For recurring buys, extract cadence as daily, weekly, "
            "biweekly, monthly, or quarterly and never invent capital_amount. For DCA, "
            "capital_amount means "
            "the recurring contribution, and the two other money roles have one field "
            "each. Money the user puts in at the start goes in initial_capital. "
            "Money that caps the whole plan, a total budget, an available-cash "
            "ceiling, or a maximum invested, goes in total_capital. These are "
            "different facts with different outcomes, so never put one in the "
            "other's field: a starting amount is executed, a cap is not. If the "
            "user gives a starting amount and a recurring contribution, set "
            "capital_amount and initial_capital. If the user gives only a total "
            "budget, leave capital_amount null and set total_capital. When you set "
            "a recurring capital_amount, set "
            "field_provenance.capital_amount='recurring_contribution' only if the user "
            "explicitly stated that recurring contribution in the message; use "
            "'starting_capital' when the number is money put in at the start and "
            "'total_capital' when it is a budget or cap. When you set cadence, set "
            "field_provenance.cadence='explicit_user' only when the user explicitly "
            "stated the purchase schedule in the current message or visible active "
            "draft context. Never infer monthly from a multi-year date range.\n\n"
            "If the user explicitly asks, in their language, for a simple buy-and-hold "
            "investment test, classify it as buy_and_hold even when the sentence also "
            "contains a start date. "
            "A start date is the backtest period, not entry logic. If you set "
            "strategy_type to buy_and_hold or dca_accumulation, do not also add "
            "unsupported_strategy_logic unless the user asked for an additional "
            "entry rule, exit rule, fundamental rule, sentiment/news/event rule, "
            "custom script, brokerage action, shorting, or another unsupported "
            "condition beyond that supported strategy. Preserve those extra rules "
            "in entry_logic, exit_logic, or strategy_thesis when they exist so a "
            "later audit can distinguish supported strategy intent from unsupported "
            "custom logic.\n\n"
            "Clarify only when required meaning is missing, genuinely ambiguous, "
            "or unsupported in a way that requires the user to choose a simplification. "
            "Starting capital, timeframe, benchmark, fees, and slippage have safe defaults; "
            "do not ask for them before confirmation unless the user explicitly wants to change them. "
            "Safe defaults are only for missing fields. If the user states a timeframe, "
            "date window, capital amount, benchmark, fee, slippage, cadence, or indicator "
            "threshold, preserve that user-stated field even when it will need deterministic "
            "validation or recovery before it can run. "
            "For DCA or recurring-buy plans, the recurring contribution amount is not a "
            "safe default. Do not invent it; if the user does not provide the amount and "
            "there is no prior strategy amount to preserve, leave capital_amount null and "
            "mark the amount as missing. "
            "For product questions or education, set assistant_response; do not force a backtest. Keep prose concise, no emoji, no decorative markdown, "
            "and no generic chatbot openers. For unsupported requests, acknowledge the understood "
            "intent, explain the limitation, and offer executable simplifications. "
            "For simplification choices, put executable meaning in canonical "
            "replacement_values; labels are display-only.\n\n"
            "semantic_turn_act is the routing source of truth. Use approval when the "
            "user clearly approves a pending confirmation; in that case set intent to "
            "backtest_execution, task_relation to continue, requires_clarification to "
            "false, and preserve the prior strategy. Use refine_current_idea when the "
            "user asks to change dates, assets, assumptions, timeframe, capital, or "
            "strategy details, and ask only for the changed missing detail. Use new_idea "
            "for a fresh testable idea, answer_pending_need when the user answers the "
            "latest missing fact, educational_question for product or investing concept "
            "questions, result_followup for questions about the latest completed run, "
            + DISCOVERY_ACT_GUIDANCE
            + "When semantic_turn_act is result_followup, set result_followup_focus to "
            "the closest value: why_underperformed, max_drawdown, drawdown_date, "
            "peak_date, peak_value, result_card_fact, what_tested, "
            "next_experiment, assumptions, or general. Use peak_date when the user "
            "asks when the latest result reached its highest value, peak_value when "
            "they ask what that highest value was, drawdown_date when they ask when "
            "the largest drawdown bottomed, and result_card_fact when they ask for "
            "another factual value shown on the latest result card. For any factual "
            "result question, set result_followup_fact_key to the canonical "
            "snake_case key of that value (schema list, or the metric's plain "
            "snake_case name); cost questions use fee_bps, slippage_bps, gross_total_return, "
            "net_total_return, return_drag, or benchmark_cost_treatment. Leave it unset otherwise. "
            "result_followup only asks what a value was. A request to change, set, "
            "use, or try a different value is an edit: classify it "
            "refine_current_idea even when it names a result-card fact such as "
            "starting capital, and even immediately after a fact question was "
            "answered. Never set result_followup_fact_key on a change request. "
            "Short imperative test asks after a completed result — such as "
            "'Test a different date range', 'Test the same setup on a similar "
            "asset', 'Probar otro rango de fechas', or 'Comparar con comprar y "
            "mantener' — are NEW experiment requests, not questions about the "
            "last run: classify them refine_current_idea (or the matching "
            "edit), ask for the one missing detail when needed, and never "
            "answer them with a result recap. "
            "Result follow-ups must be answered from the latest result facts supplied to the runtime; do not "
            "invent metrics. Use why_underperformed for any why/how the result happened "
            "or other performance "
            "question, including phrases like 'why did this result happen', even "
            "when the run actually outperformed; the answer layer will correct false "
            "underperformance premises from the facts. Use next_experiment when "
            "the user asks what to try next, what else to test, next steps, what "
            "to change, or how to refine the latest result. Assumption questions "
            "about a visible confirmation should set semantic_turn_act="
            "result_followup and result_followup_focus=assumptions even when no "
            "completed run exists; use the active confirmation/card context instead of "
            "regenerating a new card. If the user asks to save, keep, bookmark, "
            "or promote the latest completed result, set semantic_turn_act="
            "result_followup, result_followup_focus=general, artifact_target="
            "latest_result, and include reason_codes=['latest_result_save_requested']. "
            "Set artifact_target to latest_result only when the current user message "
            "is actually about the latest completed run. Set artifact_target to "
            "pending_refinement when the user is answering a Refine strategy prompt. "
            "Set artifact_target to active_confirmation for visible confirmation/card "
            "questions. Set artifact_target to none for new ideas, standalone market "
            "questions, product help, or education. Do not let a completed result "
            "capture unrelated turns merely because it exists. "
            "When semantic_turn_act is educational_question and the user asks what "
            "Argus can do, what indicators it supports, what strategies it can run, "
            "what assets are available, or what the limits are, set "
            "capability_question_focus to supported_indicators, supported_strategies, "
            "assets, limits, or general. The runtime will answer from the executable "
            "capability registry; do not make unsupported execution claims in prose. "
            "Do not set capability_question_focus when the user is asking for plain "
            "education about an investing concept or a strategy family, such as what "
            "dollar cost averaging means; answer those with natural prose and connect "
            "the concept to the closest runnable Argus experiment when useful. "
            "For standalone macro, market-event, or market-context curiosity that is "
            "not asking for live feed output and is not tied to the latest result, set "
            "context_question_focus instead of capability_question_focus. Use "
            "macro_context for inflation, rates, Fed, recession, risk-on/off, or broad "
            "macro backdrop; corporate_events for splits, dividends, corporate actions, "
            "or earnings/event context; and market_movers for broad movers, most-active, "
            "or unusual-move curiosity. Keep artifact_target=none unless the user "
            "clearly targets a visible result or current confirmation. "
            "Retry turns should preserve the failed action payload; do "
            "not reinterpret the original investing idea from scratch. "
            "Social turns are conversation_followup with assistant_response and no "
            "strategy draft unless they also contain a real investing idea. "
            "When the user explicitly asks for response style, verbosity, or expertise "
            "for this turn, set response_profile_overrides; do not rely on backend "
            "regex for those preferences.\n\n"
            "Selected thread metadata may include the pending requested_field from "
            "the visible artifact. Use it as context for short answers, not as "
            "user-facing copy. If requested_field is asset_universe, treat the "
            "reply as an operation-agnostic asset edit context: the user may add "
            "assets, remove assets, keep a subset, replace assets, or change a "
            "different setup field. Do not assume the visible chip means single-asset "
            "replacement. Extract only the user's typed edit into "
            "candidate_strategy_draft and keep unrelated prior strategy fields "
            "unchanged. Use normal market-symbol knowledge for common assets; "
            "deterministic provider validation will accept, clarify, or reject it "
            "after you return. If the user gives a fresh complete idea instead of a "
            "field answer, classify that as a new idea and extract the full draft.\n\n"
            "assistant_response must be natural user-facing prose. Never expose "
            "internal field names such as asset_universe, capital_amount, "
            "requested_field, or missing_required_fields. Never output raw JSON, "
            "'not specified', template placeholders, scaffolding labels, or backend "
            "schema language. Avoid responses under 10 words except deliberate short "
            "confirmations.\n\n"
            "Treat prior result state as optional context, not the active topic by default. "
            "Set uses_latest_result_context=true only when the latest user message is semantically "
            "about the latest run/result, such as metrics, return, benchmark, drawdown, assumptions "
            "in the backtest, underperformance, or what exactly was tested. If the user asks for "
            "beginner onboarding, product help, a concept explanation, or a new idea, set it false "
            "and do not classify as results_explanation just because a completed run exists."
        )

    def _to_runtime_interpretation(
        self,
        response: LLMInterpretationResponse,
        *,
        request: InterpretationRequest,
    ) -> StructuredInterpretation:
        response = retain_pending_focused_seed(response, request=request)
        strategy = _strategy_from_llm(response.candidate_strategy_draft, request.current_user_message)  # fmt: skip
        _merge_prior_strategy(strategy=strategy, request=request, response=response)
        _ground_strategy_in_current_turn(strategy=strategy, request=request)
        _validate_capability_boundaries(
            strategy=strategy,
            response=response,
            request=request,
        )
        unsupported = [
            _unsupported_from_llm(item) for item in response.unsupported_constraints
        ]
        ambiguous = [
            AmbiguousField.model_validate(item.model_dump(mode="python"))
            for item in response.ambiguous_fields
        ]
        return StructuredInterpretation(
            intent=response.intent,
            task_relation=response.task_relation,
            requires_clarification=response.requires_clarification,
            user_goal_summary=response.user_goal_summary,
            detected_user_language=response.detected_user_language,
            candidate_strategy_draft=strategy,
            missing_required_fields=list(response.missing_required_fields),
            assistant_response=response.assistant_response,
            confidence=response.confidence,
            reason_codes=list(response.reason_codes),
            ambiguous_fields=ambiguous,
            unsupported_constraints=unsupported,
            response_profile_overrides=response.response_profile_overrides,
            semantic_turn_act=response.semantic_turn_act,
            result_followup_focus=response.result_followup_focus,
            result_followup_fact_key=response.result_followup_fact_key,
            capability_question_focus=response.capability_question_focus,
            context_question_focus=response.context_question_focus,
            artifact_target=_artifact_target_from_response(response),
            asset_discovery=response.asset_discovery,
            research_query=response.research_query,
        )


def _provider_asset_resolution_context_from_extraction(extraction):
    return provider_asset_resolution_context_from_extraction(
        extraction, resolve_asset_candidate=_resolve_asset_candidate
    )


async def _asset_grounding_audited_response(
    *,
    response: LLMInterpretationResponse,
    preferred_model: str,
    request: InterpretationRequest,
) -> LLMInterpretationResponse:
    suspicious_symbols = _suspicious_extracted_asset_symbols(
        response=response, request=request
    )
    trusted = asset_grounding.trusted_asset_symbols(response, suspicious_symbols)
    if not suspicious_symbols:
        response = _response_with_misplaced_benchmark_asset_recovered(
            response=response, request=request
        )
        return provider_context_assets.response_with_grounded_partial_context(response)
    try:
        audit = await invoke_openrouter_json_schema(
            task="interpretation",
            messages=_asset_grounding_audit_messages(
                response=response,
                request=request,
                suspicious_symbols=suspicious_symbols,
            ),
            schema_model=AssetGroundingAudit,
            schema_name="AssetGroundingAudit",
            model_name=preferred_model,
        )
    except Exception as exc:
        log_openrouter_failure(
            task="interpretation",
            model_name=preferred_model,
            exc=exc,
            message="Asset grounding audit failed; clearing suspicious extracted assets",
        )
        return _response_without_ungrounded_symbols(
            response=response,
            grounded_symbols=trusted,
            reason_code="asset_grounding_audit_unavailable_cleared_suspicious_symbols",
        )
    if not isinstance(audit, AssetGroundingAudit) or audit.confidence < 0.6:
        return _response_without_ungrounded_symbols(
            response=response,
            grounded_symbols=trusted,
            reason_code="asset_grounding_audit_low_confidence_cleared_suspicious_symbols",
        )
    audited_response = _response_without_ungrounded_symbols(
        response=response,
        grounded_symbols=[*trusted, *audit.grounded_symbols],
        reason_code="asset_grounding_audit_removed_unsubstantiated_symbols",
    )
    return _response_with_misplaced_benchmark_asset_recovered(
        response=audited_response,
        request=request,
        ignored_name_supported_symbols=_normalized_extracted_symbols(
            response.candidate_strategy_draft.asset_universe
        ),
    )


def _suspicious_extracted_asset_symbols(
    *,
    response: LLMInterpretationResponse,
    request: InterpretationRequest,
) -> list[str]:
    if _selected_requested_field_base(request) == "asset_universe":
        return []
    symbols = [
        str(symbol).strip().upper()
        for symbol in response.candidate_strategy_draft.asset_universe
        if str(symbol).strip()
    ]
    if not symbols:
        return []
    raw_tokens = set(request.current_user_message.translate(_ASSET_TOKEN_MAP).split())
    lower_tokens = {token.casefold() for token in raw_tokens}
    cashtag_tokens = {
        token.lstrip("$").casefold() for token in raw_tokens if token.startswith("$")
    }
    grounded_symbols = {
        str(asset.canonical_symbol).strip().upper()
        for asset in _resolved_asset_mentions_from_message(request.current_user_message)
        if str(getattr(asset, "canonical_symbol", "")).strip()
    }
    provider_ticker_symbol_map = _current_message_provider_ticker_asset_map(request)
    context_symbols = _context_inheritable_asset_symbols(
        response=response,
        request=request,
        current_grounded_symbols=grounded_symbols,
    )
    suspicious: list[str] = []
    for symbol in symbols:
        folded = symbol.casefold()
        if symbol in raw_tokens or f"${symbol}" in raw_tokens or folded in cashtag_tokens:
            continue
        if symbol in grounded_symbols or symbol in context_symbols:
            continue
        if provider_context_assets.preflight_record_supports_symbol(
            response.candidate_strategy_draft, symbol
        ):
            continue
        if _provider_exact_ticker_supports_extracted_symbol(
            symbol,
            provider_ticker_symbol_map=provider_ticker_symbol_map,
        ):
            continue
        if folded in lower_tokens:
            suspicious.append(symbol)
            continue
        suspicious.append(symbol)
    return suspicious


def _current_message_provider_ticker_asset_map(
    request: InterpretationRequest,
) -> dict[str, Any]:
    assets = provider_ticker_assets_from_text(
        request.current_user_message,
        resolve_candidate=_resolve_benchmark_candidate_from_message,
        limit=10,
    )
    symbol_map: dict[str, Any] = {}
    for asset in assets:
        symbol = str(getattr(asset, "canonical_symbol", "") or "").strip().upper()
        if symbol and symbol not in symbol_map:
            symbol_map[symbol] = asset
    return symbol_map


def _request_has_provider_exact_execution_asset(
    request: InterpretationRequest,
) -> bool:
    provider_ticker_symbol_map = _current_message_provider_ticker_asset_map(request)
    return any(
        _provider_exact_ticker_supports_extracted_symbol(
            symbol,
            provider_ticker_symbol_map=provider_ticker_symbol_map,
        )
        for symbol in provider_ticker_symbol_map
    )


def _misplaced_benchmark_asset_candidate(
    *,
    response: LLMInterpretationResponse,
    request: InterpretationRequest,
    provider_ticker_symbol_map: dict[str, Any] | None = None,
    ignored_name_supported_symbols: set[str] | None = None,
) -> Any | None:
    draft = response.candidate_strategy_draft
    benchmark_symbol = _normalized_extracted_symbol(draft.comparison_baseline)
    if benchmark_symbol is None:
        return None
    if _current_message_has_other_name_supported_asset(
        response=response,
        request=request,
        excluding_symbol=benchmark_symbol,
        ignored_symbols=ignored_name_supported_symbols or set(),
    ):
        return None
    symbol_map = provider_ticker_symbol_map
    if symbol_map is None:
        symbol_map = _current_message_provider_ticker_asset_map(request)
    return symbol_map.get(benchmark_symbol)


def _current_message_has_other_name_supported_asset(
    *,
    response: LLMInterpretationResponse,
    request: InterpretationRequest,
    excluding_symbol: str,
    ignored_symbols: set[str],
) -> bool:
    def _resolve_candidate(query: str) -> AssetResolution | None:
        try:
            return _resolve_asset_candidate(
                query,
                field="asset_universe[0]",
                source="user_mention",
            )
        except ValueError:
            return None

    mentions = grounded_asset_mentions_from_text(
        request.current_user_message,
        resolve_candidate=_resolve_candidate,
        excluded_tokens=current_message_execution_context_tokens(
            request.current_user_message,
            strategy_type=response.candidate_strategy_draft.strategy_type,
        ),
        limit=5,
    )
    for mention in mentions:
        symbol = str(getattr(mention.asset, "canonical_symbol", "") or "").strip().upper()
        if (
            symbol != excluding_symbol
            and symbol not in ignored_symbols
            and grounded_asset_mention_has_name_support(mention)
        ):
            return True
    return False


def _comparison_baseline_has_provider_ticker_support(
    draft: LLMStrategyDraft,
    *,
    current_message: str,
) -> bool:
    benchmark = _normalized_extracted_symbol(draft.comparison_baseline)
    if benchmark is None:
        return False
    symbol_map = {
        str(getattr(asset, "canonical_symbol", "") or "").strip().upper()
        for asset in provider_ticker_assets_from_text(
            current_message,
            resolve_candidate=_resolve_benchmark_candidate_from_message,
            limit=10,
        )
    }
    return benchmark in symbol_map


def _response_with_misplaced_benchmark_asset_recovered(
    *,
    response: LLMInterpretationResponse,
    request: InterpretationRequest,
    ignored_name_supported_symbols: set[str] | None = None,
) -> LLMInterpretationResponse:
    draft = response.candidate_strategy_draft
    if draft.asset_universe:
        return response
    candidate = _misplaced_benchmark_asset_candidate(
        response=response,
        request=request,
        ignored_name_supported_symbols=ignored_name_supported_symbols,
    )
    if candidate is None:
        return response
    symbol = str(getattr(candidate, "canonical_symbol", "") or "").strip().upper()
    if not symbol:
        return response

    repaired = response.model_copy(deep=True)
    repaired_draft = repaired.candidate_strategy_draft
    repaired_draft.asset_universe = [symbol]
    asset_class = str(getattr(candidate, "asset_class", "") or "").strip()
    if asset_class:
        repaired_draft.asset_class = asset_class
    repaired_draft.strategy_thesis = None
    repaired_draft.comparison_baseline = None
    field_provenance = dict(repaired_draft.field_provenance or {})
    field_provenance.pop("comparison_baseline", None)
    repaired_draft.field_provenance = field_provenance
    extra_parameters = dict(repaired_draft.extra_parameters or {})
    if field_provenance:
        extra_parameters["field_provenance"] = field_provenance
    else:
        extra_parameters.pop("field_provenance", None)
    repaired_draft.extra_parameters = extra_parameters
    return repaired.model_copy(
        update={
            "candidate_strategy_draft": repaired_draft,
            "reason_codes": list(
                dict.fromkeys(
                    [
                        *repaired.reason_codes,
                        "misplaced_benchmark_asset_recovered",
                    ]
                )
            ),
        }
    )


def _response_without_ungrounded_symbols(
    *,
    response: LLMInterpretationResponse,
    grounded_symbols: list[str],
    reason_code: str,
) -> LLMInterpretationResponse:
    grounded = {symbol.strip().upper() for symbol in grounded_symbols if symbol.strip()}
    draft = response.candidate_strategy_draft.model_copy(deep=True)
    original_symbols = [str(symbol).strip().upper() for symbol in draft.asset_universe]
    draft.asset_universe = [symbol for symbol in original_symbols if symbol in grounded]
    mixed_asset_response = _response_with_mixed_asset_guardrail_from_symbols(
        response=response,
        symbols=draft.asset_universe,
    )
    if mixed_asset_response is not None:
        return mixed_asset_response
    if len(draft.asset_universe) == len(original_symbols):
        return provider_context_assets.response_with_grounded_partial_context(response)
    missing_required_fields = list(response.missing_required_fields)
    requires_clarification = response.requires_clarification
    if not draft.asset_universe:
        draft.asset_class = None
        if canonical_strategy_type(draft.strategy_type):
            missing_required_fields = list(
                dict.fromkeys([*missing_required_fields, "asset_universe"])
            )
            requires_clarification = True
    return _response_with_canonical_interpreter_assets(
        response.model_copy(
            update={
                "candidate_strategy_draft": draft,
                "assistant_response": None,
                "requires_clarification": requires_clarification,
                "missing_required_fields": missing_required_fields,
                "reason_codes": list(
                    dict.fromkeys([*response.reason_codes, reason_code])
                ),
            }
        )
    )


def _response_with_mixed_asset_guardrail_from_symbols(
    *,
    response: LLMInterpretationResponse,
    symbols: list[str],
) -> LLMInterpretationResponse | None:
    resolved_symbols: list[str] = []
    asset_classes: set[str] = set()
    for index, symbol in enumerate(symbols):
        try:
            resolution = _resolve_asset_candidate(
                symbol,
                field=f"asset_universe[{index}]",
                source="llm_extraction",
            )
        except ValueError:
            continue
        if resolution.status != "resolved" or resolution.asset is None:
            continue
        canonical_symbol = str(resolution.asset.canonical_symbol or "").strip().upper()
        asset_class = str(resolution.asset.asset_class or "").strip().lower()
        if canonical_symbol:
            resolved_symbols.append(canonical_symbol)
        if asset_class:
            asset_classes.add(asset_class)
    if len(asset_classes) <= 1:
        return None
    draft = response.candidate_strategy_draft.model_copy(deep=True)
    draft.asset_universe = list(dict.fromkeys(resolved_symbols))
    draft.asset_class = "mixed"
    unsupported_constraints = list(response.unsupported_constraints)
    if not any(
        item.category == "unsupported_asset_mix" for item in unsupported_constraints
    ):
        unsupported_constraints.append(
            LLMUnsupportedConstraint(
                category="unsupported_asset_mix",
                raw_value=", ".join(draft.asset_universe),
                explanation=(
                    "Argus Alpha cannot run equity, crypto, and currency pairs "
                    "together in one simulation yet."
                ),
                simplification_options=_options.asset_class_simplification_options(),
            )
        )
    missing_required_fields = [
        field
        for field in response.missing_required_fields
        if _field_path_base(field) != "asset_universe"
    ]
    return response.model_copy(
        update={
            "candidate_strategy_draft": draft,
            "assistant_response": None,
            "requires_clarification": True,
            "missing_required_fields": missing_required_fields,
            "unsupported_constraints": unsupported_constraints,
            "reason_codes": list(
                dict.fromkeys(
                    [
                        *response.reason_codes,
                        "mixed_asset_guardrail_preserved_grounding_symbols",
                    ]
                )
            ),
        }
    )


async def _requested_asset_answer_candidate_audited_response(
    *,
    response: LLMInterpretationResponse,
    preferred_model: str,
    request: InterpretationRequest,
) -> LLMInterpretationResponse:
    return (
        await _requested_asset_answer.requested_asset_answer_candidate_audited_response(
            response=response,
            preferred_model=preferred_model,
            request=request,
            invoke_schema=invoke_openrouter_json_schema,
            resolve_asset_candidate=_resolve_asset_candidate,
            model_candidates=_unique_repair_models,
        )
    )


def _response_from_requested_asset_answer_candidate_audit(
    *,
    response: LLMInterpretationResponse,
    request: InterpretationRequest,
    audit: Any,
) -> LLMInterpretationResponse | None:
    return _requested_asset_answer.response_from_requested_asset_answer_candidate_audit(
        response=response,
        request=request,
        audit=audit,
        resolve_asset_candidate=_resolve_asset_candidate,
    )


def _response_needs_requested_asset_answer_candidate_audit(
    *,
    response: LLMInterpretationResponse,
    request: InterpretationRequest,
) -> bool:
    return _requested_asset_answer.response_needs_requested_asset_answer_candidate_audit(
        response=response,
        request=request,
        resolve_asset_candidate=_resolve_asset_candidate,
    )


def _response_is_requested_asset_answer_patch(
    *,
    response: LLMInterpretationResponse,
    request: InterpretationRequest,
) -> bool:
    return _requested_asset_answer.response_is_requested_asset_answer_patch(
        response=response,
        request=request,
        resolve_asset_candidate=_resolve_asset_candidate,
    )


def _response_is_audited_requested_asset_answer_patch(
    *,
    response: LLMInterpretationResponse,
    request: InterpretationRequest,
) -> bool:
    return _response_is_requested_asset_answer_patch(
        response=response,
        request=request,
    )


def _draft_has_valid_requested_asset_update(
    draft: LLMStrategyDraft,
    request: InterpretationRequest,
) -> bool:
    return _requested_asset_answer.draft_has_valid_requested_asset_update(
        draft,
        request,
        resolve_asset_candidate=_resolve_asset_candidate,
    )


_ASSET_TOKEN_MAP = str.maketrans({char: " " for char in ".,;:!?()[]{}<>\"'`"})


def _asset_grounding_audit_messages(
    *,
    response: LLMInterpretationResponse,
    request: InterpretationRequest,
    suspicious_symbols: list[str],
) -> list[dict[str, str]]:
    provider_ticker_symbol_map = _current_message_provider_ticker_asset_map(request)
    misplaced_candidate = _misplaced_benchmark_asset_candidate(
        response=response,
        request=request,
        provider_ticker_symbol_map=provider_ticker_symbol_map,
        ignored_name_supported_symbols=set(suspicious_symbols),
    )
    misplaced_symbol = (
        str(getattr(misplaced_candidate, "canonical_symbol", "") or "").strip().upper()
        if misplaced_candidate is not None
        else None
    )
    return [
        {
            "role": "system",
            "content": (
                "You are Argus's asset-grounding audit. The interpreter extracted "
                "asset symbols that may not be grounded in the current user message "
                "or safely inherited artifact context. Return only the extracted "
                "symbols that the user clearly intended as assets or tickers. Do "
                "not treat pronouns, helper words, verbs, or generic conversation "
                "words as assets. Keep a symbol when the user clearly named the "
                "company, asset, ticker, or cashtag. Do not invent new symbols."
            ),
        },
        {
            "role": "system",
            "content": f"Extracted symbols to audit: {suspicious_symbols}",
        },
        {
            "role": "system",
            "content": (
                "Provider-backed exact ticker candidates in the current message: "
                f"{sorted(provider_ticker_symbol_map)}"
            ),
        },
        {
            "role": "system",
            "content": f"Possible misplaced benchmark asset: {misplaced_symbol}",
        },
        {
            "role": "system",
            "content": (
                "Current structured interpretation: "
                f"{response.model_dump(mode='json', exclude_none=True)}"
            ),
        },
        {"role": "user", "content": request.current_user_message},
    ]


async def _capability_side_question_audited_response(
    *,
    response: LLMInterpretationResponse,
    preferred_model: str,
    request: InterpretationRequest,
) -> LLMInterpretationResponse:
    if not _response_needs_capability_side_question_audit(
        response=response,
        request=request,
    ):
        return response
    try:
        audit = await invoke_openrouter_json_schema(
            task="interpretation",
            messages=_capability_side_question_audit_messages(
                response=response,
                request=request,
            ),
            schema_model=CapabilitySideQuestionAudit,
            schema_name="CapabilitySideQuestionAudit",
            model_name=preferred_model,
        )
    except Exception as exc:
        log_openrouter_failure(
            task="interpretation",
            model_name=preferred_model,
            exc=exc,
            message="Capability side-question audit failed; preserving primary interpretation",
        )
        fallback_response = _capability_audit_unavailable_response_if_safe(
            response=response,
            request=request,
        )
        if fallback_response is not None:
            return fallback_response
        return response
    if (
        not isinstance(audit, CapabilitySideQuestionAudit)
        or not audit.is_capability_question
        or audit.focus is None
        or audit.confidence < 0.6
    ):
        return response
    return response.model_copy(
        update={
            "intent": "conversation_followup",
            "task_relation": "continue",
            "requires_clarification": False,
            "candidate_strategy_draft": LLMStrategyDraft(
                raw_user_phrasing=request.current_user_message
            ),
            "missing_required_fields": [],
            "ambiguous_fields": [],
            "unsupported_constraints": [],
            "assistant_response": audit.assistant_response,
            "semantic_turn_act": "educational_question",
            "capability_question_focus": audit.focus,
            "artifact_target": "none",
            "reason_codes": list(
                dict.fromkeys(
                    [
                        *response.reason_codes,
                        "capability_side_question_audit",
                    ]
                )
            ),
        }
    )


def _response_needs_capability_side_question_audit(
    *,
    response: LLMInterpretationResponse,
    request: InterpretationRequest,
) -> bool:
    if response.capability_question_focus is not None:
        return False
    if response.context_question_focus is not None:
        return False
    if response.semantic_turn_act in {
        "approval",
        "retry_failed_action",
        "result_followup",
    }:
        return False
    if _llm_strategy_draft_has_concrete_execution_target(
        response.candidate_strategy_draft
    ):
        return False
    if _response_needs_material_evidence_strategy_repair(
        response=response,
        request=request,
    ):
        return False
    if _response_had_unsubstantiated_asset_removed(response):
        return True
    pending_field = str(
        request.selected_thread_metadata.get("requested_field") or ""
    ).strip()
    if _field_path_base(pending_field) == "refinement":
        return False
    if pending_field:
        return True
    # A plain educational turn keeps the primary's typed focus; only a
    # strategy-flow shape earns a second read.
    return _is_vague_strategy_start(response)


def _capability_audit_unavailable_response_if_safe(
    *,
    response: LLMInterpretationResponse,
    request: InterpretationRequest,
) -> LLMInterpretationResponse | None:
    if not _response_had_unsubstantiated_asset_removed(response):
        return None
    if _request_current_turn_has_material_execution_evidence(request):
        return None
    return response.model_copy(
        update={
            "intent": "conversation_followup",
            "task_relation": "continue",
            "requires_clarification": False,
            "candidate_strategy_draft": LLMStrategyDraft(
                raw_user_phrasing=request.current_user_message
            ),
            "missing_required_fields": [],
            "ambiguous_fields": [],
            "unsupported_constraints": [],
            "assistant_response": None,
            "semantic_turn_act": "educational_question",
            "capability_question_focus": None,
            "artifact_target": "none",
            "reason_codes": list(
                dict.fromkeys(
                    [
                        *response.reason_codes,
                        "capability_side_question_audit",
                        "capability_side_question_audit_unavailable_after_asset_grounding",
                    ]
                )
            ),
        }
    )


async def _context_question_audited_response(
    *,
    response: LLMInterpretationResponse,
    preferred_model: str,
    request: InterpretationRequest,
    force: bool = False,
) -> LLMInterpretationResponse:
    if not force and not _response_needs_context_question_audit(
        response=response, request=request
    ):
        return response
    try:
        audit = await invoke_openrouter_json_schema(
            task="interpretation",
            messages=_context_question_audit_messages(
                response=response,
                request=request,
            ),
            schema_model=ContextQuestionAudit,
            schema_name="ContextQuestionAudit",
            model_name=preferred_model,
        )
    except Exception as exc:
        log_openrouter_failure(
            task="interpretation",
            model_name=preferred_model,
            exc=exc,
            message="Context-question audit failed; preserving primary interpretation",
        )
        return response
    if (
        not isinstance(audit, ContextQuestionAudit)
        or not audit.is_context_question
        or audit.focus is None
        or audit.confidence < 0.6
    ):
        return response
    return response.model_copy(
        update={
            "intent": "conversation_followup",
            "task_relation": "continue",
            "requires_clarification": False,
            "candidate_strategy_draft": LLMStrategyDraft(
                raw_user_phrasing=request.current_user_message
            ),
            "missing_required_fields": [],
            "ambiguous_fields": [],
            "unsupported_constraints": [],
            "assistant_response": None,
            "semantic_turn_act": "educational_question",
            "capability_question_focus": None,
            "context_question_focus": audit.focus,
            "artifact_target": "none",
            "uses_latest_result_context": False,
            "reason_codes": list(
                dict.fromkeys(
                    [
                        *response.reason_codes,
                        "context_question_audit",
                    ]
                )
            ),
        }
    )


async def _unsupported_context_question_audited_response(
    *,
    response: LLMInterpretationResponse,
    preferred_model: str,
    request: InterpretationRequest,
) -> LLMInterpretationResponse | None:
    if (
        response.intent != "unsupported_or_out_of_scope"
        or response.semantic_turn_act != "unsupported_request"
        or response.missing_required_fields
        or response.context_question_focus is not None
    ):
        return None
    repaired = await _context_question_audited_response(
        response=response,
        preferred_model=preferred_model,
        request=request,
        force=True,
    )
    return repaired if repaired is not response else None


async def _strategy_family_continuity_audited_response(
    *,
    response: LLMInterpretationResponse,
    preferred_model: str,
    request: InterpretationRequest,
) -> LLMInterpretationResponse:
    if not _response_needs_strategy_family_continuity_audit(
        response=response,
        request=request,
    ):
        return response
    try:
        audit = await invoke_openrouter_json_schema(
            task="interpretation",
            messages=_strategy_family_continuity_audit_messages(
                response=response,
                request=request,
            ),
            schema_model=StrategyFamilyContinuityAudit,
            schema_name="StrategyFamilyContinuityAudit",
            model_name=preferred_model,
        )
    except Exception as exc:
        log_openrouter_failure(
            task="interpretation",
            model_name=preferred_model,
            exc=exc,
            message="Strategy family continuity audit failed; preserving primary interpretation",
        )
        return response
    if (
        not isinstance(audit, StrategyFamilyContinuityAudit)
        or not audit.should_rebind_strategy_family
        or audit.confidence < 0.7
    ):
        return response
    strategy_type = canonical_strategy_type(audit.strategy_type)
    if strategy_type not in {
        "buy_and_hold",
        "dca_accumulation",
        "indicator_threshold",
        "signal_strategy",
    }:
        return response
    draft = response.candidate_strategy_draft.model_copy(deep=True)
    draft.strategy_type = strategy_type
    missing_required_fields = list(response.missing_required_fields)
    requires_clarification = response.requires_clarification
    if strategy_type == "dca_accumulation" and audit.total_budget_not_recurring:
        _move_dca_total_budget_out_of_recurring_amount(draft)
        if draft.capital_amount is None:
            missing_required_fields = list(
                dict.fromkeys([*missing_required_fields, "capital_amount"])
            )
            requires_clarification = True
        if _llm_value_is_empty(draft.cadence):
            missing_required_fields = list(
                dict.fromkeys([*missing_required_fields, "cadence"])
            )
            requires_clarification = True
    return response.model_copy(
        update={
            "intent": "strategy_drafting" if requires_clarification else response.intent,
            "task_relation": "continue",
            "requires_clarification": requires_clarification,
            "candidate_strategy_draft": draft,
            "missing_required_fields": missing_required_fields,
            "assistant_response": None,
            "semantic_turn_act": "answer_pending_need",
            "artifact_target": "none",
            "reason_codes": list(
                dict.fromkeys(
                    [
                        *response.reason_codes,
                        "strategy_family_continuity_rebound",
                    ]
                )
            ),
        }
    )


async def _dca_contract_audited_response(
    *,
    response: LLMInterpretationResponse,
    preferred_model: str,
    request: InterpretationRequest,
) -> LLMInterpretationResponse:
    if not _response_needs_dca_contract_audit(response=response, request=request):
        return response
    messages = _dca_contract_audit_messages(response=response, request=request)
    for model_name in _unique_repair_models(preferred_model):
        try:
            audit = await invoke_openrouter_json_schema(
                task="interpretation",
                messages=messages,
                schema_model=DcaContractAudit,
                schema_name="DcaContractAudit",
                model_name=model_name,
            )
        except Exception as exc:
            log_openrouter_failure(
                task="interpretation",
                model_name=model_name,
                exc=exc,
                message="DCA contract audit failed; trying next candidate model",
            )
            continue
        repaired = _response_from_dca_contract_audit(
            response=response, audit=audit, request=request
        )
        if repaired is not None:
            return repaired
    return response


def _response_needs_dca_contract_audit(
    *,
    response: LLMInterpretationResponse,
    request: InterpretationRequest,
) -> bool:
    if response.artifact_target == "latest_result":
        return False
    if response.semantic_turn_act in {
        "approval",
        "educational_question",
        "refine_current_idea",
        "result_followup",
        "retry_failed_action",
    }:
        return False
    if response.intent not in {
        "strategy_drafting",
        "backtest_execution",
        "unsupported_or_out_of_scope",
    }:
        return False
    if not request.current_user_message.strip():
        return False
    draft = response.candidate_strategy_draft
    if canonical_strategy_type(draft.strategy_type) == "dca_accumulation":
        return _dca_response_needs_semantic_field_audit(
            response
        ) or _current_message_has_dca_contract_shape(
            response=response,
            request=request,
        )
    if not _current_message_has_dca_contract_shape(
        response=response,
        request=request,
    ):
        return False
    if response.capability_question_focus is not None:
        return _llm_strategy_draft_has_extractable_fields(draft) or bool(
            draft.raw_user_phrasing or draft.strategy_thesis
        )
    if response.semantic_turn_act == "unsupported_request":
        return _llm_strategy_draft_has_extractable_fields(draft) or bool(
            draft.raw_user_phrasing or draft.strategy_thesis
        )
    return (
        response.requires_clarification
        and not canonical_strategy_type(draft.strategy_type)
        and _llm_strategy_draft_has_extractable_fields(draft)
    )


def _current_message_has_dca_contract_shape(
    *,
    response: LLMInterpretationResponse,
    request: InterpretationRequest,
) -> bool:
    draft = response.candidate_strategy_draft
    if _supported_dca_cadence_value(draft.cadence) is not None:
        return _draft_contains_structured_capital_context(draft)
    if not _request_current_turn_has_material_execution_evidence(request):
        return False
    if response.intent == "unsupported_or_out_of_scope":
        return _llm_strategy_draft_has_extractable_fields(draft)
    if response.capability_question_focus is not None:
        return _llm_strategy_draft_has_extractable_fields(draft)
    return (
        response.semantic_turn_act == "unsupported_request"
        and _llm_strategy_draft_has_extractable_fields(draft)
    )


async def _dca_contribution_role_audited_response(
    *,
    response: LLMInterpretationResponse,
    preferred_model: str,
    request: InterpretationRequest,
) -> LLMInterpretationResponse:
    if not _response_needs_dca_contribution_role_audit(response):
        return response
    try:
        audit = await invoke_openrouter_json_schema(
            task="interpretation",
            messages=_dca_contribution_role_audit_messages(
                response=response,
                request=request,
            ),
            schema_model=DcaContributionRoleAudit,
            schema_name="DcaContributionRoleAudit",
            model_name=preferred_model,
        )
    except Exception as exc:
        log_openrouter_failure(
            task="interpretation",
            model_name=preferred_model,
            exc=exc,
            message="DCA contribution role audit failed; preserving primary interpretation",
        )
        return response
    if not isinstance(audit, DcaContributionRoleAudit) or audit.confidence < 0.65:
        return response
    if audit.recurring_contribution_explicit:
        draft = response.candidate_strategy_draft.model_copy(deep=True)
        draft.recurring_contribution = draft.capital_amount
        if draft.field_provenance.get("capital_amount") != "recurring_contribution":
            draft.field_provenance["capital_amount"] = "recurring_contribution"
        draft.field_provenance["recurring_contribution"] = "explicit_user"
        cadence = _supported_dca_cadence_value(draft.cadence)
        missing_required_fields = list(response.missing_required_fields)
        if cadence is not None:
            draft.cadence = cadence
            draft.field_provenance["cadence"] = "explicit_user"
            missing_required_fields = [
                field
                for field in missing_required_fields
                if _field_path_base(field) != "cadence"
            ]
        missing_required_fields = [
            field
            for field in missing_required_fields
            if _field_path_base(field) != "capital_amount"
        ]
        return response.model_copy(
            update={
                "candidate_strategy_draft": draft,
                "missing_required_fields": missing_required_fields,
                "requires_clarification": bool(missing_required_fields),
                "assistant_response": None,
                "reason_codes": list(
                    dict.fromkeys(
                        [
                            *response.reason_codes,
                            "dca_recurring_contribution_grounded_in_current_message",
                        ]
                        + (
                            ["dca_total_budget_preserved_as_context"]
                            if audit.total_budget_not_recurring
                            else []
                        )
                    )
                ),
            }
        )
    return total_budget_audited_response(
        response=response,
        audit=audit,
        answers_pending_sizing_question=_turn_answers_pending_sizing_question(request),
    )


def _turn_answers_pending_sizing_question(request: InterpretationRequest) -> bool:
    """Whether THIS turn answers the runtime's own money question.

    ``requested_field`` alone is carried forward while a pending strategy
    exists, so it only says a question was asked at some point. When the
    previous turn's stage outcome is ``await_user_reply`` the metadata beside
    it was set by that same clarify, which makes the pair current-turn
    accurate. The DCA ceiling recovery asks for the money too, but through
    ``simplification_choice`` with no requested field, so its reason code is
    the second admissible shape.
    """
    metadata = request.selected_thread_metadata
    if str(metadata.get("last_stage_outcome") or "") != "await_user_reply":
        return False
    if _selected_requested_field_base(request) == "capital_amount":
        return True
    clarification = metadata.get("clarification")
    reason_code = (
        str(clarification.get("reason_code") or "")
        if isinstance(clarification, dict)
        else ""
    )
    return reason_code == UNSUPPORTED_DCA_CONTRIBUTION_CEILING


async def _pending_response_option_selected_response(
    *,
    response: LLMInterpretationResponse,
    preferred_model: str,
    request: InterpretationRequest,
) -> LLMInterpretationResponse:
    if not _response_needs_pending_response_option_selection_audit(
        response=response,
        request=request,
    ):
        return response
    options = _pending_response_intent_options(request)
    messages = _pending_response_option_selection_audit_messages(
        response=response,
        request=request,
        options=options,
    )
    for model_name in _unique_repair_models(preferred_model):
        try:
            audit = await invoke_openrouter_json_schema(
                task="interpretation",
                messages=messages,
                schema_model=PendingResponseOptionSelectionAudit,
                schema_name="PendingResponseOptionSelectionAudit",
                model_name=model_name,
            )
        except Exception as exc:
            log_openrouter_failure(
                task="interpretation",
                model_name=model_name,
                exc=exc,
                message=(
                    "Pending response option selection audit failed; trying next "
                    "candidate model"
                ),
            )
            continue
        repaired = _response_from_pending_response_option_selection_audit(
            response=response,
            request=request,
            audit=audit,
            options=options,
        )
        if repaired is not None:
            return repaired
    return response


async def _response_ready_for_runtime(
    *,
    response: LLMInterpretationResponse,
    preferred_model: str,
    request: InterpretationRequest,
    asset_resolution_context: str | None = None,
) -> LLMInterpretationResponse:
    if (
        research_rail_enabled()
        and primary_research_query(response) is not None
        and request.selected_thread_metadata.get("last_stage_outcome") != "await_user_reply"
    ):
        # The primary read owns this question. Strategy and discovery intent
        # repairs must not replace it; provider grounding happens in the rail.
        return response
    discovery_response = discovery_response_ready_for_runtime(
        response=response,
        request=request,
        asset_resolution_context=asset_resolution_context,
        normalize=_normalize_response_for_runtime_context,
    )
    if discovery_response is None:
        recovered = await focused_discovery_payload_response(
            response=response, request=request
        )
        if recovered is not None:
            discovery_response = discovery_response_ready_for_runtime(
                response=recovered,
                request=request,
                asset_resolution_context=asset_resolution_context,
                normalize=_normalize_response_for_runtime_context,
            )
    if discovery_response is not None:
        return discovery_response
    response = response_without_unroutable_discovery_payload(response)
    return await _audited_response_ready_for_runtime(
        response=response,
        preferred_model=preferred_model,
        request=request,
        asset_resolution_context=asset_resolution_context,
    )


async def _audited_response_ready_for_runtime(
    *,
    response: LLMInterpretationResponse,
    preferred_model: str,
    request: InterpretationRequest,
    asset_resolution_context: str | None = None,
) -> LLMInterpretationResponse:
    response = _normalize_response_for_runtime_context(
        response, request=request, asset_resolution_context=asset_resolution_context
    )
    response = _bare_asset_answer_without_unevidenced_operation(
        response=response,
        request=request,
        resolve_asset_candidate=_resolve_asset_candidate,
    )
    _log_runtime_readiness_step("started", response=response)
    planned_artifact_edit = await _ready_active_artifact_edit_planned_response(
        response=response,
        preferred_model=preferred_model,
        request=request,
    )
    if planned_artifact_edit is not None:
        return _carry_asset_blocker(planned_artifact_edit, asset_resolution_context)
    if _response_can_skip_optional_runtime_readiness_audits(
        response=response,
        request=request,
    ):
        _log_runtime_readiness_step(
            "ready_after_initial_interpretation",
            response=response,
        )
        return response
    capital_response = await _early_starting_capital_rechecked_response(
        response=response,
        request=request,
    )
    if capital_response is not None:
        response = capital_response
        if _response_can_skip_optional_runtime_readiness_audits(
            response=response,
            request=request,
        ):
            _log_runtime_readiness_step(
                "ready_after_starting_capital_recheck",
                response=response,
            )
            return response
    focused_response = await _early_focused_strategy_repaired_response(
        response=response,
        preferred_model=preferred_model,
        request=request,
        asset_resolution_context=asset_resolution_context,
    )
    if focused_response is not None:
        response = focused_response
        if _response_can_skip_optional_runtime_readiness_audits(
            response=response,
            request=request,
        ):
            _log_runtime_readiness_step(
                "ready_after_early_focused_strategy_repair",
                response=response,
            )
            return response
    response = await _pending_response_option_selected_response(
        response=response,
        preferred_model=preferred_model,
        request=request,
    )
    response = await _requested_asset_answer_candidate_audited_response(
        response=response,
        preferred_model=preferred_model,
        request=request,
    )
    if _response_is_requested_asset_answer_patch(
        response=response,
        request=request,
    ):
        return response
    response = await _latest_result_routing_audited_response(
        response=response,
        preferred_model=preferred_model,
        request=request,
    )
    if _response_targets_latest_result_followup(response=response, request=request):
        return response
    response = await _asset_grounding_audited_response(
        response=response,
        preferred_model=preferred_model,
        request=request,
    )
    if _response_needs_material_evidence_strategy_repair(
        response=response,
        request=request,
    ):
        repaired_response = await _repair_incomplete_strategy_extraction(
            failed_response=response,
            preferred_model=preferred_model,
            request=request,
            asset_resolution_context=asset_resolution_context,
        )
        if repaired_response is not None:
            return await _stated_run_field_audited_response(
                response=repaired_response,
                preferred_model=preferred_model,
                request=request,
            )
    if _response_needs_pre_guidance_focused_strategy_extraction(
        response=response,
        request=request,
    ):
        repaired_response = await _repair_incomplete_strategy_extraction(
            failed_response=response,
            preferred_model=preferred_model,
            request=request,
            asset_resolution_context=asset_resolution_context,
        )
        if repaired_response is not None:
            return await _stated_run_field_audited_response(
                response=repaired_response,
                preferred_model=preferred_model,
                request=request,
            )
    response = await _capability_side_question_audited_response(
        response=response,
        preferred_model=preferred_model,
        request=request,
    )
    if (
        response.artifact_target == "none"
        and "capability_side_question_audit" in response.reason_codes
        and _response_had_unsubstantiated_asset_removed(response)
    ):
        return response
    response = await _context_question_audited_response(
        response=response,
        preferred_model=preferred_model,
        request=request,
    )
    response = await _dca_contract_audited_response(
        response=response,
        preferred_model=preferred_model,
        request=request,
    )
    response = await _strategy_family_continuity_audited_response(
        response=response,
        preferred_model=preferred_model,
        request=request,
    )
    response = await _dca_contribution_role_audited_response(
        response=response,
        preferred_model=preferred_model,
        request=request,
    )
    _log_runtime_readiness_step("baseline_audits_completed", response=response)
    if _response_can_skip_optional_runtime_readiness_audits(
        response=response,
        request=request,
    ):
        _log_runtime_readiness_step("ready_after_baseline_audits", response=response)
        return response
    if (
        _optional_runtime_readiness_audit_blocker(
            response=response,
            request=request,
        )
        == "launch_field_fidelity"
    ):
        _log_runtime_readiness_step(
            "launch_field_fidelity_audit_started",
            response=response,
        )
        audited_response = await _audit_stated_run_fields(
            response=response,
            preferred_model=preferred_model,
            request=request,
        )
        if audited_response is not None:
            response = audited_response
            if _response_can_skip_optional_runtime_readiness_audits(
                response=response,
                request=request,
            ):
                _log_runtime_readiness_step(
                    "ready_after_launch_field_fidelity_audit",
                    response=response,
                )
                return response
    _log_runtime_readiness_step(
        "capability_conflict_audit_started",
        response=response,
    )
    conflict_response = await _audit_supported_strategy_capability_conflict(
        response=response,
        preferred_model=preferred_model,
        request=request,
    )
    if conflict_response is not None:
        conflict_response = await _underfilled_strategy_repaired_response(
            response=conflict_response,
            preferred_model=preferred_model,
            request=request,
        )
        return await _stated_run_field_audited_response(
            response=conflict_response,
            preferred_model=preferred_model,
            request=request,
        )
    _log_runtime_readiness_step(
        "focused_date_window_audit_started",
        response=response,
    )
    date_window_response = await _focused_date_window_audited_response(
        response=response,
        preferred_model=preferred_model,
        request=request,
    )
    if date_window_response is not None:
        return await _stated_run_field_audited_response(
            response=date_window_response,
            preferred_model=preferred_model,
            request=request,
        )
    _log_runtime_readiness_step(
        "supported_date_gap_repair_started",
        response=response,
    )
    supported_date_gap_response = await _supported_date_gap_schema_repaired_response(
        response=response,
        preferred_model=preferred_model,
        request=request,
    )
    if supported_date_gap_response is not None:
        readiness_blocker = _optional_runtime_readiness_audit_blocker(
            response=supported_date_gap_response,
            request=request,
        )
        if readiness_blocker is None:
            return supported_date_gap_response
        if readiness_blocker == "stated_run_field_fidelity":
            audited_response = await _audit_stated_run_fields(
                response=supported_date_gap_response,
                preferred_model=preferred_model,
                request=request,
            )
            return audited_response or supported_date_gap_response
        return await _stated_run_field_audited_response(
            response=supported_date_gap_response,
            preferred_model=preferred_model,
            request=request,
        )
    if response.capability_question_focus is not None and (
        response.artifact_target == "none" or not _request_has_latest_result(request)
    ):
        if "capability_side_question_audit" in response.reason_codes:
            return response
        if _response_needs_testable_idea_repair(response=response, request=request):
            repaired_response = await _repair_incomplete_strategy_extraction(
                failed_response=response,
                preferred_model=preferred_model,
                request=request,
                asset_resolution_context=asset_resolution_context,
            )
            if repaired_response is not None:
                return await _stated_run_field_audited_response(
                    response=repaired_response,
                    preferred_model=preferred_model,
                    request=request,
                )
            context_response = await _unsupported_context_question_audited_response(
                response=response,
                preferred_model=preferred_model,
                request=request,
            )
            if context_response is not None:
                return context_response
        return response
    response = _vague_strategy_start_as_guidance(response)
    if _is_vague_strategy_start_guidance(response):
        return response
    response = _augment_strategy_assets_from_resolvable_context(
        response=response,
        request=request,
    )
    response = _clear_auto_simplified_strategy_when_rule_is_ambiguous(response)
    if _response_needs_signal_rule_plan(response):
        repaired_response = await _repair_incomplete_strategy_extraction(
            failed_response=response,
            preferred_model=preferred_model,
            request=request,
            asset_resolution_context=asset_resolution_context,
        )
        if repaired_response is not None:
            return await _stated_run_field_audited_response(
                response=repaired_response,
                preferred_model=preferred_model,
                request=request,
            )
    response = await _signal_rule_checked_response(
        response=response,
        preferred_model=preferred_model,
        request=request,
    )
    grounded_response = await _audit_executable_strategy_grounding(
        response=response,
        preferred_model=preferred_model,
        request=request,
    )
    if grounded_response is not None:
        response = grounded_response
        if response.requires_clarification:
            return response
    if _response_needs_indicator_default_grounding_repair(
        response=response,
        request=request,
    ):
        repaired_response = await _repair_incomplete_strategy_extraction(
            failed_response=response,
            preferred_model=preferred_model,
            request=request,
            asset_resolution_context=asset_resolution_context,
        )
        if repaired_response is not None:
            response = repaired_response
    if _response_needs_indicator_parameter_repair(response):
        repaired_response = await _repair_incomplete_strategy_extraction(
            failed_response=response,
            preferred_model=preferred_model,
            request=request,
            asset_resolution_context=asset_resolution_context,
        )
        if repaired_response is not None:
            response = repaired_response
    if _response_needs_launch_field_fidelity_repair(response=response):
        repaired_response = await _repair_incomplete_strategy_extraction(
            failed_response=response,
            preferred_model=preferred_model,
            request=request,
            asset_resolution_context=asset_resolution_context,
        )
        if repaired_response is not None:
            response = repaired_response
    if _response_needs_artifact_context_repair(response):
        repaired_response = await _repair_incomplete_strategy_extraction(
            failed_response=response,
            preferred_model=preferred_model,
            request=request,
            asset_resolution_context=asset_resolution_context,
        )
        if repaired_response is not None:
            return await _stated_run_field_audited_response(
                response=repaired_response,
                preferred_model=preferred_model,
                request=request,
            )
        # Entered only when the response already carries assistant text.
        return _carry_asset_blocker(response, asset_resolution_context)
    if _response_needs_structured_strategy_repair(response=response):
        repaired_response = await _repair_incomplete_strategy_extraction(
            failed_response=response,
            preferred_model=preferred_model,
            request=request,
            asset_resolution_context=asset_resolution_context,
        )
        if repaired_response is not None:
            return await _stated_run_field_audited_response(
                response=repaired_response,
                preferred_model=preferred_model,
                request=request,
            )
    if _response_needs_testable_idea_repair(response=response, request=request):
        repaired_response = await _repair_incomplete_strategy_extraction(
            failed_response=response,
            preferred_model=preferred_model,
            request=request,
            asset_resolution_context=asset_resolution_context,
        )
        if repaired_response is not None:
            return await _stated_run_field_audited_response(
                response=repaired_response,
                preferred_model=preferred_model,
                request=request,
            )
        context_response = await _unsupported_context_question_audited_response(
            response=response,
            preferred_model=preferred_model,
            request=request,
        )
        if context_response is not None:
            return context_response
    if (pending := retain_pending_focused_seed(response, request=request)) is not response:
        return pending
    if _response_replays_prior_strategy_without_current_turn_update(
        response=response,
        request=request,
    ):
        if _pending_dca_assumption_reply_needs_stated_run_field_audit(
            response=response,
            request=request,
        ):
            audited_response = await _audit_stated_run_fields(
                response=response,
                preferred_model=preferred_model,
                request=request,
            )
            if audited_response is not None:
                return audited_response
        planned_response = await _plan_artifact_edit_response(
            preferred_model=preferred_model,
            request=request,
            primary_draft=response.candidate_strategy_draft,
        )
        if planned_response is not None:
            return _carry_asset_blocker(planned_response, asset_resolution_context)
        raise contract_recovery.replay_without_update_error()
    audited_response = await _audit_stated_run_fields(
        response=response,
        preferred_model=preferred_model,
        request=request,
    )
    if audited_response is not None:
        response = audited_response
        date_window_response = await _focused_date_window_audited_response(
            response=response,
            preferred_model=preferred_model,
            request=request,
        )
        if date_window_response is not None:
            response = date_window_response
    conflict_response = await _audit_supported_strategy_capability_conflict(
        response=response,
        preferred_model=preferred_model,
        request=request,
    )
    if conflict_response is not None:
        response = await _underfilled_strategy_repaired_response(
            response=conflict_response,
            preferred_model=preferred_model,
            request=request,
        )
    grounded_response = await _audit_executable_strategy_grounding(
        response=response,
        preferred_model=preferred_model,
        request=request,
    )
    if grounded_response is not None:
        response = grounded_response
    response = _response_with_executable_fields_preferred_over_clarification_prose(
        response
    )
    if _structured_interpretation_has_required_shape(response, request=request):
        return response

    planned_response = await _plan_artifact_edit_response(
        preferred_model=preferred_model,
        request=request,
        rejected_response=response,
        primary_draft=response.candidate_strategy_draft,
    )
    if planned_response is not None:
        return _carry_asset_blocker(planned_response, asset_resolution_context)
    repaired_response = await _repair_incomplete_strategy_extraction(
        failed_response=response,
        preferred_model=preferred_model,
        request=request,
        asset_resolution_context=asset_resolution_context,
    )
    if repaired_response is not None:
        return await _stated_run_field_audited_response(
            response=repaired_response,
            preferred_model=preferred_model,
            request=request,
        )
    raise contract_recovery.incomplete_response_error(response=response, request=request)


async def _ready_active_artifact_edit_planned_response(
    *,
    response: LLMInterpretationResponse,
    preferred_model: str,
    request: InterpretationRequest,
) -> LLMInterpretationResponse | None:
    if _request_targets_no_active_pending_artifact_edit(request):
        last_stage_outcome = request.selected_thread_metadata.get("last_stage_outcome")
        if last_stage_outcome not in (None, "await_user_reply"):
            return None
        if response.semantic_turn_act == "new_idea":
            return None
        if response.task_relation == "new_task":
            return None
    if _selected_requested_field_base(request) == "asset_universe":
        snapshot = request.latest_task_snapshot
        if snapshot is None:
            return None
        if snapshot.active_confirmation_reference is None:
            if snapshot.pending_strategy_summary is None:
                return None
        if response.semantic_turn_act == "educational_question":
            return None
    if not (
        _request_targets_pending_artifact_assumption_edit(request)
        or _request_targets_post_result_artifact_edit(request)
        or _scoped_date_reply_carries_broader_edit(
            request, response.candidate_strategy_draft
        )
    ):
        return None
    if response.semantic_turn_act in {
        "approval",
        "retry_failed_action",
    }:
        return None
    if _refinement_reply_needs_full_interpretation(
        response=response,
        request=request,
    ):
        return None
    if response.semantic_turn_act == "result_followup" and (
        _selected_requested_field_base(request) == "refinement"
        or not _request_has_planner_edit_candidate_after_model_failure(request)
    ):
        # A refine prompt sits right on a result card, so result fact
        # questions ("how did it do in 2022?") are common there; the
        # interpreter's own result classification must keep its routing
        # instead of being overridden by a planned edit confirmation.
        return None
    if _plain_requested_asset_answer_can_use_provider_resolution(
        response=response,
        request=request,
        draft_has_valid_requested_asset_update=_draft_has_valid_requested_asset_update,
    ):
        return None

    async def _planned_with_primary() -> LLMInterpretationResponse | None:
        return await _plan_pending_artifact_assumption_edit(
            request=request,
            preferred_model=preferred_model,
            primary_draft=response.candidate_strategy_draft,
        )

    if _active_artifact_asset_universe_operation_needs_planner(
        response=response,
        request=request,
    ):
        planned = await _planned_with_primary()
        if planned is not None:
            return planned
        return _asset_universe_operation_clarification_response(
            response=response,
            request=request,
        )
    if _llm_strategy_draft_has_supported_artifact_assumption_edit(
        response.candidate_strategy_draft
    ):
        return await _planned_with_primary()
    planned = await _planned_with_primary()
    if planned is None or planned.requires_clarification:
        return None
    return planned


def _request_targets_no_active_pending_artifact_edit(
    request: InterpretationRequest,
) -> bool:
    requested_field = _selected_requested_field_base(request)
    snapshot = request.latest_task_snapshot
    return bool(
        requested_field in ARTIFACT_EDIT_PENDING_FIELDS
        and snapshot is not None
        and snapshot.pending_strategy_summary is not None
        and snapshot.active_confirmation_reference is None
    )


def _response_can_skip_optional_runtime_readiness_audits(
    *,
    response: LLMInterpretationResponse,
    request: InterpretationRequest,
) -> bool:
    blocker = _optional_runtime_readiness_audit_blocker(
        response=response,
        request=request,
    )
    if blocker is None:
        return True
    logger.debug(
        "Structured interpreter runtime readiness skip blocked reason={} "
        "intent={} semantic_turn_act={} strategy_type={}",
        blocker,
        response.intent,
        response.semantic_turn_act,
        canonical_strategy_type(response.candidate_strategy_draft.strategy_type),
        blocker=blocker,
        intent=response.intent,
        semantic_turn_act=response.semantic_turn_act,
        strategy_type=canonical_strategy_type(
            response.candidate_strategy_draft.strategy_type
        ),
    )
    return False


def _optional_runtime_readiness_audit_blocker(
    *,
    response: LLMInterpretationResponse,
    request: InterpretationRequest,
) -> str | None:
    if response.intent not in {"strategy_drafting", "backtest_execution"}:
        return "unsupported_intent"
    if response.semantic_turn_act != "new_idea":
        return "not_new_idea"
    if (
        response.requires_clarification
        or response.missing_required_fields
        or response.ambiguous_fields
        or response.unsupported_constraints
        or response.capability_question_focus is not None
        or response.context_question_focus is not None
    ):
        return "pending_clarification_or_constraint"
    draft = response.candidate_strategy_draft
    strategy_type = executable_strategy_type(draft.model_dump(mode="python"))
    if strategy_type not in SUPPORTED_STRATEGY_TYPES:
        return "unsupported_strategy_type"
    if _llm_strategy_draft_has_rule_or_indicator_fields(draft):
        return "rule_or_indicator_fields"
    if _capability_required_missing_fields_for_canonical_strategy([], draft=draft):
        return "missing_required_execution_fields"
    if not _structured_interpretation_has_required_shape(response, request=request):
        return "required_shape_missing"
    if _response_replays_prior_strategy_without_current_turn_update(
        response=response,
        request=request,
    ):
        return "prior_strategy_replay"
    if _response_needs_launch_field_fidelity_repair(response=response):
        return "launch_field_fidelity"
    if _response_needs_executable_strategy_grounding_audit(response=response):
        return "executable_strategy_grounding"
    if _response_needs_supported_strategy_capability_conflict_audit(response):
        return "capability_conflict"
    if not _draft_asset_universe_has_exact_provider_symbols(draft):
        return "asset_universe_not_exact_provider_symbols"
    if _response_needs_missing_benchmark_fidelity_audit(response):
        return "missing_benchmark_fidelity"
    if (
        "stated_run_field_fidelity_audit" not in response.reason_codes
        and _draft_missing_exact_ticker_benchmark_needs_fidelity_audit(
            draft,
            current_message=request.current_user_message,
        )
    ):
        return "missing_benchmark_fidelity"
    if _draft_has_unprovenanced_benchmark(
        draft
    ) and not _draft_has_supported_default_benchmark(draft):
        return "unprovenanced_benchmark"
    if has_execution_cost_candidate(draft.extra_parameters):
        return "stated_run_field_fidelity"
    if _response_needs_stated_timeframe_fidelity_audit(response):
        return "stated_run_field_fidelity"
    if _response_has_current_message_date_range_reconciliation(
        response=response,
        request=request,
    ):
        return "date_range_reconciliation"
    if _response_needs_temporal_runtime_repair(response=response, request=request):
        return "temporal_runtime_repair"
    if canonical_strategy_type(
        draft.strategy_type
    ) == "dca_accumulation" and _dca_response_needs_semantic_field_audit(response):
        return "dca_semantic_field_audit"
    if _response_needs_stated_starting_capital_recheck(
        response=response,
        request=request,
    ):
        return "stated_starting_capital_recheck"
    return None


def _draft_asset_universe_has_exact_provider_symbols(
    draft: LLMStrategyDraft,
) -> bool:
    symbols = [
        str(symbol or "").strip()
        for symbol in draft.asset_universe
        if str(symbol or "").strip()
    ]
    if not symbols:
        return False
    for symbol in symbols:
        if not is_ticker_like_query(symbol):
            return False
        try:
            resolution = _resolve_asset_candidate(
                symbol,
                field="asset_universe",
                source="llm_extraction",
            )
        except ValueError:
            return False
        if resolution.status != "resolved" or resolution.asset is None:
            return False
        if resolution.asset.canonical_symbol.upper() != symbol.upper():
            return False
    return True


def _response_needs_stated_timeframe_fidelity_audit(
    response: LLMInterpretationResponse,
) -> bool:
    if "stated_run_field_fidelity_audit" in response.reason_codes:
        return False
    draft = response.candidate_strategy_draft
    return _llm_value_is_empty(
        draft.timeframe
    ) and _draft_has_timeframe_evidence_for_audit(draft)


def _draft_has_supported_default_benchmark(draft: LLMStrategyDraft) -> bool:
    benchmark = _normalized_extracted_symbol(draft.comparison_baseline)
    if benchmark is None:
        return False
    asset_class = _single_provider_asset_class_for_draft(draft)
    if asset_class == "equity":
        return benchmark == "SPY"
    if asset_class == "crypto":
        return benchmark == "BTC"
    return False


def _single_provider_asset_class_for_draft(draft: LLMStrategyDraft) -> str | None:
    symbols = [
        str(symbol or "").strip()
        for symbol in draft.asset_universe
        if str(symbol or "").strip()
    ]
    asset_classes: set[str] = set()
    for symbol in symbols:
        try:
            resolution = _resolve_asset_candidate(
                symbol,
                field="asset_universe",
                source="llm_extraction",
            )
        except ValueError:
            return None
        if resolution.status != "resolved" or resolution.asset is None:
            return None
        asset_class = str(resolution.asset.asset_class or "").strip().lower()
        if asset_class:
            asset_classes.add(asset_class)
    if len(asset_classes) == 1:
        return next(iter(asset_classes))
    if asset_classes:
        return None
    explicit_asset_class = str(draft.asset_class or "").strip().lower()
    if explicit_asset_class in {"equity", "crypto"}:
        return explicit_asset_class
    return None


async def _supported_date_gap_schema_repaired_response(
    *,
    response: LLMInterpretationResponse,
    preferred_model: str,
    request: InterpretationRequest,
) -> LLMInterpretationResponse | None:
    if not _response_has_repairable_current_turn_date_gap(
        response=response,
        request=request,
    ):
        return None
    return await _repair_incomplete_strategy_extraction(
        failed_response=response,
        preferred_model=preferred_model,
        request=request,
    )


async def _plan_artifact_edit_response(
    *,
    preferred_model: str,
    request: InterpretationRequest,
    rejected_response: LLMInterpretationResponse | None = None,
    primary_draft: LLMStrategyDraft | None = None,
) -> LLMInterpretationResponse | None:
    planned_response = None
    if rejected_response is None or not _refinement_reply_needs_full_interpretation(
        response=rejected_response,
        request=request,
    ):
        planned_response = await _plan_pending_artifact_assumption_edit(
            request=request,
            preferred_model=preferred_model,
            primary_draft=primary_draft,
        )
    if planned_response is None:
        planned_response = await _plan_focused_artifact_edit(
            model_name=preferred_model,
            request=request,
        )
    if planned_response is None:
        return None
    return await _stated_run_field_audited_response(
        response=planned_response,
        preferred_model=preferred_model,
        request=request,
    )


async def _stated_run_field_audited_response(
    *,
    response: LLMInterpretationResponse,
    preferred_model: str,
    request: InterpretationRequest,
) -> LLMInterpretationResponse:
    grounded_response = await _audit_executable_strategy_grounding(
        response=response,
        preferred_model=preferred_model,
        request=request,
    )
    if grounded_response is not None:
        response = grounded_response
        if response.requires_clarification:
            return response
    date_window_response = await _focused_date_window_audited_response(
        response=response,
        preferred_model=preferred_model,
        request=request,
    )
    if date_window_response is not None:
        response = date_window_response
    audited_response = await _audit_stated_run_fields(
        response=response,
        preferred_model=preferred_model,
        request=request,
    )
    if audited_response is not None:
        response = audited_response
        date_window_response = await _focused_date_window_audited_response(
            response=response,
            preferred_model=preferred_model,
            request=request,
        )
        if date_window_response is not None:
            response = date_window_response
    conflict_response = await _audit_supported_strategy_capability_conflict(
        response=response,
        preferred_model=preferred_model,
        request=request,
    )
    if conflict_response is not None:
        response = await _underfilled_strategy_repaired_response(
            response=conflict_response,
            preferred_model=preferred_model,
            request=request,
        )
    if _response_needs_supported_signal_rule_recovery(
        response,
        current_user_message=request.current_user_message,
    ) or _llm_signal_strategy_is_underfilled(response.candidate_strategy_draft):
        response = await _signal_rule_checked_response(
            response=response,
            preferred_model=preferred_model,
            request=request,
        )
    return _response_with_executable_fields_preferred_over_clarification_prose(response)


async def _underfilled_strategy_repaired_response(
    *,
    response: LLMInterpretationResponse,
    preferred_model: str,
    request: InterpretationRequest,
) -> LLMInterpretationResponse:
    if _structured_interpretation_has_required_shape(response, request=request):
        return response
    repaired_response = await _repair_incomplete_strategy_extraction(
        failed_response=response,
        preferred_model=preferred_model,
        request=request,
    )
    return repaired_response or response


async def _audit_stated_run_fields(
    *,
    response: LLMInterpretationResponse,
    preferred_model: str,
    request: InterpretationRequest,
    required: bool = False,
) -> LLMInterpretationResponse | None:
    audited_response = await _audit_stated_run_field_fidelity(
        response=response,
        preferred_model=preferred_model,
        request=request,
        required=required,
    )
    if audited_response is not None:
        return _response_with_resolved_runtime_date_range(
            response=audited_response,
            request=request,
        )
    capital_response = await _audit_stated_starting_capital_fidelity(
        response=response,
        request=request,
    )
    if capital_response is not None:
        return _response_with_resolved_runtime_date_range(
            response=capital_response,
            request=request,
        )
    return None


async def _plan_focused_artifact_edit(
    *,
    model_name: str,
    request: InterpretationRequest,
) -> LLMInterpretationResponse | None:
    messages = _focused_artifact_edit_messages(request)
    if messages is None:
        return None
    try:
        response = await invoke_openrouter_json_schema(
            task="interpretation",
            messages=_openrouter_wire_messages(messages),
            schema_model=LLMInterpretationResponse,
            schema_name="LLMInterpretationResponse",
            model_name=model_name,
        )
    except Exception:
        return None
    if not isinstance(response, LLMInterpretationResponse):
        return None
    response = _normalize_response_for_runtime_context(response, request=request)
    response = await _signal_rule_checked_response(
        response=response,
        preferred_model=model_name,
        request=request,
    )
    if not _structured_interpretation_has_required_shape(response, request=request):
        return None
    return response


@turn_execution.focused_repair
async def _repair_incomplete_strategy_extraction(
    *,
    failed_response: LLMInterpretationResponse,
    preferred_model: str,
    request: InterpretationRequest,
    asset_resolution_context: str | None = None,
) -> LLMInterpretationResponse | None:
    if not _strategy_extraction_repair_is_allowed(failed_response, request=request):
        return None
    schema_name = "FocusedStrategyExtraction"
    trigger_reason = "required_strategy_shape_missing"
    annotate_repair = partial(_annotate_interpretation_repair, schema_name=schema_name, before=failed_response, trigger_reason=trigger_reason)
    messages = _focused_strategy_extraction_messages(request)
    for model_name in _unique_repair_models(
        preferred_model,
        task=_INTERPRETATION_REPAIR_TASK,
    ):
        try:
            extraction = await invoke_openrouter_json_schema(
                task=_INTERPRETATION_REPAIR_TASK,
                messages=_openrouter_wire_messages(messages),
                schema_model=FocusedStrategyExtraction,
                schema_name=schema_name,
                model_name=model_name,
            )
        except Exception:
            annotate_repair(after=failed_response, repair_applied=False, no_op_reason="provider_call_failed")
            continue
        if not isinstance(extraction, FocusedStrategyExtraction):
            annotate_repair(after=failed_response, repair_applied=False, no_op_reason="invalid_provider_result")
            continue
        if not _focused_strategy_extraction_has_material_fields(extraction):
            annotate_repair(after=failed_response, repair_applied=False, no_op_reason="no_material_fields")
            if not extraction.is_testable_strategy:
                # A clear "no strategy here" is an answer; only a read that
                # calls the turn testable yet extracts nothing moves on.
                return None
            continue
        base_response = failed_response
        # The pending setup fills the re-read only for a turn that answers
        # the runtime's question; a fresh task is filled from itself alone.
        turn = repaired_turn_act(
            base_act=failed_response.semantic_turn_act,
            base_relation=failed_response.task_relation,
            request=request,
        )
        if turn.answers_pending and _selected_requested_field_base(request):
            pending_draft = _pending_strategy_draft_from_request_or_response(
                response=failed_response,
                request=request,
            )
            if pending_draft is not None:
                base_response = failed_response.model_copy(
                    update={"candidate_strategy_draft": pending_draft}
                )
        response = _response_from_focused_strategy_extraction(
            extraction=extraction,
            request=request,
            base_response=base_response,
        )
        response = _normalize_response_for_runtime_context(
            response,
            request=request,
            asset_resolution_context=asset_resolution_context,
        )
        response = _augment_strategy_assets_from_resolvable_context(
            response=response,
            request=request,
        )
        if not _response_can_skip_optional_runtime_readiness_audits(response=response, request=request):
            response = await _signal_rule_checked_response(
                response=response,
                preferred_model=model_name,
                request=request,
            )
            conflict_response = await _audit_supported_strategy_capability_conflict(
                response=response,
                preferred_model=model_name,
                request=request,
            )
            if conflict_response is not None:
                response = conflict_response
            date_window_response = await _focused_date_window_audited_response(
                response=response,
                preferred_model=model_name,
                request=request,
            )
            if date_window_response is not None:
                response = date_window_response
        audited_response = await _audit_stated_run_fields(
            response=response,
            preferred_model=model_name,
            request=request,
            required=_llm_strategy_draft_has_concrete_execution_target(response.candidate_strategy_draft),
        )
        if audited_response is not None:
            response = audited_response
        if _structured_interpretation_has_required_shape(response, request=request):
            annotate_repair(after=response, repair_applied=True)
            return response
        annotate_repair(after=failed_response, repair_applied=False, no_op_reason="required_shape_rejected")
    return None


async def _focused_date_window_audited_response(
    *,
    response: LLMInterpretationResponse,
    preferred_model: str,
    request: InterpretationRequest,
) -> LLMInterpretationResponse | None:
    if not _response_needs_focused_date_window_intent_repair(
        response=response,
        request=request,
    ):
        return None
    schema_name = "FocusedDateWindowExtraction"
    trigger_reason = "date_window_intent_uncertain"
    annotate_repair = partial(_annotate_interpretation_repair, schema_name=schema_name, before=response, trigger_reason=trigger_reason)
    messages = _focused_date_window_extraction_messages(
        response=response,
        request=request,
    )
    for model_name in _unique_repair_models(
        preferred_model,
        task=_INTERPRETATION_REPAIR_TASK,
    ):
        try:
            extraction = await invoke_openrouter_json_schema(
                task=_INTERPRETATION_REPAIR_TASK,
                messages=messages,
                schema_model=FocusedDateWindowExtraction,
                schema_name=schema_name,
                model_name=model_name,
            )
        except Exception as exc:
            annotate_repair(after=response, repair_applied=False, no_op_reason="provider_call_failed")
            log_openrouter_failure(
                task=_INTERPRETATION_REPAIR_TASK,
                model_name=model_name,
                exc=exc,
                message="Focused date-window extraction failed; preserving draft dates",
            )
            continue
        if not isinstance(extraction, FocusedDateWindowExtraction):
            annotate_repair(after=response, repair_applied=False, no_op_reason="invalid_provider_result")
            continue
        if not extraction.has_date_window:
            # A well-formed "no window" is authoritative; remaining repair models
            # are not asked.
            annotate_repair(after=response, repair_applied=False, no_op_reason="no_date_window")
            return None
        repaired = _response_from_focused_date_window_extraction(
            response=response,
            extraction=extraction,
            request=request,
        )
        if repaired is not None:
            # The focused extraction can name the latest-result reference; the
            # binder runs again because normalization already passed.
            repaired = _response_with_latest_result_window_bound(
                repaired,
                request=request,
            )
            annotate_repair(after=repaired, repair_applied=True)
            return repaired
        annotate_repair(after=response, repair_applied=False, no_op_reason="invalid_date_window")
    return None


def _response_needs_focused_date_window_intent_repair(
    *,
    response: LLMInterpretationResponse,
    request: InterpretationRequest,
) -> bool:
    if "latest_result_window_bound" in response.reason_codes:
        # The window was bound from the canonical latest result, not from
        # current-turn date text; re-auditing message evidence would strip it.
        return False
    if "focused_date_window_intent_repair" in response.reason_codes:
        return False
    # A recovery/unsupported draft that dropped the user's stated window recovers it
    # here, so the refusal keeps the window (never nulled, never trailing-defaulted).
    if _response_has_repairable_recovery_date_gap(response=response, request=request):
        return True
    pending_date_answer = _request_has_pending_date_answer_context(request)
    if (
        response.intent not in {"strategy_drafting", "backtest_execution"}
        and not pending_date_answer
    ):
        return False
    pending_supported_date_answer = (
        _pending_supported_execution_date_answer_can_use_focused_audit(
            response=response,
            request=request,
        )
    )
    draft = response.candidate_strategy_draft
    if _post_result_dateless_execution_draft(response=response, request=request):
        return True
    has_repairable_current_turn_date_gap = _response_has_repairable_current_turn_date_gap(
        response=response,
        request=request,
    )
    if response.task_relation != "new_task" and not (
        pending_date_answer
        or pending_supported_date_answer
        or has_repairable_current_turn_date_gap
    ):
        return False
    has_material_evidence = (
        _request_current_turn_has_material_execution_evidence(request)
        or _draft_has_supported_capability_shape_for_date_repair(draft)
        or pending_date_answer
    )
    has_semantic_date_evidence = _draft_has_semantic_date_window_evidence(draft)
    if response.semantic_turn_act == "answer_pending_need" and not (
        (
            has_material_evidence
            and _response_has_pending_base_field(response, "date_range")
        )
        or pending_supported_date_answer
        or has_repairable_current_turn_date_gap
    ):
        return False
    if (
        response.semantic_turn_act
        in {
            "approval",
            "refine_current_idea",
            "result_followup",
            "retry_failed_action",
            "unsupported_request",
        }
        and not pending_date_answer
    ):
        return False
    if response.semantic_turn_act == "educational_question" and not pending_date_answer:
        return False
    if (
        not pending_date_answer
        and not has_material_evidence
        and not _supported_partial_draft_has_repairable_shape(draft)
    ):
        return False
    if resolve_date_range_intent(draft.date_range_intent) is not None:
        # A calendar-year intent whose evidence is not the bare year the user
        # stated (or that carries no evidence at all) cannot vouch for the
        # drafted window — the draft matching its own intent proves nothing.
        if (
            draft.date_range_intent is not None
            and draft.date_range_intent.kind == "calendar_year"
            and not _date_range_intent_can_safely_suppress_focused_repair(draft)
        ):
            return True
        if has_semantic_date_evidence:
            if _complete_date_range_matches_resolved_intent(draft):
                return False
            return True
    has_complete_date_range = _has_complete_date_range_payload(
        normalize_date_range_candidate(draft.date_range)
    )
    has_pending_date_range = _response_has_pending_base_field(response, "date_range")
    if (
        has_complete_date_range
        and response.requires_clarification
        and not has_pending_date_range
    ):
        return False
    if has_pending_date_range:
        return (
            has_material_evidence
            or has_semantic_date_evidence
            or _supported_partial_draft_has_repairable_shape(draft)
        )
    if _llm_value_is_empty(draft.date_range):
        return (
            pending_date_answer
            or has_semantic_date_evidence
            or has_repairable_current_turn_date_gap
        )
    if has_partial_explicit_date_range(draft.date_range):
        return True
    if has_semantic_date_evidence:
        return True
    if _complete_date_range_needs_current_turn_date_audit(
        response=response,
        request=request,
        has_complete_date_range=has_complete_date_range,
        has_material_execution_evidence=(
            _request_current_turn_has_material_execution_evidence(request)
        ),
    ):
        return True
    if not _llm_value_is_empty(draft.date_range_raw_text):
        return True
    return has_repairable_current_turn_date_gap


async def _plan_pending_artifact_assumption_edit(
    *,
    request: InterpretationRequest,
    preferred_model: str,
    require_failure_edit_evidence: bool = False,
    primary_draft: LLMStrategyDraft | None = None,
) -> LLMInterpretationResponse | None:
    if not (
        _request_targets_pending_artifact_assumption_edit(request)
        or _request_targets_post_result_artifact_edit(request)
        or _scoped_date_reply_carries_broader_edit(request, primary_draft)
    ):
        return None
    if (
        require_failure_edit_evidence
        and not _request_has_planner_edit_candidate_after_model_failure(request)
    ):
        return None
    snapshot = request.latest_task_snapshot
    prior_strategy = _prior_strategy_payload(request)
    if prior_strategy is None:
        # Post-result surface: plan against the strategy that actually ran.
        reconstructed = _current_artifact_strategy(request)
        if reconstructed is not None:
            prior_strategy = reconstructed.model_dump(mode="json")
    active_confirmation = snapshot.active_confirmation_reference.model_dump(mode="json") if snapshot is not None and snapshot.active_confirmation_reference is not None else None  # fmt: skip
    resolver = _asset_edit_symbol_resolver(_resolve_asset_candidate)
    # fmt: off
    plan = await plan_artifact_assumption_edit(
        current_user_message=request.current_user_message,
        prior_strategy=prior_strategy,
        active_confirmation=active_confirmation,
        preferred_model=preferred_model,
        language=request.user.language_preference,
        required_targets=_required_edit_targets_from_primary_draft(primary_draft, current_strategy=_current_artifact_strategy(request), request=request),
        materialized_targets_for_plan=lambda candidate: materialized_artifact_edit_targets(candidate, request=request, asset_symbol_resolver=resolver, resolve_asset_candidate=_resolve_asset_candidate, primary_draft=primary_draft),
        stated_operations=stated_edit_operations(primary_draft, current_strategy=_current_artifact_strategy(request), request=request),
    )
    # fmt: on
    if plan is None:
        return None
    # Recurring fields reshape a non-recurring artifact regardless of which
    # artifact-edit entry point produced the plan. The edit-operation set cannot
    # change strategy family, so let the full interpretation path own that turn.
    prior = _current_artifact_strategy(request)
    if _edit_plan_reshapes_non_recurring_strategy(
        plan,
        prior_strategy_type=prior.strategy_type if prior is not None else None,
    ):
        return None
    return _response_from_artifact_assumption_edit_plan(
        plan=plan,
        request=request,
        asset_symbol_resolver=resolver,
        primary_draft=primary_draft,
    )


def _request_has_planner_edit_candidate_after_model_failure(
    request: InterpretationRequest,
) -> bool:
    requested_field = _field_path_base(
        request.selected_thread_metadata.get("requested_field")
    )
    if requested_field in ARTIFACT_EDIT_PENDING_FIELDS:
        return True

    snapshot = request.latest_task_snapshot
    prior = (
        snapshot.pending_strategy_summary or snapshot.confirmed_strategy_summary
        if snapshot is not None
        else None
    )
    if prior is None:
        return False

    def _resolve_candidate(query: str) -> AssetResolution | None:
        try:
            return _resolve_asset_candidate(
                query,
                field="asset_universe[0]",
                source="user_mention",
            )
        except ValueError:
            return None

    current_symbols = {
        symbol
        for asset in provider_ticker_assets_from_text(
            request.current_user_message,
            resolve_candidate=_resolve_candidate,
            limit=10,
        )
        if (symbol := _normalized_ticker_symbol(getattr(asset, "canonical_symbol", None)))
        is not None
    }
    if not current_symbols:
        return False
    prior_symbols = {
        symbol
        for value in prior.asset_universe
        if (symbol := _normalized_ticker_symbol(value)) is not None
    }
    prior_benchmark = _normalized_ticker_symbol(prior.comparison_baseline)
    if prior_benchmark is not None:
        prior_symbols.add(prior_benchmark)
    return not current_symbols <= prior_symbols


async def _signal_rule_checked_response(
    *,
    response: LLMInterpretationResponse,
    preferred_model: str,
    request: InterpretationRequest,
) -> LLMInterpretationResponse:
    pending_rule_answer = await _repair_pending_signal_rule_answer_if_needed(
        response=response,
        preferred_model=preferred_model,
        request=request,
    )
    response = pending_rule_answer or response
    recovered_signal_rule = await _recover_supported_signal_rule_from_draft_if_needed(
        response=response,
        preferred_model=preferred_model,
        request=request,
    )
    response = recovered_signal_rule or response
    planned = (
        await _plan_underfilled_signal_rule_if_needed(
            response=response,
            preferred_model=preferred_model,
            request=request,
        )
        or response
    )
    audited = await _audit_signal_rule_grounding_if_needed(
        response=planned,
        preferred_model=preferred_model,
        request=request,
    )
    return audited or planned


async def _recover_supported_signal_rule_from_draft_if_needed(
    *,
    response: LLMInterpretationResponse,
    preferred_model: str,
    request: InterpretationRequest,
) -> LLMInterpretationResponse | None:
    if not _response_needs_supported_signal_rule_recovery(
        response,
        current_user_message=request.current_user_message,
    ):
        return None
    planning_response = _supported_signal_rule_planning_response(response)
    planning_response = _augment_signal_planning_context_from_message(
        response=planning_response,
        request=request,
    )
    plan = await repair_signal_rule_plan(
        current_user_message=request.current_user_message,
        candidate_strategy=planning_response.candidate_strategy_draft.model_dump(
            mode="json"
        ),
        prior_strategy=_prior_strategy_payload(request),
        preferred_model=preferred_model,
    )
    if plan is None or plan.outcome != "ready_to_confirm":
        return None
    return _response_with_canonical_interpreter_assets(
        _response_from_signal_rule_plan(
            response=planning_response,
            plan=plan,
        )
    )


def _augment_signal_planning_context_from_message(
    *,
    response: LLMInterpretationResponse,
    request: InterpretationRequest,
) -> LLMInterpretationResponse:
    del request
    return response


def _augment_strategy_assets_from_resolvable_context(
    *,
    response: LLMInterpretationResponse,
    request: InterpretationRequest,
) -> LLMInterpretationResponse:
    del request
    return response


def _resolved_asset_mentions_from_message(message: str) -> list[Any]:
    def _resolve_candidate(query: str) -> AssetResolution | None:
        try:
            return _resolve_asset_candidate(
                query,
                field="asset_universe[0]",
                source="user_mention",
            )
        except ValueError:
            return None

    return [
        mention.asset
        for mention in grounded_asset_mentions_from_text(
            message,
            resolve_candidate=_resolve_candidate,
            limit=5,
        )
    ]


async def _repair_pending_signal_rule_answer_if_needed(
    *,
    response: LLMInterpretationResponse,
    preferred_model: str,
    request: InterpretationRequest,
) -> LLMInterpretationResponse | None:
    if not _request_targets_pending_signal_rule(request):
        return None
    if _response_needs_signal_rule_grounding_audit(response):
        return None
    prior_strategy = _prior_strategy_payload(request)
    if not prior_strategy:
        return None
    if canonical_strategy_type(prior_strategy.get("strategy_type")) != "signal_strategy":
        return None

    planning_response = _pending_signal_rule_planning_response(
        response=response,
        prior_strategy=prior_strategy,
        current_user_message=request.current_user_message,
    )
    plan = await repair_signal_rule_plan(
        current_user_message=request.current_user_message,
        candidate_strategy=planning_response.candidate_strategy_draft.model_dump(
            mode="json"
        ),
        prior_strategy=prior_strategy,
        preferred_model=preferred_model,
    )
    if plan is None:
        return None
    return _response_with_canonical_interpreter_assets(
        _response_from_signal_rule_plan(
            response=planning_response,
            plan=plan,
        )
    )


async def _plan_underfilled_signal_rule_if_needed(
    *,
    response: LLMInterpretationResponse,
    preferred_model: str,
    request: InterpretationRequest,
) -> LLMInterpretationResponse | None:
    if not _response_needs_signal_rule_plan(response):
        return None
    plan = await repair_signal_rule_plan(
        current_user_message=request.current_user_message,
        candidate_strategy=response.candidate_strategy_draft.model_dump(mode="json"),
        prior_strategy=_prior_strategy_payload(request),
        preferred_model=preferred_model,
    )
    if plan is None:
        return None
    return _response_with_canonical_interpreter_assets(
        _response_from_signal_rule_plan(
            response=response,
            plan=plan,
        )
    )


def _unique_repair_models(
    preferred_model: str,
    *,
    task: OpenRouterTask = "interpretation",
) -> list[str]:
    task_candidates = openrouter_structured_model_candidates(task=task)
    if task == "interpretation":
        candidates = [preferred_model, *task_candidates]
    else:
        candidates = [*task_candidates, preferred_model]
    seen: set[str] = set()
    ordered: list[str] = []
    for model_name in candidates:
        if not model_name or model_name in seen:
            continue
        seen.add(model_name)
        ordered.append(model_name)
    return ordered


def _response_needs_testable_idea_repair(
    *,
    response: LLMInterpretationResponse,
    request: InterpretationRequest,
) -> bool:
    if _is_vague_strategy_start_guidance(response):
        return False
    requested_field = _field_path_base(
        request.selected_thread_metadata.get("requested_field")
    )
    if requested_field:
        return False
    draft = response.candidate_strategy_draft
    if _supported_anchor_needs_focused_run_window_repair(
        response=response,
        request=request,
    ):
        return True
    if _supported_partial_strategy_needs_focused_schema_repair(
        response=response,
        request=request,
    ):
        return True
    if _noncanonical_strategy_text_needs_focused_schema_repair(
        response=response,
        request=request,
    ):
        return True
    if (
        response.intent == "unsupported_or_out_of_scope"
        and response.semantic_turn_act == "unsupported_request"
        and any(
            item.category == "unsupported_strategy_logic"
            for item in response.unsupported_constraints
        )
        and bool(draft.raw_user_phrasing or draft.strategy_thesis)
    ):
        return True
    if _llm_strategy_draft_has_semantic_execution_anchor(draft):
        return False
    if (
        response.intent in {"strategy_drafting", "backtest_execution"}
        and response.requires_clarification
        and bool(response.assistant_response)
        and bool(draft.raw_user_phrasing or draft.strategy_thesis)
    ):
        return True
    if (
        response.intent == "unsupported_or_out_of_scope"
        and response.semantic_turn_act == "unsupported_request"
    ):
        return True
    if response.intent in {"beginner_guidance", "conversation_followup"} and (
        response.semantic_turn_act == "unsupported_request"
    ):
        return True
    if response.intent in {"beginner_guidance", "conversation_followup"} and (
        response.semantic_turn_act in {None, "educational_question", "new_idea"}
    ):
        return True
    return False


def _supported_anchor_needs_focused_run_window_repair(
    *,
    response: LLMInterpretationResponse,
    request: InterpretationRequest,
) -> bool:
    if not (
        response.intent in {"strategy_drafting", "backtest_execution"}
        and response.requires_clarification
        and bool(response.assistant_response)
    ):
        return False
    if _semantic_turn_act_blocks_supported_schema_repair(
        response=response,
        request=request,
    ):
        return False
    if (
        response.capability_question_focus is not None
        or response.context_question_focus is not None
        or response.unsupported_constraints
        or response.ambiguous_fields
    ):
        return False
    if not _request_current_turn_has_material_execution_evidence(request):
        return False
    draft = response.candidate_strategy_draft
    if canonical_strategy_type(draft.strategy_type) not in {
        "buy_and_hold",
        "dca_accumulation",
        "indicator_threshold",
        "signal_strategy",
    }:
        return False
    if not (draft.raw_user_phrasing or draft.strategy_thesis):
        return False
    return _llm_value_is_empty(draft.date_range) and (
        _date_range_from_intent_or_bounded_evidence(draft) is None
    )


def _supported_partial_strategy_needs_focused_schema_repair(
    *,
    response: LLMInterpretationResponse,
    request: InterpretationRequest,
) -> bool:
    if not (
        response.intent in {"strategy_drafting", "backtest_execution"}
        and response.requires_clarification
        and bool(response.assistant_response)
    ):
        return False
    if _semantic_turn_act_blocks_supported_schema_repair(
        response=response,
        request=request,
    ):
        return False
    if (
        response.capability_question_focus is not None
        or response.context_question_focus is not None
        or response.unsupported_constraints
        or response.ambiguous_fields
    ):
        return False
    draft = response.candidate_strategy_draft
    if canonical_strategy_type(draft.strategy_type) not in {
        "buy_and_hold",
        "dca_accumulation",
        "indicator_threshold",
        "signal_strategy",
    }:
        return False
    if not (
        draft.raw_user_phrasing
        or draft.strategy_thesis
        or request.current_user_message.strip()
    ):
        return False
    missing_fields = {
        _field_path_base(field)
        for field in response.missing_required_fields
        if str(field).strip()
    }
    if not missing_fields:
        return _llm_value_is_empty(
            draft.date_range
        ) and _supported_partial_draft_has_repairable_shape(draft)
    if not missing_fields.intersection(
        {
            "asset_universe",
            "capital_amount",
            "cadence",
            "date_range",
            "entry_logic",
            "entry_rule",
            "entry_threshold",
            "exit_logic",
            "exit_rule",
            "exit_threshold",
            "indicator",
            "indicator_period",
            "rule_spec",
        }
    ):
        return False
    return _supported_partial_draft_has_repairable_shape(draft)


def _noncanonical_strategy_text_needs_focused_schema_repair(
    *,
    response: LLMInterpretationResponse,
    request: InterpretationRequest,
) -> bool:
    if response.intent not in {
        "backtest_execution",
        "beginner_guidance",
        "conversation_followup",
        "strategy_drafting",
        "unsupported_or_out_of_scope",
    }:
        return False
    if not (
        response.requires_clarification
        and bool(response.assistant_response)
        and _request_current_turn_has_material_execution_evidence(request)
    ):
        return False
    if (
        response.capability_question_focus is not None
        or response.context_question_focus is not None
        or response.unsupported_constraints
        or response.ambiguous_fields
    ):
        return False
    if response.semantic_turn_act in {
        "answer_pending_need",
        "approval",
        "educational_question",
        "refine_current_idea",
        "result_followup",
        "retry_failed_action",
    }:
        return False
    draft = response.candidate_strategy_draft
    if canonical_strategy_type(draft.strategy_type) in SUPPORTED_STRATEGY_TYPES:
        return False
    if _llm_strategy_draft_has_structured_rule_or_indicator_fields(draft):
        return False
    return bool(
        draft.raw_user_phrasing
        or draft.strategy_thesis
        or draft.strategy_type
        or request.current_user_message.strip()
    )


def _semantic_turn_act_blocks_supported_schema_repair(
    *,
    response: LLMInterpretationResponse,
    request: InterpretationRequest,
) -> bool:
    if response.semantic_turn_act == "answer_pending_need":
        return _request_has_active_strategy_context(
            request
        ) and not _request_current_turn_has_material_execution_evidence(request)
    return response.semantic_turn_act in {
        "approval",
        "educational_question",
        "refine_current_idea",
        "result_followup",
        "retry_failed_action",
        "unsupported_request",
    }


def _response_needs_material_evidence_strategy_repair(
    *,
    response: LLMInterpretationResponse,
    request: InterpretationRequest,
) -> bool:
    if not _request_current_turn_has_material_execution_evidence(request):
        return False
    if response.intent not in {"strategy_drafting", "backtest_execution"}:
        return False
    if not response.requires_clarification or not response.assistant_response:
        return False
    if response.capability_question_focus is not None:
        return False
    draft = response.candidate_strategy_draft
    if _llm_strategy_draft_has_semantic_execution_anchor(draft):
        return False
    return bool(draft.raw_user_phrasing or draft.strategy_thesis)


def _response_needs_pre_guidance_focused_strategy_extraction(
    *,
    response: LLMInterpretationResponse,
    request: InterpretationRequest,
) -> bool:
    if response.intent not in {"strategy_drafting", "backtest_execution"}:
        return False
    if response.semantic_turn_act not in {None, "new_idea"}:
        return False
    if response.requires_clarification and response.assistant_response:
        return False
    if (
        response.capability_question_focus is not None
        or response.context_question_focus is not None
        or response.unsupported_constraints
        or response.ambiguous_fields
    ):
        return False
    if not _request_current_turn_has_material_execution_evidence(request):
        return False
    draft = response.candidate_strategy_draft
    if _llm_strategy_draft_has_semantic_execution_anchor(draft):
        return bool(
            _capability_required_missing_fields_for_canonical_strategy([], draft=draft)
        )
    return bool(
        draft.raw_user_phrasing
        or draft.strategy_thesis
        or request.current_user_message.strip()
    )


async def _audit_executable_strategy_grounding(
    *,
    response: LLMInterpretationResponse,
    preferred_model: str,
    request: InterpretationRequest,
) -> LLMInterpretationResponse | None:
    if not _response_needs_executable_strategy_grounding_audit(response=response):
        return None
    messages = _executable_strategy_grounding_messages(
        response=response,
        request=request,
    )
    for model_name in _unique_repair_models(preferred_model):
        try:
            audit = await invoke_openrouter_json_schema(
                task="interpretation",
                messages=messages,
                schema_model=ExecutableStrategyGroundingAudit,
                schema_name="ExecutableStrategyGroundingAudit",
                model_name=model_name,
            )
        except Exception:
            continue
        if not isinstance(audit, ExecutableStrategyGroundingAudit):
            continue
        repaired = _response_from_executable_strategy_grounding_audit(
            response=response,
            audit=audit,
        )
        if repaired is not None:
            return repaired
        return None
    return None


async def _audit_stated_run_field_fidelity(
    *,
    response: LLMInterpretationResponse,
    preferred_model: str,
    request: InterpretationRequest,
    required: bool = False,
) -> LLMInterpretationResponse | None:
    del preferred_model
    if not required and not _response_needs_stated_run_field_fidelity_audit(
        response=response,
        request=request,
    ):
        return None
    deterministic_repair = _response_from_current_message_run_field_contract(
        response=response,
        request=request,
    )
    if deterministic_repair is not None:
        response = deterministic_repair
        if not required and not _response_needs_stated_run_field_fidelity_audit(
            response=response,
            request=request,
        ):
            return response
    messages = _stated_run_field_fidelity_messages(
        response=response,
        request=request,
    )
    audit_response = response
    try:
        audit = await invoke_openrouter_json_schema(
            task="field_fidelity",
            messages=messages,
            schema_model=StatedRunFieldFidelityAudit,
            schema_name="StatedRunFieldFidelityAudit",
        )
    except Exception:
        audit = None
    valid_audit = audit if isinstance(audit, StatedRunFieldFidelityAudit) else None
    if not isinstance(audit, StatedRunFieldFidelityAudit):
        audit = StatedRunFieldFidelityAudit()
        audit_response = deterministic_repair or response
    repaired = _response_from_stated_run_field_fidelity_audit(
        response=audit_response,
        audit=audit,
        current_message=request.current_user_message,
        prior_strategy=_current_artifact_strategy(request),
    )
    candidate_response = repaired or deterministic_repair or response
    capital_recheck = await _audit_stated_starting_capital_fidelity(
        response=candidate_response,
        request=request,
    )
    if capital_recheck is not None:
        candidate_response = capital_recheck
    if required:
        candidate_response = focused_stated_field_audit_guard(response=candidate_response, audit=valid_audit)
        return candidate_response
    if capital_recheck is not None:
        return capital_recheck
    if repaired is None:
        return deterministic_repair
    return repaired


async def _audit_supported_strategy_capability_conflict(
    *,
    response: LLMInterpretationResponse,
    preferred_model: str,
    request: InterpretationRequest,
) -> LLMInterpretationResponse | None:
    if not _response_needs_supported_strategy_capability_conflict_audit(response):
        return None
    messages = _supported_strategy_capability_conflict_messages(
        response=response,
        request=request,
    )
    try:
        audit = await invoke_openrouter_json_schema(
            task="capability_conflict",
            messages=messages,
            schema_model=SupportedStrategyCapabilityConflictAudit,
            schema_name="SupportedStrategyCapabilityConflictAudit",
        )
    except Exception:
        return _structured_supported_strategy_capability_conflict_fallback(response)
    if not isinstance(audit, SupportedStrategyCapabilityConflictAudit):
        return _structured_supported_strategy_capability_conflict_fallback(response)
    if (
        audit.drop_unsupported_strategy_logic
        and not audit.keep_unsupported_strategy_logic
        and audit.confidence >= 0.7
    ):
        draft = response.candidate_strategy_draft
        strategy_type = safe_conflict_strategy_type(audit.selected_strategy_type, draft)
        if strategy_type is None:
            return None
        repaired = _response_with_supported_strategy_capability_conflict_removed(
            response=response,
            strategy_type=strategy_type,
        )
        return await _dca_contribution_role_audited_response(
            response=repaired,
            preferred_model=preferred_model,
            request=request,
        )
    if audit.confidence < 0.7:
        return _structured_supported_strategy_capability_conflict_fallback(response)
    return None


def _response_needs_stated_run_field_fidelity_audit(
    *,
    response: LLMInterpretationResponse,
    request: InterpretationRequest | None = None,
) -> bool:
    if (
        response.requires_clarification
        and not _llm_strategy_draft_has_concrete_execution_target(
            response.candidate_strategy_draft
        )
    ):
        return False
    if response.intent not in {"strategy_drafting", "backtest_execution"}:
        return False
    if response.semantic_turn_act in {
        "approval",
        "result_followup",
        "unsupported_request",
    }:
        return False
    if "stated_run_field_fidelity_audit" in response.reason_codes:
        return False
    if _pending_dca_assumption_reply_needs_stated_run_field_audit(
        response=response,
        request=request,
    ):
        return True
    draft = response.candidate_strategy_draft
    current_message = request.current_user_message if request is not None else ""
    if has_execution_cost_candidate(draft.extra_parameters):
        return True
    if (
        request is not None
        and _response_replays_prior_strategy_without_current_turn_update(
            response=response,
            request=request,
        )
    ):
        return False
    requested_field = ""
    if request is not None:
        requested_field = _field_path_base(
            request.selected_thread_metadata.get("requested_field")
        )
    if canonical_strategy_type(
        draft.strategy_type
    ) == "dca_accumulation" and _dca_response_needs_semantic_field_audit(response):
        return True
    if _response_needs_current_message_date_repair(
        response=response,
        current_message=current_message,
    ):
        return True
    if _response_needs_missing_benchmark_fidelity_audit(response):
        return True
    if _draft_has_unprovenanced_benchmark(draft):
        return True
    if _response_has_current_message_date_range_reconciliation(
        response=response,
        request=request,
    ):
        return True
    if response.semantic_turn_act == "answer_pending_need":
        if _supported_pending_need_has_recoverable_current_turn_run_fields(
            response=response,
            request=request,
            current_message=current_message,
            requested_field=requested_field,
        ):
            return True
        if requested_field == "date_range":
            return any(
                [
                    not _llm_value_is_empty(draft.date_range),
                    _draft_has_semantic_date_window_evidence(draft),
                    _draft_missing_comparison_baseline_needs_stated_run_field_audit(
                        draft,
                        current_message=current_message,
                    ),
                    _draft_capital_needs_stated_run_field_audit(
                        draft,
                        current_message=current_message,
                    ),
                ]
            )
        if requested_field == "assumption":
            return _draft_capital_needs_stated_run_field_audit(
                draft,
                current_message=current_message,
            )
        return False
    if not any(
        code in response.reason_codes
        for code in {
            "focused_strategy_extraction_repair",
            "signal_rule_plan_repair",
            "focused_repair_preserved_structured_context",
        }
    ):
        return _ready_response_has_unreconciled_stated_run_fields(
            draft,
            current_message=current_message,
        )
    if "focused_repair_from_unsupported_context" in response.reason_codes:
        return draft.capital_amount is None
    if "signal_rule_plan_repair" in response.reason_codes:
        return any(
            [
                _draft_capital_needs_stated_run_field_audit(
                    draft,
                    current_message=current_message,
                ),
                _llm_value_is_empty(draft.timeframe)
                and _draft_has_timeframe_evidence_for_audit(draft),
                _draft_date_range_needs_stated_run_field_audit(
                    draft,
                    current_message=current_message,
                ),
            ]
        )
    return any(
        [
            _focused_repair_benchmark_needs_fidelity_audit(
                draft,
                current_message=current_message,
            ),
            _focused_repair_capital_needs_stated_run_field_audit(
                draft,
                current_message=current_message,
            ),
            _llm_value_is_empty(draft.timeframe)
            and _draft_has_timeframe_evidence_for_audit(draft),
            _draft_date_range_needs_stated_run_field_audit(
                draft,
                current_message=current_message,
            ),
        ]
    )


def _response_has_current_message_date_range_reconciliation(
    *,
    response: LLMInterpretationResponse,
    request: InterpretationRequest | None,
) -> bool:
    if request is None:
        return False
    date_range = _date_range_from_intent_or_bounded_evidence(
        response.candidate_strategy_draft,
        language=request.user.language_preference,
    )
    if date_range is None:
        return False
    draft = response.candidate_strategy_draft
    if _llm_value_is_empty(draft.date_range):
        return True
    if has_partial_explicit_date_range(draft.date_range):
        return True
    if _draft_complete_date_range_matches_current_turn_date_evidence(
        draft,
        request=request,
    ):
        return False
    if resolve_date_range_intent(
        draft.date_range_intent
    ) is not None and _draft_has_semantic_date_window_evidence(draft):
        return True
    if not isinstance(draft.date_range, dict):
        return False
    has_complete_date_range = _has_complete_date_range_payload(
        normalize_date_range_candidate(draft.date_range)
    )
    if _complete_date_range_needs_current_turn_date_audit(
        response=response,
        request=request,
        has_complete_date_range=has_complete_date_range,
        has_material_execution_evidence=(
            _request_current_turn_has_material_execution_evidence(request)
        ),
    ):
        return True
    return _normalized_stated_field(draft.date_range) != _normalized_stated_field(
        date_range
    )


def _supported_pending_need_has_recoverable_current_turn_run_fields(
    *,
    response: LLMInterpretationResponse,
    request: InterpretationRequest | None,
    current_message: str,
    requested_field: str,
) -> bool:
    if request is None:
        return False
    if requested_field:
        return False
    if response.unsupported_constraints or response.ambiguous_fields:
        return False
    if (
        response.capability_question_focus is not None
        or response.context_question_focus is not None
    ):
        return False
    if _request_has_active_strategy_context(
        request
    ) and not _request_current_turn_has_material_execution_evidence(request):
        return False
    if not _request_current_turn_has_material_execution_evidence(request):
        return False
    draft = response.candidate_strategy_draft
    if canonical_strategy_type(draft.strategy_type) not in SUPPORTED_STRATEGY_TYPES:
        return False
    if not _llm_strategy_draft_has_concrete_execution_target(draft):
        return False
    return any(
        [
            _draft_missing_comparison_baseline_needs_stated_run_field_audit(
                draft,
                current_message=current_message,
            ),
            _draft_capital_needs_stated_run_field_audit(
                draft,
                current_message=current_message,
            ),
        ]
    )


def _focused_repair_benchmark_needs_fidelity_audit(
    draft: LLMStrategyDraft,
    *,
    current_message: str,
) -> bool:
    if _llm_value_is_empty(draft.comparison_baseline):
        return False
    if _comparison_baseline_has_trusted_provenance(
        draft
    ) and _comparison_baseline_has_provider_ticker_support(
        draft,
        current_message=current_message,
    ):
        return False
    return current_message_has_extra_provider_asset_for_benchmark(
        draft,
        current_message=current_message,
        resolved_asset_mentions=_resolved_asset_mentions_from_message(current_message),
        resolve_candidate=_resolve_benchmark_candidate_from_message,
    )


def _ready_response_has_unreconciled_stated_run_fields(
    draft: LLMStrategyDraft,
    *,
    current_message: str = "",
) -> bool:
    return any(
        [
            _draft_missing_comparison_baseline_needs_stated_run_field_audit(
                draft,
                current_message=current_message,
            ),
            _draft_capital_needs_stated_run_field_audit(
                draft,
                current_message=current_message,
            ),
            _llm_value_is_empty(draft.timeframe)
            and _draft_has_timeframe_evidence_for_audit(draft),
            _draft_date_range_needs_stated_run_field_audit(
                draft,
                current_message=current_message,
            ),
        ]
    )


def _draft_missing_comparison_baseline_needs_stated_run_field_audit(
    draft: LLMStrategyDraft,
    *,
    current_message: str,
) -> bool:
    if not _llm_value_is_empty(draft.comparison_baseline):
        return False
    if not _llm_strategy_draft_has_concrete_execution_target(draft):
        return False
    if _draft_has_comparison_baseline_evidence(draft):
        return True
    return current_message_has_extra_provider_asset_for_benchmark(
        draft,
        current_message=current_message,
        resolved_asset_mentions=_resolved_asset_mentions_from_message(current_message),
        resolve_candidate=_resolve_benchmark_candidate_from_message,
    )


def _draft_missing_exact_ticker_benchmark_needs_fidelity_audit(
    draft: LLMStrategyDraft,
    *,
    current_message: str,
) -> bool:
    if not _llm_value_is_empty(draft.comparison_baseline):
        return False
    if not _llm_strategy_draft_has_concrete_execution_target(draft):
        return False
    draft_symbols = {
        str(symbol or "").strip().upper()
        for symbol in draft.asset_universe
        if str(symbol or "").strip()
    }
    if not draft_symbols:
        return False
    draft_asset_class = str(draft.asset_class or "").strip().lower()
    for query in _explicit_benchmark_ticker_queries(current_message):
        resolution = _resolve_benchmark_candidate_from_message(query)
        if (
            resolution is None
            or resolution.status != "resolved"
            or resolution.asset is None
        ):
            continue
        asset = resolution.asset
        symbol = str(getattr(asset, "canonical_symbol", "") or "").strip().upper()
        if not symbol or symbol in draft_symbols:
            continue
        asset_class = str(getattr(asset, "asset_class", "") or "").strip().lower()
        if draft_asset_class and asset_class and asset_class != draft_asset_class:
            continue
        return True
    return False


def _resolve_benchmark_candidate_from_message(query: str) -> AssetResolution | None:
    try:
        return _resolve_asset_candidate(
            query,
            field="comparison_baseline",
            source="user_mention",
        )
    except ValueError:
        return None


async def _latest_result_routing_audited_response(
    *,
    response: LLMInterpretationResponse,
    preferred_model: str,
    request: InterpretationRequest,
) -> LLMInterpretationResponse:
    if not _response_needs_latest_result_routing_audit(response, request=request):
        return response
    try:
        audit = await invoke_openrouter_json_schema(
            task="interpretation",
            messages=_latest_result_routing_audit_messages(
                response=response,
                request=request,
            ),
            schema_model=LatestResultRoutingAudit,
            schema_name="LatestResultRoutingAudit",
            model_name=preferred_model,
        )
    except Exception as exc:
        log_openrouter_failure(
            task="interpretation",
            model_name=preferred_model,
            exc=exc,
            message=(
                "Latest result routing audit failed; preserving primary "
                "interpreter decision"
            ),
        )
        return response
    if not isinstance(audit, LatestResultRoutingAudit):
        return response
    if not audit.targets_latest_result or audit.confidence < 0.6:
        return response
    save_requested = audit.save_requested
    if not save_requested:
        save_requested = await _latest_result_save_request_audit(
            preferred_model=preferred_model,
            request=request,
        )
    reason_codes = ["latest_result_routing_audit"]
    if save_requested:
        reason_codes.append("latest_result_save_requested")
    return response.model_copy(
        update={
            "intent": "conversation_followup",
            "requires_clarification": False,
            "missing_required_fields": [],
            "assistant_response": None,
            "semantic_turn_act": "result_followup",
            "result_followup_focus": audit.focus or "general",
            "result_followup_fact_key": audit.fact_key,
            "capability_question_focus": None,
            "context_question_focus": None,
            "uses_latest_result_context": True,
            "artifact_target": "latest_result",
            "reason_codes": list(
                dict.fromkeys(
                    [
                        *response.reason_codes,
                        *reason_codes,
                    ]
                )
            ),
        }
    )


async def _latest_result_save_request_audit(
    *,
    preferred_model: str,
    request: InterpretationRequest,
) -> bool:
    try:
        audit = await invoke_openrouter_json_schema(
            task="interpretation",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Argus's latest-result save-intent audit. "
                        "Classify only whether the current user message asks to "
                        "save, keep, bookmark, store, or promote the latest "
                        "completed result artifact. Return false for explanation, "
                        "breakdown, refinement, rerun, or education requests. "
                        "If a latest result exists, messages like 'save this', "
                        "'save this result', 'keep this', 'bookmark this run', "
                        "or 'save that strategy from the result' are save requests."
                    ),
                },
                {
                    "role": "system",
                    "content": (
                        "Latest result fact bank JSON: "
                        + json.dumps(_latest_result_fact_bank_for_routing(request))
                    ),
                },
                {"role": "user", "content": request.current_user_message},
            ],
            schema_model=LatestResultSaveAudit,
            schema_name="LatestResultSaveAudit",
            model_name=preferred_model,
        )
    except Exception as exc:
        log_openrouter_failure(
            task="interpretation",
            model_name=preferred_model,
            exc=exc,
            message="Latest result save-intent audit failed; preserving routing audit",
        )
        return False
    return bool(
        isinstance(audit, LatestResultSaveAudit)
        and audit.save_requested
        and audit.confidence >= 0.6
    )


async def _audit_stated_starting_capital_fidelity(
    *,
    response: LLMInterpretationResponse,
    request: InterpretationRequest,
) -> LLMInterpretationResponse | None:
    if not _response_needs_stated_starting_capital_recheck(
        response=response,
        request=request,
    ):
        return None
    try:
        audit = await invoke_openrouter_json_schema(
            task="field_fidelity",
            messages=_stated_starting_capital_messages(
                response=response,
                request=request,
            ),
            schema_model=StatedStartingCapitalAudit,
            schema_name="StatedStartingCapitalAudit",
        )
    except Exception:
        return None
    if not isinstance(audit, StatedStartingCapitalAudit):
        return None
    return _response_from_stated_starting_capital_audit(
        response=response,
        audit=audit,
    )


async def _early_starting_capital_rechecked_response(
    *,
    response: LLMInterpretationResponse,
    request: InterpretationRequest,
) -> LLMInterpretationResponse | None:
    if (
        _optional_runtime_readiness_audit_blocker(
            response=response,
            request=request,
        )
        != "stated_starting_capital_recheck"
    ):
        return None
    _log_runtime_readiness_step(
        "starting_capital_recheck_started",
        response=response,
    )
    repaired = await _audit_stated_starting_capital_fidelity(
        response=response,
        request=request,
    )
    if repaired is None:
        _log_runtime_readiness_step(
            "starting_capital_recheck_no_repair",
            response=response,
        )
        return None
    _log_runtime_readiness_step(
        "starting_capital_recheck_repaired",
        response=repaired,
    )
    return repaired


async def _early_focused_strategy_repaired_response(
    *,
    response: LLMInterpretationResponse,
    preferred_model: str,
    request: InterpretationRequest,
    asset_resolution_context: str | None = None,
) -> LLMInterpretationResponse | None:
    blocker = _optional_runtime_readiness_audit_blocker(
        response=response,
        request=request,
    )
    if blocker not in {
        "missing_required_execution_fields",
        "required_shape_missing",
        "stated_starting_capital_recheck",
    }:
        return None
    if (
        response.requires_clarification
        or response.capability_question_focus is not None
        or response.context_question_focus is not None
        or response.unsupported_constraints
        or response.ambiguous_fields
    ):
        return None
    if not _request_current_turn_has_material_execution_evidence(request):
        return None
    _log_runtime_readiness_step(
        "early_focused_strategy_repair_started",
        response=response,
    )
    repaired = await _repair_incomplete_strategy_extraction(
        failed_response=response,
        preferred_model=preferred_model,
        request=request,
        asset_resolution_context=asset_resolution_context,
    )
    if repaired is None:
        _log_runtime_readiness_step(
            "early_focused_strategy_repair_no_repair",
            response=response,
        )
        return None
    _log_runtime_readiness_step(
        "early_focused_strategy_repaired",
        response=repaired,
    )
    return repaired


def _strategy_extraction_repair_is_allowed(
    response: LLMInterpretationResponse,
    *,
    request: InterpretationRequest,
) -> bool:
    return strategy_extraction_repair_is_allowed(
        response,
        request=request,
        has_failed_action_launch_payload=_request_has_failed_action_launch_payload,
        noncanonical_text_needs_repair=(
            _noncanonical_strategy_text_needs_focused_schema_repair
        ),
        has_active_strategy_context=_request_has_active_strategy_context,
        current_turn_has_material_execution_evidence=(
            _request_current_turn_has_material_execution_evidence
        ),
    )


async def _focused_strategy_repair_after_candidate_failures(
    *,
    request: InterpretationRequest,
    preferred_model: str,
    asset_resolution_context: str | None = None,
    failed_response: LLMInterpretationResponse | None = None,
) -> LLMInterpretationResponse | None:
    # Only this turn's typed read can authorize strategy repair. Outages,
    # numbers, tickers and pending tests cannot establish the question's intent.
    if failed_response is None or route_owner(
        intent=failed_response.intent,
        semantic_turn_act=failed_response.semantic_turn_act,
    ) != "strategy":
        return None
    if failed_response.semantic_turn_act not in (None, "retry_failed_action", *STRATEGY_TURN_ACTS):
        return None
    if _request_has_active_strategy_context(
        request
    ) and not _request_current_turn_has_material_execution_evidence(request):
        return None
    seed_response = failed_response.model_copy(deep=True)
    seed_response.reason_codes.append("structured_interpretation_candidates_failed")
    logger.bind(
        llm_task=_INTERPRETATION_REPAIR_TASK,
        preferred_model=preferred_model,
        current_message_length=len(request.current_user_message),
        reason_codes=list(seed_response.reason_codes),
    ).info("Structured interpretation candidates failed; attempting focused repair")
    with turn_execution.last_resort_repair_scope():
        return await _repair_incomplete_strategy_extraction(
            failed_response=seed_response,
            preferred_model=preferred_model,
            request=request,
            asset_resolution_context=asset_resolution_context,
        )


def _response_from_focused_strategy_extraction(
    *,
    extraction: FocusedStrategyExtraction,
    request: InterpretationRequest,
    base_response: LLMInterpretationResponse | None = None,
) -> LLMInterpretationResponse:
    return response_from_focused_strategy_extraction(
        extraction=extraction,
        request=request,
        base_response=base_response,
        resolve_asset_candidate=_resolve_asset_candidate,
    )


def _structured_interpretation_has_required_shape(
    response: LLMInterpretationResponse,
    *,
    request: InterpretationRequest,
) -> bool:
    if response.intent == "results_explanation" and not _request_has_latest_result(
        request
    ):
        return False
    if (
        response.semantic_turn_act in {"answer_pending_need", "approval"}
        and not _request_has_active_strategy_context(request)
        and not _llm_strategy_draft_has_extractable_fields(
            response.candidate_strategy_draft
        )
    ):
        return False
    if (
        response.intent == "unsupported_or_out_of_scope"
        and response.semantic_turn_act == "unsupported_request"
        and _request_has_active_strategy_context(request)
        and _selected_requested_field_base(request)
        and _request_current_turn_has_material_execution_evidence(request)
        and not response.unsupported_constraints
    ):
        return False
    if (
        response.intent == "unsupported_or_out_of_scope"
        and response.requires_clarification
        and not response.unsupported_constraints
        # A reference-only draft (resolved asset, date) is not an answer; fail
        # the shape without text so the corrective re-ask demands one.
        and not strategy_has_execution_evidence(response.candidate_strategy_draft)
    ):
        return bool(response.assistant_response)
    if _response_underfills_pending_result_refinement(
        response=response,
        request=request,
    ):
        return False
    if response.semantic_turn_act == "retry_failed_action":
        return _request_has_failed_action_launch_payload(request)
    if response.intent not in {"strategy_drafting", "backtest_execution"}:
        return True
    if response.semantic_turn_act == "approval":
        return True
    if _response_underfills_active_artifact_assumption_edit(
        response=response,
        request=request,
    ):
        return False
    if _response_underfills_active_artifact_rule_edit(
        response=response,
        request=request,
    ):
        return False
    if response.requires_clarification and response.assistant_response:
        if _supported_anchor_needs_focused_run_window_repair(
            response=response,
            request=request,
        ):
            return False
        if _supported_partial_strategy_needs_focused_schema_repair(
            response=response,
            request=request,
        ):
            return False
        if _noncanonical_strategy_text_needs_focused_schema_repair(
            response=response,
            request=request,
        ):
            return False
        return True
    draft = response.candidate_strategy_draft
    if _llm_strategy_draft_has_extractable_fields(draft):
        if canonical_strategy_type(draft.strategy_type) == "dca_accumulation":
            missing = _capability_required_missing_fields_for_canonical_strategy(
                response.missing_required_fields,
                draft=draft,
            )
            if missing:
                if _structured_strategy_missing_fields_can_clarify(
                    response=response,
                    draft=draft,
                    missing=missing,
                ):
                    return True
                return False
        if _llm_signal_strategy_is_underfilled(draft):
            return False
        if _response_replays_prior_strategy_without_current_turn_update(
            response=response,
            request=request,
        ):
            return False
        return True
    if response.task_relation == "refine" or response.semantic_turn_act in {
        "refine_current_idea",
        "answer_pending_need",
    }:
        return False
    return False


def _normalize_response_for_runtime_context(
    response: LLMInterpretationResponse,
    *,
    request: InterpretationRequest,
    asset_resolution_context: str | None = None,
) -> LLMInterpretationResponse:
    response = _response_with_latest_result_window_bound(response, request=request)
    response = _response_with_post_result_window_inherited(
        response,
        request=request,
    )
    response = provider_context_assets.response_with_runtime_context_assets(
        response,
        request=request,
        asset_resolution_context=asset_resolution_context,
    )
    response = _response_with_canonical_interpreter_assets(response)
    response = response_with_recovery_intent_window_materialized(response)
    if _request_has_latest_result(request):
        return response
    if (
        response.intent in {"strategy_drafting", "backtest_execution"}
        and response.semantic_turn_act is None
        and not _request_has_active_strategy_context(request)
        and (
            _llm_strategy_draft_has_extractable_fields(response.candidate_strategy_draft)
            or _request_current_turn_has_material_execution_evidence(request)
        )
    ):
        response = response.model_copy(
            update={
                "semantic_turn_act": "new_idea",
                "reason_codes": list(
                    dict.fromkeys(
                        [
                            *response.reason_codes,
                            "coerced_missing_turn_act_to_new_idea",
                        ]
                    )
                ),
            }
        )
    if response.intent != "results_explanation":
        return response
    if (
        response.semantic_turn_act == "result_followup"
        and response.result_followup_focus == "assumptions"
        and _request_has_active_strategy_context(request)
    ):
        return response.model_copy(
            update={
                "intent": "conversation_followup",
                "assistant_response": None,
                "uses_latest_result_context": False,
                "reason_codes": [
                    *response.reason_codes,
                    "routed_pending_artifact_assumptions_followup",
                ],
            }
        )
    if response.semantic_turn_act == "educational_question":
        return response.model_copy(
            update={
                "intent": "conversation_followup",
                "uses_latest_result_context": False,
                "reason_codes": [
                    *response.reason_codes,
                    "coerced_result_explanation_without_result_context",
                ],
            }
        )
    if not _llm_strategy_draft_has_extractable_fields(response.candidate_strategy_draft):
        return response
    semantic_turn_act = response.semantic_turn_act
    if semantic_turn_act not in {
        "new_idea",
        "refine_current_idea",
        "answer_pending_need",
    }:
        semantic_turn_act = "new_idea"
    return response.model_copy(
        update={
            "intent": "strategy_drafting",
            "semantic_turn_act": semantic_turn_act,
            "assistant_response": None,
            "uses_latest_result_context": False,
            "reason_codes": [
                *response.reason_codes,
                "coerced_result_explanation_to_strategy_draft",
            ],
        }
    )


def _response_with_canonical_interpreter_assets(
    response: LLMInterpretationResponse,
) -> LLMInterpretationResponse:
    return provider_context_assets.response_with_canonical_interpreter_assets(
        response,
        resolve_asset_candidate=_resolve_asset_candidate,
    )


def _request_current_turn_has_material_execution_evidence(
    request: InterpretationRequest,
) -> bool:
    if _current_message_has_numeric_execution_fact(request.current_user_message):
        return current_turn_has_material_execution_evidence(
            request.current_user_message,
            has_provider_asset_mention=False,
            active_strategy_context=_request_has_active_strategy_context(request),
            requested_field=request.selected_thread_metadata.get("requested_field"),
        )
    return current_turn_has_material_execution_evidence(
        request.current_user_message,
        has_provider_asset_mention=bool(
            _resolved_asset_mentions_from_message(request.current_user_message)
        )
        or _request_has_provider_exact_execution_asset(request),
        active_strategy_context=_request_has_active_strategy_context(request),
        requested_field=request.selected_thread_metadata.get("requested_field"),
    )


def _current_message_has_numeric_execution_fact(message: str) -> bool:
    return any(
        any(char.isdigit() for char in token)
        for token in field_fidelity_tokens(str(message or ""))
    )


def _validate_capability_boundaries(
    *,
    strategy: StrategySummary,
    response: LLMInterpretationResponse,
    request: InterpretationRequest,
) -> None:
    symbols = list(strategy.asset_universe)
    canonical_symbols: list[str] = []
    asset_classes = set()
    invalid_symbols: list[str] = []
    field_owned_indicator_symbols: list[str] = []
    resolution_provenance = []
    for index, symbol in enumerate(symbols):
        if _field_owned_indicator_asset_candidate(
            strategy=strategy,
            symbol=symbol,
            request=request,
        ):
            field_owned_indicator_symbols.append(symbol)
            continue
        resolution = provider_context_assets.resolution_from_strategy_context(
            strategy,
            symbol,
            field=f"asset_universe[{index}]",
        ) or _resolve_asset_candidate(
            symbol,
            field=f"asset_universe[{index}]",
            source="llm_extraction",
            asset_class_hint=strategy.asset_class,
        )
        resolution_provenance.append(resolution.provenance)
        if resolution.status == "ambiguous":
            candidate_symbols = [
                normalized
                for candidate in resolution.candidates
                if (
                    normalized := str(getattr(candidate, "canonical_symbol", "") or "")
                    .strip()
                    .upper()
                )
            ]
            response.ambiguous_fields.append(
                LLMAmbiguousField(
                    field_name=f"asset_universe[{index}]",
                    raw_value=symbol,
                    candidate_normalized_value=candidate_symbols or None,
                    reason_code="asset_resolution_ambiguous",
                )
            )
            continue
        if resolution.status != "resolved" or resolution.asset is None:
            invalid_symbols.append(symbol)
            continue
        canonical_symbols.append(resolution.asset.canonical_symbol)
        context_asset_classes = (
            provider_context_assets.resolved_asset_classes_from_strategy_context(
                strategy, symbol
            )
        )
        asset_classes.update(context_asset_classes or {resolution.asset.asset_class})
    strategy.asset_universe = list(dict.fromkeys(canonical_symbols))
    if field_owned_indicator_symbols and (
        "field_owned_indicator_asset_token_removed" not in response.reason_codes
    ):
        response.reason_codes.append("field_owned_indicator_asset_token_removed")
    strategy.resolution_provenance = _dedupe_resolution_provenance(
        [*strategy.resolution_provenance, *resolution_provenance]
    )
    if len(asset_classes) == 1:
        strategy.asset_class = next(iter(asset_classes))
    elif len(asset_classes) > 1:
        strategy.asset_class = "mixed"
        if not any(
            item.category == "unsupported_asset_mix"
            for item in response.unsupported_constraints
        ):
            response.unsupported_constraints.append(
                LLMUnsupportedConstraint(
                    category="unsupported_asset_mix",
                    raw_value=", ".join(symbols),
                    explanation=(
                        "Argus Alpha cannot run equity, crypto, and currency pairs "
                        "together in one simulation yet."
                    ),
                    simplification_options=_options.asset_class_simplification_options(),
                )
            )
    if invalid_symbols and not any(
        item.category == "unsupported_symbol" for item in response.unsupported_constraints
    ):
        response.unsupported_constraints.append(
            LLMUnsupportedConstraint(
                category="unsupported_symbol",
                raw_value=", ".join(invalid_symbols),
                explanation=(
                    "I understood the symbol, but I could not verify it in the "
                    "supported market data universe for this run."
                ),
                simplification_labels=["Use a supported stock or crypto symbol"],
            )
        )
    _validate_indicator_rule_support(strategy=strategy, response=response)
    canonical_type = executable_strategy_type(strategy)
    if canonical_type in {"buy_and_hold", "dca_accumulation"}:
        strategy.strategy_type = canonical_type
        strategy.entry_logic = None
        strategy.exit_logic = None
        _remove_unstated_model_defaults(strategy)
    if canonical_type == "indicator_threshold":
        strategy.strategy_type = canonical_type
        _apply_executable_indicator_defaults(strategy)
    if canonical_type == "signal_strategy":
        strategy.strategy_type = canonical_type
        _apply_signal_strategy_defaults(strategy)
    if (
        canonical_type == "dca_accumulation"
        and strategy.capital_amount is not None
        and not _dca_amount_has_user_provenance(strategy=strategy, request=request)
    ):
        strategy.capital_amount = None
        strategy.sizing_mode = None
    if (
        canonical_type == "dca_accumulation"
        and strategy.cadence not in (None, "", [], {})
        and not _dca_cadence_has_user_provenance(strategy=strategy, request=request)
    ):
        ungrounded_cadence = str(strategy.cadence).casefold()
        strategy.cadence = None
        strategy.assumptions = [
            assumption
            for assumption in strategy.assumptions
            if ungrounded_cadence not in str(assumption).casefold()
        ]
    if canonical_type == "dca_accumulation":
        _ensure_dca_missing_execution_fields(strategy=strategy, response=response)
    _remove_stale_indicator_constraints(
        response=response,
        strategy=strategy,
        current_message=request.current_user_message,
    )


def _resolve_asset_candidate(
    query: str,
    *,
    field: str,
    source: ResolutionSource,
    resolution_mode: str = "auto",
    asset_class_hint: str | None = None,
) -> AssetResolution:
    if resolve_asset is _DEFAULT_RESOLVE_ASSET:
        kwargs: dict[str, Any] = {"field": field, "source": source}
        if callable_accepts_keyword(runtime_resolve_asset_candidate, "resolution_mode"):
            kwargs["resolution_mode"] = resolution_mode
        if asset_class_hint is not None and callable_accepts_keyword(
            runtime_resolve_asset_candidate,
            "asset_class_hint",
        ):
            kwargs["asset_class_hint"] = asset_class_hint
        return runtime_resolve_asset_candidate(query, **kwargs)
    resolved = resolve_asset(query)
    provenance = ResolutionProvenance(
        field=field,
        raw_text=query,
        source=source,
        candidate_kind="asset",
        resolution_status="resolved",
        canonical_symbol=resolved.canonical_symbol,
        asset_class=resolved.asset_class,
        validated_by="provider_catalog",
        confidence="high",
    )
    return AssetResolution(
        status="resolved",
        raw_text=query,
        asset=resolved,
        candidates=(resolved,),
        provenance=provenance,
    )
