"""Change-based CI job selection: run the real classifier and the real aggregate.

Each case names the jobs a ready pull request runs. The marketing guard below
proves the one narrowing the classifier makes: marketing-checks reads nothing
outside marketing/ and supabase/functions/.
"""

from __future__ import annotations

import os
import posixpath
import re
import subprocess
from pathlib import Path

import pytest
import yaml
from faker import Faker

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "docs-only-changes.sh"
WORKFLOW = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
FAKE = Faker()

ALWAYS = {"docs-change-gate", "ownership-gate", "ci"}
HEAVY = ALWAYS | {"backend-checks", "frontend-checks", "guest-release-gates"}
EVERY = HEAVY | {"marketing-checks"}
DOCS = ALWAYS | {"docs-checks"}


def classify(*paths: str, cwd: Path = ROOT, env: dict[str, str] | None = None):
    return subprocess.run(
        ["bash", str(SCRIPT), *paths],
        cwd=cwd,
        # Never append to the hosted step's real output file.
        env={**os.environ, "GITHUB_OUTPUT": "", **(env or {})},
        capture_output=True,
        text=True,
    )


def outputs(result: subprocess.CompletedProcess[str]) -> dict[str, str]:
    assert result.returncode == 0, result.stdout + result.stderr
    return dict(
        line.split("=", 1)
        for line in result.stdout.splitlines()
        if line.split("=", 1)[0] in {"docs_only", "run_heavy", "run_marketing"}
    )


def selected_jobs(flags: dict[str, str]) -> set[str]:
    """Read each job's gate output from the workflow, as Actions does."""
    picked = set()
    for name, job in WORKFLOW["jobs"].items():
        gate = re.search(r"needs\.docs-change-gate\.outputs\.(\w+) == 'true'", job["if"])
        if gate is None or flags[gate.group(1)] == "true":
            picked.add(name)
    return picked


def jobs_for(*paths: str) -> set[str]:
    return selected_jobs(outputs(classify("--files", *paths)))


CASES = {
    "backend-only": ([f"src/argus/api/{FAKE.word()}.py"], HEAVY),
    "web-only": ([f"web/components/{FAKE.word()}.tsx"], HEAVY),
    "marketing-only": ([f"marketing/app/{FAKE.word()}/page.tsx"], EVERY),
    "migration-only": ([f"supabase/migrations/20261021120000_{FAKE.word()}.sql"], HEAVY),
    "database-test-only": ([f"tests/test_{FAKE.word()}_postgres.py"], HEAVY),
    "schema-docs-and-migration": (
        ["docs/DATA_MODEL.md", f"supabase/migrations/20261021120001_{FAKE.word()}.sql"],
        HEAVY,
    ),
    "python-lockfile": (["poetry.lock", "pyproject.toml"], HEAVY),
    "web-lockfile": (["web/bun.lock", "web/package.json"], HEAVY),
    "marketing-lockfile": (["marketing/bun.lock"], EVERY),
    "edge-function-shared-with-marketing": (
        ["supabase/functions/waitlist-reminders/handler.ts"],
        EVERY,
    ),
    "supabase-config": (["supabase/config.toml"], HEAVY),
    "ci-workflow-defines-marketing-job": ([".github/workflows/ci.yml"], EVERY),
    "other-workflow": ([f".github/workflows/{FAKE.word()}.yml"], HEAVY),
    "selection-script-selects-marketing": ([".github/docs-only-changes.sh"], EVERY),
    "docs-only": ([f"docs/{FAKE.word()}.md", "docs/api/openapi.yaml"], DOCS),
    "native-only": (
        [f"ios/{FAKE.word()}.swift", f"mobile/android/{FAKE.word()}.kt"],
        HEAVY,
    ),
    "unknown-top-level": ([f"{FAKE.word()}-tool/config.yml"], HEAVY),
    "unknown-root-file": (["Makefile", ".gitattributes"], HEAVY),
    "unknown-beside-backend": ([f"src/argus/{FAKE.word()}.py", "temp/.gitkeep"], HEAVY),
    "root-markdown": (["AGENTS.md"], HEAVY),
    "marketing-beside-backend": (
        [f"src/argus/{FAKE.word()}.py", f"marketing/lib/{FAKE.word()}.ts"],
        EVERY,
    ),
    "edge-function-beside-workflow": (
        [".github/workflows/ci.yml", "supabase/functions/waitlist-reminders/index.ts"],
        EVERY,
    ),
    "docs-beside-marketing": (
        [f"docs/{FAKE.word()}.md", "marketing/app/page.tsx"],
        EVERY,
    ),
    "docs-beside-workflow": (
        [f"docs/{FAKE.word()}.md", ".github/workflows/ci.yml"],
        EVERY,
    ),
    "other-github-path": ([".github/CODEOWNERS", ".github/workflows/ci.yml.bak"], HEAVY),
    "marketing-prefix-lookalike": (
        ["marketing-notes.md", "supabase/functions.md"],
        HEAVY,
    ),
}


@pytest.mark.parametrize("paths,expected", CASES.values(), ids=CASES.keys())
def test_changed_paths_select_expected_jobs(paths, expected):
    assert jobs_for(*paths) == expected


def test_migrations_always_reach_the_real_postgres_matrix():
    migration = f"supabase/migrations/20261021120002_{FAKE.word()}.sql"
    assert "guest-release-gates" in jobs_for(migration)
    matrix = WORKFLOW["jobs"]["guest-release-gates"]["strategy"]["matrix"]
    # A pull request runs both CLI legs; only the probe narrows to latest.
    assert '\'["pinned", "latest"]\'' in matrix["supabase-cli"]


@pytest.mark.parametrize("event", ["push", "workflow_dispatch", "schedule"])
def test_events_other_than_pull_request_flag_every_job(event):
    # The workflow's event conditions then narrow the schedule to its probe.
    flags = outputs(classify(env={"GITHUB_EVENT_NAME": event}))
    assert selected_jobs(flags) == EVERY


def test_pull_request_without_base_fails_closed_to_every_job():
    result = classify(env={"GITHUB_EVENT_NAME": "pull_request", "PR_BASE_SHA": ""})
    assert selected_jobs(outputs(result)) == EVERY


def test_manual_full_run_reaches_every_job():
    full_run = "(github.event_name == 'workflow_dispatch' && inputs.full_run)"
    assert WORKFLOW["on"]["workflow_dispatch"]["inputs"]["full_run"] == {
        "description": "Run every job, as an integration push does",
        "type": "boolean",
        "default": False,
    }
    for name, job in WORKFLOW["jobs"].items():
        if name in {"docs-change-gate", "guest-release-gates"}:
            assert "github.event_name == 'workflow_dispatch'" in job["if"], name
        elif name != "docs-checks":
            assert full_run in job["if"], name


# Deleted and renamed files, through real git history.


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "ci@example.test")
    git(tmp_path, "config", "user.name", "CI")
    git(tmp_path, "config", "commit.gpgsign", "false")
    for path in ("marketing/app/page.tsx", "web/lib/a.ts", "docs/notes.md"):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(FAKE.sentence())
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    return tmp_path


def commit_change(repo: Path, *args: str) -> set[str]:
    git(repo, *args)
    git(repo, "commit", "-qm", "change")
    return selected_jobs(outputs(classify("--from-git", "HEAD~1", cwd=repo)))


@pytest.mark.parametrize(
    "change,expected",
    [
        (("rm", "-q", "marketing/app/page.tsx"), EVERY),
        (("mv", "marketing/app/page.tsx", "web/lib/page.tsx"), EVERY),
        (("mv", "web/lib/a.ts", "web/lib/b.ts"), HEAVY),
        (("rm", "-q", "web/lib/a.ts"), HEAVY),
        (("mv", "docs/notes.md", "docs/moved.md"), DOCS),
        (("rm", "-q", "docs/notes.md"), DOCS),
        (("mv", "web/lib/a.ts", "docs/a.md"), HEAVY),
    ],
    ids=[
        "delete-marketing",
        "rename-marketing-to-web",
        "rename-inside-web",
        "delete-web",
        "rename-inside-docs",
        "delete-docs",
        "rename-web-to-docs",
    ],
)
def test_deleted_and_renamed_paths_count_both_sides(repo, change, expected):
    assert commit_change(repo, *change) == expected


@pytest.mark.parametrize(
    "path,expected",
    [
        ("marketing/app/espa\u00f1ol.tsx", EVERY),
        ("marketing/my page/index.tsx", EVERY),
        ("supabase/functions/se\u00f1al/index.ts", EVERY),
        ("web/lib/espa\u00f1ol.ts", HEAVY),
        ("docs/gu\u00eda r\u00e1pida.md", DOCS),
    ],
    ids=[
        "accented-marketing",
        "spaced-marketing",
        "accented-edge-function",
        "accented-web",
        "accented-spaced-docs",
    ],
)
def test_paths_git_would_quote_are_classified_by_their_real_name(repo, path, expected):
    # Real git output: with core.quotePath on (the default), a newline-based
    # listing prints these quoted and escaped, which matches no prefix.
    git(repo, "config", "core.quotePath", "true")
    (repo / path).parent.mkdir(parents=True, exist_ok=True)
    (repo / path).write_text(FAKE.sentence())
    assert commit_change(repo, "add", "-A") == expected


# Failed classification fails the gate instead of guessing.


def test_git_failure_after_partial_listing_fails_the_gate(repo, tmp_path_factory):
    bin_dir = tmp_path_factory.mktemp("bin")
    fake_git = bin_dir / "git"
    fake_git.write_text(
        '#!/bin/bash\n[ "$1" = cat-file ] && exit 0\nprintf "docs/notes.md\\n"\nexit 1\n'
    )
    fake_git.chmod(0o755)
    result = classify(
        "--from-git", "HEAD", cwd=repo, env={"PATH": f"{bin_dir}:{os.environ['PATH']}"}
    )
    assert result.returncode != 0
    assert "docs_only=true" not in result.stdout


def test_unreachable_base_fails_the_gate(repo):
    result = classify("--from-git", FAKE.sha1(), cwd=repo)
    assert result.returncode != 0
    assert "docs_only=" not in result.stdout


# The aggregate: a selected job must succeed; only an unselected job may skip.

AGGREGATE = WORKFLOW["jobs"]["ci"]["steps"][0]
RESULT_KEYS = {
    "docs-checks": "DOCS_CHECKS",
    "backend-checks": "BACKEND_CHECKS",
    "frontend-checks": "FRONTEND_CHECKS",
    "marketing-checks": "MARKETING_CHECKS",
    "guest-release-gates": "GUEST_RELEASE_GATES",
}


def aggregate(tmp_path: Path, flags: dict[str, str], **results: str):
    picked = selected_jobs(flags)
    env = {"DOCS_CHANGE_GATE": "success", "OWNERSHIP_GATE": "success"}
    env.update(DOCS_ONLY=flags["docs_only"], RUN_HEAVY=flags["run_heavy"])
    env["RUN_MARKETING"] = flags["run_marketing"]
    for job, key in RESULT_KEYS.items():
        env[key] = "success" if job in picked else "skipped"
    env.update(results)
    assert set(env) == set(AGGREGATE["env"])
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", AGGREGATE["run"]],
        cwd=tmp_path,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("paths,expected", CASES.values(), ids=CASES.keys())
def test_aggregate_passes_each_selection_and_rejects_each_unexpected_skip(
    tmp_path, paths, expected
):
    flags = outputs(classify("--files", *paths))
    assert aggregate(tmp_path, flags).returncode == 0
    for job, key in RESULT_KEYS.items():
        if job in expected:
            for state in ("skipped", "cancelled", "failure"):
                result = aggregate(tmp_path, flags, **{key: state})
                assert result.returncode != 0, (job, state)
                assert f"{job}: {state}" in result.stdout
        else:
            assert aggregate(tmp_path, flags, **{key: "failure"}).returncode != 0


@pytest.mark.parametrize(
    "flags",
    [
        {"docs_only": "true", "run_heavy": "true", "run_marketing": "false"},
        {"docs_only": "false", "run_heavy": "false", "run_marketing": "false"},
        {"docs_only": "true", "run_heavy": "false", "run_marketing": "true"},
        {"docs_only": "false", "run_heavy": "true", "run_marketing": ""},
        {"docs_only": "false", "run_heavy": "yes", "run_marketing": "true"},
    ],
)
def test_aggregate_rejects_inconsistent_or_invalid_selection(tmp_path, flags):
    defaults = {"docs_only": "false", "run_heavy": "true", "run_marketing": "true"}
    result = aggregate(
        tmp_path,
        defaults,
        DOCS_ONLY=flags["docs_only"],
        RUN_HEAVY=flags["run_heavy"],
        RUN_MARKETING=flags["run_marketing"],
    )
    assert result.returncode != 0


def test_aggregate_reports_a_failed_gate_before_its_missing_outputs(tmp_path):
    result = aggregate(
        tmp_path,
        {"docs_only": "false", "run_heavy": "true", "run_marketing": "true"},
        DOCS_CHANGE_GATE="failure",
        DOCS_ONLY="",
        RUN_HEAVY="",
        RUN_MARKETING="",
    )
    assert result.returncode != 0
    assert "docs-change-gate: failure" in result.stdout


# Marketing independence: the evidence behind every path that skips marketing.

MARKETING_INPUTS = ("marketing", "supabase/functions")
SOURCE_SUFFIXES = {".ts", ".tsx", ".mts", ".cts", ".js", ".mjs", ".cjs", ".json", ".toml"}
# Manual evidence tools that read the whole checkout. No package script, test or
# workflow runs them (test_manual_capture_scripts_stay_unwired).
MANUAL_CAPTURE = re.compile(r"marketing/scripts/capture-[\w-]+\.mjs")
RELATIVE = re.compile(r"""["'`]((?:\.\./)+[^"'`]*)["'`]""")
SEGMENT = re.compile(r"""["'`]\.\.["'`]""")
REPO_WIDE = re.compile(r"""ls-files|git grep|["'`]git["'`],\s*\[\s*["'`]grep""")


def outside_reads(path: str, text: str) -> set[str]:
    """Repository paths a file may read outside the marketing inputs.

    Relative literals resolve from the file (imports, import.meta.url) and from
    the package root (the cwd of bun and Playwright); both are kept. A "." result
    is the repository root: a whole-checkout read.
    """
    package = next(root for root in MARKETING_INPUTS if path.startswith(root + "/"))
    folder = posixpath.dirname(path)
    reads = set()
    for line in text.splitlines():
        if REPO_WIDE.search(line):
            reads.add(".")
        for literal in RELATIVE.findall(line):
            reads.update(
                posixpath.normpath(posixpath.join(base, literal))
                for base in (folder, package)
            )
        steps = len(SEGMENT.findall(line))
        if steps:
            base = package if "process.cwd()" in line else folder
            reads.add(posixpath.normpath(posixpath.join(base, *[".."] * steps)))
    return {
        read
        for read in reads
        if not read.startswith("..")
        and not any(
            read == root or read.startswith(root + "/") for root in MARKETING_INPUTS
        )
    }


def tracked(*paths: str) -> list[str]:
    listing = subprocess.run(
        ["git", "ls-files", "-z", "--", *paths], cwd=ROOT, check=True, capture_output=True
    )
    return listing.stdout.decode().split("\0")[:-1]


def marketing_reads() -> set[str]:
    reads = set()
    for path in tracked(*MARKETING_INPUTS):
        if Path(path).suffix in SOURCE_SUFFIXES and not MANUAL_CAPTURE.fullmatch(path):
            reads |= outside_reads(path, (ROOT / path).read_text(encoding="utf-8"))
    return reads


@pytest.mark.parametrize(
    "line,read",
    [
        ('import x from "../../web/lib/format";', "web/lib/format"),
        ('readFileSync("../src/argus/api/schemas.py")', "src/argus/api/schemas.py"),
        ('const root = join(import.meta.dir, "..", "..");', "."),
        ('join(process.cwd(), "..")', "."),
        ('execFileSync("git", ["grep", "-n", needle])', "."),
    ],
)
def test_marketing_scan_detects_reads_outside_the_package(line, read):
    assert read in outside_reads("marketing/__tests__/example.test.ts", line)


def test_marketing_scan_ignores_reads_inside_the_package():
    lines = [
        'import { a } from "../lib/forms/config";',
        'const root = join(import.meta.dir, "..");',
        'import { b } from "../../supabase/functions/waitlist-reminders/handler";',
    ]
    for line in lines:
        assert outside_reads("marketing/__tests__/example.test.ts", line) <= {
            "lib/forms/config"
        }
    handler = 'import { m } from "../../../marketing/lib/waitlist/email.ts";'
    assert not outside_reads("supabase/functions/waitlist-reminders/handler.ts", handler)


def test_marketing_reads_only_paths_that_select_marketing_checks():
    files = tracked()
    violations = []
    for read in sorted(marketing_reads()):
        if read == ".":
            violations.append("whole-repository read")
            continue
        for path in files:
            if path == read or path.startswith((read + "/", read + ".")):
                if outputs(classify("--files", path))["run_marketing"] != "true":
                    violations.append(f"{read} -> {path}")
    assert not violations, (
        "marketing-checks reads paths that skip it; make selects_marketing in "
        f"{SCRIPT.name} select marketing for them: {violations}"
    )


def test_marketing_tests_really_read_the_edge_function():
    importer = ROOT / "marketing/__tests__/waitlist-scheduler.test.ts"
    assert "../../supabase/functions/waitlist-reminders/handler" in importer.read_text()
    assert jobs_for("supabase/functions/waitlist-reminders/handler.ts") == EVERY


def test_manual_capture_scripts_stay_unwired():
    captures = [path for path in tracked("marketing") if MANUAL_CAPTURE.fullmatch(path)]
    assert captures
    for path in tracked("marketing", ".github"):
        # Markdown documents the manual command; only executable wiring counts.
        if path in captures or Path(path).suffix in {
            ".md",
            ".png",
            ".jpg",
            ".woff2",
            ".ico",
        }:
            continue
        text = (ROOT / path).read_text(encoding="utf-8", errors="ignore")
        assert "scripts/capture-" not in text, path
