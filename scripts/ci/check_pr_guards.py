from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path

HOTSPOTS = (
    "web/public/locales/*/common.json",
    ".env.example",
    ".github/private-alpha-release-profile.json",
    "render.yaml",
    "scripts/ops/staging_env_manifest.json",
    "web/lib/private-alpha-flags.ts",
    ".gitattributes",
)
LOCK_NAMES = frozenset(
    {
        "package-lock.json",
        "pnpm-lock.yaml",
        "poetry.lock",
        "uv.lock",
        "yarn.lock",
    }
)
WARN_ABOVE = 400
FAIL_ABOVE = 800
LANDING_NEXT = "landing-next"
SIZE_APPROVED = "size-approved"
MISSING_BASE = "Cannot find the merge base. Fetch the base history and retry."
HOTSPOT_SENTENCE = "The lead applies landing-next when the pull request is next to land."
SIZE_SENTENCE = (
    "The lead applies size-approved when an oversized pull request is approved."
)


class GuardError(Exception):
    pass


@dataclass(frozen=True)
class ChangedFile:
    path: str
    previous_path: str | None
    added: int | None
    deleted: int | None


def decode_field(field: bytes) -> str:
    return field.decode("utf-8", "surrogateescape")


def display_path(path: str) -> str:
    return path.encode("utf-8", "surrogateescape").decode("utf-8", "backslashreplace")


def nul_fields(blob: bytes) -> list[bytes]:
    parts = blob.split(b"\0")
    if parts and parts[-1] == b"":
        parts.pop()
    return parts


def is_hotspot(path: str) -> bool:
    parts = path.split("/")
    for pattern in HOTSPOTS:
        tokens = pattern.split("/")
        if len(tokens) != len(parts):
            continue
        if all(
            fnmatchcase(part, token) for part, token in zip(parts, tokens, strict=True)
        ):
            return True
    return False


def is_test_path(path: str) -> bool:
    parts = path.split("/")
    if parts[0] in {"tests", "e2e"} or "__tests__" in parts:
        return True
    name = parts[-1]
    return fnmatchcase(name, "*.test.*") or fnmatchcase(name, "*.spec.*")


def is_excluded(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    parts = path.split("/")
    return (
        is_test_path(path)
        or name in LOCK_NAMES
        or name.startswith("bun.lock")
        or "fixtures" in parts
        or fnmatchcase(name, "*.generated.*")
    )


def line_count(text: str) -> int | None:
    if text == "-":
        return None
    if not text.isdigit():
        raise GuardError("Cannot read the diff.")
    return int(text)


def parse_numstat(blob: bytes) -> list[ChangedFile]:
    parts = nul_fields(blob)
    changes: list[ChangedFile] = []
    index = 0
    while index < len(parts):
        pieces = decode_field(parts[index]).split("\t")
        index += 1
        if len(pieces) != 3:
            raise GuardError("Cannot read the diff.")
        added_text, deleted_text, path = pieces
        previous = None
        if path == "":
            if index + 1 >= len(parts):
                raise GuardError("Cannot read the diff.")
            previous = decode_field(parts[index])
            path = decode_field(parts[index + 1])
            index += 2
        changes.append(
            ChangedFile(
                path=path,
                previous_path=previous,
                added=line_count(added_text),
                deleted=line_count(deleted_text),
            )
        )
    return changes


def parse_names(blob: bytes) -> list[str]:
    return [decode_field(field) for field in nul_fields(blob)]


def resolve_merge_base(root: Path, base: str) -> str:
    if not base:
        raise GuardError(MISSING_BASE)
    present = subprocess.run(
        ["git", "cat-file", "-e", f"{base}^{{commit}}"],
        cwd=root,
        capture_output=True,
    )
    if present.returncode != 0:
        raise GuardError(MISSING_BASE)
    result = subprocess.run(
        ["git", "merge-base", base, "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise GuardError(MISSING_BASE)
    return result.stdout.strip()


def git_diff(root: Path, merge_base: str, mode: str) -> bytes:
    result = subprocess.run(
        [
            "git",
            "diff",
            "-z",
            mode,
            "--find-renames",
            f"{merge_base}...HEAD",
        ],
        cwd=root,
        capture_output=True,
    )
    if result.returncode != 0:
        raise GuardError(MISSING_BASE)
    return result.stdout


def load_changes(root: Path, base: str) -> tuple[list[str], list[ChangedFile]]:
    merge_base = resolve_merge_base(root, base)
    names = parse_names(git_diff(root, merge_base, "--name-only"))
    changes = parse_numstat(git_diff(root, merge_base, "--numstat"))
    return names, changes


def event_labels() -> frozenset[str]:
    raw_path = os.environ.get("GITHUB_EVENT_PATH", "").strip()
    if not raw_path:
        raise GuardError("GITHUB_EVENT_PATH is required.")
    try:
        payload = json.loads(Path(raw_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GuardError(f"Cannot read the pull request event: {exc}") from exc
    if not isinstance(payload, dict):
        raise GuardError("The event has no pull request.")
    request = payload.get("pull_request")
    if not isinstance(request, dict):
        raise GuardError("The event has no pull request.")
    raw_labels = request.get("labels") or []
    if not isinstance(raw_labels, list):
        raise GuardError("The event labels are not a list.")
    names: set[str] = set()
    for item in raw_labels:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if isinstance(name, str) and name:
            names.add(name)
    return frozenset(names)


def hotspot_hits(names: list[str], changes: list[ChangedFile]) -> list[str]:
    seen: set[str] = set()
    candidates = list(names)
    for change in changes:
        candidates.append(change.path)
        if change.previous_path is not None:
            candidates.append(change.previous_path)
    for path in candidates:
        if is_hotspot(path):
            seen.add(path)
    return sorted(seen)


def report_hotspots(
    names: list[str], changes: list[ChangedFile], labels: frozenset[str]
) -> int:
    hits = hotspot_hits(names, changes)
    if not hits or LANDING_NEXT in labels:
        return 0
    for path in hits:
        print(display_path(path), file=sys.stderr)
    print(HOTSPOT_SENTENCE, file=sys.stderr)
    return 1


def generated_paths(root: Path, paths: list[str]) -> set[str]:
    if not paths:
        return set()
    result = subprocess.run(
        ["git", "check-attr", "-z", "linguist-generated", "--", *paths],
        cwd=root,
        capture_output=True,
    )
    if result.returncode != 0:
        raise GuardError("Cannot read linguist-generated attributes.")
    parts = nul_fields(result.stdout)
    generated: set[str] = set()
    index = 0
    while index < len(parts):
        if index + 2 >= len(parts):
            raise GuardError("Cannot read linguist-generated attributes.")
        path = decode_field(parts[index])
        value = decode_field(parts[index + 2])
        if value in {"set", "true"}:
            generated.add(path)
        index += 3
    return generated


def counted_lines(change: ChangedFile, generated: set[str]) -> int:
    if change.added is None or change.deleted is None:
        return 0
    if is_excluded(change.path) or change.path in generated:
        return 0
    return change.added + change.deleted


def report_size(root: Path, changes: list[ChangedFile], labels: frozenset[str]) -> int:
    generated = generated_paths(root, [change.path for change in changes])
    rows: list[tuple[int, str]] = []
    total = 0
    for change in changes:
        lines = counted_lines(change, generated)
        if lines <= 0:
            continue
        total += lines
        rows.append((lines, change.path))
    rows.sort(key=lambda item: (-item[0], item[1]))
    output = [f"counted {total}"]
    output.extend(f"{display_path(path)} {count}" for count, path in rows)
    if total > WARN_ABOVE:
        output.append(f"::warning::{total} non-test lines is above {WARN_ABOVE}.")
    print("\n".join(output))
    if total > FAIL_ABOVE and SIZE_APPROVED not in labels:
        print(
            f"{total} non-test lines is above {FAIL_ABOVE}. {SIZE_SENTENCE}",
            file=sys.stderr,
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail hotspot edits and oversized pull requests."
    )
    parser.add_argument("command", choices=("hotspot", "size"))
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--base", default="")
    args = parser.parse_args(argv)
    root = args.root if args.root is not None else Path(__file__).resolve().parents[2]
    base = args.base.strip() or os.environ.get("PR_BASE_SHA", "").strip()
    try:
        labels = event_labels()
        names, changes = load_changes(root, base)
    except GuardError as exc:
        print(exc, file=sys.stderr)
        return 1
    if args.command == "hotspot":
        return report_hotspots(names, changes, labels)
    return report_size(root, changes, labels)


if __name__ == "__main__":
    raise SystemExit(main())
