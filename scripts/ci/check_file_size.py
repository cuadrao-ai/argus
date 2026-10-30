"""Fail when a pull request adds or changes a file over 2 MB.

The diff is `git diff --name-status --find-renames --diff-filter=ACMR
<merge-base>...HEAD`, so files already on the base branch and files that
arrive by merging the base never fail. A rename that keeps the content
unchanged does not fail. Sizes are the blob sizes at HEAD.

Files under marketing/public/ are site assets and are allowed.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

LIMIT_BYTES = 2 * 1024 * 1024
ALLOWED_PREFIXES = ("marketing/public/",)
MISSING_BASE = "Cannot find the merge base. Fetch the base history and retry."


class MergeBaseMissing(Exception):
    pass


def resolve_merge_base(root: Path, base: str) -> str:
    result = subprocess.run(
        ["git", "merge-base", base, "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise MergeBaseMissing(MISSING_BASE)
    return result.stdout.strip()


def changed_paths(root: Path, base: str) -> list[str]:
    merge_base = resolve_merge_base(root, base)
    blob = subprocess.run(
        [
            "git",
            "diff",
            "--name-status",
            "--find-renames",
            "--diff-filter=ACMR",
            "-z",
            f"{merge_base}...HEAD",
        ],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    parts = [p.decode("utf-8", "surrogateescape") for p in blob.split(b"\0") if p]
    paths: list[str] = []
    index = 0
    while index < len(parts):
        status = parts[index]
        if status[0] in "RC":
            if status != "R100":
                paths.append(parts[index + 2])
            index += 3
            continue
        paths.append(parts[index + 1])
        index += 2
    return paths


def blob_size(root: Path, path: str) -> int:
    result = subprocess.run(
        ["git", "cat-file", "-s", f"HEAD:{path}"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return int(result.stdout)


def oversized(root: Path, paths: list[str]) -> list[tuple[str, int]]:
    found: list[tuple[str, int]] = []
    for path in paths:
        if path.startswith(ALLOWED_PREFIXES):
            continue
        size = blob_size(root, path)
        if size > LIMIT_BYTES:
            found.append((path, size))
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--base", default=os.environ.get("PR_BASE_SHA", ""))
    args = parser.parse_args(argv)
    base = args.base.strip()
    if not base:
        if os.environ.get("GITHUB_EVENT_NAME") == "pull_request":
            print("PR_BASE_SHA is required.", file=sys.stderr)
            return 1
        return 0
    try:
        found = oversized(args.root, changed_paths(args.root, base))
    except MergeBaseMissing as exc:
        print(exc, file=sys.stderr)
        return 1
    for path, size in found:
        print(
            f"{path}: {size / 1024 / 1024:.1f} MB is over the 2 MB limit. "
            "Attach it on the pull request or upload it with actions/upload-artifact.",
            file=sys.stderr,
        )
    return int(bool(found))


if __name__ == "__main__":
    raise SystemExit(main())
