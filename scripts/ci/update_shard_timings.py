"""Generate file timing weights from a completed test inventory."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from scripts.ci.test_shards import verify


def generate(inventory: dict, require_passed: bool = False) -> dict[str, float]:
    evidence = {
        **inventory,
        "full_nodeids": inventory.get("nodeids"),
        "shard_index": 0,
        "shard_count": 1,
    }
    verify([evidence], require_passed=require_passed)
    durations: dict[str, float] = defaultdict(float)
    for report in inventory["reports"]:
        durations[report["nodeid"].split("::", 1)[0]] += report["duration_seconds"]
    return {name: round(seconds, 6) for name, seconds in sorted(durations.items())}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--require-passed", action="store_true")
    args = parser.parse_args()
    try:
        timings = generate(
            json.loads(args.inventory.read_text(encoding="utf-8")), args.require_passed
        )
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Timing generation failed: {exc}\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(timings, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
