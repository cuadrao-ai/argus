"""A read that fails for now is taken again through the queue, bounded, and the
person keeps seeing it being read. A failure that will not pass ends the read
at once. When the provider keeps failing, the breaker stops every send, then
one read probes. Nothing here reaches a provider: the call is scripted."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from threading import Barrier
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
from argus.domain.business.read_budget import InMemoryReadBudget, ReadBudgetSettings
from argus.domain.ingestion.connections import InMemoryConnectionRepository
from argus.domain.ingestion.documents import breaker as breaking
from argus.domain.ingestion.documents import extractor as extraction
from argus.domain.ingestion.documents import preparation
from argus.domain.ingestion.documents.breaker import (
    COOLDOWN,
    WINDOW,
    BreakerState,
    InMemoryReadBreaker,
)
from argus.domain.ingestion.documents.config import (
    BREAKER_COOLDOWN_SECONDS,
    BREAKER_FAILURES,
    BREAKER_WINDOW_SECONDS,
    MAX_PROVIDER_CALLS,
    PROVIDER_CALLS_PER_READ,
    READ_DEADLINE_SECONDS,
    RETRY_BASE_SECONDS,
    RETRY_FACTOR,
    RETRY_MAX_WAIT_SECONDS,
    DocumentExtractionSettings,
    DocumentJobSettings,
)
from argus.domain.ingestion.documents.failures import (
    CONFIG_ALERT,
    READ_DEADLINE_PASSED,
    READS_PAUSED,
    ReadFailure,
    classify,
    retry_wait,
)
from argus.domain.ingestion.documents.jobs import PreparationJobs, run_attempt
from argus.domain.ingestion.documents.models import (
    DocumentDraft,
    DocumentExtractionError,
    ExtractionResult,
    PreparationJob,
)
from argus.domain.ingestion.documents.service import (
    DocumentServiceError,
    DocumentsService,
)
from argus.domain.ingestion.documents.store import InMemoryDocumentStore
from argus.domain.ingestion.documents.worker import DocumentWorker
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.owner_scope import BusinessSpace
from faker import Faker
from loguru import logger

from tests.business_reading_support import reading_setting, turn_reading
from tests.document_extractor_support import admit
from tests.ingestion.test_document_jobs_api import observation
from tests.ingestion.test_read_budget_local_refusals import poppler

fake = Faker("es_MX")
OK = "ok"
UNREADABLE = "unreadable"
FAILED = "extraction_provider_failed"


def status(code: int, **headers: str) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://provider.test/read")
    return httpx.HTTPStatusError(
        f"HTTP {code}",
        request=request,
        response=httpx.Response(code, headers=headers, request=request),
    )


# A failure that may pass, and the provider calls one take makes before it
# gives up on it: a timeout is read once more inside the take.
TRANSIENT = [
    pytest.param(lambda: status(503), 1, id="503"),
    pytest.param(lambda: status(500), 1, id="500"),
    pytest.param(lambda: status(429), 1, id="429"),
    pytest.param(lambda: httpx.ConnectError("refused"), 1, id="refused connection"),
    pytest.param(lambda: httpx.RemoteProtocolError("cut"), 1, id="interrupted answer"),
    pytest.param(
        lambda: httpx.ReadTimeout("slow"), PROVIDER_CALLS_PER_READ, id="timeout"
    ),
]


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 16, 15, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def pass_(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class Provider:
    """One scripted answer per provider call: ``OK``, ``UNREADABLE`` or an
    error to raise. The last answer repeats. Every call is admitted first, as
    the real call is. ``held`` keeps each admitted call out until released."""

    def __init__(self, *answers: object, held: bool = False) -> None:
        self.answers, self.calls = list(answers), 0
        self.out = asyncio.Event()
        self.release = None if not held else asyncio.Event()

    async def __call__(self, **kwargs: object) -> ExtractionResult:
        await admit(kwargs.get("before_request"))
        self.calls += 1
        if self.release is not None:
            self.out.set()
            await self.release.wait()
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, BaseException):
            raise answer
        read = observation("250.50")
        if answer is UNREADABLE:
            read = {**read, "readable": False, "observations": []}
        return ExtractionResult.model_validate(read)


class CountingBudget(InMemoryReadBudget):
    def __init__(self) -> None:
        super().__init__(ReadBudgetSettings(per_day=300))
        self.charged = 0

    def charge(self, business_id: str, now: datetime):  # noqa: ANN201
        refused = super().charge(business_id, now)
        self.charged += refused is None
        return refused


@dataclass
class Rig:
    service: DocumentsService
    jobs: PreparationJobs
    clock: Clock
    budget: CountingBudget
    breaker: InMemoryReadBreaker
    scope: BusinessSpace
    owner: str
    monkeypatch: pytest.MonkeyPatch
    saves: int = 0
    logs: list[str] = field(default_factory=list)

    @property
    def store(self) -> InMemoryDocumentStore:
        return self.service.store

    def answers(self, *answers: object, held: bool = False) -> Provider:
        provider = Provider(*answers, held=held)
        self.monkeypatch.setattr(extraction, "invoke_openrouter_json_schema", provider)
        return provider

    async def queued(self) -> str:
        """A receipt uploaded with consent, its read waiting for a puller."""
        outcome = await self.service.upload(
            user_id=self.owner,
            content=b"%PDF-" + fake.uuid4().encode(),
            filename=fake.file_name(extension="pdf"),
            media_type="application/pdf",
            consent=True,
            scope=self.scope,
        )
        self.jobs.start(user_id=self.owner, connection_id=outcome.connection_id)
        return outcome.connection_id

    def pull(self) -> tuple[str, str] | None:
        return self.store.pull(now=self.clock(), cap=3)

    async def take(self) -> str | None:
        """What a worker does next: pull the oldest waiting read and run it."""
        pulled = self.pull()
        return None if pulled is None else await run_attempt(self.service, *pulled)

    def draft(self, connection: str) -> DocumentDraft:
        return self.service.get(
            user_id=self.owner, connection_id=connection, scope=self.scope
        )

    def job(self, connection: str) -> PreparationJob:
        return self.store.job(user_id=self.owner, connection_id=connection)

    def leyendo(self, connection: str) -> bool:
        """The person sees the receipt being read, with no reason on it."""
        draft = self.draft(connection)
        return draft.error_code is None and self.service.read_pending(
            self.owner, connection, draft
        )

    def wait_out(self, connection: str) -> float:
        """Pass the wait of the read's next take; the seconds it was."""
        wait = (self.job(connection).not_before - self.clock()).total_seconds()
        self.clock.pass_(wait)
        return wait


@pytest.fixture
def rig(monkeypatch):
    monkeypatch.setenv("ARGUS_VISION_MODEL", "test/vision")
    monkeypatch.setenv("CUADRAO_OPENROUTER_API_KEY_DEV", "offline-test-key")
    monkeypatch.setattr(preparation, "_run", poppler("Pages: 1\nEncrypted: no\n"))
    clock = Clock()
    repo = InMemoryConnectionRepository()
    hub = IngestionHub(repo, box=None, sink=Mock(), clock=clock)
    budget, breaker = CountingBudget(), InMemoryReadBreaker()
    store = InMemoryDocumentStore(repo)
    service = DocumentsService(
        hub,
        store,
        extraction.DocumentExtractor(DocumentExtractionSettings(enabled=True)),
        business_actions=Mock(),
        read_budget=budget,
        read_breaker=breaker,
    )
    service.business_receipt_consent = reading_setting()
    scope, owner = BusinessSpace(str(uuid4())), str(uuid4())
    turn_reading(service.business_receipt_consent, scope.space_id, owner)
    rig = Rig(
        service,
        PreparationJobs(service),
        clock,
        budget,
        breaker,
        scope,
        owner,
        monkeypatch,
    )
    save = store.save

    def counted_save(**kwargs):  # noqa: ANN003, ANN202
        rig.saves += 1
        return save(**kwargs)

    monkeypatch.setattr(store, "save", counted_save)
    sink = logger.add(lambda message: rig.logs.append(str(message)), level="WARNING")
    yield rig
    logger.remove(sink)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure, calls", TRANSIENT)
async def test_a_failure_for_now_then_an_answer_reads_once_the_wait_passes(
    rig, failure, calls
):
    provider = rig.answers(*(failure() for _ in range(calls)), OK)
    connection = await rig.queued()

    assert await rig.take() == FAILED
    assert rig.leyendo(connection), "the person never sees the failure"
    assert rig.draft(connection).status == "queued"
    waiting = rig.job(connection)
    assert waiting.not_before > rig.clock()
    assert rig.pull() is None, "no worker holds a slot while the read waits"
    assert rig.jobs.sweep().redispatched == []

    rig.clock.pass_((waiting.not_before - rig.clock()).total_seconds() - 1)
    assert rig.pull() is None
    rig.clock.pass_(1)
    assert await rig.take() == "prepared"

    assert rig.draft(connection).status == "review_ready"
    # Every provider call is charged to the Business, a retry included.
    assert provider.calls == rig.budget.charged == rig.job(connection).provider_calls
    assert provider.calls == calls + 1
    assert rig.saves == 1
    assert rig.service.business_actions.prepare_attachment.call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "header",
    [
        pytest.param(lambda now: "120", id="seconds"),
        pytest.param(
            lambda now: format_datetime(now + timedelta(seconds=120), usegmt=True),
            id="date",
        ),
    ],
)
async def test_a_429_waits_at_least_its_retry_after(rig, header, monkeypatch):
    from argus.domain.ingestion.documents import failures

    class Now(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001, ANN206
            return rig.clock()

    monkeypatch.setattr(failures, "datetime", Now)
    provider = rig.answers(status(429, **{"Retry-After": header(rig.clock())}), OK)
    connection = await rig.queued()

    assert await rig.take() == FAILED
    assert rig.leyendo(connection)
    assert rig.job(connection).not_before >= rig.clock() + timedelta(seconds=120)
    rig.clock.pass_(119)
    assert rig.pull() is None
    rig.wait_out(connection)
    assert await rig.take() == "prepared"
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_a_retry_after_past_the_total_wait_ends_the_read_instead(rig):
    provider = rig.answers(
        status(429, **{"Retry-After": str(int(RETRY_MAX_WAIT_SECONDS) + 1)}), OK
    )
    connection = await rig.queued()
    assert await rig.take() == FAILED
    draft = rig.draft(connection)
    assert (draft.status, draft.error_code) == ("needs_attention", FAILED)
    assert rig.pull() is None and provider.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure, calls", TRANSIENT)
async def test_failures_that_never_pass_end_in_necesitan_atencion_and_stop(
    rig, failure, calls
):
    provider = rig.answers(failure())
    connection = await rig.queued()
    waited = 0.0
    for _ in range(MAX_PROVIDER_CALLS):
        assert await rig.take() == FAILED
        if rig.draft(connection).status != "queued":
            break
        assert rig.leyendo(connection)
        # Past the breaker's window, so this test is the retries alone.
        waited += rig.wait_out(connection)
        rig.clock.pass_(BREAKER_WINDOW_SECONDS)

    draft = rig.draft(connection)
    assert (draft.status, draft.error_code) == ("needs_attention", FAILED)
    assert draft.source_available, "the person can still ask to read it again"
    assert provider.calls == rig.budget.charged == MAX_PROVIDER_CALLS
    assert waited <= RETRY_MAX_WAIT_SECONDS
    assert rig.saves == 0

    rig.clock.pass_(24 * 3600)
    assert rig.pull() is None
    report = rig.jobs.sweep()
    assert (report.redispatched, report.rerun) == ([], [])
    assert provider.calls == MAX_PROVIDER_CALLS
    final = [line for line in rig.logs if "document_read_failed" in line]
    assert len(final) == 1 and connection in final[0] and FAILED in final[0]


def test_the_waits_grow_stay_jittered_and_never_pass_the_total():
    assert MAX_PROVIDER_CALLS == 4 and PROVIDER_CALLS_PER_READ <= MAX_PROVIDER_CALLS
    longest = [retry_wait(calls, 0, rand=lambda: 1.0) for calls in (1, 2, 3)]
    shortest = [retry_wait(calls, 0, rand=lambda: 0.0) for calls in (1, 2, 3)]
    assert longest == [
        RETRY_BASE_SECONDS * RETRY_FACTOR**step for step in range(3)
    ]
    assert shortest == [wait / 2 for wait in longest]
    assert sum(longest) <= RETRY_MAX_WAIT_SECONDS == 600
    assert len({retry_wait(1, 0) for _ in range(20)}) > 1, "the wait is jittered"
    assert retry_wait(MAX_PROVIDER_CALLS, 0) is None
    assert retry_wait(1, RETRY_MAX_WAIT_SECONDS) is None
    assert retry_wait(1, 0, asked=RETRY_MAX_WAIT_SECONDS) == RETRY_MAX_WAIT_SECONDS


@pytest.mark.asyncio
async def test_a_file_that_cannot_be_opened_fails_with_no_retry(rig, monkeypatch):
    monkeypatch.setattr(preparation, "_run", poppler("Pages: 1\nEncrypted: yes\n"))
    provider = rig.answers(OK)
    connection = await rig.queued()
    code = await rig.take()
    draft = rig.draft(connection)
    assert (draft.status, draft.error_code) == ("needs_attention", code)
    assert classify(DocumentExtractionError(code)).kind == "permanent"
    assert (provider.calls, rig.budget.charged) == (0, 0)
    rig.clock.pass_(24 * 3600)
    assert rig.pull() is None and rig.jobs.sweep().redispatched == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "answer, reason",
    [
        pytest.param(UNREADABLE, "unreadable_document", id="unreadable"),
        pytest.param(status(400), FAILED, id="refused request"),
        pytest.param(status(422), FAILED, id="refused content"),
        pytest.param(ValueError("Incomplete document response"), FAILED, id="cut"),
    ],
)
async def test_an_answer_that_will_not_change_is_never_read_again(rig, answer, reason):
    provider = rig.answers(answer, OK)
    connection = await rig.queued()
    await rig.take()
    draft = rig.draft(connection)
    assert (draft.status, draft.error_code) == ("needs_attention", reason)
    rig.clock.pass_(24 * 3600)
    assert rig.pull() is None and rig.jobs.sweep().redispatched == []
    assert provider.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [401, 403])
async def test_a_refused_key_fails_fast_and_alerts_us(rig, code):
    provider = rig.answers(status(code), OK)
    connection = await rig.queued()
    assert await rig.take() == FAILED
    draft = rig.draft(connection)
    assert (draft.status, draft.error_code) == ("needs_attention", FAILED)
    rig.clock.pass_(24 * 3600)
    assert rig.pull() is None and provider.calls == 1
    alerts = [line for line in rig.logs if CONFIG_ALERT in line]
    assert len(alerts) == 1
    assert connection in alerts[0] and f"http_status={code}" in alerts[0]
    assert "ERROR" in alerts[0]
    assert rig.breaker.state == BreakerState(), "our own fault is no provider outage"


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["ARGUS_VISION_MODEL", "CUADRAO_OPENROUTER_API_KEY_DEV"])
async def test_a_missing_model_or_key_fails_fast_and_alerts_us(
    rig, missing, monkeypatch
):
    provider = rig.answers(OK)
    connection = await rig.queued()
    monkeypatch.delenv(missing)
    monkeypatch.delenv(missing.replace("ARGUS_", "CUADRAO_"), raising=False)
    code = await rig.take()
    assert code in {"missing_vision_model", "missing_api_key"}
    assert rig.draft(connection).status == "needs_attention"
    assert rig.pull() is None and provider.calls == 0
    alerts = [line for line in rig.logs if CONFIG_ALERT in line]
    assert len(alerts) == 1 and connection in alerts[0] and code in alerts[0]


@pytest.mark.parametrize(
    "error, kind",
    [
        (asyncio.TimeoutError(), "transient"),
        (httpx.ReadTimeout("slow"), "transient"),
        (httpx.ConnectError("refused"), "transient"),
        (httpx.RemoteProtocolError("cut"), "transient"),
        (status(408), "transient"),
        (status(429), "transient"),
        (status(500), "transient"),
        (status(502), "transient"),
        (status(503), "transient"),
        (status(401), "config"),
        (status(403), "config"),
        (DocumentExtractionError("missing_vision_model"), "config"),
        (DocumentExtractionError("missing_api_key"), "config"),
        (status(400), "permanent"),
        (status(404), "permanent"),
        (ValueError("Incomplete document response"), "permanent"),
        (DocumentExtractionError("unsupported_media_type"), "permanent"),
        (DocumentServiceError("document_source_unavailable"), "permanent"),
        (DocumentServiceError("document_source_changed"), "permanent"),
    ],
)
def test_one_function_names_the_kind_of_every_failure(error, kind):
    assert classify(error).kind == kind


def test_a_retry_after_is_honored_only_when_it_is_a_wait():
    assert classify(status(429, **{"Retry-After": "30"})) == ReadFailure("transient", 30)
    assert classify(status(503, **{"Retry-After": "7"})) == ReadFailure("transient", 7)
    assert classify(status(429, **{"Retry-After": "soon"})) == ReadFailure("transient")
    assert classify(status(429, **{"Retry-After": "-5"})) == ReadFailure("transient", 0)
    assert classify(status(429)) == ReadFailure("transient")


async def open_the_breaker(rig: Rig) -> list[str]:
    """Enough receipts fail once inside the window to open the breaker."""
    connections = [await rig.queued() for _ in range(BREAKER_FAILURES)]
    for _ in connections:
        assert rig.breaker.state.opened_at is None
        assert await rig.take() == FAILED
        rig.clock.pass_(1)
    assert rig.breaker.state.opened_at is not None
    return connections


@pytest.mark.asyncio
async def test_failures_across_reads_open_the_breaker_and_a_probe_closes_it(rig):
    provider = rig.answers(status(503))
    # One read is already past the pull when the breaker opens.
    held = await rig.queued()
    held_take = rig.pull()
    waiting = await open_the_breaker(rig)
    calls, charged = provider.calls, rig.budget.charged
    assert calls == BREAKER_FAILURES
    worker = DocumentWorker(rig.service, DocumentJobSettings())

    # No worker runs a read while the breaker is open, however long it waited:
    # each one it pulls goes back to the queue until the cooldown ends.
    opened = rig.breaker.state.opened_at
    rig.clock.now = opened + COOLDOWN - timedelta(seconds=1)
    assert all(rig.job(each).not_before <= rig.clock() for each in waiting)
    assert worker._take(rig.clock()) is None
    for each in waiting:
        assert rig.job(each).not_before == opened + COOLDOWN
        assert rig.job(each).dispatched_at is None and rig.leyendo(each)
        assert (rig.job(each).provider_calls, rig.draft(each).status) == (1, "queued")
    assert rig.pull() is None

    # The read that was already pulled is held back: never sent, never charged.
    assert await run_attempt(rig.service, *held_take) == READS_PAUSED
    assert rig.leyendo(held)
    assert rig.job(held).provider_calls == 0 and rig.job(held).retry_waited == 0
    assert (provider.calls, rig.budget.charged) == (calls, charged)
    assert rig.job(held).not_before == opened + COOLDOWN

    # After the cooldown two workers each pull a read. One read probes; the
    # other is held back uncharged, and no worker pulls while the probe is out.
    rig.clock.pass_(1)
    answering = rig.answers(OK, held=True)
    first, second = worker._take(rig.clock()), worker._take(rig.clock())
    probe = asyncio.create_task(run_attempt(rig.service, *first))
    await asyncio.wait_for(answering.out.wait(), timeout=5)
    assert await run_attempt(rig.service, *second) == READS_PAUSED
    assert rig.job(second[0]).not_before > rig.clock()
    assert worker._take(rig.clock()) is None
    assert (answering.calls, rig.budget.charged) == (1, charged + 1)
    answering.release.set()
    assert await probe == "prepared"
    assert rig.breaker.state == BreakerState()

    # Closed: every read left is read once its own wait passes.
    rig.clock.pass_(BREAKER_COOLDOWN_SECONDS)
    while (taken := worker._take(rig.clock())) is not None:
        assert await run_attempt(rig.service, *taken) == "prepared"
    assert {rig.draft(each).status for each in (held, *waiting)} == {"review_ready"}


@pytest.mark.asyncio
async def test_a_failed_probe_starts_the_cooldown_again(rig):
    provider = rig.answers(status(503))
    await open_the_breaker(rig)
    rig.clock.pass_(BREAKER_COOLDOWN_SECONDS)
    calls = provider.calls
    worker = DocumentWorker(rig.service, DocumentJobSettings())

    assert await run_attempt(rig.service, *worker._take(rig.clock())) == FAILED
    assert provider.calls == calls + 1, "one probe was sent"
    assert rig.breaker.state == BreakerState(opened_at=rig.clock())
    rig.clock.pass_(BREAKER_COOLDOWN_SECONDS - 1)
    assert worker._take(rig.clock()) is None
    rig.clock.pass_(1)
    assert worker._take(rig.clock()) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("late", [OK, status(503)], ids=["answers", "fails"])
async def test_a_call_sent_before_the_breaker_opened_never_moves_it(rig, late):
    """One slow call is still out while other reads open the breaker. Its late
    answer does not close the breaker, and its late failure does not start the
    cooldown again, with or without a probe out."""
    slow = rig.answers(late, held=True)
    early = await rig.queued()
    reading = asyncio.create_task(run_attempt(rig.service, *rig.pull()))
    await asyncio.wait_for(slow.out.wait(), timeout=5)
    rig.answers(status(503))
    await open_the_breaker(rig)
    opened = rig.breaker.state
    worker = DocumentWorker(rig.service, DocumentJobSettings())

    rig.clock.pass_(BREAKER_COOLDOWN_SECONDS / 2)
    slow.release.set()
    assert await reading == ("prepared" if late is OK else FAILED)
    assert rig.breaker.state == opened, "no probe was admitted yet"
    assert worker._take(rig.clock()) is None
    if late is OK:
        assert rig.draft(early).status == "review_ready"

    # The same late call while the probe is out: only the probe's end counts.
    rig.clock.now = opened.opened_at + COOLDOWN
    probing = rig.breaker.admit(rig.clock())
    assert probing.until is None and probing.probe is not None
    probed = rig.breaker.state
    rig.breaker.succeeded(rig.clock())
    rig.breaker.failed(rig.clock())
    assert rig.breaker.state == probed
    rig.breaker.succeeded(rig.clock(), probing.probe)
    assert rig.breaker.state == BreakerState()


def test_only_the_current_probe_moves_an_open_breaker():
    start = datetime(2026, 11, 16, tzinfo=timezone.utc)
    opened = BreakerState(opened_at=start)
    after = start + COOLDOWN
    probing, first = breaking.admitted(opened, after, "first")
    assert (first.until, first.probe) == (None, "first")
    assert (probing.probe_at, probing.probe_id) == (after, "first")
    # A call with no probe id, sent before the breaker opened.
    assert breaking.succeeded(opened) == opened
    assert breaking.succeeded(probing) == probing
    assert breaking.failed(probing, after) == probing
    # A probe that was given up reports late, after the next probe went out.
    later = after + timedelta(hours=1)
    again, second = breaking.admitted(probing, later, "second")
    assert (second.probe, again.probe_id) == ("second", "second")
    assert breaking.succeeded(again, "first") == again
    assert breaking.failed(again, later, "first") == again
    # The current probe: its answer closes, its failure starts the cooldown.
    assert breaking.succeeded(again, "second") == BreakerState()
    assert breaking.failed(again, later, "second") == BreakerState(opened_at=later)
    # A closed breaker counts every failed call, whatever it carries.
    assert breaking.failed(BreakerState(), later, "first").failures == (later,)


@pytest.mark.asyncio
async def test_a_timeout_read_once_more_counts_each_failed_call(rig):
    """A take whose first call times out asks to be sent again; that tells the
    breaker about the first call, so slow failures open it too."""
    rig.answers(httpx.ReadTimeout("slow"))
    connection = await rig.queued()
    assert await rig.take() == FAILED
    assert rig.job(connection).provider_calls == PROVIDER_CALLS_PER_READ
    assert len(rig.breaker.state.failures) == PROVIDER_CALLS_PER_READ


def test_the_breaker_counts_only_failures_inside_its_window():
    assert (BREAKER_FAILURES, BREAKER_WINDOW_SECONDS, BREAKER_COOLDOWN_SECONDS) == (
        5,
        120,
        300,
    )
    start = datetime(2026, 11, 16, tzinfo=timezone.utc)
    state = BreakerState()
    for step in range(BREAKER_FAILURES * 2):
        # One failure every half window: never five inside one window.
        state = breaking.failed(state, start + step * WINDOW / 2)
        assert state.opened_at is None
    for step in range(BREAKER_FAILURES):
        state = breaking.failed(state, start + timedelta(days=1, seconds=step))
    assert state.opened_at == start + timedelta(days=1, seconds=BREAKER_FAILURES - 1)
    assert breaking.paused_until(state, state.opened_at) == state.opened_at + COOLDOWN
    # A call sent before it opened fails late: the cooldown does not restart.
    assert breaking.failed(state, state.opened_at + COOLDOWN / 2) == state
    # A probe whose worker died is given up, and the next read probes.
    probing, sent = breaking.admitted(state, state.opened_at + COOLDOWN, "first")
    assert sent.until is None and probing.probe_at == state.opened_at + COOLDOWN
    assert breaking.admitted(probing, probing.probe_at, "held")[0] == probing
    assert breaking.admitted(probing, probing.probe_at, "held")[1].until is not None
    later = probing.probe_at + timedelta(hours=1)
    assert breaking.admitted(probing, later, "second") == (
        BreakerState(opened_at=state.opened_at, probe_at=later, probe_id="second"),
        breaking.Admission(probe="second"),
    )


@pytest.mark.asyncio
async def test_a_breaker_that_cannot_be_reached_never_stops_a_read(rig, monkeypatch):
    def down(now: datetime, probe: str | None = None):  # noqa: ANN202
        raise ConnectionError("database away")

    for ask in ("admit", "failed", "succeeded"):
        monkeypatch.setattr(rig.breaker, ask, down)
    rig.answers(status(503), OK)
    connection = await rig.queued()
    assert await rig.take() == FAILED
    rig.wait_out(connection)
    assert await rig.take() == "prepared"


@pytest.mark.asyncio
async def test_a_worker_that_cannot_read_the_breaker_still_reads(rig, monkeypatch):
    def down(now: datetime):  # noqa: ANN202
        raise ConnectionError("database away")

    monkeypatch.setattr(rig.breaker, "paused_until", down)
    rig.answers(OK)
    connection = await rig.queued()
    worker = DocumentWorker(rig.service, DocumentJobSettings())
    assert await run_attempt(rig.service, *worker._take(rig.clock())) == "prepared"
    assert rig.draft(connection).status == "review_ready"
    assert any("document_read_breaker_unavailable" in line for line in rig.logs)


@pytest.mark.asyncio
async def test_two_workers_never_pull_the_same_retry(rig):
    rig.answers(status(503), OK)
    connection = await rig.queued()
    assert await rig.take() == FAILED
    rig.wait_out(connection)
    barrier = Barrier(2)

    def pull(_: int) -> tuple[str, str] | None:
        barrier.wait()
        return rig.pull()

    with ThreadPoolExecutor(max_workers=2) as workers:
        pulled = list(workers.map(pull, range(2)))
    assert sorted(pulled, key=lambda take: take is not None) == [
        None,
        (connection, rig.job(connection).attempt_id),
    ]


@pytest.mark.asyncio
async def test_a_take_superseded_while_it_waited_writes_nothing(rig):
    """The owner asks again while the retry waits: the new read replaces it,
    with a fresh count, and the old take can no longer claim."""
    rig.answers(status(503), OK)
    connection = await rig.queued()
    assert await rig.take() == FAILED
    stale = rig.job(connection)
    rig.store.advance(
        user_id=rig.owner,
        connection_id=connection,
        now=rig.clock(),
        expected_attempt_id=stale.attempt_id,
        job=PreparationJob(
            attempt=1, attempt_id=str(uuid4()), draft_version=stale.draft_version
        ),
    )
    assert await run_attempt(rig.service, connection, stale.attempt_id) == (
        "document_attempt_superseded"
    )
    assert await rig.take() == "prepared"
    assert rig.saves == 1 and rig.job(connection).provider_calls == 1


@pytest.mark.asyncio
async def test_a_read_cut_by_a_deploy_keeps_its_count_of_calls(rig):
    """A worker that dies during a retry's call is rerun by the sweep; the
    rerun still counts against the same four calls."""
    provider = rig.answers(status(503), status(503), status(503), status(503), OK)
    connection = await rig.queued()
    for _ in range(2):
        assert await rig.take() == FAILED
        rig.wait_out(connection)
        rig.clock.pass_(BREAKER_WINDOW_SECONDS)
    assert rig.job(connection).provider_calls == 2

    # The third take dies after its call was admitted and before any answer.
    connection_id, attempt = rig.pull()
    killed = Provider(asyncio.CancelledError())
    rig.monkeypatch.setattr(extraction, "invoke_openrouter_json_schema", killed)
    with pytest.raises(asyncio.CancelledError):
        await run_attempt(rig.service, connection_id, attempt)
    assert rig.job(connection).provider_calls == 3
    rig.monkeypatch.setattr(extraction, "invoke_openrouter_json_schema", provider)

    assert rig.jobs.sweep().rerun == [connection]
    assert rig.job(connection).provider_calls == 3
    assert await rig.take() == FAILED
    draft = rig.draft(connection)
    assert (draft.status, draft.error_code) == ("needs_attention", FAILED)
    assert provider.calls + killed.calls == MAX_PROVIDER_CALLS


@pytest.mark.asyncio
async def test_a_read_out_of_calls_is_never_sent_again(rig):
    provider = rig.answers(OK)
    connection = await rig.queued()
    spent = rig.job(connection).model_copy(update={"provider_calls": MAX_PROVIDER_CALLS})
    rig.store.advance(
        user_id=rig.owner,
        connection_id=connection,
        now=rig.clock(),
        expected_attempt_id=spent.attempt_id,
        job=spent,
    )
    assert await rig.take() == FAILED
    assert rig.draft(connection).status == "needs_attention"
    assert (provider.calls, rig.budget.charged) == (0, 0)


@pytest.mark.asyncio
async def test_leer_de_nuevo_after_the_retries_starts_a_new_count(rig):
    provider = rig.answers(status(503))
    connection = await rig.queued()
    while rig.draft(connection).status != "needs_attention":
        await rig.take()
        if rig.draft(connection).status == "queued":
            rig.wait_out(connection)
            rig.clock.pass_(BREAKER_WINDOW_SECONDS)
    rig.answers(OK)
    rig.service.queue(
        user_id=rig.owner, connection_id=connection, consent=True, scope=rig.scope
    )
    rig.jobs.start(user_id=rig.owner, connection_id=connection)
    assert rig.job(connection).provider_calls == 0
    assert await rig.take() == "prepared"
    assert provider.calls == MAX_PROVIDER_CALLS and rig.saves == 1


def expired(rig: Rig, connection: str) -> bool:
    """The read ended on its deadline: Necesitan atención with its own reason,
    never pulled again, and the final error logged once with the document."""
    draft = rig.draft(connection)
    logged = [
        line
        for line in rig.logs
        if "document_read_failed" in line and connection in line
    ]
    return (
        (draft.status, draft.error_code) == ("needs_attention", READ_DEADLINE_PASSED)
        and not rig.leyendo(connection)
        and len(logged) == 1
        and READ_DEADLINE_PASSED in logged[0]
    )


@pytest.mark.asyncio
async def test_the_read_deadline_counts_from_the_upload_not_the_first_try(rig):
    assert READ_DEADLINE_SECONDS == 6 * 60 * 60
    provider = rig.answers(status(503))
    connection = await rig.queued()
    uploaded = rig.draft(connection).created_at
    assert rig.job(connection).asked_at == uploaded == rig.clock()

    # No worker takes it until one second before the deadline. It fails for
    # now and waits for its next take: the first try does not move the deadline.
    rig.clock.pass_(READ_DEADLINE_SECONDS - 1)
    assert rig.jobs.sweep().expired == [] and rig.leyendo(connection)
    assert await rig.take() == FAILED
    assert rig.job(connection).asked_at == uploaded
    assert rig.job(connection).not_before > uploaded + timedelta(
        seconds=READ_DEADLINE_SECONDS
    )
    assert rig.jobs.sweep().expired == [] and rig.leyendo(connection)

    rig.clock.now = uploaded + timedelta(seconds=READ_DEADLINE_SECONDS)
    assert rig.jobs.sweep().expired == [connection]
    assert expired(rig, connection)
    assert FAILED != READ_DEADLINE_PASSED, "not the reason of a receipt that failed"
    rig.clock.pass_(86400)
    assert rig.pull() is None and rig.jobs.sweep().expired == []
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_a_read_the_open_breaker_holds_expires_while_it_stays_open(
    rig, monkeypatch
):
    rig.answers(status(503))
    waiting = await open_the_breaker(rig)
    never_sent = await rig.queued()
    worker = DocumentWorker(rig.service, DocumentJobSettings())
    opened = rig.breaker.state

    # Every pulled read is held back, and the outage outlasts the deadline.
    assert worker._take(rig.clock()) is None
    assert rig.job(never_sent).provider_calls == 0
    for ask in ("paused_until", "admit", "failed", "succeeded"):
        monkeypatch.setattr(rig.breaker, ask, Mock(side_effect=AssertionError(ask)))
    rig.clock.now = rig.draft(never_sent).created_at + timedelta(
        seconds=READ_DEADLINE_SECONDS - 1
    )
    assert sorted(rig.jobs.sweep().expired) == sorted(waiting)
    rig.clock.pass_(1)
    assert rig.jobs.sweep().expired == [never_sent]

    assert rig.breaker.state == opened, "the sweep never asks or moves the breaker"
    assert all(expired(rig, each) for each in (never_sent, *waiting))
    assert rig.pull() is None


@pytest.mark.asyncio
async def test_a_read_a_worker_has_taken_is_left_to_end(rig):
    """The sweep moves only a read that waits in the queue. One a worker took
    just before the deadline ends by its own answer."""
    answering = rig.answers(OK, held=True)
    connection = await rig.queued()
    rig.clock.pass_(READ_DEADLINE_SECONDS - 1)
    pulled = rig.pull()
    rig.clock.pass_(1)
    assert rig.jobs.sweep().expired == []
    reading = asyncio.create_task(run_attempt(rig.service, *pulled))
    await asyncio.wait_for(answering.out.wait(), timeout=5)
    assert rig.jobs.sweep().expired == []
    answering.release.set()
    assert await reading == "prepared"
    assert rig.draft(connection).status == "review_ready"


@pytest.mark.asyncio
async def test_leer_de_nuevo_after_the_deadline_counts_from_the_ask(rig):
    rig.answers(OK)
    connection = await rig.queued()
    rig.clock.pass_(READ_DEADLINE_SECONDS)
    assert rig.jobs.sweep().expired == [connection]

    rig.clock.pass_(86400)
    rig.service.queue(
        user_id=rig.owner, connection_id=connection, consent=True, scope=rig.scope
    )
    rig.jobs.start(user_id=rig.owner, connection_id=connection)
    assert rig.job(connection).asked_at == rig.clock()
    rig.clock.pass_(READ_DEADLINE_SECONDS - 1)
    assert rig.jobs.sweep().expired == [] and rig.leyendo(connection)
    assert await rig.take() == "prepared"


@pytest.mark.asyncio
async def test_a_read_cut_by_a_deploy_keeps_its_deadline(rig):
    """The sweep's rerun of a read whose worker died is the same read: it was
    asked for at the upload."""
    rig.answers(asyncio.CancelledError())
    connection = await rig.queued()
    uploaded = rig.draft(connection).created_at
    rig.clock.pass_(60)
    with pytest.raises(asyncio.CancelledError):
        await rig.take()
    assert rig.jobs.sweep().rerun == [connection]
    assert rig.job(connection).asked_at == uploaded


@pytest.mark.asyncio
async def test_a_take_written_before_the_deadline_existed_is_not_ended_early(rig):
    """A waiting take with no ``asked_at`` counts from when its draft was last
    queued, so the deploy of the deadline ends no read at once."""
    connection = await rig.queued()
    rig.clock.pass_(READ_DEADLINE_SECONDS * 2)
    rig.service.queue(
        user_id=rig.owner, connection_id=connection, consent=True, scope=rig.scope
    )
    queued = rig.draft(connection)
    old = rig.job(connection)
    rig.store.advance(
        user_id=rig.owner,
        connection_id=connection,
        now=rig.clock(),
        expected_attempt_id=old.attempt_id,
        job=PreparationJob(
            attempt=1, attempt_id=str(uuid4()), draft_version=queued.version
        ),
    )
    assert rig.job(connection).asked_at is None
    rig.clock.pass_(READ_DEADLINE_SECONDS - 1)
    assert rig.jobs.sweep().expired == []
    rig.clock.pass_(1)
    assert rig.jobs.sweep().expired == [connection]


@pytest.mark.asyncio
async def test_the_deadline_adds_nothing_to_an_idle_sweep(rig, monkeypatch):
    """A sweep with nothing waiting asks the database once, as before. One
    with a read inside its deadline reads that row and writes nothing."""
    real = rig.store
    store = Mock(wraps=real)
    monkeypatch.setattr(rig.service, "store", store)
    for ask in ("paused_until", "admit", "failed", "succeeded"):
        monkeypatch.setattr(rig.breaker, ask, Mock(side_effect=AssertionError(ask)))

    assert rig.jobs.sweep().expired == []
    assert [call[0] for call in store.method_calls] == ["pending"]

    store.reset_mock()
    monkeypatch.setattr(rig.service, "store", real)
    await rig.queued()
    monkeypatch.setattr(rig.service, "store", store)
    assert rig.jobs.sweep().expired == []
    assert [call[0] for call in store.method_calls] == ["pending", "draft", "job"]
