"""The WhatsApp replay, linking and isolation cases on real Postgres."""

import asyncio
import shutil
import subprocess
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from argus.domain.business.access import PostgresAccessStore
from argus.domain.business.spaces import PostgresSpaceStore
from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository
from argus.domain.ingestion.documents.service import DocumentsService
from argus.domain.ingestion.documents.store_postgres import PostgresDocumentStore
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.whatsapp.reply_worker import FailureReplyWorker
from argus.domain.ingestion.whatsapp.store import SenderLink
from argus.domain.ingestion.whatsapp.store_postgres import PostgresWhatsAppStore
from psycopg import Connection
from psycopg.errors import QueryCanceled
from psycopg_pool import ConnectionPool

from tests import test_financial_accounts_postgres as shared
from tests.document_sources_support import source_objects
from tests.ingestion import whatsapp_cases as cases
from tests.ingestion import whatsapp_heartbeat_cases as heartbeat
from tests.ingestion.whatsapp_support import (
    RECEIPT_PNG,
    Media,
    RefusingExtractor,
    fixture,
)
from tests.ingestion.whatsapp_unlinked_cases import UNLINKED_CASES

W4_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "supabase/migrations/20261125205442_whatsapp_person_links.sql"
)

users = shared.users
pytestmark = pytest.mark.skipif(
    not shared.DSN, reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured"
)


@pytest.fixture
def pool() -> Iterator[ConnectionPool]:
    with ConnectionPool(shared.DSN, min_size=0, max_size=4) as opened:
        yield opened


def _world(pool: ConnectionPool, users: dict[str, str]) -> cases.World:
    clock = cases.Clock()
    connections = PostgresConnectionRepository(pool)
    hub = IngestionHub(connections, box=None, sink=None, clock=clock)
    documents = DocumentsService(
        hub, PostgresDocumentStore(pool, source_objects()), RefusingExtractor()
    )
    return cases.build_world(
        documents=documents,
        store=PostgresWhatsAppStore(pool),
        clock=clock,
        alice=users["owner"],
        bob=users["other"],
        spaces=PostgresSpaceStore(pool),
        access=PostgresAccessStore(pool),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("case", cases.CASES, ids=lambda case: case.__name__)
async def test_intake_case_on_postgres(case, pool, users) -> None:  # noqa: ANN001
    await case(_world(pool, users))


def test_redeeming_without_a_live_grant_preserves_the_existing_link(pool, users) -> None:  # noqa: ANN001
    owner, other = users["owner"], users["other"]
    space, _ = PostgresSpaceStore(pool).create(owner, "Mi negocio")
    cases.prepare_phone_business(pool, space.id, owner)
    store = PostgresWhatsAppStore(pool)
    now, sender = cases.Clock()(), uuid4().bytes + uuid4().bytes

    def redeem(person: str) -> SenderLink | None:
        code = uuid4().bytes + uuid4().bytes
        store.issue_code(
            destination_owner_id=person,
            code_digest=code,
            reply_language="es-419",
            disclosure=cases.NOTICE,
            now=now,
            expires_at=now + timedelta(minutes=10),
        )
        return store.redeem_code(
            code_digest=code, sender_hash=sender, last4="1234", now=now
        )

    original = redeem(owner)
    assert original is not None
    assert redeem(other) is None
    assert store.sender_link(sender_hash=sender) == original


def test_concurrent_unlinked_reservations_for_one_day_take_one_reply(pool, users) -> None:  # noqa: ANN001
    world = _world(pool, users)
    store, now = world.store, world.clock.now
    sender = world.keys.sender(cases.STRANGER_PHONE)
    keys = [world.keys.message(f"wamid.RACE-{n}") for n in range(4)]
    for key in keys:
        store.claim(
            provider_message_key=key,
            sender_hash=sender,
            now=now,
            claim_until=now + timedelta(seconds=90),
        )
    start = threading.Barrier(len(keys))

    def reserve(key: bytes) -> bool:
        start.wait()
        return store.reserve_unlinked_reply(
            sender_hash=sender, provider_message_key=key, now=now
        )

    with ThreadPoolExecutor(len(keys)) as threads:
        taken = list(threads.map(reserve, keys))
    assert sorted(taken) == [False, False, False, True]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    heartbeat.HEARTBEAT_CASES,
    ids=lambda case: case.__name__,
)
async def test_heartbeat_case_on_postgres(case, pool, users) -> None:  # noqa: ANN001
    await case(_world(pool, users))


@pytest.fixture
def pre_w4_database(
    tmp_path: Path, unused_tcp_port: int, pool: ConnectionPool
) -> Iterator[Connection]:
    """Start a separate local database with the migrations preceding W4."""
    migrations = tmp_path / "supabase" / "migrations"
    migrations.mkdir(parents=True)
    for migration in W4_MIGRATION.parent.glob("*.sql"):
        if migration.name < W4_MIGRATION.name:
            shutil.copyfile(migration, migrations / migration.name)
    with pool.connection() as matrix_db:
        major_version = matrix_db.info.server_version // 10000
    (migrations.parent / "config.toml").write_text(
        f'project_id = "w4-replay-{uuid4().hex}"\n'
        f"[db]\nport = {unused_tcp_port}\nmajor_version = {major_version}\n"
        "[db.seed]\nenabled = false\n"
    )
    cli = ["supabase", "--workdir", str(tmp_path)]
    try:
        subprocess.run([*cli, "db", "start"], check=True)
        with Connection.connect(
            host="127.0.0.1",
            port=unused_tcp_port,
            dbname="postgres",
            user="postgres",
            password="postgres",
            autocommit=True,
        ) as db:
            yield db
    finally:
        subprocess.run([*cli, "stop", "--no-backup"], check=True)


def test_migrating_a_pre_w4_capture_names_the_original_person(
    pre_w4_database: Connection,
) -> None:
    """A relink cannot reassign a document captured before W4."""
    from argus.domain.business.authority import authorize
    from argus.domain.business.contracts.authority import TrustedActor
    from argus.domain.business.sent_by import receipt_senders
    from argus.domain.business.transactions import ActionTransaction
    from faker import Faker

    from tests.test_business_spaces_migration_postgres import connection, owned_space

    db = pre_w4_database
    owner = shared._create_users(db, ("owner", False))["owner"]
    with db.transaction():
        business = owned_space(db, owner)
        receipt = connection(db, owner, business)
        person = Faker().name()
        db.execute(
            "update public.profiles set display_name=%s where id=%s", (person, owner)
        )
        sender = uuid4().bytes + uuid4().bytes
        link, pinned_space = db.execute(
            "insert into public.whatsapp_sender_links"
            "(destination_owner_id,wa_id_hash,last4,reply_language,status,linked_at)"
            " values(%s,%s,'1234','es-419','active',now()-interval '2 days')"
            " returning id, destination_space_id::text",
            (owner, sender),
        ).fetchone()
        assert pinned_space == business
        legacy_capture = db.execute(
            "insert into public.whatsapp_inbound_messages"
            "(provider_message_key,sender_hash,destination_owner_id,status,connection_id,"
            "received_at,updated_at) values(%s,%s,%s,'captured',%s,now()-interval '1 day',"
            "now()-interval '1 day') returning sender_link_id",
            (uuid4().bytes + uuid4().bytes, sender, owner, receipt),
        ).fetchone()
        assert legacy_capture == (None,)
        db.execute(
            "update public.whatsapp_sender_links set status='revoked', revoked_at=now()"
            " where id=%s",
            (link,),
        )
        db.execute(
            "insert into public.whatsapp_sender_links"
            "(destination_owner_id,wa_id_hash,last4,reply_language,status,linked_at)"
            " values(%s,%s,'1234','en','active',now())",
            (owner, sender),
        )
    db.execute(W4_MIGRATION.read_text())
    assert db.execute(
        "select sender_link_id from public.whatsapp_inbound_messages where connection_id=%s",
        (receipt,),
    ).fetchone() == (link,)
    auth = authorize(
        db, TrustedActor(actor_id=owner, space_id=business, actor_kind="member")
    )
    tx = ActionTransaction(db, auth, None)
    shown = receipt_senders(tx, [{"id": receipt, "channel": "whatsapp"}])[receipt]
    assert shown.id == f"member:{owner}" and shown.person.display_name == person


def test_erasing_a_sender_keeps_only_masked_attribution_until_the_receipt_is_deleted(
    pool,
    users,
) -> None:  # noqa: ANN001
    from argus.domain.business.authority import authorize
    from argus.domain.business.contracts.authority import TrustedActor
    from argus.domain.business.sent_by import receipt_senders
    from argus.domain.business.transactions import ActionTransaction
    from argus.domain.postgres_connection import BorrowedConnection

    from tests.test_business_spaces_migration_postgres import connection, owned_space

    with pool.connection() as db, db.transaction(force_rollback=True):
        owner, sender = users["owner"], users["other"]
        business = owned_space(db, owner)
        receipt = connection(db, owner, business)
        digest = uuid4().bytes + uuid4().bytes
        message_key = uuid4().bytes + uuid4().bytes
        link = db.execute(
            "insert into public.whatsapp_sender_links"
            "(destination_owner_id,wa_id_hash,last4,reply_language,status,linked_at)"
            " values(%s,%s,'1234','es-419','active',now()) returning id",
            (sender, digest),
        ).fetchone()[0]
        db.execute(
            "insert into public.whatsapp_inbound_messages"
            "(provider_message_key,sender_hash,destination_owner_id,status,connection_id,"
            "sender_link_id,received_at,updated_at) values(%s,%s,%s,'captured',%s,%s,now(),now())",
            (message_key, digest, sender, receipt, link),
        )
        store = PostgresWhatsAppStore(BorrowedConnection(db))
        assert store.captured_connections(destination_owner_id=owner) == {receipt}
        assert not store.captured_connections(destination_owner_id=sender)
        db.execute("delete from auth.users where id=%s", (sender,))
        now = cases.Clock()()
        replay = store.claim(
            provider_message_key=message_key,
            sender_hash=digest,
            now=now,
            claim_until=now + timedelta(seconds=90),
        )
        assert not replay.claimed
        assert replay.record.status == "captured" and replay.record.sender_hash is None
        assert db.execute(
            "select l.destination_owner_id,l.wa_id_hash,l.status,l.last4,m.sender_hash,m.destination_owner_id"
            " from public.whatsapp_inbound_messages m join public.whatsapp_sender_links l on l.id=m.sender_link_id"
            " where m.connection_id=%s",
            (receipt,),
        ).fetchone() == (None, None, "revoked", "1234", None, None)
        auth = authorize(
            db, TrustedActor(actor_id=owner, space_id=business, actor_kind="member")
        )
        shown = receipt_senders(
            ActionTransaction(db, auth, None), [{"id": receipt, "channel": "whatsapp"}]
        )[receipt]
        assert shown.phone_last4 == "1234" and shown.person is None
        db.execute(
            "delete from public.financial_source_connections where id=%s", (receipt,)
        )
        assert (
            db.execute(
                "select 1 from public.whatsapp_sender_links where id=%s", (link,)
            ).fetchone()
            is None
        )


def test_claim_payload_cannot_survive_settlement(pool) -> None:  # noqa: ANN001
    with pool.connection() as db:
        assert (
            db.execute(
                "select column_name from information_schema.columns where table_schema='public'"
                " and table_name='whatsapp_inbound_messages'"
                " and column_name in ('claim_envelope','recovery_attempts')"
            ).fetchall()
            == []
        )


@pytest.mark.asyncio
async def test_english_link_gets_english_only(pool, users) -> None:  # noqa: ANN001
    await cases.english_owner_gets_english_only(_world(pool, users))


@pytest.mark.asyncio
async def test_link_language_wins_over_the_default_english_profile(pool, users) -> None:  # noqa: ANN001
    with pool.connection() as connection:
        [profile_language] = connection.execute(
            "select language from public.profiles where id = %s", (users["owner"],)
        ).fetchone()
    assert profile_language == "en"
    world = _world(pool, users)
    await world.link(world.alice, cases.ALICE_PHONE, "es-419")
    assert world.transport.bodies() == [
        "Listo, este WhatsApp quedó conectado. "
        "Envía aquí la foto o el PDF de tus recibos."
    ]
    with pool.connection() as connection:
        [stored] = connection.execute(
            "select reply_language from public.whatsapp_sender_links "
            "where destination_owner_id = %s and status = 'active'",
            (users["owner"],),
        ).fetchone()
    assert stored == "es-419"


def test_clients_cannot_read_or_write_whatsapp_tables(users) -> None:  # noqa: ANN001
    import psycopg

    with psycopg.connect(shared.DSN) as connection, connection.cursor() as cursor:
        shared._set_authenticated_claims(
            cursor, user_id=users["owner"], is_anonymous=False
        )
        for table in (
            "whatsapp_inbound_messages",
            "whatsapp_link_codes",
            "whatsapp_sender_links",
            "whatsapp_reply_groups",
            "whatsapp_reply_days",
            "whatsapp_reply_attempts",
        ):
            cursor.execute("savepoint probe")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cursor.execute(f"select 1 from public.{table} limit 1")
            cursor.execute("rollback to savepoint probe")
        connection.rollback()


def _worker(world, *, store=None):
    return FailureReplyWorker(
        store=store or world.store.reply_groups,
        codec=world.intake.reply_codec,
        transport=world.transport,
        clock=world.clock,
        enabled=lambda: True,
    )


async def _failed(world, index: int, *, kind: str = "blocked") -> None:
    media_id = f"700000000{index:06d}"
    mime = "image/gif" if kind == "unsupported" else "image/png"
    world.graph.media[media_id] = Media(
        b"not an image" if kind == "blocked" else RECEIPT_PNG,
        mime,
        file_size=cases.MAX_BYTES + 1 if kind == "too_large" else None,
    )
    await world.deliver(
        fixture(
            "image_message.json",
            id=f"wamid.GROUP-{index}",
            image={"id": media_id, "mime_type": mime, "filename": f"factura_{index}.png"},
        )
    )


async def _linked(pool, users):
    world = _world(pool, users)
    await world.link(world.alice, cases.ALICE_PHONE)
    world.transport.sent.clear()
    return world


def _counts(pool, world):
    with pool.connection() as connection:
        return connection.execute(
            "select sent_count,reserved_count from public.whatsapp_reply_days where sender_hash=%s",
            (world.keys.sender(cases.ALICE_PHONE),),
        ).fetchall()


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [1, 5, 12])
async def test_failed_files_wait_then_send_one_group(pool, users, count):
    world = await _linked(pool, users)
    for index in range(count):
        await _failed(world, index)
    assert world.transport.sent == []
    assert not await _worker(world).run_once()
    world.clock.now += timedelta(seconds=120)
    assert await _worker(world).run_once()
    assert len(world.transport.sent) == 1
    if count == 1:
        assert world.transport.sent[0]["context"] == {"message_id": "wamid.GROUP-0"}
        assert world.transport.bodies() == [
            "No pudimos leer este archivo. Envíalo como foto o PDF."
        ]
    else:
        assert world.transport.bodies()[0] == (
            f"No pudimos leer {count} archivos:\n• factura_0.png\n• factura_1.png\n• factura_2.png\n"
            f"• y {count-3} más\nEnvíalos como foto o PDF."
        )
    assert _counts(pool, world) == [(1, 0)]


@pytest.mark.asyncio
async def test_each_failure_resets_wait_and_restart_keeps_group(pool, users):
    from argus.domain.ingestion.whatsapp.reply_groups_postgres import PostgresReplyGroups

    world = await _linked(pool, users)
    await _failed(world, 0)
    world.clock.now += timedelta(seconds=119)
    await _failed(world, 1)
    world.clock.now += timedelta(seconds=1)
    restarted = _worker(world, store=PostgresReplyGroups(pool))
    assert not await restarted.run_once()
    world.clock.now += timedelta(seconds=119)
    assert await restarted.run_once()
    assert len(world.transport.sent) == 1
    assert "2 archivos" in world.transport.bodies()[0]


@pytest.mark.asyncio
async def test_two_workers_send_one_group_and_valid_receipt_stays_immediate(pool, users):
    world = await _linked(pool, users)
    await _failed(world, 0)
    world.graph.media["700000000000991"] = Media(RECEIPT_PNG, "image/png")
    await world.deliver(cases.image("700000000000991", "wamid.VALID"))
    assert len(world.transport.sent) == 1
    assert world.record("wamid.VALID").status == "captured"
    assert _counts(pool, world) == []
    world.clock.now += timedelta(seconds=120)
    results = await asyncio.gather(_worker(world).run_once(), _worker(world).run_once())
    assert sum(results) == 1
    assert len(world.transport.sent) == 2
    assert _counts(pool, world) == [(1, 0)]


@pytest.mark.asyncio
async def test_tenth_group_is_last_and_eleventh_is_suppressed_until_utc_tomorrow(
    pool, users
):
    from argus.domain.ingestion.whatsapp.reply_groups import FINAL_REPLY
    from loguru import logger

    world = await _linked(pool, users)
    # Keep the eleven 2-minute waits inside a single UTC day.
    world.clock.now = world.clock.now.replace(hour=12, minute=0, second=0, microsecond=0)
    records = []
    sink = logger.add(lambda message: records.append(message.record["extra"]))
    try:
        for index in range(11):
            await _failed(world, index)
            world.clock.now += timedelta(seconds=120)
            await _worker(world).run_once()
    finally:
        logger.remove(sink)
    assert len(world.transport.sent) == 10
    assert world.transport.bodies()[-1] == FINAL_REPLY
    assert _counts(pool, world) == [(10, 0)]
    assert any(
        row.get("event") == "whatsapp_reply_suppressed"
        and row.get("reason") == "daily_limit"
        for row in records
    )
    world.clock.now += timedelta(days=1)
    await _failed(world, 11)
    world.clock.now += timedelta(seconds=120)
    await _worker(world).run_once()
    assert len(world.transport.sent) == 11


@pytest.mark.asyncio
@pytest.mark.parametrize("ending", ["window", "revoked"])
async def test_expired_or_revoked_group_never_sends(pool, users, ending):
    world = await _linked(pool, users)
    await _failed(world, 0)
    world.clock.now += (
        timedelta(hours=24) if ending == "window" else timedelta(seconds=120)
    )
    if ending == "revoked":
        world.store.revoke(destination_owner_id=world.alice, now=world.clock.now)
    worker = _worker(world)
    assert await worker.run_once()
    assert not await worker.run_once()
    assert world.transport.sent == []
    assert _counts(pool, world) == []


@pytest.mark.asyncio
async def test_all_grouped_failure_reasons_share_one_counter(pool, users):
    world = await _linked(pool, users)
    for index, kind in enumerate(("blocked", "unsupported", "too_large")):
        await _failed(world, index, kind=kind)
    world.clock.now += timedelta(seconds=120)
    await _worker(world).run_once()
    assert len(world.transport.sent) == 1
    assert "3 archivos" in world.transport.bodies()[0]
    assert _counts(pool, world) == [(1, 0)]


@pytest.mark.asyncio
async def test_known_send_failure_retries_without_charging_and_unknown_does_not_duplicate(
    pool, users
):
    from argus.domain.ingestion.whatsapp.replies import ReplyFailed

    world = await _linked(pool, users)
    world.clock.now = world.clock.now.replace(hour=12, minute=0, second=0, microsecond=0)
    await _failed(world, 0)
    world.clock.now += timedelta(seconds=120)
    original = world.transport.send

    async def rejected(payload):
        raise ReplyFailed("503")

    world.transport.send = rejected
    assert await _worker(world).run_once()
    assert _counts(pool, world) == [(0, 0)]
    world.transport.send = original
    assert not await _worker(world).run_once()
    world.clock.now += timedelta(seconds=30)
    assert await _worker(world).run_once()
    assert len(world.transport.sent) == 1
    assert _counts(pool, world) == [(1, 0)]

    await _failed(world, 1)
    world.clock.now += timedelta(seconds=120)

    async def ambiguous(payload):
        await original(payload)
        raise ReplyFailed("timeout", outcome_unknown=True)

    world.transport.send = ambiguous
    assert await _worker(world).run_once()
    world.clock.now += timedelta(seconds=120)
    assert not await _worker(world).run_once()
    assert len(world.transport.sent) == 2
    assert _counts(pool, world) == [(1, 1)]


@pytest.mark.asyncio
async def test_new_failure_during_send_stays_pending_for_its_own_wait(pool, users):
    world = await _linked(pool, users)
    await _failed(world, 0)
    world.clock.now += timedelta(seconds=120)
    original = world.transport.send

    async def send_with_arrival(payload):
        await _failed(world, 1)
        await original(payload)

    world.transport.send = send_with_arrival
    assert await _worker(world).run_once()
    world.transport.send = original
    assert not await _worker(world).run_once()
    world.clock.now += timedelta(seconds=120)
    assert await _worker(world).run_once()
    assert len(world.transport.sent) == 2
    assert _counts(pool, world) == [(2, 0)]


@pytest.mark.asyncio
async def test_crash_after_claim_never_replays_an_uncertain_send(pool, users):
    world = await _linked(pool, users)
    await _failed(world, 0)
    world.clock.now += timedelta(seconds=120)
    claimed = world.store.reply_groups.claim(now=world.clock.now, limit=10)
    assert claimed is not None
    assert _counts(pool, world) == [(0, 1)]
    world.clock.now += timedelta(seconds=60)
    assert not await _worker(world).run_once()
    assert world.transport.sent == []
    assert _counts(pool, world) == [(0, 1)]


@pytest.mark.asyncio
async def test_group_enqueue_rolls_back_with_settlement_and_replay_counts_once(
    pool, users, monkeypatch
):
    world = await _linked(pool, users)
    original = world.store.reply_groups.enqueue_on

    def fail_after_enqueue(connection, failure):
        original(connection, failure)
        raise RuntimeError("synthetic_transaction_failure")

    monkeypatch.setattr(world.store.reply_groups, "enqueue_on", fail_after_enqueue)
    with pytest.raises(RuntimeError, match="synthetic_transaction_failure"):
        await _failed(world, 0)
    assert world.record("wamid.GROUP-0").status == "received"
    with pool.connection() as connection:
        assert connection.execute(
            "select count(*) from public.whatsapp_reply_groups where owner_id=%s",
            (world.alice,),
        ).fetchone() == (0,)
    monkeypatch.setattr(world.store.reply_groups, "enqueue_on", original)
    world.clock.now += timedelta(seconds=91)
    await _failed(world, 0)
    await _failed(world, 0)
    world.clock.now += timedelta(seconds=120)
    assert await _worker(world).run_once()
    assert world.transport.bodies() == [
        "No pudimos leer este archivo. Envíalo como foto o PDF."
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("fails_twice", [False, True])
async def test_capture_retry_counts_only_a_second_failure_on_postgres(
    pool, users, fails_twice
):
    from argus.domain.ingestion.whatsapp.intake import CaptureFailed

    world = await _linked(pool, users)
    world.graph.media["700000000000991"] = Media(RECEIPT_PNG, "image/png")
    original = world.intake.destination.capture
    attempts = 0

    async def flaky(**kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1 or fails_twice:
            raise CaptureFailed("whatsapp_capture_failed")
        return await original(**kwargs)

    world.intake.destination.capture = flaky
    await world.deliver(cases.image("700000000000991", "wamid.CAPTURE-RETRY"))
    assert attempts == 2
    assert len(world.transport.sent) == int(not fails_twice)
    world.clock.now += timedelta(seconds=120)
    assert await _worker(world).run_once() == fails_twice
    assert _counts(pool, world) == ([(1, 0)] if fails_twice else [])


@pytest.mark.asyncio
async def test_group_storage_encrypts_transport_identity_and_purges_expired_data(
    pool, users
):
    from loguru import logger

    world = await _linked(pool, users)
    await _failed(world, 0)
    with pool.connection() as connection:
        row = connection.execute(
            "select samples::text from public.whatsapp_reply_groups where owner_id=%s",
            (world.alice,),
        ).fetchone()[0]
    for raw in (cases.ALICE_PHONE, "wamid.GROUP-0", "factura_0.png"):
        assert raw not in row
    world.clock.now += timedelta(seconds=120)
    await _worker(world).run_once()
    records = []
    sink = logger.add(lambda message: records.append(message.record["extra"]))
    try:
        world.clock.now += timedelta(days=8)
        world.store.reply_groups.recover(now=world.clock.now)
    finally:
        logger.remove(sink)
    assert _counts(pool, world) == []
    assert any(
        row.get("event") == "whatsapp_reply_counters_purged" and row["rows"] >= 1
        for row in records
    )


@pytest.mark.asyncio
async def test_retry_keeps_earliest_names_when_new_failures_arrive_during_send(
    pool, users
):
    from argus.domain.ingestion.whatsapp.replies import ReplyFailed

    world = await _linked(pool, users)
    await _failed(world, 0)
    world.clock.now += timedelta(seconds=120)
    original = world.transport.send

    async def rejected_with_arrival(payload):
        await _failed(world, 1)
        raise ReplyFailed("503")

    world.transport.send = rejected_with_arrival
    assert await _worker(world).run_once()
    world.transport.send = original
    world.clock.now += timedelta(seconds=120)
    assert await _worker(world).run_once()
    assert world.transport.bodies() == [
        "No pudimos leer 2 archivos:\n• factura_0.png\n• factura_1.png\nEnvíalos como foto o PDF."
    ]
    assert _counts(pool, world) == [(1, 0)]


@pytest.mark.asyncio
async def test_owner_erasure_cascades_pending_attempt_and_daily_counter(pool, users):
    world = await _linked(pool, users)
    await _failed(world, 0)
    world.clock.now += timedelta(seconds=120)
    assert world.store.reply_groups.claim(now=world.clock.now, limit=10)
    await _failed(world, 1)
    from tests.test_business_account_deletion_postgres import (
        erase_open_owner,
        release_custodian,
    )

    with pool.connection() as connection:
        for table in ("groups", "attempts", "days"):
            assert connection.execute(
                f"select count(*) from public.whatsapp_reply_{table} where owner_id=%s",
                (world.alice,),
            ).fetchone() == (1,)
        space_id = connection.execute(
            "select id::text from public.spaces where current_owner_id=%s",
            (world.alice,),
        ).fetchone()[0]
    outcome = erase_open_owner(pool, world.alice)
    assert outcome.status == "done"
    try:
        with pool.connection() as connection:
            for table in ("groups", "attempts", "days"):
                assert connection.execute(
                    f"select count(*) from public.whatsapp_reply_{table} where owner_id=%s",
                    (world.alice,),
                ).fetchone() == (0,)
    finally:
        release_custodian(space_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", UNLINKED_CASES, ids=lambda case: case.__name__)
async def test_unlinked_case_on_postgres(case, pool, users) -> None:  # noqa: ANN001
    await case(_world(pool, users))


@pytest.mark.asyncio
async def test_final_settlement_cannot_wait_on_a_lock_past_the_processing_budget(
    pool, users, monkeypatch
) -> None:
    world = _world(pool, users)
    await world.link(world.alice, cases.ALICE_PHONE)
    media_id, message_id = "700000000000156", "wamid.CASE-SETTLEMENT-LOCK"
    world.graph.media[media_id] = Media(RECEIPT_PNG, "image/png")
    world.intake.processing_seconds = 1.5
    destination = world.intake.destination
    capture = destination.capture
    locked = asyncio.Event()

    with pool.connection() as blocker, blocker.transaction():

        async def capture_then_lock(**kwargs):
            result = await capture(**kwargs)
            blocker.execute(
                "select 1 from public.whatsapp_inbound_messages "
                "where provider_message_key = %s for update",
                (world.keys.message(message_id),),
            ).fetchone()
            locked.set()
            return result

        monkeypatch.setattr(destination, "capture", capture_then_lock)
        delivery = asyncio.create_task(world.deliver(cases.image(media_id, message_id)))
        await asyncio.wait_for(locked.wait(), timeout=3)
        done, _ = await asyncio.wait({delivery}, timeout=3)

    if not done:
        await delivery
        pytest.fail("settlement outlasted its budget while waiting to lock the claim")
    with pytest.raises(QueryCanceled):
        await delivery
    assert world.record(message_id).status == "received"
    assert len(world.transport.sent) == 1
