"""Document preparation jobs on real Postgres: one current attempt, lease-fenced."""

import asyncio
import hashlib
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import Mock
from uuid import uuid4

import pytest
from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository
from argus.domain.ingestion.contract import ImportCandidate, SourceRef
from argus.domain.ingestion.documents.jobs import (
    DISPATCH_WINDOW,
    PreparationJobs,
    SweepReport,
    run_attempt,
)
from argus.domain.ingestion.documents.models import (
    DocumentDraft,
    ExtractionBatch,
    PreparationJob,
)
from argus.domain.ingestion.documents.objects import InMemorySourceObjects
from argus.domain.ingestion.documents.service import DocumentsService
from argus.domain.ingestion.documents.store_postgres import PostgresDocumentStore
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.sink import SubmitResult
from argus.domain.owner_scope import PERSONAL
from psycopg_pool import ConnectionPool

from tests import test_financial_accounts_postgres as shared
from tests.business_reading_support import ROUTE, reading_setting, turn_reading
from tests.document_sources_support import source_objects, stored_paths

users = shared.users
pytestmark = pytest.mark.skipif(
    not shared.DSN, reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured"
)


@pytest.fixture
def pool() -> Iterator[ConnectionPool]:
    with ConnectionPool(shared.DSN, min_size=0, max_size=4) as opened:
        yield opened


def draft(connection_id: str, now: datetime, **changes: Any) -> DocumentDraft:
    return DocumentDraft(
        connection_id=connection_id,
        filename="receipt.pdf",
        media_type="application/pdf",
        sha256=hashlib.sha256(changes.pop("content", b"%PDF-x")).hexdigest(),
        size_bytes=12,
        consent=True,
        created_at=now,
        updated_at=now,
        **{"status": "queued", **changes},
    )


def test_advance_names_one_current_attempt_and_respects_the_lease(
    pool: ConnectionPool, users: dict[str, str]
) -> None:
    now = datetime.now(timezone.utc)
    repo = PostgresConnectionRepository(pool)
    store = PostgresDocumentStore(pool, source_objects())
    owner, other = users["owner"], users["other"]
    row = repo.create(
        user_id=owner,
        source="statement",
        external_ref=str(uuid4()),
        label=None,
        now=now,
        scope=PERSONAL,
    )
    assert store.capture(user_id=owner, draft=draft(row.id, now), content=b"%PDF-x")
    first = PreparationJob(attempt=1, attempt_id="a1", draft_version=1, dispatched_at=now)
    second = first.model_copy(update={"attempt": 2, "attempt_id": "a2"})

    assert store.owner(connection_id=row.id) == owner
    assert (owner, row.id) in store.pending(limit=1000)
    assert not store.advance(
        user_id=other, connection_id=row.id, now=now, expected_attempt_id=None, job=first
    )
    assert store.advance(
        user_id=owner, connection_id=row.id, now=now, expected_attempt_id=None, job=first
    )
    assert not store.advance(
        user_id=owner, connection_id=row.id, now=now, expected_attempt_id=None, job=second
    )
    assert store.job(user_id=owner, connection_id=row.id) == first
    assert store.job(user_id=other, connection_id=row.id) is None

    assert repo.lease(connection_id=row.id, holder="worker", now=now)
    assert not store.advance(
        user_id=owner, connection_id=row.id, now=now, expected_attempt_id="a1", job=second
    ), "a live lease is never superseded"
    later = now + DISPATCH_WINDOW + timedelta(seconds=1)
    stale_version = draft(row.id, later, version=5)
    assert not store.advance(
        user_id=owner,
        connection_id=row.id,
        now=later,
        expected_attempt_id="a1",
        job=second,
        draft=stale_version,
    ), "the draft version is compared and set with the job"
    requeued = draft(row.id, later, version=2)
    assert store.advance(
        user_id=owner,
        connection_id=row.id,
        now=later,
        expected_attempt_id="a1",
        job=second,
        draft=requeued,
    )
    assert store.job(user_id=owner, connection_id=row.id) == second
    assert store.draft(user_id=owner, connection_id=row.id) == requeued

    failed = draft(row.id, later, version=3, status="needs_attention")
    assert store.advance(
        user_id=owner,
        connection_id=row.id,
        now=later,
        expected_attempt_id="a2",
        job=second,
        draft=failed,
    )
    assert (owner, row.id) not in store.pending(limit=1000)
    retry = second.model_copy(update={"retry": True})
    assert store.advance(
        user_id=owner,
        connection_id=row.id,
        now=later,
        expected_attempt_id="a2",
        job=retry,
    )
    assert (owner, row.id) in store.pending(limit=1000)

    repo.disconnect(user_id=owner, connection_id=row.id, now=later)
    assert store.owner(connection_id=row.id) is None
    assert (owner, row.id) not in store.pending(limit=1000)
    store.forget(user_id=owner, connection_id=row.id)


class Clock:
    def __init__(self) -> None:
        self.now = datetime.now(timezone.utc)

    def __call__(self) -> datetime:
        return self.now


class Extractor:
    """Scripted extraction: ``hang`` holds the first call after the marker."""

    def __init__(self, hang: bool = False) -> None:
        self.calls, self.hang = 0, hang
        self.release = asyncio.Event()

    async def extract(self, **kwargs: Any) -> ExtractionBatch:
        self.calls += 1
        amount = "129.50"
        if self.hang and self.calls == 1:
            await self.release.wait()
            amount = "999.00"
        candidate = ImportCandidate(
            source=SourceRef(
                source="statement",
                connection_id=kwargs["connection_id"],
                external_id="document:p1:r1",
                observed_at=kwargs["observed_at"],
            ),
            evidence="transaction",
            amount=amount,
            currency="DOP",
            direction="outflow",
        )
        return ExtractionBatch(candidates=(candidate,))


class GatedStore(PostgresDocumentStore):
    """Holds the first ``blocked`` source reads: a worker that dies after
    claiming and before its provider marker, with its lease still held."""

    def __init__(self, pool: ConnectionPool, blocked: int = 0) -> None:
        super().__init__(pool, source_objects())
        self.blocked, self.entered = blocked, 0
        self.release = threading.Event()
        self._gate = threading.Lock()

    def source(self, *, user_id: str, connection_id: str) -> bytes | None:
        with self._gate:
            self.entered += 1
            hold = self.entered <= self.blocked
        if hold:
            self.release.wait(10)
        return super().source(user_id=user_id, connection_id=connection_id)


@dataclass
class Instance:
    """One API process: its own pool, service and dispatch log over one database."""

    service: DocumentsService
    jobs: PreparationJobs
    dispatched: list[tuple[str, str]]
    sink: Mock

    def attempts(self, connection: str) -> list[str]:
        return [attempt for target, attempt in self.dispatched if target == connection]


def instance(
    pool: ConnectionPool,
    clock: Clock,
    extractor: Extractor,
    store: PostgresDocumentStore | None = None,
    dispatch: Callable[[DocumentsService], Callable[[str, str], None]] | None = None,
) -> Instance:
    sink = Mock()
    sink.submit.return_value = SubmitResult(1, 0, 0)
    hub = IngestionHub(
        PostgresConnectionRepository(pool), box=None, sink=sink, clock=clock
    )
    service = DocumentsService(
        hub,
        store or PostgresDocumentStore(pool, source_objects()),
        extractor,
        jobs_recover_interruptions=True,
    )
    dispatched: list[tuple[str, str]] = []
    forward = dispatch(service) if dispatch else None

    def record(connection_id: str, attempt_id: str) -> None:
        dispatched.append((connection_id, attempt_id))
        if forward is not None:
            forward(connection_id, attempt_id)

    return Instance(service, PreparationJobs(service, record), dispatched, sink)


async def capture(service: DocumentsService, owner: str) -> str:
    captured = await service.upload(
        user_id=owner,
        content=b"%PDF-" + uuid4().bytes,
        filename="receipt.pdf",
        media_type="application/pdf",
        consent=True,
        scope=PERSONAL,
    )
    return captured.connection_id


def forget(service: DocumentsService, owner: str, connection: str) -> None:
    service.forget(
        service.hub.connections.get(
            user_id=owner, connection_id=connection, scope=PERSONAL
        )
    )


@pytest.mark.asyncio
async def test_kill_before_the_marker_recovers_with_one_provider_call(
    pool: ConnectionPool, users: dict[str, str]
) -> None:
    clock, extractor = Clock(), Extractor()
    api = instance(pool, clock, extractor, GatedStore(pool, blocked=1))
    store, owner = api.service.store, users["owner"]
    connection = await capture(api.service, owner)
    api.jobs.start(user_id=owner, connection_id=connection)
    api.jobs.start(user_id=owner, connection_id=connection)
    [first] = api.attempts(connection)
    dead = asyncio.create_task(run_attempt(api.service, connection, first))
    while store.entered == 0:
        await asyncio.sleep(0.01)

    clock.now += DISPATCH_WINDOW - timedelta(seconds=1)
    assert connection not in api.jobs.sweep().redispatched
    clock.now += timedelta(seconds=2)
    assert connection in api.jobs.sweep().redispatched
    [_, second] = api.attempts(connection)

    assert await run_attempt(api.service, connection, first) == (
        "document_attempt_superseded"
    ), "a late duplicate of the superseded attempt never claims"
    assert await run_attempt(api.service, connection, second) == "prepared"
    store.release.set()
    assert await dead == "document_lease_lost"

    assert api.service.get(
        user_id=owner, connection_id=connection, scope=PERSONAL
    ).status == ("review_ready")
    assert extractor.calls == 1
    api.sink.submit.assert_called_once()
    assert connection not in api.jobs.sweep().redispatched
    forget(api.service, owner, connection)


@pytest.mark.asyncio
async def test_kill_after_the_marker_settles_until_a_consented_retry(
    pool: ConnectionPool, users: dict[str, str]
) -> None:
    clock, extractor = Clock(), Extractor(hang=True)
    api = instance(pool, clock, extractor)
    owner = users["owner"]
    connection = await capture(api.service, owner)
    api.jobs.start(user_id=owner, connection_id=connection)
    [first] = api.attempts(connection)
    dead = asyncio.create_task(run_attempt(api.service, connection, first))
    while extractor.calls == 0:
        await asyncio.sleep(0.01)

    clock.now += DISPATCH_WINDOW + timedelta(seconds=1)
    report = api.jobs.sweep()
    assert connection in report.outcome_unknown
    assert connection not in report.redispatched
    settled = api.service.get(user_id=owner, connection_id=connection, scope=PERSONAL)
    assert (settled.status, settled.error_code) == (
        "needs_attention",
        "document_preparation_outcome_unknown",
    )
    assert connection not in api.jobs.sweep().redispatched
    assert api.attempts(connection) == [first]
    assert extractor.calls == 1

    api.service.queue(
        user_id=owner, connection_id=connection, consent=True, scope=PERSONAL
    )
    api.jobs.start(user_id=owner, connection_id=connection)
    [_, retried] = api.attempts(connection)
    assert await run_attempt(api.service, connection, retried) == "prepared"
    extractor.release.set()
    assert await dead == "document_lease_lost"

    batch = api.service.store.get(user_id=owner, connection_id=connection)
    assert [c.amount for c in batch.candidates] == ["129.5"]
    assert extractor.calls == 2
    api.sink.submit.assert_called_once()
    forget(api.service, owner, connection)


def test_concurrent_sweepers_dispatch_each_attempt_once(
    pool: ConnectionPool, users: dict[str, str]
) -> None:
    clock, owner = Clock(), users["owner"]
    with ConnectionPool(shared.DSN, min_size=0, max_size=4) as other_pool:
        first = instance(pool, clock, Extractor())
        second = instance(other_pool, clock, Extractor())
        connections = []
        for _ in range(5):
            connection = asyncio.run(capture(first.service, owner))
            first.jobs.start(user_id=owner, connection_id=connection)
            connections.append(connection)
        clock.now += DISPATCH_WINDOW + timedelta(seconds=1)
        barrier = threading.Barrier(2)
        for api in (first, second):
            store, advance = api.service.store, api.service.store.advance

            def gated(advance=advance, **kwargs: Any) -> bool:
                barrier.wait(5)
                return advance(**kwargs)

            store.advance = gated  # type: ignore[method-assign]
        reports: list[SweepReport] = []
        sweeps = [
            threading.Thread(target=lambda api=api: reports.append(api.jobs.sweep()))
            for api in (first, second)
        ]
        for sweep in sweeps:
            sweep.start()
        for sweep in sweeps:
            sweep.join(30)
        assert len(reports) == 2
        for connection in connections:
            winners = [r for r in reports if connection in r.redispatched]
            assert len(winners) == 1, "exactly one instance dispatches the attempt"
            assert len(first.attempts(connection)) + len(second.attempts(connection)) == 2
        for connection in connections:
            forget(first.service, owner, connection)


@pytest.mark.asyncio
async def test_two_running_instances_recover_a_dead_worker_without_restart(
    pool: ConnectionPool, users: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from argus.api.document_jobs import InProcessDispatcher, sweep_forever

    # The sweep waits while extraction is off.
    monkeypatch.setenv("ARGUS_DOCUMENT_EXTRACTION_ENABLED", "true")

    loop = asyncio.get_running_loop()
    clock, extractor, owner = Clock(), Extractor(), users["owner"]
    gated = GatedStore(pool, blocked=1)
    with ConnectionPool(shared.DSN, min_size=0, max_size=4) as other_pool:
        apis = [
            instance(
                pool,
                clock,
                extractor,
                gated,
                lambda service: InProcessDispatcher(loop, service),
            ),
            instance(
                other_pool,
                clock,
                extractor,
                dispatch=lambda service: InProcessDispatcher(loop, service),
            ),
        ]
        # The sweepers scan every row in the database on a real clock, so they
        # must not outlive this test whatever it raises.
        sweepers = [asyncio.create_task(sweep_forever(api.jobs, 0.02)) for api in apis]
        try:
            connection = await capture(apis[0].service, owner)
            apis[0].jobs.start(user_id=owner, connection_id=connection)
            for _ in range(500):
                if gated.entered:
                    break
                await asyncio.sleep(0.01)
            assert gated.entered == 1
            await asyncio.sleep(0.2)
            assert sum(len(api.attempts(connection)) for api in apis) == 1

            clock.now += DISPATCH_WINDOW + timedelta(seconds=1)
            for _ in range(500):
                draft = apis[0].service.get(
                    user_id=owner, connection_id=connection, scope=PERSONAL
                )
                if draft.status == "review_ready":
                    break
                await asyncio.sleep(0.01)
            await asyncio.sleep(0.2)
        finally:
            for sweeper in sweepers:
                sweeper.cancel()
            gated.release.set()

        assert draft.status == "review_ready"
        assert sum(len(api.attempts(connection)) for api in apis) == 2
        assert extractor.calls == 1
        forget(apis[0].service, owner, connection)


def test_workflow_worker_prepares_the_dispatched_attempt(
    pool: ConnectionPool, users: dict[str, str]
) -> None:
    from workflows.document_job import (
        postgres_documents_service,
        run_document_preparation,
    )

    class Prepared:
        calls = 0

        async def extract(self, **kwargs: Any) -> ExtractionBatch:
            Prepared.calls += 1
            candidate = ImportCandidate(
                source=SourceRef(
                    source="statement",
                    connection_id=kwargs["connection_id"],
                    external_id="document:p1:r1",
                    observed_at=kwargs["observed_at"],
                ),
                evidence="transaction",
                amount="42.00",
                currency="DOP",
                direction="outflow",
            )
            return ExtractionBatch(candidates=(candidate,))

    objects = source_objects()
    api = postgres_documents_service(pool, objects, Prepared())
    outcomes: list[dict[str, str]] = []
    jobs = PreparationJobs(
        api,
        lambda connection_id, attempt_id: outcomes.append(
            asyncio.run(
                run_document_preparation(
                    connection_id,
                    attempt_id,
                    env={"ARGUS_WORKFLOW_DATABASE_URL": shared.DSN},
                    objects=objects,
                    extractor=Prepared(),
                )
            )
        ),
    )
    owner = users["owner"]
    captured = asyncio.run(
        api.upload(
            user_id=owner,
            content=b"%PDF-" + uuid4().bytes,
            filename="receipt.pdf",
            media_type="application/pdf",
            consent=True,
            scope=PERSONAL,
        )
    )

    jobs.start(user_id=owner, connection_id=captured.connection_id)

    assert [outcome["outcome"] for outcome in outcomes] == ["prepared"]
    assert Prepared.calls == 1
    assert api.get(
        user_id=owner, connection_id=captured.connection_id, scope=PERSONAL
    ).status == ("review_ready")
    with pool.connection() as connection:
        events = connection.execute(
            "select count(distinct event_id) from public.financial_import_observations "
            "where user_id=%s and connection_id=%s",
            (owner, captured.connection_id),
        ).fetchone()
        legacy = connection.execute(
            "select source_bytes is null, source_sha256 "
            "from public.financial_document_extractions where connection_id=%s",
            (captured.connection_id,),
        ).fetchone()
        prefix = f"{owner}/{captured.connection_id}/"
        paths = stored_paths(connection, prefix)
    assert events == (1,)
    assert legacy[0] is True, "the worker read the source from Storage, not bytea"
    if not isinstance(objects, InMemorySourceObjects):
        assert paths == [prefix + legacy[1]], "stored at {user}/{connection}/{sha256}"
    api.forget(
        api.hub.connections.get(
            user_id=owner, connection_id=captured.connection_id, scope=PERSONAL
        )
    )


def test_workflow_worker_never_reads_a_business_receipt_once_reading_is_off(
    pool: ConnectionPool, users: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from argus.domain.owner_scope import BusinessSpace

    from workflows.document_job import (
        postgres_documents_service,
        run_document_preparation,
    )

    monkeypatch.setattr(
        "argus.domain.ingestion.whatsapp.receipt_consent.receipt_provider_route",
        lambda: ROUTE,
    )

    class Counted:
        calls = 0

        async def extract(self, **kwargs: Any) -> ExtractionBatch:
            Counted.calls += 1
            return ExtractionBatch()

    owner = users["owner"]
    scope = BusinessSpace(str(uuid4()))
    with pool.connection() as connection:
        connection.execute(
            "insert into public.spaces(id,created_by,kind,name) "
            "values(%s,%s,'business','Reading proof')",
            (scope.space_id, owner),
        )
    setting = reading_setting(pool)
    turn_reading(setting, scope.space_id, owner)
    objects = source_objects()
    api = postgres_documents_service(pool, objects, Counted())
    api.business_receipt_consent = setting
    dispatched: list[tuple[str, str]] = []
    jobs = PreparationJobs(
        api,
        lambda connection_id, attempt_id: dispatched.append((connection_id, attempt_id)),
    )
    captured = asyncio.run(
        api.upload(
            user_id=owner,
            content=b"%PDF-" + uuid4().bytes,
            filename="receipt.pdf",
            media_type="application/pdf",
            scope=scope,
        )
    )
    assert captured.status == "queued"
    jobs.start(user_id=owner, connection_id=captured.connection_id)
    [(connection_id, attempt_id)] = dispatched

    turn_reading(setting, scope.space_id, owner, enabled=False)
    outcome = asyncio.run(
        run_document_preparation(
            connection_id,
            attempt_id,
            env={"ARGUS_WORKFLOW_DATABASE_URL": shared.DSN},
            objects=objects,
            extractor=Counted(),
        )
    )

    assert Counted.calls == 0
    assert outcome["outcome"] == "document_reading_not_allowed"
    draft = api.get(user_id=owner, connection_id=connection_id, scope=scope)
    assert (draft.status, draft.consent) == ("saved", False)


def test_redispatch_refuses_a_marker_or_a_finished_draft_that_landed_after_the_snapshot(
    pool: ConnectionPool, users: dict[str, str]
) -> None:
    from argus.domain.ingestion.connections import DEFAULT_LEASE

    now = datetime.now(timezone.utc)
    repo = PostgresConnectionRepository(pool)
    store = PostgresDocumentStore(pool, source_objects())
    owner = users["owner"]
    row = repo.create(
        user_id=owner,
        source="statement",
        external_ref=str(uuid4()),
        label=None,
        now=now,
        scope=PERSONAL,
    )
    assert store.capture(user_id=owner, draft=draft(row.id, now), content=b"%PDF-x")
    first = PreparationJob(attempt=1, attempt_id="a1", draft_version=1, dispatched_at=now)
    assert store.advance(
        user_id=owner, connection_id=row.id, now=now, expected_attempt_id=None, job=first
    )
    assert repo.lease(connection_id=row.id, holder="worker", now=now)
    preparing = draft(row.id, now, version=2, status="preparing")
    assert store.update(
        user_id=owner, draft=preparing, expected_version=1, holder="worker"
    )
    snapshot = store.job(user_id=owner, connection_id=row.id)
    assert snapshot.provider_call_started_at is None

    marked_at = now + timedelta(minutes=4)
    assert store.mark_provider_call(
        user_id=owner,
        connection_id=row.id,
        attempt_id="a1",
        holder="worker",
        now=marked_at,
    )
    lease = repo.get(user_id=owner, connection_id=row.id, scope=PERSONAL).lease_until
    assert lease == marked_at + DEFAULT_LEASE, "the marker renews the lease"

    later = lease + timedelta(seconds=1)
    second = first.model_copy(
        update={
            "attempt": 2,
            "attempt_id": "a2",
            "draft_version": 3,
            "dispatched_at": later,
        }
    )
    assert not store.advance(
        user_id=owner,
        connection_id=row.id,
        now=later,
        expected_attempt_id=snapshot.attempt_id,
        job=second,
        draft=draft(row.id, later, version=3),
        unmarked=True,
    ), "a marker committed after the sweep's snapshot blocks the re-dispatch"
    assert store.job(user_id=owner, connection_id=row.id).attempt_id == "a1"

    finished = draft(row.id, later, version=3, status="review_ready")
    assert store.update(user_id=owner, draft=finished, expected_version=2)
    stale = second.model_copy(update={"draft_version": 1})
    assert not store.advance(
        user_id=owner,
        connection_id=row.id,
        now=later,
        expected_attempt_id="a1",
        job=stale,
    ), "a draft that moved past the attempt's version is not re-dispatched"
    assert store.advance(
        user_id=owner,
        connection_id=row.id,
        now=later,
        expected_attempt_id="a1",
        job=second,
    ), "the current version may still be replayed"
    repo.disconnect(user_id=owner, connection_id=row.id, now=later)
    store.forget(user_id=owner, connection_id=row.id)


def test_only_the_named_attempt_claims_and_records_it(
    pool: ConnectionPool, users: dict[str, str]
) -> None:
    now = datetime.now(timezone.utc)
    repo = PostgresConnectionRepository(pool)
    store = PostgresDocumentStore(pool, source_objects())
    owner = users["owner"]
    row = repo.create(
        user_id=owner,
        source="statement",
        external_ref=str(uuid4()),
        label=None,
        now=now,
        scope=PERSONAL,
    )
    assert store.capture(user_id=owner, draft=draft(row.id, now), content=b"%PDF-x")
    job = PreparationJob(attempt=1, attempt_id="a1", draft_version=1, dispatched_at=now)
    assert store.advance(
        user_id=owner, connection_id=row.id, now=now, expected_attempt_id=None, job=job
    )
    assert repo.lease(connection_id=row.id, holder="worker", now=now)
    preparing = draft(row.id, now, version=2, status="preparing")

    assert not store.update(
        user_id=owner, draft=preparing, expected_version=1, holder="worker", claim="a0"
    ), "a claim for another attempt changes nothing"
    assert store.draft(user_id=owner, connection_id=row.id).version == 1
    assert store.update(
        user_id=owner, draft=preparing, expected_version=1, holder="worker", claim="a1"
    )
    assert store.job(user_id=owner, connection_id=row.id).claimed is True

    other = repo.create(
        user_id=owner,
        source="statement",
        external_ref=str(uuid4()),
        label=None,
        now=now,
        scope=PERSONAL,
    )
    assert store.capture(
        user_id=owner, draft=draft(other.id, now, content=b"%PDF-y"), content=b"%PDF-y"
    )
    assert store.advance(
        user_id=owner,
        connection_id=other.id,
        now=now,
        expected_attempt_id=None,
        job=job.model_copy(update={"attempt_id": "b1"}),
    )
    assert repo.lease(connection_id=other.id, holder="flag-off", now=now)
    assert store.update(
        user_id=owner,
        draft=draft(other.id, now, content=b"%PDF-y", version=2, status="preparing"),
        expected_version=1,
        holder="flag-off",
    )
    assert store.job(user_id=owner, connection_id=other.id).claimed is False
    for connection in (row.id, other.id):
        repo.disconnect(user_id=owner, connection_id=connection, now=now)
        store.forget(user_id=owner, connection_id=connection)
