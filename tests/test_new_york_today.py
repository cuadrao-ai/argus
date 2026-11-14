"""Today is the New York date on the one clock (#586).

A date derived from the current instant comes from domain.clock. The investing
readers that used to sit in this file are gone with that stack.
"""

from __future__ import annotations

import ast
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from argus.domain.clock import new_york_now, new_york_today

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src/argus"
OWNER = SOURCE_ROOT / "domain/clock.py"

INSTANTS = pytest.mark.parametrize(
    ("asked_at", "new_york_date"),
    [
        (datetime(2026, 9, 10, 0, 17, tzinfo=timezone.utc), date(2026, 9, 9)),
        (datetime(2026, 1, 1, 1, 17, tzinfo=timezone.utc), date(2025, 12, 31)),
        (datetime(2026, 3, 16, 16, 0, tzinfo=timezone.utc), date(2026, 3, 16)),
    ],
    ids=["daylight-evening", "standard-evening", "midday"],
)


@INSTANTS
def test_today_is_the_new_york_date(freeze_new_york_clock, asked_at: datetime, new_york_date: date) -> None:
    freeze_new_york_clock(asked_at)
    assert new_york_today() == new_york_date
    assert new_york_now() == asked_at


def _clock_offense(node: ast.AST, path: Path) -> bool:
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
        return False
    method, receiver = node.func.attr, node.func.value
    arguments = [*node.args, *node.keywords]
    if isinstance(receiver, ast.Name):
        if receiver.id in {"date", "datetime"} and method == "today":
            return True
        if receiver.id == "datetime" and method == "now" and not arguments:
            return True
        return method == "now" and path != OWNER and any(
            isinstance(argument, ast.Name) and argument.id == "EASTERN" for argument in node.args
        )
    if method == "date" and not arguments and isinstance(receiver, ast.Call):
        clock = receiver.func
        reads_now = (isinstance(clock, ast.Attribute) and clock.attr in {"now", "utcnow"}) or (
            isinstance(clock, ast.Name) and clock.id == "utcnow"
        )
        return reads_now and path != OWNER
    return False


def test_no_reader_dates_today_outside_the_one_clock() -> None:
    offenders = [
        f"{path.relative_to(SOURCE_ROOT)}:{node.lineno}"
        for path in sorted(SOURCE_ROOT.rglob("*.py"))
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if _clock_offense(node, path)
    ]
    assert offenders == []
