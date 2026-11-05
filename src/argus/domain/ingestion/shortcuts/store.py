"""Where device-token digests live: one row per Shortcuts connection.

The digest is not a provider credential, so it does not use the connection's
sealed ``secret`` column (the hub would try to open it). It lives beside the
connection, is deleted on revoke, and is only consulted for a connection the
shared repository still reports as live, so a disconnected device is refused
even if a delete were ever missed.

The per-person device limit is enforced here, where the digest is written:
counting a person's live devices and inserting the new digest happen in one
transaction under a per-person advisory lock, so concurrent enrollments
cannot exceed it.
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Protocol

# First key of the two-key advisory lock: names "Shortcuts enrollment".
_ENROLL_LOCK = 0x5C7E


class DeviceTokenStore(Protocol):
    def put_within_limit(
        self,
        *,
        connection_id: str,
        user_id: str,
        digest: bytes,
        now: datetime,
        limit: int,
    ) -> bool:
        """Store the digest unless the person already has ``limit`` live
        devices; ``False`` means nothing was written."""
        ...

    def get(self, *, connection_id: str) -> bytes | None: ...

    def delete(self, *, connection_id: str) -> None: ...


class InMemoryDeviceTokenStore:
    """Twin for hermetic tests; a disconnect always deletes its row here."""

    def __init__(self) -> None:
        self._rows: dict[str, tuple[str, bytes]] = {}
        self._lock = threading.Lock()

    def put_within_limit(
        self,
        *,
        connection_id: str,
        user_id: str,
        digest: bytes,
        now: datetime,
        limit: int,
    ) -> bool:
        with self._lock:
            held = sum(1 for owner, _ in self._rows.values() if owner == user_id)
            if held >= limit:
                return False
            self._rows[connection_id] = (user_id, bytes(digest))
            return True

    def get(self, *, connection_id: str) -> bytes | None:
        row = self._rows.get(connection_id)
        return row[1] if row else None

    def delete(self, *, connection_id: str) -> None:
        with self._lock:
            self._rows.pop(connection_id, None)


class PostgresDeviceTokenStore:
    def __init__(self, pool) -> None:  # noqa: ANN001 - psycopg_pool.ConnectionPool
        self._pool = pool

    def put_within_limit(
        self,
        *,
        connection_id: str,
        user_id: str,
        digest: bytes,
        now: datetime,
        limit: int,
    ) -> bool:
        with self._pool.connection() as conn, conn.transaction():
            conn.execute(
                "select pg_advisory_xact_lock(%s, hashtext(%s))",
                (_ENROLL_LOCK, user_id),
            )
            held = conn.execute(
                """select count(*)
                from public.financial_shortcut_device_tokens t
                join public.financial_source_connections c on c.id = t.connection_id
                where t.user_id = %s::uuid and c.status <> 'disconnected'""",
                (user_id,),
            ).fetchone()[0]
            if held >= limit:
                return False
            conn.execute(
                """insert into public.financial_shortcut_device_tokens
                    (connection_id, user_id, token_sha256, created_at)
                values (%s::uuid, %s::uuid, %s, %s)""",
                (connection_id, user_id, digest, now),
            )
            return True

    def get(self, *, connection_id: str) -> bytes | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                """select token_sha256 from public.financial_shortcut_device_tokens
                where connection_id = %s::uuid""",
                (connection_id,),
            ).fetchone()
        return bytes(row[0]) if row else None

    def delete(self, *, connection_id: str) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """delete from public.financial_shortcut_device_tokens
                where connection_id = %s::uuid""",
                (connection_id,),
            )
