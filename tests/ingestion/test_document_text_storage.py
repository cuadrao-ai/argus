"""Extracted text persists without rewriting the uploaded evidence."""

import hashlib
from unittest.mock import AsyncMock

import pytest
from argus.domain.business.contracts.actions import canonical_input_hash
from argus.domain.ingestion.documents.models import (
    ExtractedObservation,
    ExtractionBatch,
    ReceiptDetails,
    ReceiptItem,
)
from argus.domain.owner_scope import BusinessSpace
from faker import Faker

from tests.ingestion.test_business_document_bridge import document_bridge, reading_on

__all__ = ["document_bridge"]
fake = Faker()
SOURCE = b"%PDF-synthetic-source-with-\x00-original-byte"


@pytest.fixture
def prepared_receipt(document_bridge):
    service, bridge, extractor, _ = document_bridge
    owner = fake.uuid4()
    scope = BusinessSpace(fake.uuid4())
    reading_on(service, scope, owner)

    async def prepare(batch: ExtractionBatch):
        extractor.extract = AsyncMock(return_value=batch)
        uploaded = await service.upload(
            user_id=owner,
            content=SOURCE,
            filename="synthetic.pdf",
            media_type="application/pdf",
            consent=True,
            scope=scope,
        )
        await service.resume(
            user_id=owner, connection_id=uploaded.connection_id, scope=scope
        )
        saved = service.store.get(user_id=owner, connection_id=uploaded.connection_id)
        return service, bridge, extractor, owner, scope, uploaded, saved

    return prepare


def extracted_batch(text: str) -> ExtractionBatch:
    return ExtractionBatch(
        candidates=(),
        observations=(
            ExtractedObservation(
                page=1, row=1, evidence="unclassified", description=text
            ),
        ),
        receipt=ReceiptDetails(
            merchant=text,
            items=(ReceiptItem(id="item-1", description=text),),
        ),
        metadata={"source": "synthetic", "nested": [text]},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["uno\x00dos", "\x00\x00", "café\x00🧾"])
async def test_nul_text_is_saved_marked_and_original_file_is_unchanged(
    prepared_receipt, text: str
) -> None:
    batch = extracted_batch(text)
    service, bridge, extractor, owner, scope, uploaded, saved = await prepared_receipt(
        batch
    )
    cleaned = text.replace("\x00", "�")
    assert saved.observations[0].description == cleaned
    assert saved.receipt.merchant == cleaned
    assert saved.receipt.items[0].description == cleaned
    assert saved.metadata == {
        "source": "synthetic",
        "nested": [cleaned],
        "text_cleaning": {"nul_replacements": 4 * text.count("\x00")},
    }
    assert batch.observations[0].description == text
    assert batch.receipt.merchant == text
    assert batch.metadata == {"source": "synthetic", "nested": [text]}
    assert (
        service.store.source(user_id=owner, connection_id=uploaded.connection_id)
        == SOURCE
    )
    draft = service.get(user_id=owner, connection_id=uploaded.connection_id, scope=scope)
    assert draft.sha256 == hashlib.sha256(SOURCE).hexdigest()
    assert draft.status == "review_ready"
    assert bridge.prepare_attachment.call_args.kwargs[
        "expected_batch_sha256"
    ] == canonical_input_hash(saved)
    await service.resume(user_id=owner, connection_id=uploaded.connection_id, scope=scope)
    extractor.extract.assert_awaited_once()
    assert service.store.get(user_id=owner, connection_id=uploaded.connection_id) == saved
    assert bridge.prepare_attachment.call_args.kwargs[
        "expected_batch_sha256"
    ] == canonical_input_hash(saved)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text", ["José\t\n🧾 e\u0301\u200d", r"literal \u0000 remains", ""]
)
async def test_database_safe_text_is_preserved_without_cleaning_marker(
    prepared_receipt, text: str
) -> None:
    batch = extracted_batch(text)
    _, _, _, _, _, _, saved = await prepared_receipt(batch)
    assert saved == batch
    assert "text_cleaning" not in saved.metadata


@pytest.mark.asyncio
async def test_replacement_does_not_join_fiscal_or_money_digits(prepared_receipt) -> None:
    batch = ExtractionBatch(
        candidates=(),
        receipt=ReceiptDetails(rnc="123\x00456", ncf="B010\x000123", total="1\x0000.00"),
    )
    _, _, _, _, _, _, saved = await prepared_receipt(batch)
    assert saved.receipt.rnc == "123�456"
    assert saved.receipt.ncf == "B010�0123"
    assert saved.receipt.total == "1�00.00"
    assert saved.metadata["text_cleaning"] == {"nul_replacements": 3}
