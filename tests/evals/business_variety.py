"""Varied owner wording for the Business agent, judged by saved state.

The model reads each message. A case asserts only the facts the owner stated,
or that an unstated fact stays unknown. It never checks wording, and it never
selects behavior from the message text: the variety lives in the case data.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
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


def _token(name: str, fact: Any) -> str:
    if not isinstance(fact, dict) or fact.get("state") != "known":
        return "unknown"
    value = fact.get("value")
    if name == "funding" and isinstance(value, dict):
        return str(value.get("kind"))
    if name == "amount":
        return _number(value)
    return str(value)


def _number(value: Any) -> str:
    try:
        return format(Decimal(str(value)).normalize(), "f")
    except InvalidOperation:
        return str(value)


def _allowed(name: str, wanted: Any) -> list[str]:
    options = wanted["any_of"] if isinstance(wanted, dict) else [wanted]
    return [
        _number(o) if name == "amount" and o != "unknown" else str(o) for o in options
    ]


def check_variety(
    case: dict[str, Any], observed_steps: list[dict[str, Any]]
) -> list[str]:
    """Failures for one captured case; empty when every stated fact held."""

    failures: list[str] = []
    if len(observed_steps) != len(case["steps"]):
        return ["step_count_mismatch"]
    for index, (step, observed) in enumerate(
        zip(case["steps"], observed_steps, strict=True)
    ):
        expect = step["expect"]
        label = f"step{index}"
        if (
            "draft_count" in expect
            and observed.get("draft_count") != expect["draft_count"]
        ):
            failures.append(f"{label}:draft_count={observed.get('draft_count')}")
        if (observed.get("money") or {}).get("record_count"):
            failures.append(f"{label}:money_recorded")
        if observed.get("approval") is not None:
            failures.append(f"{label}:approval_present")
        facts = (observed.get("draft_facts") or {}).get(case["draft_alias"], {})
        for name in FACTS:
            if name not in expect:
                continue
            actual = _token(name, facts.get(name))
            if actual not in _allowed(name, expect[name]):
                failures.append(f"{label}:{name}={actual}")
    return failures
