"""Staging deploy decisions and the workflow that calls them.

The script is the caller the workflow uses. These tests drive that command
and the workflow file, not private helpers.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml
from faker import Faker

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ci" / "deploy_staging.py"
WORKFLOW = ROOT / ".github" / "workflows" / "deploy-staging.yml"
SKIP = "Nothing deployable changed since the comparison commit. Skipping deploy."
PROD_NAMES = (
    "cuadrao-api",
    "cuadrao-app",
    "cuadrao-marketing",
    "cuadrao-web",
)
FAKE = Faker()


def run(
    *args: str,
    stdin: str = "",
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.pop("FORCE_ALL", None)
    merged.pop("INPUT_SHA", None)
    merged.pop("LIVE_COMMIT", None)
    merged.pop("PARENT_SHA", None)
    merged.pop("API_BASE", None)
    merged.pop("WEB_BASE", None)
    if env:
        merged.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin,
        capture_output=True,
        text=True,
        env=merged,
        cwd=ROOT,
        check=False,
    )


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def init_repo(repo: Path) -> str:
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "dev@example.com")
    git(repo, "config", "user.name", "Dev")
    git(repo, "config", "commit.gpgsign", "false")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    git(repo, "add", "README.md")
    git(repo, "commit", "-q", "-m", "base")
    return git(repo, "rev-parse", "HEAD")


def selected(result: subprocess.CompletedProcess[str]) -> list[str]:
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    if lines == [SKIP]:
        return []
    return lines


def test_invalid_sha_is_rejected() -> None:
    samples = (
        "abc",
        "g" * 40,
        "a" * 39,
        "a" * 41,
    )
    for sha in samples:
        result = run("validate-sha", "--sha", sha)
        assert result.returncode == 1, sha
        assert result.stderr.strip() == "SHA must be 40 hex characters."
    dashed = run("validate-sha", env={"INPUT_SHA": "-" + "a" * 39})
    assert dashed.returncode == 1
    assert dashed.stderr.strip() == "SHA must be 40 hex characters."


def test_empty_input_uses_the_checked_out_commit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    head = init_repo(repo)

    result = run(
        "validate-sha",
        "--repo",
        str(repo),
        env={"INPUT_SHA": ""},
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == head


def test_sha_must_be_an_ancestor_of_the_integration_tip(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    git(repo, "checkout", "-q", "-b", "integration")
    (repo / "README.md").write_text("integration\n", encoding="utf-8")
    git(repo, "commit", "-q", "-am", "integration")
    tip = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "--orphan", "side")
    (repo / "README.md").write_text("side\n", encoding="utf-8")
    git(repo, "add", "README.md")
    git(repo, "commit", "-q", "-m", "side")
    side = git(repo, "rev-parse", "HEAD")

    rejected = run(
        "assert-ancestor",
        "--repo",
        str(repo),
        "--sha",
        side,
        "--tip",
        tip,
    )
    accepted = run(
        "assert-ancestor",
        "--repo",
        str(repo),
        "--sha",
        tip,
        "--tip",
        tip,
    )

    assert rejected.returncode == 1
    assert side in rejected.stderr
    assert accepted.returncode == 0
    assert accepted.stderr == ""


def test_prod_service_names_are_rejected() -> None:
    for name in PROD_NAMES:
        result = run("allow-name", "--name", name)
        assert result.returncode == 1, name
        assert name in result.stderr
        assert "cuadrao-api-staging" in result.stderr
        assert "cuadrao-app-staging" in result.stderr


def test_marketing_staging_name_is_rejected() -> None:
    result = run("allow-name", "--name", "cuadrao-marketing-staging")
    assert result.returncode == 1
    assert "cuadrao-marketing-staging" in result.stderr
    assert "cuadrao-api-staging" in result.stderr
    assert "cuadrao-app-staging" in result.stderr


def test_staging_service_names_are_allowed() -> None:
    for name in ("cuadrao-api-staging", "cuadrao-app-staging"):
        result = run("allow-name", "--name", name)
        assert result.returncode == 0, result.stderr
        assert result.stdout == ""


def test_web_only_change_selects_web() -> None:
    path = f"web/{FAKE.word()}/{FAKE.word()}.tsx"
    result = run("select-services", stdin=path + "\n")
    assert selected(result) == ["cuadrao-app-staging"]


def test_backend_only_change_selects_api() -> None:
    path = f"src/argus/{FAKE.word()}.py"
    result = run("select-services", stdin=path + "\n")
    assert selected(result) == ["cuadrao-api-staging"]


def test_docs_only_change_selects_nothing() -> None:
    path = f"docs/{FAKE.word()}.md"
    result = run("select-services", stdin=path + "\n")
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [SKIP]


def test_force_all_selects_both_staging_services() -> None:
    result = run(
        "select-services",
        stdin="docs/PRODUCT.md\n",
        env={"FORCE_ALL": "true"},
    )
    assert selected(result) == ["cuadrao-api-staging", "cuadrao-app-staging"]


def test_path_rules_follow_render_build_and_poetry_packages() -> None:
    blueprint = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    services = {item["name"]: item for item in blueprint["services"]}
    api = services["cuadrao-api-staging"]
    web_blocks = [item for item in blueprint["services"] if item.get("rootDir") == "web"]
    assert len(web_blocks) == 1
    web = web_blocks[0]
    assert api["rootDir"] == "."
    assert api["autoDeployTrigger"] == "off"
    assert "poetry install" in api["buildCommand"]
    assert "dockerfilePath" not in api
    assert web["rootDir"] == "web"
    assert web["autoDeployTrigger"] == "off"
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '{include = "argus", from = "src"}' in pyproject
    assert '{include = "argus_display_contract", from = "web"}' in pyproject

    shared = run(
        "select-services",
        stdin="web/argus_display_contract/support_contact.json\n",
    )
    schema = run(
        "select-services",
        stdin="supabase/migrations/20261030120000_example.sql\n",
    )
    config = run("select-services", stdin="supabase/config.toml\n")
    edge = run(
        "select-services",
        stdin="supabase/functions/waitlist-reminders/handler.ts\n",
    )
    marketing = run("select-services", stdin="marketing/app/page.tsx\n")
    root_build = run(
        "select-services",
        stdin="pyproject.toml\npoetry.lock\n.python-version\nDockerfile\nrequirements.txt\n",
    )

    assert selected(shared) == ["cuadrao-api-staging", "cuadrao-app-staging"]
    assert selected(schema) == ["cuadrao-api-staging"]
    assert selected(config) == ["cuadrao-api-staging"]
    assert selected(edge) == []
    assert selected(marketing) == []
    assert selected(root_build) == ["cuadrao-api-staging"]


def test_each_service_uses_its_own_diff(tmp_path: Path) -> None:
    api_paths = tmp_path / "api.txt"
    web_paths = tmp_path / "web.txt"
    api_paths.write_text("web/app/page.tsx\n", encoding="utf-8")
    web_paths.write_text("", encoding="utf-8")

    untouched_web = run(
        "select-services",
        "--api-paths",
        str(api_paths),
        "--web-paths",
        str(web_paths),
    )
    api_paths.write_text("src/argus/api/main.py\n", encoding="utf-8")
    web_paths.write_text("web/app/page.tsx\n", encoding="utf-8")
    both = run(
        "select-services",
        "--api-paths",
        str(api_paths),
        "--web-paths",
        str(web_paths),
    )

    assert selected(untouched_web) == []
    assert selected(both) == ["cuadrao-api-staging", "cuadrao-app-staging"]


def test_ci_success_allows_skipped_docs_checks(tmp_path: Path) -> None:
    checks = tmp_path / "checks.jsonl"
    checks.write_text(
        "\n".join(
            (
                json.dumps(
                    {
                        "name": "ci",
                        "conclusion": "failure",
                        "completed_at": "2026-10-30T00:00:00Z",
                    }
                ),
                json.dumps(
                    {
                        "name": "ci",
                        "conclusion": "success",
                        "completed_at": "2026-10-30T01:00:00Z",
                    }
                ),
                json.dumps(
                    {
                        "name": "docs-checks",
                        "conclusion": "skipped",
                        "completed_at": "2026-10-30T01:00:00Z",
                    }
                ),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    status = tmp_path / "status.json"
    status.write_text(
        json.dumps({"state": "pending", "total_count": 0, "statuses": []}),
        encoding="utf-8",
    )

    result = run(
        "require-green",
        "--check-runs",
        str(checks),
        "--status",
        str(status),
    )

    assert result.returncode == 0, result.stderr


def test_missing_or_failed_ci_check_is_rejected(tmp_path: Path) -> None:
    checks = tmp_path / "checks.jsonl"
    checks.write_text(
        json.dumps(
            {
                "name": "backend-checks",
                "conclusion": "success",
                "completed_at": "2026-10-30T01:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    status = tmp_path / "status.json"
    status.write_text(
        json.dumps({"state": "success", "total_count": 0, "statuses": []}),
        encoding="utf-8",
    )

    missing = run(
        "require-green",
        "--check-runs",
        str(checks),
        "--status",
        str(status),
    )
    checks.write_text(
        json.dumps(
            {
                "name": "ci",
                "conclusion": "failure",
                "completed_at": "2026-10-30T02:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    failed = run(
        "require-green",
        "--check-runs",
        str(checks),
        "--status",
        str(status),
    )

    assert missing.returncode == 1
    assert "ci" in missing.stderr
    assert failed.returncode == 1


def test_failed_combined_status_is_rejected(tmp_path: Path) -> None:
    checks = tmp_path / "checks.json"
    checks.write_text(
        json.dumps(
            {
                "check_runs": [
                    {
                        "name": "ci",
                        "conclusion": "success",
                        "completed_at": "2026-10-30T01:00:00Z",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    status = tmp_path / "status.json"
    status.write_text(
        json.dumps(
            {
                "state": "failure",
                "total_count": 1,
                "statuses": [{"context": "review", "state": "failure"}],
            }
        ),
        encoding="utf-8",
    )

    result = run(
        "require-green",
        "--check-runs",
        str(checks),
        "--status",
        str(status),
    )

    assert result.returncode == 1
    assert "status" in result.stderr.lower()


def test_resolve_service_keeps_only_the_exact_staging_name() -> None:
    payload = json.dumps(
        [
            {"service": {"id": "srv-prodapi", "name": "cuadrao-api"}},
            {"service": {"id": "srv-stagingapi", "name": "cuadrao-api-staging"}},
        ]
    )

    resolved = run(
        "resolve-service",
        "--expect",
        "cuadrao-api-staging",
        stdin=payload,
    )
    rejected = run("resolve-service", "--expect", "cuadrao-api", stdin=payload)
    unsafe = run(
        "resolve-service",
        "--expect",
        "cuadrao-api-staging",
        stdin=json.dumps(
            [{"service": {"id": "srv-ok/extra", "name": "cuadrao-api-staging"}}]
        ),
    )

    assert resolved.returncode == 0, resolved.stderr
    assert resolved.stdout.strip() == "srv-stagingapi"
    assert rejected.returncode == 1
    assert unsafe.returncode == 1


def test_unknown_live_commit_uses_the_parent() -> None:
    parent = "b" * 40
    unknown = run(
        "comparison-base",
        env={"LIVE_COMMIT": "unknown", "PARENT_SHA": parent},
    )
    live = run(
        "comparison-base",
        env={"LIVE_COMMIT": "A" * 40, "PARENT_SHA": parent},
    )
    deploys = run(
        "live-commit",
        stdin=json.dumps(
            [
                {
                    "deploy": {
                        "status": "build_failed",
                        "createdAt": "2026-10-30T02:00:00Z",
                        "commit": {"id": "c" * 40},
                    }
                },
                {
                    "deploy": {
                        "status": "live",
                        "createdAt": "2026-10-30T01:00:00Z",
                        "commit": {"id": "d" * 40},
                    }
                },
            ]
        ),
    )

    plain = run(
        "live-commit",
        stdin=json.dumps(
            [
                {
                    "status": "live",
                    "createdAt": "2026-10-30T03:00:00Z",
                    "commit": "e" * 40,
                }
            ]
        ),
    )

    assert unknown.returncode == 0, unknown.stderr
    assert unknown.stdout.strip() == parent
    assert live.stdout.strip() == "a" * 40
    assert deploys.stdout.strip() == "d" * 40
    assert plain.stdout.strip() == "e" * 40


def test_older_base_is_the_ancestor(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    parent = init_repo(repo)
    (repo / "README.md").write_text("child\n", encoding="utf-8")
    git(repo, "commit", "-q", "-am", "child")
    child = git(repo, "rev-parse", "HEAD")

    result = run(
        "older-base",
        "--repo",
        str(repo),
        env={"API_BASE": child, "WEB_BASE": parent},
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == parent


SHA = "a" * 40


def write_status(path: Path, status: str, commit: str = SHA) -> None:
    path.write_text(
        json.dumps({"status": status, "commit": {"id": commit}}) + "\n",
        encoding="utf-8",
    )


def wait_deploy(path: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return run(
        "wait-deploy",
        "--name",
        "cuadrao-api-staging",
        "--sha",
        SHA,
        "--responses",
        str(path),
        "--timeout",
        "5",
        "--interval",
        "1",
        *extra,
    )


def test_failed_or_unknown_deploy_status_exits_nonzero(tmp_path: Path) -> None:
    for status in (
        "build_failed",
        "update_failed",
        "deactivated",
        "canceled",
        "rolled_back",
    ):
        payload = tmp_path / f"{status}.jsonl"
        write_status(payload, status)
        result = wait_deploy(payload)
        assert result.returncode != 0, status
        assert "cuadrao-api-staging" in result.stderr


def test_live_deploy_for_the_requested_commit_exits_zero(tmp_path: Path) -> None:
    payload = tmp_path / "live.jsonl"
    write_status(payload, "build_in_progress")
    payload.write_text(
        payload.read_text(encoding="utf-8")
        + json.dumps({"status": "live", "commit": {"id": SHA}})
        + "\n",
        encoding="utf-8",
    )
    result = wait_deploy(payload)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "cuadrao-api-staging is live."


def test_live_deploy_at_another_commit_fails(tmp_path: Path) -> None:
    payload = tmp_path / "mismatch.jsonl"
    write_status(payload, "live", "b" * 40)
    result = wait_deploy(payload)
    assert result.returncode != 0
    assert "cuadrao-api-staging" in result.stderr


def test_pending_deploy_times_out(tmp_path: Path) -> None:
    payload = tmp_path / "pending.jsonl"
    write_status(payload, "build_in_progress")
    result = wait_deploy(payload, "--timeout", "1")
    assert result.returncode != 0
    assert "timed out" in result.stderr
    assert "cuadrao-api-staging" in result.stderr


def git_diff_z(repo: Path, base: str, head: str) -> bytes:
    return subprocess.check_output(
        [
            "git",
            "diff",
            "--name-only",
            "-z",
            "--no-renames",
            "--diff-filter=ACDMRTUXB",
            f"{base}...{head}",
        ],
        cwd=repo,
    )


def add_file(repo: Path, relative: str) -> str:
    target = repo.joinpath(*relative.split("/"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "--", relative], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add"], cwd=repo, check=True)
    return git(repo, "rev-parse", "HEAD")


def test_unusual_git_paths_select_the_service(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    base = init_repo(repo)
    api_file = tmp_path / "api.z"
    web_file = tmp_path / "web.z"
    api_file.write_bytes(b"")

    accent = add_file(repo, "web/src/ñandú.ts")
    web_file.write_bytes(git_diff_z(repo, base, accent))
    accent_result = run(
        "select-services",
        "--api-paths",
        str(api_file),
        "--web-paths",
        str(web_file),
    )

    parent = accent
    newline_head = add_file(repo, "web/src/line\nbreak.ts")
    web_file.write_bytes(git_diff_z(repo, parent, newline_head))
    newline_result = run(
        "select-services",
        "--api-paths",
        str(api_file),
        "--web-paths",
        str(web_file),
    )

    spaced = add_file(repo, "src/argus/my module.py")
    api_file.write_bytes(git_diff_z(repo, newline_head, spaced))
    web_file.write_bytes(b"")
    spaced_result = run(
        "select-services",
        "--api-paths",
        str(api_file),
        "--web-paths",
        str(web_file),
    )

    assert selected(accent_result) == ["cuadrao-app-staging"]
    assert selected(newline_result) == ["cuadrao-app-staging"]
    assert newline_result.stdout.strip() != SKIP
    assert selected(spaced_result) == ["cuadrao-api-staging"]


def test_summarize_deploy_hides_ids(tmp_path: Path) -> None:
    response = tmp_path / "response.json"
    response.write_text(
        json.dumps(
            {
                "id": "dep-secret",
                "status": "build_in_progress",
                "service": {"id": "srv-secret"},
            }
        ),
        encoding="utf-8",
    )

    result = run(
        "summarize-deploy",
        "--name",
        "cuadrao-app-staging",
        "--response",
        str(response),
    )

    assert result.returncode == 0, result.stderr
    assert "cuadrao-app-staging" in result.stdout
    assert "srv-" not in result.stdout
    assert "dep-" not in result.stdout


def test_workflow_is_manual_and_least_privilege() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)

    assert set(workflow["on"]) == {"workflow_dispatch"}
    inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    assert inputs["sha"]["default"] == ""
    assert inputs["force_all"]["type"] == "boolean"
    assert inputs["dry_run"]["type"] == "boolean"
    assert inputs["dry_run"]["default"] is False
    assert workflow["permissions"] == {"contents": "read", "checks": "read"}
    assert workflow["concurrency"] == {
        "group": "deploy-staging",
        "cancel-in-progress": False,
    }
    assert "secrets.RENDER_API_KEY" in text
    assert "RENDER_API_KEY is missing" in text
    assert "cuadrao-app-staging" in text
    assert "cuadrao-web-staging" not in text
    assert "cuadrao-marketing" not in text
    assert re.search(r"(?<![\w-])cuadrao-api(?!-staging)\b", text) is None
    assert re.search(r"(?<![\w-])cuadrao-app(?!-staging)\b", text) is None
    assert re.search(r"(?<![\w-])cuadrao-web(?!-staging)\b", text) is None
    assert "uses:" not in text
    assert "set -x" not in text

    classify = None
    for job in workflow["jobs"].values():
        for step in job["steps"]:
            run_script = step.get("run")
            if not isinstance(run_script, str):
                continue
            assert "${{" not in run_script
            assert "inputs." not in run_script
            assert "secrets." not in run_script
            assert run_script.lstrip().startswith("set -euo pipefail\n")
            if ".github/docs-only-changes.sh" in run_script:
                classify = step
    assert classify is not None
    assert classify["env"]["PR_BASE_SHA"]
    assert classify["env"]["GITHUB_EVENT_NAME"] == "pull_request"
    assert any(
        line.strip() == ".github/docs-only-changes.sh"
        for line in classify["run"].splitlines()
    )
    assert "/v1/services/" in text
    assert "commitId" in text
    assert "/deploys" in text
    assert "--name-only -z" in text
    for job in workflow["jobs"].values():
        for step in job["steps"]:
            script = step.get("run") or ""
            if re.search(r"\bgh ", script):
                assert (step.get("env") or {}).get("GH_TOKEN") == "${{ github.token }}"
