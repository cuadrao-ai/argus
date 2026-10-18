"""A read that was saved but whose hosted hand-off refused or failed never
shows as "no purchase found": the receipt keeps the real code, waits as
interrupted, and a retry replays the saved read (no new provider call) and
runs the hand-off again. A read that found nothing still says so."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from argus.domain.business.authority import ActionError
from argus.domain.business.receipts import compose
from argus.domain.ingestion.documents.extractor import batch_from_result
from argus.domain.ingestion.documents.models import DocumentDraft, ExtractionResult
from argus.domain.owner_scope import BusinessSpace

from tests.business.receipt_stub import DETAILS, PURCHASE
from tests.ingestion.test_business_document_bridge import (  # noqa: F401
    document_bridge,
    reading_on,
)

NOW = datetime(2026, 10, 12, 20, 26, tzinfo=timezone.utc)


def _draft(error_code: str | None, status: str = "needs_attention") -> DocumentDraft:
    return DocumentDraft(
        connection_id=str(uuid4()),
        filename="image.png",
        media_type="image/png",
        sha256="a" * 64,
        size_bytes=214_557,
        consent=True,
        status=status,
        error_code=error_code,
        source_available=True,
        created_at=NOW,
        updated_at=NOW,
    )


def _batch(draft: DocumentDraft, rows: list[dict]):  # noqa: ANN202
    result = ExtractionResult.model_validate(
        dict(
            complete=True,
            readable=True,
            pages_read=[1],
            observations=rows,
            receipt=DETAILS,
        )
    )
    return batch_from_result(result, draft.sha256, draft.connection_id, NOW, 1)


@pytest.mark.parametrize(
    "code",
    [
        "business_preparation_binding_live",
        "business_preparation_binding_denied",
        "business_preparation_batch_changed",
        "business_record_not_found",
        "document_extraction_failed",
    ],
)
def test_a_saved_read_whose_handoff_failed_waits_as_interrupted_and_retryable(code):
    draft = _draft(code)
    batch = _batch(draft, [PURCHASE])
    assert len(batch.candidates) == 1 and batch.issues == ()
    receipt = compose(draft, batch, [], "web")
    assert (receipt.status, receipt.attention, receipt.error_code) == (
        "needs_attention",
        "interrupted",
        code,
    )
    assert receipt.preparable is True
    assert receipt.detail()["evidence"]["total"] == DETAILS["total"]
    assert receipt.detail()["draft_id"] is None


def test_a_read_that_found_nothing_still_says_no_purchase_found():
    draft = _draft("no_financial_observations")
    batch = _batch(draft, [])
    receipt = compose(draft, batch, [], "web")
    # The read's own finding keeps its code; the inbox says no purchase was found.
    assert (receipt.status, receipt.attention, receipt.error_code) == (
        "needs_attention",
        "no_purchase_found",
        "no_financial_observations",
    )
    assert receipt.preparable is False and receipt.enterable is True


def test_a_stored_statement_refusal_reads_as_not_a_receipt():
    draft = _draft("receipt_requires_review")
    statement = {
        **PURCHASE,
        "evidence": "statement_period",
        "direction": "unknown",
        "kind_hint": "unknown",
        "currency": "USD",
        "amount": "42.00",
    }
    result = ExtractionResult.model_validate(
        dict(
            complete=True,
            readable=True,
            pages_read=[1],
            observations=[statement],
            receipt=None,
        )
    )
    batch = batch_from_result(result, draft.sha256, draft.connection_id, NOW, 1)
    receipt = compose(draft, batch, [], "web")
    assert (receipt.attention, receipt.preparable, receipt.enterable) == (
        "not_a_receipt",
        False,
        True,
    )
    assert receipt.error_code == "receipt_requires_review"


def test_a_stored_unreadable_refusal_reads_as_unreadable():
    draft = _draft("receipt_requires_review")
    result = ExtractionResult.model_validate(
        dict(
            complete=True,
            readable=False,
            pages_read=[1],
            observations=[],
            receipt=None,
        )
    )
    batch = batch_from_result(result, draft.sha256, draft.connection_id, NOW, 1)
    receipt = compose(draft, batch, [], "web")
    assert (receipt.attention, receipt.preparable, receipt.enterable) == (
        "unreadable",
        False,
        True,
    )


def test_a_stored_ncf_bill_refusal_stays_reprocessable():
    draft = _draft("receipt_requires_review")
    notice = {
        **PURCHASE,
        "evidence": "due_notice",
        "direction": "unknown",
        "kind_hint": "unknown",
    }
    result = ExtractionResult.model_validate(
        dict(
            complete=False,
            readable=True,
            pages_read=[1],
            observations=[notice],
            receipt=dict(total="1500.00", currency="DOP", ncf="B0100000001"),
        )
    )
    batch = batch_from_result(result, draft.sha256, draft.connection_id, NOW, 1)
    receipt = compose(draft, batch, [], "web")
    assert (receipt.attention, receipt.preparable, receipt.enterable) == (
        "interrupted",
        True,
        True,
    )


def test_an_error_the_read_itself_produced_keeps_its_own_blocker():
    draft = _draft("receipt_purchase_ambiguous")
    batch = _batch(draft, [PURCHASE, {**PURCHASE, "row": 2, "amount": "100.00"}])
    receipt = compose(draft, batch, [], "web")
    assert receipt.error_code == "receipt_purchase_ambiguous"
    assert receipt.preparable is False and receipt.enterable is True


@pytest.mark.asyncio
async def test_a_terminal_refusal_is_logged_without_the_document(
    document_bridge,  # noqa: F811
):
    from loguru import logger

    service, bridge, _, _ = document_bridge
    bridge.prepare_attachment.side_effect = ActionError("invalid_input", "not_a_receipt")
    scope = BusinessSpace(str(uuid4()))
    owner = str(uuid4())
    reading_on(service, scope, owner)
    receipt = await service.upload(
        user_id=owner,
        content=b"%PDF-fixture",
        filename="receipt.pdf",
        media_type="application/pdf",
        consent=True,
        scope=scope,
    )
    messages: list[str] = []
    sink = logger.add(
        lambda message: messages.append(message.record["message"]), level="WARNING"
    )
    try:
        with pytest.raises(ActionError, match="not_a_receipt"):
            await service.resume(
                user_id=owner, connection_id=receipt.connection_id, scope=scope
            )
    finally:
        logger.remove(sink)
    logged = [line for line in messages if "document_preparation_refused" in line]
    assert logged
    assert receipt.connection_id in logged[0]
    assert "not_a_receipt" in logged[0]
    assert "receipt.pdf" not in logged[0]
    assert "%PDF" not in logged[0]


@pytest.mark.asyncio
async def test_a_refused_handoff_keeps_the_read_and_the_retry_hands_off_again(
    document_bridge,  # noqa: F811
):
    service, bridge, extractor, sink = document_bridge
    bridge.prepare_attachment.side_effect = [
        ActionError("invalid_input", "business_preparation_binding_live"),
        None,
    ]
    scope = BusinessSpace(str(uuid4()))
    owner = str(uuid4())
    reading_on(service, scope, owner)
    receipt = await service.upload(
        user_id=owner,
        content=b"%PDF-fixture",
        filename="receipt.pdf",
        media_type="application/pdf",
        consent=True,
        scope=scope,
    )
    with pytest.raises(ActionError, match="business_preparation_binding_live"):
        await service.resume(
            user_id=owner, connection_id=receipt.connection_id, scope=scope
        )
    draft = service.get(user_id=owner, connection_id=receipt.connection_id, scope=scope)
    assert (draft.status, draft.error_code) == (
        "needs_attention",
        "business_preparation_binding_live",
    )
    assert (
        service.store.get(user_id=owner, connection_id=receipt.connection_id) is not None
    )
    outcome = await service.resume(
        user_id=owner, connection_id=receipt.connection_id, scope=scope
    )
    assert outcome.replayed is True
    extractor.extract.assert_awaited_once()
    assert bridge.prepare_attachment.call_count == 2
    sink.ingest.assert_not_called()
    after = service.get(user_id=owner, connection_id=receipt.connection_id, scope=scope)
    assert after.error_code is None
