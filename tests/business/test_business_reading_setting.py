"""The owner's stored receipt-reading setting is the only consent for a Business
read. A documents service built without it never reads a Business receipt."""

from __future__ import annotations

import asyncio
from copy import copy

import pytest
from argus.api.documents import documents_service
from argus.domain.ingestion.documents.service import DocumentServiceError

from tests.business.receipt_stub import ReceiptStub
from tests.business.test_business_api import RECEIPT, Owner, alice  # noqa: F401


def test_a_service_without_the_setting_never_reads_a_business_receipt(
    alice: Owner,  # noqa: F811
    stub: ReceiptStub,
) -> None:
    documents = documents_service()
    assert documents is not None
    scope = alice.scope().owner
    uploaded = alice.upload(RECEIPT + b"\x07", consent=False)
    assert uploaded.status_code == 200, uploaded.text
    receipt_id = uploaded.json()["id"]
    # Queued the way the API queues it while the owner's reading is on.
    setting = documents.business_receipt_consent
    shown = setting.status(scope.space_id, alice.person)
    accepted = setting.set(
        scope.space_id,
        alice.person,
        enabled=True,
        version=1,
        disclosure_token=shown["disclosure_token"],
    )
    draft = documents.get(user_id=alice.person, connection_id=receipt_id, scope=scope)
    documents._update(
        alice.person,
        draft,
        status="queued",
        consent=True,
        business_reading_consent_id=accepted["consent_id"],
    )
    worker = copy(documents)
    worker.business_receipt_consent = None

    with pytest.raises(DocumentServiceError) as refused:
        asyncio.run(
            worker.resume(
                user_id=alice.person,
                connection_id=receipt_id,
                queued_only=True,
                scope=scope,
            )
        )
    assert refused.value.code == "document_reading_not_allowed"
    assert stub.calls == []
    assert alice.detail(receipt_id)["status"] == "saved"

    captured = asyncio.run(
        worker.upload(
            user_id=alice.person,
            content=RECEIPT + b"\x08",
            filename="recibo.png",
            media_type="image/png",
            consent=True,
            scope=scope,
        )
    )
    assert captured.status == "saved"
    assert stub.calls == []
