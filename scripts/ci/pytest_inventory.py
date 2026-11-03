"""Record exact test identities and timings without changing test selection."""

from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--ci-inventory", help="Write collection and execution evidence as JSON")


def pytest_configure(config: pytest.Config) -> None:
    output = config.getoption("--ci-inventory")
    if output:
        config.pluginmanager.register(Inventory(Path(output)), "ci-inventory-recorder")


class Inventory:
    def __init__(self, output: Path) -> None:
        self.output = output
        self.started = perf_counter()
        self.nodeids: list[str] = []
        self.deselected: list[str] = []
        self.reports: list[dict[str, str | float]] = []
        self.collection_errors = 0

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        self.nodeids = [item.nodeid for item in session.items]
        self.write(None)

    def pytest_deselected(self, items: list[pytest.Item]) -> None:
        self.deselected.extend(item.nodeid for item in items)

    def pytest_collectreport(self, report: pytest.CollectReport) -> None:
        if report.failed:
            self.collection_errors += 1

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        self.reports.append(
            {
                "nodeid": report.nodeid,
                "phase": report.when,
                "outcome": report.outcome,
                "duration_seconds": report.duration,
            }
        )

    def pytest_sessionfinish(self, exitstatus: int) -> None:
        self.write(int(exitstatus))

    def write(self, exitstatus: int | None) -> None:
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.output.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "nodeids": self.nodeids,
                    "deselected": self.deselected,
                    "collection_errors": self.collection_errors,
                    "exitstatus": exitstatus,
                    "elapsed_seconds": perf_counter() - self.started,
                    "reports": self.reports,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
