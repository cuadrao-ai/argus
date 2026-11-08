from __future__ import annotations

import os
import subprocess
import sys

import pytest

from tests.agent_runtime.test_shared_loop_import_boundary import REPO_ROOT

_BUSINESS_IMPORT_FIREWALL = (
    "import importlib,importlib.abc,sys\n"
    "F=('argus.domain.capability_registry','argus.domain.backtesting',"
    "'argus.domain.engine_launch','argus.agent_runtime.strategy_contract',"
    "'argus.domain.strategy_capabilities','argus.agent_runtime.tools.registered_backtest',"
    "'argus.domain.ingestion')\n"
    "class G(importlib.abc.MetaPathFinder):\n"
    " def find_spec(self,n,p=None,t=None):\n"
    "  if any(n==r or n.startswith(r+'.') for r in F): raise ImportError('firewall:'+n)\n"
    "sys.meta_path.insert(0,G());importlib.import_module(sys.argv[1])\n"
    "if sys.argv[1]=='argus.domain.business.tool_catalog':\n"
    " from argus.domain.business.tool_catalog import get_business_tool_catalog\n"
    " assert len(get_business_tool_catalog().declarations)==7\n"
    "for root in F:\n"
    " assert not any(m==root or m.startswith(root+'.') for m in sys.modules),root"
)

_BUSINESS_IMPORT_FIREWALL_MODULES = (
    "argus.domain.business.tool_catalog",
    "argus.agent_runtime.business.interpretation",
    "argus.agent_runtime.business.binding",
    "argus.agent_runtime.business.stages",
    "argus.domain.business.fact_blockers",
)


@pytest.mark.parametrize("module", _BUSINESS_IMPORT_FIREWALL_MODULES)
def test_business_modules_pass_import_firewall(module: str) -> None:
    completed = subprocess.run(
        [sys.executable, "-c", _BUSINESS_IMPORT_FIREWALL, module],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
