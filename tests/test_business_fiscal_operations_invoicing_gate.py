"""A fiscal operation that belongs to an invoice answers Facturación's one refusal
while invoicing is off. The manifest lane and the emission webhook stay on the
fiscal gate alone."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from argus.api.business_drafts import require_drafts
from argus.api.routers.business_fiscal_operations import router
from argus.domain.business.fiscal_sandbox.contracts import FiscalOperation, FiscalState
from fastapi import FastAPI
from fastapi.testclient import TestClient

OPERATION_ID = UUID(int=3)
BUSINESS_ID = UUID(int=4)
INVOICE_ID = UUID(int=5)
DIGEST = "a" * 64

# (method, route template, status while answered, handler that answers it)
OPERATION_ROUTES = (
    ("GET", "/business/fiscal-operations/{operation_id}", 200, "get"),
    ("POST", "/business/fiscal-operations/{operation_id}/submit", 202, "submit"),
    ("GET", "/business/fiscal-operations/{operation_id}/artifacts/xml", 200, "artifact"),
    ("GET", "/business/fiscal-operations/{operation_id}/artifacts/pdf", 200, "artifact"),
)
ROUTE_IDS = [f"{method} {path}" for method, path, _, _ in OPERATION_ROUTES]


class FakeService:
    """Answers like the fiscal service and records which of its methods ran."""

    def __init__(self, invoice_id: UUID | None) -> None:
        self.operation = FiscalOperation(
            invoice_id=invoice_id,
            invoice_revision_id=uuid4() if invoice_id else None,
            id=OPERATION_ID,
            business_id=BUSINESS_ID,
            case_id="synthetic-case",
            kind="E31",
            number="E310000000001",
            payload_digest=DIGEST,
            provider_id=None,
            state=FiscalState(submission="prepared"),
        )
        self.calls: list[str] = []

    async def prepare(self, actor, grant, case_id) -> FiscalOperation:
        self.calls.append("prepare")
        return self.operation

    async def get(self, actor, grant, operation_id) -> FiscalOperation:
        self.calls.append("get")
        return self.operation

    async def submit(self, actor, grant, operation_id, expected_digest) -> FiscalOperation:
        self.calls.append("submit")
        return self.operation

    async def artifact(self, actor, grant, operation_id, kind) -> bytes:
        self.calls.append("artifact")
        return b"<synthetic/>"

    def authenticate(self, supplied: str) -> None:
        self.calls.append("authenticate")
        raise PermissionError


def make_client(monkeypatch, *, invoicing_on: bool, invoice_id: UUID | None):
    monkeypatch.setenv("CUADRAO_BUSINESS_INVOICING_ENABLED", "true" if invoicing_on else "false")
    service = FakeService(invoice_id)
    app = FastAPI()
    app.include_router(router)
    app.state.fiscal_sandbox = service

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = "synthetic-request"
        return await call_next(request)

    app.dependency_overrides[require_drafts] = lambda: SimpleNamespace(
        actor_id=uuid4(), space_id=str(BUSINESS_ID), grant_id=None
    )
    return TestClient(app), service


def call(client, method, path):
    return client.request(
        method, path.format(operation_id=OPERATION_ID), json={"payload_digest": DIGEST}
    )


@pytest.mark.parametrize(("method", "path", "status", "handler"), OPERATION_ROUTES, ids=ROUTE_IDS)
def test_invoice_operation_refuses_while_invoicing_is_off(monkeypatch, method, path, status, handler):
    client, service = make_client(monkeypatch, invoicing_on=False, invoice_id=INVOICE_ID)
    response = call(client, method, path)
    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "business_invoicing_unavailable"
    assert response.headers["cache-control"] == "no-store"
    assert service.calls == ["get"], "only the read that found the invoice link ran"


@pytest.mark.parametrize(("method", "path", "status", "handler"), OPERATION_ROUTES, ids=ROUTE_IDS)
def test_invoice_operation_answers_while_invoicing_is_on(monkeypatch, method, path, status, handler):
    client, service = make_client(monkeypatch, invoicing_on=True, invoice_id=INVOICE_ID)
    response = call(client, method, path)
    assert response.status_code == status, response.text
    assert service.calls[-1] == handler


@pytest.mark.parametrize(("method", "path", "status", "handler"), OPERATION_ROUTES, ids=ROUTE_IDS)
def test_manifest_operation_answers_while_invoicing_is_off(monkeypatch, method, path, status, handler):
    client, service = make_client(monkeypatch, invoicing_on=False, invoice_id=None)
    response = call(client, method, path)
    assert response.status_code == status, response.text
    assert service.calls[-1] == handler


def test_manifest_prepare_stays_on_the_fiscal_gate(monkeypatch):
    client, service = make_client(monkeypatch, invoicing_on=False, invoice_id=None)
    response = client.post("/business/fiscal-operations", json={"case_id": "synthetic-case"})
    assert response.status_code == 201, response.text
    assert service.calls == ["prepare"]


def test_emission_webhook_stays_on_the_fiscal_gate(monkeypatch):
    client, service = make_client(monkeypatch, invoicing_on=False, invoice_id=INVOICE_ID)
    response = client.post("/webhooks/fiscal-sandbox/emission", json={})
    assert response.status_code == 401, response.text
    assert response.json()["detail"] == "fiscal_callback_authentication"
    assert service.calls == ["authenticate"]
