"""Collect tests twice in fresh processes and reject unstable test identities."""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def generated_parameter_lines(source: str) -> list[int]:
    """Reject generated auto IDs even when another module seeds the generator.

    This deliberately checks local expressions, not arbitrary helper execution.
    Collection comparison still covers dynamic IDs and custom ID functions.
    """
    tree = ast.parse(source)
    bindings: dict[str, ast.expr] = {}
    imports: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imports[alias.asname or alias.name] = f"{node.module}.{alias.name}"
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    bindings[target.id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.value is not None:
                bindings[node.target.id] = node.value

    def resolve(node: ast.expr, seen: frozenset[str] = frozenset()) -> ast.expr:
        if isinstance(node, ast.Name) and node.id in bindings and node.id not in seen:
            return resolve(bindings[node.id], seen | {node.id})
        return node

    def origin(node: ast.expr, seen: frozenset[str] = frozenset()) -> str:
        if isinstance(node, ast.Name):
            if node.id in bindings and node.id not in seen:
                return origin(bindings[node.id], seen | {node.id})
            return imports.get(node.id, "")
        if isinstance(node, ast.Attribute):
            return f"{origin(node.value, seen)}.{node.attr}"
        if isinstance(node, ast.Call):
            return f"{origin(node.func, seen)}()"
        return ""

    def generated(node: ast.expr) -> bool:
        node = resolve(node)
        # Pytest uses the argument name/index for container values, not their contents.
        if isinstance(node, (ast.Dict, ast.List, ast.Tuple, ast.Set)):
            return False
        return any(
            isinstance(child, ast.Call)
            and origin(child.func).startswith(("faker.", "random."))
            for child in ast.walk(node)
        )

    failures = []
    for node in ast.walk(tree):
        if (
            not isinstance(node, ast.Call)
            or origin(node.func) != "pytest.mark.parametrize"
        ):
            continue
        keywords = {item.arg: item.value for item in node.keywords}
        explicit_ids = keywords.get("ids", node.args[3] if len(node.args) > 3 else None)
        if (
            explicit_ids is not None
            and not isinstance(explicit_ids, (ast.List, ast.Tuple))
            and not (
                isinstance(explicit_ids, ast.Constant) and explicit_ids.value is None
            )
        ):
            # Callable and other dynamic ID expressions keep collection comparison.
            continue
        names = node.args[0] if node.args else keywords.get("argnames")
        values = node.args[1] if len(node.args) > 1 else keywords.get("argvalues")
        if names is None or values is None:
            continue
        names, values = resolve(names), resolve(values)
        unpack_row = (
            len([name for name in names.value.split(",") if name.strip()]) != 1
            if isinstance(names, ast.Constant) and isinstance(names.value, str)
            else isinstance(names, (ast.List, ast.Tuple))
        )
        if isinstance(values, (ast.List, ast.Tuple, ast.Set)):
            rows = values.elts
        elif isinstance(values, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            rows = [values.elt]
        else:
            rows = [values]
        for index, row in enumerate(rows):
            if isinstance(explicit_ids, (ast.List, ast.Tuple)):
                entries = explicit_ids.elts
                if isinstance(values, (ast.List, ast.Tuple)) and not any(
                    isinstance(value, ast.Starred) for value in values.elts
                ):
                    entries = entries[index : index + 1]
                # Expanded/unordered rows require every supplied ID to be explicit;
                # collection still checks that a nonempty IDs list has the right length.
                if entries and all(
                    isinstance(entry, ast.Constant) and isinstance(entry.value, str)
                    for entry in entries
                ):
                    continue
            row = resolve(row)
            if isinstance(row, ast.Call) and origin(row.func) == "pytest.param":
                if any(
                    item.arg == "id"
                    and isinstance(item.value, ast.Constant)
                    and isinstance(item.value.value, str)
                    for item in row.keywords
                ):
                    continue
                parameters = row.args
            elif unpack_row and isinstance(row, (ast.List, ast.Tuple)):
                parameters = row.elts
            else:
                parameters = [row]
            if any(generated(parameter) for parameter in parameters):
                failures.append(node.lineno)
                break
    return failures


def check_generated_parameters(paths: list[str]) -> None:
    failures = []
    for raw_path in paths:
        path = Path(raw_path.split("::", 1)[0])
        files = sorted(path.rglob("test_*.py")) if path.is_dir() else [path]
        for file in files:
            if file.is_file() and file.suffix == ".py":
                for line in generated_parameter_lines(file.read_text(encoding="utf-8")):
                    failures.append(f"{file}:{line}")
    if failures:
        raise ValueError(
            "Generated parameter values require stable explicit parameter IDs "
            "(ids= or pytest.param(id=)):\n" + "\n".join(failures)
        )


def collect(paths: list[str], output: Path, attempt: int) -> list[str]:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *paths,
            "--collect-only",
            "-q",
            "-o",
            "addopts=",
            "-p",
            "scripts.ci.pytest_inventory",
            f"--ci-inventory={output}",
            "--ci-shard-count=1",
            "--ci-shard-index=0",
        ],
        cwd=ROOT,
        env={**os.environ, "PYTEST_ADDOPTS": ""},
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode:
        detail = (result.stdout + result.stderr)[-2000:]
        raise ValueError(f"Collection {attempt} failed ({result.returncode}):\n{detail}")
    evidence = json.loads(output.read_text(encoding="utf-8"))
    if evidence["exitstatus"] != 0 or evidence["collection_errors"]:
        raise ValueError(f"Collection {attempt} failed")
    if evidence["deselected"] or evidence["sharded_out"]:
        raise ValueError(f"Collection {attempt} unexpectedly deselected tests")
    nodeids = evidence["full_nodeids"]
    if not nodeids:
        raise ValueError(f"Collection {attempt} is empty")
    if len(set(nodeids)) != len(nodeids):
        raise ValueError(f"Collection {attempt} contains duplicate test IDs")
    return nodeids


def check(paths: list[str]) -> int:
    check_generated_parameters(paths)
    with tempfile.TemporaryDirectory(prefix="test-id-collection-") as directory:
        work = Path(directory)
        first = collect(paths, work / "first.json", 1)
        second = collect(paths, work / "second.json", 2)
    if Counter(first) != Counter(second):
        removed = sorted(set(first) - set(second))
        added = sorted(set(second) - set(first))
        raise ValueError(
            "Test IDs differ between collections. Use stable explicit parameter IDs.\n"
            f"Only in first ({len(removed)}): {json.dumps(removed[:10])}\n"
            f"Only in second ({len(added)}): {json.dumps(added[:10])}"
        )
    return len(first)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", default=["tests"])
    args = parser.parse_args()
    try:
        count = check(args.paths)
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, f"Test ID stability check failed: {exc}\n")
    sys.stdout.write(f"Stable test IDs: {count} across two collections\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
