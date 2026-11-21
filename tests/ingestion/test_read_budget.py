"""A Business reads only inside its day and month budget. Over it, the receipt
stays saved and unread with the reason, and reads again when the budget allows.
Every channel's read passes the same owner, so WhatsApp and web count together."""

from __future__ import annotations

import asyncio
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
from workflows.read_resume import ReadResume

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


async def refused_by_the_day(service, owner, scope) -> str:  # noqa: ANN001
    """One read spends the day; the next is refused through the worker's path."""
    jobs = PreparationJobs(service)
    read_first, refused = [await queued(service, owner, scope) for _ in range(2)]
    for receipt in (read_first, refused):
        jobs.start(user_id=owner, connection_id=receipt)
        attempt = service.store.job(user_id=owner, connection_id=receipt).attempt_id
        outcome = await run_attempt(service, receipt, attempt)
        assert outcome == (
            "prepared" if receipt == read_first else "business_read_budget_day"
        )
    return refused


async def resumed(service: DocumentsService) -> dict[str, int]:
    """One pass, on a thread as the worker's upkeep runs it."""
    return await asyncio.to_thread(ReadResume(service).run, service.hub.clock())


@pytest.mark.asyncio
async def test_a_refused_read_waits_out_its_day_then_resumes_on_its_own(rig):
    service, extractor, clock = rig
    budget(service, per_day=1)
    scope, owner = business(service)
    refused = await refused_by_the_day(service, owner, scope)
    spent = service.store.job(user_id=owner, connection_id=refused)
    assert spent.provider_calls == 1
    assert service.store.pending(now=clock(), limit=10) == []
    assert PreparationJobs(service).sweep().redispatched == []
    assert await resumed(service) == {"due": 0, "requeued": 0}
    assert service.store.pull(now=clock(), cap=3) is None
    clock.now += timedelta(days=1)
    assert await resumed(service) == {"due": 1, "requeued": 1}
    fresh = service.store.job(user_id=owner, connection_id=refused)
    assert (fresh.attempt, fresh.provider_calls, fresh.asked_at) == (1, 0, clock())
    assert fresh.attempt_id != spent.attempt_id
    assert await resumed(service) == {"due": 0, "requeued": 0}
    pulled = service.store.pull(now=clock(), cap=3)
    assert pulled == (refused, fresh.attempt_id)
    assert await run_attempt(service, *pulled) == "prepared"
    assert extractor.provider_calls == 2


@pytest.mark.asyncio
async def test_the_day_that_resumes_a_read_turns_at_midnight_in_santo_domingo(rig):
    service, _, clock = rig
    budget(service, per_day=1)
    scope, owner = business(service)
    await refused_by_the_day(service, owner, scope)
    # 03:59 UTC is still 23:59 the day before in Santo Domingo.
    clock.now = datetime(2026, 11, 5, 3, 59, tzinfo=timezone.utc)
    assert await resumed(service) == {"due": 0, "requeued": 0}
    clock.now = datetime(2026, 11, 5, 4, 1, tzinfo=timezone.utc)
    assert await resumed(service) == {"due": 1, "requeued": 1}


@pytest.mark.asyncio
async def test_a_read_the_month_refused_resumes_when_the_month_turns(rig):
    service, extractor, clock = rig
    budget(service, per_day=300, per_month=1)
    scope, owner = business(service)
    await read(service, owner, scope, await queued(service, owner, scope))
    refused = await queued(service, owner, scope)
    with pytest.raises(DocumentServiceError, match="business_read_budget_month"):
        await read(service, owner, scope, refused)
    clock.now = datetime(2026, 12, 1, 3, 59, tzinfo=timezone.utc)
    assert await resumed(service) == {"due": 0, "requeued": 0}
    clock.now = datetime(2026, 12, 1, 4, 1, tzinfo=timezone.utc)
    assert await resumed(service) == {"due": 1, "requeued": 1}
    assert (await read(service, owner, scope, refused)).status == "review_ready"
    assert extractor.provider_calls == 2


@pytest.mark.asyncio
async def test_a_refused_read_stays_as_it_is_while_reading_is_off(rig):
    service, _, clock = rig
    budget(service, per_day=1)
    scope, owner = business(service)
    refused = await refused_by_the_day(service, owner, scope)
    waiting = service.get(user_id=owner, connection_id=refused, scope=scope)
    turn_reading(service.business_receipt_consent, scope.space_id, owner, enabled=False)
    clock.now += timedelta(days=1)
    assert await resumed(service) == {"due": 1, "requeued": 0}
    assert service.get(user_id=owner, connection_id=refused, scope=scope) == waiting
    assert service.store.pull(now=clock(), cap=3) is None


@pytest.mark.asyncio
async def test_a_business_with_reading_off_does_not_hold_back_another(rig):
    service, _, clock = rig
    budget(service, per_day=1)
    off, off_owner = business(service)
    on, on_owner = business(service)
    await refused_by_the_day(service, off_owner, off)
    resumes = await refused_by_the_day(service, on_owner, on)
    turn_reading(service.business_receipt_consent, off.space_id, off_owner, enabled=False)
    clock.now += timedelta(days=1)
    assert await resumed(service) == {"due": 2, "requeued": 1}
    assert service.store.pull(now=clock(), cap=3)[0] == resumes


@pytest.mark.asyncio
async def test_a_read_refused_again_on_resume_waits_for_the_next_day(rig):
    service, extractor, clock = rig
    budget(service, per_day=1)
    scope, owner = business(service)
    refused = await refused_by_the_day(service, owner, scope)
    clock.now += timedelta(days=1)
    await read(service, owner, scope, await queued(service, owner, scope))
    assert await resumed(service) == {"due": 1, "requeued": 1}
    assert (
        await run_attempt(service, *service.store.pull(now=clock(), cap=3))
        == "business_read_budget_day"
    )
    assert await resumed(service) == {"due": 0, "requeued": 0}
    clock.now += timedelta(days=1)
    assert await resumed(service) == {"due": 1, "requeued": 1}
    assert (
        await run_attempt(service, *service.store.pull(now=clock(), cap=3)) == "prepared"
    )
    assert (
        service.get(user_id=owner, connection_id=refused, scope=scope).error_code is None
    )
    assert extractor.provider_calls == 3


@pytest.mark.asyncio
async def test_a_receipt_the_person_already_asked_for_is_not_resumed(rig):
    service, _, clock = rig
    budget(service, per_day=1)
    scope, owner = business(service)
    refused = await refused_by_the_day(service, owner, scope)
    clock.now += timedelta(days=1)
    [(_, _, seen)] = service.store.refused_before(
        before={"business_read_budget_day": clock()}
    )
    service.queue(user_id=owner, connection_id=refused, consent=True, scope=scope)
    asked = service.get(user_id=owner, connection_id=refused, scope=scope)
    assert await resumed(service) == {"due": 0, "requeued": 0}
    # A pass that chose the receipt before the person asked finds it moved.
    with pytest.raises(DocumentServiceError, match="document_version_conflict"):
        service.queue(
            user_id=owner,
            connection_id=refused,
            consent=True,
            scope=scope,
            expected_version=seen,
        )
    assert service.get(user_id=owner, connection_id=refused, scope=scope) == asked


@pytest.mark.parametrize("extraction", ["true", "false"])
@pytest.mark.asyncio
async def test_the_worker_pass_resumes_only_while_extraction_is_on(
    rig, monkeypatch, extraction
):
    service, _, clock = rig
    budget(service, per_day=1)
    scope, owner = business(service)
    refused = await refused_by_the_day(service, owner, scope)
    clock.now += timedelta(days=1)
    monkeypatch.setenv("CUADRAO_DOCUMENT_EXTRACTION_ENABLED", extraction)
    await asyncio.to_thread(ReadResume(service).tick)
    pulled = service.store.pull(now=clock(), cap=3)
    assert (pulled is not None and pulled[0] == refused) == (extraction == "true")


def test_the_worker_pass_asks_the_store_at_most_once_in_its_interval(rig, monkeypatch):
    service, _, clock = rig
    monkeypatch.setenv("CUADRAO_DOCUMENT_EXTRACTION_ENABLED", "true")
    asked = []
    monkeypatch.setattr(
        service.store, "refused_before", lambda **query: asked.append(query) or []
    )
    pass_ = ReadResume(service, every=timedelta(minutes=10))
    pass_.tick()
    clock.now += timedelta(minutes=9)
    pass_.tick()
    assert len(asked) == 1
    clock.now += timedelta(minutes=1)
    pass_.tick()
    assert len(asked) == 2


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
