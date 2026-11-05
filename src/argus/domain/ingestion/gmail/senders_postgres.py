"""Postgres twin of ``InMemorySenderRepository``.

``replace`` runs in one transaction and inserts only through the owning, live
connection row, so a sender can never be attached to someone else's or an
ended connection even if a caller skipped its own check.
"""

from __future__ import annotations

from datetime import datetime

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from argus.domain.ingestion.connections import ConnectionNotFound
from argus.domain.ingestion.gmail.senders import SenderRule

_TABLE = "public.financial_source_gmail_senders"


class PostgresSenderRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def list(self, *, connection_id: str) -> list[SenderRule]:
        with self._pool.connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    f"""select sender, created_at, backfilled_at from {_TABLE}
                    where connection_id = %s::uuid order by sender""",
                    (connection_id,),
                )
                return [SenderRule(**row) for row in cursor.fetchall()]

    def replace(
        self, *, user_id: str, connection_id: str, senders: tuple[str, ...], now: datetime
    ) -> list[SenderRule]:
        with self._pool.connection() as connection:
            with connection.transaction(), connection.cursor() as cursor:
                cursor.execute(
                    """select 1 from public.financial_source_connections
                    where id = %s::uuid and user_id = %s and source = 'gmail'
                      and status <> 'disconnected'
                    for update""",
                    (connection_id, user_id),
                )
                if cursor.fetchone() is None:
                    raise ConnectionNotFound()
                cursor.execute(
                    f"""delete from {_TABLE}
                    where connection_id = %s::uuid and not (sender = any(%s::text[]))""",
                    (connection_id, list(senders)),
                )
                cursor.execute(
                    f"""insert into {_TABLE} (connection_id, user_id, sender, created_at)
                    select %s::uuid, %s, value, %s from unnest(%s::text[]) as value
                    on conflict (connection_id, sender) do nothing""",
                    (connection_id, user_id, now, list(senders)),
                )
        return self.list(connection_id=connection_id)

    def mark_backfilled(
        self, *, connection_id: str, senders: tuple[str, ...], now: datetime
    ) -> None:
        with self._pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""update {_TABLE} set backfilled_at = %s
                    where connection_id = %s::uuid and sender = any(%s::text[])
                      and backfilled_at is null""",
                    (now, connection_id, list(senders)),
                )

    def delete(self, *, connection_id: str) -> None:
        with self._pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"delete from {_TABLE} where connection_id = %s::uuid",
                    (connection_id,),
                )
