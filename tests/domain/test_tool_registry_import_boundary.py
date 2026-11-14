"""Tool declarations and their lifecycle stay usable without backtest bodies."""

from __future__ import annotations

import pytest

from tests.agent_runtime.test_shared_loop_import_boundary import _run_probe


@pytest.mark.parametrize(
    "module",
    (
        "argus.domain.tool_contracts",
        "argus.domain.tool_declaration",
        "argus.domain.tool_job_binding",
        "argus.domain.pending_artifacts",
    ),
)
def test_tool_contract_import_refuses_backtest_and_catalog_dependencies(module: str) -> None:
    # Reuse the existing fresh-process guard, including its network prohibition.
    _run_probe(module)


