from __future__ import annotations

from collections.abc import Callable, Collection, Iterable
from datetime import datetime, timezone
from threading import RLock
from typing import Literal
from uuid import uuid4

from psycopg import Connection
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

Kind = Literal["invitation_received", "new_sender_waiting"]


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

    def read_subjects(
        self, recipient_user_id: str, kind: Kind, subject_ids: Collection[str]
    ) -> set[str]:
        with self._lock:
            return {
                r.subject_id
                for r in self._rows.values()
                if (r.recipient_user_id, r.kind) == (recipient_user_id, kind)
                and r.read_at is not None
                and r.subject_id in subject_ids
            }

    def mark_read(
        self, recipient_user_id: str, kind: Kind, subjects: Iterable[tuple[str, str]]
    ) -> None:
        """Marks each (business, subject) read, once: the first reading time stays."""

        with self._lock:
            for business_id, subject_id in subjects:
                self.put(business_id, recipient_user_id, kind, subject_id)
                for row in self._rows.values():
                    if (
                        row.business_id,
                        row.recipient_user_id,
                        row.kind,
                        row.subject_id,
                    ) == (business_id, recipient_user_id, kind, subject_id) and (
                        row.resolved_at is None and row.read_at is None
                    ):
                        row.read_at = self.clock()


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

    def read_subjects(
        self, recipient_user_id: str, kind: Kind, subject_ids: Collection[str]
    ) -> set[str]:
        if not subject_ids:
            return set()
        with self.pool.connection() as db:
            return {
                row[0]
                for row in db.execute(
                    "select subject_id::text from public.business_notifications"
                    " where recipient_user_id=%s and kind=%s and read_at is not null"
                    " and subject_id=any(%s::uuid[])",
                    (recipient_user_id, kind, list(subject_ids)),
                ).fetchall()
            }

    def mark_read(
        self, recipient_user_id: str, kind: Kind, subjects: Iterable[tuple[str, str]]
    ) -> None:
        """Marks each (business, subject) read, once: the first reading time stays."""

        with self.pool.connection() as db, db.transaction():
            for business_id, subject_id in subjects:
                db.execute(
                    "insert into public.business_notifications"
                    "(business_id,recipient_user_id,kind,subject_id,read_at)"
                    " values(%s,%s,%s,%s,clock_timestamp())"
                    " on conflict(business_id,recipient_user_id,kind,subject_id)"
                    " where resolved_at is null do update set read_at="
                    "coalesce(public.business_notifications.read_at,excluded.read_at)",
                    (business_id, recipient_user_id, kind, subject_id),
                )
