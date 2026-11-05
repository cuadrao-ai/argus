"""Local link policy, exercised through the production command in a tiny repo."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts/check_docs_links.py"


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "ci@example.test")
    git(tmp_path, "config", "user.name", "CI fixture")
    git(tmp_path, "config", "commit.gpgsign", "false")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/historical.md").write_text("[old](missing.md)\n")
    (tmp_path / "docs/target (one).md").write_text("# Target\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "fixture base")
    return tmp_path


def check(repo, markdown, base="HEAD"):
    (repo / "docs/changed.md").write_text(markdown)
    git(repo, "add", ".")
    before = git(repo, "rev-parse", base)
    git(repo, "commit", "-qm", "changed document")
    return subprocess.run(
        [os.sys.executable, str(CHECKER), "--base", before],
        cwd=repo,
        text=True,
        capture_output=True,
    )


@pytest.mark.parametrize(
    "markdown",
    [
        "[valid](<target (one).md>)",
        "[valid](target%20%28one%29.md#target)",
        "[root](/docs/target%20%28one%29.md?raw=1)",
        "[folder](../docs/)",
        '[ref][target]\n\n[target]: <target (one).md> "title"',
        "![image](<target (one).md>)",
        '<a href="target%20%28one%29.md">file</a>',
        '<img src="target%20%28one%29.md">',
        "[external](https://example.invalid/no-http) [email](mailto:a@example.test)",
        "[external](//example.invalid/file) [anchor](#heading)",
        "`[example](missing.md)`\n\n```md\n[example](missing.md)\n```",
    ],
)
def test_valid_links_and_unchanged_history(repo, markdown):
    result = check(repo, markdown)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "markdown",
    [
        "[broken](missing.md)",
        "![broken](missing.png)",
        "[broken][ref]\n\n[ref]: missing.md",
        '<a href="missing.md">broken</a>',
        "[escape](../../outside.md)",
        "[escape](/../outside.md)",
    ],
)
def test_broken_local_links_fail(repo, markdown):
    result = check(repo, markdown)
    assert result.returncode != 0
    assert "docs/changed.md" in result.stdout + result.stderr


def test_invalid_base_fails(repo):
    result = check(repo, "# valid", base="HEAD")
    assert result.returncode == 0, result.stderr
    result = subprocess.run(
        [os.sys.executable, str(CHECKER), "--base", "missing-ref"],
        cwd=repo,
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0


def test_deleted_documents_are_not_opened(repo):
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "rm", "docs/historical.md")
    git(repo, "commit", "-qm", "delete historical document")
    result = subprocess.run(
        [os.sys.executable, str(CHECKER), "--base", base],
        cwd=repo,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
