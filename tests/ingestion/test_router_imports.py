"""Every ingestion router imports on its own, in a fresh interpreter, so tests,
tooling and other app compositions do not depend on the main app's order."""

import os
import subprocess
import sys

import pytest

ROUTERS = [
    "argus.api.routers.financial_connections_plaid",
    "argus.api.routers.financial_connections_gmail",
    "argus.api.routers.ingestion_shortcuts",
    "argus.api.routers.financial_connections",
    "argus.api.routers.financial_connections_schemas",
    "argus.api.routers.financial_imports",
]


@pytest.mark.parametrize("module", ROUTERS)
def test_router_imports_in_a_fresh_process(module: str) -> None:
    done = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
        text=True,
        timeout=120,
        # The same import path as this test run (worktrees, editable installs).
        env={**os.environ, "PYTHONPATH": os.pathsep.join(p for p in sys.path if p)},
    )
    assert done.returncode == 0, done.stderr[-2000:]
