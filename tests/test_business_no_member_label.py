"""The Business domain never names a person with a fixed word: the profile
names them and the screen picks the fallback (#2219)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

BUSINESS = Path(__file__).resolve().parents[1] / "src" / "argus" / "domain" / "business"
STAND_INS = ("Member", "Miembro")


def stand_ins(source: str) -> list[int]:
    """Lines holding a stand-in as a whole string or a quoted SQL literal."""

    return sorted(
        node.lineno
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and any(node.value == word or f"'{word}'" in node.value for word in STAND_INS)
    )


@pytest.mark.parametrize(
    "path",
    sorted(BUSINESS.rglob("*.py")),
    ids=lambda path: str(path.relative_to(BUSINESS)),
)
def test_no_member_literal_stands_in_for_a_person(path: Path) -> None:
    assert stand_ins(path.read_text()) == []


def test_the_guard_sees_python_and_sql_fallbacks_but_not_prose() -> None:
    source = (
        'a = name or "Member"\n'
        "b = \"select coalesce(p.display_name,'Miembro')\"\n"
        'c = "Members no longer have access"\n'
    )
    assert stand_ins(source) == [1, 2]
