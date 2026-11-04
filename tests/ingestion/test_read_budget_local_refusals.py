"""A file the local preparation refuses never spends a read: the budget is
charged after preparation succeeds and right before the provider is reached."""

from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest
from argus.domain.business.read_budget import InMemoryReadBudget, ReadBudgetSettings
from argus.domain.ingestion.connections import InMemoryConnectionRepository
from argus.domain.ingestion.documents import extractor as extraction
from argus.domain.ingestion.documents import preparation
from argus.domain.ingestion.documents.config import DocumentExtractionSettings
from argus.domain.ingestion.documents.jobs import PreparationJobs
from argus.domain.ingestion.documents.models import (
    DocumentExtractionError,
    ExtractionResult,
)
from argus.domain.ingestion.documents.service import (
    DocumentServiceError,
    DocumentsService,
)
from argus.domain.ingestion.documents.store import InMemoryDocumentStore
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.owner_scope import BusinessSpace
from faker import Faker
from PIL import Image

from tests.business_reading_support import reading_setting, turn_reading
from tests.document_extractor_support import admit
from tests.ingestion.test_document_jobs_api import observation

fake = Faker("es_MX")


class Provider:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, **kwargs: object) -> ExtractionResult:
        await admit(kwargs.get("before_request"))
        self.calls += 1
        return ExtractionResult.model_validate(observation("250.50"))


def poppler(pdfinfo: str):
    """A stand-in for the poppler tools: ``pdfinfo`` answers ``pdfinfo``,
    ``pdftotext`` answers nothing, ``pdftoppm`` renders one blank page."""

    def run(args: list[str], output: Path) -> None:
        if args[0] == "pdfinfo":
            output.write_text(pdfinfo)
        elif args[0] == "pdftoppm":
            page = io.BytesIO()
            Image.new("RGB", (40, 40), "white").save(page, format="JPEG")
            Path(args[-1]).with_suffix(".jpg").write_bytes(page.getvalue())
            output.write_text("")
        else:
            output.write_text("")

    return run


@pytest.fixture
def rig(monkeypatch):
    monkeypatch.setenv("ARGUS_VISION_MODEL", "test/vision")
    monkeypatch.setenv("OPENROUTER_API_KEY", "offline-test-key")
    provider = Provider()
    monkeypatch.setattr(extraction, "invoke_openrouter_json_schema", provider)
    repo = InMemoryConnectionRepository()
    hub = IngestionHub(
        repo, box=None, sink=Mock(), clock=lambda: datetime.now(timezone.utc)
    )
    service = DocumentsService(
        hub,
        InMemoryDocumentStore(repo),
        extraction.DocumentExtractor(DocumentExtractionSettings(enabled=True)),
        business_actions=Mock(),
        read_budget=InMemoryReadBudget(ReadBudgetSettings(per_day=1)),
    )
    service.business_receipt_consent = reading_setting()
    scope, owner = BusinessSpace(str(uuid4())), str(uuid4())
    turn_reading(service.business_receipt_consent, scope.space_id, owner)
    return service, provider, scope, owner


async def read(
    service: DocumentsService, owner: str, scope: BusinessSpace,
    media_type: str = "application/pdf",
):  # noqa: ANN201
    if media_type == "image/png":
        image = io.BytesIO()
        Image.new("RGB", (40, 40), fake.hex_color()).save(image, format="PNG")
        content = image.getvalue()
    else:
        content = b"%PDF-" + fake.uuid4().encode()
    outcome = await service.upload(
        user_id=owner,
        content=content,
        filename=fake.file_name(extension="pdf"),
        media_type=media_type,
        consent=True,
        scope=scope,
    )
    try:
        await service.resume(
            user_id=owner, connection_id=outcome.connection_id, scope=scope
        )
    except (DocumentServiceError, DocumentExtractionError) as error:
        code = error.code
    else:
        code = None
    draft = service.get(user_id=owner, connection_id=outcome.connection_id, scope=scope)
    return code, draft


@pytest.mark.parametrize(
    "pdfinfo,code",
    [
        ("Pages: 1\nEncrypted: yes (print:yes)\n", "encrypted_document"),
        ("", "invalid_document"),
        ("Pages: 9\nEncrypted: no\n", "document_page_limit"),
    ],
)
@pytest.mark.asyncio
async def test_a_file_refused_locally_spends_no_read(rig, monkeypatch, pdfinfo, code):
    service, provider, scope, owner = rig
    monkeypatch.setattr(preparation, "_run", poppler(pdfinfo))
    refused, draft = await read(service, owner, scope)
    assert refused == code
    assert (draft.status, draft.error_code) == ("needs_attention", code)
    assert provider.calls == 0

    monkeypatch.setattr(preparation, "_run", poppler("Pages: 1\nEncrypted: no\n"))
    code, draft = await read(service, owner, scope)
    assert (code, draft.status) == (None, "review_ready"), "the day's one read was kept"
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_a_valid_file_charges_exactly_once(rig, monkeypatch):
    service, provider, scope, owner = rig
    monkeypatch.setattr(preparation, "_run", poppler("Pages: 1\nEncrypted: no\n"))
    code, draft = await read(service, owner, scope)
    assert (code, draft.status) == (None, "review_ready")
    code, draft = await read(service, owner, scope)
    assert (code, draft.error_code) == (
        "business_read_budget_day",
        "business_read_budget_day",
    )
    assert provider.calls == 1


@pytest.mark.parametrize("media_type", ["image/png", "application/pdf"])
@pytest.mark.parametrize(
    "refusal,code",
    [
        ("missing_api_key", "missing_api_key"),
        ("document_extraction_disabled", "document_extraction_disabled"),
        ("missing_vision_model", "missing_vision_model"),
        ("encrypted", "encrypted_document"),
        ("malformed", "invalid_document"),
        ("over_page_limit", "document_page_limit"),
        ("unreadable_image", "invalid_document"),
    ],
)
@pytest.mark.asyncio
async def test_every_local_refusal_preserves_budget(
    rig, monkeypatch, media_type, refusal, code
):
    service, provider, scope, owner = rig
    monkeypatch.setattr(preparation, "_run", poppler("Pages: 1\nEncrypted: no\n"))
    with monkeypatch.context() as patch:
        if code == "missing_api_key":
            patch.setattr(extraction, "resolve_openrouter_api_key", lambda *_: "")
        elif code == "missing_vision_model":
            patch.setattr(extraction, "resolve_openrouter_model", lambda **_: "")
        elif code == "document_extraction_disabled":
            patch.setattr(service.extractor.settings, "enabled", False)
        else:
            # Inject each preparation refusal at the shared decoder boundary.
            # The ordering invariant applies regardless of the source format.
            def refuse(*args, **kwargs):
                raise DocumentExtractionError(code)
            patch.setattr(extraction, "prepare_document", refuse)
        refused, _ = await read(service, owner, scope, media_type)
        assert refused == code
        assert provider.calls == 0
        assert service.read_budget._reads == {}
    result, draft = await read(service, owner, scope, media_type)
    assert (result, draft.status) == (None, "review_ready")
    assert provider.calls == 1


@pytest.mark.parametrize("media_type", ["image/png", "application/pdf"])
@pytest.mark.asyncio
async def test_unreadable_image_bytes_never_spend_budget(rig, monkeypatch, media_type):
    service, provider, scope, owner = rig
    render = poppler("Pages: 1\nEncrypted: no\n")

    def unreadable(args, output):
        render(args, output)
        if args[0] == "pdftoppm":
            Path(args[-1]).with_suffix(".jpg").write_bytes(b"not an image")

    monkeypatch.setattr(preparation, "_run", unreadable)
    with pytest.raises(DocumentExtractionError, match="invalid_document"):
        if media_type == "image/png":
            await service.upload(
                user_id=owner, content=b"not an image", filename="receipt.png",
                media_type=media_type, consent=True, scope=scope,
            )
        else:
            saved = await service.upload(
                user_id=owner, content=b"%PDF-fixture", filename="receipt.pdf",
                media_type=media_type, consent=True, scope=scope,
            )
            await service.resume(
                user_id=owner, connection_id=saved.connection_id, scope=scope
            )
    assert service.read_budget._reads == {}
    assert provider.calls == 0


@pytest.mark.parametrize("failure", ["reading", "attachment", "lease"])
@pytest.mark.parametrize("media_type", ["image/png", "application/pdf"])
@pytest.mark.asyncio
async def test_final_local_admission_refusal_never_spends_budget(
    rig, monkeypatch, failure, media_type
):
    service, provider, scope, owner = rig
    monkeypatch.setattr(preparation, "_run", poppler("Pages: 1\nEncrypted: no\n"))
    content = b"%PDF-fixture"
    if media_type == "image/png":
        image = io.BytesIO()
        Image.new("RGB", (40, 40), "white").save(image, format="PNG")
        content = image.getvalue()
    saved = await service.upload(
        user_id=owner, content=content, filename="receipt", media_type=media_type,
        consent=True, scope=scope,
    )
    jobs = PreparationJobs(service, None)
    jobs.start(user_id=owner, connection_id=saved.connection_id)
    attempt = service.store.job(user_id=owner, connection_id=saved.connection_id)
    if failure == "reading":
        monkeypatch.setattr(service, "_reading_allowed", Mock(side_effect=[True, False]))
        code = "document_reading_not_allowed"
    elif failure == "attachment":
        code = "document_preparation_refused"
        service.business_actions.check_attachment_preparation.side_effect = [
            None, DocumentServiceError(code)
        ]
    else:
        code = "document_lease_lost"
        monkeypatch.setattr(service.store, "mark_provider_call", lambda **_: False)
    with pytest.raises(DocumentServiceError, match=code):
        await service.resume(
            user_id=owner, connection_id=saved.connection_id, scope=scope,
            attempt_id=attempt.attempt_id,
        )
    assert service.read_budget._reads == {}
    assert provider.calls == 0


@pytest.mark.asyncio
async def test_saved_batch_replay_never_prepares_or_charges_again(rig, monkeypatch):
    service, provider, scope, owner = rig
    monkeypatch.setattr(preparation, "_run", poppler("Pages: 1\nEncrypted: no\n"))
    code, draft = await read(service, owner, scope)
    assert code is None
    before = dict(service.read_budget._reads)
    monkeypatch.setattr(service.extractor, "prepare", Mock(side_effect=AssertionError))
    await service.resume(user_id=owner, connection_id=draft.connection_id, scope=scope)
    assert service.read_budget._reads == before
    assert provider.calls == 1
