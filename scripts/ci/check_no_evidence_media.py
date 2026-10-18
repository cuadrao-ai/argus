"""Fail when a pull request adds evidence media.

A path is evidence when it is under docs/reports/, or when any directory
segment is "evidence" or ends with "-evidence". The match is
case-insensitive for that segment and for the suffix. Suffixes are png,
jpg, jpeg, gif, webp, mp4, mov, and pdf.

Only added files fail. Git copy status counts as added. A modification
or a rename does not. Brand canon paths in .github/media-allowlist.txt
are exempt.
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


def is_media(path: str) -> bool:
    dot = path.rfind(".")
    return dot >= 0 and path[dot:].lower() in MEDIA_SUFFIXES


def is_evidence_path(path: str) -> bool:
    parts = path.split("/")
    if len(parts) >= 2 and parts[0] == "docs" and parts[1] == "reports":
        return True
    for segment in parts[:-1]:
        lowered = segment.lower()
        if lowered == "evidence" or lowered.endswith("-evidence"):
            return True
    return False


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


def blocking_paths(changes: list[tuple[str, str]], globs: tuple[str, ...]) -> list[str]:
    blocked: list[str] = []
    for letter, path in changes:
        if letter not in {"A", "C"}:
            continue
        if not is_media(path) or not is_evidence_path(path):
            continue
        if any(matches_glob(path, pattern) for pattern in globs):
            continue
        blocked.append(path)
    return blocked


def parse_name_status(blob: bytes) -> list[tuple[str, str]]:
    parts = blob.split(b"\0")
    if parts and parts[-1] == b"":
        parts.pop()
    changes: list[tuple[str, str]] = []
    index = 0
    while index < len(parts):
        status = parts[index].decode()
        letter = status[:1]
        if letter in {"R", "C"}:
            changes.append((letter, parts[index + 2].decode()))
            index += 3
            continue
        changes.append((letter, parts[index + 1].decode()))
        index += 2
    return changes


def changed_paths(root: Path, base: str) -> list[tuple[str, str]]:
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-status",
            "--find-renames",
            "--find-copies",
            "-z",
            f"{base}...HEAD",
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
    blocked = blocking_paths(changed_paths(args.root, base), globs)
    for path in blocked:
        print(f"{path}: {REJECTION}", file=sys.stderr)
    return int(bool(blocked))


if __name__ == "__main__":
    raise SystemExit(main())
