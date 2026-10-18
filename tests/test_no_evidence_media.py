from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts/ci/check_no_evidence_media.py"
ALLOWLIST = ROOT / ".github/media-allowlist.txt"
REJECTION = (
    "do not commit evidence media. Attach it on the pull request, "
    "or upload it with actions/upload-artifact."
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


def init_repo(tmp_path: Path) -> tuple[Path, str]:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "dev@example.com")
    git(tmp_path, "config", "user.name", "Dev")
    git(tmp_path, "config", "commit.gpgsign", "false")
    (tmp_path / "README.md").write_text("base\n")
    git(tmp_path, "add", "README.md")
    git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path, git(tmp_path, "rev-parse", "HEAD")


def commit_bytes(repo: Path, path: str, payload: bytes) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    git(repo, "add", "--", path)
    git(repo, "commit", "-q", "-m", path)


def run_check(
    repo: Path,
    base: str,
    allowlist: Path = ALLOWLIST,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(CHECKER),
            "--root",
            str(repo),
            "--base",
            base,
            "--allowlist",
            str(allowlist),
        ],
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.mark.parametrize(
    "path",
    [
        "docs/reports/evidence/new.png",
        "docs/evidence/note.pdf",
        "docs/release-evidence/clip.mp4",
        "docs/reports/shot.PNG",
    ],
)
def test_added_evidence_media_fails(tmp_path: Path, path: str) -> None:
    repo, base = init_repo(tmp_path)
    commit_bytes(repo, path, b"new-evidence")
    result = run_check(repo, base)
    assert result.returncode == 1
    assert result.stderr.splitlines() == [f"{path}: {REJECTION}"]


def test_modified_existing_png_passes(tmp_path: Path) -> None:
    repo, _base = init_repo(tmp_path)
    path = "docs/reports/evidence/shot.png"
    commit_bytes(repo, path, b"old")
    base = git(repo, "rev-parse", "HEAD")
    commit_bytes(repo, path, b"edited")
    assert run_check(repo, base).returncode == 0


def rename(repo: Path, source: str, destination: str) -> None:
    (repo / destination).parent.mkdir(parents=True, exist_ok=True)
    git(repo, "mv", "--", source, destination)
    git(repo, "commit", "-q", "-m", "rename")


@pytest.mark.parametrize(
    ("source", "destination"),
    [
        ("assets/shot.png", "docs/reports/shot.png"),
        ("assets/shot.png", "notes/evidence/shot.png"),
        ("docs/reports/evidence/shot.png", "docs/reports/evidence/moved.png"),
    ],
)
def test_rename_into_gated_media_fails(
    tmp_path: Path, source: str, destination: str
) -> None:
    repo, _base = init_repo(tmp_path)
    commit_bytes(repo, source, b"same")
    base = git(repo, "rev-parse", "HEAD")
    rename(repo, source, destination)
    result = run_check(repo, base)
    assert result.returncode == 1
    assert result.stderr.splitlines() == [f"{destination}: {REJECTION}"]


@pytest.mark.parametrize(
    ("source", "destination"),
    [
        ("docs/reports/shot.png", "assets/shot.png"),
        ("assets/shot.png", "web/icons/shot.png"),
        ("assets/notes.txt", "docs/reports/notes.txt"),
        ("assets/notes.txt", "notes/evidence/notes.txt"),
    ],
)
def test_rename_that_does_not_introduce_gated_media_passes(
    tmp_path: Path, source: str, destination: str
) -> None:
    repo, _base = init_repo(tmp_path)
    commit_bytes(repo, source, b"same")
    base = git(repo, "rev-parse", "HEAD")
    rename(repo, source, destination)
    result = run_check(repo, base)
    assert result.returncode == 0
    assert result.stderr == ""


def test_copy_fails(tmp_path: Path) -> None:
    repo, _base = init_repo(tmp_path)
    source = "docs/reports/evidence/shot.png"
    commit_bytes(repo, source, b"same")
    base = git(repo, "rev-parse", "HEAD")
    destination = "docs/reports/evidence/copied.png"
    (repo / destination).write_bytes(b"same")
    (repo / source).write_bytes(b"edited")
    git(repo, "add", "--", source, destination)
    git(repo, "commit", "-q", "-m", "copy")
    result = run_check(repo, base)
    assert result.returncode == 1
    assert result.stderr.splitlines() == [f"{destination}: {REJECTION}"]


def test_committed_allowlist_matches_tracked_brand_files() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("check_no_evidence_media", CHECKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    globs = module.load_globs(ALLOWLIST.read_text(encoding="utf-8"))
    tracked = (
        subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    )
    missed = [
        pattern
        for pattern in globs
        if not any(module.matches_glob(path, pattern) for path in tracked if path)
    ]
    icons = sorted(
        path
        for path in tracked
        if path.startswith("marketing/app/")
        and path.count("/") == 2
        and path.rsplit(".", 1)[-1].lower() in {"png", "ico", "svg"}
    )
    app_globs = sorted(
        pattern for pattern in globs if pattern.startswith("marketing/app/")
    )
    assert globs
    assert missed == []
    assert icons
    assert app_globs == icons


def test_allowlisted_brand_asset_passes(tmp_path: Path) -> None:
    repo, base = init_repo(tmp_path)
    commit_bytes(repo, "web/public/icons/cuadrao-mark.png", b"brand")
    assert run_check(repo, base).returncode == 0


@pytest.mark.parametrize(
    ("path", "pattern"),
    [
        ("marketing/app/evidence/x.png", "marketing/app/**"),
        ("docs/reports/evidence/logo.png", "docs/reports/evidence/**"),
    ],
)
def test_allowlist_does_not_exempt_an_evidence_path(
    tmp_path: Path, path: str, pattern: str
) -> None:
    repo, base = init_repo(tmp_path)
    commit_bytes(repo, path, b"brand")
    allowlist = tmp_path / "allow.txt"
    allowlist.write_text(pattern + "\n")
    result = run_check(repo, base, allowlist)
    assert result.returncode == 1
    assert result.stderr.splitlines() == [f"{path}: {REJECTION}"]


@pytest.mark.parametrize(
    "path",
    [
        "Docs/Reports/x.png",
        "docs/REPORTS/x.png",
        "docs/EVIDENCE/x.png",
    ],
)
def test_evidence_path_match_ignores_case(tmp_path: Path, path: str) -> None:
    repo, base = init_repo(tmp_path)
    commit_bytes(repo, path, b"new-evidence")
    result = run_check(repo, base)
    assert result.returncode == 1
    assert result.stderr.splitlines() == [f"{path}: {REJECTION}"]


def commit_raw_path(repo: Path, name: bytes, payload: bytes) -> None:
    hashed = subprocess.run(
        ["git", "hash-object", "-w", "--stdin"],
        cwd=repo,
        input=payload,
        check=True,
        capture_output=True,
    )
    line = b"100644 " + hashed.stdout.strip() + b"\t" + name + b"\n"
    subprocess.run(
        ["git", "update-index", "--add", "--index-info"],
        cwd=repo,
        input=line,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", "raw-name"],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def test_non_utf8_evidence_media_fails(tmp_path: Path) -> None:
    repo, base = init_repo(tmp_path)
    commit_raw_path(repo, b"docs/reports/\xff.png", b"new-evidence")
    result = run_check(repo, base)
    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert result.stderr.splitlines() == [f"docs/reports/\\xff.png: {REJECTION}"]


def test_non_utf8_non_media_passes(tmp_path: Path) -> None:
    repo, base = init_repo(tmp_path)
    commit_raw_path(repo, b"notes\xff.txt", b"notes")
    result = run_check(repo, base)
    assert result.returncode == 0
    assert result.stderr == ""


@pytest.mark.parametrize(
    "path",
    [
        "tests/document_extraction_fixtures/sample.pdf",
        "web/e2e/__screenshots__/frame.png",
    ],
)
def test_non_evidence_folder_passes(tmp_path: Path, path: str) -> None:
    repo, base = init_repo(tmp_path)
    commit_bytes(repo, path, b"fixture")
    assert run_check(repo, base).returncode == 0


def test_png_already_on_the_base_passes(tmp_path: Path) -> None:
    repo, _base = init_repo(tmp_path)
    commit_bytes(repo, "ios/evidence/already.png", b"tip")
    base = git(repo, "rev-parse", "HEAD")
    (repo / "notes.txt").write_text("notes\n")
    git(repo, "add", "notes.txt")
    git(repo, "commit", "-q", "-m", "notes")
    result = run_check(repo, base)
    assert result.returncode == 0
    assert result.stderr == ""


def _merge_tip_with_pngs(repo: Path, root: str) -> str:
    git(repo, "checkout", "-q", "-b", "pr")
    (repo / "notes.txt").write_text("notes\n")
    git(repo, "add", "notes.txt")
    git(repo, "commit", "-q", "-m", "notes")
    git(repo, "checkout", "-q", "-b", "tip", root)
    for name in ("one.png", "two.png"):
        commit_bytes(repo, f"ios/evidence/{name}", b"tip")
    tip = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "pr")
    git(repo, "merge", "--no-edit", "tip")
    return tip


def test_merged_tip_pngs_pass(tmp_path: Path) -> None:
    repo, root = init_repo(tmp_path)
    tip = _merge_tip_with_pngs(repo, root)
    result = run_check(repo, tip)
    assert result.returncode == 0
    assert "ios/evidence/" not in result.stderr
    assert result.stderr == ""


def test_pr_png_after_merged_tip_names_only_that_file(tmp_path: Path) -> None:
    repo, root = init_repo(tmp_path)
    tip = _merge_tip_with_pngs(repo, root)
    ours = "docs/reports/evidence/ours.png"
    commit_bytes(repo, ours, b"ours")
    result = run_check(repo, tip)
    assert result.returncode == 1
    assert result.stderr.splitlines() == [f"{ours}: {REJECTION}"]


def test_missing_merge_base_fails_closed(tmp_path: Path) -> None:
    repo, _base = init_repo(tmp_path)
    missing = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
    result = run_check(repo, missing)
    assert result.returncode == 1
    assert result.stderr.strip() == (
        "Cannot find the merge base. Fetch the base history and retry."
    )
    assert missing not in result.stdout


def test_pull_request_without_a_base_fails(tmp_path: Path) -> None:
    repo, _base = init_repo(tmp_path)
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(repo), "--base", ""],
        capture_output=True,
        text=True,
        env={**os.environ, "GITHUB_EVENT_NAME": "pull_request", "PR_BASE_SHA": ""},
    )
    assert result.returncode == 1
    assert result.stderr.strip() == "PR_BASE_SHA is required."


def test_push_without_a_base_passes(tmp_path: Path) -> None:
    repo, _base = init_repo(tmp_path)
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(repo)],
        capture_output=True,
        text=True,
        env={**os.environ, "GITHUB_EVENT_NAME": "push", "PR_BASE_SHA": ""},
    )
    assert result.returncode == 0
    assert result.stderr == ""
