"""The pull worker on real Postgres: one taker per attempt, one cap for all."""

import asyncio
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository
from argus.domain.ingestion.documents.config import DocumentJobSettings
from argus.domain.ingestion.documents.jobs import (
    DISPATCH_WINDOW,
    OUTCOME_UNKNOWN,
    PreparationJobs,
    run_attempt,
)
from argus.domain.ingestion.documents.models import ExtractionBatch
from argus.domain.ingestion.documents.service import DocumentsService
from argus.domain.ingestion.documents.store_postgres import PostgresDocumentStore
from argus.domain.owner_scope import PERSONAL
from psycopg_pool import ConnectionPool

from tests import test_document_jobs_postgres as support
from tests import test_financial_accounts_postgres as shared
from tests.document_sources_support import source_objects
from workflows import document_worker
from workflows.document_job import postgres_documents_service
from workflows.document_worker import DocumentWorker

users = shared.users
pytestmark = pytest.mark.skipif(
    not shared.DSN, reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured"
)


class Clock(support.Clock):
    """Years ahead: the cap counts every read in the database, and rows other
    tests leave behind hold no live lease or dispatch this far along."""

    def __init__(self) -> None:
        super().__init__()
        self.now += timedelta(days=3650)


class Gauge(support.Extractor):
    """Measures reads at once. Each read holds long enough to overlap the next."""

    def __init__(self) -> None:
        super().__init__()
        self.running, self.peak = 0, 0
        self.read: list[str] = []

    async def extract(self, **kwargs: Any) -> ExtractionBatch:
        self.read.append(kwargs["connection_id"])
        self.running += 1
        self.peak = max(self.peak, self.running)
        await asyncio.sleep(0.05)
        self.running -= 1
        return await super().extract(**kwargs)


@pytest.fixture
def pool() -> Iterator[ConnectionPool]:
    with ConnectionPool(shared.DSN, min_size=4, max_size=4) as opened:
        opened.wait()
        yield opened


@pytest.fixture
def other_pool() -> Iterator[ConnectionPool]:
    with ConnectionPool(shared.DSN, min_size=4, max_size=4) as opened:
        opened.wait()
        yield opened


def puller(service: DocumentsService, *mine: str) -> PreparationJobs:
    """Pull-mode jobs whose sweep sees only this test's rows."""

    service.store.pending = lambda *, limit: [  # type: ignore[method-assign]
        (service.store.owner(connection_id=connection), connection) for connection in mine
    ]
    return PreparationJobs(service, None)


async def waiting(service: DocumentsService, owner: str, count: int) -> list[str]:
    jobs = PreparationJobs(service, None)
    connections = []
    for _ in range(count):
        connection = await support.capture(service, owner)
        jobs.start(user_id=owner, connection_id=connection)
        connections.append(connection)
        service.hub.clock.now += timedelta(seconds=1)
    return connections


def observations(pool: ConnectionPool, owner: str, connection_id: str) -> int:
    with pool.connection() as connection:
        return connection.execute(
            "select count(distinct event_id) from public.financial_import_observations "
            "where user_id=%s and connection_id=%s",
            (owner, connection_id),
        ).fetchone()[0]


@pytest.mark.asyncio
async def test_racing_pullers_take_each_attempt_once_and_stop_at_the_cap(
    pool: ConnectionPool, other_pool: ConnectionPool, users: dict[str, str]
) -> None:
    clock = Clock()
    api = support.instance(pool, clock, support.Extractor())
    connections = await waiting(api.service, users["owner"], 6)
    stores = [
        PostgresDocumentStore(racing, source_objects()) for racing in (pool, other_pool)
    ]
    barrier = threading.Barrier(8)

    def race(store: PostgresDocumentStore) -> tuple[str, str] | None:
        barrier.wait(10)
        return store.pull(now=clock(), cap=3)

    with ThreadPoolExecutor(8) as racers:
        results = list(racers.map(race, stores * 4))

    taken = [result for result in results if result is not None]
    assert sorted(connection for connection, _ in taken) == sorted(connections[:3])
    assert all(
        api.service.store.job(user_id=users["owner"], connection_id=connection).attempt_id
        == attempt_id
        for connection, attempt_id in taken
    )


@pytest.mark.asyncio
async def test_two_workers_share_one_cap_and_read_each_receipt_once(
    pool: ConnectionPool,
    other_pool: ConnectionPool,
    users: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARGUS_DOCUMENT_EXTRACTION_ENABLED", "true")
    monkeypatch.setattr(document_worker, "POLL_SECONDS", 0.01)

    async def no_sweep(*_: Any) -> None:
        await asyncio.Event().wait()

    monkeypatch.setattr(document_worker, "sweep_forever", no_sweep)
    clock, gauge, owner = Clock(), Gauge(), users["owner"]
    first = support.instance(pool, clock, gauge)
    second = support.instance(other_pool, clock, gauge)
    connections = await waiting(first.service, owner, 9)
    settings = DocumentJobSettings(enabled=True, pull=True, max_reads=3)
    stop = asyncio.Event()
    workers = [
        asyncio.create_task(DocumentWorker(api.service, settings).run(stop))
        for api in (first, second)
    ]

    def settled() -> bool:
        return all(
            first.service.get(
                user_id=owner, connection_id=connection, scope=PERSONAL
            ).status
            == "review_ready"
            for connection in connections
        )

    deadline = time.monotonic() + 30
    while not settled():
        assert time.monotonic() < deadline, "reads did not finish"
        await asyncio.sleep(0.02)
    stop.set()
    await asyncio.gather(*workers)

    assert gauge.peak == 3, "measured across both workers"
    assert sorted(gauge.read) == sorted(connections)


@pytest.mark.asyncio
async def test_a_read_that_runs_outside_the_pull_counts_against_the_cap(
    pool: ConnectionPool, users: dict[str, str]
) -> None:
    clock = Clock()
    api = support.instance(pool, clock, support.Extractor())
    store = api.service.store
    elsewhere, next_up = await waiting(api.service, users["owner"], 2)
    assert api.service.hub.connections.lease(
        connection_id=elsewhere, holder="api-process", now=clock()
    )

    assert store.pull(now=clock(), cap=1) is None
    taken = store.pull(now=clock(), cap=2)
    assert taken is not None
    assert taken[0] == next_up


@pytest.mark.asyncio
async def test_pull_takes_only_a_live_current_attempt(
    pool: ConnectionPool, users: dict[str, str]
) -> None:
    clock, owner = Clock(), users["owner"]
    api = support.instance(pool, clock, support.Extractor())
    store, service = api.service.store, api.service
    gone, edited, current = await waiting(service, owner, 3)
    PostgresConnectionRepository(pool).disconnect(
        user_id=owner, connection_id=gone, now=clock()
    )
    draft = store.draft(user_id=owner, connection_id=edited)
    service._update(owner, draft, consent=True)

    taken = store.pull(now=clock(), cap=3)

    job = store.job(user_id=owner, connection_id=current)
    assert taken == (current, job.attempt_id)
    assert job.dispatched_at == clock()
    assert store.pull(now=clock(), cap=3) is None


@pytest.mark.asyncio
async def test_a_kill_before_the_marker_reads_once_and_records_once(
    pool: ConnectionPool, users: dict[str, str]
) -> None:
    clock, extractor, owner = Clock(), support.Extractor(), users["owner"]
    service = postgres_documents_service(pool, source_objects(), extractor)
    service.hub.clock = clock
    gated = support.GatedStore(pool, blocked=1)
    service.store = gated
    [connection] = await waiting(service, owner, 1)
    jobs = puller(service, connection)
    dead = asyncio.create_task(
        run_attempt(service, *service.store.pull(now=clock(), cap=3))
    )
    while gated.entered == 0:
        await asyncio.sleep(0.01)

    assert service.store.pull(now=clock(), cap=1) is None, "the dead read holds a slot"
    clock.now += DISPATCH_WINDOW + timedelta(seconds=1)
    assert jobs.sweep().redispatched == [connection]

    assert await run_attempt(service, *gated.pull(now=clock(), cap=3)) == "prepared"
    gated.release.set()
    assert await dead == "document_lease_lost"

    assert extractor.calls == 1
    assert observations(pool, owner, connection) == 1


@pytest.mark.asyncio
async def test_a_kill_after_the_marker_waits_for_the_owner_and_records_once(
    pool: ConnectionPool, users: dict[str, str]
) -> None:
    clock, extractor, owner = Clock(), support.Extractor(hang=True), users["owner"]
    service = postgres_documents_service(pool, source_objects(), extractor)
    service.hub.clock = clock
    [connection] = await waiting(service, owner, 1)
    jobs = puller(service, connection)
    dead = asyncio.create_task(
        run_attempt(service, *service.store.pull(now=clock(), cap=3))
    )
    while extractor.calls == 0:
        await asyncio.sleep(0.01)

    clock.now += DISPATCH_WINDOW + timedelta(seconds=1)
    assert jobs.sweep().outcome_unknown == [connection]
    draft = service.get(user_id=owner, connection_id=connection, scope=PERSONAL)
    assert draft.error_code == OUTCOME_UNKNOWN
    assert service.store.pull(now=clock(), cap=3) is None

    service.queue(user_id=owner, connection_id=connection, consent=True, scope=PERSONAL)
    jobs.start(user_id=owner, connection_id=connection)
    assert await run_attempt(service, *service.store.pull(now=clock(), cap=3)) == (
        "prepared"
    )
    extractor.release.set()
    assert await dead == "document_lease_lost"

    assert extractor.calls == 2
    assert observations(pool, owner, connection) == 1


def test_the_worker_command_starts_and_stops_on_sigterm() -> None:
    env = {
        **os.environ,
        "CUADRAO_DOCUMENT_JOBS_ENABLED": "true",
        "CUADRAO_DOCUMENT_JOBS_PULL_ENABLED": "true",
        "ARGUS_WORKFLOW_DATABASE_URL": shared.DSN,
        "SUPABASE_URL": os.environ.get("ARGUS_LOCAL_SUPABASE_URL", "http://127.0.0.1:9"),
        "SUPABASE_SERVICE_ROLE_KEY": "not-a-key",
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "workflows.document_worker"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    watchdog = threading.Timer(60, process.kill)
    watchdog.start()
    try:
        for line in process.stdout:
            if "Document worker started" in line:
                break
        process.send_signal(signal.SIGTERM)
        assert process.wait(30) == 0
    finally:
        watchdog.cancel()
        process.kill()
