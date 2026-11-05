from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_legacy_strategy_and_collection_routes_are_absent() -> None:
    openapi = yaml.safe_load(
        (ROOT / "docs" / "api" / "openapi.yaml").read_text(encoding="utf-8")
    )

    paths = openapi["paths"]
    assert not any(path.startswith("/api/v1/strategies") for path in paths)
    assert not any(path.startswith("/api/v1/collections") for path in paths)
    assert not (ROOT / "src" / "argus" / "api" / "routers" / "strategies.py").exists()
    assert not (ROOT / "src" / "argus" / "api" / "routers" / "collections.py").exists()


def test_legacy_rows_keep_read_compatibility_without_write_routes() -> None:
    schemas = (ROOT / "src" / "argus" / "api" / "schemas.py").read_text(
        encoding="utf-8"
    )
    history_reader = (
        ROOT / "src" / "argus" / "domain" / "postgres_history_reader.py"
    ).read_text(encoding="utf-8")
    gateway = (
        ROOT / "src" / "argus" / "domain" / "supabase_gateway.py"
    ).read_text(encoding="utf-8")

    assert "class Strategy(BaseModel):" in schemas
    assert "class Collection(BaseModel):" in schemas
    assert "strategy_id: str | None = None" in schemas
    assert "from public.strategies as strategy" in history_reader
    assert "from public.collections as collection" in history_reader
    assert "def get_strategy(" in gateway


def test_live_asset_provider_override_remains_untouched() -> None:
    assets = (
        ROOT / "src" / "argus" / "domain" / "market_data" / "assets.py"
    ).read_text(encoding="utf-8")

    assert "ARGUS_ASSET_PROVIDER_MODE" in assets
    assert "ARGUS_MARKET_DATA_PROVIDER_MODE" in assets
