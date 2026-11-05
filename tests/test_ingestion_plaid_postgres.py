"""Plaid sync against the real connection table: lease and cursor CAS.

The provider is scripted (no network); the repository is
``PostgresConnectionRepository`` on the wave-0 migration, so the lease and the
compare-and-set cursor advance are decided by the database.
"""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import httpx
import pytest
from argus.domain.ingestion.plaid.config import PlaidConfig
from argus.domain.ingestion.plaid.connector import PlaidConnector
from argus.domain.ingestion.plaid.link import PlaidItemOwnedElsewhere
from argus.domain.owner_scope import PERSONAL

from tests import test_financial_accounts_postgres as shared
from tests.ingestion.plaid_fakes import (
    ACCESS_TOKEN,
    PUBLIC_TOKEN,
    FakePlaid,
    RecordingSink,
    make_connector,
    page,
    txn,
)
from tests.ingestion.test_plaid_sync_safety import (
    HookedFake,
    failure_just_before_renewal,
    webhook_login_required,
)

users = shared.users
pytestmark = pytest.mark.skipif(
    not shared.DSN, reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured"
)
psycopg_pool = pytest.importorskip("psycopg_pool")


@pytest.fixture
def repo():
    from argus.domain.ingestion.connections_postgres import (
        PostgresConnectionRepository,
    )

    pool = psycopg_pool.ConnectionPool(shared.DSN, min_size=0, max_size=8, open=True)
    try:
        yield PostgresConnectionRepository(pool)
    finally:
        pool.close()


def test_exchange_sync_and_resync_on_postgres(repo, users):  # noqa: ANN001
    owner = users["owner"]
    fake = FakePlaid(
        sync={
            None: [page(added=[txn("t1", 4.5)], next_cursor="c1", has_more=True)],
            "c1": [page(added=[txn("t2", -20)], next_cursor="c2")],
            "c2": [page(next_cursor="c2")],
        }
    )
    sink = RecordingSink()
    connector = make_connector(fake, sink=sink, repo=repo)
    first = connector.link.exchange(user_id=owner, public_token=PUBLIC_TOKEN)
    again = connector.link.exchange(user_id=owner, public_token=PUBLIC_TOKEN)
    assert first.created and not again.created
    assert again.connection.id == first.connection.id
    assert connector.hub.credential(first.connection) == ACCESS_TOKEN
    assert connector.sync(first.connection).status == "synced"
    row = repo.get(user_id=owner, connection_id=first.connection.id, scope=PERSONAL)
    assert row.cursor == "c2" and row.lease_holder is None
    # The sealing key's fingerprint round-trips through the table (Priya B1).
    assert row.secret_key == connector.hub.box.key_id
    assert connector.sync(row).added == 0
    fake.item_error = "ITEM_LOGIN_REQUIRED"
    assert connector.sync(row).error_code == "plaid_item_login_required"
    failed = repo.get(user_id=owner, connection_id=row.id, scope=PERSONAL)
    assert failed.status == "needs_reauth"
    assert failed.cursor == "c2" and failed.last_success_at == row.last_success_at
    fake.item_error = None
    restored = connector.link.reconnected(user_id=owner, connection_id=row.id)
    assert restored.status == "active" and restored.cursor == "c2"
    # Consent expiring: attention survives a successful sync, update mode clears it.
    connector.webhooks.plan(
        {
            "webhook_type": "ITEM",
            "webhook_code": "PENDING_EXPIRATION",
            "item_id": restored.external_ref,
            "environment": "sandbox",
        }
    )
    assert connector.sync(restored).status == "synced"
    warned = repo.get(user_id=owner, connection_id=row.id, scope=PERSONAL)
    assert (warned.status, warned.attention_code) == (
        "active",
        "plaid_pending_expiration",
    )
    cleared = connector.link.reconnected(user_id=owner, connection_id=row.id)
    assert cleared.attention_code is None and cleared.attention_at is None
    outcome = connector.hub.disconnect(
        user_id=owner, connection_id=row.id, scope=PERSONAL
    )
    assert outcome.provider_revocation == "revoked"
    assert repo.get(user_id=owner, connection_id=row.id, scope=PERSONAL).secret is None


def test_concurrent_syncs_advance_the_cursor_once(repo, users):  # noqa: ANN001
    owner = users["owner"]
    barrier = Barrier(2)

    class SlowFake(FakePlaid):
        def _transactions_sync(self, body):  # noqa: ANN001
            barrier.wait(timeout=10)
            return super()._transactions_sync(body)

    fake = SlowFake(sync={None: [page(added=[txn("t1", 4.5)], next_cursor="c1")]})
    sink = RecordingSink()
    first = make_connector(fake, sink=sink, repo=repo)
    row = first.link.exchange(user_id=owner, public_token=PUBLIC_TOKEN).connection
    second = PlaidConnector(
        first.hub,
        PlaidConfig(client_id="client-id", secret="plaid-secret-value"),
        transport=httpx.MockTransport(fake),
    )

    def guarded(connector):  # noqa: ANN001
        outcome = connector.sync(row)
        if outcome.status == "busy":
            barrier.wait(timeout=10)
        return outcome.status

    with ThreadPoolExecutor(2) as pool:
        statuses = sorted(pool.map(guarded, [first, second]))
    assert statuses == ["busy", "synced"]
    assert len(sink.batches) == 1
    stored = repo.get(user_id=owner, connection_id=row.id, scope=PERSONAL)
    assert stored.cursor == "c1" and stored.lease_holder is None
    # A stale writer (cursor moved underneath it) cannot advance it again.
    assert repo.lease(connection_id=row.id, holder="late", now=first.hub.clock())
    assert not repo.record_success(
        connection_id=row.id,
        holder="late",
        expected_cursor=None,
        cursor="c-stale",
        now=first.hub.clock(),
    )
    repo.release(connection_id=row.id, holder="late")
    assert repo.get(user_id=owner, connection_id=row.id, scope=PERSONAL).cursor == "c1"


def test_webhook_needs_reauth_mid_sync_wins_on_postgres(repo, users):  # noqa: ANN001
    owner = users["owner"]
    fake = HookedFake(
        sync={
            None: [page(added=[txn("t1", 1)], next_cursor="c1", has_more=True)],
            "c1": [page(added=[txn("t2", 2)], next_cursor="c2")],
        }
    )
    sink = RecordingSink()
    connector = make_connector(fake, sink=sink, repo=repo)
    row = connector.link.exchange(user_id=owner, public_token=PUBLIC_TOKEN).connection
    fake.hook = webhook_login_required(connector, row)
    assert connector.sync(row).status == "superseded"
    after = repo.get(user_id=owner, connection_id=row.id, scope=PERSONAL)
    assert (after.status, after.cursor, after.lease_holder) == (
        "needs_reauth",
        None,
        None,
    )
    assert sink.batches == []


def test_an_item_held_by_another_person_is_refused_and_kept(repo, users):  # noqa: ANN001
    fake = FakePlaid()
    connector = make_connector(fake, repo=repo)
    connector.link.exchange(user_id=users["other"], public_token=PUBLIC_TOKEN)
    # Skip the pre-check so the database's global index decides the race.
    connector.hub.connections.find_live = lambda **kwargs: []
    with pytest.raises(PlaidItemOwnedElsewhere):
        connector.link.exchange(user_id=users["owner"], public_token=PUBLIC_TOKEN)
    assert fake.paths().count("/item/remove") == 0


def test_failure_between_pages_cannot_be_undone_by_renewal_on_postgres(repo, users):  # noqa: ANN001
    owner = users["owner"]
    fake = FakePlaid(
        sync={
            None: [page(added=[txn("t1", 1)], next_cursor="c1", has_more=True)],
            "c1": [page(added=[txn("t2", 2)], next_cursor="c2")],
        }
    )
    sink = RecordingSink()
    connector = make_connector(fake, sink=sink, repo=repo)
    row = connector.link.exchange(user_id=owner, public_token=PUBLIC_TOKEN).connection
    calls = failure_just_before_renewal(connector, row)
    outcome = connector.sync(row)
    assert len(calls) == 2 and outcome.status == "superseded"
    after = repo.get(user_id=owner, connection_id=row.id, scope=PERSONAL)
    assert (after.status, after.cursor, after.lease_holder) == (
        "needs_reauth",
        None,
        None,
    )
    assert sink.batches == []
