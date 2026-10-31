"""The WhatsApp replay, linking and isolation cases on real Postgres."""

import asyncio
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from argus.domain.business.spaces import PostgresSpaceStore
from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository
from argus.domain.ingestion.documents.service import DocumentsService
from argus.domain.ingestion.documents.store_postgres import PostgresDocumentStore
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.whatsapp.reply_worker import FailureReplyWorker
from argus.domain.ingestion.whatsapp.store_postgres import PostgresWhatsAppStore
from psycopg_pool import ConnectionPool

from tests import test_financial_accounts_postgres as shared
from tests.document_sources_support import source_objects
from tests.ingestion import whatsapp_cases as cases
from tests.ingestion import whatsapp_heartbeat_cases as heartbeat
from tests.ingestion import whatsapp_lease_cases as lease
from tests.ingestion import whatsapp_recovery_cases as recovery
from tests.ingestion.whatsapp_support import (
    RECEIPT_PNG,
    Media,
    RefusingExtractor,
    fixture,
)
from tests.ingestion.whatsapp_unlinked_cases import UNLINKED_CASES

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
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("case", cases.CASES, ids=lambda case: case.__name__)
async def test_intake_case_on_postgres(case, pool, users) -> None:  # noqa: ANN001
    await case(_world(pool, users))


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
    recovery.RECOVERY_CASES + lease.LEASE_CASES + heartbeat.HEARTBEAT_CASES,
    ids=lambda case: case.__name__,
)
async def test_recovery_case_on_postgres(case, pool, users) -> None:  # noqa: ANN001
    await case(_world(pool, users))


# The settlement statement of the code before 20261031010000, verbatim: it
# never names claim_envelope, so a rollout or a code-only rollback runs it
# against sealed rows.
_PRE_ENVELOPE_SETTLE = (
    "update public.whatsapp_inbound_messages set status = %s, "
    "destination_owner_id = %s, connection_id = %s, error_code = %s, "
    "claim_until = null, updated_at = %s "
    "where provider_message_key = %s and status in ('received', 'failed') "
    "and claim_until is not distinct from %s"
)
_SEALED = b"\x01" + b"x" * 40


@pytest.mark.parametrize("status", ["received", "rejected", "failed"])
def test_pre_envelope_code_settles_a_sealed_claim_and_clears_it(pool, status) -> None:  # noqa: ANN001
    import os

    key, now = os.urandom(32), cases.Clock()()
    held = now + timedelta(seconds=90)
    with pool.connection() as connection:
        connection.execute(
            "insert into public.whatsapp_inbound_messages "
            "(provider_message_key, sender_hash, status, claim_until, received_at, "
            "updated_at, claim_envelope) values (%s, %s, 'received', %s, %s, %s, %s)",
            (key, b"s" * 32, held, now, now, _SEALED),
        )
        settled = connection.execute(
            _PRE_ENVELOPE_SETTLE, (status, None, None, None, now, key, held)
        )
        row = connection.execute(
            "select status, claim_envelope from public.whatsapp_inbound_messages "
            "where provider_message_key = %s",
            (key,),
        ).fetchone()
    assert settled.rowcount == 1
    assert row == (status, None)


def test_a_settled_row_never_keeps_a_claim_envelope(pool) -> None:  # noqa: ANN001
    import os

    import psycopg

    key = os.urandom(32)
    with pool.connection() as connection:
        connection.execute(
            "insert into public.whatsapp_inbound_messages "
            "(provider_message_key, sender_hash, status, received_at, updated_at, "
            "claim_envelope) values (%s, %s, 'rejected', now(), now(), %s)",
            (key, b"s" * 32, _SEALED),
        )
        assert connection.execute(
            "select claim_envelope from public.whatsapp_inbound_messages "
            "where provider_message_key = %s",
            (key,),
        ).fetchone() == (None,)
    with pool.connection() as connection, pytest.raises(psycopg.errors.CheckViolation):
        connection.execute(
            "insert into public.whatsapp_inbound_messages "
            "(provider_message_key, sender_hash, status, claim_until, received_at, "
            "updated_at, claim_envelope) values (%s, %s, 'received', now(), now(), "
            "now(), %s)",
            (os.urandom(32), b"s" * 32, b"\x02" + b"x" * 40),
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
    assert not await _worker(world).run_once()
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
        await _worker(world).run_once()
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
