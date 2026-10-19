from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "ci" / "check_pr_guards.py"
WORKFLOW = ROOT / ".github" / "workflows" / "pr-guards.yml"
AGENTS_RULE = (
    "Hotspot files need the lead's `landing-next` label, and a pull request "
    "over about 800 non-test lines needs `size-approved`."
)
HOTSPOT_SENTENCE = "The lead applies landing-next when the pull request is next to land."


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def init_repo(tmp_path: Path) -> tuple[Path, str]:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "dev@example.com")
    git(tmp_path, "config", "user.name", "Dev")
    git(tmp_path, "config", "commit.gpgsign", "false")
    (tmp_path / "README.md").write_text("base\n", encoding="utf-8")
    git(tmp_path, "add", "README.md")
    git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path, git(tmp_path, "rev-parse", "HEAD")


def commit_text(repo: Path, path: str, text: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    git(repo, "add", "--", path)
    git(repo, "commit", "-q", "-m", path)


def commit_lines(repo: Path, path: str, count: int) -> None:
    commit_text(repo, path, "".join(f"line {index}\n" for index in range(count)))


def run_check(
    repo: Path,
    base: str,
    command: str,
    labels: list[str],
    head: str | None = None,
) -> subprocess.CompletedProcess[str]:
    event = repo / f"{command}-event.json"
    payload = {"pull_request": {"labels": [{"name": label} for label in labels]}}
    event.write_text(json.dumps(payload), encoding="utf-8")
    env = os.environ.copy()
    env["GITHUB_EVENT_PATH"] = str(event)
    env["PR_BASE_SHA"] = base
    env.pop("PR_HEAD_SHA", None)
    if head is not None:
        env["PR_HEAD_SHA"] = head
    return subprocess.run(
        [sys.executable, str(CHECKER), command, "--root", str(repo)],
        capture_output=True,
        text=True,
        env=env,
    )


def test_hotspot_edit_without_label_fails(tmp_path: Path) -> None:
    repo, base = init_repo(tmp_path)
    commit_text(repo, ".env.example", "PLACEHOLDER=\n")

    result = run_check(repo, base, "hotspot", [])

    assert result.returncode == 1
    assert result.stderr.splitlines() == [".env.example", HOTSPOT_SENTENCE]


def test_hotspot_edit_with_label_passes(tmp_path: Path) -> None:
    repo, base = init_repo(tmp_path)
    commit_text(repo, ".env.example", "PLACEHOLDER=\n")

    result = run_check(repo, base, "hotspot", ["landing-next"])

    assert result.returncode == 0
    assert result.stderr == ""


def test_non_hotspot_edit_passes(tmp_path: Path) -> None:
    repo, base = init_repo(tmp_path)
    commit_text(repo, "src/app.py", "value = 1\n")

    result = run_check(repo, base, "hotspot", [])

    assert result.returncode == 0
    assert result.stderr == ""


def test_locale_glob_matches_common_json_only(tmp_path: Path) -> None:
    repo, base = init_repo(tmp_path)
    commit_text(repo, "web/public/locales/es/common.json", "{}\n")
    matched = run_check(repo, base, "hotspot", [])

    other_root = tmp_path / "other"
    other_root.mkdir()
    other_repo, other_base = init_repo(other_root)
    commit_text(other_repo, "web/public/locales/es/other.json", "{}\n")
    other = run_check(other_repo, other_base, "hotspot", [])

    assert matched.returncode == 1
    assert matched.stderr.splitlines() == [
        "web/public/locales/es/common.json",
        HOTSPOT_SENTENCE,
    ]
    assert other.returncode == 0
    assert other.stderr == ""


def test_deleted_hotspot_fails(tmp_path: Path) -> None:
    repo, _base = init_repo(tmp_path)
    commit_text(repo, ".env.example", "PLACEHOLDER=\n")
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "rm", "-q", "--", ".env.example")
    git(repo, "commit", "-q", "-m", "delete")

    result = run_check(repo, base, "hotspot", [])

    assert result.returncode == 1
    assert result.stderr.splitlines() == [".env.example", HOTSPOT_SENTENCE]


def test_rename_into_hotspot_fails(tmp_path: Path) -> None:
    repo, _base = init_repo(tmp_path)
    commit_text(repo, "notes/example.env", "PLACEHOLDER=\n")
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "mv", "--", "notes/example.env", ".env.example")
    git(repo, "commit", "-q", "-m", "rename")

    result = run_check(repo, base, "hotspot", [])

    assert result.returncode == 1
    assert result.stderr.splitlines() == [".env.example", HOTSPOT_SENTENCE]


def test_rename_away_from_hotspot_fails(tmp_path: Path) -> None:
    repo, _base = init_repo(tmp_path)
    commit_text(repo, ".env.example", "PLACEHOLDER=\n")
    base = git(repo, "rev-parse", "HEAD")
    (repo / "notes").mkdir()
    git(repo, "mv", "--", ".env.example", "notes/example.env")
    git(repo, "commit", "-q", "-m", "rename")

    result = run_check(repo, base, "hotspot", [])

    assert result.returncode == 1
    assert result.stderr.splitlines() == [".env.example", HOTSPOT_SENTENCE]


def test_401_lines_warns_and_passes(tmp_path: Path) -> None:
    repo, base = init_repo(tmp_path)
    commit_lines(repo, "src/app.py", 401)

    result = run_check(repo, base, "size", [])

    assert result.returncode == 0
    assert "counted 401\n" in result.stdout
    assert "src/app.py 401" in result.stdout
    assert "::warning::401 non-test lines is above 400." in result.stdout
    assert result.stderr == ""


def test_400_lines_pass_without_a_warning(tmp_path: Path) -> None:
    repo, base = init_repo(tmp_path)
    commit_lines(repo, "src/app.py", 400)

    result = run_check(repo, base, "size", [])

    assert result.returncode == 0
    assert "counted 400\n" in result.stdout
    assert "::warning::" not in result.stdout
    assert result.stderr == ""


def test_801_lines_fail(tmp_path: Path) -> None:
    repo, base = init_repo(tmp_path)
    commit_lines(repo, "src/app.py", 801)

    result = run_check(repo, base, "size", [])

    assert result.returncode == 1
    assert "counted 801\n" in result.stdout
    assert "src/app.py 801" in result.stdout
    assert "::warning::801 non-test lines is above 400." in result.stdout
    assert result.stderr.splitlines() == [
        "801 non-test lines is above 800. "
        "The lead applies size-approved when an oversized pull request is approved."
    ]


def test_800_lines_warn_and_pass(tmp_path: Path) -> None:
    repo, base = init_repo(tmp_path)
    commit_lines(repo, "src/app.py", 800)

    result = run_check(repo, base, "size", [])

    assert result.returncode == 0
    assert "counted 800\n" in result.stdout
    assert "::warning::800 non-test lines is above 400." in result.stdout
    assert result.stderr == ""


def test_801_lines_with_size_approved_pass(tmp_path: Path) -> None:
    repo, base = init_repo(tmp_path)
    commit_lines(repo, "src/app.py", 801)

    result = run_check(repo, base, "size", ["size-approved"])

    assert result.returncode == 0
    assert "counted 801\n" in result.stdout
    assert "::warning::801 non-test lines is above 400." in result.stdout
    assert result.stderr == ""


def test_excluded_lines_do_not_count(tmp_path: Path) -> None:
    repo, _base = init_repo(tmp_path)
    commit_text(repo, ".gitattributes", "vendor/** linguist-generated\n")
    base = git(repo, "rev-parse", "HEAD")
    excluded = (
        "tests/big_case.py",
        "web/__tests__/widget.ts",
        "web/widget.test.ts",
        "web/widget.spec.ts",
        "e2e/flow.py",
        "poetry.lock",
        "bun.lock",
        "src/out.generated.py",
        "vendor/blob.py",
        "fixtures/sample.json",
    )
    for path in excluded:
        commit_lines(repo, path, 500)
    target = repo / "pic.bin"
    target.write_bytes(b"\x00\x01\x02" * 50)
    git(repo, "add", "--", "pic.bin")
    git(repo, "commit", "-q", "-m", "pic.bin")
    commit_lines(repo, "src/real.py", 10)

    result = run_check(repo, base, "size", [])

    assert result.returncode == 0
    assert "counted 10\n" in result.stdout
    assert "src/real.py 10" in result.stdout
    assert "::warning::" not in result.stdout
    for path in (*excluded, "pic.bin"):
        assert path not in result.stdout


def test_missing_merge_base_fails(tmp_path: Path) -> None:
    repo, _base = init_repo(tmp_path)

    result = run_check(repo, "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef", "hotspot", [])

    assert result.returncode == 1
    assert "merge base" in result.stderr.lower()


def test_merge_checkout_with_stale_base_judges_the_pull_request_head(
    tmp_path: Path,
) -> None:
    repo, stale_base = init_repo(tmp_path)
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    git(repo, "checkout", "-q", "-b", "feature")
    commit_lines(repo, "src/app.py", 10)
    feature = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", branch)
    commit_text(repo, "web/public/locales/en/common.json", "{}\n")
    commit_lines(repo, "src/base_only.py", 900)
    git(repo, "merge", "-q", "--no-ff", feature, "-m", "merge feature")

    blamed = run_check(repo, stale_base, "hotspot", [])
    judged = run_check(repo, stale_base, "hotspot", [], head=feature)
    size = run_check(repo, stale_base, "size", [], head=feature)

    assert blamed.returncode == 1
    assert blamed.stderr.splitlines() == [
        "web/public/locales/en/common.json",
        HOTSPOT_SENTENCE,
    ]
    assert judged.returncode == 0
    assert judged.stderr == ""
    assert size.returncode == 0
    assert "counted 10\n" in size.stdout
    assert "src/app.py 10" in size.stdout
    assert "src/base_only.py" not in size.stdout
    assert "common.json" not in size.stdout


def test_missing_pull_request_head_fails(tmp_path: Path) -> None:
    repo, base = init_repo(tmp_path)

    result = run_check(
        repo,
        base,
        "hotspot",
        [],
        head="c0ffeec0ffeec0ffeec0ffeec0ffeec0ffeec0ff",
    )

    assert result.returncode == 1
    assert "merge base" in result.stderr.lower()


def test_agents_states_the_label_rule() -> None:
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert AGENTS_RULE in text


def test_workflow_runs_both_guards_without_a_path_filter() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    pull_request = workflow["on"]["pull_request"]
    jobs = workflow["jobs"]

    assert pull_request["types"] == [
        "opened",
        "synchronize",
        "reopened",
        "labeled",
        "unlabeled",
    ]
    assert "paths" not in pull_request
    assert set(jobs) == {"hotspot-guard", "size-guard"}
    for name, command in (("hotspot-guard", "hotspot"), ("size-guard", "size")):
        steps = jobs[name]["steps"]
        checkout = next(
            step
            for step in steps
            if str(step.get("uses", "")).startswith("actions/checkout@")
        )
        assert checkout["with"]["fetch-depth"] == 0
        check = next(
            step
            for step in steps
            if step.get("run") == f"python scripts/ci/check_pr_guards.py {command}"
        )
        assert check["env"]["PR_BASE_SHA"] == "${{ github.event.pull_request.base.sha }}"
        assert check["env"]["PR_HEAD_SHA"] == "${{ github.event.pull_request.head.sha }}"
