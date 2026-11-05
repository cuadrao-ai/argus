"""Keep balancing weights tied to complete measured test executions."""

from __future__ import annotations

import pytest

from scripts.ci.update_shard_timings import generate


def inventory() -> dict:
    nodes = [
        "tests/test_a.py::test_a[one]",
        "tests/test_a.py::test_a[two]",
        "tests/test_b.py::test_b",
    ]
    return {
        "nodeids": nodes,
        "exitstatus": 0,
        "collection_errors": 0,
        "deselected": [],
        "reports": [
            {
                "nodeid": node,
                "phase": phase,
                "outcome": "passed",
                "duration_seconds": seconds,
            }
            for node in nodes
            for phase, seconds in [("setup", 1), ("call", 2), ("teardown", 3)]
        ],
    }


def test_weights_include_setup_call_and_teardown_for_every_test() -> None:
    assert generate(inventory()) == {"tests/test_a.py": 12, "tests/test_b.py": 6}


@pytest.mark.parametrize(
    "field,value",
    [("exitstatus", 1), ("collection_errors", 1), ("deselected", ["outside"])],
)
def test_incomplete_runs_cannot_become_balancing_evidence(
    field: str, value: object
) -> None:
    evidence = inventory()
    evidence[field] = value
    with pytest.raises(ValueError):
        generate(evidence)


def test_database_weights_require_all_tests_passed() -> None:
    evidence = inventory()
    evidence["reports"][1]["outcome"] = "skipped"
    generate(evidence)
    with pytest.raises(ValueError):
        generate(evidence, require_passed=True)
