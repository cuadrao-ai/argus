from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _imports_symbol(source_path: Path, *, module: str, symbol: str) -> bool:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    module_aliases = {module}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == module:
                    module_aliases.add(alias.asname or alias.name)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            if any(alias.name == symbol for alias in node.names):
                return True
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in module_aliases and node.attr == symbol:
                return True
    return False


def test_import_detector_catches_module_attribute_references(tmp_path: Path) -> None:
    source_path = tmp_path / "uses_strenum.py"
    source_path.write_text("import enum as enum_module\nenum_module.StrEnum\n", encoding="utf-8")

    assert _imports_symbol(source_path, module="enum", symbol="StrEnum")
