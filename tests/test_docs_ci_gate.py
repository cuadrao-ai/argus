"""Execute production selectors and workflow Bash against isolated fixtures."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())


def bash(script: str, cwd: Path, env: dict[str, str] | None = None):
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", script],
        cwd=cwd,
        env={**os.environ, **(env or {})},
        capture_output=True,
        text=True,
    )


def write(root: Path, name: str, text: str = "") -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


@pytest.fixture
def selector_repo(tmp_path):
    write(
        tmp_path,
        ".github/docs-reading-tests.sh",
        (ROOT / ".github/docs-reading-tests.sh").read_text(),
    )
    (tmp_path / "tests").mkdir()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


def select(repo: Path, env: dict[str, str] | None = None):
    # git grep intentionally reads tracked files, as it does in an Actions checkout.
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    return bash("bash .github/docs-reading-tests.sh", repo, env)


@pytest.mark.parametrize("reader", ["conftest.py", "helpers.py"])
def test_helper_reader_selects_folder_without_collecting_helper(selector_repo, reader):
    write(selector_repo, f"tests/research/{reader}", 'SOURCE = "docs/evidence.json"\n')
    write(selector_repo, "tests/research/test_evidence.py", "def test_evidence(): pass\n")
    write(
        selector_repo, "tests/research/ignored.py", 'raise RuntimeError("not a test")\n'
    )
    result = select(selector_repo)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["tests/research"]
    collected = subprocess.run(
        [
            os.sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            *result.stdout.splitlines(),
        ],
        cwd=selector_repo,
        capture_output=True,
        text=True,
    )
    assert collected.returncode == 0, collected.stdout + collected.stderr
    assert "1 test collected" in collected.stdout


def test_direct_reader_selection(selector_repo):
    write(selector_repo, "tests/test_direct.py", 'SOURCE = "docs/PRODUCT.md"\n')
    write(selector_repo, "tests/other_test.py", 'SOURCE = Path("docs")\n')
    write(selector_repo, "tests/test_unrelated.py")
    result = select(selector_repo)
    assert result.returncode == 0, result.stderr
    assert set(result.stdout.splitlines()) == {
        "tests/test_direct.py",
        "tests/other_test.py",
    }


def test_selector_propagates_search_failure(selector_repo):
    executable = write(
        selector_repo,
        "bin/rg",
        '#!/bin/bash\nprintf "tests/test_partial.py\\n"\nexit 2\n',
    )
    executable.chmod(0o755)
    result = select(
        selector_repo,
        {"PATH": f'{executable.parent}:{os.environ["PATH"]}'},
    )
    assert result.returncode != 0


@pytest.mark.parametrize("flag", ["", "TRUE", "False", "0", "true ", "unexpected"])
def test_aggregate_rejects_invalid_flag(tmp_path, flag):
    assert aggregate(tmp_path, flag).returncode != 0


HEAVY_JOBS = {"BACKEND_CHECKS", "FRONTEND_CHECKS", "MARKETING_CHECKS", "DATABASE_CHECKS"}


def selected(job, flag):
    """A docs-only run selects docs-checks; any other run selects every heavy job."""
    return job in {"DOCS_CHANGE_GATE", "OWNERSHIP_GATE"} or (
        job == "DOCS_CHECKS" if flag == "true" else job in HEAVY_JOBS
    )


def aggregate(tmp_path, flag="true", **overrides):
    step = WORKFLOW["jobs"]["ci"]["steps"][0]
    env = {
        key: "success" if selected(key, flag) else "skipped"
        for key in step["env"]
    }
    heavy = "false" if flag == "true" else "true"
    env.update(DOCS_ONLY=flag, RUN_HEAVY=heavy, RUN_MARKETING=heavy, **overrides)
    return bash(step["run"], tmp_path, env)


@pytest.mark.parametrize("flag", ["true", "false"])
@pytest.mark.parametrize(
    "job",
    [
        "DOCS_CHANGE_GATE",
        "OWNERSHIP_GATE",
        "DOCS_CHECKS",
        "BACKEND_CHECKS",
        "FRONTEND_CHECKS",
        "MARKETING_CHECKS",
        "DATABASE_CHECKS",
    ],
)
@pytest.mark.parametrize("state", ["success", "failure", "cancelled", "skipped"])
def test_aggregate_preserves_dependency_policy(tmp_path, flag, job, state):
    # Only an unselected job may skip; failure and cancellation never pass.
    required = selected(job, flag)
    expected = state == "success" or (state == "skipped" and not required)
    result = aggregate(tmp_path, flag, **{job: state})
    assert (result.returncode == 0) == expected, result.stdout + result.stderr


@pytest.mark.parametrize("output,status", [("", 0), ("tests/test_partial.py\n", 2)])
def test_workflow_stops_before_pytest_on_empty_or_failed_selection(
    tmp_path, output, status
):
    selector = write(
        tmp_path,
        ".github/docs-reading-tests.sh",
        "#!/bin/bash\n" + f"printf '%s' '{output}'\nexit {status}\n",
    )
    selector.chmod(0o755)
    poetry = write(tmp_path, "bin/poetry", "#!/bin/bash\ntouch pytest-was-run\n")
    poetry.chmod(0o755)
    step = next(
        step
        for step in WORKFLOW["jobs"]["docs-checks"]["steps"]
        if step["name"] == "Run docs-reading backend tests"
    )
    result = bash(
        step["run"], tmp_path, {"PATH": f'{poetry.parent}:{os.environ["PATH"]}'}
    )
    assert result.returncode != 0
    if status == 0:
        assert "selector returned no files" in result.stdout
    assert not (tmp_path / "pytest-was-run").exists()
    # A failing docs job must remain red at the final aggregate.
    assert aggregate(tmp_path, DOCS_CHECKS="failure").returncode != 0


def test_aggregate_rejects_missing_flag(tmp_path, monkeypatch):
    monkeypatch.delenv("DOCS_ONLY", raising=False)
    step = WORKFLOW["jobs"]["ci"]["steps"][0]
    env = {key: "success" for key in step["env"] if key != "DOCS_ONLY"}
    env.update(RUN_HEAVY="true", RUN_MARKETING="true")
    result = bash(step["run"], tmp_path, env)
    assert result.returncode != 0
    assert "Invalid DOCS_ONLY" in result.stdout


def test_folder_selection_obeys_pytest_exclusions(selector_repo):
    write(
        selector_repo,
        "tests/research/conftest.py",
        'SOURCE = "docs/evidence.json"\ncollect_ignore = ["test_ignored.py"]\n',
    )
    write(selector_repo, "tests/research/test_ok.py", "def test_ok(): pass\n")
    write(
        selector_repo, "tests/research/test_ignored.py", 'raise RuntimeError("ignored")\n'
    )
    write(
        selector_repo,
        "tests/research/.hidden/test_hidden.py",
        'raise RuntimeError("hidden")\n',
    )
    result = select(selector_repo)
    assert result.returncode == 0
    collected = subprocess.run(
        [
            os.sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            *result.stdout.splitlines(),
        ],
        cwd=selector_repo,
        capture_output=True,
        text=True,
    )
    assert collected.returncode == 0, collected.stdout + collected.stderr
    assert "1 test collected" in collected.stdout


def test_git_grep_fallback_and_empty_search(selector_repo):
    # A real minimal PATH exercises the fallback without a mock of git grep.
    import shutil

    commands = selector_repo / "commands"
    commands.mkdir()
    for command in ("bash", "git", "dirname", "sort", "awk"):
        (commands / command).symlink_to(shutil.which(command))
    env = {"PATH": str(commands)}
    result = select(selector_repo, env)
    assert result.returncode == 0, result.stderr
    assert not result.stdout
    write(selector_repo, "tests/nested/helpers.py", 'SOURCE = "docs/evidence.json"\n')
    write(selector_repo, "tests/test_direct.py", 'SOURCE = "docs/PRODUCT.md"\n')
    subprocess.run(["git", "add", "."], cwd=selector_repo, check=True)
    result = select(selector_repo, env)
    assert result.returncode == 0, result.stderr
    assert set(result.stdout.splitlines()) == {"tests/nested", "tests/test_direct.py"}
    # Outside a repository, the fallback must fail, not yield an empty success.
    result = select(
        selector_repo,
        {**env, "GIT_DIR": str(selector_repo / "absent")},
    )
    assert result.returncode != 0


def test_workflow_passes_selected_paths_to_pytest(tmp_path):
    selector = write(
        tmp_path,
        ".github/docs-reading-tests.sh",
        '#!/bin/bash\nprintf "tests/folder with spaces\\ntests/test_direct.py\\n"\n',
    )
    selector.chmod(0o755)
    poetry = write(
        tmp_path, "bin/poetry", '#!/bin/bash\nprintf "%s\\n" "$@" > pytest-args\n'
    )
    poetry.chmod(0o755)
    step = next(
        step
        for step in WORKFLOW["jobs"]["docs-checks"]["steps"]
        if step["name"] == "Run docs-reading backend tests"
    )
    result = bash(
        step["run"], tmp_path, {"PATH": f'{poetry.parent}:{os.environ["PATH"]}'}
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "pytest-args").read_text().splitlines() == [
        "run",
        "pytest",
        "tests/folder with spaces",
        "tests/test_direct.py",
        "-q",
        "--no-cov",
    ]


def test_workflow_wires_changed_links_to_pr_base():
    step = next(
        step
        for step in WORKFLOW["jobs"]["docs-checks"]["steps"]
        if step["name"] == "Check changed documentation links"
    )
    assert step["env"]["PR_BASE_SHA"] == "${{ github.event.pull_request.base.sha }}"
    assert (
        step["run"]
        == 'poetry run python scripts/check_docs_links.py --base "$PR_BASE_SHA"'
    )
