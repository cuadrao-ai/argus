"""Pull mode: a queued read waits on its row until a worker takes it."""

import asyncio
import json
import time
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from argus.api.document_jobs import document_jobs
from argus.domain.ingestion.documents.config import (
    DocumentJobSettings,
    load_document_job_settings,
)
from argus.domain.ingestion.documents.jobs import (
    DISPATCH_WINDOW,
    MAX_ATTEMPTS,
    OUTCOME_UNKNOWN,
    PreparationJobs,
    SweepReport,
    run_attempt,
)
from argus.domain.ingestion.documents.models import (
    DocumentDraft,
    DraftProposal,
    ExtractionBatch,
    PreparationJob,
)
from argus.domain.ingestion.documents.service import DocumentsService
from argus.domain.ingestion.sink import SubmitResult
from argus.domain.owner_scope import PERSONAL

from tests.ingestion import test_document_jobs_api as api
from tests.ingestion import test_document_jobs_recharge as support
from workflows import document_worker
from workflows.document_worker import DocumentWorker, serve

rig = support.rig
jobs_env = api.jobs_env
jobs_client = api.jobs_client

OWNER = "owner"
ROOT = Path(__file__).resolve().parents[2]
JOB_SETTINGS = {
    "CUADRAO_DOCUMENT_JOBS_ENABLED": "false",
    "CUADRAO_DOCUMENT_JOBS_PULL_ENABLED": "false",
    "CUADRAO_DOCUMENT_JOBS_MAX_READS": "3",
    "CUADRAO_DOCUMENT_JOBS_DRAIN_SECONDS": "120",
}


class Gauge(support.Extractor):
    """Extraction that measures reads at once and holds each until released."""

    def __init__(self) -> None:
        super().__init__()
        self.running, self.peak = 0, 0
        self.read: list[str] = []
        self.release = asyncio.Event()

    async def extract(self, **kwargs: Any) -> ExtractionBatch:
        self.read.append(kwargs["connection_id"])
        self.running += 1
        self.peak = max(self.peak, self.running)
        try:
            await self.release.wait()
        finally:
            self.running -= 1
        return await super().extract(**kwargs)


def read(service: DocumentsService, connection: str) -> DocumentDraft:
    return service.get(user_id=OWNER, connection_id=connection, scope=PERSONAL)


def attempt(service: DocumentsService, connection: str) -> PreparationJob:
    job = service.store.job(user_id=OWNER, connection_id=connection)
    assert job is not None
    return job


def settings(**changes: Any) -> DocumentJobSettings:
    return DocumentJobSettings(
        **{
            "enabled": True,
            "pull": True,
            "max_reads": 3,
            "sweep_seconds": 3600,
            "drain_seconds": 5,
            **changes,
        }
    )


async def until(predicate: Callable[[], bool], seconds: float = 5.0) -> None:
    deadline = time.monotonic() + seconds
    while not predicate():
        assert time.monotonic() < deadline, "condition not reached"
        await asyncio.sleep(0.005)


@pytest.fixture
def pull(rig):
    service, _, clock, extractor, _ = rig
    return service, PreparationJobs(service, None), clock, extractor


@pytest.fixture
def worker_env(monkeypatch):
    monkeypatch.setenv("CUADRAO_DOCUMENT_EXTRACTION_ENABLED", "true")
    monkeypatch.setattr(document_worker, "POLL_SECONDS", 0.01)


async def waiting(service: DocumentsService, jobs: PreparationJobs, count: int = 1):
    connections = []
    for _ in range(count):
        connection = await service.upload(
            user_id=OWNER,
            content=f"%PDF-{len(connections)}-{id(connections)}".encode(),
            filename="receipt.pdf",
            media_type="application/pdf",
            consent=True,
            scope=PERSONAL,
        )
        jobs.start(user_id=OWNER, connection_id=connection.connection_id)
        connections.append(connection.connection_id)
        service.hub.clock.now += timedelta(seconds=1)
    return connections


@pytest.mark.asyncio
async def test_a_read_queued_past_the_old_window_runs_with_no_attempt_burned(pull):
    service, jobs, clock, extractor = pull
    [connection] = await waiting(service, jobs)

    for _ in range(MAX_ATTEMPTS + 1):
        clock.now += DISPATCH_WINDOW + timedelta(seconds=1)
        assert jobs.sweep() == SweepReport(), "a waiting read is left alone"

    assert read(service, connection).status == "queued"
    assert attempt(service, connection).attempt == 1

    taken = service.store.pull(now=clock(), cap=3)
    assert taken == (connection, attempt(service, connection).attempt_id)
    assert await run_attempt(service, *taken) == "prepared"
    assert read(service, connection).status == "review_ready"
    assert attempt(service, connection).attempt == 1
    assert extractor.calls == 1


@pytest.mark.asyncio
async def test_pull_counts_every_read_against_the_cap(pull):
    service, jobs, clock, _ = pull
    pulled, leased, next_up = await waiting(service, jobs, 3)
    assert service.store.pull(now=clock(), cap=1) == (
        pulled,
        attempt(service, pulled).attempt_id,
    )
    assert service.store.pull(now=clock(), cap=1) is None
    assert service.hub.connections.lease(
        connection_id=leased, holder="api-process", now=clock()
    )

    assert service.store.pull(now=clock(), cap=2) is None
    assert service.store.pull(now=clock(), cap=3) == (
        next_up,
        attempt(service, next_up).attempt_id,
    )


@pytest.mark.asyncio
async def test_turning_pull_off_hands_waiting_reads_back_with_no_attempt_burned(rig):
    service, push, clock, extractor, dispatched = rig
    [connection] = await waiting(service, PreparationJobs(service, None))

    assert push.sweep().redispatched == [connection]

    assert attempt(service, connection).attempt == 1
    assert attempt(service, connection).dispatched_at == clock()
    [handed_off] = dispatched
    assert await run_attempt(service, connection, handed_off) == "prepared"
    assert extractor.calls == 1


@pytest.mark.asyncio
async def test_attempts_lost_after_a_pull_stop_at_the_bound(pull):
    service, jobs, clock, extractor = pull
    [connection] = await waiting(service, jobs)

    for number in range(1, MAX_ATTEMPTS + 1):
        assert attempt(service, connection).attempt == number
        assert service.store.pull(now=clock(), cap=3) is not None
        assert jobs.sweep() == SweepReport(), "a pulled read is in flight"
        clock.now += DISPATCH_WINDOW + timedelta(seconds=1)
        report = jobs.sweep()

    assert report.exhausted == [connection]
    draft = read(service, connection)
    assert (draft.status, draft.error_code) == (
        "needs_attention",
        "document_preparation_interrupted",
    )
    assert service.store.pull(now=clock(), cap=3) is None
    assert extractor.calls == 0


@pytest.mark.asyncio
async def test_a_claimed_read_that_died_before_the_provider_is_read_again_once(pull):
    service, jobs, clock, extractor = pull
    [connection] = await waiting(service, jobs)
    original, kills = service.store.source, [support.WorkerKilled()]

    def source(**kwargs: Any) -> bytes | None:
        if kills:
            raise kills.pop()
        return original(**kwargs)

    service.store.source = source  # type: ignore[method-assign]
    taken = service.store.pull(now=clock(), cap=3)
    with pytest.raises(support.WorkerKilled):
        await run_attempt(service, *taken)
    assert attempt(service, connection).claimed

    assert jobs.sweep().redispatched == [connection]
    retried = attempt(service, connection)
    assert (retried.attempt, retried.dispatched_at) == (2, None)
    assert await run_attempt(service, *service.store.pull(now=clock(), cap=3)) == (
        "prepared"
    )
    assert extractor.calls == 1


@pytest.mark.asyncio
async def test_a_claimed_read_that_died_after_the_provider_waits_for_the_owner(pull):
    service, jobs, clock, extractor = pull
    [connection] = await waiting(service, jobs)
    original, kills = extractor.extract, [support.WorkerKilled()]

    async def killed(**kwargs: Any) -> ExtractionBatch:
        if kills:
            extractor.calls += 1
            raise kills.pop()
        return await original(**kwargs)

    extractor.extract = killed
    taken = service.store.pull(now=clock(), cap=3)
    with pytest.raises(support.WorkerKilled):
        await run_attempt(service, *taken)

    assert jobs.sweep().outcome_unknown == [connection]
    assert read(service, connection).error_code == OUTCOME_UNKNOWN
    assert service.store.pull(now=clock(), cap=3) is None
    assert extractor.calls == 1, "an uncertain read is never billed again"

    service.queue(user_id=OWNER, connection_id=connection, consent=True, scope=PERSONAL)
    jobs.start(user_id=OWNER, connection_id=connection)
    assert await run_attempt(service, *service.store.pull(now=clock(), cap=3)) == (
        "prepared"
    )
    assert extractor.calls == 2
    assert service.hub.sink.submit.call_count == 1


@pytest.mark.asyncio
async def test_a_saved_read_replays_through_the_queue_with_no_provider_call(pull):
    service, jobs, clock, extractor = pull
    [connection] = await waiting(service, jobs)
    service.hub.sink.submit.side_effect = [
        RuntimeError("delivery down"),
        SubmitResult(1, 0, 0),
    ]
    taken = service.store.pull(now=clock(), cap=3)
    assert await run_attempt(service, *taken) == "document_delivery_failed"
    assert read(service, connection).status == "needs_attention"
    assert extractor.calls == 1

    service.queue(user_id=OWNER, connection_id=connection, consent=True, scope=PERSONAL)
    jobs.start(user_id=OWNER, connection_id=connection)

    assert read(service, connection).status == "queued", "the wait shows as a read"
    assert await run_attempt(service, *service.store.pull(now=clock(), cap=3)) == (
        "prepared"
    )
    assert read(service, connection).status == "review_ready"
    assert extractor.calls == 1


@pytest.mark.asyncio
async def test_an_edit_while_waiting_gets_a_fresh_attempt_from_the_sweep(pull):
    service, jobs, clock, extractor = pull
    [connection] = await waiting(service, jobs)
    stale = attempt(service, connection).attempt_id
    service.update_proposal(
        user_id=OWNER,
        scope=PERSONAL,
        connection_id=connection,
        version=read(service, connection).version,
        proposal=DraftProposal(requested_plan="Trip"),
    )
    assert service.store.pull(now=clock(), cap=3) is None, "that attempt cannot claim"

    assert jobs.sweep().redispatched == [connection]
    fresh = attempt(service, connection)
    assert (fresh.attempt, fresh.dispatched_at) == (1, None)
    assert fresh.attempt_id != stale
    assert service.store.pull(now=clock(), cap=3) == (connection, fresh.attempt_id)


@pytest.mark.asyncio
async def test_a_worker_reads_oldest_first_and_never_passes_the_cap(
    rig, worker_env
) -> None:
    service, _, clock, _, _ = rig
    gauge = service.extractor = Gauge()
    jobs = PreparationJobs(service, None)
    connections = await waiting(service, jobs, 5)
    stop = asyncio.Event()
    running = asyncio.create_task(
        DocumentWorker(service, settings(max_reads=2)).run(stop)
    )

    await until(lambda: gauge.running == 2)
    await asyncio.sleep(0.05)
    assert gauge.read == connections[:2]

    gauge.release.set()
    await until(lambda: len(gauge.read) == 5)
    await until(
        lambda: all(read(service, c).status == "review_ready" for c in connections)
    )
    stop.set()
    await running

    assert gauge.peak == 2
    assert gauge.read == connections


@pytest.mark.asyncio
async def test_stop_takes_no_new_read_and_lets_reads_in_flight_finish(
    rig, worker_env
) -> None:
    service, _, clock, _, _ = rig
    gauge = service.extractor = Gauge()
    jobs = PreparationJobs(service, None)
    first, second = await waiting(service, jobs, 2)
    stop = asyncio.Event()
    running = asyncio.create_task(
        DocumentWorker(service, settings(max_reads=1)).run(stop)
    )
    await until(lambda: gauge.running == 1)

    stop.set()
    await asyncio.sleep(0.05)
    assert not running.done(), "the drain waits for the read in flight"
    gauge.release.set()
    await running

    assert read(service, first).status == "review_ready"
    assert read(service, second).status == "queued"
    assert attempt(service, second).dispatched_at is None
    assert gauge.read == [first]


@pytest.mark.asyncio
async def test_stop_ends_the_pulls_even_with_slots_free(rig, worker_env) -> None:
    service, _, clock, _, _ = rig
    gauge = service.extractor = Gauge()
    gauge.release.set()
    jobs = PreparationJobs(service, None)
    first, second, third = await waiting(service, jobs, 3)
    stop = asyncio.Event()
    original = service.store.pull

    def pull(**kwargs: Any) -> tuple[str, str] | None:
        stop.set()
        return original(**kwargs)

    service.store.pull = pull  # type: ignore[method-assign]
    await DocumentWorker(service, settings()).run(stop)

    assert gauge.read == [first]
    assert attempt(service, second).dispatched_at is None
    assert attempt(service, third).dispatched_at is None


@pytest.mark.asyncio
async def test_a_read_past_the_drain_bound_stays_recoverable(rig, worker_env) -> None:
    service, _, clock, _, _ = rig
    gauge = service.extractor = Gauge()
    jobs = PreparationJobs(service, None)
    [connection] = await waiting(service, jobs)
    stop = asyncio.Event()
    worker = DocumentWorker(service, settings(drain_seconds=0.01))
    running = asyncio.create_task(worker.run(stop))
    await until(lambda: gauge.running == 1)

    stop.set()
    await asyncio.wait_for(running, 5)

    assert jobs.sweep().outcome_unknown == [connection]
    assert read(service, connection).error_code == OUTCOME_UNKNOWN
    assert gauge.read == [connection], "reached the provider, so never billed twice"


@pytest.mark.asyncio
async def test_with_extraction_off_a_waiting_read_neither_runs_nor_fails(
    pull, monkeypatch
) -> None:
    service, jobs, clock, extractor = pull
    monkeypatch.delenv("CUADRAO_DOCUMENT_EXTRACTION_ENABLED", raising=False)
    monkeypatch.delenv("ARGUS_DOCUMENT_EXTRACTION_ENABLED", raising=False)
    monkeypatch.setattr(document_worker, "POLL_SECONDS", 0.01)
    [connection] = await waiting(service, jobs)
    stop = asyncio.Event()

    running = asyncio.create_task(DocumentWorker(service, settings()).run(stop))
    await asyncio.sleep(0.05)
    stop.set()
    await running

    assert read(service, connection).status == "queued"
    assert attempt(service, connection).dispatched_at is None
    assert extractor.calls == 0


@pytest.mark.asyncio
async def test_a_pull_failure_leaves_the_worker_running(rig, worker_env) -> None:
    service, _, clock, _, _ = rig
    gauge = service.extractor = Gauge()
    jobs = PreparationJobs(service, None)
    [connection] = await waiting(service, jobs)
    original, failures = service.store.pull, [ConnectionError("database down")]

    def pull(**kwargs: Any) -> tuple[str, str] | None:
        if failures:
            raise failures.pop()
        return original(**kwargs)

    service.store.pull = pull  # type: ignore[method-assign]
    stop = asyncio.Event()
    running = asyncio.create_task(DocumentWorker(service, settings()).run(stop))
    await until(lambda: gauge.running == 1)
    gauge.release.set()
    await until(lambda: read(service, connection).status == "review_ready")
    stop.set()
    await running


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"CUADRAO_DOCUMENT_JOBS_ENABLED": "true"},
        {"CUADRAO_DOCUMENT_JOBS_PULL_ENABLED": "true"},
    ],
)
@pytest.mark.asyncio
async def test_the_worker_command_refuses_to_run_unless_pull_mode_is_on(
    monkeypatch, env
) -> None:
    for name in JOB_SETTINGS:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.replace("CUADRAO_", "ARGUS_"), raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    with pytest.raises(SystemExit, match="pull mode is off"):
        await serve()


@pytest.fixture
def pull_env(monkeypatch):
    monkeypatch.setenv("ARGUS_DOCUMENT_JOBS_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_DOCUMENT_JOBS_PULL_ENABLED", "true")
    monkeypatch.setenv("ARGUS_DOCUMENT_JOBS_SWEEP_SECONDS", "0.02")


@pytest.fixture
def pull_client(pull_env, client):
    return client


def test_the_api_records_the_attempt_and_leaves_the_read_and_sweep_to_the_worker(
    pull_client, monkeypatch
):
    provider = api.Provider("succeed")
    clock = api.install(monkeypatch, provider)
    connection = api.upload(pull_client)

    job = api.job(connection)
    assert (job.attempt, job.dispatched_at) == (1, None)
    assert api.document(pull_client, connection)["status"] == "queued"

    service = document_jobs().service
    assert service.store.pull(now=clock(), cap=1) == (connection, job.attempt_id)
    clock.offset = DISPATCH_WINDOW * 2
    time.sleep(0.1)

    assert provider.calls == 0, "no read runs in the API"
    assert api.job(connection).attempt == 1, "no sweep runs in the API"


def test_the_owner_retry_in_the_api_waits_in_the_queue_too(pull_client, monkeypatch):
    provider = api.Provider("succeed")
    clock = api.install(monkeypatch, provider)
    connection = api.upload(pull_client)
    service = document_jobs().service
    owner = service.store.owner(connection_id=connection)
    draft = service.store.draft(user_id=owner, connection_id=connection)
    service._update(owner, draft, status="needs_attention", error_code="anything")

    assert api.retry_with_consent(pull_client, connection).status_code == 200

    time.sleep(0.05)
    assert provider.calls == 0
    assert api.document(pull_client, connection)["status"] == "queued"
    assert service.store.pull(now=clock(), cap=1) == (
        connection,
        api.job(connection).attempt_id,
    )


def test_pull_off_keeps_the_api_on_its_own_dispatch_and_sweep(jobs_client, monkeypatch):
    provider = api.Provider("succeed")
    api.install(monkeypatch, provider)
    connection = api.upload(jobs_client)

    api.wait_for(
        lambda: api.document(jobs_client, connection)["status"] == "review_ready"
    )
    assert provider.calls == 1
    assert api.job(connection).dispatched_at is not None
    assert document_jobs().dispatch is not None


def test_reads_at_once_default_to_three_and_pull_stays_off(monkeypatch):
    for name in JOB_SETTINGS:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.replace("CUADRAO_", "ARGUS_"), raising=False)
    loaded = load_document_job_settings()
    assert (loaded.pull, loaded.max_reads, loaded.drain_seconds) == (False, 3, 120.0)


def test_job_settings_are_declared_off_on_staging_and_absent_from_production():
    profile = json.loads(
        (ROOT / ".github/private-alpha-release-profile.json").read_text()
    )
    manifest = json.loads((ROOT / "scripts/ops/staging_env_manifest.json").read_text())
    services = {
        service["name"]: service
        for service in yaml.safe_load((ROOT / "render.yaml").read_text())["services"]
    }
    example = (ROOT / ".env.example").read_text()
    entries = {e["name"]: e for e in manifest["services"]["api"]["entries"]}
    staging = {e["key"]: e for e in services["cuadrao-api-staging"]["envVars"]}

    for name, value in JOB_SETTINGS.items():
        assert name in profile["staging_only"]["api"]["settings"]
        assert entries[name]["value"] == value
        assert staging[name]["value"] == value
        assert f"{name}={value}\n" in example
        assert name not in profile["services"]["api"]["env"]
        assert name not in {e["key"] for e in services["cuadrao-api"]["envVars"]}
    assert not any(service["type"] == "worker" for service in services.values())
