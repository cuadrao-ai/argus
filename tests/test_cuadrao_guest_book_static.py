"""Static guards for the on-device guest book package (native/Packages/CuadraoBook).

They protect one promise without a Swift toolchain: the package stays dependency
free and imports Foundation only.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "native/Packages/CuadraoBook"


def test_package_declares_no_dependencies():
    manifest = (PACKAGE / "Package.swift").read_text()
    assert ".package(" not in manifest
    for match in re.finditer(r"dependencies:\s*(\[[^\]]*\])", manifest):
        assert match.group(1) == '["CuadraoBook"]', "only the test target may depend on the book itself"


def test_package_sources_import_foundation_only():
    for source in (PACKAGE / "Sources/CuadraoBook").glob("*.swift"):
        imports = [line for line in source.read_text().splitlines() if line.startswith("import ")]
        assert all(line == "import Foundation" for line in imports), (source.name, imports)
