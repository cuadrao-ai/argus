from types import SimpleNamespace
from uuid import uuid4

import pytest
from argus.api.business_drafts import require_drafts
from argus.api.fiscal_operations import require_fiscal
from argus.api.routers.business_fiscal_operations import router
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests import test_financial_accounts_postgres as shared
from tests.fiscal import conftest as fixtures

users = fixtures.users
case_factory = fixtures.case_factory
lane = fixtures.lane

pytestmark = pytest.mark.skipif(not shared.DSN, reason="Disposable database required")


@pytest.fixture
def client(lane):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[require_fiscal] = lambda: lane.service
    app.dependency_overrides[require_drafts] = lambda: SimpleNamespace(
        actor_id=lane.owner.actor_id,
        space_id=str(lane.case.business_id),
        grant_id=lane.grant,
    )
    with TestClient(app) as client:
        yield client


def test_backend_workflow_no_private_urls(client, lane):
    response = client.post(
        "/api/v1/business/fiscal-operations", json={"case_id": lane.case.case_id}
    )
    assert response.status_code == 201
    assert "no-store" in response.headers["cache-control"]
    operation = response.json()
    response = client.post(
        f"/api/v1/business/fiscal-operations/{operation['id']}/submit",
        json={"payload_digest": operation["payload_digest"]},
    )
    assert response.status_code == 202
    assert response.json()["state"]["legal"] == "ACCEPTED"
    assert "storage.example" not in response.text
    assert "token" not in response.text
    for _ in range(2):
        assert (
            client.post(
                f"/api/v1/business/fiscal-operations/{operation['id']}/submit",
                json={"payload_digest": operation["payload_digest"]},
            ).status_code
            == 202
        )
    assert lane.provider.calls == 1
    response = client.get(
        f"/api/v1/business/fiscal-operations/{operation['id']}/artifacts/pdf"
    )
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF-")
    assert "no-store" in response.headers["cache-control"]


def test_callback_auth_probe_size_and_failed_durable_ack(client, lane, monkeypatch):
    path = "/api/v1/webhooks/fiscal-sandbox/emission"
    assert client.post(path, content=b"not json").status_code == 401
    headers = {"X-Cuadrao-Fiscal-Callback": "synthetic-callback-only"}
    assert (
        client.post(path, json={"message": "Test message"}, headers=headers).status_code
        == 200
    )
    assert client.post(path, content=b"x" * 32769, headers=headers).status_code == 413
    assert client.post(path, content=b"not json", headers=headers).status_code == 422

    def unavailable(*args, **kwargs):
        raise RuntimeError("synthetic_database_unavailable")

    monkeypatch.setattr(lane.store, "quarantine", unavailable)
    assert (
        client.post(
            path, json={"type": "documents.reception"}, headers=headers
        ).status_code
        == 503
    )


def test_disabled_surface_and_forbidden_caller_fields(lane):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_drafts] = lambda: SimpleNamespace(
        actor_id=lane.owner.actor_id,
        space_id=str(lane.case.business_id),
        grant_id=lane.grant,
    )
    with TestClient(app) as client:
        assert client.get(f"/business/fiscal-operations/{uuid4()}").status_code == 404
        app.dependency_overrides[require_fiscal] = lambda: lane.service
        response = client.post(
            "/business/fiscal-operations",
            json={"case_id": lane.case.case_id, "number": lane.case.number},
        )
        assert response.status_code == 422
