from __future__ import annotations

import ast
from pathlib import Path

RUNTIME_INTENT_FILES = [
    "src/argus/agent_runtime/strategy_contract.py",
    "src/argus/agent_runtime/rule_specs.py",
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
        "src/argus/agent_runtime/strategy_contract.py": [
            "_date_range_from_raw_phrase",
            "_extract_period_label_from_raw_phrase",
        ],
        "src/argus/agent_runtime/rule_specs.py": [
            "moving_average_crossover_rules_from_text",
            "_rule_tokens",
            "_moving_average_mentions",
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
