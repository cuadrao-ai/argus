"""A Business reads only inside its day and month budget. Over it, the receipt
stays saved and unread with the reason, and reads again when the budget allows.
Every channel's read passes the same owner, so WhatsApp and web count together."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from argus.domain.business.read_budget import InMemoryReadBudget, ReadBudgetSettings
from argus.domain.ingestion.connections import InMemoryConnectionRepository
from argus.domain.ingestion.documents.jobs import PreparationJobs, run_attempt
from argus.domain.ingestion.documents.models import ExtractionBatch
from argus.domain.ingestion.documents.service import (
    DocumentServiceError,
    DocumentsService,
)
from argus.domain.ingestion.documents.store import InMemoryDocumentStore
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.owner_scope import PERSONAL, BusinessSpace
from faker import Faker

from tests.business_reading_support import reading_setting, turn_reading
from tests.document_extractor_support import start_request
from tests.ingestion.test_whatsapp_receipt_reading import _send, _status, _world

fake = Faker("es_MX")


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 4, 15, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def rig():
    repo = InMemoryConnectionRepository()
    clock = Clock()
    hub = IngestionHub(repo, box=None, sink=Mock(), clock=clock)
    async def extract(**kwargs):
        await start_request(kwargs)
        extractor.provider_calls += 1
        return ExtractionBatch(candidates=())

    extractor = Mock(extract=AsyncMock(side_effect=extract), provider_calls=0)
    service = DocumentsService(
        hub, InMemoryDocumentStore(repo), extractor, business_actions=Mock()
    )
    service.business_receipt_consent = reading_setting()
    return service, extractor, clock


def budget(service: DocumentsService, **limits: int) -> InMemoryReadBudget:
    service.read_budget = InMemoryReadBudget(ReadBudgetSettings(**limits))
    return service.read_budget


def business(service: DocumentsService) -> tuple[BusinessSpace, str]:
    scope, owner = BusinessSpace(str(uuid4())), str(uuid4())
    turn_reading(service.business_receipt_consent, scope.space_id, owner)
    return scope, owner


async def queued(service: DocumentsService, owner: str, scope) -> str:  # noqa: ANN001
    outcome = await service.upload(
        user_id=owner,
        content=b"%PDF-" + fake.uuid4().encode(),
        filename=fake.file_name(extension="pdf"),
        media_type="application/pdf",
        consent=True,
        scope=scope,
    )
    return outcome.connection_id


async def read(service: DocumentsService, owner: str, scope, connection: str):  # noqa: ANN001
    return await service.resume(user_id=owner, connection_id=connection, scope=scope)


@pytest.mark.asyncio
async def test_the_read_over_the_day_budget_stays_saved_with_the_reason(rig):
    service, extractor, _ = rig
    budget(service, per_day=2)
    scope, owner = business(service)
    receipts = [await queued(service, owner, scope) for _ in range(3)]
    for receipt in receipts[:2]:
        assert (await read(service, owner, scope, receipt)).status == "review_ready"
    with pytest.raises(DocumentServiceError, match="business_read_budget_day"):
        await read(service, owner, scope, receipts[2])
    draft = service.get(user_id=owner, connection_id=receipts[2], scope=scope)
    assert (draft.status, draft.consent, draft.error_code) == (
        "saved",
        False,
        "business_read_budget_day",
    )
    assert draft.source_available
    assert not service.read_pending(owner, receipts[2], draft)
    assert extractor.provider_calls == 2


@pytest.mark.asyncio
async def test_another_business_still_reads_when_one_is_over_budget(rig):
    service, extractor, _ = rig
    budget(service, per_day=1)
    first, owner = business(service)
    second, other = business(service)
    await read(service, owner, first, await queued(service, owner, first))
    with pytest.raises(DocumentServiceError, match="business_read_budget_day"):
        await read(service, owner, first, await queued(service, owner, first))
    assert (
        await read(service, other, second, await queued(service, other, second))
    ).status == "review_ready"
    assert extractor.provider_calls == 2


@pytest.mark.asyncio
async def test_the_month_budget_counts_every_day_of_the_month(rig):
    service, extractor, clock = rig
    budget(service, per_day=300, per_month=2)
    scope, owner = business(service)
    for _ in range(2):
        await read(service, owner, scope, await queued(service, owner, scope))
        clock.now += timedelta(days=1)
    refused = await queued(service, owner, scope)
    with pytest.raises(DocumentServiceError, match="business_read_budget_month"):
        await read(service, owner, scope, refused)
    draft = service.get(user_id=owner, connection_id=refused, scope=scope)
    assert (draft.status, draft.error_code) == ("saved", "business_read_budget_month")
    clock.now = datetime(2026, 12, 1, 15, tzinfo=timezone.utc)
    service.queue(user_id=owner, connection_id=refused, consent=True, scope=scope)
    assert (await read(service, owner, scope, refused)).status == "review_ready"
    assert extractor.provider_calls == 3


@pytest.mark.asyncio
async def test_a_refused_receipt_reads_again_the_next_day_when_asked(rig):
    service, extractor, clock = rig
    budget(service, per_day=1)
    scope, owner = business(service)
    await read(service, owner, scope, await queued(service, owner, scope))
    refused = await queued(service, owner, scope)
    with pytest.raises(DocumentServiceError):
        await read(service, owner, scope, refused)
    clock.now += timedelta(days=1)
    service.queue(user_id=owner, connection_id=refused, consent=True, scope=scope)
    assert (await read(service, owner, scope, refused)).status == "review_ready"
    assert (
        service.get(user_id=owner, connection_id=refused, scope=scope).error_code is None
    )
    assert extractor.provider_calls == 2


@pytest.mark.asyncio
async def test_a_personal_read_has_no_business_budget(rig):
    service, extractor, _ = rig
    budget(service, per_day=1)
    owner = str(uuid4())
    for _ in range(2):
        await read(service, owner, PERSONAL, await queued(service, owner, PERSONAL))
    assert extractor.provider_calls == 2


@pytest.mark.asyncio
async def test_a_refused_pull_attempt_is_not_pulled_or_swept_again(rig):
    service, extractor, _ = rig
    budget(service, per_day=1)
    scope, owner = business(service)
    jobs = PreparationJobs(service)
    read_first, refused = [await queued(service, owner, scope) for _ in range(2)]
    for receipt in (read_first, refused):
        jobs.start(user_id=owner, connection_id=receipt)
        attempt = service.store.job(user_id=owner, connection_id=receipt).attempt_id
        outcome = await run_attempt(service, receipt, attempt)
        assert outcome == (
            "prepared" if receipt == read_first else "business_read_budget_day"
        )
    assert service.store.pending(limit=10) == []
    assert jobs.sweep().redispatched == []
    assert service.store.pull(now=service.hub.clock(), cap=3) is None
    assert extractor.provider_calls == 1


@pytest.mark.asyncio
async def test_a_whatsapp_read_spends_the_same_budget_as_the_web() -> None:
    world, extractor, _ = _world(on=True)
    budget(world.documents, per_day=1)
    scope = world.business(world.alice)
    by_whatsapp = await _send(world, "wamid.BUDGET-1")
    assert _status(world, by_whatsapp) == "review_ready"
    by_web = await queued(world.documents, world.alice, scope)
    with pytest.raises(DocumentServiceError, match="business_read_budget_day"):
        await read(world.documents, world.alice, scope, by_web)
    assert extractor.calls == 1
