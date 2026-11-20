from __future__ import annotations

from pathlib import Path

LEGACY_COMPOSER_PATH = Path("src/argus/agent_runtime/stages/compose.py")


def test_legacy_response_composer_is_retired() -> None:
    """Assistant voice belongs to LLM clarification or explicit recovery paths."""

    assert not LEGACY_COMPOSER_PATH.exists()
