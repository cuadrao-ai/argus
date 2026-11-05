"""Gmail against the real tables: sender allowlist, lease and cursor CAS.

Google is scripted (no network); the repositories are
``PostgresConnectionRepository`` on the wave-0 migration and
``PostgresSenderRepository`` on the Gmail senders migration, so ownership,
row-level security, the lease and the compare-and-set cursor advance are
decided by the database.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from argus.domain.ingestion.connections import ConnectionNotFound
from argus.domain.owner_scope import PERSONAL

from tests import test_financial_accounts_postgres as shared
from tests.ingestion.gmail_fakes import FakeGoogle, RecordingSink, connect, make_connector
from tests.ingestion.gmail_mailbox import alert_es, standard_mailbox

users = shared.users
pytestmark = pytest.mark.skipif(
    not shared.DSN, reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured"
)
psycopg = pytest.importorskip("psycopg")
psycopg_pool = pytest.importorskip("psycopg_pool")


@pytest.fixture
def pool():
    opened = psycopg_pool.ConnectionPool(shared.DSN, min_size=0, max_size=8, open=True)
    try:
        yield opened
    finally:
        opened.close()


def postgres_connector(pool, fake, sink):  # noqa: ANN001
    from argus.domain.ingestion.connections_postgres import (
        PostgresConnectionRepository,
    )
    from argus.domain.ingestion.gmail.senders_postgres import PostgresSenderRepository

    return make_connector(
        fake,
        sink=sink,
        repo=PostgresConnectionRepository(pool),
        senders=PostgresSenderRepository(pool),
    )


def test_connect_sync_increment_reconnect_and_disconnect(pool, users):  # noqa: ANN001
    owner = users["owner"]
    fake = FakeGoogle(mails=standard_mailbox())
    sink = RecordingSink()
    connector = postgres_connector(pool, fake, sink)
    repo, senders = connector.hub.connections, connector.senders
    row = connect(connector, fake, owner).connection
    # The sealing key's fingerprint round-trips through the table (Priya B1).
    key_id = connector.hub.box.key_id
    assert (
        repo.get(user_id=owner, connection_id=row.id, scope=PERSONAL).secret_key == key_id
    )
    assert [r.sender for r in senders.list(connection_id=row.id)] == [
        "alerts@card-example.test",
        "banco-ejemplo.test",
    ]
    assert connector.sync(row).candidates == 6
    synced = repo.get(user_id=owner, connection_id=row.id, scope=PERSONAL)
    assert synced.cursor == "1000" and synced.lease_holder is None
    assert all(r.backfilled_at for r in senders.list(connection_id=row.id))
    fake.deliver(alert_es("a0600", days_ago=0))
    assert connector.sync(synced).mode == "incremental"
    assert repo.get(user_id=owner, connection_id=row.id, scope=PERSONAL).cursor == "1001"

    fake.revoked.update(fake.refresh_tokens)
    assert connector.sync(synced).error_code == "gmail_token_revoked"
    failed = repo.get(user_id=owner, connection_id=row.id, scope=PERSONAL)
    assert failed.status == "needs_reauth" and failed.cursor == "1001"
    again = connect(connector, fake, owner, senders=None)
    assert not again.created and again.connection.id == row.id
    assert again.connection.status == "active" and again.connection.cursor == "1001"
    assert (
        repo.get(user_id=owner, connection_id=row.id, scope=PERSONAL).secret_key == key_id
    )
    assert len(repo.list(user_id=owner, scope=PERSONAL)) == 1

    outcome = connector.hub.disconnect(
        user_id=owner, connection_id=row.id, scope=PERSONAL
    )
    assert outcome.provider_revocation == "revoked"
    ended = repo.get(user_id=owner, connection_id=row.id, scope=PERSONAL)
    assert ended.secret is None and ended.secret_key is None
    assert senders.list(connection_id=row.id) == []
    with pytest.raises(ConnectionNotFound):
        senders.replace(
            user_id=owner, connection_id=row.id, senders=("x.test",), now=fake.clock()
        )


def test_two_people_cannot_both_hold_a_live_mailbox(pool, users, monkeypatch):  # noqa: ANN001
    from argus.domain.ingestion.gmail.oauth import MailboxOwnedElsewhere

    fake = FakeGoogle()
    connector = postgres_connector(pool, fake, RecordingSink())
    owner = connect(connector, fake, users["owner"]).connection
    # The other person's callback read no live row before the owner's insert
    # committed; the database's global live-reference index decides.
    monkeypatch.setattr(connector.hub.connections, "find_live", lambda **_: [])
    with pytest.raises(MailboxOwnedElsewhere):
        connect(connector, fake, users["other"])
    assert connector.hub.connections.list(user_id=users["other"], scope=PERSONAL) == []
    assert connector.hub.credential(owner) not in fake.revoked


def test_senders_attach_only_to_the_owners_live_gmail_connection(pool, users):  # noqa: ANN001
    fake = FakeGoogle()
    connector = postgres_connector(pool, fake, RecordingSink())
    row = connect(connector, fake, users["owner"]).connection
    with pytest.raises(ConnectionNotFound):
        connector.senders.replace(
            user_id=users["other"], connection_id=row.id, senders=("x.test",),
            now=fake.clock(),
        )  # fmt: skip
    kept = connector.senders.replace(
        user_id=users["owner"], connection_id=row.id,
        senders=("banco-ejemplo.test", "new.test"), now=fake.clock(),
    )  # fmt: skip
    assert [r.sender for r in kept] == ["banco-ejemplo.test", "new.test"]


def test_clients_read_their_own_senders_and_never_write(pool, users):  # noqa: ANN001
    fake = FakeGoogle()
    connector = postgres_connector(pool, fake, RecordingSink())
    row = connect(connector, fake, users["owner"]).connection

    def as_user(cursor, user_id, anonymous=False):  # noqa: ANN001
        cursor.execute("set local role authenticated")
        cursor.execute(
            "select set_config('request.jwt.claims', %s, true)",
            (json.dumps({"sub": user_id, "role": "authenticated",
                         "is_anonymous": anonymous}),),
        )  # fmt: skip

    table = "public.financial_source_gmail_senders"
    with psycopg.connect(shared.DSN) as connection:
        for user, anonymous, expected in (
            (users["owner"], False, 2),
            (users["other"], False, 0),
            (users["owner"], True, 0),
        ):
            with connection.transaction(), connection.cursor() as cursor:
                as_user(cursor, user, anonymous)
                cursor.execute(
                    f"select count(*) from {table} where connection_id = %s", (row.id,)
                )
                assert cursor.fetchone()[0] == expected
        for statement in (
            f"insert into {table} (connection_id, user_id, sender) "
            f"values ('{row.id}', '{users['owner']}', 'evil.test')",
            f"update {table} set sender = 'evil.test'",
            f"delete from {table}",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with connection.transaction(), connection.cursor() as cursor:
                    as_user(cursor, users["owner"])
                    cursor.execute(statement)
        with pytest.raises(psycopg.errors.CheckViolation):
            with connection.transaction(), connection.cursor() as cursor:
                cursor.execute(
                    f"insert into {table} (connection_id, user_id, sender) "
                    "values (%s, %s, 'Has Space.test')",
                    (row.id, users["owner"]),
                )


def test_concurrent_syncs_advance_the_cursor_once(pool, users):  # noqa: ANN001
    owner = users["owner"]
    barrier = Barrier(2)

    class SlowFake(FakeGoogle):
        slowed = True

        def __call__(self, request):  # noqa: ANN001
            if request.url.path.endswith("/profile") and not self.slowed:
                self.slowed = True
                barrier.wait(timeout=10)
            return super().__call__(request)

    fake = SlowFake(mails=standard_mailbox())
    sink = RecordingSink()
    connector = postgres_connector(pool, fake, sink)
    row = connect(connector, fake, owner).connection
    fake.slowed = False

    def guarded(_):  # noqa: ANN001
        # Two workers, one connection: the database lease admits one.
        outcome = connector.sync(row)
        if outcome.status == "busy":
            barrier.wait(timeout=10)
        return outcome.status

    with ThreadPoolExecutor(2) as threads:
        statuses = sorted(threads.map(guarded, [1, 2]))
    assert statuses == ["busy", "synced"]
    assert len(sink.batches) == 1
    stored = connector.hub.connections.get(
        user_id=owner, connection_id=row.id, scope=PERSONAL
    )
    assert stored.cursor == "1000" and stored.lease_holder is None
