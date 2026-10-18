"""Fail when a pull request adds evidence media.

The diff is `git diff --name-status --diff-filter=A <merge-base>...HEAD`.
It compares that merge base to HEAD. It does not diff the work tree, so
files that arrive by merging the base branch are not added files.

A path is evidence when it is under docs/reports/, or when any directory
segment is "evidence" or ends with "-evidence". Directory names and
suffixes match without regard to case. Suffixes are png, jpg, jpeg, gif,
webp, mp4, mov, and pdf.

Only added files fail. A modification or a rename does not. A line in
.github/media-allowlist.txt does not exempt an evidence path.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

MEDIA_SUFFIXES = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".mov", ".pdf"}
)
REJECTION = (
    "do not commit evidence media. Attach it on the pull request, "
    "or upload it with actions/upload-artifact."
)
MISSING_BASE = "Cannot find the merge base. Fetch the base history and retry."


class MergeBaseMissing(Exception):
    pass


def is_media(path: str) -> bool:
    dot = path.rfind(".")
    return dot >= 0 and path[dot:].lower() in MEDIA_SUFFIXES


def is_evidence_path(path: str) -> bool:
    directories = [segment.lower() for segment in path.split("/")[:-1]]
    if directories[:2] == ["docs", "reports"]:
        return True
    return any(
        segment == "evidence" or segment.endswith("-evidence") for segment in directories
    )


def load_globs(text: str) -> tuple[str, ...]:
    globs: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            globs.append(stripped)
    return tuple(globs)


def matches_glob(path: str, pattern: str) -> bool:
    if pattern.endswith("/**"):
        prefix = pattern[: -len("/**")]
        return path == prefix or path.startswith(prefix + "/")
    return path == pattern


def is_exempt(path: str, globs: tuple[str, ...]) -> bool:
    if is_evidence_path(path):
        return False
    return any(matches_glob(path, pattern) for pattern in globs)


def blocking_paths(changes: list[tuple[str, str]], globs: tuple[str, ...]) -> list[str]:
    blocked: list[str] = []
    for letter, path in changes:
        if letter != "A" or not is_media(path) or is_exempt(path, globs):
            continue
        if is_evidence_path(path):
            blocked.append(path)
    return blocked


def decode_field(field: bytes) -> str:
    return field.decode("utf-8", "surrogateescape")


def display_path(path: str) -> str:
    return path.encode("utf-8", "surrogateescape").decode("utf-8", "backslashreplace")


def parse_name_status(blob: bytes) -> list[tuple[str, str]]:
    parts = blob.split(b"\0")
    if parts and parts[-1] == b"":
        parts.pop()
    changes: list[tuple[str, str]] = []
    index = 0
    while index < len(parts):
        letter = decode_field(parts[index])[:1]
        if letter in {"R", "C"}:
            changes.append((letter, decode_field(parts[index + 2])))
            index += 3
            continue
        changes.append((letter, decode_field(parts[index + 1])))
        index += 2
    return changes


def resolve_merge_base(root: Path, base: str) -> str:
    present = subprocess.run(
        ["git", "cat-file", "-e", f"{base}^{{commit}}"],
        cwd=root,
        capture_output=True,
    )
    if present.returncode != 0:
        raise MergeBaseMissing(MISSING_BASE)
    result = subprocess.run(
        ["git", "merge-base", base, "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise MergeBaseMissing(MISSING_BASE)
    return result.stdout.strip()


def changed_paths(root: Path, base: str) -> list[tuple[str, str]]:
    resolved = resolve_merge_base(root, base)
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-status",
            "--find-renames",
            "--diff-filter=A",
            "-z",
            f"{resolved}...HEAD",
        ],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return parse_name_status(result.stdout)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--base", default=os.environ.get("PR_BASE_SHA", ""))
    parser.add_argument("--allowlist", type=Path, default=None)
    args = parser.parse_args(argv)
    base = args.base.strip()
    if not base:
        if os.environ.get("GITHUB_EVENT_NAME") == "pull_request":
            print("PR_BASE_SHA is required.", file=sys.stderr)
            return 1
        return 0
    allowlist = args.allowlist or (args.root / ".github" / "media-allowlist.txt")
    globs = load_globs(allowlist.read_text(encoding="utf-8"))
    try:
        changes = changed_paths(args.root, base)
    except MergeBaseMissing as exc:
        print(exc, file=sys.stderr)
        return 1
    blocked = blocking_paths(changes, globs)
    for path in blocked:
        print(f"{display_path(path)}: {REJECTION}", file=sys.stderr)
    return int(bool(blocked))


if __name__ == "__main__":
    raise SystemExit(main())
