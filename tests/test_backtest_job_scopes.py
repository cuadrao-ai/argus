"""Every ``operation_scope`` value is spelled once, in the registry.

The registry only holds if nothing else spells a scope. This walks every
production Python file (``src``, ``workflows``, ``scripts``) as an AST and
fails on any string constant equal to a scope value outside
``argus.domain.job_scopes``; docstrings are skipped, comments never
reach the AST. A consumer that hardcodes a scope stops matching the moment the
registry and the rendered constraint move, and this is the test that would
have caught the two sites the review found.

Tests are out of the sweep on purpose: fixtures spell the value they assert.
"""

from __future__ import annotations

import ast
from pathlib import Path

from argus.domain.job_scopes import OPERATION_SCOPES

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "src/argus/domain/job_scopes.py"
PRODUCTION_TREES = ("src", "workflows", "scripts")


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
    return ids


def _scope_literals(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstrings = _docstring_nodes(tree)
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value in OPERATION_SCOPES
        and id(node) not in docstrings
    ]


def _production_files() -> list[Path]:
    files: list[Path] = []
    for tree in PRODUCTION_TREES:
        files.extend(
            path
            for path in (ROOT / tree).rglob("*.py")
            if "tests" not in path.parts and path != REGISTRY
        )
    return sorted(files)


def test_no_production_code_spells_a_scope_outside_the_registry() -> None:
    offenders = {
        str(path.relative_to(ROOT)): literals
        for path in _production_files()
        if (literals := _scope_literals(path))
    }
    assert offenders == {}, (
        "Scope values are owned by argus.domain.job_scopes; import the "
        f"constant instead of spelling it: {offenders}"
    )


def test_the_registry_spells_each_scope_exactly_once() -> None:
    literals = [value for _, value in _scope_literals(REGISTRY)]
    assert sorted(literals) == sorted(OPERATION_SCOPES)
