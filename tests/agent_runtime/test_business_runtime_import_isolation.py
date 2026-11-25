from __future__ import annotations

import os
import subprocess
import sys
from uuid import uuid4

import pytest
from argus.domain.business.tool_catalog import get_business_tool_catalog
from argus.domain.capability_registry import get_tool_catalog

from tests.agent_runtime.test_shared_loop_import_boundary import REPO_ROOT

_BUSINESS_IMPORT_FIREWALL = (
    "import importlib,importlib.abc,sys\n"
    "F=('argus.domain.capability_registry','argus.domain.strategy_capabilities',"
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


def test_business_catalogue_excludes_personal_tools_and_approval():
    business = get_business_tool_catalog(surface="business")
    registry = get_tool_catalog(surface="business")
    assert business.capability_text() == registry.capability_text()
    personal = get_tool_catalog()
    assert all(
        declaration.surfaces == {"business"} for declaration in business.declarations
    )
    assert not {d.name for d in business.declarations} & {
        d.name for d in personal.declarations
    }
    assert all("approv" not in d.name for d in business.declarations)


def test_business_tool_arguments_cannot_supply_authority_or_approval():
    catalog = get_business_tool_catalog()
    declaration = catalog.get("business_read_context")
    for field in ("actor_id", "space_id", "grant_id", "approve"):
        with pytest.raises(ValueError):
            declaration.validate_arguments({field: str(uuid4())})
