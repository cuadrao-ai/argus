from __future__ import annotations

from typing import Any

from argus.api.main import app
from fastapi import Request
from fastapi.testclient import TestClient


def test_internal_readiness_is_404_when_ops_token_missing(monkeypatch) -> None:
    monkeypatch.delenv("CUADRAO_OPS_TOKEN", raising=False)
    client = TestClient(app)

    response = client.get("/internal/readiness")

    assert response.status_code == 404


def test_internal_readiness_requires_matching_bearer_token(monkeypatch) -> None:
    monkeypatch.setenv("CUADRAO_OPS_TOKEN", "test-token")
    client = TestClient(app)

    response = client.get(
        "/internal/readiness",
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert response.status_code == 404


def test_internal_readiness_returns_safe_check_summary(monkeypatch) -> None:
    from argus.api.routers import ops

    async def _ready_checks(request: Request, *, force: bool) -> dict[str, Any]:
        del request
        assert force is True
        return {
            "status": "ready",
            "checks": [
                {"name": "supabase", "status": "ready", "duration_ms": 3},
                {"name": "asset_universe", "status": "ready", "duration_ms": 12},
            ],
        }

    monkeypatch.setenv("CUADRAO_OPS_TOKEN", "test-token")
    monkeypatch.setattr(ops, "run_readiness_checks", _ready_checks)
    client = TestClient(app)

    response = client.get(
        "/internal/readiness?force=true",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["checks"][0]["name"] == "supabase"
    assert "SUPABASE_SERVICE_ROLE_KEY" not in response.text
    assert "OPENROUTER_API_KEY" not in response.text
    assert "CUADRAO_PROD_OPENROUTER_API_KEY" not in response.text
    assert "CUADRAO_GUEST_ACCESS_OPENROUTER_API_KEY" not in response.text
    assert "ALPACA_SECRET_KEY" not in response.text


def test_internal_readiness_returns_503_when_any_check_is_degraded(monkeypatch) -> None:
    from argus.api.routers import ops

    async def _degraded_checks(request: Request, *, force: bool) -> dict[str, Any]:
        del request, force
        return {
            "status": "degraded",
            "checks": [
                {
                    "name": "asset_universe",
                    "status": "degraded",
                    "duration_ms": 25,
                }
            ],
        }

    monkeypatch.setenv("CUADRAO_OPS_TOKEN", "test-token")
    monkeypatch.setattr(ops, "run_readiness_checks", _degraded_checks)
    client = TestClient(app)

    response = client.get(
        "/internal/readiness",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
