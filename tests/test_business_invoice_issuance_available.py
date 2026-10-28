"""The invoice page tells clients whether issuance is wired before any click."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from argus.api.business_drafts import require_drafts
from argus.api.routers import business_invoices
from argus.domain.business.contracts.invoicing import InvoicePage
from fastapi import FastAPI
from fastapi.testclient import TestClient


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


def test_page_says_unavailable_when_no_fiscal_service_is_wired(client):
    response = client.get("/business/invoices")
    assert response.status_code == 200, response.text
    assert response.json()["issuance_available"] is False
    prepared = client.post(
        f"/business/invoices/{uuid4()}/prepare", json={"expected_version": 1}
    )
    assert prepared.status_code == 404
    assert prepared.json()["detail"] == "fiscal_sandbox_unavailable"


def test_page_says_available_when_the_fiscal_service_is_wired(client):
    client.app.state.fiscal_sandbox = object()
    response = client.get("/business/invoices")
    assert response.status_code == 200, response.text
    assert response.json()["issuance_available"] is True
