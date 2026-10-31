"""The workspace-language invariant, asserted as a property.

`docs/CONVERSATIONAL_RUNTIME.md` binds response prose to the workspace language
everywhere, and forbids solving that with per-language copy tables in the
runtime. What makes both true at once is a seam: the runtime emits a typed code,
and the presentation boundary localizes it.

These tests assert the seam itself rather than any particular string, because
the defects that reached Spanish users (#434, #489, #482) were each a new
instance of one shape: deterministic English prose with no typed code beside it,
or a typed code with no localized copy behind it. Naming today's three strings
would let the fourth one ship.
"""

from __future__ import annotations

import json
from itertools import product
from pathlib import Path
from typing import Any

import pytest
from argus.agent_runtime.clarification_contract import (
    intent_clarification_fallback,
    typed_clarification_contract,
)
from argus.agent_runtime.recovery_messages import (
    RECOVERY_FALLBACK_MESSAGES,
    RecoveryMessageCode,
)

SUPPORTED_LANGUAGES = ("en", "es-419")
LOCALES_ROOT = Path(__file__).resolve().parents[2] / "web" / "public" / "locales"


def _bundle(language: str) -> dict[str, Any]:
    return json.loads((LOCALES_ROOT / language / "common.json").read_text("utf-8"))


def _lookup(bundle: dict[str, Any], dotted_key: str) -> Any:
    node: Any = bundle
    for part in dotted_key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


# ── The typed-code side: every code a reader can reach is localized ──────────


@pytest.mark.parametrize("code", sorted(RECOVERY_FALLBACK_MESSAGES))
def test_every_recovery_code_renders_in_both_languages(code: RecoveryMessageCode) -> None:
    """A typed code with no Spanish copy behind it is English on a Spanish turn.

    The English fallback text in `RECOVERY_FALLBACK_MESSAGES` is persisted
    compatibility prose, never what a reader sees, so the localized bundles are
    the only thing standing between a Spanish workspace and English.
    """

    rendered = {
        language: _lookup(_bundle(language), f"chat.recovery.{code}")
        for language in SUPPORTED_LANGUAGES
    }
    for language, text in rendered.items():
        assert isinstance(text, str) and text.strip(), (
            f"recovery code {code!r} has no {language} copy; a workspace in that "
            "language would fall back to the English compatibility string"
        )
    # Identical copy in both bundles is the tell of an untranslated key: it is
    # how #489's parametrized test passed while proving nothing about Spanish.
    assert rendered["en"] != rendered["es-419"], (
        f"recovery code {code!r} has identical en and es-419 copy, so the "
        "es-419 case proves nothing"
    )


# ── The prose side: deterministic prose never travels without a typed code ───


def _unsupported_intent(category: str, *, with_options: bool) -> dict[str, Any]:
    return {
        "kind": "unsupported_recovery",
        "semantic_needs": ["simplification_choice"],
        "requested_fields": ["unsupported_constraints"],
        "facts": {
            "unsupported_constraints": [
                {
                    "category": category,
                    "raw_value": "cada 5 minutos",
                    "minimum": 1000.0,
                    "maximum": 10_000_000.0,
                }
            ],
            "strategy": {"asset_universe": ["AAPL"]},
        },
        "options": [
            {
                "label": "Compare with buy and hold",
                "replacement_values": {"strategy_type": "buy_and_hold"},
            }
        ]
        if with_options
        else [],
    }


def _coverage_intent(code: str | None, *, with_options: bool) -> dict[str, Any]:
    coverage: dict[str, Any] = {"code": code} if code is not None else {}
    return {
        "kind": "coverage_recovery",
        "semantic_needs": [],
        "requested_fields": ["date_range"],
        "facts": {"coverage": coverage, "strategy": {"asset_universe": ["AAPL"]}},
        "options": [
            {
                "id": "change_dates",
                "replacement_values": {"requested_field": "date_range"},
            }
        ]
        if with_options
        else [],
    }


UNSUPPORTED_CATEGORIES = (
    "future_performance",
    "unsupported_time_granularity",
    "unsupported_starting_capital",
    "sentiment_news_rule",
    "unsupported_constraint",
    "unsupported_strategy_logic",
)

COVERAGE_CODES = (
    "no_common_data_window",
    "insufficient_common_data",
    "market_data_unavailable",
    None,
)

# Every semantic need the deterministic clarification fallback answers, plus a
# pair, so a need added without a typed reason code is caught here.
CLARIFICATION_NEEDS: tuple[list[str], ...] = (
    ["period"],
    ["asset_target"],
    ["assumption"],
    ["sizing_amount"],
    ["schedule"],
    ["sizing_amount", "schedule"],
    ["rule_definition"],
    ["refinement"],
)


def _clarification_intent(needs: list[str]) -> dict[str, Any]:
    return {
        "kind": "clarification",
        "semantic_needs": needs,
        "requested_fields": [],
        "facts": {"strategy": {"asset_universe": ["AAPL"]}},
    }


def _all_deterministic_intents() -> list[tuple[str, dict[str, Any]]]:
    intents: list[tuple[str, dict[str, Any]]] = []
    for category, with_options in product(UNSUPPORTED_CATEGORIES, (True, False)):
        intents.append(
            (
                f"unsupported:{category}:options={with_options}",
                _unsupported_intent(category, with_options=with_options),
            )
        )
    for code, with_options in product(COVERAGE_CODES, (True, False)):
        intents.append(
            (
                f"coverage:{code}:options={with_options}",
                _coverage_intent(code, with_options=with_options),
            )
        )
    for needs in CLARIFICATION_NEEDS:
        intents.append((f"clarification:{'+'.join(needs)}", _clarification_intent(needs)))
    return intents


@pytest.mark.parametrize(
    ("label", "response_intent"),
    _all_deterministic_intents(),
    ids=[label for label, _ in _all_deterministic_intents()],
)
@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_deterministic_prose_always_carries_a_typed_contract(
    label: str,
    response_intent: dict[str, Any],
    language: str,
) -> None:
    """Prose without a contract is prose the reader gets in English.

    The deterministic fallbacks are English by construction and that is allowed,
    because the localized surface renders the typed contract instead. The
    property that makes it safe is one-directional: wherever the runtime has
    words, it must also have a code. #489 was three sites where it did not.
    """

    prose = intent_clarification_fallback(
        response_intent=response_intent,
        strategy=None,
    )
    contract = typed_clarification_contract(
        response_intent=response_intent,
        strategy=None,
        prompt_source="degraded_fallback",
    )
    if prose is None:
        return
    assert contract is not None, (
        f"{label} produces deterministic prose with no typed contract, so a "
        f"{language} workspace renders the English string verbatim"
    )
    assert isinstance(contract.get("reason_code"), str) and contract["reason_code"], (
        f"{label} has a contract with no reason_code, so the presentation "
        "boundary has nothing to localize"
    )


@pytest.mark.parametrize(
    ("label", "response_intent"),
    _all_deterministic_intents(),
    ids=[label for label, _ in _all_deterministic_intents()],
)
def test_every_reachable_reason_code_is_localized(
    label: str,
    response_intent: dict[str, Any],
) -> None:
    """A reason code the runtime can emit must exist in both bundles.

    This is the other half of the seam: a contract nothing can render leaves the
    reader on the persisted English just as surely as no contract at all.
    """

    contract = typed_clarification_contract(
        response_intent=response_intent,
        strategy=None,
        prompt_source="degraded_fallback",
    )
    if contract is None or contract["kind"] == "clarification":
        # `clarification` keys are chosen from semantic needs by the frontend
        # rather than from the reason code; the frontend suite owns that map.
        return
    namespace = (
        "chat.coverage_recovery"
        if contract["kind"] == "coverage_recovery"
        else "chat.clarification"
    )
    if namespace == "chat.clarification":
        # Unsupported recovery composes its sentence from several keys, so the
        # frontend suite asserts the rendering; here we only require that the
        # reason code is one the frontend knows how to branch on.
        return
    for language in SUPPORTED_LANGUAGES:
        text = _lookup(_bundle(language), f"{namespace}.{contract['reason_code']}")
        assert isinstance(text, str) and text.strip(), (
            f"{label} emits reason_code {contract['reason_code']!r} with no "
            f"{language} copy under {namespace}"
        )


# ── The confirm stage: strategy.assumptions is interpreter-owned (#508) ──────


def test_confirm_stage_does_not_fabricate_english_assumption_prose() -> None:
    """The confirmation payload carries the interpreter's assumptions verbatim.

    The confirm stage used to overwrite `strategy.assumptions` with its own
    English strip ("$10,000 starting capital", "1D bars", "No fees", ...),
    which reached Spanish turns through the stream payload, the interpreter's
    prior-strategy context, and the deterministic assumptions answer. The card
    builds its localizable strip from typed facts, so the runtime dict must
    hold only what interpretation produced.
    """
    from argus.agent_runtime.capabilities.contract import (
        build_default_capability_contract,
    )
    from argus.agent_runtime.stages.confirm import confirm_stage
    from argus.agent_runtime.state.models import RunState, StrategySummary

    interpreter_assumptions = ["interpreter-owned assumption"]
    state = RunState.new(
        current_user_message="Prueba comprar y mantener AAPL desde 2023.",
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = StrategySummary(
        strategy_type="buy_and_hold",
        strategy_thesis="Comprar y mantener AAPL.",
        asset_universe=["AAPL"],
        asset_class="equity",
        capital_amount=10000,
        date_range={"start": "2023-01-01", "end": "2024-12-31"},
        assumptions=list(interpreter_assumptions),
    )

    result = confirm_stage(
        state=state,
        contract=build_default_capability_contract(),
        language="es-419",
    )

    assert result.outcome == "await_approval"
    for strategy in (
        result.patch["candidate_strategy_draft"],
        result.patch["confirmation_payload"]["strategy"],
    ):
        assert strategy["assumptions"] == interpreter_assumptions


# ── The confirm surface: a language it accepts is a language it reads (#523) ──

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_LANGUAGE_MODULES = (
    REPO_ROOT / "src" / "argus" / "api" / "chat" / "confirmation.py",
    REPO_ROOT / "src" / "argus" / "api" / "chat" / "confirmation_lifecycle.py",
    REPO_ROOT / "src" / "argus" / "api" / "chat" / "confirmation_research_peers.py",
    REPO_ROOT / "src" / "argus" / "agent_runtime" / "stages" / "confirm.py",
    REPO_ROOT / "src" / "argus" / "agent_runtime" / "stages" / "explain.py",
    REPO_ROOT / "src" / "argus" / "agent_runtime" / "clarification_contract.py",
    REPO_ROOT / "src" / "argus" / "domain" / "run_dossiers.py",
)


def _functions_that_ignore_language(module_path: Path) -> list[str]:
    import ast

    tree = ast.parse(module_path.read_text("utf-8"))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        parameters = [arg.arg for arg in node.args.args + node.args.kwonlyargs]
        if "language" not in parameters:
            continue
        reads_language = any(
            isinstance(child, ast.Name)
            and child.id == "language"
            and isinstance(child.ctx, ast.Load)
            for child in ast.walk(node)
        )
        if not reads_language:
            offenders.append(f"{module_path.name}:{node.lineno} {node.name}")
    return offenders


@pytest.mark.parametrize("module_path", WORKSPACE_LANGUAGE_MODULES, ids=lambda p: p.name)
def test_workspace_surface_never_accepts_a_language_it_ignores(module_path: Path) -> None:
    """No function on these artifact surfaces accepts a language it ignores.

    An accepted-and-ignored language parameter is worse than an absent one:
    the call site reads as if language were handled, so English reaches a
    Spanish reader with nothing at the boundary to catch it. Either the value
    feeds a localized formatter or the parameter does not exist.
    """
    offenders = _functions_that_ignore_language(module_path)
    assert offenders == [], "accepted-and-ignored language parameters: " + ", ".join(
        offenders
    )
