"""Bank matching routes. The switch is off until the pilot and the flag are on."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest
from argus.api import state as api_state
from argus.api.main import app
from argus.domain.business.bank.service import bank_matching_service
from argus.domain.business.bank.targets import RecordedTarget, StaticCatalog
from fastapi.testclient import TestClient

from tests.business.test_business_api import Owner, started
from tests.ingestion.conftest import ALICE

BASE = "/api/v1/business/bank"
STATEMENT = (
    "# synthetic\n"
    "Fecha,Descripcion,Debito,Credito,Moneda\n"
    "01/10/2026,Ferreteria Luna,1500.00,,DOP\n"
    "07/10/2026,Sin recibo,250.00,,DOP\n"
).encode()


@pytest.fixture
def bank_client(ingestion_env, gateway, monkeypatch) -> Iterator[TestClient]:  # noqa: ANN001
    monkeypatch.setenv("ARGUS_BUSINESS_PILOT_ENABLED", "true")
    monkeypatch.setenv("ARGUS_BUSINESS_BANK_MATCHING_ENABLED", "true")
    monkeypatch.setenv("ARGUS_DOCUMENT_EXTRACTION_ENABLED", "true")
    assert api_state.PERSISTENCE_MODE == "memory"
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
        TestClient(app) as test_client,
    ):
        yield test_client


def test_the_routes_are_absent_until_the_pilot_is_on(client: TestClient) -> None:
    response = client.get(f"{BASE}/suggestions")
    assert response.status_code == 404
    assert response.json()["code"] == "business_unavailable"
    assert response.headers["cache-control"] == "no-store"


def test_import_confirm_and_sin_comprobante(bank_client: TestClient, identities) -> None:  # noqa: ANN001
    owner = started(Owner(bank_client, ALICE, identities[ALICE]["id"]))
    account_id = owner.account()
    service = bank_matching_service()
    assert service is not None
    service.catalog = StaticCatalog(
        (
            RecordedTarget(
                id="receipt-1",
                kind="receipt",
                amount=Decimal("1500.00"),
                currency="DOP",
                occurred_on=date(2026, 10, 1),
                merchant="Ferreteria Luna",
            ),
        )
    )
    created = bank_client.post(
        f"{BASE}/imports",
        files={"statement": ("statement.csv", STATEMENT, "text/csv")},
        data={"account_id": account_id},
        headers={**owner.auth, "Idempotency-Key": "oct-import"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["reader_id"] == "banco_popular"
    assert body["inserted_count"] == 2
    assert {line["state"] for line in body["lines"]} == {"sin_comprobante"}
    suggestion = body["suggestions"][0]
    assert suggestion["status"] == "pending"
    assert suggestion["actionable"] is True
    confirmed = bank_client.post(
        f"{BASE}/suggestions/{suggestion['id']}/confirm",
        headers={**owner.auth, "Idempotency-Key": "yes-1"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirmed"
    unmatched = owner.client.get(
        f"{BASE}/unmatched",
        params={"period_start": "2026-10-01", "period_end": "2026-10-17"},
        headers=owner.auth,
    )
    assert unmatched.status_code == 200, unmatched.text
    assert unmatched.json()["count"] == 1
    assert unmatched.json()["lines"][0]["amount"].startswith("-250")
    replay = bank_client.post(
        f"{BASE}/imports",
        files={"statement": ("statement.csv", STATEMENT, "text/csv")},
        data={"account_id": account_id},
        headers={**owner.auth, "Idempotency-Key": "oct-import"},
    )
    assert replay.status_code == 200
    assert replay.json()["created"] is False


def test_bank_flag_off_stays_404_while_the_pilot_is_on(
    ingestion_env,
    gateway,
    monkeypatch,  # noqa: ANN001
) -> None:
    monkeypatch.setenv("ARGUS_BUSINESS_PILOT_ENABLED", "true")
    monkeypatch.delenv("ARGUS_BUSINESS_BANK_MATCHING_ENABLED", raising=False)
    monkeypatch.delenv("CUADRAO_BUSINESS_BANK_MATCHING_ENABLED", raising=False)
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
        TestClient(app) as test_client,
    ):
        response = test_client.get(f"{BASE}/unmatched")
    assert response.status_code == 404
    assert response.json()["code"] == "business_unavailable"


def test_a_partial_mapping_is_422(bank_client: TestClient, identities) -> None:  # noqa: ANN001
    owner = started(Owner(bank_client, ALICE, identities[ALICE]["id"]))
    response = bank_client.post(
        f"{BASE}/imports",
        files={"statement": ("statement.csv", b"a,b\n1,2\n", "text/csv")},
        data={"account_id": str(uuid4()), "date_column": "a"},
        headers={**owner.auth, "Idempotency-Key": "bad-map"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_mapping"
