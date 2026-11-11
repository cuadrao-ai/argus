"""Unhandled server exceptions reach the analytics project without their message."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from argus.api.dependencies import request_id_middleware
from argus.domain.ingestion.documents import jobs
from argus.observability import envelope
from argus.observability.product_events import actor_hash_for_user
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.money_assertions import _assert_no_money_properties


class Inline:
    def submit(self, fn) -> None:  # noqa: ANN001
        fn()


@pytest.fixture
def posts(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    bodies: list[dict[str, Any]] = []

    def fake_post(url: str, *, json: dict[str, Any], timeout: float) -> httpx.Response:
        bodies.append(json)
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setenv("POSTHOG_PROJECT_TOKEN", "ph_project_token")
    monkeypatch.setenv("POSTHOG_REGION", "us")
    monkeypatch.setattr(envelope.httpx, "post", fake_post)
    monkeypatch.setattr(envelope, "_SENDER", Inline())
    return bodies


def _app() -> FastAPI:
    app = FastAPI()
    app.middleware("http")(request_id_middleware)

    @app.post("/business/receipts/{receipt_id}")
    def explode(receipt_id: str) -> None:
        rnc, email, amount = "101010101", "jose@example.com", "RD$3,450.00"
        raise ValueError(f"RNC {rnc} {email} {amount} for receipt {receipt_id}")

    return app


def test_an_unhandled_api_error_sends_its_class_route_and_frames_only(
    posts: list[dict[str, Any]],
) -> None:
    client = TestClient(_app(), raise_server_exceptions=False)

    answer = client.post(
        "/business/receipts/7f0d",
        json={"note": "RNC 101010101"},
        headers={"x-request-id": "r1"},
    )

    assert answer.status_code == 500
    assert answer.json()["code"] == "internal_error"
    [body] = posts
    properties = body["properties"]
    assert properties["route"] == "/business/receipts/{receipt_id}"
    [entry] = properties["$exception_list"]
    assert entry["type"] == "ValueError"
    assert entry["stacktrace"]["frames"][-1]["function"] == "explode"
    assert body["distinct_id"] == envelope.SERVER_DISTINCT_ID
    sent = json.dumps(body)
    for value in (
        "101010101",
        "jose@example.com",
        "RNC",
        "7f0d",
        "note",
    ):
        assert value not in sent
    _assert_no_money_properties(body["properties"], "3450")
    for entry in body["properties"]["$exception_list"]:
        assert set(entry) == {"type", "stacktrace"}


def test_an_api_error_with_no_token_sends_nothing_and_still_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POSTHOG_PROJECT_TOKEN", "")
    monkeypatch.setattr(envelope, "_SENDER", Inline())
    sent: list[object] = []
    monkeypatch.setattr(envelope.httpx, "post", lambda *a, **k: sent.append(a))
    client = TestClient(_app(), raise_server_exceptions=False)

    answer = client.post("/business/receipts/1", headers={"x-request-id": "r2"})

    assert answer.status_code == 500
    assert sent == []


def test_an_api_error_survives_a_down_analytics_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POSTHOG_PROJECT_TOKEN", "ph_project_token")
    monkeypatch.setenv("POSTHOG_REGION", "us")
    monkeypatch.setattr(envelope, "_SENDER", Inline())

    def down(*_: object, **__: object) -> httpx.Response:
        raise httpx.ConnectError("down")

    monkeypatch.setattr(envelope.httpx, "post", down)
    client = TestClient(_app(), raise_server_exceptions=False)

    answer = client.post("/business/receipts/1", headers={"x-request-id": "r3"})

    assert answer.status_code == 500
    assert answer.json()["code"] == "internal_error"


def test_an_unhandled_read_error_sends_the_job_and_the_hashed_owner(
    posts: list[dict[str, Any]],
) -> None:
    class Service:
        store = SimpleNamespace(owner=lambda connection_id: "owner-raw-id")
        hub = SimpleNamespace(
            connections=SimpleNamespace(
                get_any_scope=lambda **_: SimpleNamespace(scope=None)
            )
        )

        async def resume(self, **_: object) -> None:
            raise RuntimeError("RNC 101010101 jose@example.com RD$3,450.00")

    outcome = asyncio.run(jobs.run_attempt(Service(), "connection-1", "attempt-1"))

    assert outcome == "document_extraction_failed"
    [body] = posts
    assert body["properties"]["job"] == "document_preparation"
    assert body["distinct_id"] == actor_hash_for_user("owner-raw-id")
    sent = json.dumps(body)
    for value in ("101010101", "jose@example.com", "owner-raw-id"):
        assert value not in sent
    _assert_no_money_properties(body["properties"], "3450")
    for entry in body["properties"]["$exception_list"]:
        assert set(entry) == {"type", "stacktrace"}
