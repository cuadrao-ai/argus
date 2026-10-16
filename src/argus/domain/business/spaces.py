"""The owner's one Business space, in Postgres and in memory.

A space belongs to the person who created it, and only that person. Nothing
here takes a space id from a client: every lookup starts from the signed-in
person. In Postgres, ``public.business_space_of`` is the one rule that maps a
person to their open space; the WhatsApp sender-link trigger reads it too.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, replace
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
    name_prompt_seen: bool = False

    @property
    def name_required(self) -> bool:
        return self.name in DEFAULT_SPACE_NAMES.values()


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

    def claim_naming_visit(self, person_id: str, space_id: str) -> bool: ...

    def rename(
        self, person_id: str, name: str, space_id: str | None = None
    ) -> Space | None: ...


class PostgresSpaceStore:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def open_space(self, person_id: str) -> Space | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "select id::text, name, business_name_prompt_seen_at is not null from public.spaces"
                " where id = public.business_space_of(%s)",
                (person_id,),
            ).fetchone()
        return Space(*row) if row else None

    def get(self, space_id: str) -> Space | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "select id::text, name, business_name_prompt_seen_at is not null from public.spaces"
                " where id = %s and kind = 'business' and closed_at is null",
                (space_id,),
            ).fetchone()
        return Space(*row) if row else None

    def create(self, person_id: str, name: str) -> tuple[Space, bool]:
        with self._pool.connection() as connection, connection.transaction():
            created = connection.execute(
                "insert into public.spaces (kind, name, created_by)"
                " values ('business', %s, %s)"
                " on conflict (created_by) where kind = 'business' and closed_at is null"
                " do nothing returning id::text, name, business_name_prompt_seen_at is not null",
                (name, person_id),
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

    def claim_naming_visit(self, person_id: str, space_id: str) -> bool:
        with self._pool.connection() as connection:
            row = connection.execute(
                "update public.spaces set business_name_prompt_seen_at = now()"
                " where id = public.business_space_of(%s) and id = %s::uuid"
                " and business_name_prompt_seen_at is null and name = any(%s)"
                " returning id",
                (person_id, space_id, list(DEFAULT_SPACE_NAMES.values())),
            ).fetchone()
        return row is not None

    def rename(
        self, person_id: str, name: str, space_id: str | None = None
    ) -> Space | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "update public.spaces set name = %s"
                " where id = public.business_space_of(%s) and (%s::uuid is null or id = %s::uuid)"
                " returning id::text, name, business_name_prompt_seen_at is not null",
                (name, person_id, space_id, space_id),
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
            space = Space(str(uuid.uuid4()), name)
            self._spaces[person_id] = space
            return space, True

    def claim_naming_visit(self, person_id: str, space_id: str) -> bool:
        with self._lock:
            space = self._spaces.get(person_id)
            if (
                space is None
                or space.id != space_id
                or space.name_prompt_seen
                or not space.name_required
            ):
                return False
            self._spaces[person_id] = replace(space, name_prompt_seen=True)
            return True

    def rename(
        self, person_id: str, name: str, space_id: str | None = None
    ) -> Space | None:
        with self._lock:
            current = self._spaces.get(person_id)
            if current is None or (space_id is not None and current.id != space_id):
                return None
            space = replace(current, name=name)
            self._spaces[person_id] = space
            return space
