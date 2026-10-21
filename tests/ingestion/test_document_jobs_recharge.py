"""No automatic second charge: a dead `preparing` draft is re-dispatched only
when its current, unmarked attempt provably wrote that state."""

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import Mock

import pytest
from argus.domain.ingestion.connections import InMemoryConnectionRepository
from argus.domain.ingestion.contract import ImportCandidate, SourceRef
from argus.domain.ingestion.documents.jobs import (
    DISPATCH_WINDOW,
    OUTCOME_UNKNOWN,
    PreparationJobs,
    run_attempt,
)
from argus.domain.ingestion.documents.models import DraftProposal, ExtractionBatch
from argus.domain.ingestion.documents.objects import SourceStorageUnavailable
from argus.domain.ingestion.documents.service import DocumentsService
from argus.domain.ingestion.documents.store import InMemoryDocumentStore
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.sink import SubmitResult
from argus.domain.owner_scope import PERSONAL


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now


class Extractor:
    def __init__(self) -> None:
        self.calls = 0

    async def extract(self, **kwargs: Any) -> ExtractionBatch:
        self.calls += 1
        return ExtractionBatch(
            candidates=(
                ImportCandidate(
                    source=SourceRef(
                        source="statement",
                        connection_id=kwargs["connection_id"],
                        external_id="document:p1:r1",
                        observed_at=kwargs["observed_at"],
                    ),
                    evidence="transaction",
                    amount="12.00",
                    currency="DOP",
                    direction="outflow",
                ),
            )
        )


@pytest.fixture
def rig():
    clock, extractor, sink = Clock(), Extractor(), Mock()
    sink.submit.return_value = SubmitResult(1, 0, 0)
    repo = InMemoryConnectionRepository()
    hub = IngestionHub(repo, box=None, sink=sink, clock=clock)
    service = DocumentsService(
        hub, InMemoryDocumentStore(repo), extractor, jobs_recover_interruptions=True
    )
    dispatched: list[str] = []
    jobs = PreparationJobs(service, lambda _, attempt: dispatched.append(attempt))
    return service, jobs, clock, extractor, dispatched


async def queued(service: DocumentsService) -> str:
    outcome = await service.upload(
        user_id="owner",
        content=b"%PDF-fixture",
        filename="receipt.pdf",
        media_type="application/pdf",
        consent=True,
        scope=PERSONAL,
    )
    return outcome.connection_id


def die_while_preparing(service: DocumentsService, connection: str) -> None:
    """A writer that is not the current attempt (a flag-off background task, or
    an attempt for an older draft version) claims the draft and dies mid-call."""
    hub = service.hub
    hub.connections.lease(connection_id=connection, holder="other", now=hub.clock())
    draft = service.store.draft(user_id="owner", connection_id=connection)
    service._update("owner", draft, holder="other", status="preparing")


@pytest.mark.asyncio
async def test_dead_preparing_draft_without_a_job_waits_for_the_owner(rig):
    service, jobs, clock, extractor, dispatched = rig
    connection = await queued(service)
    die_while_preparing(service, connection)

    clock.now += DISPATCH_WINDOW + timedelta(seconds=1)
    report = jobs.sweep()

    draft = service.get(user_id="owner", connection_id=connection, scope=PERSONAL)
    assert report.outcome_unknown == [connection]
    assert (draft.status, draft.error_code) == ("needs_attention", OUTCOME_UNKNOWN)
    assert dispatched == []
    assert extractor.calls == 0
    assert jobs.sweep().redispatched == []


@pytest.mark.asyncio
async def test_dead_preparing_draft_with_a_stale_job_waits_for_the_owner(rig):
    service, jobs, clock, extractor, dispatched = rig
    connection = await queued(service)
    jobs.start(user_id="owner", connection_id=connection)
    [stale] = dispatched
    draft = service.store.draft(user_id="owner", connection_id=connection)
    service.update_proposal(
        user_id="owner",
        scope=PERSONAL,
        connection_id=connection,
        version=draft.version,
        proposal=DraftProposal(requested_plan="Trip"),
    )
    assert await run_attempt(service, connection, stale) == (
        "document_attempt_superseded"
    ), "an attempt cannot claim a draft version it was not dispatched for"
    die_while_preparing(service, connection)

    clock.now += DISPATCH_WINDOW + timedelta(seconds=1)
    report = jobs.sweep()

    draft = service.get(user_id="owner", connection_id=connection, scope=PERSONAL)
    assert report.outcome_unknown == [connection]
    assert (draft.status, draft.error_code) == ("needs_attention", OUTCOME_UNKNOWN)
    assert dispatched == [stale]
    assert extractor.calls == 0


@pytest.mark.asyncio
async def test_superseded_queued_attempt_is_replaced_on_the_next_sweep(rig):
    service, jobs, _, extractor, dispatched = rig
    connection = await queued(service)
    jobs.start(user_id="owner", connection_id=connection)
    [stale] = dispatched
    draft = service.store.draft(user_id="owner", connection_id=connection)
    service.update_proposal(
        user_id="owner",
        scope=PERSONAL,
        connection_id=connection,
        version=draft.version,
        proposal=DraftProposal(requested_plan="Trip"),
    )
    assert await run_attempt(service, connection, stale) == (
        "document_attempt_superseded"
    )

    assert jobs.sweep().redispatched == [connection]
    [_, fresh] = dispatched
    assert await run_attempt(service, connection, fresh) == "prepared"
    assert extractor.calls == 1


@pytest.mark.asyncio
async def test_storage_failure_before_the_marker_is_retried_once(rig):
    service, jobs, _, extractor, dispatched = rig
    connection = await queued(service)
    original, failures = service.store.source, [1]

    def source(**kwargs: Any) -> bytes | None:
        if failures:
            failures.pop()
            raise SourceStorageUnavailable()
        return original(**kwargs)

    service.store.source = source  # type: ignore[method-assign]
    jobs.start(user_id="owner", connection_id=connection)
    [first] = dispatched
    assert await run_attempt(service, connection, first) == (
        "document_storage_unavailable"
    )
    job = service.store.job(user_id="owner", connection_id=connection)
    assert (job.retry, job.provider_call_started_at) == (True, None)

    assert jobs.sweep().redispatched == [connection]
    [_, second] = dispatched
    assert await run_attempt(service, connection, second) == "prepared"
    assert extractor.calls == 1
    assert service.get(
        user_id="owner", connection_id=connection, scope=PERSONAL
    ).status == ("review_ready")


@pytest.mark.asyncio
async def test_foreign_claim_of_the_dispatched_version_waits_for_the_owner(rig):
    service, jobs, clock, extractor, dispatched = rig
    connection = await queued(service)
    jobs.start(user_id="owner", connection_id=connection)
    job = service.store.job(user_id="owner", connection_id=connection)
    die_while_preparing(service, connection)
    draft = service.store.draft(user_id="owner", connection_id=connection)
    assert draft.version == job.draft_version + 1, "same shape as the attempt's claim"

    clock.now += DISPATCH_WINDOW + timedelta(seconds=1)
    report = jobs.sweep()

    draft = service.get(user_id="owner", connection_id=connection, scope=PERSONAL)
    assert report.outcome_unknown == [connection]
    assert (draft.status, draft.error_code) == ("needs_attention", OUTCOME_UNKNOWN)
    assert len(dispatched) == 1
    assert extractor.calls == 0


@pytest.mark.asyncio
async def test_foreign_claim_after_a_superseding_redispatch_waits_for_the_owner(rig):
    service, jobs, clock, extractor, dispatched = rig
    connection = await queued(service)
    jobs.start(user_id="owner", connection_id=connection)
    draft = service.store.draft(user_id="owner", connection_id=connection)
    service.update_proposal(
        user_id="owner",
        scope=PERSONAL,
        connection_id=connection,
        version=draft.version,
        proposal=DraftProposal(requested_plan="Trip"),
    )
    assert jobs.sweep().redispatched == [connection], "a stale queued attempt"
    die_while_preparing(service, connection)

    clock.now += DISPATCH_WINDOW + timedelta(seconds=1)
    report = jobs.sweep()

    draft = service.get(user_id="owner", connection_id=connection, scope=PERSONAL)
    assert report.outcome_unknown == [connection]
    assert draft.error_code == OUTCOME_UNKNOWN
    assert len(dispatched) == 2
    assert extractor.calls == 0


class WorkerKilled(BaseException):
    pass


@pytest.mark.asyncio
async def test_marked_attempt_that_saved_its_batch_is_replayed_without_a_call(rig):
    service, jobs, clock, extractor, dispatched = rig
    connection = await queued(service)
    sink = service.hub.sink
    sink.submit.side_effect = [WorkerKilled(), SubmitResult(1, 0, 0)]
    jobs.start(user_id="owner", connection_id=connection)
    [first] = dispatched
    with pytest.raises(WorkerKilled):
        await run_attempt(service, connection, first)
    job = service.store.job(user_id="owner", connection_id=connection)
    assert job.provider_call_started_at is not None
    assert service.store.get(user_id="owner", connection_id=connection) is not None
    assert service.store.draft(user_id="owner", connection_id=connection).status == (
        "preparing"
    )

    assert jobs.sweep().redispatched == [connection]
    [_, replay] = dispatched
    assert await run_attempt(service, connection, replay) == "prepared"
    assert extractor.calls == 1, "replaying a saved preparation never calls"
    assert sink.submit.call_count == 2
    assert service.get(
        user_id="owner", connection_id=connection, scope=PERSONAL
    ).status == ("review_ready")


@pytest.mark.asyncio
async def test_foreign_claim_of_a_recovered_attempt_waits_for_the_owner(rig):
    service, jobs, clock, extractor, dispatched = rig
    connection = await queued(service)
    original, holds = service.store.source, [1]

    def source(**kwargs: Any) -> bytes | None:
        if holds:
            holds.pop()
            raise WorkerKilled()
        return original(**kwargs)

    service.store.source = source  # type: ignore[method-assign]
    jobs.start(user_id="owner", connection_id=connection)
    [first] = dispatched
    with pytest.raises(WorkerKilled):
        await run_attempt(service, connection, first)
    assert service.store.job(user_id="owner", connection_id=connection).claimed

    assert jobs.sweep().redispatched == [connection]
    second = service.store.job(user_id="owner", connection_id=connection)
    assert (second.attempt, second.claimed) == (2, False)
    die_while_preparing(service, connection)

    clock.now += DISPATCH_WINDOW + timedelta(seconds=1)
    report = jobs.sweep()

    draft = service.get(user_id="owner", connection_id=connection, scope=PERSONAL)
    assert report.outcome_unknown == [connection]
    assert draft.error_code == OUTCOME_UNKNOWN
    assert len(dispatched) == 2
    assert extractor.calls == 0
