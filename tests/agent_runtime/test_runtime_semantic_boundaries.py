from __future__ import annotations

import ast
from pathlib import Path

RUNTIME_INTENT_FILES = [
    "src/argus/agent_runtime/stages/interpret.py",
    "src/argus/agent_runtime/llm_interpreter.py",
    "src/argus/agent_runtime/semantic_integrity.py",
    "src/argus/agent_runtime/strategy_contract.py",
    "src/argus/agent_runtime/stages/execute.py",
    "src/argus/agent_runtime/rule_specs.py",
    "src/argus/agent_runtime/signal_rule_repair.py",
    "src/argus/agent_runtime/turn_progress.py",
    "src/argus/agent_runtime/turn_execution_evidence.py",
]

LEGACY_COMPOSER_PATH = Path("src/argus/agent_runtime/stages/compose.py")


def test_runtime_intent_boundary_does_not_depend_on_regex_nlu() -> None:
    """Strategy/runtime semantics must come from typed interpretation, not regex gates."""
    violations: list[str] = []

    for relative_path in RUNTIME_INTENT_FILES:
        path = Path(relative_path)
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                violations.extend(
                    f"{relative_path}: import {alias.name}"
                    for alias in node.names
                    if alias.name == "re"
                )
            if isinstance(node, ast.ImportFrom) and node.module == "re":
                violations.append(f"{relative_path}: from re import ...")
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "re"
            ):
                violations.append(f"{relative_path}: re.{node.attr}")

    assert violations == []


def test_runtime_does_not_restore_raw_message_semantic_routers() -> None:
    """Runtime routing must trust structured interpreter fields, not prose scanners."""
    forbidden_by_file = {
        "src/argus/agent_runtime/stages/interpret.py": [
            "_latest_result_followup_semantically_indicated",
            "_is_affirmative_pending_resolution_reply",
            "_typed_pending_need_fallback_stage_result_if_applicable",
            "typed_pending_need_validator_used",
            "summary = str(decision.user_goal_summary or \"\").lower()",
            "_message_asks_for_runnable_prompt_example",
            "runnable_prompt_example_route_suppressed",
            "retry_failed_action_prompt_example_suppressed",
            "_pending_date_endpoint_role",
            "_parse_pending_date_endpoint_answer",
            "deterministic_pending_date_answer_fallback",
            "_misclassified_dca_education_has_strategy_baggage",
            "_dca_education_answer_for_message",
            "_message_asks_for_strategy_explanation",
            "_message_mentions_dca_concept",
        ],
        "src/argus/agent_runtime/semantic_integrity.py": [
            "_current_turn_has_signal_rule_reference",
            "_semantic_tokens",
        ],
        "src/argus/agent_runtime/strategy_contract.py": [
            "_date_range_from_raw_phrase",
            "_extract_period_label_from_raw_phrase",
        ],
        "src/argus/agent_runtime/rule_specs.py": [
            "moving_average_crossover_rules_from_text",
            "_rule_tokens",
            "_moving_average_mentions",
        ],
        "src/argus/agent_runtime/signal_rule_repair.py": [
            "explicit_signal_rule_intent_from_text",
            "moving_average_crossover_rules_from_text",
        ],
        "src/argus/agent_runtime/turn_execution_evidence.py": [
            "explicit_signal_rule_intent_from_text",
            "moving_average_crossover_rules_from_text",
        ],
        "src/argus/agent_runtime/llm_interpreter.py": [
            "Nvidia to NVDA",
            "Apple to AAPL",
            "Tesla to TSLA",
            "Microsoft to MSFT",
            "_message_looks_like_investing_experiment",
            "_message_asks_for_capability_inventory",
            "explicit_signal_rule_intent_from_text",
            "_has_explicit_signal_rule_intent",
            "_message_states_current_date_endpoint",
            "_current_message_natural_date_range",
            "_response_can_use_current_message_natural_time",
            "_draft_contains_structured_date_context",
            "_draft_contains_structured_timeframe_context",
        ],
        "src/argus/agent_runtime/stages/confirm.py": [
            "Ready to test",
            "Use the card to run it when you are ready",
            "entry rule:",
        ],
    }
    violations: list[str] = []

    for relative_path, tokens in forbidden_by_file.items():
        source = Path(relative_path).read_text()
        for token in tokens:
            if token in source:
                violations.append(f"{relative_path}: {token}")

    assert violations == []


def test_runtime_contracts_do_not_own_human_language_date_tables() -> None:
    """Date language belongs behind argus.nlp.natural_time, not runtime contracts."""

    forbidden_by_file = {
        "src/argus/agent_runtime/strategy_contract.py": [
            "MONTH_ALIASES",
            "parse_date_text",
            "resolve_date_range_text",
            "_month_year_span",
            "_month_span_with_shared_year",
            "_build_month_year_date",
            "_date_range_resolution_from_natural",
            "_relative_period",
            "_year_to_date",
            "_multi_year_period",
            "_calendar_year",
            "_beginning_last_year",
            "_normalize_period_number_words",
            "_relative_date_label_from_user_phrasing",
            "_date_range_dict_uses_natural_endpoint",
            "_extract_relative_period_label",
            "_split_compact_period_token",
            "_subtract_period",
        ],
        "src/argus/agent_runtime/run_field_contract.py": [
            "current_message_date_range",
            "current_message_dca_cadence",
            "message_states_bar_timeframe",
            "resolve_current_message_date_patch",
            "MONTH_ALIASES",
            "MONTH_TOKENS",
            "_month_year_date_range_from_tokens",
            "_month_year_endpoint",
            "_year_so_far_date_range_from_tokens",
            "_multi_year_date_range_from_tokens",
            "_calendar_year_date_range_from_tokens",
            "_date_endpoint_from_marker_tokens",
            "_relative_date_endpoint_from_marker_tokens",
            "_tokens_after_year_include_date_endpoint",
        ],
    }
    violations: list[str] = []

    for relative_path, tokens in forbidden_by_file.items():
        source = Path(relative_path).read_text()
        for token in tokens:
            if token in source:
                violations.append(f"{relative_path}: {token}")

    assert violations == []


def test_legacy_response_composer_is_retired() -> None:
    """Assistant voice belongs to LLM clarification or explicit recovery paths."""

    assert not LEGACY_COMPOSER_PATH.exists()


def test_production_paths_do_not_import_legacy_response_composer() -> None:
    """Normal runtime paths must not revive compose.py as a shadow chat brain."""

    forbidden_tokens = [
        "argus.agent_runtime.stages.compose",
        "compose_response_intent",
        "should_prefer_composed_intent",
    ]
    production_files = [
        "src/argus/agent_runtime/runtime.py",
        "src/argus/agent_runtime/stages/clarify.py",
    ]
    violations: list[str] = []

    for relative_path in production_files:
        source = Path(relative_path).read_text()
        for token in forbidden_tokens:
            if token in source:
                violations.append(f"{relative_path}: {token}")

    assert violations == []


def test_runtime_llm_voice_prompts_are_not_english_locked() -> None:
    """LLM recovery voice must follow locale, not English-only prompt idioms."""

    prompt_files = [
        "src/argus/agent_runtime/llm_interpreter.py",
        "src/argus/agent_runtime/stages/interpret.py",
        "src/argus/agent_runtime/stages/recovery_composer.py",
    ]
    violations = [
        relative_path
        for relative_path in prompt_files
        if "plain English" in Path(relative_path).read_text()
    ]

    assert violations == []
