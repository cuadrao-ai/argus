from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_api_main_is_only_app_entrypoint() -> None:
    source = _source("src/argus/api/main.py")

    assert "include_router(" in source
    assert "from argus.api.routers import" in source
    assert '@app.post("/api/v1/chat/stream")' not in source
    assert '@app.post("/api/v1/backtests/run")' not in source
    assert '@app.post("/api/v1/strategies")' not in source
    assert '@app.post("/api/v1/collections")' not in source
    assert '@app.post("/api/v1/conversations")' not in source
    assert "from argus.domain.orchestrator" not in source
    assert len(source.splitlines()) <= 180


def test_required_api_router_modules_exist() -> None:
    required = [
        "auth",
        "profile",
        "business_conversations",
        "history",
        "search",
        "feedback",
        "dev",
    ]
    for name in required:
        path = ROOT / "src" / "argus" / "api" / "routers" / f"{name}.py"
        assert path.exists(), f"missing router {name}"
        assert "router = APIRouter(" in path.read_text(encoding="utf-8")

    for retired_name in (
        "strategies",
        "collections",
        "backtest",
        "conversations",
        "computations",
        "decisions",
        "discovery",
        "evidence",
        "evidence_receipts",
        "market",
        "public_receipts",
        "receipt_forks",
        "tool_results",
    ):
        retired_path = ROOT / "src" / "argus" / "api" / "routers" / f"{retired_name}.py"
        assert not retired_path.exists()


def test_shared_dependencies_are_not_in_main() -> None:
    main = _source("src/argus/api/main.py")
    dependencies = _source("src/argus/api/dependencies.py")

    assert "def current_user" not in main
    assert "def problem" not in main
    assert "def current_user" in dependencies
    assert "def problem" in dependencies


def test_legacy_orchestrator_file_is_deleted() -> None:
    assert not (ROOT / "src" / "argus" / "domain" / "orchestrator.py").exists()
    assert importlib.util.find_spec("argus.domain.orchestrator") is None


def test_legacy_signal_parser_package_is_deleted() -> None:
    signals_path = ROOT / "src" / "argus" / "agent_runtime" / "signals"
    assert not (signals_path / "__init__.py").exists()
    assert not (signals_path / "task_relation.py").exists()
    assert list(signals_path.glob("*.py")) == []
