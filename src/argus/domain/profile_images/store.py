"""The rows that say a person or a Business has a picture, in Postgres and in memory."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Protocol

from psycopg_pool import ConnectionPool

Kind = Literal["person", "business"]

TABLES: dict[Kind, tuple[str, str]] = {
    "person": ("public.profile_photos", "user_id"),
    "business": ("public.business_logos", "space_id"),
}


@dataclass(frozen=True)
class StoredImage:
    sha256: str
    updated_at: datetime


class ProfileImageStore(Protocol):
    def get_many(self, kind: Kind, ids: Sequence[str]) -> dict[str, StoredImage]: ...

    def save(self, kind: Kind, subject_id: str, sha256: str) -> StoredImage:
        """The subject's row, inserted or replaced."""
        ...

    def delete(self, kind: Kind, subject_id: str) -> bool: ...


class PostgresProfileImageStore:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def get_many(self, kind: Kind, ids: Sequence[str]) -> dict[str, StoredImage]:
        if not ids:
            return {}
        table, key = TABLES[kind]
        with self._pool.connection() as connection:
            rows = connection.execute(
                f"select {key}::text, sha256, updated_at from {table}"
                f" where {key} = any(%s::uuid[])",
                (list(ids),),
            ).fetchall()
        return {row[0]: StoredImage(row[1], row[2]) for row in rows}

    def save(self, kind: Kind, subject_id: str, sha256: str) -> StoredImage:
        table, key = TABLES[kind]
        with self._pool.connection() as connection:
            row = connection.execute(
                f"insert into {table} ({key}, sha256) values (%s, %s)"
                f" on conflict ({key}) do update"
                " set sha256 = excluded.sha256, updated_at = now()"
                " returning sha256, updated_at",
                (subject_id, sha256),
            ).fetchone()
        return StoredImage(row[0], row[1])

    def delete(self, kind: Kind, subject_id: str) -> bool:
        table, key = TABLES[kind]
        with self._pool.connection() as connection:
            row = connection.execute(
                f"delete from {table} where {key} = %s returning 1", (subject_id,)
            ).fetchone()
        return row is not None


class InMemoryProfileImageStore:
    def __init__(self) -> None:
        self._rows: dict[tuple[Kind, str], StoredImage] = {}
        self._lock = threading.Lock()

    def get_many(self, kind: Kind, ids: Sequence[str]) -> dict[str, StoredImage]:
        with self._lock:
            return {
                subject_id: self._rows[(kind, subject_id)]
                for subject_id in ids
                if (kind, subject_id) in self._rows
            }

    def save(self, kind: Kind, subject_id: str, sha256: str) -> StoredImage:
        with self._lock:
            row = StoredImage(sha256, datetime.now(timezone.utc))
            self._rows[(kind, subject_id)] = row
            return row

    def delete(self, kind: Kind, subject_id: str) -> bool:
        with self._lock:
            return self._rows.pop((kind, subject_id), None) is not None
