from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

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


def _event(tmp_path: Path, body: str | None, login: str = "dev") -> Path:
    payload = {"pull_request": {"body": body, "user": {"login": login}}}
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
    result = _run(_event(tmp_path, VALID_BLOCK))

    assert result.returncode == 0, result.stderr


def test_dependabot_is_exempt(tmp_path: Path) -> None:
    result = _run(_event(tmp_path, "", login="dependabot[bot]"))

    assert result.returncode == 0, result.stderr
    assert "dependabot[bot]" in result.stdout


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
