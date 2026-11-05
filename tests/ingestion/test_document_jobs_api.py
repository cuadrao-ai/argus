"""Document preparation jobs recover a dead worker while the API keeps running.

The worker is this process's in-process fallback; the provider is scripted, so
no model is called. The sweep runs on its own cadence inside the running app.
"""

import asyncio
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from argus.api import state as api_state
from argus.api.document_jobs import (
    document_worker,
    drain_document_jobs,
    start_document_jobs,
    stop_document_jobs,
)
from argus.api.documents import dispatch_preparation, documents_service
from argus.api.main import app
from argus.domain.ingestion.documents import worker as reading
from argus.domain.ingestion.documents.config import DocumentJobSettings
from argus.domain.ingestion.documents.jobs import (
    DISPATCH_WINDOW,
    MAX_ATTEMPTS,
    PreparationJobs,
)
from argus.domain.ingestion.documents.worker import DocumentWorker
from argus.domain.owner_scope import PERSONAL
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient

from tests.document_extractor_support import admit
from tests.ingestion import test_document_jobs_recharge as support
from tests.ingestion.conftest import ALICE, bearer

rig = support.rig

DOCUMENTS = "/api/v1/financial-documents"
IMPORTS = "/api/v1/financial-imports"
RECEIPT = Path(__file__).parents[1] / "document_extraction_fixtures/receipt-dop.png"


def observation(amount: str) -> dict[str, object]:
    return {
        "complete": True,
        "readable": True,
        "pages_read": [1],
        "observations": [
            {
                "page": 1,
                "row": 1,
                "evidence": "transaction",
                "status": "posted",
                "amount": amount,
                "currency": "DOP",
                "occurred_on": "2026-09-10",
                "direction": "outflow",
                "kind_hint": "expense",
            }
        ],
    }




class Provider:
    """Scripted provider: each call takes the next behavior from ``script``."""

    def __init__(self, *script: str) -> None:
        self.script, self.calls = list(script), 0
        self.release = threading.Event()

    async def __call__(self, **kwargs: object) -> object:
        import asyncio

        from argus.domain.ingestion.documents.models import ExtractionResult

        await admit(kwargs.get("before_request"))
        behavior = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        if behavior == "fail":
            raise RuntimeError("provider failed")
        if behavior == "timeout":
            raise TimeoutError("provider timed out")
        if behavior == "hang":
            while not self.release.is_set():
                await asyncio.sleep(0.01)
            return ExtractionResult.model_validate(observation("999.00"))
        return ExtractionResult.model_validate(observation("250.50"))


class Clock:
    def __init__(self) -> None:
        self.start = datetime.now(timezone.utc)
        self.offset = timedelta()

    def __call__(self) -> datetime:
        return self.start + self.offset


@pytest.fixture
def reads_finish_inside_the_request():
    """These tests watch the app's real puller, so no read runs in the request."""


@pytest.fixture
def jobs_env(monkeypatch):
    """The sweep and the pull on a test cadence; nothing else to turn on."""
    monkeypatch.setenv("ARGUS_DOCUMENT_JOBS_SWEEP_SECONDS", "0.02")
    monkeypatch.setattr(reading, "POLL_SECONDS", 0.01)


@pytest.fixture
def jobs_client(jobs_env, client):
    return client


def install(monkeypatch, provider: Provider) -> Clock:
    from argus.domain.ingestion.documents import extractor
    from argus.domain.ingestion.documents.config import DocumentExtractionSettings

    monkeypatch.setenv("ARGUS_DOCUMENT_EXTRACTION_ENABLED", "true")
    monkeypatch.setenv("ARGUS_VISION_MODEL", "test/vision")
    monkeypatch.setenv("OPENROUTER_API_KEY", "offline-test-key")
    service = documents_service()
    monkeypatch.setattr(extractor, "invoke_openrouter_json_schema", provider)
    monkeypatch.setattr(
        service,
        "extractor",
        extractor.DocumentExtractor(DocumentExtractionSettings(enabled=True)),
    )
    clock = Clock()
    monkeypatch.setattr(service.hub, "clock", clock)
    return clock


def wait_for(predicate, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "condition not reached"
        time.sleep(0.01)


def upload(client) -> str:
    response = client.post(
        DOCUMENTS,
        content=RECEIPT.read_bytes(),
        headers={
            **bearer(ALICE),
            "Content-Type": "image/png",
            "X-Extraction-Consent": "true",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "queued"
    return response.json()["connection_id"]


def document(client, connection: str) -> dict:
    return client.get(f"{DOCUMENTS}/{connection}", headers=bearer(ALICE)).json()


def imports(client) -> list[dict]:
    return client.get(IMPORTS, headers=bearer(ALICE)).json()["items"]


def job(connection: str):
    service = documents_service()
    user = service.store.owner(connection_id=connection)
    return service.store.job(user_id=user, connection_id=connection)


class SourceGate:
    """Holds the first ``blocked`` source reads: a worker that dies after claiming
    the draft and before its provider marker, with its lease still held."""

    def __init__(self, blocked: int) -> None:
        self.blocked, self.entered = blocked, 0
        self.release = threading.Event()
        self._lock = threading.Lock()

    def wrap(self, original):
        def source(**kwargs):
            with self._lock:
                self.entered += 1
                hold = self.entered <= self.blocked
            if hold:
                self.release.wait(10)
            return original(**kwargs)

        return source


@pytest.fixture
def gate(jobs_client, monkeypatch):
    holder = {}

    def install_gate(blocked: int = 1) -> SourceGate:
        store = documents_service().store
        holder["gate"] = SourceGate(blocked)
        monkeypatch.setattr(store, "source", holder["gate"].wrap(store.source))
        return holder["gate"]

    yield install_gate
    if "gate" in holder:
        holder["gate"].release.set()


def retry_with_consent(client, connection: str, consent: bool = True):
    headers = (
        {**bearer(ALICE), "X-Extraction-Consent": "true"} if consent else bearer(ALICE)
    )
    return client.post(f"{DOCUMENTS}/{connection}/resume", headers=headers)


def stale_attempts():
    return list(document_worker().reads)


def test_kill_before_the_provider_marker_recovers_with_one_provider_call(
    jobs_client, gate, monkeypatch
):
    provider = Provider("succeed")
    clock = install(monkeypatch, provider)
    held = gate()
    connection = upload(jobs_client)
    wait_for(lambda: held.entered == 1)
    assert document(jobs_client, connection)["status"] == "preparing"
    assert job(connection).provider_call_started_at is None

    clock.offset = DISPATCH_WINDOW - timedelta(seconds=1)
    time.sleep(0.2)
    assert job(connection).attempt == 1, "a live lease is never superseded"

    clock.offset = DISPATCH_WINDOW + timedelta(seconds=1)
    wait_for(lambda: document(jobs_client, connection)["status"] == "review_ready")
    assert provider.calls == 1
    assert job(connection).attempt == 2
    assert job(connection).provider_call_started_at is not None
    assert len(imports(jobs_client)) == 1

    before = document(jobs_client, connection)
    [stale] = stale_attempts()
    held.release.set()
    wait_for(stale.done)
    assert stale.result() == "document_lease_lost"
    assert provider.calls == 1, "the superseded attempt never reaches the provider"
    assert document(jobs_client, connection) == before


def test_a_read_cut_off_after_the_provider_marker_is_read_once_more(
    jobs_client, monkeypatch
):
    provider = Provider("hang", "succeed")
    install(monkeypatch, provider)
    connection = upload(jobs_client)
    wait_for(lambda: provider.calls == 1)
    assert job(connection).provider_call_started_at is not None
    [running] = stale_attempts()

    running.cancel()

    wait_for(lambda: document(jobs_client, connection)["status"] == "review_ready")
    assert document(jobs_client, connection)["error_code"] is None
    assert provider.calls == 2, "the rerun is one more paid call"
    assert (job(connection).attempt, job(connection).reruns) == (2, 1)
    assert len(imports(jobs_client)) == 1


def test_both_completions_of_one_receipt_save_once(jobs_client, monkeypatch):
    provider = Provider("hang", "succeed")
    clock = install(monkeypatch, provider)
    connection = upload(jobs_client)
    wait_for(lambda: provider.calls == 1)
    assert job(connection).provider_call_started_at is not None

    clock.offset = DISPATCH_WINDOW + timedelta(seconds=1)
    wait_for(lambda: document(jobs_client, connection)["status"] == "review_ready")
    assert provider.calls == 2
    assert (job(connection).attempt, job(connection).reruns) == (2, 1)
    assert len(imports(jobs_client)) == 1

    before = document(jobs_client, connection)
    wait_for(lambda: len(stale_attempts()) == 1)
    [stale] = stale_attempts()
    provider.release.set()
    wait_for(stale.done)
    assert stale.result() == "document_lease_lost"
    assert document(jobs_client, connection) == before
    assert [c["amount"] for c in before["preparation"]["candidates"]] == ["250.5"]
    assert len(imports(jobs_client)) == 1


def test_a_rerun_cut_off_after_its_marker_is_one_clear_failure(jobs_client, monkeypatch):
    provider = Provider("hang", "hang", "succeed")
    install(monkeypatch, provider)
    connection = upload(jobs_client)
    for call in (1, 2):
        wait_for(lambda call=call: provider.calls == call)
        wait_for(lambda: len(stale_attempts()) == 1)
        [running] = stale_attempts()
        running.cancel()

    wait_for(lambda: document(jobs_client, connection)["status"] == "needs_attention")
    settled = document(jobs_client, connection)
    assert settled["error_code"] == "document_preparation_outcome_unknown"
    time.sleep(0.2)
    assert provider.calls == 2, "one paid rerun, then the owner decides"
    assert (job(connection).attempt, job(connection).reruns) == (2, 1)

    refused = retry_with_consent(jobs_client, connection, consent=False)
    assert refused.status_code == 422
    assert refused.json()["code"] == "document_extraction_consent_required"
    assert provider.calls == 2

    assert retry_with_consent(jobs_client, connection).status_code == 200
    wait_for(lambda: document(jobs_client, connection)["status"] == "review_ready")
    assert provider.calls == 3
    assert job(connection).attempt == 1, "an owner retry starts a new preparation"
    assert len(imports(jobs_client)) == 1


def test_cancelled_worker_before_the_marker_recovers_on_the_next_sweep(
    jobs_client, gate, monkeypatch
):
    provider = Provider("succeed")
    install(monkeypatch, provider)
    held = gate()
    connection = upload(jobs_client)
    wait_for(lambda: held.entered == 1)
    [worker] = stale_attempts()

    worker.cancel()

    wait_for(lambda: document(jobs_client, connection)["status"] == "review_ready")
    assert provider.calls == 1
    assert len(imports(jobs_client)) == 1


def test_reported_provider_failure_is_not_retried_automatically(jobs_client, monkeypatch):
    provider = Provider("fail", "succeed")
    install(monkeypatch, provider)
    connection = upload(jobs_client)
    wait_for(lambda: document(jobs_client, connection)["status"] == "needs_attention")
    assert document(jobs_client, connection)["error_code"] == (
        "extraction_provider_failed"
    )
    time.sleep(0.2)
    assert provider.calls == 1
    assert job(connection).retry is False

    assert retry_with_consent(jobs_client, connection).status_code == 200
    wait_for(lambda: document(jobs_client, connection)["status"] == "review_ready")
    assert provider.calls == 2


def test_a_timed_out_read_is_read_once_more_and_shown_as_one(jobs_client, monkeypatch):
    provider = Provider("timeout", "succeed")
    install(monkeypatch, provider)
    connection = upload(jobs_client)
    wait_for(lambda: document(jobs_client, connection)["status"] == "review_ready")
    assert document(jobs_client, connection)["error_code"] is None
    assert provider.calls == 2
    assert job(connection).retry is False
    assert len(imports(jobs_client)) == 1


def test_a_second_timeout_is_one_clear_failure_the_owner_reads_again(
    jobs_client, monkeypatch
):
    provider = Provider("timeout", "timeout", "succeed")
    install(monkeypatch, provider)
    connection = upload(jobs_client)
    wait_for(lambda: document(jobs_client, connection)["status"] == "needs_attention")
    assert document(jobs_client, connection)["error_code"] == (
        "extraction_provider_failed"
    )
    time.sleep(0.2)
    assert provider.calls == 2
    assert job(connection).retry is False

    assert retry_with_consent(jobs_client, connection).status_code == 200
    wait_for(lambda: document(jobs_client, connection)["status"] == "review_ready")
    assert provider.calls == 3
    assert len(imports(jobs_client)) == 1


def test_attempts_dying_before_the_marker_stop_at_the_bound(
    jobs_client, gate, monkeypatch
):
    provider = Provider("succeed")
    clock = install(monkeypatch, provider)
    held = gate(blocked=MAX_ATTEMPTS)
    connection = upload(jobs_client)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        wait_for(lambda attempt=attempt: held.entered == attempt)
        clock.offset += DISPATCH_WINDOW + timedelta(seconds=1)
    wait_for(lambda: document(jobs_client, connection)["status"] == "needs_attention")
    assert document(jobs_client, connection)["error_code"] == (
        "document_preparation_interrupted"
    )
    time.sleep(0.2)
    assert held.entered == MAX_ATTEMPTS
    assert provider.calls == 0

    held.release.set()
    assert retry_with_consent(jobs_client, connection).status_code == 200
    wait_for(lambda: document(jobs_client, connection)["status"] == "review_ready")
    assert provider.calls == 1


@contextmanager
def running_app(gateway) -> Iterator[TestClient]:
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
        TestClient(app) as test_client,
    ):
        yield test_client


def test_shutdown_lets_a_read_in_flight_finish_inside_the_drain(
    jobs_env, ingestion_env, gateway, monkeypatch
):
    monkeypatch.setenv("ARGUS_DOCUMENT_JOBS_DRAIN_SECONDS", "5")
    with running_app(gateway) as client:
        provider = Provider("hang")
        install(monkeypatch, provider)
        service = documents_service()
        connection = upload(client)
        wait_for(lambda: provider.calls == 1)
        user = service.store.owner(connection_id=connection)
        threading.Timer(0.3, provider.release.set).start()
        stopping = time.monotonic()

    assert time.monotonic() - stopping >= 0.3, "shutdown waited for the read"
    draft = service.store.draft(user_id=user, connection_id=connection)
    assert (draft.status, provider.calls) == ("review_ready", 1)


def test_shutdown_cancels_a_read_past_the_drain_for_the_next_boot_to_rerun(
    jobs_env, ingestion_env, gateway, monkeypatch
):
    monkeypatch.setenv("ARGUS_DOCUMENT_JOBS_DRAIN_SECONDS", "0.05")
    with running_app(gateway) as client:
        provider = Provider("hang", "succeed")
        install(monkeypatch, provider)
        service = documents_service()
        connection = upload(client)
        wait_for(lambda: provider.calls == 1)
        user = service.store.owner(connection_id=connection)

    row = service.hub.connections.get_any_scope(user_id=user, connection_id=connection)
    assert row.lease_until is None, "the cancelled read released its lease"
    assert service.store.draft(user_id=user, connection_id=connection).status == (
        "preparing"
    )
    booted = PreparationJobs(service)
    assert booted.sweep().rerun == [connection]
    job = service.store.job(user_id=user, connection_id=connection)
    assert (job.reruns, job.dispatched_at) == (1, None), "waits for the next puller"
    assert service.store.pull(now=service.hub.clock(), cap=1) == (
        connection,
        job.attempt_id,
    )
    assert provider.calls == 1, "nothing ran again before the next boot"


@pytest.fixture
def paused_sweep(monkeypatch):
    """The sweep holds on its thread until released, then runs or raises."""
    original = PreparationJobs.sweep
    entered, release, failure = threading.Event(), threading.Event(), []

    def gated(self, **kwargs):  # noqa: ANN001, ANN003, ANN202
        entered.set()
        release.wait(10)
        if failure:
            raise failure[0]
        return original(self, **kwargs)

    monkeypatch.setattr(PreparationJobs, "sweep", gated)
    yield entered, release, failure
    release.set()


def puller_settings(**changes):  # noqa: ANN003, ANN201
    return DocumentJobSettings(**{"sweep_seconds": 3600, "drain_seconds": 5, **changes})


async def read_by_the_next_boot(service, connection: str) -> None:  # noqa: ANN001
    start_document_jobs(service, puller_settings())
    try:
        for _ in range(500):
            draft = service.get(user_id="owner", connection_id=connection, scope=PERSONAL)
            if draft.status == "review_ready":
                break
            await asyncio.sleep(0.01)
        assert draft.status == "review_ready"
    finally:
        await drain_document_jobs()
        stop_document_jobs()


@pytest.mark.asyncio
async def test_shutdown_joins_a_running_sweep_and_leaves_its_read_to_the_next_boot(
    rig, paused_sweep, monkeypatch
):
    service, _, clock, extractor, _ = rig
    monkeypatch.setenv("CUADRAO_DOCUMENT_EXTRACTION_ENABLED", "true")
    monkeypatch.setattr(reading, "POLL_SECONDS", 0.01)
    entered, release, _ = paused_sweep
    connection = await support.queued(service)
    # Past the window the upload's own start had, so the sweep requeues it.
    clock.now += DISPATCH_WINDOW + timedelta(seconds=1)
    start_document_jobs(service, puller_settings())
    try:
        await asyncio.to_thread(entered.wait, 5)
        draining = asyncio.create_task(drain_document_jobs())
        await asyncio.sleep(0.05)
        assert not draining.done(), "the drain waits for the sweep on its thread"

        release.set()
        await asyncio.wait_for(draining, 5)
    finally:
        stop_document_jobs()

    assert extractor.calls == 0, "a stopped puller takes no read the sweep requeued"
    job = service.store.job(user_id="owner", connection_id=connection)
    assert (job.attempt, job.dispatched_at) == (1, None)

    await read_by_the_next_boot(service, connection)
    assert extractor.calls == 1


@pytest.mark.asyncio
async def test_a_sweep_that_raises_after_the_cancel_does_not_hold_the_drain(
    rig, paused_sweep, monkeypatch
):
    service, _, _, extractor, _ = rig
    monkeypatch.setenv("CUADRAO_DOCUMENT_EXTRACTION_ENABLED", "true")
    entered, release, failure = paused_sweep
    failure.append(RuntimeError("database away"))
    start_document_jobs(service, puller_settings())
    try:
        await asyncio.to_thread(entered.wait, 5)
        draining = asyncio.create_task(drain_document_jobs())
        await asyncio.sleep(0.05)
        assert not draining.done()

        release.set()
        await asyncio.wait_for(draining, 5)
    finally:
        stop_document_jobs()
    assert extractor.calls == 0


@pytest.mark.asyncio
async def test_a_cancel_while_the_puller_joins_its_sweep_stops_it(rig, paused_sweep, monkeypatch):
    """Shutdown past its window cancels the puller while it waits for a sweep
    on its thread: the cancel ends the puller, and it never carries on as if
    the cancel were the sweeper's own."""
    service, _, _, _, _ = rig
    monkeypatch.setenv("CUADRAO_DOCUMENT_EXTRACTION_ENABLED", "true")
    entered, release, _ = paused_sweep
    stop = asyncio.Event()
    running = asyncio.create_task(DocumentWorker(service, puller_settings()).run(stop))
    await asyncio.to_thread(entered.wait, 5)
    stop.set()
    await asyncio.sleep(0.05)
    assert not running.done(), "the puller waits for the sweep on its thread"

    running.cancel()
    release.set()
    await asyncio.wait({running}, timeout=5)
    assert running.cancelled()


@pytest.mark.asyncio
async def test_a_read_queued_while_the_puller_stops_waits_for_the_next_boot(
    rig, monkeypatch
):
    service, _, _, extractor, _ = rig
    monkeypatch.setenv("CUADRAO_DOCUMENT_EXTRACTION_ENABLED", "true")
    monkeypatch.setattr(reading, "POLL_SECONDS", 0.01)
    start_document_jobs(service, puller_settings())
    await drain_document_jobs()
    connection = await support.queued(service)

    await dispatch_preparation(
        service, "owner", connection, BackgroundTasks(), scope=PERSONAL
    )
    await asyncio.sleep(0.05)
    assert extractor.calls == 0, "no read starts after the drain began"
    job = service.store.job(user_id="owner", connection_id=connection)
    assert (job.attempt, job.dispatched_at) == (1, None), "it waits on its row"

    await read_by_the_next_boot(service, connection)
    assert extractor.calls == 1


def test_only_a_puller_reads_a_receipt():
    """Web, email, WhatsApp and "Leer de nuevo" all call ``dispatch_preparation``,
    which records an attempt; the read itself, ``DocumentsService.resume``, has
    one caller outside the service: ``run_attempt``, which only a puller runs."""
    root = Path(__file__).parents[2]
    readers = sorted(
        str(path.relative_to(root))
        for folder in ("src", "workflows")
        for path in (root / folder).rglob("*.py")
        if ".resume(" in path.read_text()
    )
    assert readers == [
        "src/argus/domain/ingestion/documents/jobs.py",
        "src/argus/domain/ingestion/documents/service.py",
    ]
    channels = {
        "src/argus/api/routers/business.py",
        "src/argus/api/routers/financial_documents.py",
        "src/argus/api/email_intake.py",
        "src/argus/api/whatsapp.py",
    }
    assert all("dispatch_preparation(" in (root / name).read_text() for name in channels)


def test_no_setting_turns_the_queue_off(jobs_client, monkeypatch):
    for name in ("CUADRAO_DOCUMENT_JOBS_ENABLED", "CUADRAO_DOCUMENT_JOBS_PULL_ENABLED"):
        monkeypatch.setenv(name, "false")
        monkeypatch.setenv(name.replace("CUADRAO_", "ARGUS_"), "false")
    provider = Provider("succeed")
    install(monkeypatch, provider)
    connection = upload(jobs_client)
    assert job(connection).attempt == 1, "the read is an attempt on the row"
    wait_for(lambda: document(jobs_client, connection)["status"] == "review_ready")
    assert provider.calls == 1


@pytest.mark.parametrize(
    "env,sweep",
    [
        ({}, 30.0),
        ({"ARGUS_DOCUMENT_JOBS_SWEEP_SECONDS": "5"}, 5.0),
        ({"CUADRAO_DOCUMENT_JOBS_SWEEP_SECONDS": "5"}, 5.0),
        ({"ARGUS_DOCUMENT_JOBS_SWEEP_SECONDS": "x"}, 30.0),
    ],
)
def test_job_settings_share_the_document_convention(monkeypatch, env, sweep):
    from argus.domain.ingestion.documents.config import load_document_job_settings

    for name in ("ARGUS_DOCUMENT_JOBS_SWEEP_SECONDS", "CUADRAO_DOCUMENT_JOBS_SWEEP_SECONDS"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    settings = load_document_job_settings()
    assert (settings.sweep_seconds, settings.max_reads) == (sweep, 3)
    assert not hasattr(settings, "enabled") and not hasattr(settings, "pull")
