"""Select balanced test shards and record exact identities and execution timings."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Generator
from pathlib import Path
from time import perf_counter

import pytest

from scripts.ci.test_shards import partition, read_timings


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--ci-inventory", help="Write collection and execution evidence as JSON"
    )
    parser.addoption("--ci-shard-index", type=int, default=0)
    parser.addoption("--ci-shard-count", type=int, default=1)
    parser.addoption("--ci-timings", type=Path)


def pytest_configure(config: pytest.Config) -> None:
    output = config.getoption("--ci-inventory")
    index = config.getoption("--ci-shard-index")
    count = config.getoption("--ci-shard-count")
    if count < 1 or not 0 <= index < count:
        raise pytest.UsageError("invalid CI shard index or count")
    if count > 1 and not output:
        raise pytest.UsageError("sharding requires --ci-inventory")
    if output:
        path = config.getoption("--ci-timings")
        try:
            timings = read_timings(path) if path else {}
        except (ValueError, OSError) as exc:
            raise pytest.UsageError(str(exc)) from exc
        config.pluginmanager.register(
            Inventory(Path(output), index, count, timings), "ci-inventory-recorder"
        )


class Inventory:
    def __init__(
        self, output: Path, index: int, count: int, timings: dict[str, float]
    ) -> None:
        self.output = output
        self.index = index
        self.count = count
        self.timings = timings
        self.full_nodeids: list[str] = []
        self.sharded_out: list[str] = []
        self.partitioning = False
        self.started = perf_counter()
        self.nodeids: list[str] = []
        self.deselected: list[str] = []
        self.reports: list[dict[str, str | float]] = []
        self.collection_errors = 0

    @pytest.hookimpl(wrapper=True, tryfirst=True)
    def pytest_collection_modifyitems(
        self, config: pytest.Config, items: list[pytest.Item]
    ) -> Generator[None, None, None]:
        original = [item.nodeid for item in items]
        result = yield
        self.full_nodeids = [item.nodeid for item in items]
        if self.count > 1:
            if self.deselected or Counter(original) != Counter(self.full_nodeids):
                raise pytest.UsageError("unexpected deselection before CI sharding")
            try:
                selected = set(
                    partition(self.full_nodeids, self.count, self.timings)[self.index]
                )
            except ValueError as exc:
                raise pytest.UsageError(str(exc)) from exc
            excluded = [item for item in items if item.nodeid not in selected]
            items[:] = [item for item in items if item.nodeid in selected]
            self.sharded_out = [item.nodeid for item in excluded]
            self.partitioning = True
            try:
                config.hook.pytest_deselected(items=excluded)
            finally:
                self.partitioning = False
        return result

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        self.nodeids = [item.nodeid for item in session.items]
        self.write(None)

    def pytest_deselected(self, items: list[pytest.Item]) -> None:
        if not self.partitioning:
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
                    "schema_version": 2,
                    "full_nodeids": self.full_nodeids,
                    "shard_index": self.index,
                    "shard_count": self.count,
                    "sharded_out": self.sharded_out,
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
