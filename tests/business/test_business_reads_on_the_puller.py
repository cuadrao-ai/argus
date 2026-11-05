"""In the running app a Business receipt is read by the document worker, over
the app's own documents service, never by the API that recorded it."""

from __future__ import annotations

import time

import pytest
from argus.api.documents import documents_service
from argus.domain.ingestion.documents import worker as reading
from fastapi.testclient import TestClient

from tests.business.conftest import ALICE
from tests.business.receipt_stub import ReceiptStub
from tests.business.test_business_api import Owner, started
from tests.ingestion.test_document_jobs_api import document_worker_on


@pytest.fixture
def reads_finish_inside_the_request() -> None:
    """The document worker reads here."""


def test_an_uploaded_business_receipt_is_read_by_the_worker_and_lands_in_its_business(
    stub: ReceiptStub, client: TestClient, identities, monkeypatch  # noqa: ANN001
) -> None:
    monkeypatch.setattr(reading, "POLL_SECONDS", 0.01)
    alice = started(Owner(client, ALICE, identities[ALICE]["id"]))

    uploaded = alice.upload(name="recibo.png")
    assert uploaded.status_code == 200, uploaded.text
    receipt = uploaded.json()["id"]
    time.sleep(0.2)
    assert alice.detail(receipt)["status"] == "queued", "the API never reads it"
    assert stub.calls == []

    with document_worker_on(client):
        deadline = time.monotonic() + 5
        while alice.detail(receipt)["status"] != "review_ready":
            assert time.monotonic() < deadline, alice.detail(receipt)["status"]
            time.sleep(0.01)

    assert stub.calls == [receipt]
    job = documents_service().store.job(user_id=identities[ALICE]["id"], connection_id=receipt)
    assert (job.attempt, job.dispatched_at is not None) == (1, True), "a pull took it"
    [listed] = alice.get("/receipts", view="inbox").json()["items"]
    assert (listed["id"], listed["status"]) == (receipt, "review_ready")
