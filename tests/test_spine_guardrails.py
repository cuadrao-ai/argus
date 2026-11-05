"""P2.0 spine guardrail tripwires.

Fail-fast tests that catch reintroduction of the language-agnostic / non-deterministic
runtime spine violations that quarantined two prior P2 branches
(``codex/private-alpha-next-quarantine-fc231e8`` and
``codex/private-alpha-next-p2.1-quarantine``).

Context and rationale:

- See ``docs/specs/private-alpha-next-roadmap.md`` (P2 board, "P2.0 Spine guardrail gate"
  and the six cross-cutting invariants) and
  ``docs/archive/private-alpha-next-p2.1-capability-audit.md``.
- Both quarantines broke the spine with "tasteful" heuristics, NOT ``import re`` or
  ``if "buy" in message``. So these tripwires name banned MECHANISMS / SIGNATURES.
- They are source-level scans on purpose: the realistic regression is cherry-picking
  quarantine code back into the runtime, and a symbol/literal scan catches that precisely
  and deterministically (no flaky LLM/behavioral runs). Behavioral intent-override
  regressions remain additionally guarded by the interpret-stage behavioral tests and by
  human review.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ARGUS_SRC = REPO_ROOT / "src" / "argus"


def _py_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if p.is_file())


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


# --- Tripwire 1: banned quarantine symbols / reason codes ----------------------------
# Each maps to a concrete quarantine mechanism (see the autopsy summarized in the P2
# board doc). A match means quarantine runtime code was reintroduced.
BANNED_SIGNATURES = {
    # umbrella: deterministic ticker-shape classifier over raw user text
    "has_additional_ticker_style_evidence": (
        "deterministic ticker-shape classifier over user text"
    ),
    # umbrella: helper module that re-scans current_user_message to drive routing
    "current_message_asset_evidence": (
        "module that re-scans current_user_message for routing"
    ),
    # umbrella: deterministic benchmark provenance stamped from a message re-scan
    "_strategy_with_current_message_benchmark_evidence": (
        "deterministic benchmark provenance from a message re-scan"
    ),
    # p2.1: post-LLM intent override via text re-analysis + its reason code
    "_text_guardrail_response": "post-LLM intent override from text re-analysis",
    "non_alpha_indicator_text_guardrail_blocked_execution": (
        "post-LLM capability intent-override reason code"
    ),
    # p2.1: substring/keyword matching over prose for capability enforcement
    "_normalized_text_contains_term": (
        "substring/keyword matching over prose for capability"
    ),
    # p2.1: 'grounding' a value by literal text presence in the raw message
    "_span_appears_in_user_text": "literal-text grounding of LLM-extracted values",
}


@pytest.mark.parametrize("signature", sorted(BANNED_SIGNATURES))
def test_no_banned_spine_signature(signature: str) -> None:
    reason = BANNED_SIGNATURES[signature]
    offenders = [
        str(p.relative_to(REPO_ROOT))
        for p in _py_files(ARGUS_SRC)
        if signature in _read(p)
    ]
    assert not offenders, (
        f"Banned spine signature {signature!r} ({reason}) found in: {offenders}. "
        "This is a quarantine anti-pattern; see docs/specs/private-alpha-next-roadmap.md "
        "(P2.0 guardrail gate)."
    )


# --- Tripwire 2: banned per-language capability / message-rescan modules --------------
BANNED_MODULE_NAMES = {
    "capability_response_voice.py": "per-language (es-419/en) capability copy tables",
    "current_message_asset_evidence.py": "current-message re-scan helper module",
}


@pytest.mark.parametrize("module_name", sorted(BANNED_MODULE_NAMES))
def test_no_banned_quarantine_module(module_name: str) -> None:
    reason = BANNED_MODULE_NAMES[module_name]
    offenders = [str(p.relative_to(REPO_ROOT)) for p in ARGUS_SRC.rglob(module_name)]
    assert not offenders, (
        f"Banned quarantine module {module_name!r} ({reason}) present: {offenders}."
    )


# --- Tripwire 3: no per-language branching in the interpretation/capability path ------
# Capability and clarification copy must be model-voiced; English/Spanish parity is proven
# by eval, not by per-language literals in the runtime interpretation path. Legitimate
# presentation-layer i18n (presentation_i18n.py, recovery_messages.py, and the other
# established locale-aware modules) is the accepted baseline and is intentionally NOT
# policed here; this tripwire guards only the interpret stage, the LLM interpreter, and
# the capability modules, where the quarantine added per-language copy.
LOCALE_FORBIDDEN_FILES = [
    ARGUS_SRC / "agent_runtime" / "stages" / "interpret.py",
    ARGUS_SRC / "agent_runtime" / "llm_interpreter.py",
]
LOCALE_FORBIDDEN_DIRS = [
    ARGUS_SRC / "agent_runtime" / "capabilities",
]
LOCALE_LITERAL = "es-419"


def _locale_scan_targets() -> list[Path]:
    targets = [p for p in LOCALE_FORBIDDEN_FILES if p.exists()]
    for directory in LOCALE_FORBIDDEN_DIRS:
        if directory.exists():
            targets.extend(_py_files(directory))
    return targets


@pytest.mark.parametrize(
    "path",
    [
        pytest.param(p, id=str(p.relative_to(REPO_ROOT)))
        for p in _locale_scan_targets()
    ],
)
def test_no_per_language_branch_in_interpretation_path(path: Path) -> None:
    assert LOCALE_LITERAL not in _read(path), (
        f"Per-language literal {LOCALE_LITERAL!r} found in {path.relative_to(REPO_ROOT)}. "
        "Capability/clarification copy must be model-voiced, not branched per language "
        "(P2.0 guardrail gate, invariant 5)."
    )


def test_locale_scan_covers_expected_files() -> None:
    """Guard the guard: ensure the locale scan actually resolved its core targets, so a
    moved/renamed interpret stage cannot silently empty the parametrization."""
    resolved = {p.name for p in _locale_scan_targets()}
    assert {"interpret.py", "llm_interpreter.py"} <= resolved, (
        "Locale tripwire lost its core targets; update LOCALE_FORBIDDEN_FILES if the "
        f"interpret stage moved. Resolved: {sorted(resolved)}"
    )


# --- Tripwire 4: issue #154 migrated surfaces stay language-agnostic ----------
# These are the S1/S3 surfaces plus the S2-cleaned heading surface already
# migrated away from deterministic en/es runtime copy. Keep presentation helpers
# and API schema aliases out until their typed frontend/API contracts are explicit.
ISSUE_154_MIGRATED_LANGUAGE_SURFACES = [
    ARGUS_SRC / "agent_runtime" / "stages" / "explain.py",
    ARGUS_SRC / "api" / "chat" / "confirmation.py",
    ARGUS_SRC / "api" / "chat" / "confirmation_lifecycle.py",
    ARGUS_SRC / "api" / "chat" / "confirmation_research_peers.py",
    ARGUS_SRC / "agent_runtime" / "recovery_messages.py",
    ARGUS_SRC / "agent_runtime" / "clarification_contract.py",
    ARGUS_SRC / "agent_runtime" / "artifact_action_recovery.py",
    ARGUS_SRC / "agent_runtime" / "stages" / "execute.py",
    ARGUS_SRC / "agent_runtime" / "response_style.py",
]

ISSUE_154_LANGUAGE_GATES = {
    "_is_spanish": "per-language helper gate",
    'Literal["en", "es-419"]': "two-language runtime literal clone",
    "Literal['en', 'es-419']": "two-language runtime literal clone",
    "es-419": "inline locale-specific runtime copy or branch",
    'startswith("es")': "Spanish-prefix runtime branch",
    "startswith('es')": "Spanish-prefix runtime branch",
}


@pytest.mark.parametrize(
    "path",
    [
        pytest.param(p, id=str(p.relative_to(REPO_ROOT)))
        for p in ISSUE_154_MIGRATED_LANGUAGE_SURFACES
    ],
)
def test_issue_154_migrated_surfaces_have_no_runtime_language_gates(
    path: Path,
) -> None:
    text = _read(path)
    offenders = {
        signature: reason
        for signature, reason in ISSUE_154_LANGUAGE_GATES.items()
        if signature in text
    }
    assert not offenders, (
        f"Issue #154 language gate(s) found in {path.relative_to(REPO_ROOT)}: "
        f"{offenders}. Migrated runtime prose must use typed facts plus LLM "
        "composition or typed recovery codes plus web i18n."
    )


def test_issue_154_language_guard_covers_expected_migrated_surfaces() -> None:
    missing = [
        str(path.relative_to(REPO_ROOT))
        for path in ISSUE_154_MIGRATED_LANGUAGE_SURFACES
        if not path.exists()
    ]
    assert not missing, f"Issue #154 language guard lost target file(s): {missing}"
