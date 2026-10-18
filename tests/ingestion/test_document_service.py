"""Document retries replay the saved extraction and never write money."""

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from argus.domain.ingestion.connections import (
    ConnectionNotFound,
    InMemoryConnectionRepository,
)
from argus.domain.ingestion.contract import ImportCandidate, SourceRef
from argus.domain.ingestion.documents.models import ExtractionBatch
from argus.domain.ingestion.documents.service import (
    DocumentOutcome,
    DocumentServiceError,
    DocumentsService,
)
from argus.domain.ingestion.documents.store import InMemoryDocumentStore
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.sink import SubmitResult
from argus.domain.owner_scope import PERSONAL
from faker import Faker

fake = Faker()
Rig = tuple[DocumentsService, IngestionHub, Mock, Mock]


@pytest.fixture
def rig() -> Rig:
    now = datetime.now(timezone.utc)
    repo = InMemoryConnectionRepository()
    sink = Mock()
    sink.submit.return_value = SubmitResult(1, 0, 0)
    hub = IngestionHub(repo, box=None, sink=sink, clock=lambda: now)
    extractor = Mock()

    async def extract(**kwargs: Any) -> ExtractionBatch:
        candidate = ImportCandidate(
            source=SourceRef(
                source="statement",
                connection_id=kwargs["connection_id"],
                external_id="document:p1:r1",
                observed_at=kwargs["observed_at"],
            ),
            evidence="transaction",
            amount="129.50",
            currency="DOP",
            direction="outflow",
        )
        return ExtractionBatch(candidates=(candidate,), metadata={})

    extractor.extract = AsyncMock(side_effect=extract)
    store = InMemoryDocumentStore(repo)
    return DocumentsService(hub, store, extractor), hub, extractor, sink


async def upload(service: DocumentsService, user: str) -> DocumentOutcome:
    captured = await service.upload(
        user_id=user,
        content=b"%PDF-fixture",
        filename="statement.pdf",
        media_type="application/pdf",
        consent=True,
        scope=PERSONAL,
    )
    return await service.resume(
        user_id=user, connection_id=captured.connection_id, scope=PERSONAL
    )


@pytest.mark.asyncio
async def test_a_venta_keeps_its_type_and_a_retitle_is_refused(rig: Rig) -> None:
    service, _, _, _ = rig
    user = fake.uuid4()
    saved = await service.upload(
        user_id=user,
        content=b"%PDF-fixture",
        filename="factura.pdf",
        media_type="application/pdf",
        consent=False,
        scope=PERSONAL,
        document_type="venta",
    )
    draft = service.get(user_id=user, connection_id=saved.connection_id, scope=PERSONAL)
    assert draft.document_type == "venta"
    again = await service.upload(
        user_id=user,
        content=b"%PDF-fixture",
        filename="factura.pdf",
        media_type="application/pdf",
        consent=False,
        scope=PERSONAL,
        document_type="venta",
    )
    assert again.replayed is True
    with pytest.raises(DocumentServiceError) as refused:
        await service.upload(
            user_id=user,
            content=b"%PDF-fixture",
            filename="factura.pdf",
            media_type="application/pdf",
            consent=False,
            scope=PERSONAL,
            document_type="recibo",
        )
    assert refused.value.code == "document_type_conflict"


@pytest.mark.asyncio
async def test_same_document_replays_without_extracting_again(rig: Rig) -> None:
    service, hub, extractor, sink = rig
    user = fake.uuid4()
    first = await upload(service, user)
    second = await upload(service, user)
    assert first.connection_id == second.connection_id
    assert not first.replayed and second.replayed
    assert second.candidate_count == 1
    assert extractor.extract.await_count == 1
    assert sink.submit.call_count == 2
    assert sink.submit.call_args_list[0] == sink.submit.call_args_list[1]
    assert (
        hub.connections.get(
            user_id=user, connection_id=first.connection_id, scope=PERSONAL
        ).lease_holder
        is None
    )


@pytest.mark.asyncio
async def test_identical_files_are_isolated_by_owner(rig: Rig) -> None:
    service, _, extractor, _ = rig
    owner, other = fake.uuid4(), fake.uuid4()
    first, second = await upload(service, owner), await upload(service, other)
    assert first.connection_id != second.connection_id
    assert extractor.extract.await_count == 2
    with pytest.raises(ConnectionNotFound):
        await service.resume(
            user_id=other, connection_id=first.connection_id, scope=PERSONAL
        )


@pytest.mark.asyncio
async def test_sink_failure_resumes_saved_batch_without_provider(rig: Rig) -> None:
    service, hub, extractor, sink = rig
    user = fake.uuid4()
    sink.submit.side_effect = RuntimeError("storage unavailable")
    with pytest.raises(DocumentServiceError, match="document_delivery_failed"):
        await upload(service, user)
    row = hub.connections.list(user_id=user, scope=PERSONAL)[0]
    assert row.status == "error"
    sink.submit.side_effect = None
    result = await service.resume(user_id=user, connection_id=row.id, scope=PERSONAL)
    assert result.replayed
    assert extractor.extract.await_count == 1


@pytest.mark.asyncio
async def test_disconnect_removes_saved_content_and_blocks_resume(rig: Rig) -> None:
    service, hub, _, sink = rig
    sink.forget_connection.return_value = 1
    user = fake.uuid4()
    first = await upload(service, user)
    hub.disconnect(user_id=user, connection_id=first.connection_id, scope=PERSONAL)
    assert service.store.get(user_id=user, connection_id=first.connection_id) is None
    with pytest.raises(DocumentServiceError, match="document_disconnected"):
        await service.resume(
            user_id=user, connection_id=first.connection_id, scope=PERSONAL
        )


@pytest.mark.asyncio
async def test_resume_without_checkpoint_requires_reupload(rig: Rig) -> None:
    service, hub, extractor, _ = rig
    user = fake.uuid4()
    row = hub.connections.create(
        user_id=user,
        source="statement",
        external_ref=fake.uuid4(),
        label=None,
        now=hub.clock(),
        scope=PERSONAL,
    )
    with pytest.raises(DocumentServiceError, match="document_source_unavailable"):
        await service.resume(user_id=user, connection_id=row.id, scope=PERSONAL)
    extractor.extract.assert_not_awaited()


@pytest.mark.asyncio
async def test_expired_worker_cannot_save_or_deliver(rig: Rig) -> None:
    service, hub, extractor, sink = rig
    user = fake.uuid4()
    original = extractor.extract.side_effect

    async def expired(**kwargs: Any) -> ExtractionBatch:
        batch = await original(**kwargs)
        old = hub.clock()
        hub.clock = lambda: old + timedelta(minutes=6)
        return batch

    extractor.extract.side_effect = expired
    with pytest.raises(DocumentServiceError, match="document_lease_lost"):
        await upload(service, user)
    sink.submit.assert_not_called()
    row = hub.connections.list(user_id=user, scope=PERSONAL)[0]
    assert service.store.get(user_id=user, connection_id=row.id) is None


@pytest.mark.asyncio
async def test_disconnect_during_extraction_never_recreates_content(rig: Rig) -> None:
    service, hub, extractor, sink = rig
    user = fake.uuid4()
    original = extractor.extract.side_effect

    async def disconnect(**kwargs: Any) -> ExtractionBatch:
        batch = await original(**kwargs)
        hub.disconnect(
            user_id=user, connection_id=kwargs["connection_id"], scope=PERSONAL
        )
        return batch

    extractor.extract.side_effect = disconnect
    with pytest.raises(DocumentServiceError, match="document_lease_lost"):
        await upload(service, user)
    sink.submit.assert_not_called()
    row = hub.connections.list(user_id=user, scope=PERSONAL)[0]
    assert service.store.get(user_id=user, connection_id=row.id) is None


@pytest.mark.asyncio
async def test_completed_delivery_with_failed_cursor_replays_saved_candidates(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, hub, extractor, sink = rig
    user = fake.uuid4()
    original = hub.connections.record_success
    monkeypatch.setattr(hub.connections, "record_success", lambda **_: False)
    with pytest.raises(DocumentServiceError, match="document_lease_lost"):
        await upload(service, user)
    submitted = sink.submit.call_args
    monkeypatch.setattr(hub.connections, "record_success", original)
    result = await upload(service, user)
    assert result.replayed
    assert extractor.extract.await_count == 1
    assert sink.submit.call_count == 2
    assert sink.submit.call_args == submitted


@pytest.mark.asyncio
async def test_concurrent_duplicate_is_busy_and_does_not_call_provider_twice(
    rig: Rig,
) -> None:
    import asyncio

    service, _, extractor, _ = rig
    user = fake.uuid4()
    started, finish = asyncio.Event(), asyncio.Event()
    original = extractor.extract.side_effect

    async def blocked(**kwargs: Any) -> ExtractionBatch:
        started.set()
        await finish.wait()
        return await original(**kwargs)

    extractor.extract.side_effect = blocked
    task = asyncio.create_task(upload(service, user))
    await started.wait()
    try:
        with pytest.raises(DocumentServiceError, match="document_busy"):
            await upload(service, user)
    finally:
        finish.set()
        await task
    assert extractor.extract.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["foreign", "duplicates", "removed"])
async def test_invalid_candidate_batch_never_reaches_checkpoint_or_sink(
    rig: Rig, invalid: str
) -> None:
    service, hub, extractor, sink = rig
    user = fake.uuid4()
    original = extractor.extract.side_effect

    async def invalid_extract(**kwargs: Any) -> ExtractionBatch:
        batch = await original(**kwargs)
        candidate = batch.candidates[0]
        if invalid == "empty":
            candidates = ()
        elif invalid == "foreign":
            candidates = (
                candidate.model_copy(
                    update={
                        "source": candidate.source.model_copy(
                            update={"connection_id": fake.uuid4()}
                        )
                    }
                ),
            )
        elif invalid == "duplicates":
            candidates = (candidate, candidate)
        else:
            candidates = (candidate.model_copy(update={"status": "removed"}),)
        return batch.model_copy(update={"candidates": candidates})

    extractor.extract.side_effect = invalid_extract
    with pytest.raises(DocumentServiceError):
        await upload(service, user)
    sink.submit.assert_not_called()
    row = hub.connections.list(user_id=user, scope=PERSONAL)[0]
    assert service.store.get(user_id=user, connection_id=row.id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["validation", "storage"])
async def test_upload_keeps_event_loop_free_during_blocking_capture(
    rig, monkeypatch, phase
):
    import asyncio
    import io
    import threading

    from argus.domain.ingestion.documents import service as module
    from PIL import Image

    source = io.BytesIO()
    Image.new("RGB", (40, 40), "white").save(source, format="PNG")
    service, _, _, _ = rig
    entered, release = threading.Event(), threading.Event()
    target = module if phase == "validation" else service.store
    name = "validate_source" if phase == "validation" else "capture"
    original = getattr(target, name)

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(2), "event loop could not release the worker"
        return original(*args, **kwargs)

    monkeypatch.setattr(target, name, blocked)
    task = asyncio.create_task(
        service.upload(
            user_id=fake.uuid4(),
            content=source.getvalue(),
            filename="receipt.png",
            media_type="image/png",
            scope=PERSONAL,
        )
    )
    try:
        for _ in range(100):
            if entered.is_set():
                break
            await asyncio.sleep(0.005)
        assert entered.is_set()
        assert not task.done()
    finally:
        release.set()
        await task


@pytest.mark.asyncio
async def test_cancelled_capture_settles_before_next_upload_and_replays(rig, monkeypatch):
    import asyncio
    import threading

    service, hub, _, _ = rig
    user = fake.uuid4()
    entered, release = threading.Event(), threading.Event()
    original = service.store.capture
    captures = []

    def blocked(**kwargs):
        captures.append(kwargs["draft"].connection_id)
        if len(captures) == 1:
            entered.set()
            assert release.wait(2)
        return original(**kwargs)

    monkeypatch.setattr(service.store, "capture", blocked)

    async def send():
        return await service.upload(
            user_id=user,
            content=b"%PDF-fixture",
            filename="receipt.pdf",
            media_type="application/pdf",
            scope=PERSONAL,
        )

    first = asyncio.create_task(send())
    second = None
    try:
        for _ in range(100):
            if entered.is_set():
                break
            await asyncio.sleep(0.005)
        assert entered.is_set()
        first.cancel()
        await asyncio.sleep(0)
        first.cancel()
        second = asyncio.create_task(send())
        await asyncio.sleep(0.02)
        assert not first.done() and not second.done()
        assert len(captures) == 1
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await first
        if second is not None:
            replay = await second
    assert replay.replayed
    assert captures == [replay.connection_id, replay.connection_id]
    assert len(hub.connections.list(user_id=user, scope=PERSONAL)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_type", [SystemExit, KeyboardInterrupt])
async def test_capture_transports_process_exception_to_caller(
    rig, monkeypatch, failure_type
):
    service, _, _, _ = rig
    failure = failure_type("synthetic source-store interruption")
    original = service.store.capture

    def interrupt(**kwargs):
        raise failure

    monkeypatch.setattr(service.store, "capture", interrupt)
    with pytest.raises(failure_type) as caught:
        await service.upload(
            user_id=fake.uuid4(),
            content=b"%PDF-fixture",
            filename="receipt.pdf",
            media_type="application/pdf",
            scope=PERSONAL,
        )
    assert caught.value is failure
    monkeypatch.setattr(service.store, "capture", original)
    # The exception settles the operation and releases capacity for the next source.
    outcome = await service.upload(
        user_id=fake.uuid4(),
        content=b"%PDF-next",
        filename="next.pdf",
        media_type="application/pdf",
        scope=PERSONAL,
    )
    assert outcome.status == "saved"
