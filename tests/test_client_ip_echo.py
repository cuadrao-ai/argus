from __future__ import annotations

import pytest
from argus.api.main import app
from argus.api.ops_contract import CLIENT_IP_ECHO_PATH
from argus.api.routers.internal_client_ip import CLIENT_IP_ECHO_ENV
from fastapi.testclient import TestClient

TOKEN = "ops-token-for-client-ip-echo"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
FORGED = {
    "CF-Connecting-IP": "203.0.113.7",
    "True-Client-IP": "203.0.113.8",
    "X-Forwarded-For": "203.0.113.9",
}


def _without_request_ids(body: dict[str, object]) -> dict[str, object]:
    return {k: v for k, v in body.items() if "id" not in k.lower()}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARGUS_OPS_TOKEN", TOKEN)
    monkeypatch.delenv(CLIENT_IP_ECHO_ENV, raising=False)
    return TestClient(app)


def test_echo_is_off_by_default_even_with_the_ops_token(client: TestClient) -> None:
    response = client.get(CLIENT_IP_ECHO_PATH, headers=AUTH)
    assert response.status_code == 404


def test_echo_answers_the_same_404_without_the_ops_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CLIENT_IP_ECHO_ENV, "true")
    off = client.get(CLIENT_IP_ECHO_PATH, headers={"Authorization": "Bearer wrong"})
    none = client.get(CLIENT_IP_ECHO_PATH)
    assert off.status_code == none.status_code == 404
    assert _without_request_ids(off.json()) == _without_request_ids(none.json())


def test_echo_reports_what_the_resolver_chose_and_what_was_forged(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CLIENT_IP_ECHO_ENV, "true")
    response = client.get(CLIENT_IP_ECHO_PATH, headers={**AUTH, **FORGED})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["resolved_client_ip"] == "203.0.113.7"
    assert body["trusted_header"] == "CF-Connecting-IP"
    assert body["headers"]["true-client-ip"] == "203.0.113.8"
    assert body["headers"]["x-forwarded-for"] == "203.0.113.9"
    assert set(body) == {"resolved_client_ip", "trusted_header", "socket_peer", "headers"}


def test_echo_is_not_published_in_the_openapi_document(client: TestClient) -> None:
    assert CLIENT_IP_ECHO_PATH not in client.get("/openapi.json").json()["paths"]
