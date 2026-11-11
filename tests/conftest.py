import os
from datetime import datetime

import pytest

# These files import the old investing interpreter or its data libraries.
# Production no longer installs those libraries, and the API and document
# worker do not import them. See tests/test_production_import_closure.py.
collect_ignore = [
    'agent_runtime/discovery/test_discovery_route.py',
    'agent_runtime/test_artifact_continuity.py',
    'agent_runtime/test_benchmark_coverage.py',
    'agent_runtime/test_calculated_answer.py',
    'agent_runtime/test_capacity_refusal_copy.py',
    'agent_runtime/test_chip_completion_guards.py',
    'agent_runtime/test_compound_edit_contract.py',
    'agent_runtime/test_confirmation_artifacts.py',
    'agent_runtime/test_confirmation_liveness.py',
    'agent_runtime/test_conversation_stages.py',
    'agent_runtime/test_current_reply_inputs.py',
    'agent_runtime/test_dca_money_role_audits.py',
    'agent_runtime/test_discovery_focused_read.py',
    'agent_runtime/test_edit_carrier_conflicts.py',
    'agent_runtime/test_execute_launch_payload.py',
    'agent_runtime/test_execute_recovery.py',
    'agent_runtime/test_history_start_guidance.py',
    'agent_runtime/test_interpret_stage.py',
    'agent_runtime/test_knowledge_answer.py',
    'agent_runtime/test_latest_market_close.py',
    'agent_runtime/test_money_question_recovery.py',
    'agent_runtime/test_next_experiments.py',
    'agent_runtime/test_pending_edit_card_paths.py',
    'agent_runtime/test_private_log_content.py',
    'agent_runtime/test_real_backtest_tool.py',
    'agent_runtime/test_recovery_edit_outcomes.py',
    'agent_runtime/test_result_followup_answers.py',
    'agent_runtime/test_strategy_contract.py',
    'agent_runtime/test_validation_failure_copy.py',
    'agent_runtime/test_workflow.py',
    'domain/test_backtest_math_audit_invariants.py',
    'domain/test_benchmark_curve_contract.py',
    'domain/test_capability_registry.py',
    'domain/test_dca_benchmark_observed_fills.py',
    'domain/test_dca_capital_semantics.py',
    'domain/test_dca_flow_adjusted_metrics.py',
    'domain/test_dca_trading_day_rule.py',
    'domain/test_engine_execution_ledger.py',
    'domain/test_engine_launch.py',
    'domain/test_market_data_coverage.py',
    'domain/test_modeled_execution_costs.py',
    'domain/test_pretrade_baseline_metrics.py',
    'domain/test_result_chart_exploration.py',
    'domain/test_rule_compiler.py',
    'evals/test_chat_runtime_eval_manifest.py',
    'evals/test_chat_runtime_trajectory_harness.py',
    'evals/test_measurement_availability.py',
    'evals/test_measurement_delivery.py',
    'evals/test_measurement_eval_dca_semantics.py',
    'evals/test_measurement_eval_harness.py',
    'evals/test_measurement_eval_issue_498.py',
    'evals/test_measurement_eval_live.py',
    'evals/test_measurement_year_qualifier.py',
    'evals/test_prose_evidence.py',
    'evals/test_research_routing_live.py',
    'nlp/test_fractional_durations.py',
    'perf/section3/test_engine_latency.py',
    'research/test_calculation_retrieval.py',
    'research/test_confirmation_peer_assets.py',
    'research/test_confirmation_peer_identity.py',
    'research/test_execution_evidence_invariant.py',
    'research/test_history_not_forecast.py',
    'research/test_provider_failure_recovery.py',
    'research/test_research_answer.py',
    'research/test_research_asset_identity.py',
    'research/test_research_pricing_delivery.py',
    'research/test_research_router_absorption.py',
    'research/test_research_scenarios.py',
    'research/test_research_shapes.py',
    'research/test_research_sources_and_voice.py',
    'research/test_research_truth_boundary.py',
    'research/test_research_turn_deadline.py',
    'research/test_scenario_regressions.py',
    'section3/test_engine_simulation.py',
    'section3/test_market_data_provider.py',
    'test_alpha_api.py',
    'test_alpha_api_supabase.py',
    'test_alpha_orchestration_regression.py',
    'test_asset_history_start.py',
    'test_backtest_admission_logs.py',
    'test_backtest_jobs_async.py',
    'test_backtest_jobs_shadow.py',
    'test_backtest_service_calendar.py',
    'test_backtest_state_machine.py',
    'test_benchmark_comparison_language.py',
    'test_chat_admission_visitor_bound.py',
    'test_confirmation_direct_edit.py',
    'test_confirmation_run_consumption.py',
    'test_context_packet_runtime_attachment.py',
    'test_conversational_ux.py',
    'test_degraded_recovery_history.py',
    'test_effective_window_confirmation.py',
    'test_engine_signals.py',
    'test_in_place_surface_flag.py',
    'test_issue_440_cancelled_draft_dates.py',
    'test_issue_542_durable_backtest_failures.py',
    'test_localization.py',
    'test_natural_time.py',
    'test_new_york_today.py',
    'test_onboarding_removal.py',
    'test_openrouter_policy.py',
    'test_openrouter_request_policy.py',
    'test_pending_artifact_card_kind.py',
    'test_pending_card_checkpoint_sync.py',
    'test_pending_card_conflict.py',
    'test_pending_card_nonturn_invariant.py',
    'test_public_excerpt_calculation_turns.py',
    'test_public_excerpt_fork_runtime.py',
    'test_public_excerpt_language.py',
    'test_public_excerpt_read_path.py',
    'test_public_excerpt_receipts.py',
    'test_public_excerpt_sharing_604.py',
    'test_public_excerpt_turns.py',
    'test_registered_backtest_publication.py',
    'test_research_job_reconciliation.py',
    'test_result_card_gain.py',
    'test_result_dca_readout.py',
    'test_result_link_outcome.py',
    'test_retest_action.py',
    'test_retest_setup.py',
    'test_run_dossiers.py',
    'test_runtime_confirmation_card.py',
    'test_ten_dollar_minimum_capital.py',
    'test_versioning_boundary.py',
    'agent_runtime/test_artifact_assumption_facts.py',
    'agent_runtime/test_artifact_edit_operations.py',
    'agent_runtime/test_calculation_subject_symbol.py',
    'agent_runtime/test_chip_clarify_edit_routing.py',
    'agent_runtime/test_confirm_mixed_asset_preflight.py',
    'agent_runtime/test_conversational_contract_hardening.py',
    'agent_runtime/test_conversion_failure_transport.py',
    'agent_runtime/test_cost_fidelity_stage_clarification.py',
    'agent_runtime/test_current_reason_measured_failures.py',
    'agent_runtime/test_current_reason_resolution.py',
    'agent_runtime/test_deterministic_answer_repairs.py',
    'agent_runtime/test_discovery_payload_routing.py',
    'agent_runtime/test_focused_repair_asset_reconciliation.py',
    'agent_runtime/test_focused_repair_preservation.py',
    'agent_runtime/test_forward_question_routing.py',
    'agent_runtime/test_future_performance_admission.py',
    'agent_runtime/test_future_temporal_direction.py',
    'agent_runtime/test_graded_interpretation_routing.py',
    'agent_runtime/test_interpretation_contract_rejections.py',
    'agent_runtime/test_interpretation_repair_observability.py',
    'agent_runtime/test_interpreter_latest_result_context.py',
    'agent_runtime/test_issue_270_strategy_transitions.py',
    'agent_runtime/test_issue_271_cost_fidelity_audit.py',
    'agent_runtime/test_issue_271_modeled_cost_preservation.py',
    'agent_runtime/test_issue_345_recommendation_continuity.py',
    'agent_runtime/test_issue_453_cause_projection.py',
    'agent_runtime/test_issue_453_focused_repair.py',
    'agent_runtime/test_issue_483_resolved_state.py',
    'agent_runtime/test_issue_600_focused_repair.py',
    'agent_runtime/test_issue_600_measurement_replay.py',
    'agent_runtime/test_latest_result_fact_answers.py',
    'agent_runtime/test_latest_result_window_binding.py',
    'agent_runtime/test_llm_interpreter_artifact_capability_repairs.py',
    'agent_runtime/test_llm_interpreter_date_window_repairs.py',
    'agent_runtime/test_llm_interpreter_grounding_and_signal_rules.py',
    'agent_runtime/test_llm_interpreter_semantic_contracts.py',
    'agent_runtime/test_money_question_recovery_copy.py',
    'agent_runtime/test_options_semantic_admission.py',
    'agent_runtime/test_ordinary_turn_runs_no_audits.py',
    'agent_runtime/test_pending_edit_outcome_contract.py',
    'agent_runtime/test_pending_setup_continuation.py',
    'agent_runtime/test_post_result_edit_routing.py',
    'agent_runtime/test_provider_asset_ownership.py',
    'agent_runtime/test_provider_context_asset_catalog.py',
    'agent_runtime/test_recognition_contract_guards.py',
    'agent_runtime/test_refine_action_edit_routing.py',
    'agent_runtime/test_registered_backtest_legacy_workflow.py',
    'agent_runtime/test_registered_backtest_presentation.py',
    'agent_runtime/test_registered_tool_execution.py',
    'agent_runtime/test_research_routing_contract.py',
    'agent_runtime/test_result_fact_answer_guard.py',
    'agent_runtime/test_result_followup_research_scope.py',
    'agent_runtime/test_simplification_option_identity.py',
    'agent_runtime/test_spanish_runtime_transcripts.py',
    'agent_runtime/test_stated_range_year_qualifier.py',
    'agent_runtime/test_unsupported_fallback_honesty.py',
    'agent_runtime/test_unsupported_recovery_asset_conservation.py',
    'agent_runtime/test_workspace_language_prose.py',
    'evals/test_measurement_eval_followup_snapshot.py',
    'test_answer_with_several_calculations.py',
    'test_chat_backtest_state_machine.py',
    'test_public_excerpt_api.py',
    'test_registration_signal.py',
    'agent_runtime/discovery/test_discovery_composer.py',
    'agent_runtime/test_answer_calculation.py',
    'agent_runtime/test_business_runtime.py',
    'agent_runtime/test_scenario_figure_labels.py',
    'agent_runtime/test_turn_execution.py',
    'domain/calculations/test_web_fixture.py',
    'domain/test_market_data_capabilities.py',
    'domain/test_tool_argument_boundaries.py',
    'domain/test_tool_declaration.py',
    'domain/test_tool_registry_import_boundary.py',
    'evals/test_measurement_eval_live_environment.py',
    'fiscal/test_invoice_artifacts.py',
    'household/test_invite_code_security.py',
    'research/test_discarded_spend.py',
    'research/test_published_answers.py',
    'research/test_question_date.py',
    'research/test_reader_location.py',
    'research/test_registered_research_jobs.py',
    'research/test_registered_research_publication.py',
    'research/test_registered_research_tools.py',
    'research/test_research_cache_isolation.py',
    'research/test_research_claim_release.py',
    'research/test_research_jobs.py',
    'research/test_research_ledger_contract.py',
    'research/test_research_rows.py',
    'research/test_retrieval_contract_probe.py',
    'research/test_retrieval_parameters.py',
    'test_allowance_accounting.py',
    'test_analytics_events.py',
    'test_answer_question_identity.py',
    'test_api_import_boundary.py',
    'test_artifact_presentation.py',
    'test_business_chat_flag.py',
    'test_chat_action_contract.py',
    'test_chat_runtime_cutover.py',
    'test_chat_runtime_reload_guardrails.py',
    'test_chat_turn_route_matrix.py',
    'test_computation_marker.py',
    'test_computations.py',
    'test_computed_answer_actions.py',
    'test_conversation_activity.py',
    'test_conversation_previews.py',
    'test_conversation_surfaces.py',
    'test_decision_attachment_api.py',
    'test_demonstrated_interest.py',
    'test_facade_reexport_integrity.py',
    'test_frontend_search_casefold.py',
    'test_guest_conversation_policy.py',
    'test_home_country.py',
    'test_local_environment_store.py',
    'test_market_session_api.py',
    'test_openapi_compatibility.py',
    'test_openrouter_retention.py',
    'test_p1_evidence_spine.py',
    'test_pending_artifact_lifecycle.py',
    'test_private_launch_hardening.py',
    'test_promotion_evidence_identity.py',
    'test_public_excerpt_forks.py',
    'test_refresh_per_card_symbol.py',
    'test_render_workflow_execution.py',
    'test_render_workflow_proof.py',
    'test_result_figures.py',
    'test_result_readout_transport.py',
    'test_run_dossiers_postgres.py',
    'test_search_bounded_reads.py',
    'test_search_computed_answers.py',
    'test_search_memory_bounded.py',
    'test_shared_fork_history.py',
    'test_sharing_604_fixture.py',
    'test_supabase_gateway.py',
    'test_support_email_agreement.py',
    'test_tool_job_binding.py',
    'test_tool_result_recompute.py',
    'test_usage_allowance_classes.py',
    'test_workflow_withheld_cleanup.py',

]

PROVIDER_CREDENTIAL_ENV_VARS = (
    "OPENROUTER_API_KEY",
    "CUADRAO_OPENROUTER_API_KEY_DEV",
    "CUADRAO_OPENROUTER_API_KEY_STG",
    "CUADRAO_OPENROUTER_API_KEY_PROD",
    "ALPACA_API_KEY",
    "ALPACA_SECRET_KEY",
    "PERPLEXITY_API_KEY",
    "CUADRAO_APPROVAL_EMAIL_SMTP_PASSWORD",
)


def _live_evals_requested() -> bool:
    return os.getenv("ARGUS_RUN_LIVE_EVALS") == "1"


@pytest.fixture(autouse=True)
def mock_auth_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", os.getenv("APP_ENV", "test"))
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "true")
    monkeypatch.setenv("ARGUS_DEV_MEMORY_FALLBACK", "true")
    monkeypatch.setenv("ARGUS_CONTEXT_PACKETS_ENABLED", "false")


@pytest.fixture(autouse=True)
def reads_finish_inside_the_request(monkeypatch):
    """Tests that watch the app's real document puller override this by name."""
    from tests.document_reads_support import read_inside_each_dispatch

    read_inside_each_dispatch(monkeypatch)


@pytest.fixture(autouse=True)
def reset_guest_funnel_milestones():
    """Milestone claims are durable by design, so they must not leak between
    tests the way they must not leak between requests."""
    from argus.api import state as api_state

    api_state.store.guest_funnel_milestones.clear()
    yield
    api_state.store.guest_funnel_milestones.clear()


@pytest.fixture(autouse=True)
def reset_usage_counters():
    """Daily claim rows are process-local in tests; leftover counts would
    trip the signed-in ceiling in a later case."""
    from argus.api import state as api_state

    api_state.store.visitor_usage_counters.clear()
    api_state.store.usage_counters.clear()
    yield
    api_state.store.visitor_usage_counters.clear()
    api_state.store.usage_counters.clear()


@pytest.fixture
def freeze_new_york_clock(monkeypatch):
    """Freeze the one clock every "today" reads at an aware instant."""
    from argus.domain import clock as new_york_clock

    def freeze(at: datetime) -> None:
        assert at.tzinfo is not None, "freeze the clock at an aware instant"

        class _Frozen(datetime):
            @classmethod
            def now(cls, tz=None):  # type: ignore[override]
                return at.astimezone(tz) if tz is not None else at.replace(tzinfo=None)

        monkeypatch.setattr(new_york_clock, "datetime", _Frozen)

    return freeze


@pytest.fixture(autouse=True)
def provider_free_env(monkeypatch):
    """Suite runs stay provider-free unless a live eval is explicitly requested.

    Sanctioned live runs own their own provider mode and credentials, including
    the mode `ARGUS_EVAL_ENV_FILE` supplies, so this fixture must not touch
    either. Credentials are emptied rather than deleted: `load_project_dotenv()`
    uses `override=False`, which refills an absent variable from a worktree
    `.env`.
    """
    if _live_evals_requested():
        return
    monkeypatch.setenv("ARGUS_MARKET_DATA_PROVIDER_MODE", "synthetic_unit_fixture")
    for name in PROVIDER_CREDENTIAL_ENV_VARS:
        monkeypatch.setenv(name, "")


@pytest.fixture
def activity_on(monkeypatch):
    """Actividad on, for a flow that reads the feed. The server's default is off."""
    monkeypatch.setenv("CUADRAO_BUSINESS_ACTIVITY_ENABLED", "true")


@pytest.fixture
def settlement_on(monkeypatch):
    """Por cobrar and Por pagar on, for a flow that marks documents cobrado or pagado."""
    monkeypatch.setenv("CUADRAO_BUSINESS_SETTLEMENT_ENABLED", "true")
