"""The API and the document worker must not import the old investing stack."""

from __future__ import annotations

import ast
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANNED = frozenset(
    {
        "alpaca",
        "dateparser",
        "joblib",
        "numba",
        "numpy",
        "pandas",
        "pandas_ta_classic",
        "scipy",
        "sklearn",
        "vectorbt",
    }
)
ROOTS = (
    "argus.api.main",
    "workflows.document_worker",
    "workflows.document_job",
)


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(ROOT).parts)
    if parts[0] == "src":
        parts = parts[1:]
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)


def _imports(path: Path) -> tuple[set[str], set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    local: set[str] = set()
    third: set[str] = set()
    package = _module_name(path)
    if path.name != "__init__.py":
        package = package.rpartition(".")[0]

    def walk(node: ast.AST, type_checking: bool) -> None:
        if isinstance(node, ast.If):
            test = node.test
            name = test.id if isinstance(test, ast.Name) else None
            if name is None and isinstance(test, ast.Attribute):
                name = test.attr
            if name == "TYPE_CHECKING":
                for child in node.orelse:
                    walk(child, type_checking)
                return
        if type_checking:
            return
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in {"argus", "workflows"}:
                    local.add(alias.name)
                else:
                    third.add(top)
        elif isinstance(node, ast.ImportFrom) and (node.module or node.level):
            names = [alias.name for alias in node.names if alias.name != "*"]
            if node.level:
                parts = package.split(".") if package else []
                parts = parts[: len(parts) - (node.level - 1)]
                if node.module:
                    parts.extend(node.module.split("."))
                base = ".".join(parts)
                local.add(base)
                local.update(f"{base}.{name}" for name in names)
            elif node.module:
                top = node.module.split(".")[0]
                if top in {"argus", "workflows"}:
                    local.add(node.module)
                    local.update(f"{node.module}.{name}" for name in names)
                else:
                    third.add(top)
        for child in ast.iter_child_nodes(node):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                walk(child, type_checking)

    walk(tree, False)
    return local, third


def _graph() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    files = list((ROOT / "src").rglob("*.py")) + list((ROOT / "workflows").rglob("*.py"))
    modules = {_module_name(path): _imports(path) for path in files}

    def resolve(edge: str) -> str | None:
        if edge in modules:
            return edge
        parent = edge
        while "." in parent:
            parent = parent.rpartition(".")[0]
            if parent in modules:
                return parent
        return None

    graph = {name: set() for name in modules}
    banned = {name: third & BANNED for name, (_, third) in modules.items()}
    for name, (local, _) in modules.items():
        for edge in local:
            target = resolve(edge)
            if target is not None and target != name:
                graph[name].add(target)
    return graph, banned


def test_api_and_document_worker_do_not_import_investing_packages() -> None:
    graph, banned = _graph()
    failures: list[str] = []
    for root in ROOTS:
        assert root in graph, root
        seen: set[str] = set()
        pending: deque[str] = deque([root])
        while pending:
            current = pending.popleft()
            if current in seen:
                continue
            seen.add(current)
            found = banned[current]
            if found:
                failures.append(f"{root} reaches {current} importing {sorted(found)}")
            pending.extend(sorted(graph[current] - seen))
    assert failures == []
