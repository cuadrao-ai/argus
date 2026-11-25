"""Prove the web test shards together ran every file bun found, each exactly once.

Each shard runs ``bun test --shard=I/N`` and keeps its JUnit report and its log.
Bun prints ``--shard=I/N: running X/Y test files``, where Y counts every test
file it found. The shards cover that full list when every shard reports the
same Y, each JUnit report names exactly X files, no file appears in two shards,
and the union holds Y files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SHARD_LINE = re.compile(r"--shard=(\d+)/(\d+): running (\d+)/(\d+) test files?")
ANSI = re.compile(r"\x1b\[[0-9;]*m")


@dataclass(frozen=True)
class Shard:
    index: int
    count: int
    selected: int
    total: int
    files: frozenset[str]
    failures: int


def read_shard(report: Path, log: Path) -> Shard:
    matches = SHARD_LINE.findall(
        ANSI.sub("", log.read_text(encoding="utf-8", errors="replace"))
    )
    if len(matches) != 1:
        raise ValueError(f"{log}: expected one bun shard line, found {len(matches)}")
    index, count, selected, total = (int(value) for value in matches[0])
    root = ET.parse(report).getroot()
    if root.tag != "testsuites":
        raise ValueError(f"{report}: not a bun JUnit report")
    files = frozenset(suite.get("file", "") for suite in root.iter("testsuite"))
    if "" in files:
        raise ValueError(f"{report}: a test suite has no file")
    return Shard(
        index=index,
        count=count,
        selected=selected,
        total=total,
        files=files,
        failures=int(root.get("failures", "-1")),
    )


def verify(shards: list[Shard]) -> dict[str, Any]:
    if not shards:
        raise ValueError("no shard evidence supplied")
    count = shards[0].count
    if sorted(shard.index for shard in shards) != list(range(1, count + 1)):
        raise ValueError(f"expected shards 1..{count}, got a missing or repeated shard")
    total = shards[0].total
    seen: dict[str, int] = {}
    for shard in shards:
        if shard.count != count or shard.total != total:
            raise ValueError("shards disagree on the shard count or the full file count")
        if shard.failures != 0:
            raise ValueError(f"shard {shard.index} reports {shard.failures} failures")
        if not shard.files or len(shard.files) != shard.selected:
            raise ValueError(
                f"shard {shard.index} ran {shard.selected} files "
                f"but its report names {len(shard.files)}"
            )
        for name in shard.files:
            if name in seen:
                raise ValueError(f"{name} ran in shards {seen[name]} and {shard.index}")
            seen[name] = shard.index
    if len(seen) != total:
        raise ValueError(f"shards ran {len(seen)} files but bun found {total}")
    files = sorted(seen)
    return {
        "schema_version": 1,
        "shard_count": count,
        "file_count": total,
        "files": files,
        "selected_counts": {str(shard.index): shard.selected for shard in shards},
        "files_sha256": hashlib.sha256(json.dumps(files).encode()).hexdigest(),
        "union_exact": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "reports", type=Path, nargs="+", help="JUnit reports, each beside its .log"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify(
            [read_shard(path, path.with_suffix(".log")) for path in args.reports]
        )
    except (ValueError, OSError, ET.ParseError) as exc:
        parser.exit(1, f"Web shard evidence failed: {exc}\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
