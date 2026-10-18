"""Atomic daily allowance and lease fencing on the coordinator's disposable PG."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from argus.domain.ingestion.documents.config import SOURCE_MAX_BYTES
from argus.domain.ingestion.email_intake.budget import DailyEmailBudget, EmailBudgetWait
from argus.domain.ingestion.email_intake.store import LeaseLost

from tests import test_business_email_intake_postgres as shared

actions = shared.actions
users = shared.users
rig = shared.rig
pytestmark = shared.pytestmark


def usage(rig):
    with rig["pool"].connection() as db:
        return db.execute(
            "select messages,bytes_used from public.business_email_daily_usage where route_id=%s",
            (rig["route"].id,),
        ).fetchone()


def enqueue(rig, external_id=None):
    delivery = rig["runtime"].enqueue_resend(
        external_id or str(uuid4()), (rig["route"].recipient,)
    )
    if delivery.route_id and delivery.state != "rejected":
        delivery = rig["store"].gate_unauthorized(delivery)
    return delivery


def test_concurrent_last_message_slot_keeps_other_delivery_pending(rig):
    rig["store"].budget = DailyEmailBudget(1, 100 * SOURCE_MAX_BYTES)
    barrier = Barrier(2)

    def call(_):
        barrier.wait()
        return enqueue(rig)

    with ThreadPoolExecutor(max_workers=2) as threads:
        results = list(threads.map(call, range(2)))
    assert sorted(d.error_code or "admitted" for d in results) == [
        "admitted",
        "email_daily_message_budget",
    ]
    waiting = next(d for d in results if d.error_code)
    assert waiting.state == "received"
    assert rig["store"].claim(delivery_id=waiting.id) is None
    assert usage(rig) == (1, 0)


def test_concurrent_exact_webhook_replay_charges_once(rig):
    external_id = str(uuid4())
    barrier = Barrier(2)

    def call(_):
        barrier.wait()
        return enqueue(rig, external_id)

    with ThreadPoolExecutor(max_workers=2) as threads:
        rows = list(threads.map(call, range(2)))
    assert rows[0].id == rows[1].id
    assert usage(rig) == (1, 0)


def test_concurrent_last_byte_reservation_has_one_winner(rig):
    store = rig["store"]
    store.budget = DailyEmailBudget(100, SOURCE_MAX_BYTES)
    deliveries = [store.claim(delivery_id=enqueue(rig).id) for _ in range(2)]
    barrier = Barrier(2)

    def reserve(delivery):
        barrier.wait()
        try:
            return store.reserve_fetch(delivery)
        except EmailBudgetWait as error:
            store.defer_budget(delivery, error.code)
            return error.code

    with ThreadPoolExecutor(max_workers=2) as threads:
        outcomes = list(threads.map(reserve, deliveries))
    assert sum(o == "email_daily_byte_budget" for o in outcomes) == 1
    assert usage(rig) == (2, SOURCE_MAX_BYTES)
    waiting = store.get(
        deliveries[outcomes.index("email_daily_byte_budget")].id, rig["route"].space_id
    )
    assert (waiting.state, waiting.attempts) == ("received", 0)


def test_lease_reclaim_keeps_uncertain_bytes_and_fences_old_refund(rig):
    store = rig["store"]
    delivery = enqueue(rig)
    old = store.claim(delivery_id=delivery.id)
    reservation = store.reserve_fetch(old)
    with rig["pool"].connection() as db:
        db.execute(
            "update public.business_email_deliveries set lease_until=now()-interval '1 second' where id=%s",
            (delivery.id,),
        )
    new = store.claim(delivery_id=delivery.id)
    fresh = store.reserve_fetch(new)
    with pytest.raises(LeaseLost):
        store.settle_fetch(old, reservation, 0)
    store.settle_fetch(new, fresh, 43)
    with pytest.raises(LeaseLost):
        store.settle_fetch(new, fresh, 0)
    assert usage(rig) == (2, SOURCE_MAX_BYTES + 43)


def test_usage_is_private_and_route_deletion_cascades(rig):
    enqueue(rig)
    with rig["pool"].connection() as db:
        with db.transaction():
            db.execute("set local role authenticated")
            with pytest.raises(shared.psycopg.errors.InsufficientPrivilege):
                with db.transaction():
                    db.execute("select * from public.business_email_daily_usage")
        db.execute(
            "delete from public.business_email_routes where id=%s", (rig["route"].id,)
        )
    assert usage(rig) is None


def test_metadata_and_raw_share_one_attempt_but_settle_each_fetch(rig):
    store = rig["store"]
    held = store.claim(delivery_id=enqueue(rig).id)
    metadata = store.reserve_fetch(held)
    store.settle_fetch(held, metadata, 139)
    raw = store.reserve_fetch(held)
    store.settle_fetch(held, raw, 371)
    assert usage(rig) == (1, 510)
