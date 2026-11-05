"""A git repository shaped like the live measurement, for evidence identity tests.

It holds one file of each kind the identity policy separates, so a test changes
one kind and asks whether evidence measured before the change still stands.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterable, Mapping
from pathlib import Path

from tests.evals.measurement_eval_scorecard import (
    measurement_fixture_identity_at_git_sha,
)
from tests.promotion_evidence_configuration import release_configuration_at_commit
from tests.promotion_evidence_identity import MEASUREMENT_ENTRY

PYTHON_VERSION = "3.10.20"
MEASUREMENT_CASES = "tests/evals/measurement_cases/messy_english.yaml"

_ENGINE = (
    "def execute(value):\n"
    "    from .ledger import record\n\n"
    "    return record(value)\n"
)
_LEDGER = "def record(value):\n    return value\n"
_HARNESS = (
    "from argus.stages import interpret\n\n\n"
    "def run_eval_case(case):\n"
    "    from argus.engine import execute\n\n"
    "    return execute(interpret(case))\n"
)

# Each reaches the measurement, so changing it needs a new one. Python the eval
# never imports is here too, because reach counts whatever it could import.
REACHED_BY_THE_EVAL = {
    "imported-module": "src/argus/stages.py",
    "lazily-imported-module": "src/argus/engine.py",
    "relatively-imported-module": "src/argus/ledger.py",
    "module-the-eval-never-imports": "src/argus/unmeasured.py",
    "test-module": "tests/evals/test_unrelated.py",
    "package-named-by-a-string": "web/argus_display_contract/__init__.py",
    "data-beside-measured-code": "web/argus_display_contract/policy.json",
    "eval-harness": "tests/evals/measurement_eval_harness.py",
    "conftest": "tests/conftest.py",
    "eval-fixture": MEASUREMENT_CASES,
    "import-roots-and-test-config": "pyproject.toml",
    "dependency-lock": "poetry.lock",
    "interpreter-pin": ".python-version",
}

# None reaches the measurement, so evidence survives changing them.
UNREACHED_BY_THE_EVAL = {
    "release-flags": (
        "render.yaml",
        ".github/private-alpha-release-profile.json",
        "scripts/ops/staging_env_manifest.json",
    ),
    "environment-template": (".env.example",),
    "migration": ("supabase/migrations/20260913000000_example.sql",),
    "frontend": ("web/app/page.tsx",),
    "docs": ("docs/release-manifests/notes.md",),
    "root-documentation": ("AGENTS.md",),
    "evidence-script": ("docs/reports/evidence/2026-09-13-promotion/run_pair.py",),
}

# Files added, deleted or moved: (committed before measuring, committed after,
# the reached files that differ). None deletes a file.
STRUCTURAL_CHANGES_REACHED: dict[
    str,
    tuple[Mapping[str, str | None], Mapping[str, str | None], tuple[str, ...]],
] = {
    "added-package-shadows-a-module": (
        {},
        {"src/argus/engine/__init__.py": _LEDGER},
        ("src/argus/engine/__init__.py",),
    ),
    "deleted-module": ({}, {"src/argus/ledger.py": None}, ("src/argus/ledger.py",)),
    "renamed-module": (
        {},
        {
            "src/argus/ledger.py": None,
            "src/argus/journal.py": _LEDGER,
            "src/argus/engine.py": _ENGINE.replace(".ledger", ".journal"),
        },
        ("src/argus/engine.py", "src/argus/journal.py", "src/argus/ledger.py"),
    ),
    "fixture-beside-an-unimported-script": (
        {"tests/evals/measurement_cases/generate.py": "CASES = []\n"},
        {MEASUREMENT_CASES: json.dumps({"cases": [{"id": "case-c"}]})},
        (MEASUREMENT_CASES,),
    ),
    "python-startup-module": (
        {},
        {"src/sitecustomize.py": "import os\n"},
        ("src/sitecustomize.py",),
    ),
    "pytest-config-added-at-the-root": (
        {},
        {".pytest.ini": "[pytest]\naddopts = -p no:cacheprovider\n"},
        (".pytest.ini",),
    ),
    "coverage-config-added-at-the-root": (
        {},
        {".coveragerc": "[run]\nbranch = True\n"},
        (".coveragerc",),
    ),
    "module-a-pytest-config-names": (
        {
            "pytest.ini": "[pytest]\naddopts = -p tests.evals.plugin\n",
            "tests/evals/plugin.py": "VALUE = 1\n",
        },
        {"tests/evals/plugin.py": "VALUE = 2\n"},
        ("tests/evals/plugin.py",),
    ),
    "warning-category-a-pytest-config-names": (
        {
            "pytest.ini": "[pytest]\nfilterwarnings = ignore::extras.CustomWarning\n",
            "src/extras.py": "class CustomWarning(Warning):\n    pass\n",
        },
        {"src/extras.py": "class CustomWarning(UserWarning):\n    pass\n"},
        ("src/extras.py",),
    ),
    "pythonpath-a-pytest-config-declares": (
        {
            "pytest.ini": "[pytest]\npythonpath = vendored-lib\n",
            "vendored-lib/extras.py": "VALUE = 1\n",
        },
        {"vendored-lib/extras.py": "VALUE = 2\n"},
        ("vendored-lib/extras.py",),
    ),
}


def commit_measured_repository(
    repository_root: Path, *, case_ids: Iterable[str] = ("case-a", "case-b")
) -> str:
    """Initialise a repository holding every kind of file, and commit it."""

    _git(repository_root, "init", "--quiet")
    return commit_files(repository_root, _layout(case_ids), message="measured")


def commit_files(
    repository_root: Path,
    writes: Mapping[str, str | None],
    *,
    message: str = "change",
) -> str:
    """Write each file, deleting it for None, and commit."""

    for relative, content in writes.items():
        path = repository_root / relative
        if content is None:
            path.unlink()
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return _commit(repository_root, message)


def commit_changes(repository_root: Path, paths: Iterable[str]) -> str:
    """Change each file by a trailing newline, which keeps every format valid."""

    return commit_files(
        repository_root,
        {
            relative: (repository_root / relative).read_text(encoding="utf-8") + "\n"
            for relative in paths
        },
    )


def live_eval_scorecard(repository_root: Path, *, measured_sha: str) -> dict[str, object]:
    """A passing live scorecard, as the eval writes one at `measured_sha`."""

    identity = measurement_fixture_identity_at_git_sha(
        candidate_sha=measured_sha, repository_root=repository_root
    )
    return {
        "schema_version": 3,
        "provenance": {
            "evaluation_mode": "live",
            "market_data_provider_mode": "live_provider",
            "asset_provider_mode": "live_provider",
            "candidate_sha": measured_sha,
            "python_version": PYTHON_VERSION,
            "fixture_sha256": identity.sha256,
            "fixture_case_ids": list(identity.case_ids),
            "worktree_clean": True,
            "release_configuration": release_configuration_at_commit(
                measured_sha, repository_root=repository_root
            ),
            "live_market_data_probe": {
                "requested_date_range": {"start": "2024-01-01", "end": "2024-01-10"},
                "effective_date_range": {"start": "2024-01-02", "end": "2024-01-10"},
                "adjustment_reason": "calendar_alignment",
            },
        },
        "totals": {
            "passed": len(identity.case_ids),
            "failed": 0,
            "expected_failed": 0,
            "unexpected_pass": 0,
            "skipped": 0,
        },
        "results": [
            {"id": case_id, "category": "messy_english", "status": "passed"}
            for case_id in identity.case_ids
        ],
    }


def write_evidence(
    repository_root: Path, name: str, document: Mapping[str, object]
) -> str:
    """Write durable evidence and return the path a manifest cites."""

    relative = f"docs/reports/evidence/promotion/{name}"
    path = repository_root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    return relative


def _layout(case_ids: Iterable[str]) -> dict[str, str]:
    return {
        "pyproject.toml": (
            "[tool.poetry]\n"
            "packages = [\n"
            '    {include = "argus", from = "src"},\n'
            '    {include = "argus_display_contract", from = "web"},\n'
            "]\n\n"
            "[tool.pytest.ini_options]\n"
            'pythonpath = ["src", "."]\n'
        ),
        "poetry.lock": '[[package]]\nname = "pydantic"\nversion = "2.11.0"\n',
        ".python-version": f"{PYTHON_VERSION}\n",
        ".env.example": "ARGUS_EXAMPLE=\n",
        "AGENTS.md": "# Agents\n",
        "tests/__init__.py": "",
        "tests/conftest.py": "import pytest\n",
        "tests/evals/__init__.py": "",
        MEASUREMENT_ENTRY: (
            "from tests.evals.measurement_eval_harness import run_eval_case\n"
        ),
        "tests/evals/measurement_eval_harness.py": _HARNESS,
        "tests/evals/test_unrelated.py": "def test_unrelated():\n    assert True\n",
        MEASUREMENT_CASES: json.dumps(
            {
                "category": "messy_english",
                "cases": [{"id": case_id} for case_id in case_ids],
            },
            sort_keys=True,
        ),
        "src/argus/__init__.py": "",
        "src/argus/stages.py": (
            "from importlib.resources import files\n\n\n"
            "def interpret(case):\n"
            '    return files("argus_display_contract").joinpath("policy.json").read_text()\n'
        ),
        "src/argus/engine.py": _ENGINE,
        "src/argus/ledger.py": _LEDGER,
        "src/argus/unmeasured.py": "VALUE = 1\n",
        "web/argus_display_contract/__init__.py": "",
        "web/argus_display_contract/policy.json": "{}\n",
        "web/app/page.tsx": "export default function Page() {\n  return null;\n}\n",
        "render.yaml": "services: []\n",
        ".github/private-alpha-release-profile.json": (
            Path(__file__).resolve().parents[1]
            / ".github/private-alpha-release-profile.json"
        ).read_text(encoding="utf-8"),
        "scripts/ops/staging_env_manifest.json": (
            Path(__file__).resolve().parents[1] / "scripts/ops/staging_env_manifest.json"
        ).read_text(encoding="utf-8"),
        "supabase/migrations/20260913000000_example.sql": "select 1;\n",
        "docs/release-manifests/notes.md": "# Notes\n",
        "docs/reports/evidence/2026-09-13-promotion/run_pair.py": "import subprocess\n",
    }


def _commit(repository_root: Path, message: str) -> str:
    _git(repository_root, "add", "--all")
    _git(
        repository_root,
        "-c",
        "user.name=Argus Release Test",
        "-c",
        "user.email=release-test@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "--quiet",
        "--allow-empty",
        "-m",
        message,
    )
    return _git(repository_root, "rev-parse", "HEAD")


def _git(repository_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repository_root,
        capture_output=True,
        check=True,
        text=True,
    )
    return completed.stdout.strip()
