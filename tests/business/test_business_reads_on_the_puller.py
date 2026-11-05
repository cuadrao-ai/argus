"""In the running app a Business receipt is read by the process's own puller,
over the app's own documents service, not by the request that uploaded it."""

from __future__ import annotations

import time

import pytest
from argus.api.document_jobs import document_worker
from argus.api.documents import documents_service
from argus.domain.ingestion.documents import worker as reading
from fastapi.testclient import TestClient

from tests.business.conftest import ALICE
from tests.business.receipt_stub import ReceiptStub
from tests.business.test_business_api import Owner, started


@pytest.fixture
def reads_finish_inside_the_request() -> None:
    """The app's real puller reads here."""


def test_an_uploaded_business_receipt_is_read_by_the_puller_and_lands_in_its_business(
    stub: ReceiptStub, client: TestClient, identities, monkeypatch  # noqa: ANN001
) -> None:
    # Only the upload's own wake can start the read.
    monkeypatch.setattr(reading, "POLL_SECONDS", 3600)
    alice = started(Owner(client, ALICE, identities[ALICE]["id"]))
    assert document_worker().service is documents_service()

    uploaded = alice.upload(name="recibo.png")
    assert uploaded.status_code == 200, uploaded.text
    receipt = uploaded.json()["id"]
    deadline = time.monotonic() + 5
    while alice.detail(receipt)["status"] != "review_ready":
        assert time.monotonic() < deadline, alice.detail(receipt)["status"]
        time.sleep(0.01)

    assert stub.calls == [receipt]
    job = documents_service().store.job(user_id=identities[ALICE]["id"], connection_id=receipt)
    assert (job.attempt, job.dispatched_at is not None) == (1, True), "a pull took it"
    [listed] = alice.get("/receipts", view="inbox").json()["items"]
    assert (listed["id"], listed["status"]) == (receipt, "review_ready")
