"""The owner's one Business space, in Postgres and in memory.

A space belongs to the person who created it, and only that person. Nothing
here takes a space id from a client: every lookup starts from the signed-in
person. In Postgres, ``public.business_space_of`` is the one rule that maps a
person to their open space; the WhatsApp sender-link trigger reads it too.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from typing import Protocol

from psycopg_pool import ConnectionPool

from argus.domain.business.access import ensure_owner_grant

# Founder-approved October 8: the name a space starts with until renamed.
DEFAULT_SPACE_NAMES = {"es": "Mi negocio", "en": "My business"}
MAX_NAME_LENGTH = 80


@dataclass(frozen=True)
class Space:
    id: str
    name: str
    custodian_id: str


def default_space_name(language: str | None) -> str:
    """English when the person's language is English, else Spanish."""

    return DEFAULT_SPACE_NAMES["en" if language == "en" else "es"]


class SpaceStore(Protocol):
    def open_space(self, person_id: str) -> Space | None: ...

    def get(self, space_id: str) -> Space | None:
        """An open Business space by id, for a grant that names it."""
        ...

    def create(self, person_id: str, name: str) -> tuple[Space, bool]:
        """The person's open space, created with ``name`` when there is none.

        Returns ``(space, created)``. Concurrent calls converge on one space.
        """
        ...

    def rename(self, person_id: str, name: str) -> Space | None: ...


class PostgresSpaceStore:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def open_space(self, person_id: str) -> Space | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "select id::text, name, created_by::text from public.spaces"
                " where id = public.business_space_of(%s)",
                (person_id,),
            ).fetchone()
        return Space(*row) if row else None

    def get(self, space_id: str) -> Space | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "select id::text, name, created_by::text from public.spaces"
                " where id = %s and kind = 'business' and closed_at is null",
                (space_id,),
            ).fetchone()
        return Space(*row) if row else None

    def create(self, person_id: str, name: str) -> tuple[Space, bool]:
        with self._pool.connection() as connection, connection.transaction():
            created = connection.execute(
                "insert into public.spaces (kind, name, created_by, current_owner_id)"
                " values ('business', %s, %s, %s)"
                " on conflict (current_owner_id) where kind = 'business' and closed_at is null"
                " do nothing returning id::text, name, created_by::text",
                (name, person_id, person_id),
            ).fetchone()
            if created is not None:
                # The owner's grant is born with the space, in the same transaction.
                ensure_owner_grant(connection, created[0], person_id)
        if created is not None:
            return Space(*created), True
        existing = self.open_space(person_id)
        if existing is None:  # pragma: no cover - the conflict means it exists
            raise LookupError("business space vanished during create")
        return existing, False

    def rename(self, person_id: str, name: str) -> Space | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "update public.spaces set name = %s"
                " where id = public.business_space_of(%s) returning id::text, name, created_by::text",
                (name, person_id),
            ).fetchone()
        return Space(*row) if row else None


class InMemorySpaceStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._spaces: dict[str, Space] = {}

    def open_space(self, person_id: str) -> Space | None:
        with self._lock:
            return self._spaces.get(person_id)

    def get(self, space_id: str) -> Space | None:
        with self._lock:
            return next((s for s in self._spaces.values() if s.id == space_id), None)

    def create(self, person_id: str, name: str) -> tuple[Space, bool]:
        with self._lock:
            existing = self._spaces.get(person_id)
            if existing is not None:
                return existing, False
            space = Space(str(uuid.uuid4()), name, person_id)
            self._spaces[person_id] = space
            return space, True

    def rename(self, person_id: str, name: str) -> Space | None:
        with self._lock:
            if person_id not in self._spaces:
                return None
            space = Space(self._spaces[person_id].id, name, person_id)
            self._spaces[person_id] = space
            return space
