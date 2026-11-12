"""Change-based CI job selection: run the real classifier and the real aggregate.

Each case names the jobs a ready pull request runs. The marketing guard below
proves the one narrowing the classifier makes: marketing-checks reads nothing
outside marketing/ and supabase/functions/.
"""

from __future__ import annotations

import os
import posixpath
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from faker import Faker

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "docs-only-changes.sh"
WORKFLOW = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
FAKE = Faker()

ALWAYS = {"docs-change-gate", "ownership-gate", "ci"}
MARKETING = ALWAYS | {"marketing-checks"}
HEAVY = ALWAYS | {"backend-checks", "backend-shards", "frontend-checks", "database-checks", "database-shards"}
EVERY = HEAVY | {"marketing-checks"}
# Backend email agreement tests recursively read the web tree.
WEB = HEAVY
PACKAGES = EVERY
DOCS = ALWAYS | {"docs-checks"}
FLAGS = {"docs_only", "run_heavy", "run_marketing", "run_backend", "run_frontend", "run_database"}


def classify(
    *paths: str,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    script: Path = SCRIPT,
):
    return subprocess.run(
        ["bash", str(script), *paths],
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
        if line.split("=", 1)[0] in FLAGS
    )


def selected_jobs(flags: dict[str, str]) -> set[str]:
    """Jobs whose work steps run. A skip-pass step does not count as work."""
    picked = set()
    for name, job in WORKFLOW["jobs"].items():
        pieces = [job.get("if") or ""]
        pieces.extend(step.get("if") or "" for step in job.get("steps") or [])
        gates = re.findall(
            r"needs\.docs-change-gate\.outputs\.(\w+) == 'true'", "\n".join(pieces)
        )
        if not gates or any(flags[gate] == "true" for gate in gates):
            picked.add(name)
    return picked


def jobs_for(*paths: str) -> set[str]:
    return selected_jobs(outputs(classify("--files", *paths)))


def test_account_layout_change_selects_web_and_backend_checks():
    assert {"frontend-checks", "backend-checks"} <= jobs_for(
        "marketing/lib/email/account-layout.ts"
    )


CASES = {
    "backend-only": ([f"src/argus/api/{FAKE.word()}.py"], HEAVY),
    "web-only": ([f"web/components/{FAKE.word()}.tsx"], WEB),
    "backend-package-under-web": (["web/argus_display_contract/x.json"], EVERY),
    "backend-package-prefix-lookalike": (
        ["web/argus_display_contract_backup/x.json"], WEB,
    ),
    "marketing-only": ([f"marketing/app/{FAKE.word()}/page.tsx"], MARKETING),
    "migration-only": ([f"supabase/migrations/20261021120000_{FAKE.word()}.sql"], HEAVY),
    "database-test-only": ([f"tests/test_{FAKE.word()}_postgres.py"], HEAVY),
    "schema-docs-and-migration": (
        ["docs/DATA_MODEL.md", f"supabase/migrations/20261021120001_{FAKE.word()}.sql"],
        HEAVY,
    ),
    "python-lockfile": (["poetry.lock", "pyproject.toml"], EVERY),
    "web-lockfile": (["web/bun.lock", "web/package.json"], EVERY),
    "marketing-lockfile": (["marketing/bun.lock"], EVERY),
    "edge-function-shared-with-marketing": (
        ["supabase/functions/waitlist-reminders/handler.ts"],
        EVERY,
    ),
    "supabase-config": (["supabase/config.toml"], HEAVY),
    "ci-workflow-defines-marketing-job": ([".github/workflows/ci.yml"], EVERY),
    "other-workflow": ([f".github/workflows/{FAKE.word()}.yml"], EVERY),
    "selection-script-selects-marketing": ([".github/docs-only-changes.sh"], EVERY),
    "docs-only": ([f"docs/{FAKE.word()}.md"], DOCS),
    "openapi-contract": (["docs/api/openapi.yaml", "docs/API_CONTRACT.md"], EVERY),
    "native-only": (
        [f"ios/{FAKE.word()}.swift", f"mobile/android/{FAKE.word()}.kt"],
        HEAVY,
    ),
    "unknown-top-level": ([f"{FAKE.word()}-tool/config.yml"], HEAVY),
    "unknown-root-file": (["Makefile", ".gitattributes"], HEAVY),
    "unknown-beside-backend": ([f"src/argus/{FAKE.word()}.py", "temp/.gitkeep"], HEAVY),
    "root-markdown": (["AGENTS.md"], HEAVY),
    "readme-only": (["README.md"], DOCS),
    "readme-beside-code": (["README.md", f"src/argus/{FAKE.word()}.py"], HEAVY),
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
    "other-github-path": ([".github/CODEOWNERS", ".github/workflows/ci.yml.bak"], EVERY),
    "web-and-marketing": (
        [f"web/lib/{FAKE.word()}.ts", f"marketing/lib/{FAKE.word()}.ts"],
        PACKAGES,
    ),
    "marketing-prefix-lookalike": (
        ["marketing-notes.md", "supabase/functions.md"],
        HEAVY,
    ),
}


@pytest.mark.parametrize("paths,expected", CASES.values(), ids=CASES.keys())
def test_changed_paths_select_expected_jobs(paths, expected):
    assert jobs_for(*paths) == expected


def test_backend_packaged_frontend_files_select_every_job():
    with (ROOT / "pyproject.toml").open("rb") as source:
        packages = tomllib.load(source)["tool"]["poetry"]["packages"]
    for package in packages:
        for path in (ROOT / package.get("from", ".")).glob(package["include"]):
            relative = path.relative_to(ROOT)
            if relative.parts[0] not in {"web", "marketing"}:
                continue
            for file in path.rglob("*") if path.is_dir() else [path]:
                if file.is_file():
                    assert jobs_for(file.relative_to(ROOT).as_posix()) == EVERY


@pytest.fixture
def classifier_checkout(tmp_path):
    script = tmp_path / ".github" / SCRIPT.name
    script.parent.mkdir()
    script.write_text(SCRIPT.read_text())
    (tmp_path / "pyproject.toml").write_text((ROOT / "pyproject.toml").read_text())
    shutil.copytree(ROOT / "scripts/emails", tmp_path / "scripts/emails")
    shutil.copytree(ROOT / "marketing/lib/email", tmp_path / "marketing/lib/email")
    shutil.copytree(ROOT / "web/__tests__", tmp_path / "web/__tests__")
    (tmp_path / "tests").mkdir()
    for agreement in (ROOT / "tests").glob("test_*email*.py"):
        shutil.copy(agreement, tmp_path / "tests" / agreement.name)
    return tmp_path, script


@pytest.mark.parametrize(
    "package,path",
    [
        ('{include = "new_contract", from = "web"}', "web/new_contract/x.json"),
        (
            '{include = "new_contract", from = "marketing"}',
            "marketing/new_contract/nested/x.json",
        ),
        ('{include = "web/new_contract"}', "./web/new_contract/x.json"),
        (
            '{include = "new_*", from = "./marketing/shared/"}',
            "marketing/shared/new_contract/x.json",
        ),
        ('{include = "*/new_contract"}', "web/new_contract/x.json"),
        ('{include = "new_contract.py", from = "web"}', "web/new_contract.py"),
        pytest.param(
            '{include = "**/new_contract", from = "web"}',
            "web/new_contract/x.json",
            id="recursive-zero-directories",
        ),
        pytest.param(
            '{include = "**/new_contract", from = "web"}',
            "web/shared/nested/new_contract/x.json",
            id="recursive-nested-directories",
        ),
        pytest.param(
            '{include = "**/shared/**/new_contract", from = "marketing"}',
            "marketing/shared/new_contract/x.json",
            id="recursive-multiple-zero-directories",
        ),
        pytest.param(
            '{include = "**/shared/**/new_contract", from = "marketing"}',
            "marketing/assets/shared/nested/new_contract/x.json",
            id="recursive-multiple-nested-directories",
        ),
    ],
)
def test_new_backend_packages_are_derived_from_metadata(classifier_checkout, package, path):
    root, script = classifier_checkout
    (root / "pyproject.toml").write_text(f"[tool.poetry]\npackages = [{package}]\n")
    result = classify("--files", path, script=script)
    assert selected_jobs(outputs(result)) == EVERY


@pytest.mark.parametrize("metadata", [None, "[tool.poetry\n", "[tool.poetry]\n"])
def test_unreadable_backend_packages_fail_the_gate(classifier_checkout, metadata):
    root, script = classifier_checkout
    project = root / "pyproject.toml"
    if metadata is None:
        project.unlink()
    else:
        project.write_text(metadata)
    result = classify("--files", "web/argus_display_contract/x.json", script=script)
    assert result.returncode != 0
    assert not any(line.startswith("run_") for line in result.stdout.splitlines())


def test_migrations_always_reach_the_real_postgres_matrix():
    migration = f"supabase/migrations/20261021120002_{FAKE.word()}.sql"
    assert "database-checks" in jobs_for(migration)
    matrix = WORKFLOW["jobs"]["database-checks"]["strategy"]["matrix"]
    # A pull request runs the pinned leg only; a push runs both; the probe runs latest.
    assert "'[\"pinned\"]'" in matrix["supabase-cli"]
    assert '\'["pinned", "latest"]\'' in matrix["supabase-cli"]
    assert '\'["latest"]\'' in matrix["supabase-cli"]


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
        if name in {"docs-change-gate", "database-checks", "database-shards"}:
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
    for path in (
        "marketing/app/page.tsx",
        "web/lib/a.ts",
        "web/argus_display_contract/x.json",
        "docs/notes.md",
    ):
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
        (("rm", "-q", "marketing/app/page.tsx"), MARKETING),
        (("mv", "marketing/app/page.tsx", "web/lib/page.tsx"), PACKAGES),
        (("mv", "web/lib/a.ts", "web/lib/b.ts"), WEB),
        (("rm", "-q", "web/lib/a.ts"), WEB),
        (("mv", "docs/notes.md", "docs/moved.md"), DOCS),
        (("rm", "-q", "docs/notes.md"), DOCS),
        (("mv", "web/lib/a.ts", "docs/a.md"), HEAVY),
        (("rm", "-q", "web/argus_display_contract/x.json"), EVERY),
        (("mv", "web/argus_display_contract/x.json", "web/lib/x.json"), EVERY),
    ],
    ids=[
        "delete-marketing",
        "rename-marketing-to-web",
        "rename-inside-web",
        "delete-web",
        "rename-inside-docs",
        "delete-docs",
        "rename-web-to-docs",
        "delete-backend-package-under-web",
        "rename-out-of-backend-package-under-web",
    ],
)
def test_deleted_and_renamed_paths_count_both_sides(repo, change, expected):
    assert commit_change(repo, *change) == expected


@pytest.mark.parametrize(
    "path,expected",
    [
        ("marketing/app/espa\u00f1ol.tsx", MARKETING),
        ("marketing/my page/index.tsx", MARKETING),
        ("supabase/functions/se\u00f1al/index.ts", EVERY),
        ("web/lib/espa\u00f1ol.ts", WEB),
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
    "database-checks": "DATABASE_CHECKS",
}


def aggregate(tmp_path: Path, flags: dict[str, str], **results: str):
    picked = selected_jobs(flags)
    env = {"DOCS_CHANGE_GATE": "success", "OWNERSHIP_GATE": "success"}
    env.update(DOCS_ONLY=flags["docs_only"], RUN_HEAVY=flags["run_heavy"])
    env["RUN_MARKETING"] = flags["run_marketing"]
    env["RUN_BACKEND"] = flags["run_backend"]
    env["RUN_FRONTEND"] = flags["run_frontend"]
    env["RUN_DATABASE"] = flags["run_database"]
    reporting = {"backend-checks", "frontend-checks", "marketing-checks", "database-checks"}
    for job, key in RESULT_KEYS.items():
        env[key] = "success" if job in picked or job in reporting else "skipped"
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
    reporting = {"backend-checks", "frontend-checks", "marketing-checks", "database-checks"}
    for job, key in RESULT_KEYS.items():
        if job in expected or job in reporting:
            for state in ("skipped", "cancelled", "failure"):
                result = aggregate(tmp_path, flags, **{key: state})
                assert result.returncode != 0, (job, state)
                assert f"{job}: {state}" in result.stdout
        else:
            assert aggregate(tmp_path, flags, **{key: "failure"}).returncode != 0


@pytest.mark.parametrize(
    "flags",
    [
        {
            "docs_only": "true",
            "run_heavy": "true",
            "run_marketing": "false",
            "run_backend": "true",
            "run_frontend": "true",
            "run_database": "true",
        },
        {
            "docs_only": "false",
            "run_heavy": "false",
            "run_marketing": "false",
            "run_backend": "false",
            "run_frontend": "false",
            "run_database": "false",
        },
        {
            "docs_only": "true",
            "run_heavy": "false",
            "run_marketing": "true",
            "run_backend": "false",
            "run_frontend": "false",
            "run_database": "false",
        },
        {
            "docs_only": "false",
            "run_heavy": "true",
            "run_marketing": "",
            "run_backend": "true",
            "run_frontend": "true",
            "run_database": "true",
        },
        {
            "docs_only": "false",
            "run_heavy": "yes",
            "run_marketing": "true",
            "run_backend": "true",
            "run_frontend": "true",
            "run_database": "true",
        },
        {
            "docs_only": "false",
            "run_heavy": "true",
            "run_marketing": "false",
            "run_backend": "true",
            "run_frontend": "false",
            "run_database": "false",
        },
    ],
)
def test_aggregate_rejects_inconsistent_or_invalid_selection(tmp_path, flags):
    defaults = {
        "docs_only": "false",
        "run_heavy": "true",
        "run_marketing": "true",
        "run_backend": "true",
        "run_frontend": "true",
        "run_database": "true",
    }
    result = aggregate(tmp_path, defaults, **{key.upper(): value for key, value in {
        "docs_only": flags["docs_only"],
        "run_heavy": flags["run_heavy"],
        "run_marketing": flags["run_marketing"],
        "run_backend": flags["run_backend"],
        "run_frontend": flags["run_frontend"],
        "run_database": flags["run_database"],
    }.items()})
    assert result.returncode != 0


def test_aggregate_reports_a_failed_gate_before_its_missing_outputs(tmp_path):
    result = aggregate(
        tmp_path,
        {
            "docs_only": "false",
            "run_heavy": "true",
            "run_marketing": "true",
            "run_backend": "true",
            "run_frontend": "true",
            "run_database": "true",
        },
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


@pytest.mark.parametrize("path", [
    "marketing/lib/email/account-layout.ts",
    "marketing/lib/email/existing-account.ts",
    "marketing/lib/email/business-invite.ts",
    "marketing/lib/email/business-transfer.ts",
    "marketing/lib/email/business-closed.ts",
    "marketing/lib/email/template-slots.ts",
    "marketing/lib/email/email-otp-contract.generated.ts",
    "marketing/lib/email/support-email.generated.ts",
    "marketing/lib/email/account-copy.generated.json",
    "web/server/emails/account-layout.generated.ts",
    "web/lib/email-otp-contract.ts",
    "web/public/locales/es-419/common.json",
    "web/public/locales/en/common.json",
    "src/argus/domain/existing_account_email.generated.json",
    "src/argus/domain/business/business_invite_email.generated.json",
    "src/argus/domain/business/business_transfer_email.generated.json",
    "src/argus/domain/business/business_closed_email.generated.json",
    *[path.relative_to(ROOT).as_posix() for path in (ROOT / "scripts/emails").glob("sync-*")],
])
def test_shared_email_generation_inputs_and_outputs_select_every_job(path):
    assert jobs_for(path) == EVERY


@pytest.mark.parametrize("extension", ["mjs", "ts"])
def test_new_email_sync_scripts_define_shared_paths(classifier_checkout, extension):
    root, script = classifier_checkout
    owner = root / "marketing/lib/email/new-owner.ts"
    owner.write_text('export { value } from "./new-dependency";')
    (owner.parent / "new-dependency.ts").write_text("export const value = 1;")
    (root / f"scripts/emails/sync-new.{extension}").write_text(
        'import { value } from "../../marketing/lib/email/new-owner";\n'
        'const destination = new URL("../../web/lib/new.generated.ts", import.meta.url);\n'
    )
    for path in [
        "marketing/lib/email/new-owner.ts", "marketing/lib/email/new-dependency.ts",
        "web/lib/new.generated.ts", f"scripts/emails/sync-new.{extension}",
    ]:
        assert selected_jobs(outputs(classify("--files", path, script=script))) == EVERY
    assert selected_jobs(outputs(classify(
        "--files", "marketing/lib/email/new-owner.ts.bak", script=script,
    ))) == MARKETING


@pytest.mark.parametrize("contents", [
    None, 'const destination = computePath();',
    'const source = new URL("../../marketing/lib/email/new.ts", import.meta.url);\n'
    'const destination = resolve(root, "web/lib/new.generated.ts");\n'
    'writeFileSync(destination, readFileSync(source, "utf8"));',
    'import x from "../../marketing/lib/email/account-layout";\n'
    'const destination = new URL(computePath(), import.meta.url);',
])
def test_unreadable_email_relationships_fail_the_gate(classifier_checkout, contents):
    root, script = classifier_checkout
    folder = root / "scripts/emails"
    if contents is None:
        shutil.rmtree(folder)
    else:
        (folder / "sync-unknown.ts").write_text(contents)
    result = classify("--files", "marketing/app/page.tsx", script=script)
    assert result.returncode != 0
    assert not any(line.startswith("run_") for line in result.stdout.splitlines())


def test_new_url_copy_includes_transitive_source_inputs(classifier_checkout):
    root, script = classifier_checkout
    owner = root / "marketing/lib/email/new-layout.ts"
    owner.write_text('import x from "./new-copy.json";')
    (root / "scripts/emails/sync-new-layout.mjs").write_text(
        'const source = new URL("../../marketing/lib/email/new-layout.ts", import.meta.url);\n'
        'const destination = new URL("../../web/server/new-layout.generated.ts", import.meta.url);\n'
    )
    assert selected_jobs(outputs(classify(
        "--files", "marketing/lib/email/new-copy.json", script=script,
    ))) == EVERY


def test_backend_email_agreement_inputs_select_backend():
    assert "backend-checks" in jobs_for("web/.env.local.example")


def test_new_backend_email_agreement_declares_shared_input(classifier_checkout):
    root, script = classifier_checkout
    (root / "tests/test_new_email_agreement.py").write_text(
        'from pathlib import Path\n'
        'ROOT = Path(__file__).resolve().parents[1]\n'
        'OWNER = ROOT / "marketing/lib/email/account-layout.ts"\n'
        'OTHER = ROOT / "web/lib/new-email-contract.json"\n'
    )
    assert selected_jobs(outputs(classify(
        "--files", "web/lib/new-email-contract.json", script=script,
    ))) == EVERY


@pytest.mark.parametrize("path", ["web/components/ordinary.tsx", "web/public/ordinary.svg"])
def test_recursive_email_agreement_selects_backend_for_web_tree(path):
    assert jobs_for(path) == HEAVY


def test_new_recursive_email_agreement_derives_scan_root(classifier_checkout):
    root, script = classifier_checkout
    (root / "tests/test_new_email_agreement.py").write_text(
        'from pathlib import Path\n'
        'ROOT = Path(__file__).resolve().parents[1]\n'
        'for path in (ROOT / "marketing/assets").rglob("*"):\n'
        '    text = path.read_text()\n'
    )
    assert selected_jobs(outputs(classify(
        "--files", "marketing/assets/new.svg", script=script,
    ))) == EVERY
