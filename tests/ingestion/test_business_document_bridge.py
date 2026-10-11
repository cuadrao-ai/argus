from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from argus.domain.ingestion.connections import InMemoryConnectionRepository
from argus.domain.ingestion.documents.models import ExtractionBatch
from argus.domain.ingestion.documents.service import (
    DocumentServiceError,
    DocumentsService,
)
from argus.domain.ingestion.documents.store import InMemoryDocumentStore
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.owner_scope import PERSONAL, BusinessSpace


@pytest.fixture
def document_bridge():
    repo = InMemoryConnectionRepository()
    store = InMemoryDocumentStore(repo)
    sink = Mock()
    hub = IngestionHub(
        repo, box=None, sink=sink, clock=lambda: datetime.now(timezone.utc)
    )
    extractor = Mock(extract=AsyncMock(return_value=ExtractionBatch(candidates=())))
    bridge = Mock()
    service = DocumentsService(hub, store, extractor, business_actions=bridge)
    return service, bridge, extractor, sink


@pytest.mark.asyncio
async def test_business_preparation_uses_canonical_bridge_and_saved_batch_on_retry(
    document_bridge,
):
    service, bridge, extractor, sink = document_bridge
    scope = BusinessSpace(str(uuid4()))
    receipt = await service.upload(
        user_id=str(uuid4()),
        content=b"%PDF-fixture",
        filename="receipt.pdf",
        media_type="application/pdf",
        consent=True,
        scope=scope,
    )
    owner = service.store.owner(connection_id=receipt.connection_id)
    await service.resume(user_id=owner, connection_id=receipt.connection_id, scope=scope)
    await service.resume(user_id=owner, connection_id=receipt.connection_id, scope=scope)
    assert bridge.check_attachment_preparation.call_count == 3
    assert bridge.prepare_attachment.call_count == 2
    extractor.extract.assert_awaited_once()
    sink.ingest.assert_not_called()


@pytest.mark.asyncio
async def test_denied_original_grant_never_calls_extractor(document_bridge):
    service, bridge, extractor, _ = document_bridge
    bridge.check_attachment_preparation.side_effect = DocumentServiceError(
        "business_permission_denied"
    )
    scope = BusinessSpace(str(uuid4()))
    owner = str(uuid4())
    receipt = await service.upload(
        user_id=owner,
        content=b"%PDF-fixture",
        filename="receipt.pdf",
        media_type="application/pdf",
        consent=True,
        scope=scope,
    )
    with pytest.raises(DocumentServiceError, match="business_permission_denied"):
        await service.resume(
            user_id=owner, connection_id=receipt.connection_id, scope=scope
        )
    extractor.extract.assert_not_awaited()
    bridge.prepare_attachment.assert_not_called()


@pytest.mark.asyncio
async def test_personal_does_not_use_business_bridge(document_bridge):
    service, bridge, extractor, _ = document_bridge
    owner = str(uuid4())
    receipt = await service.upload(
        user_id=owner,
        content=b"%PDF-fixture",
        filename="receipt.pdf",
        media_type="application/pdf",
        consent=True,
        scope=PERSONAL,
    )
    await service.resume(
        user_id=owner, connection_id=receipt.connection_id, scope=PERSONAL
    )
    extractor.extract.assert_awaited_once()
    bridge.check_attachment_preparation.assert_not_called()
    bridge.prepare_attachment.assert_not_called()


@pytest.mark.asyncio
async def test_failed_canonical_save_keeps_batch_for_retry(document_bridge):
    service, bridge, extractor, sink = document_bridge
    bridge.prepare_attachment.side_effect = [
        DocumentServiceError("document_delivery_failed"),
        None,
    ]
    scope = BusinessSpace(str(uuid4()))
    owner = str(uuid4())
    receipt = await service.upload(
        user_id=owner,
        content=b"%PDF-fixture",
        filename="receipt.pdf",
        media_type="application/pdf",
        consent=True,
        scope=scope,
    )
    with pytest.raises(DocumentServiceError, match="document_delivery_failed"):
        await service.resume(
            user_id=owner, connection_id=receipt.connection_id, scope=scope
        )
    assert (
        service.store.get(user_id=owner, connection_id=receipt.connection_id) is not None
    )
    await service.resume(user_id=owner, connection_id=receipt.connection_id, scope=scope)
    extractor.extract.assert_awaited_once()
    sink.ingest.assert_not_called()


@pytest.mark.asyncio
async def test_unwired_business_preparation_fails_before_provider(document_bridge):
    service, _, extractor, _ = document_bridge
    service.business_actions = None
    scope = BusinessSpace(str(uuid4()))
    owner = str(uuid4())
    receipt = await service.upload(
        user_id=owner,
        content=b"%PDF-fixture",
        filename="receipt.pdf",
        media_type="application/pdf",
        consent=True,
        scope=scope,
    )
    with pytest.raises(DocumentServiceError, match="business_preparation_unavailable"):
        await service.resume(
            user_id=owner, connection_id=receipt.connection_id, scope=scope
        )
    extractor.extract.assert_not_awaited()
