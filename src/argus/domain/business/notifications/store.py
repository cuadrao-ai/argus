from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Literal
from uuid import uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

Kind = Literal["invitation_received", "new_sender_waiting"]
RECENT_DAYS = 30


class Notification(BaseModel):
    id: str
    business_id: str
    recipient_user_id: str
    kind: Kind
    subject_id: str
    created_at: datetime
    read_at: datetime | None = None
    resolved_at: datetime | None = None


class InMemoryNotificationStore:
    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._rows: dict[str, Notification] = {}
        self._lock = RLock()

    def put(
        self, business_id: str, recipient_user_id: str, kind: Kind, subject_id: str
    ) -> None:
        with self._lock:
            if any(
                (r.business_id, r.recipient_user_id, r.kind, r.subject_id)
                == (business_id, recipient_user_id, kind, subject_id)
                and r.resolved_at is None
                for r in self._rows.values()
            ):
                return
            row = Notification(
                id=str(uuid4()),
                business_id=business_id,
                recipient_user_id=recipient_user_id,
                kind=kind,
                subject_id=subject_id,
                created_at=self.clock(),
            )
            self._rows[row.id] = row

    def resolve(
        self, business_id: str, kind: Kind, subject_id: str, at: datetime | None = None
    ) -> None:
        with self._lock:
            for row in self._rows.values():
                if (row.business_id, row.kind, row.subject_id) == (
                    business_id,
                    kind,
                    subject_id,
                ) and row.resolved_at is None:
                    row.resolved_at = at or self.clock()

    def list(self, business_id: str, recipient_user_id: str) -> list[Notification]:
        with self._lock:
            cutoff = self.clock() - timedelta(days=RECENT_DAYS)
            return sorted(
                (
                    r.model_copy()
                    for r in self._rows.values()
                    if r.business_id == business_id
                    and r.recipient_user_id == recipient_user_id
                    and (r.resolved_at is None or r.resolved_at >= cutoff)
                ),
                key=lambda r: (r.created_at, r.id),
                reverse=True,
            )

    def mark_read(
        self, business_id: str, recipient_user_id: str, notification_id: str | None = None
    ) -> int:
        with self._lock:
            rows = [
                r
                for r in self._rows.values()
                if r.business_id == business_id
                and r.recipient_user_id == recipient_user_id
                and r.read_at is None
                and (notification_id is None or r.id == notification_id)
            ]
            for row in rows:
                row.read_at = self.clock()
            return len(rows)


def put(
    db: Connection, business_id: str, recipient_user_id: str, kind: Kind, subject_id: str
) -> None:
    db.execute(
        "insert into public.business_notifications(business_id,recipient_user_id,kind,subject_id)"
        " values(%s,%s,%s,%s) on conflict(business_id,recipient_user_id,kind,subject_id)"
        " where resolved_at is null do nothing",
        (business_id, recipient_user_id, kind, subject_id),
    )


def resolve(
    db: Connection,
    business_id: str,
    kind: Kind,
    subject_id: str,
    at: datetime | None = None,
) -> None:
    db.execute(
        "update public.business_notifications set resolved_at=coalesce(%s,clock_timestamp())"
        " where business_id=%s and kind=%s and subject_id=%s and resolved_at is null",
        (at, business_id, kind, subject_id),
    )


class PostgresNotificationStore:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    def put(
        self, business_id: str, recipient_user_id: str, kind: Kind, subject_id: str
    ) -> None:
        with self.pool.connection() as db:
            put(db, business_id, recipient_user_id, kind, subject_id)

    def resolve(
        self, business_id: str, kind: Kind, subject_id: str, at: datetime | None = None
    ) -> None:
        with self.pool.connection() as db:
            resolve(db, business_id, kind, subject_id, at)

    def list(self, business_id: str, recipient_user_id: str) -> list[Notification]:
        with self.pool.connection() as db, db.cursor(row_factory=dict_row) as cursor:
            rows = cursor.execute(
                "select id::text,business_id::text,recipient_user_id::text,kind,subject_id::text,"
                "created_at,read_at,resolved_at from public.business_notifications"
                " where business_id=%s and recipient_user_id=%s"
                " and (resolved_at is null or resolved_at>=clock_timestamp()-%s)"
                " order by created_at desc,id desc",
                (business_id, recipient_user_id, timedelta(days=RECENT_DAYS)),
            ).fetchall()
        return [Notification(**row) for row in rows]

    def mark_read(
        self, business_id: str, recipient_user_id: str, notification_id: str | None = None
    ) -> int:
        with self.pool.connection() as db:
            return db.execute(
                "update public.business_notifications set read_at=clock_timestamp()"
                " where business_id=%s and recipient_user_id=%s and read_at is null"
                " and (%s::uuid is null or id=%s::uuid)",
                (business_id, recipient_user_id, notification_id, notification_id),
            ).rowcount
