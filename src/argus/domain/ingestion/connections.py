"""Connected-source state shared by every connector.

One row per person-authorized connection (a Plaid Item, a Gmail mailbox, a
Shortcuts device). It owns what the MVEE requires every connection to show:
status, last successful refresh, and an actionable failure. It also owns the
sync cursor and a short lease so two webhook-triggered syncs of the same
connection never interleave cursor advances.

A failed sync only records the failure: it never clears ``last_success_at``
or the cursor, so existing evidence and its freshness stay truthful.
"""

from __future__ import annotations

import re
import threading
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Literal, Protocol

from argus.domain.ingestion.contract import SourceKind, inert_text
from argus.domain.owner_scope import OwnerScope

ConnectionStatus = Literal["active", "needs_reauth", "error", "disconnected"]
LIVE: frozenset[str] = frozenset({"active", "needs_reauth", "error"})
DEFAULT_LEASE = timedelta(minutes=5)
_CODE = re.compile(r"^[a-z0-9_]{1,64}$")


# One domain boundary for both repositories, matching the migration's checks,
# so the in-memory twin cannot accept what Postgres would refuse.
def checked_ref(value: str) -> str:
    if not 1 <= len(value) <= 200:
        raise ValueError("external_ref must be 1-200 characters")
    return value


def checked_label(value: str | None) -> str | None:
    return inert_text(value, 80)


def checked_code(value: str) -> str:
    if not _CODE.match(value):
        raise ValueError("codes are 1-64 lowercase letters, digits or underscores")
    return value


def checked_cursor(value: str | None) -> str | None:
    if value is not None and len(value) > 4096:
        raise ValueError("cursor exceeds 4096 characters")
    return value


def checked_holder(value: str) -> str:
    if not 1 <= len(value) <= 64:
        raise ValueError("lease holder must be 1-64 characters")
    return value


class ConnectionNotFound(LookupError):
    pass


class DuplicateConnection(RuntimeError):
    """A live connection already holds this provider reference.

    ``elsewhere`` means it belongs to another person: one provider grant (a
    Plaid Item, a mailbox) never backs two people's connections, because
    revoking it for one would silently break the other.
    """

    def __init__(self, existing_id: str, *, elsewhere: bool = False) -> None:
        super().__init__("a live connection for this source reference exists")
        self.existing_id = existing_id
        self.elsewhere = elsewhere


@dataclass(frozen=True)
class SourceConnection:
    id: str
    user_id: str
    source: SourceKind
    status: ConnectionStatus
    # Non-secret display label: institution name, masked mailbox, device name.
    label: str | None
    # Provider handle: Plaid item_id, Gmail address digest, Shortcuts device id.
    external_ref: str
    cursor: str | None
    secret: bytes | None
    last_success_at: datetime | None
    last_attempt_at: datetime | None
    last_error_code: str | None
    # A warning that outlives successful syncs (Plaid consent expiring soon).
    # Only re-authorization or disconnect clears it; sync status does not.
    attention_code: str | None
    attention_at: datetime | None
    lease_holder: str | None
    lease_until: datetime | None
    created_at: datetime
    updated_at: datetime
    disconnected_at: datetime | None
    version: int
    # Which key sealed ``secret`` (``SecretBox.key_id``), stored next to it.
    # None for rows sealed before Lane 6 or with no secret.
    secret_key: str | None = None
    # The connection is a root row: its documents, observations and the import
    # events made from them belong to this scope.
    scope: OwnerScope = field(kw_only=True)


class ConnectionRepository(Protocol):
    def create(
        self,
        *,
        user_id: str,
        source: SourceKind,
        external_ref: str,
        label: str | None,
        now: datetime,
        secret: bytes | None = None,
        connection_id: str | None = None,
        secret_key: str | None = None,
        scope: OwnerScope,
    ) -> SourceConnection: ...

    def get(
        self, *, user_id: str, connection_id: str, scope: OwnerScope
    ) -> SourceConnection: ...

    def get_any_scope(self, *, user_id: str, connection_id: str) -> SourceConnection:
        """The row whatever its scope, for server-keyed paths (preparation jobs,
        storage liveness). A request path reads through ``get``."""
        ...

    def list(self, *, user_id: str, scope: OwnerScope) -> list[SourceConnection]: ...

    def find_live(
        self, *, source: SourceKind, external_ref: str
    ) -> list[SourceConnection]: ...

    def set_secret(
        self,
        *,
        connection_id: str,
        secret: bytes,
        status: ConnectionStatus,
        now: datetime,
        secret_key: str | None = None,
    ) -> SourceConnection: ...

    def lease(
        self,
        *,
        connection_id: str,
        holder: str,
        now: datetime,
        ttl: timedelta = DEFAULT_LEASE,
    ) -> bool: ...

    def renew(
        self,
        *,
        connection_id: str,
        holder: str,
        now: datetime,
        ttl: timedelta = DEFAULT_LEASE,
    ) -> bool:
        """Extend a lease only while ``holder`` still holds it; never re-take
        a lease a failure released or another sync acquired."""
        ...

    def release(self, *, connection_id: str, holder: str) -> None: ...

    def record_success(
        self,
        *,
        connection_id: str,
        holder: str,
        expected_cursor: str | None,
        cursor: str | None,
        now: datetime,
    ) -> bool: ...

    def record_failure(
        self,
        *,
        connection_id: str,
        code: str,
        status: ConnectionStatus,
        now: datetime,
        holder: str | None = None,
    ) -> SourceConnection:
        """Record an actionable failure and release the sync lease, so a sync
        that was already running cannot report success over it.

        A sync reporting its own failure passes ``holder``: if it no longer
        holds the lease (another sync took over), nothing changes. Provider
        signals such as webhooks pass no holder and always apply."""
        ...

    def flag_attention(
        self, *, connection_id: str, code: str, now: datetime
    ) -> SourceConnection: ...

    def disconnect(
        self, *, user_id: str, connection_id: str, now: datetime
    ) -> SourceConnection: ...


class InMemoryConnectionRepository:
    """Deterministic twin of the Postgres repository for hermetic tests."""

    def __init__(self) -> None:
        self._rows: dict[str, SourceConnection] = {}
        self._lock = threading.Lock()

    def create(
        self,
        *,
        user_id: str,
        source: SourceKind,
        external_ref: str,
        label: str | None,
        now: datetime,
        secret: bytes | None = None,
        connection_id: str | None = None,
        secret_key: str | None = None,
        scope: OwnerScope,
    ) -> SourceConnection:
        external_ref, label = checked_ref(external_ref), checked_label(label)
        with self._lock:
            for row in self._rows.values():
                if (
                    row.source == source
                    and row.external_ref == external_ref
                    and row.status in LIVE
                ):
                    if row.user_id != user_id or row.scope != scope:
                        raise DuplicateConnection("", elsewhere=True)
                    raise DuplicateConnection(row.id)
            row = SourceConnection(
                id=connection_id or str(uuid.uuid4()),
                user_id=user_id,
                source=source,
                status="active",
                label=label,
                external_ref=external_ref,
                cursor=None,
                secret=secret,
                last_success_at=None,
                last_attempt_at=None,
                last_error_code=None,
                attention_code=None,
                attention_at=None,
                lease_holder=None,
                lease_until=None,
                created_at=now,
                updated_at=now,
                disconnected_at=None,
                version=1,
                secret_key=secret_key if secret is not None else None,
                scope=scope,
            )
            self._rows[row.id] = row
            return row

    def get(
        self, *, user_id: str, connection_id: str, scope: OwnerScope
    ) -> SourceConnection:
        row = self.get_any_scope(user_id=user_id, connection_id=connection_id)
        if row.scope != scope:
            raise ConnectionNotFound()
        return row

    def get_any_scope(self, *, user_id: str, connection_id: str) -> SourceConnection:
        row = self._rows.get(connection_id)
        if row is None or row.user_id != user_id:
            raise ConnectionNotFound()
        return row

    def list(self, *, user_id: str, scope: OwnerScope) -> list[SourceConnection]:
        rows = [
            r for r in self._rows.values() if r.user_id == user_id and r.scope == scope
        ]
        return sorted(rows, key=lambda r: (r.created_at, r.id))

    def find_live(
        self, *, source: SourceKind, external_ref: str
    ) -> list[SourceConnection]:
        return [
            r
            for r in self._rows.values()
            if r.source == source and r.external_ref == external_ref and r.status in LIVE
        ]

    def set_secret(
        self,
        *,
        connection_id: str,
        secret: bytes,
        status: ConnectionStatus,
        now: datetime,
        secret_key: str | None = None,
    ) -> SourceConnection:
        with self._lock:
            row = self._live(connection_id)
            return self._put(
                replace(
                    row,
                    secret=secret,
                    secret_key=secret_key,
                    status=status,
                    last_error_code=None,
                    attention_code=None,
                    attention_at=None,
                ),
                now,
            )

    def lease(
        self,
        *,
        connection_id: str,
        holder: str,
        now: datetime,
        ttl: timedelta = DEFAULT_LEASE,
    ) -> bool:
        checked_holder(holder)
        with self._lock:
            row = self._rows.get(connection_id)
            if row is None or row.status not in LIVE:
                return False
            held = row.lease_until is not None and row.lease_until > now
            if held and row.lease_holder != holder:
                return False
            self._rows[connection_id] = replace(
                row, lease_holder=holder, lease_until=now + ttl, last_attempt_at=now
            )
            return True

    def renew(
        self,
        *,
        connection_id: str,
        holder: str,
        now: datetime,
        ttl: timedelta = DEFAULT_LEASE,
    ) -> bool:
        checked_holder(holder)
        with self._lock:
            row = self._rows.get(connection_id)
            if (
                row is None
                or row.status not in LIVE
                or row.lease_holder != holder
                or row.lease_until is None
                or row.lease_until <= now
            ):
                return False
            self._rows[connection_id] = replace(row, lease_until=now + ttl)
            return True

    def release(self, *, connection_id: str, holder: str) -> None:
        with self._lock:
            row = self._rows.get(connection_id)
            if row is not None and row.lease_holder == holder:
                self._rows[connection_id] = replace(
                    row, lease_holder=None, lease_until=None
                )

    def record_success(
        self,
        *,
        connection_id: str,
        holder: str,
        expected_cursor: str | None,
        cursor: str | None,
        now: datetime,
    ) -> bool:
        checked_cursor(cursor)
        with self._lock:
            row = self._rows.get(connection_id)
            if (
                row is None
                or row.status not in LIVE
                or row.lease_holder != holder
                or row.cursor != expected_cursor
            ):
                return False
            self._put(
                replace(
                    row,
                    cursor=cursor,
                    status="active",
                    last_success_at=now,
                    last_attempt_at=now,
                    last_error_code=None,
                ),
                now,
            )
            return True

    def record_failure(
        self,
        *,
        connection_id: str,
        code: str,
        status: ConnectionStatus,
        now: datetime,
        holder: str | None = None,
    ) -> SourceConnection:
        if status == "disconnected":
            raise ValueError("use disconnect() to end a connection")
        checked_code(code)
        with self._lock:
            row = self._live(connection_id)
            if holder is not None and row.lease_holder != holder:
                return row  # a stale sync; the current one owns the state
            # Ends any sync in flight: its finish must not overwrite this.
            return self._put(
                replace(
                    row,
                    status=status,
                    last_error_code=code,
                    last_attempt_at=now,
                    lease_holder=None,
                    lease_until=None,
                ),
                now,
            )

    def flag_attention(
        self, *, connection_id: str, code: str, now: datetime
    ) -> SourceConnection:
        checked_code(code)
        with self._lock:
            row = self._live(connection_id)
            return self._put(replace(row, attention_code=code, attention_at=now), now)

    def disconnect(
        self, *, user_id: str, connection_id: str, now: datetime
    ) -> SourceConnection:
        with self._lock:
            row = self.get_any_scope(user_id=user_id, connection_id=connection_id)
            if row.status == "disconnected":
                return row
            return self._put(
                replace(
                    row,
                    status="disconnected",
                    secret=None,
                    secret_key=None,
                    cursor=None,
                    attention_code=None,
                    attention_at=None,
                    lease_holder=None,
                    lease_until=None,
                    disconnected_at=now,
                ),
                now,
            )

    def _live(self, connection_id: str) -> SourceConnection:
        row = self._rows.get(connection_id)
        if row is None or row.status not in LIVE:
            raise ConnectionNotFound()
        return row

    def _put(self, row: SourceConnection, now: datetime) -> SourceConnection:
        row = replace(row, updated_at=now, version=row.version + 1)
        self._rows[row.id] = row
        return row
