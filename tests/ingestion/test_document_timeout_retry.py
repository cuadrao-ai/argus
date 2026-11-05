"""A read whose provider call times out is read once more inside the same
attempt, under the same lease: admitted and charged like any read, saved once,
shown to nobody as a second read. Any other provider error, and a second
timeout, settle the receipt so the owner can ask "Leer de nuevo"."""

from __future__ import annotations

import asyncio
import io
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
from argus.domain.business.read_budget import InMemoryReadBudget, ReadBudgetSettings
from argus.domain.ingestion.connections import InMemoryConnectionRepository
from argus.domain.ingestion.documents import extractor as extraction
from argus.domain.ingestion.documents import preparation
from argus.domain.ingestion.documents.config import DocumentExtractionSettings
from argus.domain.ingestion.documents.jobs import PreparationJobs, run_attempt
from argus.domain.ingestion.documents.models import (
    DocumentDraft,
    DocumentExtractionError,
    ExtractionResult,
)
from argus.domain.ingestion.documents.preparation import PreparedDocument
from argus.domain.ingestion.documents.service import (
    DocumentOutcome,
    DocumentServiceError,
    DocumentsService,
)
from argus.domain.ingestion.documents.store import InMemoryDocumentStore
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.owner_scope import BusinessSpace
from argus.llm import openrouter, openrouter_transport
from faker import Faker
from PIL import Image

from tests.business_reading_support import reading_setting, turn_reading
from tests.document_extractor_support import admit
from tests.ingestion.test_document_jobs_api import observation
from tests.ingestion.test_read_budget_local_refusals import poppler

fake = Faker("es_MX")
OK = "ok"
TIMEOUTS = [
    pytest.param(asyncio.TimeoutError, id="call deadline"),
    pytest.param(httpx.ReadTimeout, id="request deadline"),
]
NOT_TIMEOUTS = [
    pytest.param(httpx.ConnectError, id="refused connection"),
    pytest.param(ValueError, id="broken answer"),
]


class Provider:
    """Stands in for the provider call with one scripted answer per call:
    ``OK`` or an exception class. Every call is admitted first, as the real
    call is, so every call is charged. ``gated`` holds each call until the
    test releases it."""

    def __init__(self, *answers: object, gated: bool = False) -> None:
        self.answers, self.calls = list(answers), 0
        self.gate = asyncio.Event() if gated else None
        self.started = asyncio.Event()

    async def __call__(self, **kwargs: object) -> ExtractionResult:
        await admit(kwargs.get("before_request"))
        self.calls += 1
        if self.gate is not None:
            self.started.set()
            await self.gate.wait()
            self.gate.clear()
        answer = self.answers.pop(0)
        if answer is not OK:
            raise answer("the provider never answered")
        return ExtractionResult.model_validate(observation("250.50"))

    def release(self) -> None:
        """Let the held call answer; the next call sets ``started`` again."""
        assert self.gate is not None
        self.started.clear()
        self.gate.set()


class CountingBudget(InMemoryReadBudget):
    def __init__(self, per_day: int) -> None:
        super().__init__(ReadBudgetSettings(per_day=per_day))
        self.asked = self.charged = 0

    def charge(self, business_id: str, now: datetime):  # noqa: ANN201
        self.asked += 1
        refused = super().charge(business_id, now)
        self.charged += refused is None
        return refused


@dataclass
class Rig:
    service: DocumentsService
    budget: CountingBudget
    scope: BusinessSpace
    owner: str
    monkeypatch: pytest.MonkeyPatch
    saves: int = field(default=0)

    def answers(self, *answers: object, gated: bool = False) -> Provider:
        provider = Provider(*answers, gated=gated)
        self.monkeypatch.setattr(extraction, "invoke_openrouter_json_schema", provider)
        return provider

    async def upload(self) -> str:
        outcome = await self.service.upload(
            user_id=self.owner,
            content=b"%PDF-" + fake.uuid4().encode(),
            filename=fake.file_name(extension="pdf"),
            media_type="application/pdf",
            consent=True,
            scope=self.scope,
        )
        return outcome.connection_id

    async def resume(self, connection: str) -> DocumentOutcome:
        return await self.service.resume(
            user_id=self.owner, connection_id=connection, scope=self.scope
        )

    async def read(self, connection: str) -> tuple[str | None, DocumentDraft]:
        try:
            await self.resume(connection)
        except (DocumentServiceError, DocumentExtractionError) as error:
            code = error.code
        else:
            code = None
        return code, self.draft(connection)

    def draft(self, connection: str) -> DocumentDraft:
        return self.service.get(
            user_id=self.owner, connection_id=connection, scope=self.scope
        )


@pytest.fixture
def rig(monkeypatch, request):
    monkeypatch.setenv("ARGUS_VISION_MODEL", "test/vision")
    monkeypatch.setenv("OPENROUTER_API_KEY", "offline-test-key")
    monkeypatch.setattr(preparation, "_run", poppler("Pages: 1\nEncrypted: no\n"))
    repo = InMemoryConnectionRepository()
    hub = IngestionHub(
        repo, box=None, sink=Mock(), clock=lambda: datetime.now(timezone.utc)
    )
    budget = CountingBudget(per_day=getattr(request, "param", 300))
    store = InMemoryDocumentStore(repo)
    service = DocumentsService(
        hub,
        store,
        extraction.DocumentExtractor(DocumentExtractionSettings(enabled=True)),
        business_actions=Mock(),
        read_budget=budget,
    )
    service.business_receipt_consent = reading_setting()
    scope, owner = BusinessSpace(str(uuid4())), str(uuid4())
    turn_reading(service.business_receipt_consent, scope.space_id, owner)
    rig = Rig(service, budget, scope, owner, monkeypatch)
    save = store.save

    def counted_save(**kwargs):  # noqa: ANN003, ANN202
        rig.saves += 1
        return save(**kwargs)

    monkeypatch.setattr(store, "save", counted_save)
    return rig


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout", TIMEOUTS)
async def test_a_timed_out_read_is_read_once_more_and_saved_once(rig, timeout):
    provider = rig.answers(timeout, OK)
    connection = await rig.upload()
    assert (await rig.resume(connection)).status == "review_ready"
    assert rig.draft(connection).error_code is None
    assert (provider.calls, rig.budget.charged, rig.saves) == (2, 2, 1)


@pytest.mark.asyncio
async def test_a_second_timeout_settles_the_receipt_for_leer_de_nuevo(rig):
    provider = rig.answers(asyncio.TimeoutError, asyncio.TimeoutError, OK)
    connection = await rig.upload()
    code, draft = await rig.read(connection)
    assert code == "extraction_provider_failed"
    assert (draft.status, draft.error_code) == (
        "needs_attention",
        "extraction_provider_failed",
    )
    assert draft.source_available
    assert (provider.calls, rig.budget.charged, rig.saves) == (2, 2, 0)

    rig.service.queue(
        user_id=rig.owner, connection_id=connection, consent=True, scope=rig.scope
    )
    assert (await rig.resume(connection)).status == "review_ready"
    assert (provider.calls, rig.budget.charged, rig.saves) == (3, 3, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("error", NOT_TIMEOUTS)
async def test_a_provider_error_that_is_not_a_timeout_is_not_read_again(rig, error):
    provider = rig.answers(error, OK)
    code, draft = await rig.read(await rig.upload())
    assert code == "extraction_provider_failed"
    assert draft.status == "needs_attention"
    assert (provider.calls, rig.budget.charged, rig.saves) == (1, 1, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("rig", [1], indirect=True, ids=["one read a day"])
async def test_a_second_call_over_the_budget_leaves_the_receipt_saved_unread(rig):
    provider = rig.answers(asyncio.TimeoutError, OK)
    code, draft = await rig.read(await rig.upload())
    assert code == "business_read_budget_day"
    assert (draft.status, draft.consent, draft.error_code) == (
        "saved",
        False,
        "business_read_budget_day",
    )
    assert draft.source_available
    assert (provider.calls, rig.budget.asked, rig.budget.charged, rig.saves) == (
        1,
        2,
        1,
        0,
    )


@pytest.mark.asyncio
async def test_nobody_reads_the_receipt_while_it_is_read_once_more(rig):
    provider = rig.answers(asyncio.TimeoutError, OK, gated=True)
    connection = await rig.upload()
    jobs = PreparationJobs(rig.service, None)
    first = asyncio.create_task(rig.resume(connection))
    for call in (1, 2):
        await asyncio.wait_for(provider.started.wait(), timeout=5)
        assert provider.calls == call
        with pytest.raises(DocumentServiceError, match="document_busy"):
            await rig.resume(connection)
        assert jobs.sweep().redispatched == []
        provider.release()
    assert (await first).status == "review_ready"
    assert (provider.calls, rig.budget.charged, rig.saves) == (2, 2, 1)


@pytest.mark.asyncio
async def test_a_worker_attempt_reads_once_more_inside_itself_and_never_again(rig):
    provider = rig.answers(asyncio.TimeoutError, asyncio.TimeoutError)
    connection = await rig.upload()
    jobs = PreparationJobs(rig.service, None)
    jobs.start(user_id=rig.owner, connection_id=connection)
    store = rig.service.store
    attempt = store.job(user_id=rig.owner, connection_id=connection).attempt_id
    assert await run_attempt(rig.service, connection, attempt) == (
        "extraction_provider_failed"
    )
    job = store.job(user_id=rig.owner, connection_id=connection)
    assert job.provider_call_started_at is not None and not job.retry
    assert jobs.sweep().redispatched == []
    assert store.pull(now=rig.service.hub.clock(), cap=3) is None
    assert rig.draft(connection).status == "needs_attention"
    assert (provider.calls, rig.budget.charged) == (2, 2)


@pytest.mark.asyncio
async def test_a_business_read_killed_after_its_call_is_rerun_and_charged_per_call(
    rig,
):
    provider = rig.answers(OK, OK, gated=True)
    connection = await rig.upload()
    rig.service.jobs_recover_interruptions = True
    jobs = PreparationJobs(rig.service, None)
    jobs.start(user_id=rig.owner, connection_id=connection)
    store, clock = rig.service.store, rig.service.hub.clock
    killed = asyncio.create_task(
        run_attempt(rig.service, *store.pull(now=clock(), cap=1))
    )
    await asyncio.wait_for(provider.started.wait(), timeout=5)
    killed.cancel()
    with pytest.raises(asyncio.CancelledError):
        await killed
    assert (provider.calls, rig.budget.charged, rig.saves) == (1, 1, 0)

    assert jobs.sweep().rerun == [connection]
    rerun = asyncio.create_task(
        run_attempt(rig.service, *store.pull(now=clock(), cap=1))
    )
    await asyncio.wait_for(provider.started.wait(), timeout=5)
    provider.release()
    assert await rerun == "prepared"

    assert rig.draft(connection).status == "review_ready"
    assert (provider.calls, rig.budget.charged, rig.saves) == (2, 2, 1)
    assert jobs.sweep().rerun == []


def _page() -> bytes:
    page = io.BytesIO()
    Image.new("RGB", (40, 40), fake.hex_color()).save(page, format="JPEG")
    return page.getvalue()


@pytest.fixture
def transport(monkeypatch):
    """The real provider call over a mocked HTTP transport: the first request
    hangs past the deadline, the second answers."""
    monkeypatch.setenv("ARGUS_VISION_MODEL", "test/vision")
    monkeypatch.setenv("OPENROUTER_API_KEY", "offline-test-key")
    profile = replace(
        openrouter.openrouter_profile_for_task("document_extraction"),
        timeout_seconds=0.05,
    )
    monkeypatch.setattr(openrouter, "openrouter_profile_for_task", lambda task: profile)
    sent: list[httpx.Request] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        if len(sent) == 1:
            await asyncio.sleep(1)
        content = json.dumps(observation("250.50"))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"finish_reason": "stop", "message": {"content": content}}
                ]
            },
        )

    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        openrouter.httpx,
        "AsyncClient",
        lambda **kwargs: client_type(transport=httpx.MockTransport(respond), **kwargs),
    )
    return sent


@pytest.mark.asyncio
async def test_the_real_call_deadline_is_a_timeout_and_is_read_once_more(transport):
    admitted = 0

    async def before_request() -> None:
        nonlocal admitted
        admitted += 1

    extractor = extraction.DocumentExtractor(DocumentExtractionSettings(enabled=True))
    batch = await extractor.extract(
        content=b"%PDF-" + fake.uuid4().encode(),
        filename=fake.file_name(extension="pdf"),
        media_type="application/pdf",
        connection_id=str(uuid4()),
        observed_at=datetime.now(timezone.utc),
        prepared=PreparedDocument(1, (_page(),)),
        before_request=before_request,
    )
    assert (len(transport), admitted) == (2, 2)
    receipts = batch.metadata["route_receipts"]
    assert [(r["outcome"], r["failure_mode"]) for r in receipts] == [
        ("failed", "TimeoutError"),
        ("succeeded", None),
    ]


@pytest.mark.parametrize(
    "error, expected",
    [
        (asyncio.TimeoutError(), True),
        (httpx.ReadTimeout("read"), True),
        (httpx.ConnectTimeout("connect"), True),
        (httpx.ConnectError("refused"), False),
        (httpx.RemoteProtocolError("closed"), False),
        (ValueError("Incomplete document response"), False),
    ],
)
def test_only_the_transport_giving_up_waiting_is_a_timeout(error, expected):
    assert openrouter_transport.timed_out(error) is expected
