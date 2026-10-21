"""Document preparation jobs recover a dead worker while the API keeps running.

The worker is this process's in-process fallback; the provider is scripted, so
no model is called. The sweep runs on its own cadence inside the running app.
"""

import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from argus.api.document_jobs import document_jobs
from argus.api.documents import documents_service
from argus.domain.ingestion.documents.jobs import DISPATCH_WINDOW, MAX_ATTEMPTS
from argus.domain.owner_scope import PERSONAL

from tests.ingestion.conftest import ALICE, bearer

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

        behavior = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        if behavior == "fail":
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
def jobs_env(monkeypatch):
    monkeypatch.setenv("ARGUS_DOCUMENT_JOBS_ENABLED", "true")
    monkeypatch.setenv("ARGUS_DOCUMENT_JOBS_SWEEP_SECONDS", "0.02")


@pytest.fixture
def jobs_client(jobs_env, client):
    return client


@pytest.fixture
def jobs_off(monkeypatch):
    monkeypatch.setenv("ARGUS_DOCUMENT_JOBS_ENABLED", "")


@pytest.fixture
def flag_off_client(jobs_off, client):
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
    return list(document_jobs().dispatch.tasks)


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


def test_kill_after_the_provider_marker_waits_for_a_consented_retry(
    jobs_client, monkeypatch
):
    provider = Provider("hang", "succeed")
    clock = install(monkeypatch, provider)
    connection = upload(jobs_client)
    wait_for(lambda: provider.calls == 1)
    assert job(connection).provider_call_started_at is not None

    clock.offset = DISPATCH_WINDOW + timedelta(seconds=1)
    wait_for(lambda: document(jobs_client, connection)["status"] == "needs_attention")
    settled = document(jobs_client, connection)
    assert settled["error_code"] == "document_preparation_outcome_unknown"
    time.sleep(0.2)
    assert provider.calls == 1, "an uncertain attempt is never billed again"
    assert job(connection).attempt == 1

    refused = retry_with_consent(jobs_client, connection, consent=False)
    assert refused.status_code == 422
    assert refused.json()["code"] == "document_extraction_consent_required"
    assert provider.calls == 1

    assert retry_with_consent(jobs_client, connection).status_code == 200
    wait_for(lambda: document(jobs_client, connection)["status"] == "review_ready")
    assert provider.calls == 2
    assert job(connection).attempt == 1, "an owner retry starts a new preparation"
    assert len(imports(jobs_client)) == 1

    before = document(jobs_client, connection)
    [stale] = stale_attempts()
    provider.release.set()
    wait_for(stale.done)
    assert stale.result() == "document_lease_lost"
    assert document(jobs_client, connection) == before
    assert [c["amount"] for c in before["preparation"]["candidates"]] == ["250.5"]
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


def test_flag_off_prepares_through_background_tasks_only(flag_off_client, monkeypatch):
    provider = Provider("succeed")
    install(monkeypatch, provider)
    service = documents_service()
    calls = []
    original = service.background_prepare

    async def spy(**kwargs):
        calls.append(kwargs)
        await original(**kwargs)

    monkeypatch.setattr(service, "background_prepare", spy)
    assert document_jobs() is None
    assert service.jobs_recover_interruptions is False

    connection = upload(flag_off_client)

    user = service.store.owner(connection_id=connection)
    assert calls == [{"user_id": user, "connection_id": connection, "scope": PERSONAL}]
    assert document(flag_off_client, connection)["status"] == "review_ready"
    assert service.store.job(user_id=user, connection_id=connection) is None
    assert provider.calls == 1


@pytest.mark.parametrize(
    "env,enabled,sweep",
    [
        ({}, False, 30.0),
        ({"ARGUS_DOCUMENT_JOBS_ENABLED": "yes"}, True, 30.0),
        ({"ARGUS_DOCUMENT_JOBS_ENABLED": "maybe"}, False, 30.0),
        (
            {
                "ARGUS_DOCUMENT_JOBS_ENABLED": "1",
                "ARGUS_DOCUMENT_JOBS_SWEEP_SECONDS": "5",
            },
            True,
            5.0,
        ),
        (
            {
                "ARGUS_DOCUMENT_JOBS_ENABLED": "1",
                "ARGUS_DOCUMENT_JOBS_SWEEP_SECONDS": "x",
            },
            False,
            30.0,
        ),
    ],
)
def test_job_settings_share_the_document_convention(monkeypatch, env, enabled, sweep):
    from argus.domain.ingestion.documents.config import load_document_job_settings

    for name in (
        "ARGUS_DOCUMENT_JOBS_ENABLED",
        "ARGUS_DOCUMENT_JOBS_SWEEP_SECONDS",
        "ARGUS_DOCUMENT_JOBS_WORKFLOW_TASK",
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    settings = load_document_job_settings()
    assert (settings.enabled, settings.sweep_seconds) == (enabled, sweep)
