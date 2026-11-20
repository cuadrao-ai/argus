"""Staging deploy decisions and the workflow that calls them.

The script is the caller the workflow uses. These tests drive that command
and the workflow file, not private helpers.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
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
    "cuadrao-documents-worker",
)
STAGING_NAMES = (
    "cuadrao-api-staging",
    "cuadrao-documents-worker-staging",
    "cuadrao-app-staging",
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
    for name in STAGING_NAMES:
        result = run("allow-name", "--name", name)
        assert result.returncode == 0, result.stderr
        assert result.stdout == ""


def test_web_only_change_selects_web() -> None:
    path = f"web/{FAKE.word()}/{FAKE.word()}.tsx"
    result = run("select-services", stdin=path + "\n")
    assert selected(result) == ["cuadrao-app-staging"]


def test_backend_only_change_selects_api_and_worker() -> None:
    path = f"src/argus/{FAKE.word()}.py"
    result = run("select-services", stdin=path + "\n")
    assert selected(result) == ["cuadrao-api-staging", "cuadrao-documents-worker-staging"]


def test_docs_only_change_selects_nothing() -> None:
    path = f"docs/{FAKE.word()}.md"
    result = run("select-services", stdin=path + "\n")
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [SKIP]


def test_force_all_selects_all_staging_services() -> None:
    result = run(
        "select-services",
        stdin="docs/PRODUCT.md\n",
        env={"FORCE_ALL": "true"},
    )
    assert selected(result) == list(STAGING_NAMES)


def test_path_rules_follow_render_build_and_poetry_packages() -> None:
    blueprint = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    services = {item["name"]: item for item in blueprint["services"]}
    api = services["cuadrao-api-staging"]
    web_blocks = [
        item
        for item in blueprint["services"]
        if item.get("rootDir") == "web" and item["branch"] == "codex/private-alpha-next"
    ]
    assert len(web_blocks) == 1
    web = web_blocks[0]
    assert web["name"] == "cuadrao-app-staging"
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

    assert selected(shared) == list(STAGING_NAMES)
    assert selected(schema) == ["cuadrao-api-staging", "cuadrao-documents-worker-staging"]
    assert selected(config) == ["cuadrao-api-staging", "cuadrao-documents-worker-staging"]
    assert selected(edge) == []
    assert selected(marketing) == []
    assert selected(root_build) == [
        "cuadrao-api-staging",
        "cuadrao-documents-worker-staging",
    ]


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
    assert selected(both) == list(STAGING_NAMES)


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


def test_status_request_errors_name_the_service(tmp_path: Path) -> None:
    (tmp_path / "deploy.json").write_text('{"id": "dep-abc123"}', encoding="utf-8")
    (tmp_path / "sitecustomize.py").write_text(
        "import os, urllib.error, urllib.request\n"
        "def urlopen(request, timeout=None):\n"
        "    if os.environ['FAKE_ERROR'] == 'timeout':\n"
        "        raise TimeoutError\n"
        "    raise urllib.error.HTTPError(request.full_url, 503, 'x', {}, None)\n"
        "urllib.request.urlopen = urlopen\n",
        encoding="utf-8",
    )
    for error, detail in (("timeout", "TimeoutError"), ("http", "HTTP 503")):
        result = run(
            "wait-deploy",
            "--name",
            "cuadrao-api-staging",
            "--sha",
            SHA,
            "--service-id",
            "srv-abc123",
            "--response",
            str(tmp_path / "deploy.json"),
            env={
                "FAKE_ERROR": error,
                "PYTHONPATH": str(tmp_path),
                "RENDER_API_KEY": "synthetic",
            },
        )
        assert result.returncode == 1, result.stderr
        assert f"cuadrao-api-staging status request failed: {detail}." in result.stderr


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
    assert selected(spaced_result) == [
        "cuadrao-api-staging",
        "cuadrao-documents-worker-staging",
    ]


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
    assert re.search(r"(?<![\w-])cuadrao-documents-worker(?!-staging)\b", text) is None
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


@pytest.mark.parametrize("path", ["workflows/document_worker.py", "workflows/runtime.py"])
def test_workflow_changes_select_the_worker(path: str) -> None:
    assert selected(run("select-services", stdin=path + "\n")) == [
        "cuadrao-documents-worker-staging"
    ]


@pytest.fixture
def workflow_run(tmp_path: Path, faker: Faker) -> dict:
    """Run the real shell steps with local service responses and a disposable repo."""
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    runner = tmp_path / "runner"
    runner.mkdir()
    for relative in ("scripts/ci/deploy_staging.py", ".github/docs-only-changes.sh"):
        for destination in (repo / relative, runner / "deploy-tools" / relative):
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "tools")
    base = git(repo, "rev-parse", "HEAD")
    middle = add_file(repo, f"src/argus/{faker.word()}.py")
    target = add_file(repo, f"docs/{faker.word()}.md")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    events = tmp_path / "events.jsonl"
    events.touch()
    curl = bin_dir / "curl"
    curl.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "services = json.loads(os.environ['FAKE_SERVICES'])\n"
        "url = args[-1]\n"
        "if '--request' in args:\n"
        "    assert args[args.index('--request') + 1] == 'POST'\n"
        "    sid = url.split('/')[-2]\n"
        "    name = next(n for n, s in services.items() if s == sid)\n"
        "    body = json.loads(args[args.index('--data') + 1])\n"
        "    with open(os.environ['FAKE_EVENTS'], 'a') as out:\n"
        "        out.write(json.dumps(['post', name, body]) + '\\n')\n"
        "    Path(args[args.index('--output') + 1]).write_text('{\"id\":\"dep-test\"}')\n"
        "elif '--get' in args:\n"
        "    name = next(a[5:] for a in args if a.startswith('name='))\n"
        "    print(json.dumps([{'service': {'name': name, 'id': services[name]}}]))\n"
        "else:\n"
        "    sid = url.split('/')[-2]\n"
        "    name = next(n for n, s in services.items() if s == sid)\n"
        "    live = json.loads(os.environ['FAKE_LIVE'])[name]\n"
        "    print(json.dumps([{'status': 'live', 'commit': {'id': live}}]))\n"
    )
    curl.chmod(0o755)
    (bin_dir / "sitecustomize.py").write_text(
        "import io, json, os, urllib.request\n"
        "def urlopen(request, timeout=None):\n"
        "    services = json.loads(os.environ['FAKE_SERVICES'])\n"
        "    sid = request.full_url.split('/')[-3]\n"
        "    name = next(n for n, s in services.items() if s == sid)\n"
        "    with open(os.environ['FAKE_EVENTS'], 'a') as out:\n"
        "        out.write(json.dumps(['wait', name]) + '\\n')\n"
        "    status = 'build_failed' if name == os.environ.get('FAIL_SERVICE') else 'live'\n"
        "    return io.BytesIO(json.dumps({'status': status, 'commit': {'id': os.environ['TARGET_SHA']}}).encode())\n"
        "urllib.request.urlopen = urlopen\n"
    )
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{Path(sys.executable).parent}:{os.environ['PATH']}",
        "PYTHONPATH": str(bin_dir),
        "RUNNER_TEMP": str(runner),
        "GITHUB_ENV": str(tmp_path / "job.env"),
        "RENDER_API_KEY": faker.pystr(),
        "TARGET_SHA": target,
        "FORCE_ALL": "true",
        "DRY_RUN": "false",
        "GITHUB_EVENT_NAME": "pull_request",
        "FAKE_SERVICES": json.dumps(
            {n: f"srv-test{i}" for i, n in enumerate(STAGING_NAMES)}
        ),
        "FAKE_LIVE": json.dumps(dict.fromkeys(STAGING_NAMES, base)),
        "FAKE_EVENTS": str(events),
    }
    return {"repo": repo, "env": env, "base": base, "middle": middle, "target": target}


def workflow_step(harness: dict, name: str) -> subprocess.CompletedProcess[str]:
    workflow = yaml.safe_load(WORKFLOW.read_text())
    step = next(s for s in workflow["jobs"]["deploy"]["steps"] if s["name"] == name)
    env = harness["env"]
    job_env = Path(env["GITHUB_ENV"])
    if job_env.exists():
        env.update(line.split("=", 1) for line in job_env.read_text().splitlines())
    if "COMPARE_BASE" in env:
        env["PR_BASE_SHA"] = env["COMPARE_BASE"]
    return subprocess.run(
        ["bash", "-c", step["run"]],
        cwd=harness["repo"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )


@pytest.mark.parametrize(
    "older_service", ["cuadrao-api-staging", "cuadrao-documents-worker-staging"]
)
def test_workflow_uses_older_api_worker_base_for_historical_drift(
    workflow_run: dict,
    older_service: str,
) -> None:
    harness = workflow_run
    live = dict.fromkeys(STAGING_NAMES, harness["target"])
    live[older_service] = harness["base"]
    harness["env"].update(FAKE_LIVE=json.dumps(live), FORCE_ALL="false")
    read = workflow_step(harness, "Read the last deployed commits")
    assert read.returncode == 0, read.stderr
    choose = workflow_step(harness, "Select jobs from changed files")
    assert choose.returncode == 0, choose.stderr
    assert harness["env"]["API_BASE"] == harness["base"]
    selection = (
        Path(harness["env"]["RUNNER_TEMP"], "selection.txt").read_text().splitlines()
    )
    assert selection == ["cuadrao-api-staging", "cuadrao-documents-worker-staging"]


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        ("", STAGING_NAMES),
        ("cuadrao-api-staging", STAGING_NAMES[:1]),
        ("cuadrao-documents-worker-staging", STAGING_NAMES[:2]),
    ],
)
def test_workflow_waits_in_order_at_one_sha_and_stops_on_failure(
    workflow_run: dict,
    failure: str,
    expected: tuple[str, ...],
) -> None:
    harness = workflow_run
    harness["env"]["FAIL_SERVICE"] = failure
    for name in ("Read the last deployed commits", "Select jobs from changed files"):
        result = workflow_step(harness, name)
        assert result.returncode == 0, result.stderr
    deployed = workflow_step(harness, "Deploy the selected services")
    assert (deployed.returncode != 0) == bool(failure), deployed.stderr
    events = [
        json.loads(line)
        for line in Path(harness["env"]["FAKE_EVENTS"]).read_text().splitlines()
    ]
    assert events == [
        event
        for name in expected
        for event in (["post", name, {"commitId": harness["target"]}], ["wait", name])
    ]


def test_workflow_dry_run_lists_all_services_at_target_without_requests(
    workflow_run: dict,
) -> None:
    harness = workflow_run
    harness["env"]["DRY_RUN"] = "true"
    for name in ("Read the last deployed commits", "Select jobs from changed files"):
        result = workflow_step(harness, name)
        assert result.returncode == 0, result.stderr
    result = workflow_step(harness, "Deploy the selected services")
    assert result.returncode == 0, result.stderr
    assert harness["target"] in result.stdout
    assert [line for line in result.stdout.splitlines() if line in STAGING_NAMES] == list(
        STAGING_NAMES
    )
    assert Path(harness["env"]["FAKE_EVENTS"]).read_text() == ""
