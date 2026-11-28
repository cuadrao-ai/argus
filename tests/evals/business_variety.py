"""Load the varied fixtures bound to the historical Business measurement."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

VARIETY_DIR = Path(__file__).with_name("business_variety_cases")
SCHEMA_VERSION = "business_variety_cases_v1"
FACTS = ("kind", "amount", "currency", "funding", "receipt_state", "occurred_on")


def load_variety_cases(directory: Path = VARIETY_DIR) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in sorted(directory.glob("case_*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if document["schema_version"] != SCHEMA_VERSION:
            raise ValueError("unknown variety case schema")
        for case in document["cases"]:
            if case["id"] in seen:
                raise ValueError(f"duplicate variety case: {case['id']}")
            seen.add(case["id"])
            for step in case["steps"]:
                expect = step["expect"]
                unknown = set(expect) - {"draft_count", *FACTS}
                if unknown:
                    raise ValueError(f"unknown expectation in {case['id']}: {unknown}")
            cases.append(case)
    return cases
