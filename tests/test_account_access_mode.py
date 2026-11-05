from __future__ import annotations

import pytest
from argus.api.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


@pytest.mark.parametrize(
    ("setting", "expected"),
    [(None, "invite_only"), ("false", "invite_only"), ("true", "open")],
)
def test_access_mode_is_public_and_follows_the_server_setting(
    monkeypatch: pytest.MonkeyPatch, setting: str | None, expected: str
) -> None:
    if setting is None:
        monkeypatch.delenv("CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED", raising=False)
    else:
        monkeypatch.setenv("CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED", setting)

    response = client.get("/api/v1/auth/access-mode")

    assert response.status_code == 200
    assert response.json() == {"access_mode": expected}
    assert response.headers["Cache-Control"] == "public, max-age=60"
