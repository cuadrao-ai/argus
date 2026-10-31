from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _name(*parts: str) -> str:
    return "".join(parts)


def _module_path(*parts: str) -> str:
    return "_".join(parts)


def _source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_domain_orchestrator_is_deleted() -> None:
    assert not (ROOT / "src/argus/domain/orchestrator.py").exists()


def test_api_main_has_no_legacy_orchestrator_wiring() -> None:
    source = _source("src/argus/api/main.py")

    banned_fragments = [
        _name("Backtest", "Conversation", "State"),
        "from argus.domain." + _module_path("backtest", "state", "machine"),
        _name("orchestrate_chat", "_turn"),
        _name("_latest_backtest", "_state"),
        _name("_state_has", "_params"),
        _name("_latest_completed", "_run_id"),
        _name("parse_onboarding", "_goal"),
        "from argus.domain.orchestrator import " + _name("_resolve", "_language"),
    ]
    for fragment in banned_fragments:
        assert fragment not in source

    naming = _source("src/argus/api/naming.py")
    assert "def get_starter_prompts" in naming
    assert "def suggest_entity_name" in naming


def test_legacy_state_module_is_retired() -> None:
    retired_path = (
        ROOT / "src/argus/domain" / (_module_path("backtest", "state", "machine") + ".py")
    )

    assert not retired_path.exists()


def test_chat_service_facade_is_retired() -> None:
    retired_path = ROOT / "src/argus/api/chat_service.py"

    assert not retired_path.exists()
    assert importlib.util.find_spec("argus.api.chat_service") is None


def test_launch_code_and_tests_do_not_import_chat_service_facade() -> None:
    scanned_paths = [
        path
        for root in ("src/argus", "tests")
        for path in (ROOT / root).rglob("*.py")
        if path.name != "chat_service.py"
    ]

    for path in scanned_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_names = {alias.name for alias in node.names}
                assert "argus.api.chat_service" not in imported_names
            if isinstance(node, ast.ImportFrom):
                if node.module == "argus.api":
                    imported_names = {alias.name for alias in node.names}
                    assert "chat_service" not in imported_names
                assert node.module != "argus.api.chat_service"
