from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "ci" / "check_pr_body.py"
TEMPLATE = ROOT / ".github" / "pull_request_template.md"
WORKFLOW = ROOT / ".github" / "workflows" / "pr-body.yml"

EVAL_TIERS = """\
## Eval tiers (agreed with the evaluator, use verbatim)

- No Eval: docs-only PRs. They land on green CI.
- Light Eval: two-way-door changes with a narrow blast radius: no auth, money math, security, secrets, migrations, tables, grants or RLS, and no flag turned on in production. Examples are tooling, CI, tests, copy and contained UI. Eval confirms the exact head SHA and green CI, a clean trial merge onto the current tip, that the diff matches the Merge Danger block's blast radius and rollback, and the evidence-media gate. Eval runs the touched tests itself, including any touched e2e spec CI doesn't run. No full repro or adversarial pass.
- Full Eval (always): anything touching auth, money, security, secrets or migrations/schema/grants/RLS; any one-way door; any PR whose rollback isn't a plain revert; any flag turned on in production; and any PR over 400 changed non-test lines (lockfiles, generated files and fixtures excluded). Full adds a targeted repro of the riskiest path, and mutation checks on auth, money or security code.
- Staging flags: turning a flag on in staging only is Light, but Eval checks the flag is declared in every hosted-settings file and render.yaml and that production stays "false". Turning a flag off anywhere is Light.
- Mismatch rule: if the Merge Danger block understates the blast radius, it goes to Full. Eval can always raise a tier, never lower it.
"""

HEADINGS = (
    "## Merge Danger",
    "## Eval tiers (agreed with the evaluator, use verbatim)",
    "## TL;DR",
    "## Motivation",
    "## Changes",
    "## Out of scope",
    "## Testing",
    "## Risks/Rollback",
    "## Docs affected",
    "## Status",
)

EVIDENCE_GUIDANCE = (
    "Attach screenshots, recordings, and PDFs on the pull request, "
    "or upload them with actions/upload-artifact. Do not commit them "
    "under `docs/reports/` or an evidence folder."
)

VALID_BLOCK = """\
## Merge Danger

- Door: two-way
- Blast radius: scripts/ci/check_pr_body.py
- Rollback: revert the commit
- Eval tier: Light
"""
VALID_BODY = VALID_BLOCK + "\n## TL;DR\n\nCloses #1599\nPilot flow: review\n"


def _event(
    tmp_path: Path, body: str | None, login: str = "dev", user_type: str = "User"
) -> Path:
    payload = {
        "pull_request": {"body": body, "user": {"login": login, "type": user_type}}
    }
    path = tmp_path / "event.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _run(event_path: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["GITHUB_EVENT_PATH"] = str(event_path)
    return subprocess.run(
        [sys.executable, str(CHECKER)],
        capture_output=True,
        text=True,
        env=env,
    )


def test_missing_block_fails(tmp_path: Path) -> None:
    result = _run(_event(tmp_path, "## TL;DR\n\nNo danger block.\n"))

    assert result.returncode != 0
    assert "missing Merge Danger block" in result.stderr


def test_empty_fields_fail(tmp_path: Path) -> None:
    body = """\
## Merge Danger

- Door:
- Blast radius:
- Rollback:
"""
    result = _run(_event(tmp_path, body))

    assert result.returncode != 0
    assert "Door is empty" in result.stderr
    assert "Blast radius is empty" in result.stderr
    assert "Rollback is empty" in result.stderr


def test_untouched_placeholders_fail(tmp_path: Path) -> None:
    body = """\
## Merge Danger

- Door: <one-way or two-way>
- Blast radius: <files, tables, routes, flags>
- Rollback: <steps>
"""
    result = _run(_event(tmp_path, body))

    assert result.returncode != 0
    assert "Door is an untouched placeholder" in result.stderr
    assert "Blast radius is an untouched placeholder" in result.stderr
    assert "Rollback is an untouched placeholder" in result.stderr


def test_bad_door_fails(tmp_path: Path) -> None:
    body = """\
## Merge Danger

- Door: sideways
- Blast radius: scripts/ci/check_pr_body.py
- Rollback: revert the commit
"""
    result = _run(_event(tmp_path, body))

    assert result.returncode != 0
    assert "Door must be one-way or two-way" in result.stderr


def test_valid_block_passes(tmp_path: Path) -> None:
    result = _run(_event(tmp_path, VALID_BODY))

    assert result.returncode == 0, result.stderr


def test_dependabot_is_exempt(tmp_path: Path) -> None:
    result = _run(_event(tmp_path, "", login="dependabot[bot]"))

    assert result.returncode == 0, result.stderr
    assert "dependabot[bot]" in result.stdout


@pytest.mark.parametrize(
    "reference", ["", "Closes #0", "Fixes #abc", "Related #1599", "See Closes #1599"]
)
def test_missing_or_invalid_issue_reference_fails(tmp_path: Path, reference: str) -> None:
    body = VALID_BODY.replace("Closes #1599", reference)
    result = _run(_event(tmp_path, body))

    assert result.returncode != 0
    assert "issue reference" in result.stderr


@pytest.mark.parametrize(
    "reference",
    [
        "Closes #1599",
        "Fixes #1599",
        "Refs #1599",
        "Closes #1599.",
        "- Closes #1599",
        "* Fixes #1599",
        "closes #1599",
        "Closes #1599. Refs #1598.",
        "Closes #1599 (item 1 only; the rest stays open)",
        "Fixes #1599 on integration",
    ],
)
def test_issue_reference_lines_pass(tmp_path: Path, reference: str) -> None:
    result = _run(_event(tmp_path, VALID_BODY.replace("Closes #1599", reference)))

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "flow",
    [
        "",
        "Pilot flow:",
        "Pilot flow: unknown",
        "Pilot flow: none",
        "Pilot flow: none ()",
        "Pilot flow: none (   )",
        "Pilot flow: none (<reason>)",
        "Pilot flow: none (reason)",
        "Pilot flow: upload | email",
        "Pilot flow: upload, unknown",
        "Pilot flow: upload,",
        "Pilot flow: upload, none (CI metadata only)",
        "See Pilot flow: review",
    ],
)
def test_missing_or_invalid_pilot_flow_fails(tmp_path: Path, flow: str) -> None:
    result = _run(_event(tmp_path, VALID_BODY.replace("Pilot flow: review", flow)))

    assert result.returncode != 0
    assert "Pilot flow" in result.stderr
    assert "upload, email, WhatsApp, review, month close, 606/607" in result.stderr


@pytest.mark.parametrize(
    "flow",
    [
        "upload",
        "email",
        "WhatsApp",
        "review",
        "month close",
        "606/607",
        "none (CI metadata only)",
        "upload, review",
        "upload,review,606/607",
    ],
)
def test_allowed_pilot_flow_passes(tmp_path: Path, flow: str) -> None:
    body = VALID_BODY.replace("Pilot flow: review", f"Pilot flow: {flow}")
    result = _run(_event(tmp_path, body))

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "login,user_type",
    [("automation[bot]", "Bot"), ("automation", "Bot"), ("automation[bot]", "User")],
)
def test_bot_authors_are_exempt(tmp_path: Path, login: str, user_type: str) -> None:
    result = _run(_event(tmp_path, None, login=login, user_type=user_type))

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("login", ["robot", "automation-bot", "dependabot"])
def test_human_authors_are_not_exempt(tmp_path: Path, login: str) -> None:
    result = _run(_event(tmp_path, "", login=login))

    assert result.returncode != 0


def test_bot_sender_does_not_exempt_human_author(tmp_path: Path) -> None:
    event = _event(tmp_path, "")
    payload = json.loads(event.read_text(encoding="utf-8"))
    payload["sender"] = {"login": "automation[bot]", "type": "Bot"}
    event.write_text(json.dumps(payload), encoding="utf-8")

    assert _run(event).returncode != 0


def test_template_opens_with_merge_danger_and_states_eval_tiers() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")

    assert text.startswith("## Merge Danger\n")
    assert EVAL_TIERS in text
    assert EVIDENCE_GUIDANCE in text
    positions = [text.index(heading) for heading in HEADINGS]
    assert positions == sorted(positions)
    assert "dependabot" not in text.lower()


def test_template_passes_once_filled(tmp_path: Path) -> None:
    raw = TEMPLATE.read_text(encoding="utf-8")
    filled = (
        raw.replace("<one-way or two-way>", "two-way", 1)
        .replace(
            "<files, tables, routes, flags>",
            "the template, the script, the workflow, the tests, and AGENTS.md",
            1,
        )
        .replace("<steps>", "revert the commit", 1)
        .replace("<No Eval, Light, or Full>", "Light", 1)
        .replace("#<issue>", "#1599", 1)
        .replace(
            "<upload | email | WhatsApp | review | month close | 606/607 | none (reason)>",
            "review",
            1,
        )
    )

    assert filled != raw
    result = _run(_event(tmp_path, filled))

    assert result.returncode == 0, result.stderr


def test_pr_body_workflow_runs_on_edit_without_a_path_filter() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    pull_request = workflow["on"]["pull_request"]
    steps = workflow["jobs"]["merge-danger"]["steps"]

    assert pull_request["types"] == ["opened", "edited", "synchronize", "reopened"]
    assert "paths" not in pull_request
    assert "paths" not in workflow["on"]
    assert any(step.get("run") == "python scripts/ci/check_pr_body.py" for step in steps)
    ci = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    assert "edited" not in ci["on"]["pull_request"]["types"]
