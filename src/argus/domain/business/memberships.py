"""Transactional membership and invitation commands."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Literal, TypedDict
from uuid import UUID

from psycopg import Connection
from psycopg_pool import ConnectionPool

from argus.domain.business.roles import (
    ROLE_PERMISSIONS,
    BusinessRole,
    legacy_capabilities,
    promotion_requires_acceptance,
)

if TYPE_CHECKING:
    from argus.domain.business.access import AccessList, RevokeGrantResult

DeliveryState = Literal[
    "accepted", "failed", "not_configured", "pending", "sending", "uncertain"
]


class InvitationCommandResult(TypedDict):
    invite_id: str | None
    state: Literal["already_member", "accepted", "revoked", "pending", "expired"]
    delivery: DeliveryState | None


class RecipientInvitation(TypedDict):
    id: str
    space_id: str
    name: str
    requested_role: BusinessRole
    expires_at: datetime


class MembershipError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def require_manager(
    connection: Connection, space_id: str, actor_id: str, role: BusinessRole | None = None
) -> str:
    from argus.domain.business.access import _lock

    _lock(connection, space_id)
    row = connection.execute(
        "select g.id::text,g.business_role from public.business_client_grants g"
        " join public.spaces s on s.id=g.space_id join auth.users u on u.id=g.grantee_id"
        " where g.space_id=%s and g.grantee_id=%s and g.revoked_at is null"
        " and (g.expires_at is null or g.expires_at>clock_timestamp())"
        " and s.closed_at is null and s.kind='business' and not coalesce(u.is_anonymous,false)"
        " and (u.banned_until is null or u.banned_until<=clock_timestamp())"
        " and not exists(select 1 from argus_private.account_deletion_runs d where d.user_id=u.id)"
        " order by g.created_at limit 1",
        (space_id, actor_id),
    ).fetchone()
    if row is None or "manage" not in ROLE_PERMISSIONS[BusinessRole(row[1])]:
        raise MembershipError("business_permission_denied")
    if role == BusinessRole.OWNER and row[1] != "owner":
        raise MembershipError("business_permission_denied")
    return row[0]


def remember_command(
    db: Connection,
    space_id: str,
    actor_id: str,
    command_key: str | None,
    email: str,
    role: BusinessRole,
    invite_id: str | None,
) -> None:
    if command_key:
        db.execute(
            "insert into argus_private.business_invitation_commands(space_id,actor_id,command_key,email,requested_role,invite_id)"
            " values(%s,%s,%s,%s,%s,%s)",
            (space_id, actor_id, command_key, email, role.value, invite_id),
        )


class PostgresMembershipCommands:
    pool: ConnectionPool

    def give(
        self,
        space_id: str,
        owner_id: str,
        email: str,
        role: BusinessRole = BusinessRole.EDITOR,
        command_key: str | None = None,
    ) -> tuple[bool, AccessList]:
        with self.pool.connection() as db, db.transaction():
            return self._give(db, space_id, owner_id, email, role, command_key)

    def _give(
        self,
        db: Connection,
        space_id: str,
        owner_id: str,
        email: str,
        role: BusinessRole = BusinessRole.EDITOR,
        command_key: str | None = None,
    ) -> tuple[bool, AccessList]:
        from argus.domain.business.access import (
            INVITE_LIFETIME,
            AccessCommand,
            _record,
            normalize_email,
        )

        role, email = BusinessRole(role), normalize_email(email)
        if command_key is not None and (
            not command_key.strip() or len(command_key) > 200
        ):
            raise MembershipError("invalid_idempotency_key")
        actor_grant = require_manager(db, space_id, owner_id, role)
        if command_key:
            previous = db.execute(
                "select email,requested_role from argus_private.business_invitation_commands"
                " where space_id=%s and actor_id=%s and command_key=%s",
                (space_id, owner_id, command_key),
            ).fetchone()
            if previous:
                if previous != (email, role.value):
                    raise MembershipError("idempotency_conflict")
                return False, self._list(db, space_id, owner_id)
        existing = db.execute(
            "select g.id::text,g.business_role,g.membership_version,g.grantee_id::text from public.business_client_grants g join auth.users u on u.id=g.grantee_id"
            " where g.space_id=%s and lower(u.email)=%s and g.revoked_at is null"
            " and (g.expires_at is null or g.expires_at>clock_timestamp())",
            (space_id, email),
        ).fetchone()
        if existing:
            if existing[1] == role.value:
                remember_command(db, space_id, owner_id, command_key, email, role, None)
                return False, self._list(db, space_id, owner_id)
            if existing[3] == owner_id:
                raise MembershipError("business_self_role_change_forbidden")
            require_manager(db, space_id, owner_id, BusinessRole(existing[1]))
            if not promotion_requires_acceptance(BusinessRole(existing[1]), role):
                raise MembershipError("business_role_change_requires_member_command")
        pending = db.execute(
            "select id::text,requested_role,expires_at>clock_timestamp() from public.business_access_invites"
            " where space_id=%s and email=%s and revoked_at is null and accepted_at is null for update",
            (space_id, email),
        ).fetchone()
        if pending and pending[2]:
            if pending[1] != role.value:
                raise MembershipError("business_invite_role_conflict")
            remember_command(db, space_id, owner_id, command_key, email, role, pending[0])
            return False, self._list(db, space_id, owner_id)
        if pending:
            db.execute(
                "update public.business_access_invites set revoked_at=clock_timestamp() where id=%s",
                (pending[0],),
            )
        invite = db.execute(
            "insert into public.business_access_invites(space_id,issuer_id,email,requested_role,expires_at,recipient_id,target_grant_id,target_version)"
            " values(%s,%s,%s,%s,clock_timestamp()+%s,(select id from auth.users where lower(email)=%s),%s,%s) returning id::text,expires_at",
            (
                space_id,
                owner_id,
                email,
                role.value,
                INVITE_LIFETIME,
                email,
                existing[0] if existing else None,
                existing[2] if existing else None,
            ),
        ).fetchone()
        remember_command(db, space_id, owner_id, command_key, email, role, invite[0])
        _record(
            db,
            space_id=space_id,
            actor_id=owner_id,
            grant_id=actor_grant,
            issuer_id=owner_id,
            command=AccessCommand(
                action="invite_access",
                invite_id=UUID(invite[0]),
                email=email,
                expires_at=invite[1],
            ),
        )
        return True, self._list(db, space_id, owner_id)

    def resend(self, space_id: str, owner_id: str, invite_id: str) -> AccessList | None:
        from argus.domain.business.access import INVITE_LIFETIME

        with self.pool.connection() as db, db.transaction():
            require_manager(db, space_id, owner_id)
            replacement = db.execute(
                "select requested_role from public.business_access_invites where supersedes_id=%s and space_id=%s"
                " and accepted_at is null and revoked_at is null and expires_at>clock_timestamp()",
                (invite_id, space_id),
            ).fetchone()
            if replacement:
                require_manager(db, space_id, owner_id, BusinessRole(replacement[0]))
                return self._list(db, space_id, owner_id)
            row = db.execute(
                "select email,requested_role,expires_at>clock_timestamp(),target_grant_id,target_version,recipient_id from public.business_access_invites"
                " where id=%s and space_id=%s and accepted_at is null and revoked_at is null for update",
                (invite_id, space_id),
            ).fetchone()
            if row is None:
                return None
            require_manager(db, space_id, owner_id, BusinessRole(row[1]))
            if not row[2]:
                if (
                    row[3] is not None
                    and db.execute(
                        "select 1 from public.business_client_grants where id=%s and space_id=%s"
                        " and grantee_id=%s and membership_version=%s and revoked_at is null"
                        " and (expires_at is null or expires_at>clock_timestamp())",
                        (row[3], space_id, row[5], row[4]),
                    ).fetchone()
                    is None
                ):
                    raise MembershipError("business_invite_membership_changed")
                db.execute(
                    "update public.business_access_invites set revoked_at=clock_timestamp() where id=%s",
                    (invite_id,),
                )
                db.execute(
                    "insert into public.business_access_invites(space_id,issuer_id,email,requested_role,expires_at,recipient_id,target_grant_id,target_version,supersedes_id)"
                    " select space_id,%s,email,requested_role,clock_timestamp()+%s,recipient_id,target_grant_id,target_version,id from public.business_access_invites where id=%s",
                    (owner_id, INVITE_LIFETIME, invite_id),
                )
            return self._list(db, space_id, owner_id)

    def revoke_grant(
        self, space_id: str, owner_id: str, grant_id: str
    ) -> RevokeGrantResult:
        from argus.domain.business.access import AccessCommand, _record

        with self.pool.connection() as db, db.transaction():
            actor_grant = require_manager(db, space_id, owner_id)
            row = db.execute(
                "select grantee_id::text,business_role from public.business_client_grants"
                " where id=%s and space_id=%s and revoked_at is null for update",
                (grant_id, space_id),
            ).fetchone()
            if row is None:
                return "missing"
            if row[0] == owner_id:
                return "own_grant"
            require_manager(db, space_id, owner_id, BusinessRole(row[1]))
            self._retain_owner(db, space_id, grant_id, row[1])
            db.execute(
                "update public.business_client_grants set revoked_at=clock_timestamp() where id=%s",
                (grant_id,),
            )
            _record(
                db,
                space_id=space_id,
                actor_id=owner_id,
                grant_id=actor_grant,
                issuer_id=owner_id,
                command=AccessCommand(action="revoke_grant", grant_id=UUID(grant_id)),
            )
            return "revoked"

    @staticmethod
    def _retain_owner(
        db: Connection, space_id: str, grant_id: str, current_role: str
    ) -> None:
        if (
            current_role == "owner"
            and not db.execute(
                "select 1 from public.business_client_grants where space_id=%s and id<>%s"
                " and business_role='owner' and revoked_at is null and expires_at is null",
                (space_id, grant_id),
            ).fetchone()
        ):
            raise MembershipError("business_last_owner_required")

    def change_role(
        self, space_id: str, actor_id: str, grant_id: str, role: BusinessRole
    ) -> AccessList:
        from argus.domain.business.access import AccessCommand, _record

        role = BusinessRole(role)
        with self.pool.connection() as db, db.transaction():
            actor_grant = require_manager(db, space_id, actor_id, role)
            row = db.execute(
                "select grantee_id::text,business_role from public.business_client_grants"
                " where id=%s and space_id=%s and revoked_at is null for update",
                (grant_id, space_id),
            ).fetchone()
            if row is None:
                raise MembershipError("business_access_not_found")
            if row[0] == actor_id:
                raise MembershipError("business_self_role_change_forbidden")
            require_manager(db, space_id, actor_id, BusinessRole(row[1]))
            if promotion_requires_acceptance(BusinessRole(row[1]), role):
                email = db.execute(
                    "select email from auth.users where id=%s", (row[0],)
                ).fetchone()[0]
                return self._give(db, space_id, actor_id, email, role)[1]
            if role != BusinessRole.OWNER:
                self._retain_owner(db, space_id, grant_id, row[1])
            if row[1] == role.value:
                return self._list(db, space_id, actor_id)
            version = db.execute(
                "update public.business_client_grants set business_role=%s where id=%s returning membership_version",
                (role.value, grant_id),
            ).fetchone()[0]
            _record(
                db,
                space_id=space_id,
                actor_id=actor_id,
                grant_id=actor_grant,
                issuer_id=actor_id,
                command=AccessCommand(
                    action="change_role",
                    grant_id=UUID(grant_id),
                    business_role=role,
                    membership_version=version,
                ),
            )
            return self._list(db, space_id, actor_id)

    def revoke_invite(self, space_id: str, owner_id: str, invite_id: str) -> bool:
        from argus.domain.business.access import AccessCommand, _record

        with self.pool.connection() as db, db.transaction():
            actor_grant = require_manager(db, space_id, owner_id)
            row = db.execute(
                "select email,requested_role from public.business_access_invites where id=%s and space_id=%s"
                " and revoked_at is null and accepted_at is null for update",
                (invite_id, space_id),
            ).fetchone()
            if row is None:
                return False
            require_manager(db, space_id, owner_id, BusinessRole(row[1]))
            db.execute(
                "update public.business_access_invites set revoked_at=clock_timestamp() where id=%s",
                (invite_id,),
            )
            _record(
                db,
                space_id=space_id,
                actor_id=owner_id,
                grant_id=actor_grant,
                issuer_id=owner_id,
                command=AccessCommand(
                    action="revoke_invite", invite_id=UUID(invite_id), email=row[0]
                ),
            )
            return True

    def accept_invites(self, user_id: str) -> int:
        return 0

    def accept_invite(self, user_id: str, space_id: str, invite_id: str) -> str:
        from argus.domain.business.access import AccessCommand, _lock, _record
        from argus.domain.business.lifecycle import require_ownership_admission

        with self.pool.connection() as db, db.transaction():
            person = db.execute(
                "select lower(email) from auth.users where id=%s and email_confirmed_at is not null"
                " and not coalesce(is_anonymous,false) and (banned_until is null or banned_until<=clock_timestamp())"
                " for no key update",
                (user_id,),
            ).fetchone()
            if person is None:
                raise MembershipError("business_invite_recipient_required")
            require_ownership_admission(db, user_id)
            _lock(db, space_id)
            row = db.execute(
                "select i.issuer_id::text,i.email,i.requested_role,i.accepted_grant_id::text,i.accepted_at,"
                " i.revoked_at,i.expires_at>clock_timestamp(),i.target_grant_id::text,i.target_version from public.business_access_invites i"
                " join public.spaces s on s.id=i.space_id where i.id=%s and i.space_id=%s and i.email=%s"
                " and (i.recipient_id is null or i.recipient_id=%s) and s.kind='business' and s.closed_at is null for update of i",
                (invite_id, space_id, person[0], user_id),
            ).fetchone()
            if row is None:
                raise MembershipError("business_invite_not_available")
            if row[4] is not None:
                live = db.execute(
                    "select id::text from public.business_client_grants where id=%s and grantee_id=%s"
                    " and revoked_at is null and (expires_at is null or expires_at>clock_timestamp())",
                    (row[3], user_id),
                ).fetchone()
                if live is None:
                    raise MembershipError("business_grant_not_live")
                return live[0]
            if row[5] is not None or not row[6]:
                raise MembershipError("business_invite_not_available")
            role = BusinessRole(row[2])
            require_manager(db, space_id, row[0], role)
            if row[7] is not None:
                updated = db.execute(
                    "update public.business_client_grants set business_role=%s,expires_at=case when %s='owner' then null else expires_at end where id=%s and space_id=%s and grantee_id=%s"
                    " and membership_version=%s and revoked_at is null and (expires_at is null or expires_at>clock_timestamp()) returning id::text",
                    (role.value, role.value, row[7], space_id, user_id, row[8]),
                ).fetchone()
                if updated is None:
                    raise MembershipError("business_invite_membership_changed")
                grant = updated[0]
            else:
                if db.execute(
                    "select 1 from public.business_client_grants where space_id=%s and grantee_id=%s"
                    " and revoked_at is null and (expires_at is null or expires_at>clock_timestamp())",
                    (space_id, user_id),
                ).fetchone():
                    raise MembershipError("business_membership_already_active")
                grant = db.execute(
                    "insert into public.business_client_grants(space_id,grantee_id,issuer_id,business_role,capabilities)"
                    " values(%s,%s,%s,%s,%s::text[]) returning id::text",
                    (
                        space_id,
                        user_id,
                        row[0],
                        role.value,
                        list(legacy_capabilities(role)),
                    ),
                ).fetchone()[0]
            db.execute(
                "update public.business_access_invites set accepted_at=clock_timestamp(),accepted_grant_id=%s where id=%s",
                (grant, invite_id),
            )
            _record(
                db,
                space_id=space_id,
                actor_id=user_id,
                grant_id=grant,
                issuer_id=row[0],
                command=AccessCommand(
                    action="accept_invite",
                    invite_id=UUID(invite_id),
                    grant_id=UUID(grant),
                    email=row[1],
                ),
            )
            return grant

    def invitations_for(self, user_id: str) -> tuple[RecipientInvitation, ...]:
        with self.pool.connection() as db:
            return tuple(
                RecipientInvitation(
                    id=row[0],
                    space_id=row[1],
                    name=row[2],
                    requested_role=BusinessRole(row[3]),
                    expires_at=row[4],
                )
                for row in db.execute(
                    "select i.id::text,i.space_id::text,s.name,i.requested_role,i.expires_at"
                    " from public.business_access_invites i join public.spaces s on s.id=i.space_id"
                    " join auth.users u on lower(u.email)=i.email where u.id=%s and not coalesce(u.is_anonymous,false)"
                    " and (i.recipient_id is null or i.recipient_id=u.id) and u.email_confirmed_at is not null"
                    " and i.accepted_at is null and i.revoked_at is null and i.expires_at>clock_timestamp() and s.closed_at is null",
                    (user_id,),
                ).fetchall()
            )

    def deliver_invitation(
        self,
        space_id: str,
        actor_id: str,
        invite_id: str,
        send: Callable[[], DeliveryState],
    ) -> DeliveryState:
        with self.pool.connection() as db, db.transaction():
            require_manager(db, space_id, actor_id)
            row = db.execute(
                "select requested_role,delivery_state from public.business_access_invites"
                " where id=%s and space_id=%s and accepted_at is null and revoked_at is null"
                " and expires_at>clock_timestamp() for update",
                (invite_id, space_id),
            ).fetchone()
            if row is None:
                raise MembershipError("business_invite_not_available")
            require_manager(db, space_id, actor_id, BusinessRole(row[0]))
            if row[1] == "accepted":
                return "accepted"
            if row[1] in ("sending", "uncertain"):
                return "uncertain"
            db.execute(
                "update public.business_access_invites set delivery_state='sending' where id=%s",
                (invite_id,),
            )
        with self.pool.connection() as db, db.transaction():
            require_manager(db, space_id, actor_id, BusinessRole(row[0]))
            pending = db.execute(
                "select 1 from public.business_access_invites where id=%s and accepted_at is null and revoked_at is null"
                " and expires_at>clock_timestamp() for update",
                (invite_id,),
            ).fetchone()
            if pending is None:
                raise MembershipError("business_invite_not_available")
            try:
                status = send()
            except Exception:
                status = "uncertain"
            db.execute(
                "update public.business_access_invites set delivery_state=%s where id=%s",
                (status, invite_id),
            )
            return status

    def invitation_command(
        self, space_id: str, actor_id: str, command_key: str
    ) -> InvitationCommandResult | None:
        with self.pool.connection() as db, db.transaction():
            require_manager(db, space_id, actor_id)
            row = db.execute(
                "select c.invite_id::text,i.accepted_at,i.revoked_at,i.expires_at>clock_timestamp(),i.delivery_state"
                " from argus_private.business_invitation_commands c left join public.business_access_invites i on i.id=c.invite_id"
                " where c.space_id=%s and c.actor_id=%s and c.command_key=%s",
                (space_id, actor_id, command_key),
            ).fetchone()
            if row is None:
                return None
            state = (
                "already_member"
                if row[0] is None
                else "accepted"
                if row[1]
                else "revoked"
                if row[2]
                else "pending"
                if row[3]
                else "expired"
            )
            return {
                "invite_id": row[0],
                "state": state,
                "delivery": "uncertain" if row[4] == "sending" else row[4],
            }
