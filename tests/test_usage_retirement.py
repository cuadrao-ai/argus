"""The retired investing usage panel has no API surface."""

from argus.api.routers.profile import router
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_usage_endpoint_is_retired() -> None:
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).get("/api/v1/me/usage")
    assert response.status_code == 404
    assert "/api/v1/me/usage" not in app.openapi()["paths"]
