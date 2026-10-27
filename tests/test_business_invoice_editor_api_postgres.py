from types import SimpleNamespace
from uuid import uuid4

import pytest
from argus.api.business_drafts import require_drafts
from argus.api.fiscal_operations import require_fiscal
from argus.api.routers.business_customers import router as customers_router
from argus.api.routers.business_invoices import router
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests import test_business_invoice_editor as unit
from tests import test_business_invoice_editor_postgres as database
from tests import test_financial_accounts_postgres as shared
from tests.fiscal import conftest as fiscal

case_factory, lane, users = fiscal.case_factory, fiscal.lane, fiscal.users
editor, draft = database.editor, unit.draft
pytestmark = pytest.mark.skipif(not shared.DSN, reason="Disposable database required")


@pytest.fixture
def client(lane, editor, monkeypatch):
    monkeypatch.setenv("CUADRAO_BUSINESS_INVOICING_ENABLED", "true")
    app = FastAPI()
    app.include_router(router)
    app.include_router(customers_router)

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = "synthetic-request"
        return await call_next(request)

    app.dependency_overrides[require_drafts] = lambda: SimpleNamespace(
        actor_id=lane.owner.actor_id,
        space_id=str(lane.owner.space_id),
        grant_id=lane.grant,
        service=SimpleNamespace(authority=SimpleNamespace(pool=lane.store.pool)),
    )
    app.dependency_overrides[require_fiscal] = lambda: lane.service
    with TestClient(app) as result:
        yield result


def test_create_reload_conflict_prepare_and_list(client, draft):
    body = {"data": draft.model_dump(mode="json")}
    response = client.post(
        "/business/invoices", json=body, headers={"Idempotency-Key": str(uuid4())}
    )
    assert response.status_code == 201, response.text
    saved = response.json()
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/business/invoices/" + saved["id"]).json() == saved
    response = client.put(
        "/business/invoices/" + saved["id"],
        json={**body, "expected_version": 2},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["context"]["attempted"]["data"] == body["data"]
    prepared = client.post(
        "/business/invoices/" + saved["id"] + "/prepare", json={"expected_version": 1}
    )
    assert prepared.status_code == 200, prepared.text
    assert prepared.json()["operation"]["invoice_id"] == saved["id"]
    assert client.get("/business/invoices").json()["total"] == 1
    assert client.get("/business/invoices?page_size=13").status_code == 422


def test_disabled_and_invalid_customer_never_creates(client, monkeypatch):
    response = client.post(
        "/business/customers",
        json={"data": {"name": "", "email": "unfinished"}},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 422
    assert client.get("/business/customers").json()["total"] == 0
    monkeypatch.setenv("CUADRAO_BUSINESS_INVOICING_ENABLED", "false")
    assert client.get("/business/invoices").status_code == 404
    assert client.get("/business/customers").status_code == 404
