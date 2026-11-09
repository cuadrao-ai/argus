"""Over HTTP on the real app, Auth and Postgres: ``filing_ready`` on the month
close is one fact. A month whose 606 and 607 stand by the export's verdict is
still not ready while a receipt of that month waits in the Bandeja, because the
export only sees approved records.
"""

from __future__ import annotations

import asyncio
import threading
import time
from contextlib import contextmanager
from uuid import uuid4

import psycopg
import pytest
from argus.api.documents import documents_service
from argus.api.email_intake import configure_email_intake, email_intake
from argus.domain.ingestion.email_intake.service import (
    EmailCapture,
    grant_route_authority,
)
from argus.domain.ingestion.email_intake.store import PostgresEmailStore
from psycopg_pool import ConnectionPool

from tests import test_business_approve_unpaid_postgres as unpaid
from tests import test_financial_accounts_postgres as shared
from tests.test_business_document_type_postgres import (  # noqa: F401
    API,
    SUPPLIER_RNC,
    _own_rnc,
    _upload,
    web,
)
from tests.test_business_document_type_postgres import pytestmark as _local_supabase
from tests.test_business_email_intake_postgres import Provider, message

pytestmark = _local_supabase


@pytest.fixture(autouse=True)
def _settlement(settlement_on: None) -> None:
    """These flows read or mark cobrado and pagado: settlement on, as before."""


MONTH = "2026-09"


def _month(world, month: str = MONTH) -> dict:  # noqa: ANN001
    answer = world.client.get(
        f"{API}/business/month-close",
        params={"month": month},
        headers=world.alice.headers,
    )
    assert answer.status_code == 200, answer.text
    return answer.json()


def test_a_receipt_still_in_the_bandeja_holds_filing_ready_while_the_forms_stand(
    web,  # noqa: ANN001, F811
) -> None:
    _own_rnc(web)
    draft, recorded = unpaid._recorded(web, "expense", "B0100000041")
    activity = recorded["approval_result"]["activity_id"]
    unpaid._declare(web, draft, category="02", payment_method="01")
    unpaid._settle(web, activity, "pagado", "efectivo")

    month = _month(web)
    assert month["dgii_forms"]["606"] == "prepared_candidate"
    assert (month["missing_fiscal_data"], month["cuentas_por_pagar"]) == ([], [])
    assert month["filing_ready"] is True

    _upload(web, SUPPLIER_RNC, occurred_on=f"{MONTH}-10")
    month = _month(web)
    assert month["dgii_forms"]["606"] == "prepared_candidate"
    assert month["unreviewed_movements_count"] == 1
    assert month["filing_ready"] is False


def test_an_unpaid_purchase_holds_filing_ready_only_while_settlement_is_on(
    web,  # noqa: ANN001, F811
    monkeypatch,  # noqa: ANN001
) -> None:
    _own_rnc(web)
    draft, recorded = unpaid._recorded(web, "expense", "B0100000061")
    unpaid._declare(web, draft, category="02", payment_method="01")
    activity = recorded["approval_result"]["activity_id"]

    held = _month(web)
    assert held["dgii_forms"]["606"] == "prepared_candidate"
    assert [line["activity_id"] for line in held["cuentas_por_pagar"]] == [activity]
    assert held["filing_ready"] is False

    monkeypatch.setenv("CUADRAO_BUSINESS_SETTLEMENT_ENABLED", "false")
    ready = _month(web)
    assert {"payment_methods", "cuentas_por_cobrar", "cuentas_por_pagar"}.isdisjoint(
        ready
    )
    assert ready["dgii_forms"] == held["dgii_forms"]
    assert ready["missing_fiscal_data"] == held["missing_fiscal_data"] == []
    assert ready["filing_ready"] is True
    refused = web.client.get(f"{API}/business/open-items", headers=web.alice.headers)
    assert (refused.status_code, refused.json()["code"]) == (
        404,
        "business_settlement_unavailable",
    )


@contextmanager
def _reader_held(world, upload):  # noqa: ANN001, ANN202
    """Run ``upload`` with the reader held open and enter once the Bandeja shows
    a receipt reading. The read lands when the block exits."""

    gate = threading.Event()
    original = world.stub.extract

    async def held(**kwargs):  # noqa: ANN003, ANN202
        deadline = time.monotonic() + 30
        while not gate.is_set() and time.monotonic() < deadline:
            await asyncio.sleep(0.05)
        return await original(**kwargs)

    world.stub.extract = held
    worker = threading.Thread(target=upload)
    worker.start()
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            counts = world.client.get(
                f"{API}/business/receipt-activity", headers=world.alice.headers
            )
            if counts.json().get("reading_count"):
                break
            time.sleep(0.1)
        else:
            raise AssertionError("the reader never showed as reading")
        yield
    finally:
        gate.set()
        worker.join(40)
        world.stub.extract = original


def _ready_september(world) -> None:  # noqa: ANN001
    _own_rnc(world)
    draft, recorded = unpaid._recorded(world, "expense", "B0100000051")
    unpaid._declare(world, draft, category="02", payment_method="01")
    unpaid._settle(
        world, recorded["approval_result"]["activity_id"], "pagado", "efectivo"
    )
    month = _month(world)
    assert month["dgii_forms"]["606"] == "prepared_candidate"
    assert month["filing_ready"] is True


def test_a_month_is_not_ready_while_an_undated_receipt_is_in_its_first_read(
    web,  # noqa: ANN001, F811
) -> None:
    _ready_september(web)

    with _reader_held(web, lambda: _upload(web, SUPPLIER_RNC, occurred_on="2026-08-12")):
        held = {month: _month(web, month) for month in (MONTH, "2026-08", "2026-10")}
    assert [answer["filing_ready"] for answer in held.values()] == [False] * 3
    assert held[MONTH]["dgii_forms"]["606"] == "prepared_candidate"
    assert held[MONTH]["unreviewed_movements_count"] == 0
    assert held[MONTH]["missing_fiscal_data"] == []

    landed = _month(web)
    assert landed["unreviewed_movements_count"] == 0
    assert landed["filing_ready"] is True
    assert _month(web, "2026-08")["unreviewed_movements_count"] == 1


def test_a_month_is_not_ready_while_an_email_is_still_reading(
    web,  # noqa: ANN001, F811
) -> None:
    _ready_september(web)
    with psycopg.connect(shared.DSN) as db:
        grant = db.execute(
            "select id from public.business_client_grants"
            " where space_id=%s and grantee_id=%s and revoked_at is null",
            (web.alice.space_id, web.alice.id),
        ).fetchone()[0]
    pool = ConnectionPool(shared.DSN, open=True)
    store = PostgresEmailStore(pool)
    recipient = f"recibos-{uuid4().hex[:8]}@recibos.example.test"
    store.create_route(
        recipient=recipient,
        space_id=web.alice.space_id,
        principal_id=web.alice.id,
        granted_by=web.alice.id,
        grant_id=str(grant),
    )
    runtime = EmailCapture(
        store,
        documents_service(),
        grant_route_authority(pool),
        Provider(message(), (recipient,)),
        lambda: True,
        lambda: True,
    )
    previous = email_intake()
    configure_email_intake(runtime)
    try:
        assert _month(web)["filing_ready"] is True
        runtime.enqueue_resend(str(uuid4()), (recipient,))
        held = _month(web)
        assert held["dgii_forms"]["606"] == "prepared_candidate"
        assert held["unreviewed_movements_count"] == 0
        assert held["filing_ready"] is False
    finally:
        configure_email_intake(previous)
        pool.close()
