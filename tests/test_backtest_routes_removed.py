"""The four backtest API routes are gone from the app and its OpenAPI document."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from argus.api.main import app
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
REMOVED_ROUTES = (
    ("POST", "/api/v1/backtests/run"),
    ("GET", "/api/v1/backtests/x"),
    ("GET", "/api/v1/backtest-jobs/x"),
    ("GET", "/api/v1/backtest-jobs/by-action/x"),
)
REMOVED_PREFIXES = ("/api/v1/backtests", "/api/v1/backtest-jobs")


@pytest.mark.parametrize(("method", "path"), REMOVED_ROUTES)
def test_removed_backtest_route_answers_not_found(method: str, path: str) -> None:
    response = TestClient(app).request(
        method, path, headers={"Authorization": "Bearer test-token"}
    )

    assert response.status_code == 404, response.text


def test_app_openapi_declares_no_backtest_paths() -> None:
    paths = app.openapi()["paths"]

    assert [path for path in paths if path.startswith(REMOVED_PREFIXES)] == []


def test_checked_openapi_artifact_declares_no_backtest_paths() -> None:
    artifact = yaml.safe_load(
        (ROOT / "docs" / "api" / "openapi.yaml").read_text(encoding="utf-8")
    )

    assert [path for path in artifact["paths"] if path.startswith(REMOVED_PREFIXES)] == []
