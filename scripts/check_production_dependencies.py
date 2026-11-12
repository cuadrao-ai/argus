"""Audit removed dependencies, including deferred imports and package initializers.

This conservative module graph includes every function body, not just functions
called at boot. It excludes TYPE_CHECKING bodies. Computed dynamic imports are
reported as errors because their targets cannot be established statically.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections import deque
from dataclasses import asdict, dataclass
from importlib.util import resolve_name
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = {
    "alpaca-py": "alpaca",
    "dateparser": "dateparser",
    "joblib": "joblib",
    "numba": "numba",
    "pandas": "pandas",
    "pandas-ta-classic": "pandas_ta_classic",
    "vectorbt": "vectorbt",
}
IMPORT_ALIASES = {
    "fonttools": "fontTools",
    "ipython": "IPython",
    "scikit-learn": "sklearn",
}
BASELINE = "origin/codex/private-alpha-next"
ENTRY_POINTS = (
    "argus.api.main",
    "workflows.document_worker",
    "workflows.document_job",
)
SMOKE_ENTRY_POINT = "argus.api.chat.backtest_jobs"


@dataclass(frozen=True)
class ImportUse:
    module: str
    target: str
    path: str
    line: int


def module_name(path: Path, root: Path) -> str:
    parts = list(path.relative_to(root).with_suffix("").parts)
    if parts[0] == "src":
        parts.pop(0)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def imports(path: Path, root: Path) -> list[ImportUse]:
    module = module_name(path, root)
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    result: list[ImportUse] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    dynamic_names = {"__import__", "importlib.import_module"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "importlib":
                    dynamic_names.add(f"{alias.asname or alias.name}.import_module")
        if isinstance(node, ast.ImportFrom) and node.module == "importlib":
            for alias in node.names:
                if alias.name == "import_module":
                    dynamic_names.add(alias.asname or alias.name)

    def add(target: str, line: int) -> None:
        result.append(ImportUse(module, target, str(path.relative_to(root)), line))

    def walk(node: ast.AST) -> None:
        if isinstance(node, ast.If) and ast.unparse(node.test) in {
            "TYPE_CHECKING",
            "typing.TYPE_CHECKING",
        }:
            for child in node.orelse:
                walk(child)
            return
        if isinstance(node, ast.Import):
            for alias in node.names:
                add(alias.name, node.lineno)
        elif isinstance(node, ast.ImportFrom):
            target = node.module or ""
            if node.level:
                target = resolve_name("." * node.level + target, package)
            add(target, node.lineno)
            for alias in node.names:
                if alias.name != "*":
                    add(f"{target}.{alias.name}", node.lineno)
        elif isinstance(node, ast.Call) and ast.unparse(node.func) in dynamic_names:
            if node.args and isinstance(node.args[0], ast.Constant):
                target = node.args[0].value
                if isinstance(target, str) and not target.startswith("."):
                    add(target, node.lineno)
                else:
                    add("<dynamic>", node.lineno)
            else:
                add("<dynamic>", node.lineno)
        for child in ast.iter_child_nodes(node):
            walk(child)

    walk(tree)
    return result


def import_graph(root: Path) -> tuple[dict[str, set[str]], list[ImportUse]]:
    files = sorted((root / "src").rglob("*.py")) + sorted(
        (root / "workflows").rglob("*.py")
    )
    graph = {module_name(path, root): set() for path in files}
    uses = [use for path in files for use in imports(path, root)]

    def targets(name: str) -> set[str]:
        parts = name.split(".")
        return {
            candidate
            for count in range(1, len(parts) + 1)
            if (candidate := ".".join(parts[:count])) in graph
        }

    for name in graph:
        graph[name].update(targets(name) - {name})
    for use in uses:
        graph[use.module].update(targets(use.target) - {use.module})
    return graph, uses


def import_paths(graph: dict[str, set[str]], entry: str) -> dict[str, list[str]]:
    if entry not in graph:
        raise ValueError(f"Missing production entry point: {entry}")
    paths = {entry: [entry]}
    pending = deque([entry])
    while pending:
        current = pending.popleft()
        for target in sorted(graph[current] - paths.keys()):
            paths[target] = [*paths[current], target]
            pending.append(target)
    return paths


def production_dependencies(text: str) -> set[str]:
    section = text.split("[tool.poetry.dependencies]", 1)[1].split("\n[", 1)[0]
    return set(re.findall(r"^([A-Za-z0-9_-]+)\s*=", section, re.MULTILINE))


def locked_production_packages(text: str) -> set[str]:
    return {
        match.group(1)
        for package in text.split("[[package]]")[1:]
        if re.search(r'^groups = .*"main"', package, re.MULTILINE)
        if (match := re.search(r'^name = "([^"]+)"$', package, re.MULTILINE))
    }


def removed_packages(root: Path, baseline: str) -> set[str]:
    def previous(path: str) -> str:
        return subprocess.check_output(
            ["git", "show", f"{baseline}:{path}"], cwd=root, text=True
        )

    previous_direct = production_dependencies(previous("pyproject.toml"))
    current_direct = production_dependencies((root / "pyproject.toml").read_text())
    previous_locked = locked_production_packages(previous("poetry.lock"))
    current_locked = locked_production_packages((root / "poetry.lock").read_text())
    return (previous_direct - current_direct) | (previous_locked - current_locked)


def audit(
    root: Path = ROOT, baseline: str = BASELINE
) -> tuple[list[dict[str, object]], list[str]]:
    graph, uses = import_graph(root)
    paths = {entry: import_paths(graph, entry) for entry in ENTRY_POINTS}
    smoke_paths = import_paths(graph, SMOKE_ENTRY_POINT)
    installed = production_dependencies((root / "pyproject.toml").read_text())
    candidates = {
        name: IMPORT_ALIASES.get(name, name.replace("-", "_"))
        for name in removed_packages(root, baseline)
    }
    candidates.update(PACKAGES)
    rows: list[dict[str, object]] = []
    failures: list[str] = []
    for package, imported_name in sorted(candidates.items()):
        direct = sorted(
            {use for use in uses if use.target.split(".")[0] == imported_name},
            key=lambda use: (use.path, use.line, use.target),
        )
        reachable = [
            {**asdict(use), "entry_point": entry, "chain": chains[use.module]}
            for use in direct
            for entry, chains in paths.items()
            if use.module in chains
        ]
        smoke = [
            {**asdict(use), "chain": smoke_paths[use.module]}
            for use in direct
            if use.module in smoke_paths
        ]
        kept = package in installed
        if reachable and not kept:
            failures.append(f"{package} is absent but production reaches its imports")
        rows.append(
            {
                "package": package,
                "kind": "direct" if package in PACKAGES else "transitive",
                "disposition": "kept" if kept else "removed",
                "direct_imports": [asdict(use) for use in direct],
                "production_imports": reachable,
                "smoke_imports": smoke,
            }
        )
    for use in uses:
        if use.target == "<dynamic>" and any(use.module in p for p in paths.values()):
            failures.append(f"Unresolved dynamic import at {use.path}:{use.line}")
    return rows, failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default=BASELINE)
    args = parser.parse_args()
    rows, failures = audit(baseline=args.baseline)
    sys.stdout.write(
        json.dumps({"packages": rows, "failures": failures}, indent=2) + "\n"
    )
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
