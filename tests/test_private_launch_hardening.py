from __future__ import annotations

from argus.api import main
from argus.api.routers import dev as dev_router
from fastapi.testclient import TestClient


def test_cors_exposes_retry_after_and_request_id_to_allowed_origins() -> None:
    origin = main.cors_allow_origins()[0]
    client = TestClient(main.app)
    response = client.get("/health", headers={"Origin": origin})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    exposed = {
        name.strip().lower()
        for name in response.headers.get("access-control-expose-headers", "").split(",")
        if name.strip()
    }
    assert {"retry-after", "x-request-id"} <= exposed


def test_cors_allow_origins_include_configured_render_origins(monkeypatch) -> None:
    monkeypatch.setenv(
        "CUADRAO_CORS_ALLOW_ORIGINS",
        "https://argus-app-suz5.onrender.com, https://preview.argus.example",
    )

    origins = main.cors_allow_origins()

    assert "http://localhost:3000" in origins
    assert "https://argus-app-suz5.onrender.com" in origins
    assert "https://preview.argus.example" in origins


def test_http_errors_do_not_echo_unconfigured_cors_origins(monkeypatch) -> None:
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    monkeypatch.delenv("CUADRAO_CORS_ALLOW_ORIGINS", raising=False)
    monkeypatch.delenv("ARGUS_DEV_ENDPOINTS_ENABLED", raising=False)
    client = TestClient(main.app)

    response = client.post(
        "/api/v1/dev/reset",
        headers={"Origin": "https://unknown.example"},
    )

    assert response.status_code == 404
    assert "access-control-allow-origin" not in response.headers


def test_dev_reset_rejects_non_mock_launch_mode_without_explicit_flag(
    monkeypatch,
) -> None:
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    monkeypatch.delenv("ARGUS_DEV_ENDPOINTS_ENABLED", raising=False)
    monkeypatch.setattr(dev_router.api_state, "supabase_gateway", None)
    client = TestClient(main.app)

    response = client.post("/api/v1/dev/reset")

    assert response.status_code == 404


def test_dev_reset_allows_explicit_dev_endpoint_flag(monkeypatch) -> None:
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    monkeypatch.setenv("ARGUS_DEV_ENDPOINTS_ENABLED", "true")
    monkeypatch.setattr(dev_router.api_state, "supabase_gateway", None)
    client = TestClient(main.app)

    response = client.post("/api/v1/dev/reset")

    assert response.status_code == 200
