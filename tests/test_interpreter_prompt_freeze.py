"""The text the interpretation model reads is frozen against measured evidence.

Unit tests never send a message through a model, so a prompt edit passes every
gate in CI and only surfaces in the paid live eval after the merge. PR #491
rewrote the shared prompt for a DCA change and silently broke asset extraction,
date preservation, and discovery routing in three unrelated places.

Changing this surface therefore requires re-measuring it, and this test is what
forces the scorecard to exist.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.interpreter_prompt_surface import (
    DOCUMENT_EXTRACTOR_OWNER,
    FINGERPRINT_PATH,
    fingerprint_surface,
    load_fingerprint,
    model_facing_surface,
    require_document_extraction_measurement,
    surface_drift,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

_HOW_TO_UPDATE = f"""
This is the shared instruction text and response schema every interpreted turn
passes through, so a change here can move behavior far from the lane that made
it. To land one:

  1. Run the live measurement for the affected scope on the branch.
  2. Commit its scorecard under docs/reports/evidence/.
  3. Compare it against the scorecard named in {FINGERPRINT_PATH} and confirm no
     case regressed within that scope.
  4. Update that scope's fingerprint and last_measured to the new scorecard;
     preserve other scopes' evidence and totals.

If you did not intend to touch model-facing text, revert instead.
"""


@pytest.fixture(scope="module")
def fingerprint() -> dict[str, object]:
    return load_fingerprint(REPOSITORY_ROOT)


@pytest.fixture(scope="module")
def observed() -> dict[str, dict[str, object]]:
    return model_facing_surface(REPOSITORY_ROOT)


def test_model_facing_text_matches_its_measured_fingerprint(
    fingerprint: dict[str, object],
    observed: dict[str, dict[str, object]],
) -> None:
    recorded = fingerprint_surface(fingerprint)

    changed, added, removed = surface_drift(recorded, observed)
    if not (changed or added or removed):
        return

    report = []
    for name in changed:
        was = recorded[name]
        now = observed[name]
        report.append(
            f"  changed  {name}  ({was['chars']} -> {now['chars']} chars, "
            f"{was['entries']} -> {now['entries']} entries)"
        )
    report.extend(f"  added    {name}" for name in added)
    report.extend(f"  removed  {name}" for name in removed)

    measured = fingerprint["last_measured"]
    assert isinstance(measured, dict)
    pytest.fail(
        "Text the interpretation model reads changed since it was last measured.\n"
        + "\n".join(report)
        + f"\n\nLast measured at {measured['commit']}: "
        + f"{measured['passed']} passed, {measured['failed']} failed.\n"
        + _HOW_TO_UPDATE
    )


def test_fingerprint_names_a_scorecard_that_exists(
    fingerprint: dict[str, object],
) -> None:
    """A fingerprint without its evidence is an unmeasured prompt."""

    measured = fingerprint["last_measured"]
    assert isinstance(measured, dict)

    scorecard = REPOSITORY_ROOT / str(measured["scorecard"])
    assert scorecard.is_file(), (
        f"{FINGERPRINT_PATH} points at {measured['scorecard']}, which is not "
        "committed. The fingerprint records that the prompt was measured, so "
        "the measurement has to travel with it."
    )

    totals = json.loads(scorecard.read_text(encoding="utf-8"))["totals"]
    assert totals["passed"] == measured["passed"]
    assert totals["failed"] == measured["failed"]


def test_the_interpreter_system_prompt_is_covered(
    observed: dict[str, dict[str, object]],
) -> None:
    """Guard the guard: the file that caused this must stay in scope."""

    interpreter = observed.get("src/argus/agent_runtime/llm_interpreter.py")
    assert interpreter is not None, (
        "The extractor no longer sees the interpreter's system prompt. Either "
        "the prompt moved, or the extraction rule stopped matching it."
    )
    assert int(str(interpreter["chars"])) > 10_000


def test_document_extractor_prompt_is_covered(
    observed: dict[str, dict[str, object]],
) -> None:
    assert int(str(observed[DOCUMENT_EXTRACTOR_OWNER]["chars"])) > 1_000


def test_document_extraction_names_an_accepted_scoped_measurement(
    fingerprint: dict[str, object],
) -> None:
    require_document_extraction_measurement(REPOSITORY_ROOT, fingerprint)
