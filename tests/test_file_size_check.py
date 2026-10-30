from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts/ci/check_file_size.py"
BIG = b"x" * (2 * 1024 * 1024 + 1)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def init_repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "dev@example.com")
    git(tmp_path, "config", "user.name", "Dev")
    git(tmp_path, "config", "commit.gpgsign", "false")
    return tmp_path


def commit_bytes(repo: Path, path: str, payload: bytes) -> str:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", path)
    return git(repo, "rev-parse", "HEAD")


def run_check(repo: Path, base: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(repo), "--base", base],
        capture_output=True,
        text=True,
    )


def test_new_file_over_limit_fails(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    base = commit_bytes(repo, "README.md", b"base\n")
    commit_bytes(repo, "docs/clip.mp4", BIG)
    result = run_check(repo, base)
    assert result.returncode == 1
    assert "docs/clip.mp4" in result.stderr


def test_changed_file_over_limit_fails(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    base = commit_bytes(repo, "data.bin", b"small")
    commit_bytes(repo, "data.bin", BIG)
    assert run_check(repo, base).returncode == 1


def test_site_asset_over_limit_passes(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    base = commit_bytes(repo, "README.md", b"base\n")
    commit_bytes(repo, "marketing/public/site/hero.png", BIG)
    assert run_check(repo, base).returncode == 0


def test_untouched_big_file_on_base_passes(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    base = commit_bytes(repo, "docs/old.mp4", BIG)
    commit_bytes(repo, "README.md", b"edit\n")
    assert run_check(repo, base).returncode == 0


def test_deleted_big_file_passes(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    base = commit_bytes(repo, "docs/old.mp4", BIG)
    (repo / "docs/old.mp4").unlink()
    git(repo, "commit", "-qam", "delete")
    assert run_check(repo, base).returncode == 0


def test_unchanged_rename_passes(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    base = commit_bytes(repo, "docs/old.mp4", BIG)
    git(repo, "mv", "docs/old.mp4", "docs/moved.mp4")
    git(repo, "commit", "-qm", "move")
    assert run_check(repo, base).returncode == 0


def test_missing_base_fails(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    commit_bytes(repo, "README.md", b"base\n")
    assert run_check(repo, "0" * 40).returncode == 1
