from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from argus.domain.business.spaces import PostgresSpaceStore
from argus.domain.ingestion.whatsapp.business_store import BusinessTurnStore, LeaseLost
from faker import Faker
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from tests import test_financial_accounts_postgres as shared

fake = Faker()
users = shared.users
pytestmark = pytest.mark.skipif(
    not shared.DSN, reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured"
)


@pytest.fixture
def pool():
    with ConnectionPool(shared.DSN, min_size=0, max_size=4) as opened:
        yield opened


@pytest.fixture
def client(pool, users):
    space, _ = PostgresSpaceStore(pool).create(users["owner"], fake.company())
    return UUID(space.id)


def test_two_workers_cannot_hold_one_sender_and_fence_survives_release(pool, client):
    store = BusinessTurnStore(pool)
    sender = fake.sha256()
    holders = [uuid4(), uuid4()]
    with ThreadPoolExecutor(max_workers=2) as workers:
        leases = list(
            workers.map(
                lambda holder: store.acquire(
                    space_id=client,
                    sender_hash=sender,
                    holder=holder,
                    duration=timedelta(seconds=60),
                ),
                holders,
            )
        )
    held = [lease for lease in leases if lease is not None]
    assert len(held) == 1
    first = held[0]
    assert first.fence == 1
    store.release(first)
    second = store.acquire(
        space_id=client,
        sender_hash=sender,
        holder=uuid4(),
        duration=timedelta(seconds=60),
    )
    assert second is not None and second.fence == first.fence + 1
    store.release(first)
    with pool.connection() as connection, connection.transaction():
        store.require_lease(connection, second)
    with pytest.raises(LeaseLost):
        store.renew(first, duration=timedelta(seconds=60))


def test_expired_lease_cannot_renew_and_replacement_uses_database_clock(pool, client):
    store = BusinessTurnStore(pool)
    first = store.acquire(
        space_id=client,
        sender_hash=fake.sha256(),
        holder=uuid4(),
        duration=timedelta(seconds=60),
    )
    with pool.connection() as connection:
        connection.execute(
            "update public.business_sender_leases set lease_until=clock_timestamp()-interval '1 second'"
            " where space_id=%s and sender_hash=%s",
            (client, first.sender_hash),
        )
    with pytest.raises(LeaseLost):
        store.renew(first, duration=timedelta(seconds=60))
    second = store.acquire(
        space_id=client,
        sender_hash=first.sender_hash,
        holder=uuid4(),
        duration=timedelta(seconds=60),
    )
    assert second.fence == first.fence + 1
    renewed = store.renew(second, duration=timedelta(seconds=120))
    assert renewed.holder == second.holder and renewed.fence == second.fence
    assert renewed.lease_until > second.lease_until


def test_sender_leases_are_independent_across_businesses(pool, client, users):
    other, _ = PostgresSpaceStore(pool).create(users["other"], fake.company())
    store = BusinessTurnStore(pool)
    sender = fake.sha256()
    first = store.acquire(
        space_id=client,
        sender_hash=sender,
        holder=uuid4(),
        duration=timedelta(seconds=60),
    )
    second = store.acquire(
        space_id=UUID(other.id),
        sender_hash=sender,
        holder=uuid4(),
        duration=timedelta(seconds=60),
    )
    assert first is not None and second is not None
    with pool.connection() as connection, connection.transaction():
        store.require_lease(connection, first)
        store.require_lease(connection, second)


def test_interrupted_interpretation_becomes_unknown_under_replacement_fence(
    pool, client, users
):
    store = BusinessTurnStore(pool)
    lease = store.acquire(
        space_id=client,
        sender_hash=fake.sha256(),
        holder=uuid4(),
        duration=timedelta(seconds=60),
    )
    key = fake.sha256()
    first = store.start_turn(turn_key=key, actor_id=UUID(users["owner"]), lease=lease)
    assert first.model_state == "running" and first.phase == "turn_running"
    store.release(lease)
    replacement = store.acquire(
        space_id=client,
        sender_hash=lease.sender_hash,
        holder=uuid4(),
        duration=timedelta(seconds=60),
    )
    recovered = store.start_turn(
        turn_key=key, actor_id=UUID(users["owner"]), lease=replacement
    )
    assert recovered.model_state == "unknown"
    assert recovered.lease_fence == replacement.fence
    assert recovered.arrival_sequence == first.arrival_sequence
    with pytest.raises(LeaseLost):
        store.mark_model_unknown(turn_key=key, lease=lease)
    again = store.start_turn(
        turn_key=key, actor_id=UUID(users["owner"]), lease=replacement
    )
    assert again.model_state == "unknown"


def test_turn_identity_cannot_be_reassigned_by_duplicate_message_key(pool, client, users):
    store = BusinessTurnStore(pool)
    lease = store.acquire(
        space_id=client,
        sender_hash=fake.sha256(),
        holder=uuid4(),
        duration=timedelta(seconds=60),
    )
    key = fake.sha256()
    first = store.start_turn(turn_key=key, actor_id=UUID(users["owner"]), lease=lease)
    with pytest.raises(ValueError, match="business_turn_identity_conflict"):
        store.start_turn(turn_key=key, actor_id=UUID(users["other"]), lease=lease)
    assert store.load_turn(key) == first


def test_failure_marks_unknown_without_erasing_an_already_persisted_plan(
    pool, client, users
):
    store = BusinessTurnStore(pool)
    lease = store.acquire(
        space_id=client,
        sender_hash=fake.sha256(),
        holder=uuid4(),
        duration=timedelta(seconds=60),
    )
    key = fake.sha256()
    store.start_turn(turn_key=key, actor_id=UUID(users["owner"]), lease=lease)

    actor = {
        "actor_id": users["owner"],
        "actor_kind": "owner_via_agent",
        "display_name": "Synthetic owner",
        "grant_id": str(uuid4()),
        "issuer_id": users["owner"],
        "issuer_display_name": "Synthetic owner",
    }
    plan = {"schema_version": 1, "actions": []}
    with pool.connection() as connection:
        connection.execute(
            "update public.business_turns set plan=%s,plan_actor=%s,model_state='completed'"
            " where turn_key=%s",
            (Jsonb(plan), Jsonb(actor), key),
        )
    store.mark_model_unknown(turn_key=key, lease=lease)
    recovered = store.start_turn(turn_key=key, actor_id=UUID(users["owner"]), lease=lease)
    assert recovered.model_state == "completed"
    assert recovered.plan.model_dump(mode="json") == plan
    assert str(recovered.plan_actor.grant_id) == actor["grant_id"]


def test_lease_expiring_while_waiting_for_row_lock_is_rejected(pool, client):
    import time
    from threading import Event

    store = BusinessTurnStore(pool)
    lease = store.acquire(
        space_id=client,
        sender_hash=fake.sha256(),
        holder=uuid4(),
        duration=timedelta(seconds=60),
    )
    waiting = Event()

    def wait_for_lease():
        with pool.connection() as other, other.transaction():
            waiting.set()
            store.require_lease(other, lease)

    with ThreadPoolExecutor(max_workers=1) as worker:
        with pool.connection() as connection, connection.transaction():
            connection.execute(
                "update public.business_sender_leases set lease_until=clock_timestamp()+interval '100 milliseconds'"
                " where space_id=%s and sender_hash=%s",
                (client, lease.sender_hash),
            )
            blocked = worker.submit(wait_for_lease)
            assert waiting.wait(timeout=1)
            time.sleep(0.15)
        with pytest.raises(LeaseLost):
            blocked.result(timeout=1)
