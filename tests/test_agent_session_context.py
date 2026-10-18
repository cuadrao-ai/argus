from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "agent-session-context.sh"
CLAUDE_SETTINGS = ROOT / ".claude" / "settings.json"
CODEX_HOOKS = ROOT / ".codex" / "hooks.json"
INTEGRATION_REF = "refs/remotes/origin/codex/private-alpha-next"
NONE_SENTENCE = (
    "Ownership gate entry for this branch: none. "
    "Cross-seat file claims arrive in the launch prompt."
)


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )


def _init_repo(tmp_path: Path, *, branch: str) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", branch)
    _git(repo, "config", "user.email", "argus-tests@example.com")
    _git(repo, "config", "user.name", "Argus Tests")
    (repo / "README").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "README")
    _git(repo, "commit", "-m", "test: seed repository")
    return repo


def _empty_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    return home


def _run_script(repo: Path, home: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _write_ownership(repo: Path, branches: dict[str, list[str]]) -> None:
    path = repo / ".agent" / "ownership" / "branch_ownership.json"
    path.parent.mkdir(parents=True)
    payload = {"branches": {name: {"allow": paths} for name, paths in branches.items()}}
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_prints_integration_tip_and_checkout_when_remote_ref_exists(
    tmp_path: Path,
) -> None:
    branch = "cursor/session-facts"
    repo = _init_repo(tmp_path, branch=branch)
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", INTEGRATION_REF, head)

    result = _run_script(repo, _empty_home(tmp_path))

    assert result.returncode == 0, result.stderr
    assert (
        f"Integration tip origin/codex/private-alpha-next: {head} "
        "(fetched this session: no)"
    ) in result.stdout
    assert f"- Checkout: {branch} at {head}" in result.stdout
    assert len(result.stdout) < 8000


def test_prints_unknown_tip_when_remote_ref_is_missing(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path, branch="cursor/session-facts")

    result = _run_script(repo, _empty_home(tmp_path))

    assert result.returncode == 0, result.stderr
    assert (
        "Integration tip origin/codex/private-alpha-next: unknown "
        "(fetched this session: no)"
    ) in result.stdout
    assert "- poteto-mode skill: not installed in this environment." in result.stdout


def test_prints_allow_paths_for_the_current_branch(tmp_path: Path) -> None:
    branch = "cursor/session-facts"
    repo = _init_repo(tmp_path, branch=branch)
    allow = ["src/argus/api/chat.py", "web/app/page.tsx"]
    _write_ownership(repo, {branch: allow})

    result = _run_script(repo, _empty_home(tmp_path))

    assert result.returncode == 0, result.stderr
    assert f"- Ownership gate entry for {branch}: 2 allowed paths" in result.stdout
    assert "  - src/argus/api/chat.py" in result.stdout
    assert "  - web/app/page.tsx" in result.stdout


def test_prints_none_sentence_when_branch_has_no_entry(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path, branch="cursor/session-facts")
    _write_ownership(
        repo,
        {"other/branch": ["src/argus/api/chat.py", "web/app/page.tsx"]},
    )

    result = _run_script(repo, _empty_home(tmp_path))

    assert result.returncode == 0, result.stderr
    assert NONE_SENTENCE in result.stdout


def test_lists_first_25_allow_paths_and_keeps_stdout_under_8000_characters(
    tmp_path: Path,
) -> None:
    branch = "cursor/session-facts"
    repo = _init_repo(tmp_path, branch=branch)
    allow = [f"src/owned/file_{index:02d}.py" for index in range(30)]
    _write_ownership(repo, {branch: allow})

    result = _run_script(repo, _empty_home(tmp_path))

    listed = [
        line
        for line in result.stdout.splitlines()
        if line.startswith("  - ") and "more in " not in line
    ]
    assert result.returncode == 0, result.stderr
    assert listed == [f"  - {path}" for path in allow[:25]]
    assert "  - ... 5 more in .agent/ownership/branch_ownership.json" in result.stdout
    assert len(result.stdout) < 8000


def test_session_start_hooks_name_the_script() -> None:
    claude_settings = json.loads(CLAUDE_SETTINGS.read_text(encoding="utf-8"))
    codex_hooks = json.loads(CODEX_HOOKS.read_text(encoding="utf-8"))
    claude_hook = claude_settings["hooks"]["SessionStart"][0]["hooks"][0]
    codex_hook = codex_hooks["hooks"]["SessionStart"][0]["hooks"][0]

    assert claude_hook["command"] == "bash"
    assert claude_hook["args"] == [
        "${CLAUDE_PROJECT_DIR}/.github/agent-session-context.sh"
    ]
    assert ".github/agent-session-context.sh" in codex_hook["command"]


def test_shared_settings_are_trackable_and_local_settings_stay_ignored() -> None:
    tracked = subprocess.run(
        ["git", "check-ignore", "-q", ".claude/settings.json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    local = subprocess.run(
        ["git", "check-ignore", "-q", ".claude/settings.local.json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert tracked.returncode == 1
    assert local.returncode == 0
