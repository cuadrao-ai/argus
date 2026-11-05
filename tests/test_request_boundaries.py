"""Contract test for the unexpected-error boundary (#235)."""

from __future__ import annotations

from typing import Any

import pytest
from argus.api.dependencies import current_user
from argus.api.main import app
from fastapi import Request
from fastapi.testclient import TestClient
from loguru import logger


def test_unexpected_error_is_generic_correlated_and_cors_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records: list[dict[str, Any]] = []

    async def _boom(_request: Request) -> None:
        raise RuntimeError("provider credential private failure detail")

    sink_id = logger.add(lambda message: records.append(message.record), level="ERROR")
    monkeypatch.setitem(app.dependency_overrides, current_user, _boom)
    try:
        response = TestClient(app, raise_server_exceptions=False).get(
            "/api/v1/me",
            headers={
                "Origin": "http://localhost:3000",
                "X-Request-Id": "unexpected-request-id",
            },
        )
    finally:
        logger.remove(sink_id)

    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.headers["x-request-id"] == "unexpected-request-id"
    assert response.json() == {
        "type": "https://api.argus.app/problems/internal-error",
        "title": "Internal Error",
        "status": 500,
        "detail": "An unexpected error occurred. Please try again.",
        "code": "internal_error",
        "request_id": "unexpected-request-id",
    }
    assert "private failure detail" not in response.text
    matching_records = [
        record
        for record in records
        if record["extra"].get("request_id") == "unexpected-request-id"
    ]
    assert len(matching_records) == 1
    record = matching_records[0]
    assert "private failure detail" not in record["message"]
    assert record["exception"] is not None
    assert record["exception"].type is RuntimeError
    assert str(record["exception"].value) == "provider credential private failure detail"
