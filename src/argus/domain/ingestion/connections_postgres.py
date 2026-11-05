"""Postgres twin of ``InMemoryConnectionRepository``.

Every compare-and-set is a single ``UPDATE ... WHERE`` so concurrent webhook
syncs, lease takeovers and disconnects resolve in the database, not in Python.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from psycopg import errors
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from argus.domain.ingestion.connections import (
    DEFAULT_LEASE,
    ConnectionNotFound,
    ConnectionStatus,
    DuplicateConnection,
    SourceConnection,
    checked_code,
    checked_cursor,
    checked_holder,
    checked_label,
    checked_ref,
)
from argus.domain.ingestion.contract import SourceKind
from argus.domain.owner_scope import OwnerScope, scope_of, space_id, sql_predicate

_COLUMNS = (
    "id::text, user_id::text, source, status, label, external_ref, sync_cursor, "
    "secret_ciphertext, secret_key_fingerprint, last_success_at, last_attempt_at, last_error_code, "
    "attention_code, attention_at, "
    "lease_holder, lease_until, created_at, updated_at, disconnected_at, version, "
    "owner_space_id::text"
)
_LIVE = "status <> 'disconnected'"


class PostgresConnectionRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

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
        try:
            row = self._one(
                f"""insert into public.financial_source_connections
                    (id, user_id, source, external_ref, label, secret_ciphertext,
                     secret_key_fingerprint, created_at, updated_at, owner_space_id)
                values (coalesce(%s::uuid, gen_random_uuid()),
                        %s, %s, %s, %s, %s, %s, %s, %s, %s)
                returning {_COLUMNS}""",
                (
                    connection_id,
                    user_id,
                    source,
                    external_ref,
                    label,
                    secret,
                    secret_key if secret is not None else None,
                    now,
                    now,
                    space_id(scope),
                ),
            )
        except errors.UniqueViolation:
            in_scope, params = sql_predicate(scope, "owner_space_id")
            existing = self._one(
                f"""select {_COLUMNS} from public.financial_source_connections
                where user_id = %s and source = %s and external_ref = %s and {_LIVE}
                and {in_scope}""",
                (user_id, source, external_ref, *params),
            )
            if existing is None:
                raise DuplicateConnection("", elsewhere=True) from None
            raise DuplicateConnection(existing["id"]) from None
        assert row is not None
        return _row(row)

    def get(
        self, *, user_id: str, connection_id: str, scope: OwnerScope
    ) -> SourceConnection:
        in_scope, params = sql_predicate(scope, "owner_space_id")
        row = self._one(
            f"""select {_COLUMNS} from public.financial_source_connections
            where id = %s::uuid and user_id = %s and {in_scope}""",
            (_uuid(connection_id), user_id, *params),
        )
        if row is None:
            raise ConnectionNotFound()
        return _row(row)

    def get_any_scope(self, *, user_id: str, connection_id: str) -> SourceConnection:
        row = self._one(
            f"""select {_COLUMNS} from public.financial_source_connections
            where id = %s::uuid and user_id = %s""",
            (_uuid(connection_id), user_id),
        )
        if row is None:
            raise ConnectionNotFound()
        return _row(row)

    def list(self, *, user_id: str, scope: OwnerScope) -> list[SourceConnection]:
        in_scope, params = sql_predicate(scope, "owner_space_id")
        return [
            _row(r)
            for r in self._all(
                f"""select {_COLUMNS} from public.financial_source_connections
                where user_id = %s and {in_scope} order by created_at, id""",
                (user_id, *params),
            )
        ]

    def find_live(
        self, *, source: SourceKind, external_ref: str
    ) -> list[SourceConnection]:
        return [
            _row(r)
            for r in self._all(
                f"""select {_COLUMNS} from public.financial_source_connections
                where source = %s and external_ref = %s and {_LIVE}""",
                (source, external_ref),
            )
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
        row = self._one(
            f"""update public.financial_source_connections
            set secret_ciphertext = %s, secret_key_fingerprint = %s,
                status = %s, last_error_code = null,
                attention_code = null, attention_at = null,
                updated_at = %s, version = version + 1
            where id = %s::uuid and {_LIVE}
            returning {_COLUMNS}""",
            (secret, secret_key, status, now, _uuid(connection_id)),
        )
        if row is None:
            raise ConnectionNotFound()
        return _row(row)

    def lease(
        self,
        *,
        connection_id: str,
        holder: str,
        now: datetime,
        ttl: timedelta = DEFAULT_LEASE,
    ) -> bool:
        checked_holder(holder)
        row = self._one(
            f"""update public.financial_source_connections
            set lease_holder = %s, lease_until = %s, last_attempt_at = %s
            where id = %s::uuid and {_LIVE}
              and (lease_until is null or lease_until <= %s or lease_holder = %s)
            returning id""",
            (holder, now + ttl, now, _uuid(connection_id), now, holder),
        )
        return row is not None

    def renew(
        self,
        *,
        connection_id: str,
        holder: str,
        now: datetime,
        ttl: timedelta = DEFAULT_LEASE,
    ) -> bool:
        checked_holder(holder)
        row = self._one(
            f"""update public.financial_source_connections
            set lease_until = %s
            where id = %s::uuid and {_LIVE} and lease_holder = %s and lease_until > %s
            returning id""",
            (now + ttl, _uuid(connection_id), holder, now),
        )
        return row is not None

    def release(self, *, connection_id: str, holder: str) -> None:
        self._one(
            """update public.financial_source_connections
            set lease_holder = null, lease_until = null
            where id = %s::uuid and lease_holder = %s returning id""",
            (_uuid(connection_id), holder),
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
        row = self._one(
            f"""update public.financial_source_connections
            set sync_cursor = %s, status = 'active', last_success_at = %s,
                last_attempt_at = %s, last_error_code = null,
                updated_at = %s, version = version + 1
            where id = %s::uuid and {_LIVE} and lease_holder = %s
              and sync_cursor is not distinct from %s
            returning id""",
            (cursor, now, now, now, _uuid(connection_id), holder, expected_cursor),
        )
        return row is not None

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
        row = self._one(
            f"""update public.financial_source_connections
            set status = %s, last_error_code = %s, last_attempt_at = %s,
                lease_holder = null, lease_until = null,
                updated_at = %s, version = version + 1
            where id = %s::uuid and {_LIVE}
              and (%s::text is null or lease_holder = %s)
            returning {_COLUMNS}""",
            (status, code, now, now, _uuid(connection_id), holder, holder),
        )
        if row is None:
            current = self._one(
                f"""select {_COLUMNS} from public.financial_source_connections
                where id = %s::uuid and {_LIVE}""",
                (_uuid(connection_id),),
            )
            if current is None:
                raise ConnectionNotFound()
            return _row(current)  # a stale sync; the current one owns the state
        return _row(row)

    def flag_attention(
        self, *, connection_id: str, code: str, now: datetime
    ) -> SourceConnection:
        checked_code(code)
        row = self._one(
            f"""update public.financial_source_connections
            set attention_code = %s, attention_at = %s,
                updated_at = %s, version = version + 1
            where id = %s::uuid and {_LIVE}
            returning {_COLUMNS}""",
            (code, now, now, _uuid(connection_id)),
        )
        if row is None:
            raise ConnectionNotFound()
        return _row(row)

    def disconnect(
        self, *, user_id: str, connection_id: str, now: datetime
    ) -> SourceConnection:
        row = self._one(
            f"""update public.financial_source_connections
            set status = 'disconnected', secret_ciphertext = null,
                secret_key_fingerprint = null, sync_cursor = null,
                attention_code = null, attention_at = null, lease_holder = null, lease_until = null, disconnected_at = %s,
                updated_at = %s, version = version + 1
            where id = %s::uuid and user_id = %s and {_LIVE}
            returning {_COLUMNS}""",
            (now, now, _uuid(connection_id), user_id),
        )
        if row is None:
            return self.get_any_scope(user_id=user_id, connection_id=connection_id)
        return _row(row)

    def _one(self, statement: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
        with self._pool.connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(statement, params)
                return cursor.fetchone()

    def _all(self, statement: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        with self._pool.connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(statement, params)
                return list(cursor.fetchall())


def _uuid(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError):
        raise ConnectionNotFound() from None


def _row(row: dict[str, Any]) -> SourceConnection:
    secret = row["secret_ciphertext"]
    return SourceConnection(
        id=row["id"],
        user_id=row["user_id"],
        source=row["source"],
        status=row["status"],
        label=row["label"],
        external_ref=row["external_ref"],
        cursor=row["sync_cursor"],
        secret=bytes(secret) if secret is not None else None,
        last_success_at=row["last_success_at"],
        last_attempt_at=row["last_attempt_at"],
        last_error_code=row["last_error_code"],
        attention_code=row["attention_code"],
        attention_at=row["attention_at"],
        lease_holder=row["lease_holder"],
        lease_until=row["lease_until"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        disconnected_at=row["disconnected_at"],
        version=row["version"],
        secret_key=row["secret_key_fingerprint"],
        scope=scope_of(row["owner_space_id"]),
    )
