from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SETUP_SH_PATH = ROOT / ".github" / "setup.sh"
INTEGRATION_SPEC_PATH = ROOT / "docs" / "specs" / "private-alpha-next-integration.md"


def test_setup_sh_is_executable_and_has_correct_commands() -> None:
    assert SETUP_SH_PATH.exists(), "setup.sh is missing"
    assert os.access(SETUP_SH_PATH, os.X_OK), "setup.sh is not executable"

    content = SETUP_SH_PATH.read_text(encoding="utf-8")

    assert "poetry install --with dev,workflows --no-interaction" in content
    assert "poetry sync --with dev,workflows --no-interaction" in content
    assert "bun install --frozen-lockfile" in content


def test_integration_spec_has_correct_branch_model() -> None:
    assert INTEGRATION_SPEC_PATH.exists(), "Integration spec is missing"

    content = INTEGRATION_SPEC_PATH.read_text(encoding="utf-8")
    content_lower = content.lower()

    # Assert presence of required branches
    assert "codex/private-alpha-next" in content
    assert "codex/private-alpha-next-jules-intake" in content
    assert "jules/**" in content

    # Assert prohibition against pushing directly to main
    assert re.search(r"do not push.*main", content_lower, re.DOTALL) is not None
