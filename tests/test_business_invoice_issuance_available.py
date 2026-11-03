"""Every invoicing route answers one refusal while Facturación is off, and the
invoice page tells clients whether issuance is wired before any click."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from argus.api.business_drafts import require_drafts
from argus.api.routers import business_customers, business_invoices
from argus.domain.business.contracts.invoicing import InvoicePage
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Route templates, so the parametrize ids stay the same in every process (CI
# proves the shards collected one union, so an id must not carry a fresh UUID).
INVOICING_ROUTES = (
    ("GET", "/business/customers"),
    ("POST", "/business/customers"),
    ("GET", "/business/customers/{customer_id}"),
    ("PUT", "/business/customers/{customer_id}"),
    ("GET", "/business/invoices"),
    ("POST", "/business/invoices"),
    ("GET", "/business/invoices/{invoice_id}"),
    ("PUT", "/business/invoices/{invoice_id}"),
    ("POST", "/business/invoices/{invoice_id}/prepare"),
)
ROUTE_IDS = {"customer_id": UUID(int=1), "invoice_id": UUID(int=2)}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("CUADRAO_BUSINESS_INVOICING_ENABLED", "true")

    def page(store, actor, grant, query, *, issuance_available):
        return InvoicePage(
            items=(),
            total=0,
            page=1,
            page_size=25,
            stage_counts={},
            summaries=(),
            query_version="synthetic",
            issuance_available=issuance_available,
        )

    monkeypatch.setattr(business_invoices, "invoices", page)
    app = FastAPI()
    app.include_router(business_customers.router)
    app.include_router(business_invoices.router)

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = "synthetic-request"
        return await call_next(request)

    app.dependency_overrides[require_drafts] = lambda: SimpleNamespace(
        actor_id=uuid4(),
        space_id=str(uuid4()),
        grant_id=None,
        service=SimpleNamespace(authority=SimpleNamespace(pool=None)),
    )
    with TestClient(app) as result:
        yield result


def test_every_invoicing_route_is_listed():
    mounted = {
        (method, route.path)
        for router in (business_customers.router, business_invoices.router)
        for route in router.routes
        for method in route.methods
    }
    assert set(INVOICING_ROUTES) == mounted


@pytest.mark.parametrize(
    "off", ["switch_off", "provider_missing"], ids=["switch off", "provider missing"]
)
@pytest.mark.parametrize(("method", "path"), INVOICING_ROUTES)
def test_every_invoicing_route_refuses_while_off(client, monkeypatch, off, method, path):
    if off == "switch_off":
        monkeypatch.setenv("CUADRAO_BUSINESS_INVOICING_ENABLED", "false")
        client.app.state.fiscal_sandbox = object()
    else:
        client.app.state.fiscal_sandbox = None
    response = client.request(method, path.format(**ROUTE_IDS), json={})
    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "business_invoicing_unavailable"
    assert response.headers["cache-control"] == "no-store"


def test_page_says_available_when_the_fiscal_service_is_wired(client):
    client.app.state.fiscal_sandbox = object()
    response = client.get("/business/invoices")
    assert response.status_code == 200, response.text
    assert response.json()["issuance_available"] is True
