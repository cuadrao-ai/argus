"""The read breaker and a waiting retry on real Postgres: every worker reads
one breaker row, no client role can see or change it, one read probes however
many ask at once, a waiting retry is pulled once and only when its wait passed,
and a retry that succeeds leaves one extraction for the document."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from threading import Barrier
from typing import Any

import psycopg
import pytest
from argus.domain.ingestion.documents.breaker import (
    COOLDOWN,
    Admission,
    BreakerState,
    PostgresReadBreaker,
)
from argus.domain.ingestion.documents.config import (
    BREAKER_FAILURES,
    BREAKER_WINDOW_SECONDS,
    MAX_PROVIDER_CALLS,
    READ_DEADLINE_SECONDS,
)
from argus.domain.ingestion.documents.failures import (
    READ_DEADLINE_PASSED,
    READS_PAUSED,
    ReadFailure,
)
from argus.domain.ingestion.documents.jobs import SweepReport, run_attempt
from argus.domain.ingestion.documents.models import (
    DocumentExtractionError,
    ExtractionBatch,
)
from argus.domain.owner_scope import PERSONAL
from psycopg_pool import ConnectionPool

from tests import test_document_jobs_postgres as documents
from tests import test_financial_accounts_postgres as shared

users = shared.users
pytestmark = pytest.mark.skipif(
    not shared.DSN, reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured"
)

TABLE = "public.document_read_breaker"
NOON = datetime(2026, 11, 16, 16, tzinfo=timezone.utc)
FAILED = "extraction_provider_failed"


def close(pool: ConnectionPool) -> None:
    with pool.connection() as db:
        db.execute(
            f"update {TABLE} set failures='{{}}', opened_at=null, probe_at=null, "
            "probe_id=null"
        )


@pytest.fixture
def pool():
    """The breaker is one row for the whole database: closed before and after."""
    with ConnectionPool(shared.DSN, min_size=0, max_size=8) as opened:
        close(opened)
        try:
            yield opened
        finally:
            close(opened)


@pytest.fixture
def other_pool():
    """A second worker, or the next deploy: its own connections."""
    with ConnectionPool(shared.DSN, min_size=0, max_size=8) as opened:
        yield opened


def open_breaker(breaker: PostgresReadBreaker, at: datetime = NOON) -> datetime:
    for second in range(BREAKER_FAILURES):
        breaker.failed(at + timedelta(seconds=second))
    return at + timedelta(seconds=BREAKER_FAILURES - 1)


def state(pool: ConnectionPool) -> BreakerState:
    return PostgresReadBreaker(pool)._load()


def test_the_migration_leaves_one_closed_row_that_cannot_be_doubled(pool):
    with pool.connection() as db:
        assert db.execute(f"select count(*) from {TABLE}").fetchone() == (1,)
        with pytest.raises(psycopg.errors.UniqueViolation):
            db.execute(f"insert into {TABLE} default values")
    with pool.connection() as db, pytest.raises(psycopg.errors.CheckViolation):
        db.execute(f"insert into {TABLE}(singleton) values (false)")
    with pool.connection() as db, pytest.raises(psycopg.errors.CheckViolation):
        db.execute(
            f"update {TABLE} set probe_at=now(), probe_id='probe', opened_at=null"
        )
    # A probe always has its id, and an id always has its probe.
    for unnamed in ("probe_at=now()", "probe_id='probe'"):
        with pool.connection() as db, pytest.raises(psycopg.errors.CheckViolation):
            db.execute(f"update {TABLE} set opened_at=now(), {unnamed}")
    assert state(pool) == BreakerState()


@contextmanager
def acting_as(db, role: str, user_id: str):  # noqa: ANN001
    with db.transaction(force_rollback=True):
        db.execute(f"set local role {role}")
        db.execute("select set_config('request.jwt.claim.sub',%s,true)", (user_id,))
        yield


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_no_client_role_reads_or_writes_the_breaker(pool, users, role):
    with pool.connection() as db:
        assert db.execute(
            f"select relrowsecurity from pg_class where oid='{TABLE}'::regclass"
        ).fetchone() == (True,)
        assert db.execute(
            "select count(*) from pg_policies where schemaname='public' "
            "and tablename='document_read_breaker'"
        ).fetchone() == (0,)
        for statement in (
            f"select * from {TABLE}",
            f"insert into {TABLE} default values",
            f"update {TABLE} set opened_at=now()",
            f"delete from {TABLE}",
        ):
            with (
                acting_as(db, role, users["owner"]),
                pytest.raises(psycopg.errors.InsufficientPrivilege),
            ):
                db.execute(statement)
    assert state(pool) == BreakerState()


def test_the_server_role_reads_and_moves_the_breaker(pool, users):
    with pool.connection() as db, acting_as(db, "service_role", users["owner"]):
        db.execute(f"update {TABLE} set opened_at=now()")
        assert db.execute(f"select opened_at is not null from {TABLE}").fetchone() == (
            True,
        )


def test_every_worker_and_the_next_deploy_see_the_same_breaker(pool, other_pool):
    here, there = PostgresReadBreaker(pool), PostgresReadBreaker(other_pool)
    for second in range(BREAKER_FAILURES - 1):
        (here if second % 2 else there).failed(NOON + timedelta(seconds=second))
        assert there.paused_until(NOON) is None
    here.failed(NOON + timedelta(seconds=BREAKER_FAILURES - 1))
    opened = NOON + timedelta(seconds=BREAKER_FAILURES - 1)

    assert there.paused_until(opened) == opened + COOLDOWN
    held = there.admit(opened + COOLDOWN - timedelta(seconds=1))
    assert (held.until, held.probe) == (opened + COOLDOWN, None)
    # A new process starts with no memory of its own and reads the same row.
    with ConnectionPool(shared.DSN, min_size=0, max_size=2) as redeploy:
        assert PostgresReadBreaker(redeploy).paused_until(opened) == opened + COOLDOWN

    # A call sent before it opened answers or fails late, from either worker:
    # the breaker stays open and its cooldown does not move.
    there.succeeded(opened + timedelta(seconds=1))
    here.failed(opened + timedelta(seconds=2))
    assert state(pool) == BreakerState(opened_at=opened)
    assert here.paused_until(opened + timedelta(seconds=2)) == opened + COOLDOWN

    # One worker sends the probe; another reports for it with the probe's id.
    probing = there.admit(opened + COOLDOWN)
    assert probing.until is None and state(pool).probe_id == probing.probe
    here.succeeded(opened + COOLDOWN)
    here.failed(opened + COOLDOWN)
    assert state(pool).probe_id == probing.probe, "only the probe's end counts"
    here.succeeded(opened + COOLDOWN, probing.probe)
    assert here.paused_until(opened + COOLDOWN) is None
    assert state(pool) == BreakerState()


def test_failures_spread_past_the_window_never_open_it(pool):
    breaker = PostgresReadBreaker(pool)
    for step in range(BREAKER_FAILURES * 2):
        breaker.failed(NOON + timedelta(seconds=step * BREAKER_WINDOW_SECONDS / 2))
    assert state(pool).opened_at is None
    assert len(state(pool).failures) < BREAKER_FAILURES, "old failures are dropped"


def test_one_read_probes_however_many_ask_at_once(pool, other_pool):
    opened = open_breaker(PostgresReadBreaker(pool))
    after = opened + COOLDOWN
    askers = [PostgresReadBreaker(pool), PostgresReadBreaker(other_pool)] * 3
    barrier = Barrier(len(askers))

    def ask(breaker: PostgresReadBreaker) -> Admission:
        barrier.wait()
        return breaker.admit(after)

    with ThreadPoolExecutor(max_workers=len(askers)) as threads:
        answers = list(threads.map(ask, askers))
    [probe] = [answer.probe for answer in answers if answer.until is None]
    assert all(answer.until > after for answer in answers if answer.probe is None)
    assert (state(pool).probe_at, state(pool).probe_id) == (after, probe)

    # The probe fails: the cooldown starts again for everyone.
    PostgresReadBreaker(other_pool).failed(after + timedelta(seconds=2), probe)
    assert state(pool) == BreakerState(opened_at=after + timedelta(seconds=2))
    # The same probe reports again, late: nothing moves.
    PostgresReadBreaker(pool).succeeded(after + timedelta(seconds=3), probe)
    PostgresReadBreaker(pool).failed(after + timedelta(seconds=3), probe)
    assert state(pool) == BreakerState(opened_at=after + timedelta(seconds=2))


class Flaky(documents.Extractor):
    """The provider fails for now ``failures`` times, then answers."""

    def __init__(self, failures: int) -> None:
        super().__init__()
        self.failures = failures

    async def extract(self, **kwargs: Any) -> ExtractionBatch:
        if self.calls < self.failures:
            await documents.start_request(dict(kwargs))
            self.calls += 1
            error = DocumentExtractionError(FAILED, True)
            error.read_failure = ReadFailure("transient")
            raise error
        return await super().extract(**kwargs)


def rows(pool: ConnectionPool, connection: str) -> int:
    with pool.connection() as db:
        return db.execute(
            "select count(*) from public.financial_document_extractions "
            "where connection_id=%s",
            (connection,),
        ).fetchone()[0]


@pytest.mark.asyncio
async def test_a_waiting_retry_is_pulled_once_and_writes_one_extraction(
    pool, other_pool, users
):
    clock, extractor = documents.far_clock(), Flaky(failures=2)
    api = documents.instance(pool, clock, extractor)
    api.service.read_breaker = PostgresReadBreaker(pool)
    other = documents.instance(other_pool, clock, extractor)
    store, owner = api.service.store, users["owner"]
    connection = await documents.capture(api.service, owner)
    api.jobs.start(user_id=owner, connection_id=connection)
    [first] = api.attempts(connection)

    attempt = first
    for calls in (1, 2):
        assert await run_attempt(api.service, connection, attempt) == FAILED
        waiting = store.job(user_id=owner, connection_id=connection)
        assert waiting.provider_calls == calls and waiting.attempt_id != attempt
        draft = store.draft(user_id=owner, connection_id=connection)
        assert (draft.status, draft.error_code) == ("queued", None)
        assert store.get(user_id=owner, connection_id=connection) is None
        # Before its wait passes no worker is given this read.
        clock.now = waiting.not_before - timedelta(seconds=1)
        assert _pull_only(store, clock, connection) is None
        assert connection not in api.jobs.sweep().redispatched
        clock.now = waiting.not_before
        if calls == 1:
            _, attempt = _pull_only(store, clock, connection)
            assert attempt == waiting.attempt_id

    # Two workers on two pools pull at the same instant: one gets the retry.
    barrier = Barrier(2)

    def pull(instance: documents.Instance) -> tuple[str, str] | None:
        barrier.wait()
        return _pull_only(instance.service.store, clock, connection)

    with ThreadPoolExecutor(max_workers=2) as workers:
        pulled = [take for take in workers.map(pull, (api, other)) if take]
    assert pulled == [(connection, waiting.attempt_id)]

    assert await run_attempt(api.service, *pulled[0]) == "prepared"
    assert await run_attempt(other.service, *pulled[0]) != "prepared"
    final = store.job(user_id=owner, connection_id=connection)
    assert final.provider_calls == 3 <= MAX_PROVIDER_CALLS
    assert rows(pool, connection) == 1, "the retry wrote into the same row"
    batch = store.get(user_id=owner, connection_id=connection)
    assert [c.amount for c in batch.candidates] == ["129.5"]
    assert api.service.get(
        user_id=owner, connection_id=connection, scope=PERSONAL
    ).status == ("review_ready")
    assert api.sink.submit.call_count + other.sink.submit.call_count == 1
    assert state(pool).opened_at is None
    documents.forget(api.service, owner, connection)


def _pull_only(store, clock, connection: str) -> tuple[str, str] | None:  # noqa: ANN001
    """One worker's pull, counted only when it is this test's receipt: other
    tests leave their own rows waiting in the shared database."""
    for _ in range(50):
        pulled = store.pull(now=clock.now, cap=10_000)
        if pulled is None or pulled[0] == connection:
            return pulled
    return None


@pytest.mark.asyncio
async def test_a_read_the_open_breaker_holds_is_not_charged_a_call(pool, users):
    clock, extractor = documents.far_clock(), documents.Extractor()
    api = documents.instance(pool, clock, extractor)
    breaker = PostgresReadBreaker(pool)
    api.service.read_breaker = breaker
    store, owner = api.service.store, users["owner"]
    connection = await documents.capture(api.service, owner)
    api.jobs.start(user_id=owner, connection_id=connection)
    [attempt] = api.attempts(connection)
    opened = open_breaker(breaker, clock.now - timedelta(seconds=BREAKER_FAILURES))

    assert await run_attempt(api.service, connection, attempt) == READS_PAUSED
    held = store.job(user_id=owner, connection_id=connection)
    assert (held.provider_calls, held.retry_waited) == (0, 0)
    assert held.not_before == opened + COOLDOWN
    assert held.provider_call_started_at is None
    draft = store.draft(user_id=owner, connection_id=connection)
    assert (draft.status, draft.error_code) == ("queued", None)
    assert extractor.calls == 0

    # After the cooldown this read is the probe, and its answer closes it.
    clock.now = opened + COOLDOWN
    assert _pull_only(store, clock, connection) == (connection, held.attempt_id)
    assert await run_attempt(api.service, connection, held.attempt_id) == "prepared"
    assert state(pool) == BreakerState()
    assert extractor.calls == 1 and rows(pool, connection) == 1
    documents.forget(api.service, owner, connection)


@pytest.mark.asyncio
async def test_a_held_read_expires_six_hours_after_the_upload(pool, users):
    """On the real store: the breaker holds the read, the outage outlasts the
    deadline, and the sweep's pass over this row ends the read with its own
    reason while the breaker stays open."""
    clock, extractor = documents.far_clock(), documents.Extractor()
    api = documents.instance(pool, clock, extractor)
    breaker = PostgresReadBreaker(pool)
    api.service.read_breaker = breaker
    store, owner = api.service.store, users["owner"]
    connection = await documents.capture(api.service, owner)
    uploaded = store.draft(user_id=owner, connection_id=connection).created_at
    api.jobs.start(user_id=owner, connection_id=connection)
    [attempt] = api.attempts(connection)
    assert store.job(user_id=owner, connection_id=connection).asked_at == uploaded
    opened = open_breaker(breaker, clock.now)
    clock.now = opened

    assert await run_attempt(api.service, connection, attempt) == READS_PAUSED
    held = store.job(user_id=owner, connection_id=connection)
    assert (held.asked_at, held.not_before) == (uploaded, opened + COOLDOWN)

    def swept() -> list[str]:
        # The sweep's own pass, over this test's row only: other tests leave
        # rows waiting in the shared database.
        report = SweepReport()
        api.jobs._reconcile(owner, connection, clock.now, report)
        return report.expired

    clock.now = uploaded + timedelta(seconds=READ_DEADLINE_SECONDS - 1)
    assert swept() == []
    clock.now += timedelta(seconds=1)
    assert swept() == [connection]
    draft = store.draft(user_id=owner, connection_id=connection)
    assert (draft.status, draft.error_code) == (
        "needs_attention",
        READ_DEADLINE_PASSED,
    )
    assert _pull_only(store, clock, connection) is None
    assert swept() == []
    assert state(pool) == BreakerState(opened_at=opened)
    assert extractor.calls == 0
    documents.forget(api.service, owner, connection)
