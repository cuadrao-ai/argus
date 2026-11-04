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
from tests.ingestion.test_document_jobs_api import observation

fake = Faker("es_MX")


class Provider:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, **kwargs: object) -> ExtractionResult:
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
    "code",
    [
        "missing_api_key", "document_extraction_disabled", "missing_vision_model",
        "encrypted_document", "invalid_document", "document_page_limit",
        "unreadable_image",
    ],
)
@pytest.mark.asyncio
async def test_every_local_refusal_preserves_budget(rig, monkeypatch, media_type, code):
    service, provider, scope, owner = rig
    monkeypatch.setattr(preparation, "_run", poppler("Pages: 1\nEncrypted: no\n"))
    with monkeypatch.context() as refusal:
        if code == "missing_api_key":
            refusal.setattr(extraction, "resolve_openrouter_api_key", lambda *_: "")
        elif code == "missing_vision_model":
            refusal.setattr(extraction, "resolve_openrouter_model", lambda **_: "")
        elif code == "document_extraction_disabled":
            refusal.setattr(service.extractor.settings, "enabled", False)
        else:
            # Inject each preparation refusal at the shared decoder boundary.
            # The ordering invariant applies regardless of the source format.
            def refuse(*args, **kwargs):
                raise DocumentExtractionError(code)
            refusal.setattr(extraction, "prepare_document", refuse)
        refused, _ = await read(service, owner, scope, media_type)
        assert refused == code
        assert provider.calls == 0
        assert service.read_budget._reads == {}
    result, draft = await read(service, owner, scope, media_type)
    assert (result, draft.status) == (None, "review_ready")
    assert provider.calls == 1
