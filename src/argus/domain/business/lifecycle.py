"""Close/reopen one Business without replacing its grants or records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from psycopg import Connection
from psycopg_pool import ConnectionPool

REOPEN_WINDOW = timedelta(days=30)
LifecycleAction = Literal["close", "reopen"]


class BusinessLifecycleError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class LifecycleResult:
    space_id: str
    name: str
    closed_at: datetime | None

    @property
    def reopen_until(self) -> datetime | None:
        return self.closed_at + REOPEN_WINDOW if self.closed_at is not None else None


class PostgresBusinessLifecycle:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def close(
        self, *, owner_id: str, space_id: str, confirmation: str, idempotency_key: str
    ) -> LifecycleResult:
        return self._command(
            owner_id=owner_id,
            space_id=space_id,
            action="close",
            confirmation=confirmation,
            idempotency_key=idempotency_key,
        )

    def reopen(
        self, *, owner_id: str, space_id: str, idempotency_key: str
    ) -> LifecycleResult:
        return self._command(
            owner_id=owner_id,
            space_id=space_id,
            action="reopen",
            confirmation=None,
            idempotency_key=idempotency_key,
        )

    def closed_spaces(self, owner_id: str) -> tuple[LifecycleResult, ...]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                "select s.id::text,s.name,s.closed_at from public.spaces s"
                " join auth.users u on u.id=s.created_by"
                " where s.created_by=%s and s.kind='business'"
                " and s.closed_at>clock_timestamp()-%s"
                " and coalesce(u.is_anonymous,false)=false"
                " order by s.closed_at desc,s.id",
                (owner_id, REOPEN_WINDOW),
            ).fetchall()
        return tuple(LifecycleResult(*row) for row in rows)

    def _command(
        self,
        *,
        owner_id: str,
        space_id: str,
        action: LifecycleAction,
        confirmation: str | None,
        idempotency_key: str,
    ) -> LifecycleResult:
        if not 1 <= len(idempotency_key) <= 200 or not idempotency_key.strip():
            raise BusinessLifecycleError("invalid_idempotency_key")
        with self._pool.connection() as connection, connection.transaction():
            name, closed_at = self._owned_space(connection, owner_id, space_id)
            previous = connection.execute(
                "select action,confirmation,result_closed_at,result_name"
                " from public.business_lifecycle_commands"
                " where space_id=%s and idempotency_key=%s",
                (space_id, idempotency_key),
            ).fetchone()
            if previous is not None:
                if previous[:2] != (action, confirmation):
                    raise BusinessLifecycleError("idempotency_conflict")
                return LifecycleResult(space_id, previous[3], previous[2])
            now = connection.execute("select clock_timestamp()").fetchone()[0]
            if action == "close":
                if confirmation != name:
                    raise BusinessLifecycleError("business_name_mismatch")
                closed_at = closed_at or now
            else:
                if closed_at is not None and now >= closed_at + REOPEN_WINDOW:
                    raise BusinessLifecycleError("business_reopen_expired")
                if connection.execute(
                    "select 1 from public.spaces where created_by=%s and id<>%s"
                    " and kind='business' and closed_at is null",
                    (owner_id, space_id),
                ).fetchone():
                    raise BusinessLifecycleError("business_already_open")
                closed_at = None
            connection.execute(
                "update public.spaces set closed_at=%s where id=%s",
                (closed_at, space_id),
            )
            connection.execute(
                "insert into public.business_lifecycle_commands"
                " (space_id,owner_id,idempotency_key,action,confirmation,result_closed_at,result_name)"
                " values(%s,%s,%s,%s,%s,%s,%s)",
                (
                    space_id,
                    owner_id,
                    idempotency_key,
                    action,
                    confirmation,
                    closed_at,
                    name,
                ),
            )
            return LifecycleResult(space_id, name, closed_at)

    @staticmethod
    def _owned_space(connection: Connection, owner_id: str, space_id: str) -> tuple:
        user = connection.execute(
            "select id from auth.users where id=%s and coalesce(is_anonymous,false)=false for no key update",
            (owner_id,),
        ).fetchone()
        if user is None:
            raise BusinessLifecycleError("business_record_not_found")
        row = connection.execute(
            "select name,closed_at from public.spaces"
            " where id=%s and created_by=%s and kind='business' for update",
            (space_id, owner_id),
        ).fetchone()
        if (
            row is None
            or not connection.execute(
                "select 1 from public.business_client_grants where space_id=%s"
                " and grantee_id=%s and issuer_id=%s and revoked_at is null"
                " and (expires_at is null or expires_at>clock_timestamp())"
                " and 'read'=any(capabilities)",
                (space_id, owner_id, owner_id),
            ).fetchone()
        ):
            raise BusinessLifecycleError("business_record_not_found")
        return row
