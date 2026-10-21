"""The in-memory app keeps no Business store. Over HTTP, each read whose
answer without a store is nothing answers that empty shape, the scope rule
and every write keep their refusals, and durable mode still refuses."""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest
from argus.api import state as api_state
from argus.domain.business import ledger
from fastapi.testclient import TestClient

from tests.business.test_bank_api import bank_client  # noqa: F401
from tests.business.test_business_api import BASE, Owner, started
from tests.ingestion.conftest import ALICE

PERIOD = {"period_start": "2026-10-01", "period_end": "2026-10-31"}
COUNTS = {
    "movimientos": 0,
    "igualadas": 0,
    "no_lleva_comprobante": 0,
    "sugerencias": 0,
    "falta_comprobante": 0,
    "sin_movimiento": 0,
    "por_igualar": 0,
}
EMPTY_OPEN_LIST = {
    "count": 0,
    "totals": [],
    "overdue": {"count": 0, "totals": []},
    "items": [],
}


@pytest.fixture
def alice(bank_client: TestClient) -> Owner:  # noqa: F811
    return Owner(bank_client, ALICE)


def _code(response) -> tuple[int, str]:  # noqa: ANN001
    return response.status_code, response.json()["code"]


def test_each_read_answers_its_empty_shape_once_the_business_exists(alice: Owner):
    started(alice)
    today = ledger.today().isoformat()

    for view in ({}, {"view": "inbox"}, {"q": "alfa", "limit": "3"}):
        notes = alice.get("/captures", **view)
        assert (notes.status_code, notes.json()) == (
            200,
            {"items": [], "has_more": False},
        )

    month = alice.get("/month-close", month="2026-10")
    assert (month.status_code, month.json()) == (
        200,
        {
            "month": "2026-10",
            "today": today,
            "from": "2026-10-01",
            "to": "2026-10-31",
            "closed": True,
            "reasons": [],
            "earliest_month": None,
            "payment_methods": [
                "efectivo",
                "transferencia",
                "tarjeta",
                "credito",
                "otro",
            ],
            "dgii_forms": {"606": "no_operations", "607": "no_operations"},
            "currencies": [],
            "missing_rnc": [],
            "missing_ncf": [],
            "cuentas_por_cobrar": [],
            "cuentas_por_pagar": [],
        },
    )
    assert _code(alice.get("/month-close", month="2026-13")) == (422, "month_invalid")

    open_items = alice.get("/open-items")
    assert (open_items.status_code, open_items.json()) == (
        200,
        {
            "today": today,
            "cuentas_por_cobrar": EMPTY_OPEN_LIST,
            "cuentas_por_pagar": EMPTY_OPEN_LIST,
        },
    )

    movements = alice.get("/bank/movements", **PERIOD)
    assert (movements.status_code, movements.json()) == (
        200,
        {
            **PERIOD,
            "segment": "todas",
            "sense": None,
            "currency": None,
            "accounts": [],
            "totals": [],
            "counts": COUNTS,
            "other_currencies": [],
            "items": [],
            "next_cursor": None,
        },
    )
    narrowed = alice.get(
        "/bank/movements", **PERIOD, segment="por_igualar", sense="charge", currency="USD"
    )
    assert narrowed.status_code == 200
    assert {key: narrowed.json()[key] for key in ("segment", "sense", "currency")} == {
        "segment": "por_igualar",
        "sense": "charge",
        "currency": "USD",
    }
    assert _code(
        alice.get("/bank/movements", period_start="2026-10-31", period_end="2026-10-01")
    ) == (422, "invalid_period")

    deliveries = alice.get("/email/deliveries")
    assert (deliveries.status_code, deliveries.json()) == (200, {"items": []})


def test_without_a_business_every_read_still_says_the_space_is_missing(alice: Owner):
    for response in (
        alice.get("/captures"),
        alice.get("/month-close", month="2026-10"),
        alice.get("/open-items"),
        alice.get("/bank/movements", **PERIOD),
        alice.get("/email/deliveries"),
    ):
        assert _code(response) == (404, "business_space_missing")


def test_writes_and_record_reads_stay_unavailable_without_a_store(alice: Owner):
    started(alice)
    key = {**alice.auth, "Idempotency-Key": str(uuid4())}
    client = alice.client
    for response in (
        client.post(f"{BASE}/captures", json={"text": "Pagué 850"}, headers=key),
        client.get(f"{BASE}/drafts/{uuid4()}/dossier", headers=alice.auth),
        client.patch(
            f"{BASE}/month-close/documents/{uuid4()}",
            json={"status": "pagado"},
            headers=key,
        ),
        client.post(
            f"{BASE}/bank/movements/{uuid4()}/match",
            json={"activity_id": str(uuid4())},
            headers=key,
        ),
        client.get(f"{BASE}/bank/movements/{uuid4()}/history", headers=alice.auth),
    ):
        assert _code(response) == (404, "business_unavailable")


def test_durable_mode_without_a_pool_refuses_as_before(alice: Owner):
    started(alice)
    with patch.object(api_state, "PERSISTENCE_MODE", "supabase"):
        assert _code(alice.get("/captures")) == (404, "business_unavailable")
        assert _code(alice.get("/month-close", month="2026-10")) == (
            404,
            "business_unavailable",
        )
        assert _code(alice.get("/open-items")) == (404, "business_unavailable")
        assert _code(alice.get("/bank/movements", **PERIOD)) == (
            404,
            "business_unavailable",
        )
        assert _code(alice.get("/email/deliveries")) == (
            503,
            "email_capture_unavailable",
        )
