"""Held-file database invariants; only a disposable local database may run them."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier, Event
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from argus.api.documents import dispatch_preparation
from argus.domain.business.contracts.deletion import PURGE_AFTER
from argus.domain.business.read_budget import (
    HELD_READ_REFUSAL,
    PostgresHeldReadBudget,
    ReadBudgetSettings,
)
from argus.domain.ingestion.documents.objects import InMemorySourceObjects
from argus.domain.ingestion.whatsapp.held import (
    BoundPool,
    HeldFileExpiry,
    PostgresHeldFiles,
)
from argus.domain.owner_scope import PERSONAL
from psycopg_pool import ConnectionPool

from tests import test_account_deletion_postgres as deletion
from tests import test_business_read_budget_postgres as budgets
from tests import test_financial_accounts_postgres as accounts
from tests.document_reads_support import read_receipt
from tests.test_whatsapp_receipt_read_postgres import Extractor
from workflows.document_job import postgres_documents_service
from workflows.read_resume import ReadResume

users = accounts.users
space = budgets.space
lane = deletion.lane
pytestmark = pytest.mark.skipif(
    not accounts.DSN, reason="Disposable local database is not configured"
)


@pytest.fixture
def reads_finish_inside_the_request() -> None:
    """The worker explicitly takes the queued attempt."""


@pytest.fixture
def pool():
    with ConnectionPool(accounts.DSN, min_size=0, max_size=8) as opened:
        yield opened


@pytest.fixture
def desk(pool, users, monkeypatch):
    for key, value in {
        "INTAKE_ENABLED": "true",
        "VERIFY_TOKEN": "fake",
        "APP_SECRET": "fake",
        "ACCESS_TOKEN": "fake",
        "SENDER_KEY": "fake",
        "NUMBER_ID": "1234",
        "HELD_READS_PER_DAY": "1",
    }.items():
        monkeypatch.setenv("CUADRAO_WHATSAPP_" + key, value)
    from tests.business_reading_support import ROUTE

    monkeypatch.setattr(
        "argus.domain.ingestion.whatsapp.receipt_consent.receipt_provider_route",
        lambda: ROUTE,
    )
    objects = InMemorySourceObjects()
    extractor = Extractor()
    service = postgres_documents_service(pool, objects, extractor)
    desk = SimpleNamespace(
        pool=pool,
        owner=users["owner"],
        other=users["other"],
        objects=objects,
        extractor=extractor,
        service=service,
        files=PostgresHeldFiles(service.store),
        now=datetime.now(timezone.utc),
    )
    service.hub.clock = lambda: desk.now
    return desk


def link_sender(desk):
    """Accept the read notice on the real link that accompanies the held draft."""
    from argus.domain.ingestion.whatsapp.store_postgres import PostgresWhatsAppStore

    from tests.ingestion.whatsapp_link_support import NOTICE

    store = PostgresWhatsAppStore(desk.pool)
    code = uuid4().bytes * 2
    desk.sender_hash = uuid4().bytes * 2
    store.issue_code(
        destination_owner_id=desk.owner,
        code_digest=code,
        reply_language="es-419",
        disclosure=NOTICE,
        now=desk.now,
        expires_at=desk.now + timedelta(minutes=10),
    )
    link = store.redeem_code(
        code_digest=code, sender_hash=desk.sender_hash, last4="0123", now=desk.now
    )
    assert link is not None
    desk.sender_link_id = link.id


@pytest.fixture
def linked_desk(desk):
    from tests.ingestion.whatsapp_link_support import prepare_phone_business
    from tests.test_business_spaces_migration_postgres import owned_space

    with desk.pool.connection() as db:
        business = owned_space(db, desk.owner)
    prepare_phone_business(desk.pool, business, desk.owner)
    link_sender(desk)
    return desk


def upload(desk, *, content=None):
    message = uuid4().bytes * 2

    async def capture():
        result = await desk.service.upload(
            user_id=desk.owner,
            content=content or b"%PDF-" + uuid4().bytes,
            filename="held.pdf",
            media_type="application/pdf",
            consent=True,
            scope=PERSONAL,
            on_capture=desk.files.capture(
                user_id=desk.owner,
                sender_link_id=getattr(desk, "sender_link_id", str(uuid4())),
                provider_message_key=message,
                reason="no_match",
                now=desk.now,
            ),
        )
        await dispatch_preparation(
            desk.service, desk.owner, result.connection_id, scope=PERSONAL
        )

    asyncio.run(capture())
    return next(
        row
        for row in desk.files.list_for_user(desk.owner)
        if row.provider_message_key == message
    )


def read(desk, row):
    return asyncio.run(read_receipt(desk.service, desk.owner, row.connection_id))


def test_one_read_no_business_charge_import_event_or_record(linked_desk):
    desk = linked_desk
    row = upload(desk)
    assert read(desk, row) == "prepared"
    assert desk.extractor.calls == 1
    with desk.pool.connection() as db:
        assert db.execute(
            "select owner_space_id from public.financial_source_connections where id=%s",
            (row.connection_id,),
        ).fetchone() == (None,)
        assert db.execute(
            "select sum(reads) from public.whatsapp_held_read_usage where user_id=%s",
            (desk.owner,),
        ).fetchone() == (1,)
        for table in ("financial_import_events", "financial_records"):
            assert db.execute(
                f"select count(*) from public.{table} where user_id=%s", (desk.owner,)
            ).fetchone() == (0,)
        assert db.execute(
            "select count(*) from public.business_read_daily_usage u join public.spaces s on s.id=u.business_id where s.created_by=%s",
            (desk.owner,),
        ).fetchone() == (0,)


def test_cap_resumes_next_santo_domingo_day(linked_desk):
    desk = linked_desk
    from argus.domain.ingestion.email_intake.budget import next_business_day

    first, waiting = upload(desk), upload(desk)
    assert read(desk, first) == "prepared"
    assert read(desk, waiting) == HELD_READ_REFUSAL
    assert desk.extractor.calls == 1
    resume = ReadResume(desk.service)
    assert resume.run(desk.now) == {"due": 0, "requeued": 0}
    desk.now = next_business_day(desk.now) + timedelta(seconds=1)
    assert resume.run(desk.now) == {"due": 1, "requeued": 1}
    assert read(desk, waiting) == "prepared"
    assert desk.extractor.calls == 2


def test_hand_over_limits_original_day_and_aborted_transaction(pool, users, space):
    now = datetime(2026, 11, 24, 15, tzinfo=timezone.utc)
    charged = now - timedelta(days=1)
    budget = PostgresHeldReadBudget(
        pool, ReadBudgetSettings(per_day=1, per_month=1), per_day=3
    )
    assert budget.charge(users["owner"], charged) is None
    with pool.connection() as db, db.transaction(force_rollback=True):
        transfer = PostgresHeldReadBudget(BoundPool(db), budget.settings)
        assert (
            transfer.hand_over(users["owner"], space, now, charged_at=charged)
            == "transferred"
        )
        assert db.execute(
            "select sum(reads) from public.business_read_daily_usage where business_id=%s",
            (space,),
        ).fetchone() == (1,)
    with pool.connection() as db:
        assert db.execute(
            "select sum(reads) from public.business_read_daily_usage where business_id=%s",
            (space,),
        ).fetchone() == (None,)
        assert db.execute(
            "select sum(reads) from public.whatsapp_held_read_usage where user_id=%s",
            (users["owner"],),
        ).fetchone() == (1,)
    assert budget.hand_over(users["owner"], space, now) == "transferred"
    budget.charge(users["owner"], charged)
    for instant in (now, now + timedelta(days=1)):
        assert (
            budget.hand_over(users["owner"], space, instant, charged_at=charged)
            == "business_full"
        )
    with pool.connection() as db:
        assert db.execute(
            "select sum(reads) from public.business_read_daily_usage where business_id=%s",
            (space,),
        ).fetchone() == (1,)
        assert db.execute(
            "select day,reads from public.whatsapp_held_read_usage where user_id=%s",
            (users["owner"],),
        ).fetchall() == [(charged.date(), 1)]


def test_concurrent_held_charges_obey_cap(pool, users):
    budget = PostgresHeldReadBudget(pool, per_day=1)
    barrier = Barrier(3)

    def charge(_):
        barrier.wait()
        return budget.charge(users["owner"], datetime.now(timezone.utc))

    with ThreadPoolExecutor(max_workers=3) as threads:
        results = list(threads.map(charge, range(3)))
    assert results.count(None) == 1
    assert results.count(HELD_READ_REFUSAL) == 2


def test_expiry_old_new_objects_and_second_run(desk):
    old = upload(desk)
    desk.now += PURGE_AFTER + timedelta(seconds=1)
    newer = upload(desk)
    HeldFileExpiry(desk.pool, desk.objects, clock=lambda: desk.now).tick()
    assert (
        desk.service.store.draft(user_id=desk.owner, connection_id=old.connection_id)
        is None
    )
    assert desk.service.store.draft(user_id=desk.owner, connection_id=newer.connection_id)
    before = dict(desk.objects.objects)
    assert not desk.files.expire(old.id, desk.now)
    assert desk.objects.objects == before
    assert {r.id: r.state for r in desk.files.list_for_user(desk.owner)} == {
        old.id: "expired",
        newer.id: "held",
    }
    assert len(before) == 1


def test_failed_erase_keeps_draft_and_assignment_wins_retry(desk, space, monkeypatch):
    row = upload(desk)
    desk.now += PURGE_AFTER + timedelta(seconds=1)

    def fail(_):
        raise RuntimeError("temporary")

    with monkeypatch.context() as patch:
        patch.setattr(desk.objects, "remove", fail)
        with pytest.raises(RuntimeError):
            desk.files.expire(row.id, desk.now)
    assert desk.service.store.draft(user_id=desk.owner, connection_id=row.connection_id)
    started = Event()

    def expire():
        started.set()
        return desk.files.expire(row.id, desk.now)

    with ThreadPoolExecutor(max_workers=1) as threads:
        with desk.files.assignment(desk.owner, row.id) as (db, held):
            assert held.state == "held"
            future = threads.submit(expire)
            assert started.wait(5)
            assert PostgresHeldFiles(
                type(desk.service.store)(BoundPool(db), desk.objects)
            ).settle(
                user_id=desk.owner,
                held_id=row.id,
                business_id=space,
                connection_id=str(uuid4()),
                now=desk.now,
            )
        assert future.result(timeout=10) is False
    assert not desk.files.expire(row.id, desk.now)
    assert desk.service.store.source(user_id=desk.owner, connection_id=row.connection_id)


def test_expiry_winner_cannot_assign(desk, space):
    row = upload(desk)
    desk.now += PURGE_AFTER + timedelta(seconds=1)
    assert desk.files.expire(row.id, desk.now)
    assert not desk.files.settle(
        user_id=desk.owner,
        held_id=row.id,
        business_id=space,
        connection_id=str(uuid4()),
        now=desk.now,
    )


def test_shared_original_rebuilt_keep_both_drafts(desk):
    row = upload(desk, content=b"%PDF-shared")
    connection = desk.service.hub.connections.create(
        user_id=desk.owner,
        source="statement",
        external_ref=str(uuid4()),
        label=None,
        now=desk.now,
        scope=PERSONAL,
    )
    draft = desk.service.store.draft(user_id=desk.owner, connection_id=row.connection_id)
    assert desk.service.store.capture(
        user_id=desk.owner,
        draft=draft.model_copy(update={"connection_id": connection.id, "resolution": {}}),
        content=b"%PDF-shared",
    )
    for target in (row.connection_id, connection.id):
        assert desk.service.store.save_rebuilt(
            user_id=desk.owner,
            connection_id=target,
            content=b"rebuilt",
            media_type="image/jpeg",
        )
    desk.now += PURGE_AFTER + timedelta(seconds=1)
    before = dict(desk.objects.objects)
    assert not desk.files.expire(row.id, desk.now)
    assert desk.objects.objects == before
    for target in (row.connection_id, connection.id):
        assert desk.service.store.draft(user_id=desk.owner, connection_id=target)


@pytest.mark.parametrize("table", ["whatsapp_held_files", "whatsapp_held_read_usage"])
def test_rls_own_select_and_no_client_writes(desk, table):
    upload(desk)
    desk.files.budget().charge(desk.owner, desk.now)
    with desk.pool.connection() as db:
        with budgets.acting_as(db, "authenticated", desk.owner):
            assert db.execute(f"select count(*) from public.{table}").fetchone() == (1,)
        with budgets.acting_as(db, "authenticated", desk.other):
            assert db.execute(f"select count(*) from public.{table}").fetchone() == (0,)
        for role in ("anon", "authenticated"):
            for sql in (
                f"insert into public.{table} select * from public.{table}",
                f"update public.{table} set user_id=user_id",
                f"delete from public.{table}",
            ):
                with (
                    budgets.acting_as(db, role, desk.owner),
                    pytest.raises(psycopg.errors.InsufficientPrivilege),
                ):
                    db.execute(sql)


def test_account_deletion_removes_held_rows_drafts_objects(desk, lane):
    row = upload(desk)
    desk.files.budget().charge(desk.owner, desk.now)
    service = deletion._service(
        lane, deletion.SqlAuthAdmin(), source_objects=desk.objects, clock=lambda: desk.now
    )
    assert service.delete_account(user_id=desk.owner).status == "done"
    with desk.pool.connection() as db:
        for table in (
            "whatsapp_held_files",
            "whatsapp_held_read_usage",
            "financial_document_extractions",
            "financial_source_connections",
        ):
            assert db.execute(
                f"select count(*) from public.{table} where user_id=%s", (desk.owner,)
            ).fetchone() == (0,)
    assert not desk.objects.objects
    assert not desk.files.expire(row.id, desk.now)


def test_custody_reference_protects_held_file(desk, space):
    row = upload(desk)
    draft = desk.service.store.draft(user_id=desk.owner, connection_id=row.connection_id)
    path = next(iter(desk.objects.objects))
    with desk.pool.connection() as db:
        db.execute(
            "insert into argus_private.business_custody_reservations(space_id,custodian_id,deleted_actor_id) values(%s,%s,%s)",
            (space, str(uuid4()), str(uuid4())),
        )
        db.execute(
            "insert into argus_private.business_custody_objects(space_id,source_path,destination_path,sha256,size_bytes,media_type) values(%s,%s,%s,%s,%s,%s)",
            (
                space,
                path,
                "custody/held-test/" + str(uuid4()),
                draft.sha256,
                draft.size_bytes,
                draft.media_type,
            ),
        )
    try:
        desk.now += PURGE_AFTER + timedelta(seconds=1)
        assert not desk.files.expire(row.id, desk.now)
        assert desk.service.store.draft(
            user_id=desk.owner, connection_id=row.connection_id
        )
        assert desk.objects.get(path)
    finally:
        with desk.pool.connection() as db:
            db.execute(
                "delete from argus_private.business_custody_objects where space_id=%s",
                (space,),
            )
            db.execute(
                "delete from argus_private.business_custody_reservations where space_id=%s",
                (space,),
            )


def test_partial_erasure_blocks_assignment_and_retries(desk, space, monkeypatch):
    row = upload(desk)
    desk.service.store.save_rebuilt(
        user_id=desk.owner,
        connection_id=row.connection_id,
        content=b"rebuilt",
        media_type="image/jpeg",
    )
    desk.now += PURGE_AFTER + timedelta(seconds=1)
    remove = desk.objects.remove
    calls = []

    def partial(path):
        calls.append(path)
        if len(calls) == 2:
            raise RuntimeError("partial")
        remove(path)

    with monkeypatch.context() as patch:
        patch.setattr(desk.objects, "remove", partial)
        with pytest.raises(RuntimeError):
            desk.files.expire(row.id, desk.now)
    assert desk.service.store.draft(user_id=desk.owner, connection_id=row.connection_id)
    assert not desk.files.settle(
        user_id=desk.owner,
        held_id=row.id,
        business_id=space,
        connection_id=str(uuid4()),
        now=desk.now,
    )
    assert desk.files.expire(row.id, desk.now)
    assert not desk.objects.objects
