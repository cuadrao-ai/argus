"""A read the Business read budget refused, on real Postgres: the document
worker's pass starts it again once the Santo Domingo day or month has turned,
with a fresh attempt, only while the owner's reading is on, and once however
many workers run the pass."""

from __future__ import annotations

import asyncio
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta, timezone
from threading import Barrier
from types import SimpleNamespace

import pytest
from argus.api.documents import dispatch_preparation
from argus.domain.business.read_budget import (
    READ_BUDGET_REFUSALS,
    PostgresReadBudget,
    ReadBudgetSettings,
    next_month_start,
)
from argus.domain.ingestion.documents.service import DocumentsService
from argus.domain.ingestion.email_intake.budget import (
    BUSINESS_ZONE,
    business_day,
    next_business_day,
)
from argus.domain.owner_scope import BusinessSpace
from faker import Faker

from tests import test_business_actions_postgres as shared
from tests.business_reading_support import turn_reading
from tests.document_reads_support import read_receipt
from tests.document_sources_support import source_objects
from tests.test_business_email_intake_postgres import receipts  # noqa: F401
from tests.test_whatsapp_receipt_read_postgres import Extractor
from workflows.document_job import postgres_documents_service
from workflows.read_resume import ReadResume

actions = shared.actions
users = shared.users
pytestmark = [shared.pytestmark, pytest.mark.owner_acts]

fake = Faker("es_MX")
MINUTE = timedelta(minutes=1)
# The database checks a lease against its own clock, so the test's days start
# from today: midnight is the next one in Santo Domingo.
NOW = datetime.now(timezone.utc)
MIDNIGHT = next_business_day(NOW)
BEFORE_MIDNIGHT, AFTER_MIDNIGHT = MIDNIGHT - MINUTE, MIDNIGHT + MINUTE
NEXT_MONTH = datetime.combine(
    next_month_start(business_day(NOW)), time.min, tzinfo=BUSINESS_ZONE
)
NOTHING = {"due": 0, "requeued": 0}
ONE_RESUMED = {"due": 1, "requeued": 1}


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


def worker_service(desk: SimpleNamespace) -> DocumentsService:
    """A document worker's own service. Its pass sees only this test's
    receipts: other tests leave theirs waiting in the shared database."""
    service = postgres_documents_service(desk.pool, source_objects(), desk.extractor)
    service.hub.clock, service.read_budget = desk.clock, desk.budget
    every = service.store.refused_before
    service.store.refused_before = lambda **query: [  # type: ignore[method-assign]
        row for row in every(**query) if row[0] == desk.owner
    ]
    return service


@pytest.fixture
def desk(receipts, request):  # noqa: ANN001, F811
    """The owner's upload path and one worker, on one clock and one budget."""
    limits = getattr(request, "param", {"per_day": 1})
    desk = SimpleNamespace(
        pool=receipts["pool"],
        owner=receipts["owner"],
        scope=BusinessSpace(receipts["space"]),
        uploads=receipts["documents"],
        clock=Clock(),
        extractor=Extractor(),
        budget=PostgresReadBudget(receipts["pool"], ReadBudgetSettings(**limits)),
    )
    desk.uploads.hub.clock, desk.uploads.read_budget = desk.clock, desk.budget
    desk.worker = worker_service(desk)
    desk.reading = desk.worker.business_receipt_consent
    return desk


def uploaded(desk: SimpleNamespace) -> str:
    """One receipt through the owner's upload, its read left to the worker."""

    async def upload() -> str:
        outcome = await desk.uploads.upload(
            user_id=desk.owner,
            content=b"%PDF-" + fake.uuid4().encode(),
            filename=fake.file_name(extension="pdf"),
            media_type="application/pdf",
            scope=desk.scope,
        )
        await dispatch_preparation(
            desk.uploads, desk.owner, outcome.connection_id, scope=desk.scope
        )
        return outcome.connection_id

    return asyncio.run(upload())


def read(desk: SimpleNamespace, receipt: str) -> str | None:
    return asyncio.run(read_receipt(desk.worker, desk.owner, receipt))


def refused(desk: SimpleNamespace, code: str = "business_read_budget_day") -> str:
    """One read spends the budget; the next is refused and waits."""
    assert read(desk, uploaded(desk)) == "prepared"
    receipt = uploaded(desk)
    assert read(desk, receipt) == code
    return receipt


def draft(desk: SimpleNamespace, receipt: str):  # noqa: ANN201
    return desk.worker.get(user_id=desk.owner, connection_id=receipt, scope=desk.scope)


def job(desk: SimpleNamespace, receipt: str):  # noqa: ANN201
    return desk.worker.store.job(user_id=desk.owner, connection_id=receipt)


def test_a_refused_read_resumes_once_the_day_turns_in_santo_domingo(desk):  # noqa: ANN001
    receipt = refused(desk)
    spent = job(desk, receipt)
    assert spent.provider_calls == 1
    resume = ReadResume(desk.worker)
    desk.clock.now = BEFORE_MIDNIGHT
    assert resume.run(desk.clock()) == NOTHING
    assert draft(desk, receipt).status == "saved"
    desk.clock.now = AFTER_MIDNIGHT
    assert resume.run(desk.clock()) == ONE_RESUMED
    fresh = job(desk, receipt)
    assert (fresh.attempt, fresh.provider_calls, fresh.asked_at) == (1, 0, AFTER_MIDNIGHT)
    assert fresh.attempt_id != spent.attempt_id
    assert (draft(desk, receipt).status, draft(desk, receipt).error_code) == (
        "queued",
        None,
    )
    assert read(desk, receipt) == "prepared"
    assert draft(desk, receipt).status == "review_ready"
    assert desk.extractor.calls == 2


@pytest.mark.parametrize("desk", [{"per_day": 300, "per_month": 1}], indirect=True)
def test_a_read_the_month_refused_resumes_once_the_month_turns(desk):  # noqa: ANN001
    receipt = refused(desk, "business_read_budget_month")
    resume = ReadResume(desk.worker)
    desk.clock.now = NEXT_MONTH - MINUTE
    assert resume.run(desk.clock()) == NOTHING
    desk.clock.now = NEXT_MONTH + MINUTE
    assert resume.run(desk.clock()) == ONE_RESUMED
    assert read(desk, receipt) == "prepared"
    assert desk.extractor.calls == 2


def test_nothing_resumes_while_the_owner_has_reading_off(desk):  # noqa: ANN001
    receipt = refused(desk)
    waiting = draft(desk, receipt)
    turn_reading(desk.reading, desk.scope.space_id, desk.owner, enabled=False)
    desk.clock.now = AFTER_MIDNIGHT
    resume = ReadResume(desk.worker)
    assert resume.run(desk.clock()) == {"due": 1, "requeued": 0}
    assert draft(desk, receipt) == waiting
    assert job(desk, receipt).provider_calls == 1
    turn_reading(desk.reading, desk.scope.space_id, desk.owner)
    assert resume.run(desk.clock()) == ONE_RESUMED
    assert read(desk, receipt) == "prepared"


def test_a_second_pass_and_a_second_worker_queue_nothing_more(desk):  # noqa: ANN001
    receipt = refused(desk)
    desk.clock.now = AFTER_MIDNIGHT
    first, second = ReadResume(desk.worker), ReadResume(worker_service(desk))
    assert first.run(desk.clock()) == ONE_RESUMED
    queued = (draft(desk, receipt), job(desk, receipt))
    assert first.run(desk.clock()) == NOTHING
    assert second.run(desk.clock()) == NOTHING
    assert (draft(desk, receipt), job(desk, receipt)) == queued
    assert read(desk, receipt) == "prepared"
    assert desk.extractor.calls == 2


def test_two_workers_choosing_the_same_receipt_at_once_queue_it_once(desk):  # noqa: ANN001
    receipt = refused(desk)
    desk.clock.now = AFTER_MIDNIGHT
    workers = [desk.worker, worker_service(desk)]
    chosen = desk.worker.store.refused_before(
        before={"business_read_budget_day": desk.clock()}
    )
    assert [row[1] for row in chosen] == [receipt]
    barrier = Barrier(2)

    def run(service: DocumentsService) -> dict[str, int]:
        def both_chose_it(**_: object) -> list[tuple[str, str, int]]:
            barrier.wait()
            return chosen

        service.store.refused_before = both_chose_it  # type: ignore[method-assign]
        return ReadResume(service).run(desk.clock())

    with ThreadPoolExecutor(max_workers=2) as threads:
        reports = list(threads.map(run, workers))
    assert sorted(report["requeued"] for report in reports) == [0, 1]
    assert (job(desk, receipt).attempt, job(desk, receipt).provider_calls) == (1, 0)
    assert read(desk, receipt) == "prepared"
    assert desk.extractor.calls == 2


def test_a_read_refused_again_on_resume_waits_for_the_next_day(desk):  # noqa: ANN001
    receipt = refused(desk)
    desk.clock.now = AFTER_MIDNIGHT
    assert read(desk, uploaded(desk)) == "prepared"
    resume = ReadResume(desk.worker)
    assert resume.run(desk.clock()) == ONE_RESUMED
    assert read(desk, receipt) == "business_read_budget_day"
    assert resume.run(desk.clock()) == NOTHING
    desk.clock.now = AFTER_MIDNIGHT + timedelta(days=1)
    assert resume.run(desk.clock()) == ONE_RESUMED
    assert read(desk, receipt) == "prepared"
    assert desk.extractor.calls == 3


def test_a_receipt_the_person_asked_for_first_is_left_to_them(desk):  # noqa: ANN001
    receipt = refused(desk)
    desk.clock.now = AFTER_MIDNIGHT
    desk.uploads.queue(
        user_id=desk.owner, connection_id=receipt, consent=True, scope=desk.scope
    )
    asyncio.run(dispatch_preparation(desk.uploads, desk.owner, receipt, scope=desk.scope))
    asked = (draft(desk, receipt), job(desk, receipt))
    assert ReadResume(desk.worker).run(desk.clock()) == NOTHING
    assert (draft(desk, receipt), job(desk, receipt)) == asked


def test_the_index_holds_exactly_the_read_budget_refusals(desk):  # noqa: ANN001
    with desk.pool.connection() as db:
        [definition] = db.execute(
            "select indexdef from pg_indexes where schemaname='public'"
            " and indexname='financial_document_extractions_refused_idx'"
        ).fetchone()
    assert set(re.findall(r"'(business_\w+)'", definition)) == READ_BUDGET_REFUSALS
