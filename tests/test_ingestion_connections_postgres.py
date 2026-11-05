"""Real-Postgres proof for connected-source state.

Runs the same specification as the in-memory twin against the migration, plus
what only the database can show: the disconnected-row check constraint and that
clients can read their own non-secret columns but never the credential envelope
or write anything.
"""

import json

import pytest

from tests import test_financial_accounts_postgres as shared
from tests.ingestion.connection_cases import *  # noqa: F403
from tests.ingestion.connection_cases import NOW, make

users = shared.users
pytestmark = pytest.mark.skipif(
    not shared.DSN, reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured"
)
psycopg = pytest.importorskip("psycopg")
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


def _as(cursor, user_id: str, anonymous: bool = False) -> None:  # noqa: ANN001
    cursor.execute("set local role authenticated")
    cursor.execute(
        "select set_config('request.jwt.claims', %s, true)",
        (
            json.dumps(
                {"sub": user_id, "role": "authenticated", "is_anonymous": anonymous}
            ),
        ),
    )


def test_clients_read_own_status_but_never_credentials_or_writes(repo, users):
    row = make(repo, users["owner"])
    with psycopg.connect(shared.DSN) as connection:
        with connection.transaction(), connection.cursor() as cursor:
            _as(cursor, users["owner"])
            cursor.execute(
                "select status, label from public.financial_source_connections where id = %s",
                (row.id,),
            )
            assert cursor.fetchall() == [("active", "Chase")]
        with connection.transaction(), connection.cursor() as cursor:
            _as(cursor, users["other"])
            cursor.execute(
                "select count(*) from public.financial_source_connections where id = %s",
                (row.id,),
            )
            assert cursor.fetchone()[0] == 0
        with connection.transaction(), connection.cursor() as cursor:
            _as(cursor, users["owner"], anonymous=True)
            cursor.execute(
                "select count(*) from public.financial_source_connections where id = %s",
                (row.id,),
            )
            assert cursor.fetchone()[0] == 0
        for statement in (
            "select secret_ciphertext from public.financial_source_connections",
            "select sync_cursor from public.financial_source_connections",
            "update public.financial_source_connections set status = 'active'",
            "delete from public.financial_source_connections",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with connection.transaction(), connection.cursor() as cursor:
                    _as(cursor, users["owner"])
                    cursor.execute(statement)


def test_disconnected_row_cannot_keep_a_credential(repo, users):
    row = make(repo, users["owner"])
    repo.disconnect(user_id=users["owner"], connection_id=row.id, now=NOW)
    with psycopg.connect(shared.DSN) as connection:
        with pytest.raises(psycopg.errors.CheckViolation):
            with connection.transaction(), connection.cursor() as cursor:
                cursor.execute(
                    "update public.financial_source_connections set secret_ciphertext = 'x' where id = %s",
                    (row.id,),
                )
