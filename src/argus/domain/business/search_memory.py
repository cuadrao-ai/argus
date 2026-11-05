"""A member's Business search memory: recent searches and the records opened.

Kept per member and per Business. Recents are the member's newest distinct
searches, one per folded query. An open counts each time the member opens a
record from a result; opened records rank first in their next searches.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from threading import Lock
from typing import Protocol
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from argus.domain.business.search import SearchKind
from argus.domain.financial_search import query_text

RECENTS = 10
OPENS = 200


@dataclass(frozen=True)
class Recent:
    id: str
    q: str
    searched_at: datetime


@dataclass(frozen=True)
class Opened:
    count: int
    last_opened_at: datetime


Opens = Mapping[tuple[str, str], Opened]


class SearchMemory(Protocol):
    def recents(self, space_id: str, user_id: str) -> list[Recent]: ...

    def remember(self, space_id: str, user_id: str, q: str) -> Recent: ...

    def forget(self, space_id: str, user_id: str, recent_id: str) -> bool: ...

    def forget_all(self, space_id: str, user_id: str) -> None: ...

    def open(
        self, space_id: str, user_id: str, kind: SearchKind, record_id: str
    ) -> None: ...

    def opens(self, space_id: str, user_id: str) -> Opens: ...


class PostgresSearchMemory:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    def recents(self, space_id: str, user_id: str) -> list[Recent]:
        with self.pool.connection() as connection:
            rows = connection.execute(
                "select id::text, query, searched_at from public.business_search_recents"
                " where space_id=%s and user_id=%s order by searched_at desc, id",
                (space_id, user_id),
            ).fetchall()
        return [Recent(*row) for row in rows]

    def remember(self, space_id: str, user_id: str, q: str) -> Recent:
        with self.pool.connection() as connection, connection.transaction():
            row = connection.execute(
                "insert into public.business_search_recents"
                " (space_id, user_id, query, query_key) values (%s, %s, %s, %s)"
                " on conflict (space_id, user_id, query_key) do update"
                " set query=excluded.query, searched_at=clock_timestamp()"
                " returning id::text, query, searched_at",
                (space_id, user_id, q, query_text(q)),
            ).fetchone()
            connection.execute(
                "delete from public.business_search_recents"
                " where space_id=%s and user_id=%s and id not in ("
                " select id from public.business_search_recents"
                " where space_id=%s and user_id=%s"
                " order by searched_at desc, id limit %s)",
                (space_id, user_id, space_id, user_id, RECENTS),
            )
        return Recent(*row)

    def forget(self, space_id: str, user_id: str, recent_id: str) -> bool:
        with self.pool.connection() as connection:
            deleted = connection.execute(
                "delete from public.business_search_recents"
                " where space_id=%s and user_id=%s and id=%s",
                (space_id, user_id, recent_id),
            )
        return deleted.rowcount == 1

    def forget_all(self, space_id: str, user_id: str) -> None:
        with self.pool.connection() as connection:
            connection.execute(
                "delete from public.business_search_recents"
                " where space_id=%s and user_id=%s",
                (space_id, user_id),
            )

    def open(self, space_id: str, user_id: str, kind: SearchKind, record_id: str) -> None:
        with self.pool.connection() as connection, connection.transaction():
            connection.execute(
                "insert into public.business_search_opens"
                " (space_id, user_id, kind, record_id) values (%s, %s, %s, %s)"
                " on conflict (space_id, user_id, kind, record_id) do update"
                " set opened_count=business_search_opens.opened_count + 1,"
                " last_opened_at=clock_timestamp()",
                (space_id, user_id, kind, record_id),
            )
            connection.execute(
                "delete from public.business_search_opens o"
                " where o.space_id=%s and o.user_id=%s and (o.kind, o.record_id) not in ("
                " select kind, record_id from public.business_search_opens"
                " where space_id=%s and user_id=%s"
                " order by last_opened_at desc, kind, record_id limit %s)",
                (space_id, user_id, space_id, user_id, OPENS),
            )

    def opens(self, space_id: str, user_id: str) -> Opens:
        with (
            self.pool.connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            rows = cursor.execute(
                "select kind, record_id::text, opened_count, last_opened_at"
                " from public.business_search_opens where space_id=%s and user_id=%s",
                (space_id, user_id),
            ).fetchall()
        return {
            (row["kind"], row["record_id"]): Opened(
                row["opened_count"], row["last_opened_at"]
            )
            for row in rows
        }


class InMemorySearchMemory:
    def __init__(self) -> None:
        self._lock = Lock()
        self._recents: dict[tuple[str, str, str], Recent] = {}
        self._opens: dict[tuple[str, str], dict[tuple[str, str], Opened]] = {}

    def recents(self, space_id: str, user_id: str) -> list[Recent]:
        with self._lock:
            mine = [
                recent
                for (space, user, _), recent in self._recents.items()
                if (space, user) == (space_id, user_id)
            ]
        return sorted(mine, key=lambda r: (-r.searched_at.timestamp(), r.id))

    def remember(self, space_id: str, user_id: str, q: str) -> Recent:
        now = datetime.now(timezone.utc)
        with self._lock:
            key = (space_id, user_id, query_text(q))
            current = self._recents.get(key)
            recent = (
                replace(current, q=q, searched_at=now)
                if current
                else Recent(str(uuid4()), q, now)
            )
            self._recents[key] = recent
            mine = sorted(
                (k for k in self._recents if k[:2] == (space_id, user_id)),
                key=lambda k: self._recents[k].searched_at,
                reverse=True,
            )
            for stale in mine[RECENTS:]:
                del self._recents[stale]
        return recent

    def forget(self, space_id: str, user_id: str, recent_id: str) -> bool:
        with self._lock:
            for key, recent in list(self._recents.items()):
                if key[:2] == (space_id, user_id) and recent.id == recent_id:
                    del self._recents[key]
                    return True
        return False

    def forget_all(self, space_id: str, user_id: str) -> None:
        with self._lock:
            for key in [k for k in self._recents if k[:2] == (space_id, user_id)]:
                del self._recents[key]

    def open(self, space_id: str, user_id: str, kind: SearchKind, record_id: str) -> None:
        now = datetime.now(timezone.utc)
        with self._lock:
            mine = self._opens.setdefault((space_id, user_id), {})
            current = mine.get((kind, record_id))
            mine[(kind, record_id)] = Opened((current.count if current else 0) + 1, now)
            for stale in sorted(mine, key=lambda k: mine[k].last_opened_at, reverse=True)[
                OPENS:
            ]:
                del mine[stale]

    def opens(self, space_id: str, user_id: str) -> Opens:
        with self._lock:
            return dict(self._opens.get((space_id, user_id), {}))


def ranked(items: list[dict], kind: SearchKind, opens: Opens) -> list[dict]:
    """The member's opened records first, most opened then most recently
    opened; every other record keeps its place in the list's own order."""

    def rank(item: dict) -> tuple[int, int, float]:
        opened = opens.get((kind, item["id"]))
        if opened is None:
            return (1, 0, 0.0)
        return (0, -opened.count, -opened.last_opened_at.timestamp())

    return sorted(items, key=rank)
