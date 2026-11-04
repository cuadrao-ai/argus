"""Collect tests twice in fresh processes and reject unstable test identities."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def collect(paths: list[str], output: Path, attempt: int) -> list[str]:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *paths,
            "--collect-only",
            "-q",
            "-o",
            "addopts=",
            "-p",
            "scripts.ci.pytest_inventory",
            f"--ci-inventory={output}",
            "--ci-shard-count=1",
            "--ci-shard-index=0",
        ],
        cwd=ROOT,
        env={**os.environ, "PYTEST_ADDOPTS": ""},
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode:
        detail = (result.stdout + result.stderr)[-2000:]
        raise ValueError(f"Collection {attempt} failed ({result.returncode}):\n{detail}")
    evidence = json.loads(output.read_text(encoding="utf-8"))
    if evidence["exitstatus"] != 0 or evidence["collection_errors"]:
        raise ValueError(f"Collection {attempt} failed")
    if evidence["deselected"] or evidence["sharded_out"]:
        raise ValueError(f"Collection {attempt} unexpectedly deselected tests")
    nodeids = evidence["full_nodeids"]
    if not nodeids:
        raise ValueError(f"Collection {attempt} is empty")
    if len(set(nodeids)) != len(nodeids):
        raise ValueError(f"Collection {attempt} contains duplicate test IDs")
    return nodeids


def check(paths: list[str]) -> int:
    with tempfile.TemporaryDirectory(prefix="test-id-collection-") as directory:
        work = Path(directory)
        first = collect(paths, work / "first.json", 1)
        second = collect(paths, work / "second.json", 2)
    if Counter(first) != Counter(second):
        removed = sorted(set(first) - set(second))
        added = sorted(set(second) - set(first))
        raise ValueError(
            "Test IDs differ between collections. Use stable explicit parameter IDs.\n"
            f"Only in first ({len(removed)}): {json.dumps(removed[:10])}\n"
            f"Only in second ({len(added)}): {json.dumps(added[:10])}"
        )
    return len(first)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", default=["tests"])
    args = parser.parse_args()
    try:
        count = check(args.paths)
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, f"Test ID stability check failed: {exc}\n")
    sys.stdout.write(f"Stable test IDs: {count} across two collections\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
