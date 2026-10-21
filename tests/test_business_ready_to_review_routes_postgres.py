"""Over HTTP, on the real app, Auth and Postgres: ``ready_to_review_count``, the
Bandeja's "por revisar", counts the receipts a person can review now and the
notes awaiting review, one per draft. A receipt still being read or one the
reader found unreadable waits elsewhere. The receipt list, the activity counts
and the Resumen give the same number."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from argus.domain.ingestion.documents.jobs import PreparationJobs

from tests import test_financial_accounts_postgres as shared
from tests.business.receipt_stub import ReceiptStub
from tests.business.test_business_api import RECEIPT
from tests.test_business_reading_setting_postgres import (  # noqa: F401
    _reading,
    _upload,
    pytestmark,
    web,
)
from tests.test_business_scope_switch_routes_postgres import API, PERIOD, _note


def _get(web, path: str, **params):  # noqa: ANN001, ANN202, F811
    answer = web.client.get(f"{API}{path}", params=params, headers=web.alice.headers)
    assert answer.status_code == 200, (path, answer.text)
    return answer.json()


def _ready(web) -> int:  # noqa: ANN001, F811
    """The one number, after checking every surface gives it."""

    inbox = _get(web, "/business/receipts", view="inbox")["activity"]
    listed = _get(web, "/business/receipts", view="all")["activity"]
    found = _get(web, "/business/receipt-activity")
    overview = _get(web, "/business/overview", **PERIOD)
    assert inbox == listed == found
    assert overview["ready_to_review_count"] == found["ready_to_review_count"]
    return found["ready_to_review_count"]


def _saved(web, content: bytes) -> str:  # noqa: ANN001, F811
    uploaded = _upload(web, content)
    assert uploaded.status_code == 200, uploaded.text
    return uploaded.json()["id"]


def _row(web, receipt_id: str) -> tuple:  # noqa: ANN001, F811
    [row] = [
        item
        for item in _get(web, "/business/receipts", view="all")["items"]
        if item["id"] == receipt_id
    ]
    return row["status"], row["attention"], row["read_pending"]


def test_por_revisar_counts_reviewable_receipts_and_notes_in_every_surface(
    web,  # noqa: ANN001, F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _ready(web) == 0

    unread = _saved(web, RECEIPT + b"\x31")
    assert _row(web, unread) == ("saved", None, False)
    assert _ready(web) == 1

    assert _reading(web, True).status_code == 200
    read = _saved(web, RECEIPT + b"\x32")
    # Read and waiting for a person; a repeat of an earlier receipt still is.
    assert _row(web, read) in (
        ("review_ready", None, False),
        ("needs_attention", "duplicate", False),
    )
    assert _ready(web) == 2

    web.stub.failure = "extraction_provider_failed"
    failed = _saved(web, RECEIPT + b"\x33")
    assert _row(web, failed) == ("needs_attention", "ai_unavailable", False)
    assert _ready(web) == 3

    web.stub.failure = "encrypted_document"
    unreadable = _saved(web, RECEIPT + b"\x34")
    assert _row(web, unreadable) == ("needs_attention", "unreadable", False)
    assert _ready(web) == 3

    attempts: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "argus.api.documents.document_jobs",
        lambda: PreparationJobs(web.documents, lambda *attempt: attempts.append(attempt)),
    )
    reading = _saved(web, RECEIPT + b"\x35")
    status, _attention, pending = _row(web, reading)
    assert status in ("queued", "preparing") or pending
    assert _ready(web) == 3

    note = _note(web, web.alice, "Pagué 850 en Ferretería Prueba")
    assert note.status_code == 200, note.text
    assert _ready(web) == 4
    again = web.client.post(
        f"{API}/business/captures",
        json={
            "text": "Con la tarjeta",
            "draft": {
                "draft_id": note.json()["draft_id"],
                "version": note.json()["version"],
            },
        },
        headers={**web.alice.headers, "Idempotency-Key": str(uuid4())},
    )
    assert again.status_code == 200, again.text
    assert _ready(web) == 4
    activity = _get(web, "/business/receipt-activity")
    assert (activity["pending_review_count"], activity["reading_count"]) == (6, 1)

    from workflows.document_job import run_document_preparation

    [(connection_id, attempt_id)] = attempts
    outcome = asyncio.run(
        run_document_preparation(
            connection_id,
            attempt_id,
            env={"ARGUS_WORKFLOW_DATABASE_URL": shared.DSN},
            objects=web.documents.store.objects,
            extractor=ReceiptStub(),
        )
    )
    assert outcome["outcome"] == "prepared"
    assert _row(web, reading)[2] is False
    assert _ready(web) == 5
