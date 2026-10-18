"""A pending command transfers authority only when its live target accepts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from psycopg import Connection
from psycopg_pool import ConnectionPool

from argus.domain.business.access import MEMBER_CAPABILITIES, OWNER_CAPABILITIES, _lock
from argus.domain.business.lifecycle import (
    BusinessLifecycleError,
    PostgresBusinessLifecycle,
)


@dataclass(frozen=True)
class TransferResult:
    id: str
    space_id: str
    owner_id: str
    target_id: str
    status: Literal["pending", "accepted", "cancelled", "declined"]


_COLUMNS = "id::text,space_id::text,owner_id::text,target_id::text,status"


class PostgresBusinessTransfer:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    def request(
        self,
        *,
        owner_id: str,
        space_id: str,
        target_grant_id: str,
        confirmation: str,
        idempotency_key: str,
    ) -> TransferResult:
        if not 1 <= len(idempotency_key) <= 200 or not idempotency_key.strip():
            raise BusinessLifecycleError("invalid_idempotency_key")
        with self.pool.connection() as db, db.transaction():
            target = db.execute(
                "select grantee_id::text from public.business_client_grants where id=%s and space_id=%s",
                (target_grant_id, space_id),
            ).fetchone()
            if target:
                self._lock_people(db, owner_id, target[0])
            name, closed_at = PostgresBusinessLifecycle._owned_space(
                db, owner_id, space_id
            )
            if closed_at is not None:
                raise BusinessLifecycleError("business_record_not_found")
            _lock(db, space_id)
            old = db.execute(
                f"select {_COLUMNS},target_grant_id::text,confirmation from public.business_ownership_transfers where space_id=%s and owner_id=%s and idempotency_key=%s",
                (space_id, owner_id, idempotency_key),
            ).fetchone()
            if old:
                if old[5:] != (target_grant_id, confirmation):
                    raise BusinessLifecycleError("idempotency_conflict")
                return TransferResult(*old[:5])
            if confirmation != name:
                raise BusinessLifecycleError("business_name_mismatch")
            target = self._target(db, space_id, target_grant_id, owner_id)
            if db.execute(
                "select 1 from public.business_ownership_transfers where space_id=%s and status='pending'",
                (space_id,),
            ).fetchone():
                raise BusinessLifecycleError("business_transfer_pending")
            row = db.execute(
                f"insert into public.business_ownership_transfers(space_id,owner_id,target_id,target_grant_id,confirmation,idempotency_key) values(%s,%s,%s,%s,%s,%s) returning {_COLUMNS}",
                (
                    space_id,
                    owner_id,
                    target,
                    target_grant_id,
                    confirmation,
                    idempotency_key,
                ),
            ).fetchone()
            return TransferResult(*row)

    def accept(self, *, actor_id: str, transfer_id: str) -> TransferResult:
        return self._resolve(actor_id, transfer_id, resolution="accepted")

    def cancel(self, *, owner_id: str, transfer_id: str) -> TransferResult:
        return self._resolve(owner_id, transfer_id, resolution="cancelled")

    def decline(self, *, actor_id: str, transfer_id: str) -> TransferResult:
        return self._resolve(actor_id, transfer_id, resolution="declined")

    def _resolve(
        self,
        actor_id: str,
        transfer_id: str,
        *,
        resolution: Literal["accepted", "cancelled", "declined"],
    ) -> TransferResult:
        accept = resolution == "accepted"
        recipient = resolution != "cancelled"
        with self.pool.connection() as db, db.transaction():
            command = db.execute(
                f"select {_COLUMNS},target_grant_id::text from public.business_ownership_transfers where id=%s",
                (transfer_id,),
            ).fetchone()
            if not command or actor_id != command[3 if recipient else 2]:
                raise BusinessLifecycleError("business_record_not_found")
            self._lock_people(db, command[2], command[3])
            live = db.execute(
                "select id from auth.users where id=%s and coalesce(is_anonymous,false)=false and (banned_until is null or banned_until<=clock_timestamp()) for no key update",
                (actor_id,),
            ).fetchone()
            if not live:
                raise BusinessLifecycleError(
                    "business_transfer_target_invalid"
                    if accept
                    else "business_record_not_found"
                )
            space = db.execute(
                "select current_owner_id::text,closed_at from public.spaces where id=%s for update",
                (command[1],),
            ).fetchone()
            _lock(db, command[1])
            command = db.execute(
                f"select {_COLUMNS},target_grant_id::text from public.business_ownership_transfers where id=%s for update",
                (transfer_id,),
            ).fetchone()
            expected = resolution
            if command[4] == expected:
                return TransferResult(*command[:5])
            if command[4] != "pending":
                raise BusinessLifecycleError("business_transfer_not_pending")
            if not space or space != (command[2], None):
                raise BusinessLifecycleError("business_record_not_found")
            PostgresBusinessLifecycle._owned_space(db, command[2], command[1])
            if recipient:
                from uuid import UUID

                from argus.domain.business.authority import ActionError, authorize
                from argus.domain.business.contracts.authority import TrustedActor

                try:
                    authorize(
                        db,
                        TrustedActor(
                            actor_id=UUID(actor_id),
                            actor_kind="member",
                            space_id=UUID(command[1]),
                        ),
                        UUID(command[5]),
                    ).require("prepare")
                except ActionError:
                    raise BusinessLifecycleError(
                        "business_transfer_target_invalid"
                    ) from None
            if accept:
                self._target(db, command[1], command[5], command[2])
                db.execute(
                    "update public.business_client_grants set capabilities=%s::text[] where space_id=%s and grantee_id=%s and revoked_at is null",
                    (list(MEMBER_CAPABILITIES), command[1], command[2]),
                )
                db.execute(
                    "update public.business_receipt_reading_consents set revoked_at=clock_timestamp() where space_id=%s and revoked_at is null",
                    (command[1],),
                )
                db.execute(
                    "update public.business_ai_consents set revoked_at=clock_timestamp(),revoked_by=null,invalidated_by_transfer_id=%s where space_id=%s and revoked_at is null",
                    (transfer_id, command[1]),
                )
                db.execute(
                    "update public.spaces set current_owner_id=%s where id=%s",
                    (actor_id, command[1]),
                )
                db.execute(
                    "update public.business_client_grants set issuer_id=%s where space_id=%s",
                    (actor_id, command[1]),
                )
                db.execute(
                    "update public.business_client_grants set capabilities=%s::text[],expires_at=null where id=%s",
                    (list(OWNER_CAPABILITIES), command[5]),
                )
                db.execute(
                    "update public.business_access_invites set issuer_id=%s where space_id=%s",
                    (actor_id, command[1]),
                )
            row = db.execute(
                f"update public.business_ownership_transfers set status=%s,resolved_at=clock_timestamp() where id=%s returning {_COLUMNS}",
                (expected, transfer_id),
            ).fetchone()
            return TransferResult(*row)

    @staticmethod
    def _lock_people(db: Connection, owner_id: str, target_id: str) -> None:
        db.execute(
            "select id from auth.users where id=any(%s::uuid[]) order by id for no key update",
            ([owner_id, target_id],),
        ).fetchall()

    @staticmethod
    def _target(db: Connection, space_id: str, grant_id: str, owner_id: str) -> str:
        row = db.execute(
            "select g.grantee_id::text from public.business_client_grants g join auth.users u on u.id=g.grantee_id where g.id=%s and g.space_id=%s and g.grantee_id<>%s and g.revoked_at is null and (g.expires_at is null or g.expires_at>clock_timestamp()) and 'read'=any(g.capabilities) and 'prepare'=any(g.capabilities) and not 'approve'=any(g.capabilities) and coalesce(u.is_anonymous,false)=false and u.email_confirmed_at is not null and (u.banned_until is null or u.banned_until<=clock_timestamp()) and not exists(select 1 from argus_private.account_deletion_runs d where d.user_id=g.grantee_id) and not exists(select 1 from public.spaces s where s.current_owner_id=g.grantee_id and s.kind='business' and s.closed_at is null) for share of g,u",
            (grant_id, space_id, owner_id),
        ).fetchone()
        if not row:
            raise BusinessLifecycleError("business_transfer_target_invalid")
        return row[0]
