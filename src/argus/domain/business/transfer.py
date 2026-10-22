"""A pending command transfers authority only when its live target accepts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from psycopg import Connection
from psycopg_pool import ConnectionPool

from argus.domain.business.access import MEMBER_CAPABILITIES, OWNER_CAPABILITIES, _lock
from argus.domain.business.authority import ActionError, authorize
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.lifecycle import (
    BusinessLifecycleError,
    PostgresBusinessLifecycle,
)
from argus.domain.business.transfer_mail import (
    deliver_transfer_mail,
    enqueue_transfer_mail,
)


@dataclass(frozen=True)
class TransferResult:
    id: str
    space_id: str
    owner_id: str
    target_id: str
    status: Literal["pending", "accepted", "cancelled", "declined", "expired"]
    expires_at: datetime | None = None


@dataclass(frozen=True)
class TransferDetails(TransferResult):
    business_name: str = ""
    owner_name: str = ""
    target_name: str = ""
    role: Literal["owner", "target"] = "target"
    grant_id: str = ""


#: Why a live member cannot take ownership: the account is unusable, the
#: grant is not Editar, the email is unconfirmed, or they own an open Business.
TransferIneligible = Literal[
    "account_unavailable", "not_editor", "email_unconfirmed", "owns_open_business"
]

_COLUMNS = "id::text,space_id::text,owner_id::text,target_id::text,case when status='pending' and expires_at<=clock_timestamp() then 'expired' else status end,expires_at"


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
        result = self._request(
            owner_id=owner_id,
            space_id=space_id,
            target_grant_id=target_grant_id,
            confirmation=confirmation,
            idempotency_key=idempotency_key,
        )
        deliver_transfer_mail(self.pool, result.id)
        return result

    def _request(
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
            db.execute(
                "update public.business_ownership_transfers set status='expired',resolved_at=clock_timestamp()"
                " where space_id=%s and status='pending' and expires_at<=clock_timestamp()",
                (space_id,),
            )
            old = db.execute(
                f"select {_COLUMNS},target_grant_id::text,confirmation from public.business_ownership_transfers where space_id=%s and owner_id=%s and idempotency_key=%s",
                (space_id, owner_id, idempotency_key),
            ).fetchone()
            if old:
                if old[6:] != (target_grant_id, confirmation):
                    raise BusinessLifecycleError("idempotency_conflict")
                return TransferResult(*old[:6])
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
            enqueue_transfer_mail(db, row[0], "pending")
            return TransferResult(*row)

    def accept(self, *, actor_id: str, transfer_id: str) -> TransferResult:
        return self._command(actor_id, transfer_id, "accepted")

    def cancel(self, *, owner_id: str, transfer_id: str) -> TransferResult:
        return self._command(owner_id, transfer_id, "cancelled")

    def decline(self, *, actor_id: str, transfer_id: str) -> TransferResult:
        return self._command(actor_id, transfer_id, "declined")

    def _command(
        self,
        actor_id: str,
        transfer_id: str,
        resolution: Literal["accepted", "cancelled", "declined"],
    ) -> TransferResult:
        result = self._resolve(actor_id, transfer_id, resolution=resolution)
        deliver_transfer_mail(self.pool, result.id)
        return result

    def discover(self, *, actor_id: str) -> tuple[TransferDetails, ...]:
        with self.pool.connection() as db:
            rows = db.execute(
                f"with participant(id,space_id,owner_id,target_id,status,expires_at) as (select {_COLUMNS} from public.business_ownership_transfers t"
                " where (owner_id=%s or target_id=%s) and exists("
                " select 1 from public.spaces s join public.business_client_grants g on g.space_id=s.id"
                " join auth.users u on u.id=g.grantee_id where s.id=t.space_id and s.closed_at is null"
                " and g.grantee_id=%s and g.revoked_at is null"
                " and (g.expires_at is null or g.expires_at>clock_timestamp())"
                " and 'read'=any(g.capabilities) and coalesce(u.is_anonymous,false)=false"
                " and (u.banned_until is null or u.banned_until<=clock_timestamp()))"
                " order by created_at desc,id)"
                " select t.*,s.name,coalesce(nullif(btrim(p.display_name),''),p.username,'Member'),"
                " coalesce(nullif(btrim(q.display_name),''),q.username,'Member'),"
                " (select g.id::text from public.business_client_grants g where g.space_id=t.space_id::uuid"
                " and g.grantee_id=%s and g.revoked_at is null and 'read'=any(g.capabilities)"
                " and (g.expires_at is null or g.expires_at>clock_timestamp()) order by g.created_at,g.id limit 1)"
                " from participant t join public.spaces s on s.id=t.space_id::uuid"
                " left join public.profiles p on p.id=t.owner_id::uuid"
                " left join public.profiles q on q.id=t.target_id::uuid",
                (actor_id, actor_id, actor_id, actor_id),
            ).fetchall()
            details = []
            for row in rows:
                if not row[9]:
                    continue
                try:
                    authorize(
                        db,
                        TrustedActor(
                            actor_id=UUID(actor_id),
                            actor_kind="member",
                            space_id=UUID(row[1]),
                        ),
                        UUID(row[9]),
                    ).require("read")
                except ActionError:
                    continue
                details.append(
                    TransferDetails(
                        *row[:9], "owner" if actor_id == row[2] else "target", row[9]
                    )
                )
        return tuple(details)

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
                return TransferResult(*command[:6])
            if command[4] == "expired":
                raise BusinessLifecycleError("business_transfer_expired")
            if command[4] != "pending":
                raise BusinessLifecycleError("business_transfer_not_pending")
            resolved_at = db.execute("select clock_timestamp()").fetchone()[0]
            if resolved_at >= command[5]:
                raise BusinessLifecycleError("business_transfer_expired")
            if not space or space != (command[2], None):
                raise BusinessLifecycleError("business_record_not_found")
            PostgresBusinessLifecycle._owned_space(db, command[2], command[1])
            if recipient:
                try:
                    authorize(
                        db,
                        TrustedActor(
                            actor_id=UUID(actor_id),
                            actor_kind="member",
                            space_id=UUID(command[1]),
                        ),
                        UUID(command[6]),
                    ).require("prepare")
                except ActionError:
                    raise BusinessLifecycleError(
                        "business_transfer_target_invalid"
                    ) from None
            if accept:
                self._target(db, command[1], command[6], command[2])
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
                    (list(OWNER_CAPABILITIES), command[6]),
                )
                db.execute(
                    "update public.business_access_invites set issuer_id=%s where space_id=%s",
                    (actor_id, command[1]),
                )
            row = db.execute(
                f"update public.business_ownership_transfers set status=%s,resolved_at=%s where id=%s returning {_COLUMNS}",
                (expected, resolved_at, transfer_id),
            ).fetchone()
            enqueue_transfer_mail(db, transfer_id, expected)
            return TransferResult(*row)

    @staticmethod
    def _lock_people(db: Connection, owner_id: str, target_id: str) -> None:
        db.execute(
            "select id from auth.users where id=any(%s::uuid[]) order by id for no key update",
            ([owner_id, target_id],),
        ).fetchall()

    @staticmethod
    def eligibility(
        db: Connection, space_id: str, grant_id: str, owner_id: str
    ) -> tuple[str, TransferIneligible | None] | None:
        """The member a live grant names, with why they cannot take ownership,
        or None when they can; None for a grant that is not a live member's."""
        row = db.execute(
            "select g.grantee_id::text,"
            " not coalesce(u.is_anonymous,false) and (u.banned_until is null or u.banned_until<=clock_timestamp())"
            "  and not exists(select 1 from argus_private.account_deletion_runs d where d.user_id=g.grantee_id),"
            " 'prepare'=any(g.capabilities) and not 'approve'=any(g.capabilities),"
            " u.email_confirmed_at is not null,"
            " not exists(select 1 from public.spaces s where s.current_owner_id=g.grantee_id and s.kind='business' and s.closed_at is null)"
            " from public.business_client_grants g join auth.users u on u.id=g.grantee_id"
            " where g.id=%s and g.space_id=%s and g.grantee_id<>%s and g.revoked_at is null"
            " and (g.expires_at is null or g.expires_at>clock_timestamp()) and 'read'=any(g.capabilities)"
            " for share of g,u",
            (grant_id, space_id, owner_id),
        ).fetchone()
        if not row:
            return None
        grantee, *facts = row
        reasons: tuple[TransferIneligible, ...] = (
            "account_unavailable",
            "not_editor",
            "email_unconfirmed",
            "owns_open_business",
        )
        return grantee, next(
            (r for r, ok in zip(reasons, facts, strict=True) if not ok), None
        )

    @staticmethod
    def _target(db: Connection, space_id: str, grant_id: str, owner_id: str) -> str:
        found = PostgresBusinessTransfer.eligibility(db, space_id, grant_id, owner_id)
        if found is None or found[1] is not None:
            raise BusinessLifecycleError("business_transfer_target_invalid")
        return found[0]
