"""Real-Postgres proof for Shortcuts device tokens.

Enrollment, intake and disconnect against the migrations, plus what only the
database shows: clients cannot read or write token digests at all, and a
deleted connection takes its digest with it.
"""

import json
from datetime import datetime, timezone

import pytest
from argus.domain.owner_scope import PERSONAL

from tests import test_financial_accounts_postgres as shared
from tests.ingestion.shortcuts_support import RecordingSink

users = shared.users
pytestmark = pytest.mark.skipif(
    not shared.DSN, reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured"
)
psycopg = pytest.importorskip("psycopg")
psycopg_pool = pytest.importorskip("psycopg_pool")


@pytest.fixture
def connector():
    from argus.domain.ingestion.connections_postgres import (
        PostgresConnectionRepository,
    )
    from argus.domain.ingestion.hub import IngestionHub
    from argus.domain.ingestion.shortcuts.connector import ShortcutsConnector
    from argus.domain.ingestion.shortcuts.store import PostgresDeviceTokenStore

    pool = psycopg_pool.ConnectionPool(shared.DSN, min_size=0, max_size=8, open=True)
    hub = IngestionHub(
        PostgresConnectionRepository(pool),
        box=None,
        sink=RecordingSink(),
        clock=lambda: datetime.now(timezone.utc),
    )
    built = ShortcutsConnector(hub, PostgresDeviceTokenStore(pool))
    hub.register(built.adapter)
    try:
        yield built
    finally:
        pool.close()


def _event():
    from argus.domain.ingestion.shortcuts.events import ShortcutEvent

    return ShortcutEvent(
        event_id="pg-1",
        kind="transaction",
        source_app="wallet",
        captured_at=datetime.now(timezone.utc),
        amount="US$ 12.50",
        merchant="Cafe",
    )


def test_enroll_intake_and_disconnect_on_real_postgres(connector, users):
    enrollment = connector.enroll(user_id=users["owner"], device_name="iPhone")
    header = f"Bearer {enrollment.token}"
    connection = connector.authenticate(header)
    assert connection is not None and connection.id == enrollment.connection.id
    assert connector.authenticate(header[:-1] + "x") is None
    first = connector.intake(connection, [_event()])
    again = connector.intake(connection, [_event()])
    assert first[0].receipt_id == again[0].receipt_id
    assert [r.outcome for r in first + again] == ["recorded", "unchanged"]
    refreshed = connector.hub.connections.get(
        user_id=users["owner"], connection_id=connection.id, scope=PERSONAL
    )
    assert refreshed.last_success_at is not None and refreshed.lease_holder is None
    outcome = connector.hub.disconnect(
        user_id=users["owner"], connection_id=connection.id, scope=PERSONAL
    )
    assert outcome.provider_revocation == "revoked"
    assert connector.store.get(connection_id=connection.id) is None
    assert connector.authenticate(header) is None


def test_clients_have_no_access_and_digests_follow_their_connection(connector, users):
    enrollment = connector.enroll(user_id=users["owner"], device_name="iPhone")
    connection_id = enrollment.connection.id
    with psycopg.connect(shared.DSN) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "select token_sha256 from public.financial_shortcut_device_tokens where connection_id = %s",
                (connection_id,),
            )
            stored = bytes(cursor.fetchone()[0])
        assert len(stored) == 32 and enrollment.token.encode() not in stored
        for statement in (
            "select * from public.financial_shortcut_device_tokens",
            "delete from public.financial_shortcut_device_tokens",
            "update public.financial_shortcut_device_tokens set created_at = now()",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with connection.transaction(), connection.cursor() as cursor:
                    cursor.execute("set local role authenticated")
                    cursor.execute(
                        "select set_config('request.jwt.claims', %s, true)",
                        (json.dumps({"sub": users["owner"], "role": "authenticated"}),),
                    )
                    cursor.execute(statement)
        with connection.transaction(), connection.cursor() as cursor:
            cursor.execute(
                "delete from public.financial_source_connections where id = %s",
                (connection_id,),
            )
            cursor.execute(
                "select count(*) from public.financial_shortcut_device_tokens where connection_id = %s",
                (connection_id,),
            )
            assert cursor.fetchone()[0] == 0


def test_concurrent_enrollment_holds_the_device_limit(connector, users):
    import threading

    from argus.domain.ingestion.shortcuts.connector import (
        MAX_LIVE_DEVICES,
        DeviceLimitReached,
    )

    outcomes: list[str] = []
    gate = threading.Barrier(10)

    def attempt(index: int) -> None:
        gate.wait()
        try:
            connector.enroll(user_id=users["owner"], device_name=f"phone {index}")
            outcomes.append("ok")
        except DeviceLimitReached:
            outcomes.append("limit")

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert outcomes.count("ok") == MAX_LIVE_DEVICES
    assert outcomes.count("limit") == 10 - MAX_LIVE_DEVICES
    live = [
        row
        for row in connector.hub.list(user_id=users["owner"], scope=PERSONAL)
        if row.status != "disconnected"
    ]
    assert len(live) == MAX_LIVE_DEVICES
    with psycopg.connect(shared.DSN) as connection, connection.cursor() as cursor:
        cursor.execute(
            "select count(*) from public.financial_shortcut_device_tokens where user_id = %s",
            (users["owner"],),
        )
        assert cursor.fetchone()[0] == MAX_LIVE_DEVICES
