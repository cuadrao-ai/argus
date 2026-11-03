"""Partition collected tests and verify the evidence from every shard."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any


def _integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def read_timings(path: Path) -> dict[str, float]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("timings must be a file-to-seconds mapping")
    return validate_timings(raw)


def validate_timings(raw: dict[str, Any]) -> dict[str, float]:
    timings = {}
    for name, seconds in raw.items():
        if not isinstance(name, str) or not name.endswith(".py") or "::" in name:
            raise ValueError("timing keys must be test file paths")
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
            raise ValueError(f"invalid duration for {name}")
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError(f"invalid duration for {name}")
        timings[name] = float(seconds)
    return timings


def identities(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(n, str) and n for n in value):
        raise ValueError(f"{label} must be a list of node IDs")
    if len(set(value)) != len(value):
        raise ValueError(f"{label} contains duplicate node IDs")
    return value


def partition(
    nodeids: list[str], count: int, timings: dict[str, float]
) -> list[list[str]]:
    identities(nodeids, "collection")
    if not _integer(count) or count < 1:
        raise ValueError("shard count must be a positive integer")
    timings = validate_timings(timings)
    files: dict[str, list[str]] = defaultdict(list)
    for nodeid in nodeids:
        files[nodeid.split("::", 1)[0]].append(nodeid)
    if len(files) < count:
        raise ValueError("shard count exceeds collected test files")
    costs = [
        timings[name] / len(nodes)
        for name, nodes in files.items()
        if timings.get(name, 0) > 0
    ]
    fallback = median(costs) if costs else 1.0
    weights = {
        name: max(timings.get(name, fallback * len(nodes)), 1e-9)
        for name, nodes in files.items()
    }
    loads = [0.0] * count
    assignments = {}
    for name in sorted(files, key=lambda name: (-weights[name], name)):
        index = min(range(count), key=lambda shard: (loads[shard], shard))
        assignments[name] = index
        loads[index] += weights[name]
    shards: list[list[str]] = [[] for _ in range(count)]
    for nodeid in nodeids:
        shards[assignments[nodeid.split("::", 1)[0]]].append(nodeid)
    if any(not shard for shard in shards):
        raise ValueError("partition produced an empty shard")
    return shards


def _execution(
    evidence: dict[str, Any], selected: list[str], require_passed: bool
) -> None:
    if not _integer(evidence.get("exitstatus")) or evidence["exitstatus"] != 0:
        raise ValueError("shard did not finish successfully")
    if (
        not _integer(evidence.get("collection_errors"))
        or evidence["collection_errors"] != 0
    ):
        raise ValueError("shard has collection errors or missing collection status")
    if evidence.get("deselected") != []:
        raise ValueError("shard has unexpected deselection")
    reports = evidence.get("reports")
    if not isinstance(reports, list):
        raise ValueError("shard has no execution reports")
    by_node: dict[str, dict[str, str]] = {nodeid: {} for nodeid in selected}
    for report in reports:
        if not isinstance(report, dict) or report.get("nodeid") not in by_node:
            raise ValueError("execution report references an unselected test")
        phases = by_node[report["nodeid"]]
        phase = report.get("phase")
        if phase not in {"setup", "call", "teardown"} or phase in phases:
            raise ValueError("duplicate or invalid execution phase")
        outcome = report.get("outcome")
        if outcome not in ({"passed"} if require_passed else {"passed", "skipped"}):
            raise ValueError("execution report has an unacceptable outcome")
        duration = report.get("duration_seconds")
        if isinstance(duration, bool) or not isinstance(duration, (int, float)):
            raise ValueError("execution report has an invalid duration")
        if not math.isfinite(duration) or duration < 0:
            raise ValueError("execution report has an invalid duration")
        phases[phase] = outcome
    for nodeid, phases in by_node.items():
        required = {"setup", "teardown"}
        if phases.get("setup") == "passed":
            required.add("call")
        if set(phases) != required:
            raise ValueError(f"incomplete execution for {nodeid}")


def verify(
    evidence: list[dict[str, Any]],
    *,
    require_passed: bool = False,
    baseline: dict[str, Any] | None = None,
    allow_added_files: tuple[str, ...] = (),
) -> dict[str, Any]:
    if not evidence:
        raise ValueError("no shard evidence supplied")
    if not all(isinstance(shard, dict) for shard in evidence):
        raise ValueError("shard evidence must contain JSON objects")
    first = evidence[0]
    count = first.get("shard_count")
    if not _integer(count) or count < 1 or len(evidence) != count:
        raise ValueError("missing shard evidence or invalid shard count")
    full = identities(first.get("full_nodeids"), "full collection")
    if not full:
        raise ValueError("full collection is empty")
    indices = []
    union: list[str] = []
    selected_counts = {}
    for shard in evidence:
        index = shard.get("shard_index")
        if not _integer(index) or not 0 <= index < count:
            raise ValueError("invalid shard index")
        if not _integer(shard.get("shard_count")) or shard["shard_count"] != count:
            raise ValueError("shard counts disagree")
        if Counter(identities(shard.get("full_nodeids"), "full collection")) != Counter(
            full
        ):
            raise ValueError("full collections disagree across shards")
        indices.append(index)
        selected = identities(shard.get("nodeids"), "selected collection")
        if not selected:
            raise ValueError("selected shard is empty")
        _execution(shard, selected, require_passed)
        union.extend(selected)
        selected_counts[str(index)] = len(selected)
    if sorted(indices) != list(range(count)):
        raise ValueError("missing or repeated shard index")
    if Counter(union) != Counter(full):
        raise ValueError("shard union differs from full collection or repeats a test")
    skipped = {
        report["nodeid"]
        for shard in evidence
        for report in shard["reports"]
        if report["outcome"] == "skipped"
    }
    added: list[str] = []
    if baseline is not None:
        previous = identities(baseline.get("nodeids"), "baseline collection")
        _execution(baseline, previous, require_passed)
        baseline_skipped = {
            report["nodeid"]
            for report in baseline["reports"]
            if report["outcome"] == "skipped"
        }
        new_skips = sorted((skipped & set(previous)) - baseline_skipped)
        if new_skips:
            raise ValueError(
                f"previously executed tests now skipped: {json.dumps(new_skips)}"
            )
        removed = sorted(set(previous) - set(full))
        added = sorted(set(full) - set(previous))
        if removed:
            raise ValueError(f"baseline tests removed: {json.dumps(removed)}")
        unexpected = [n for n in added if n.split("::", 1)[0] not in allow_added_files]
        if unexpected:
            raise ValueError(f"unexpected added tests: {json.dumps(unexpected)}")
    digest = hashlib.sha256(
        json.dumps(sorted(full), ensure_ascii=True).encode()
    ).hexdigest()
    return {
        "schema_version": 1,
        "shard_count": count,
        "test_count": len(full),
        "nodeids": full,
        "selected_counts": selected_counts,
        "skipped_nodeids": sorted(skipped),
        "nodeids_sha256": digest,
        "union_exact": True,
        "duplicates": 0,
        "added_nodeids": added,
        "removed_nodeids": [],
        "baseline_compared": baseline is not None,
        "require_passed": require_passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-passed", action="store_true")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--allow-added-file", action="append", default=[])
    args = parser.parse_args()
    try:
        result = verify(
            [json.loads(path.read_text(encoding="utf-8")) for path in args.evidence],
            require_passed=args.require_passed,
            baseline=json.loads(args.baseline.read_text(encoding="utf-8"))
            if args.baseline
            else None,
            allow_added_files=tuple(args.allow_added_file),
        )
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Shard evidence failed: {exc}\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
