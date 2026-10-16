import base64
import hashlib
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from argus.domain.ingestion.documents import extractor as extraction
from argus.domain.ingestion.documents import rebuilt
from argus.domain.ingestion.documents.config import DocumentExtractionSettings
from argus.domain.ingestion.documents.preparation import PreparedDocument
from argus.domain.ingestion.documents.service import DocumentServiceError
from argus.domain.owner_scope import PERSONAL

from tests.ingestion.test_document_extraction import result
from tests.ingestion.test_document_rebuilt import image_bytes
from tests.ingestion.test_document_service import rig  # noqa: F401


@pytest.mark.asyncio
@pytest.mark.parametrize("download_first", [False, True])
async def test_image_extraction_reuses_one_copy_and_preserves_original_identity(
    rig, monkeypatch, download_first  # noqa: F811
):
    service, _, extractor, _ = rig
    original = image_bytes()
    saved = await service.upload(
        user_id="owner",
        content=original,
        filename="source.png",
        media_type="image/png",
        consent=True,
        scope=PERSONAL,
    )
    decode = Mock(wraps=rebuilt.rebuild_image)
    monkeypatch.setattr(rebuilt, "rebuild_image", decode)
    if download_first:
        service.source_bytes(
            user_id="owner", connection_id=saved.connection_id, scope=PERSONAL
        )
    await service.resume(
        user_id="owner", connection_id=saved.connection_id, scope=PERSONAL
    )
    assert decode.call_count == 1
    arguments = extractor.extract.call_args.kwargs
    assert arguments["content"] == original
    assert arguments["media_type"] == "image/png"
    assert arguments["filename"] == "source.png"
    stored = service.store.rebuilt(user_id="owner", connection_id=saved.connection_id)
    assert stored[0] == "image/jpeg"
    assert arguments["prepared"].images == (stored[1],)
    assert (
        service.store.source(user_id="owner", connection_id=saved.connection_id)
        == original
    )
    assert (
        service.get(
            user_id="owner", connection_id=saved.connection_id, scope=PERSONAL
        ).sha256
        == hashlib.sha256(original).hexdigest()
    )
    assert (
        service.source_bytes(
            user_id="owner", connection_id=saved.connection_id, scope=PERSONAL
        )
        == stored[1]
    )
    assert decode.call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content,media_type",
    [(b"%PDF-fixture", "application/pdf"), (b"Purchase 25 DOP", "text/plain")],
)
async def test_nonimage_extraction_keeps_original_path(rig, content, media_type):  # noqa: F811
    service, _, extractor, _ = rig
    saved = await service.upload(
        user_id="owner",
        content=content,
        filename="source",
        media_type=media_type,
        consent=True,
        scope=PERSONAL,
    )
    await service.resume(
        user_id="owner", connection_id=saved.connection_id, scope=PERSONAL
    )
    assert extractor.extract.call_args.kwargs["content"] == content
    assert "prepared" not in extractor.extract.call_args.kwargs
    assert (
        service.store.rebuilt(user_id="owner", connection_id=saved.connection_id) is None
    )


@pytest.mark.asyncio
async def test_deleted_copy_is_not_sent_to_extractor(rig, monkeypatch):  # noqa: F811
    service, _, extractor, _ = rig
    saved = await service.upload(
        user_id="owner",
        content=image_bytes(),
        filename="source.png",
        media_type="image/png",
        consent=True,
        scope=PERSONAL,
    )
    monkeypatch.setattr(service.store, "save_rebuilt", lambda **kwargs: False)
    with pytest.raises(DocumentServiceError, match="document_source_unavailable"):
        await service.resume(
            user_id="owner", connection_id=saved.connection_id, scope=PERSONAL
        )
    extractor.extract.assert_not_awaited()
    assert (
        service.store.source(user_id="owner", connection_id=saved.connection_id)
        is not None
    )


@pytest.mark.asyncio
async def test_storage_failure_stays_retryable_and_does_not_call_extractor(
    rig, monkeypatch  # noqa: F811
):
    from argus.domain.ingestion.documents.objects import SourceStorageUnavailable

    service, _, extractor, _ = rig
    saved = await service.upload(
        user_id="owner",
        content=image_bytes(),
        filename="source.png",
        media_type="image/png",
        consent=True,
        scope=PERSONAL,
    )
    monkeypatch.setattr(
        service.store,
        "save_rebuilt",
        Mock(side_effect=SourceStorageUnavailable("unavailable")),
    )
    with pytest.raises(DocumentServiceError) as error:
        await service.resume(
            user_id="owner", connection_id=saved.connection_id, scope=PERSONAL
        )
    assert error.value.code == "document_storage_unavailable"
    assert error.value.retryable
    extractor.extract.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("reuse", [False, True])
async def test_extractor_preserves_original_provenance_with_prepared_copy(
    monkeypatch, reuse
):
    original = image_bytes()
    jpeg = rebuilt.rebuild_image(original, "image/png")
    prepared = PreparedDocument(1, (jpeg,))
    prepare = Mock(return_value=prepared)
    invoke = AsyncMock(return_value=result())
    monkeypatch.setattr(extraction, "prepare_document", prepare)
    monkeypatch.setattr(
        extraction, "resolve_openrouter_model", lambda **kwargs: "fixture"
    )
    monkeypatch.setattr(extraction, "resolve_openrouter_api_key", lambda *args: "fixture")
    monkeypatch.setattr(extraction, "invoke_openrouter_json_schema", invoke)
    batch = await extraction.DocumentExtractor(
        DocumentExtractionSettings(enabled=True)
    ).extract(
        original,
        "source.png",
        "image/png",
        "receipt",
        datetime.now(timezone.utc),
        **({"prepared": prepared} if reuse else {}),
    )
    assert prepare.call_count == (0 if reuse else 1)
    digest = hashlib.sha256(original).hexdigest()
    assert batch.metadata["sha256"] == digest
    assert batch.metadata["media_type"] == "image/png"
    assert batch.candidates[0].source.external_id.startswith(digest + ":")
    attachment = batch.candidates[0].attachments[0]
    assert attachment.sha256 == digest
    assert attachment.size_bytes == len(original)
    assert attachment.media_type == "image/png"
    assert attachment.filename == "source.png"
    blocks = invoke.call_args.kwargs["messages"][1]["content"]
    assert blocks[2]["image_url"]["url"] == "data:image/jpeg;base64," + base64.b64encode(
        jpeg
    ).decode("ascii")
