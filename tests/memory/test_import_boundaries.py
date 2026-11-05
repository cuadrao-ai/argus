from __future__ import annotations

import ast
import importlib
import pkgutil
import subprocess
import sys
from pathlib import Path

MEMORY_ROOT = Path("src/argus/memory")
SOURCE_ROOT = Path("src/argus")


def _imports_from_source(
    source: str, *, filename: str = "<memory-import-test>"
) -> tuple[str, ...]:
    tree = ast.parse(source, filename=filename)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.extend(f"{node.module}.{alias.name}" for alias in node.names)
    return tuple(imported)


def _imports(path: Path) -> tuple[str, ...]:
    return _imports_from_source(
        path.read_text(encoding="utf-8"),
        filename=str(path),
    )


def test_every_memory_module_imports_without_forbidden_runtime_dependencies() -> None:
    """Catches the isolated domain package loading shared runtime implementations."""
    script = """
import importlib
import pkgutil
import sys
import argus.memory as memory
for module in pkgutil.walk_packages(memory.__path__, prefix=f"{memory.__name__}."):
    importlib.import_module(module.name)
blocked = sorted(
    name for name in sys.modules
    if name == "argus.api" or name.startswith("argus.api.")
    or name == "argus.agent_runtime" or name.startswith("argus.agent_runtime.")
    or name == "argus.observability" or name.startswith("argus.observability.")
    or name == "supabase" or name.startswith("supabase.")
)
if blocked:
    raise SystemExit(",".join(blocked))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

    import argus.memory as memory

    loaded = tuple(
        importlib.import_module(module.name)
        for module in pkgutil.walk_packages(
            memory.__path__,
            prefix=f"{memory.__name__}.",
        )
    )
    assert loaded


def test_memory_modules_have_no_network_environment_or_shared_runtime_imports() -> None:
    """Catches later adapters leaking into the deterministic incubation package."""
    forbidden_roots = {
        "argus.api",
        "argus.agent_runtime",
        "argus.observability",
        "supabase",
        "requests",
        "httpx",
        "aiohttp",
        "urllib",
        "socket",
        "dotenv",
        "os",
    }
    # One deliberate exception: service.py reads a single default-off env var
    # (ARGUS_ENABLE_PERSONALIZATION_MEMORY) as this subsystem's own activation
    # kill switch. No other env, network, or shared-runtime coupling is allowed.
    allowed_env_imports = {("src/argus/memory/service.py", "os")}
    violations: list[tuple[str, str]] = []
    for path in sorted(MEMORY_ROOT.rglob("*.py")):
        for imported in _imports(path):
            if (str(path), imported) in allowed_env_imports:
                continue
            if any(
                imported == root or imported.startswith(f"{root}.")
                for root in forbidden_roots
            ):
                violations.append((str(path), imported))
    assert violations == []


def test_consumer_detection_covers_all_python_import_forms() -> None:
    """Catches `from argus import memory` escaping the no-consumer proof."""
    for source in (
        "import argus.memory\n",
        "from argus.memory import MemoryService\n",
        "from argus import memory\n",
    ):
        assert any(
            imported == "argus.memory" or imported.startswith("argus.memory.")
            for imported in _imports_from_source(source)
        )


AUTHORIZED_API_CONSUMERS = frozenset(
    {
        "src/argus/api/personalization_memory.py",
        "src/argus/api/personalization_memory_assessor.py",
        # Vendor client and env switches live in the composition layer.
        "src/argus/api/personalization_memory_index.py",
        "src/argus/api/personalization_memory_schemas.py",
        "src/argus/api/routers/personalization_memory.py",
    }
)


def test_only_authorized_api_modules_consume_argus_memory() -> None:
    """Catches incubation code gaining an unauthorized consumer before promotion.

    The registered-only API slice is the one authorized consumer seam; the
    runtime, interpreter, gateway, and every other production surface must
    still not import the memory package.
    """
    consumers: set[str] = set()
    unauthorized: list[tuple[str, str]] = []
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        if MEMORY_ROOT in path.parents:
            continue
        for imported in _imports(path):
            if imported == "argus.memory" or imported.startswith("argus.memory."):
                consumers.add(str(path))
                if str(path) not in AUTHORIZED_API_CONSUMERS:
                    unauthorized.append((str(path), imported))
    assert unauthorized == []
    assert consumers == set(AUTHORIZED_API_CONSUMERS)
