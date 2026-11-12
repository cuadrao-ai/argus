"""A facade re-exports its parts; it never re-implements them.

`confirmation` and `next_experiments` each keep the import path their callers
already hold while their code lives in modules beside them. Three things can
rot silently: a re-exported name can grow a second definition on the facade,
a name a caller imports can stop being re-exported, and an owner module can
gain a module-scope import of its facade and deadlock the pair. The expected
names are derived from what the repository actually imports, so no list here
goes stale.
"""

from __future__ import annotations

import ast
import importlib
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = ("src", "tests", "workflows")

FACADES: dict[str, tuple[str, ...]] = {
    "argus.agent_runtime.next_experiments": (
        "argus.agent_runtime.next_experiments_contract",
    ),
}

FACADE_CASES = sorted(
    (facade, owner) for facade, owners in FACADES.items() for owner in owners
)


def _names_imported_from(module_name: str) -> set[str]:
    names: set[str] = set()
    for root in SOURCE_ROOTS:
        for path in (REPO_ROOT / root).rglob("*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module == module_name:
                    names.update(alias.name for alias in node.names)
    return names


def _defined_names(module_name: str) -> set[str]:
    module = importlib.import_module(module_name)
    source = Path(module.__file__ or "").read_text(encoding="utf-8")
    names: set[str] = set()
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(
                target.id for target in node.targets if isinstance(target, ast.Name)
            )
    return names


@pytest.mark.parametrize(("facade_name", "owner_name"), FACADE_CASES)
def test_a_reexported_name_is_the_owner_s_own_object(
    facade_name: str, owner_name: str
) -> None:
    """One definition, reachable by two paths, never two definitions."""

    facade = importlib.import_module(facade_name)
    owner = importlib.import_module(owner_name)

    copies = [
        name
        for name in sorted(_defined_names(owner_name))
        if hasattr(facade, name) and getattr(facade, name) is not getattr(owner, name)
    ]
    assert not copies, (
        f"{facade_name} holds its own {copies} instead of re-exporting "
        f"{owner_name}'s. A facade that re-implements a name is the split brain "
        "the split removed."
    )


@pytest.mark.parametrize("facade_name", sorted(FACADES))
def test_the_facade_still_answers_every_name_the_repository_imports(
    facade_name: str,
) -> None:
    """Callers hold the facade's path; a missing re-export breaks them at import."""

    facade = importlib.import_module(facade_name)
    missing = sorted(
        name for name in _names_imported_from(facade_name) if not hasattr(facade, name)
    )
    assert not missing, f"{facade_name} no longer exports {missing}"


@pytest.mark.parametrize(("facade_name", "owner_name"), FACADE_CASES)
def test_an_owner_module_imports_alone(facade_name: str, owner_name: str) -> None:
    """The owner must not import its facade at module scope, in either order."""

    for first, second in ((owner_name, facade_name), (facade_name, owner_name)):
        completed = subprocess.run(
            [sys.executable, "-c", f"import {first}, {second}"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert (
            completed.returncode == 0
        ), f"importing {first} before {second} failed:\n{completed.stderr}"


