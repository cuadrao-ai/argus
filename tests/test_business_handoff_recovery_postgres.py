"""A receipt stuck on a saved read the hand-off now finishes recovers on one
"Leer de nuevo" with no new read (#2057)."""

import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from argus.domain.business.actions import mutations
from psycopg_pool import ConnectionPool

from tests import test_business_actions_postgres as shared
from tests import test_financial_accounts_postgres as database
from tests.business.test_business_api import RECEIPT
from tests.document_reads_support import leave_reads_waiting, read_receipt
from tests.test_business_attachment_preparation_postgres import (
    STUCK,
    _connection_state,
)
from tests.test_business_reading_setting_postgres import (  # noqa: F401
    _reading,
    _receipt,
    _upload,
    web,
)
from tests.test_business_reading_setting_postgres import (
    pytestmark as _local_supabase,
)
from tests.test_business_scope_switch_routes_postgres import API

pytestmark = shared.pytestmark


def _read_again(web, monkeypatch: pytest.MonkeyPatch, receipt_id: str) -> dict:  # noqa: ANN001, F811
    """One "Leer de nuevo" and the worker that runs it; the receipt after."""

    from workflows.document_job import postgres_documents_service

    leave_reads_waiting(monkeypatch)
    again = web.client.post(
        f"{API}/business/receipts/{receipt_id}/prepare",
        headers={
            **web.alice.headers,
            "Idempotency-Key": str(uuid4()),
            "X-Extraction-Consent": "true",
        },
    )
    assert again.status_code == 200, again.text
    store = web.documents.store
    with ConnectionPool(database.DSN, min_size=0, max_size=2) as own:
        worker = postgres_documents_service(own, store.objects, web.stub)
        asyncio.run(read_receipt(worker, web.alice.id, receipt_id))
    return _receipt(web, receipt_id)


def _dossier_facts(web, draft_id: str) -> dict:  # noqa: ANN001, F811
    dossier = web.client.get(
        f"{API}/business/drafts/{draft_id}/dossier", headers=web.alice.headers
    )
    assert dossier.status_code == 200, dossier.text
    return dossier.json()["facts"]


@_local_supabase
@pytest.mark.parametrize(
    ("row", "fiscal", "total", "stuck", "amount"),
    [
        ("transaction", {}, "0.00", "amount_positive_required", None),
        ("none", {"ncf": "B0100000001"}, "0.00", "amount_positive_required", None),
        (
            "none",
            {"ncf": "B0100000001"},
            "01180.00",
            "document_extraction_failed",
            "1180",
        ),
    ],
    ids=["zero-purchase", "zero-fiscal-bill", "leading-zero-fiscal-bill"],
)
def test_a_receipt_stuck_on_a_read_amount_recovers_without_a_new_read(
    web,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    faker,
    row: str,
    fiscal: dict,
    total: str,
    stuck: str,
    amount: str | None,
) -> None:
    """A bound receipt whose stored read has an amount the facts cannot hold
    (zero, or a leading zero) failed the same way on every hand-off. One "Leer
    de nuevo" replays that read into a review draft with the amount normalized
    or left for a person. The reader is not called again."""

    merchant = faker.company()
    reads = web.stub
    reads.complete = row == "transaction"
    reads.rows = (
        [
            dict(
                page=1,
                row=1,
                evidence="transaction",
                amount=total,
                currency="DOP",
                occurred_on="2026-11-10",
                direction="outflow",
                kind_hint="expense",
                merchant=merchant,
            )
        ]
        if row == "transaction"
        else []
    )
    reads.details = (
        dict(merchant=merchant, occurred_on="2026-11-10", total=total, currency="DOP")
        | fiscal
    )
    assert _reading(web, True).status_code == 200
    with monkeypatch.context() as before_the_fix:
        # The stuck state dates from when the hand-off took the model's amount as is.
        before_the_fix.setattr(
            mutations, "_read_amount", lambda text: text, raising=False
        )
        uploaded = _upload(web, RECEIPT + faker.binary(length=8))
    assert uploaded.status_code == 200, uploaded.text
    receipt_id = uploaded.json()["id"]
    stored = web.documents.store.get(user_id=web.alice.id, connection_id=receipt_id)
    assert stored.receipt.total == total
    assert _connection_state(receipt_id) == ("error", stuck)
    reads.calls.clear()

    detail = _read_again(web, monkeypatch, receipt_id)

    assert reads.calls == []
    assert (
        web.documents.store.get(user_id=web.alice.id, connection_id=receipt_id) == stored
    )
    assert _connection_state(receipt_id) == ("active", None)
    facts = _dossier_facts(web, detail["draft_id"])
    if amount is None:
        assert (facts["amount"]["state"], facts["amount"]["value"]) == ("unknown", None)
    else:
        assert Decimal(str(facts["amount"]["value"])) == Decimal(amount)
    assert facts["currency"]["value"] == "DOP"


@_local_supabase
def test_a_transfer_with_no_currency_recovers_without_a_new_read(
    web,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    faker,
) -> None:
    """A bound transfer screenshot (one purchase row with an amount, no currency,
    no receipt details) was refused as not a receipt with no way to read it
    again. It now offers "Leer de nuevo", which replays the stored read into a
    review draft with the currency left for a person."""

    reads = web.stub
    reads.rows = [
        dict(
            page=1,
            row=1,
            evidence="transaction",
            amount="500.00",
            occurred_on="2026-11-10",
            direction="outflow",
            kind_hint="expense",
            merchant=faker.company(),
        )
    ]
    reads.details = None
    assert _reading(web, True).status_code == 200
    with monkeypatch.context() as before_the_fix:
        # The stuck state dates from when the hand-off refused this read.
        before_the_fix.setattr(
            mutations, "read_refusal", lambda _: "not_a_receipt", raising=False
        )
        uploaded = _upload(web, RECEIPT + faker.binary(length=8))
    assert uploaded.status_code == 200, uploaded.text
    receipt_id = uploaded.json()["id"]
    stored = web.documents.store.get(user_id=web.alice.id, connection_id=receipt_id)
    assert stored.receipt is None
    assert _connection_state(receipt_id) == ("error", "not_a_receipt")
    reads.calls.clear()
    shown = _receipt(web, receipt_id)
    assert (shown["attention"], shown["preparable"]) == ("interrupted", True)

    detail = _read_again(web, monkeypatch, receipt_id)

    assert reads.calls == []
    assert (
        web.documents.store.get(user_id=web.alice.id, connection_id=receipt_id) == stored
    )
    assert _connection_state(receipt_id) == ("active", None)
    facts = _dossier_facts(web, detail["draft_id"])
    assert Decimal(str(facts["amount"]["value"])) == Decimal("500.00")
    assert facts["currency"]["state"] == "unknown"


@_local_supabase
def test_a_stuck_receipt_with_no_total_asks_for_its_details_without_a_new_read(
    web,  # noqa: F811
    faker,
) -> None:
    """A bound incomplete receipt with no total, stuck by
    ``business_preparation_batch_changed``, showed "No parece un recibo" after
    its retry. Its view now says what the hand-off says: check the details and
    enter them by hand. A new read would replay the same refusal, so none is
    offered, and looking at it reads nothing."""

    merchant = faker.company()
    reads = web.stub
    reads.complete = False
    reads.rows = [dict(page=1, row=1, evidence="unclassified", merchant=merchant)]
    reads.details = dict(merchant=merchant, occurred_on="2026-11-10")
    assert _reading(web, True).status_code == 200
    uploaded = _upload(web, RECEIPT + faker.binary(length=8))
    assert uploaded.status_code == 200, uploaded.text
    receipt_id = uploaded.json()["id"]
    # The first hand-off can also end in STUCK at random (#2064); the loop sets each code.
    assert _connection_state(receipt_id)[0] == "error"
    for code in (STUCK, "receipt_requires_review"):
        with database.psycopg.connect(database.DSN) as db:
            db.execute(
                "update public.financial_source_connections set last_error_code=%s"
                " where id=%s and status='error'",
                (code, receipt_id),
            )
            db.execute(
                "update public.financial_document_extractions"
                " set draft=jsonb_set(draft,'{error_code}',to_jsonb(%s::text))"
                " where connection_id=%s and preparation_binding is not null",
                (code, receipt_id),
            )
        reads.calls.clear()
        shown = _receipt(web, receipt_id)
        assert reads.calls == []
        assert (shown["error_code"], shown["attention"]) == (code, "check_details")
        assert (shown["preparable"], shown["enterable"]) == (False, True)
