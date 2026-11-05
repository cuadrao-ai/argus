"""Postgres household store over the financial DATABASE_URL pool."""

from __future__ import annotations

import secrets
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from psycopg_pool import ConnectionPool

from argus.domain.household import invite_record
from argus.domain.household.errors import (
    AccountNotOwned,
    AdminRequired,
    GrantNotFound,
    HouseholdClosed,
    HouseholdNotFound,
    InvitationConsumed,
    InvitationExpired,
    InvitationNotFound,
    InvitationRevoked,
    MemberNotFound,
    MustTransferOrClose,
)
from argus.domain.household.invite_codes import (
    CodeHasher,
    format_code,
    store_code,
    unique_code,
)
from argus.domain.household.repository import (
    INVITE_TTL,
    FinancialAccountLookup,
    code_hasher,
    hash_token,
    locate_secret,
)
from argus.domain.household.schemas import (
    AcceptanceResult,
    AccountGrantRecord,
    AccountShare,
    HouseholdRecord,
    InvitationCreated,
    InvitationMetadata,
    InvitationPreview,
    MemberRecord,
    Permission,
    Recipient,
    SharedAccountView,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PostgresHouseholdRepository:
    # Accept locks the invitation row, then claims it with a guarded update whose
    # row count is checked. Tests clear the lock to prove the check alone still
    # refuses an invitation that changed underneath the read.
    _household_accept_lock = " for update"

    def __init__(
        self,
        pool: ConnectionPool,
        accounts: FinancialAccountLookup,
        *,
        clock=_utcnow,  # noqa: ANN001
        code_hasher: CodeHasher | None = None,
    ) -> None:
        self._pool = pool
        self._accounts = accounts
        self._clock = clock
        self._hasher = code_hasher
        self._current_connection = ContextVar("household_connection", default=None)

    @contextmanager
    def connection(self):
        current = self._current_connection.get()
        if current is not None:
            yield current
            return
        with self._pool.connection() as connection:
            token = self._current_connection.set(connection)
            try:
                yield connection
            finally:
                self._current_connection.reset(token)

    def create_household(
        self, *, user_id: str, name: str | None, display_name: str = "Member"
    ) -> HouseholdRecord:
        now = self._clock()
        hid = str(uuid4())
        trimmed = name.strip() if name and name.strip() else None
        with self.connection() as connection:
            with connection.transaction():
                connection.execute(
                    "insert into public.households"
                    " (id, name, status, created_by, admin_user_id, created_at)"
                    " values (%s, %s, 'active', %s, %s, %s)",
                    (hid, trimmed, user_id, user_id, now),
                )
                connection.execute(
                    "insert into public.household_members"
                    " (id, household_id, user_id, joined_at, display_name)"
                    " values (%s, %s, %s, %s, %s)",
                    (str(uuid4()), hid, user_id, now, display_name),
                )
            return self._load(connection, user_id=user_id, household_id=hid)

    def list_households(self, *, user_id: str) -> list[HouseholdRecord]:
        with self.connection() as connection:
            rows = connection.execute(
                "select h.id from public.households h"
                " join public.household_members m on m.household_id = h.id"
                " where h.status = 'active' and m.user_id = %s and m.left_at is null"
                " order by h.created_at asc",
                (user_id,),
            ).fetchall()
            return [
                self._load(connection, user_id=user_id, household_id=str(row[0]))
                for row in rows
            ]

    def get_household(self, *, user_id: str, household_id: str) -> HouseholdRecord:
        with self.connection() as connection:
            return self._load(connection, user_id=user_id, household_id=household_id)

    def create_invitation(self, *, user_id: str, household_id: str) -> InvitationCreated:
        with self.connection() as connection:
            with connection.transaction():
                self._require_admin(
                    connection, user_id=user_id, household_id=household_id
                )
                now = self._clock()
                token = secrets.token_urlsafe(32)
                code, code_digest = unique_code(connection, code_hasher(self._hasher))
                invite_id = str(uuid4())
                expires = now + INVITE_TTL
                connection.execute(
                    "insert into public.household_invitations"
                    " (id, household_id, token_hash, created_by, created_at,"
                    " expires_at) values (%s, %s, %s, %s, %s, %s)",
                    (
                        invite_id,
                        household_id,
                        hash_token(token),
                        user_id,
                        now,
                        expires,
                    ),
                )
                store_code(connection, code_digest, household_invitation_id=invite_id)
                invite_record.record_sent(
                    connection,
                    kind="household",
                    sender=user_id,
                    at=now,
                    household_invitation_id=invite_id,
                )
                return InvitationCreated(
                    id=invite_id,
                    household_id=household_id,
                    expires_at=expires,
                    token=token,
                    code=format_code(code),
                )

    def revoke_invitation(
        self, *, user_id: str, household_id: str, invitation_id: str
    ) -> None:
        with self.connection() as connection:
            with connection.transaction():
                # Household first (via admin check), then invitation — same order
                # as accept_invitation.
                self._require_admin(
                    connection, user_id=user_id, household_id=household_id
                )
                row = connection.execute(
                    "select accepted_at, revoked_at from public.household_invitations"
                    " where id = %s and household_id = %s for update",
                    (invitation_id, household_id),
                ).fetchone()
                if row is None:
                    raise InvitationNotFound()
                if row[0] is not None:
                    raise InvitationConsumed()
                if row[1] is None:
                    connection.execute(
                        "update public.household_invitations set revoked_at = %s"
                        " where id = %s",
                        (self._clock(), invitation_id),
                    )

    def preview_invitation(
        self, *, user_id: str, token: str | None = None, code: str | None = None
    ) -> InvitationPreview:
        with self.connection() as c:
            column, digest = locate_secret(c, token, code, self._hasher)
            row = c.execute(
                "select h.name,i.expires_at,i.revoked_at,i.accepted_at,h.status from public.household_invitations i join public.households h on h.id=i.household_id where i."  # noqa: S608
                + column
                + "=%s",
                (digest,),
            ).fetchone()
            if row is None:
                raise InvitationNotFound()
            return InvitationPreview(
                name=row[0],
                expires_at=row[1],
                available=row[2] is None
                and row[3] is None
                and row[4] == "active"
                and row[1] > self._clock(),
            )

    def accept_invitation(
        self,
        *,
        user_id: str,
        token: str | None = None,
        display_name: str = "Member",
        code: str | None = None,
    ) -> AcceptanceResult:
        with self.connection() as c, c.transaction():
            column, digest = locate_secret(c, token, code, self._hasher)
            where = " from public.household_invitations where " + column + "=%s"
            located = c.execute("select household_id" + where, (digest,)).fetchone()
            if not located:
                raise InvitationNotFound()
            hid = str(located[0])
            status = c.execute(
                "select status from public.households where id=%s for update", (hid,)
            ).fetchone()[0]
            row = c.execute(
                "select id,expires_at,revoked_at,accepted_by,accepted_at,accepted_membership_id"
                + where
                + self._household_accept_lock,
                (digest,),
            ).fetchone()
            if row[4] is not None:
                if str(row[3]) != user_id or row[5] is None:
                    raise InvitationConsumed()
                member = c.execute(
                    "select left_at from public.household_members where id=%s and user_id=%s",
                    (row[5], user_id),
                ).fetchone()
                return AcceptanceResult(
                    household_id=hid,
                    membership_id=str(row[5]),
                    state="active"
                    if member and member[0] is None and status == "active"
                    else "departed",
                )
            if row[2] is not None:
                raise InvitationRevoked()
            if row[1] <= self._clock():
                raise InvitationExpired()
            if status != "active":
                raise HouseholdClosed()
            active = c.execute(
                "select id from public.household_members where household_id=%s and user_id=%s and left_at is null",
                (hid, user_id),
            ).fetchone()
            mid = str(active[0]) if active else str(uuid4())
            if not active:
                c.execute(
                    "insert into public.household_members(id,household_id,user_id,joined_at,display_name) values(%s,%s,%s,%s,%s)",
                    (mid, hid, user_id, self._clock(), display_name),
                )
            accepted_at = self._clock()
            claimed = c.execute(
                "update public.household_invitations set accepted_by=%s,accepted_at=%s,"
                "accepted_membership_id=%s where id=%s and accepted_at is null"
                " and revoked_at is null",
                (user_id, accepted_at, mid, row[0]),
            ).rowcount
            if claimed != 1:
                # Behind the row lock this cannot miss; if it ever does, the
                # whole acceptance (membership included) rolls back.
                raise InvitationConsumed()
            # Accepting a household invite also lets the person into the beta.
            invite_record.record_household_accepted(
                c, invitation_id=str(row[0]), acceptor=user_id, at=accepted_at
            )
            return AcceptanceResult(household_id=hid, membership_id=mid, state="active")

    def leave(self, *, user_id: str, household_id: str) -> None:
        with self.connection() as connection:
            with connection.transaction():
                household = self._require_member_row(
                    connection, user_id=user_id, household_id=household_id
                )
                if str(household["admin_user_id"]) == user_id:
                    raise MustTransferOrClose()
                self._end_membership(
                    connection, household_id=household_id, user_id=user_id
                )

    def remove_member(
        self, *, admin_user_id: str, household_id: str, member_user_id: str
    ) -> None:
        with self.connection() as connection:
            with connection.transaction():
                self._require_admin(
                    connection, user_id=admin_user_id, household_id=household_id
                )
                if member_user_id == admin_user_id:
                    raise MustTransferOrClose()
                row = connection.execute(
                    "select 1 from public.household_members"
                    " where household_id = %s and user_id = %s and left_at is null",
                    (household_id, member_user_id),
                ).fetchone()
                if row is None:
                    raise MemberNotFound()
                self._end_membership(
                    connection, household_id=household_id, user_id=member_user_id
                )

    def transfer_admin(
        self, *, admin_user_id: str, household_id: str, new_admin_user_id: str
    ) -> HouseholdRecord:
        with self.connection() as connection:
            with connection.transaction():
                self._require_admin(
                    connection, user_id=admin_user_id, household_id=household_id
                )
                if new_admin_user_id != admin_user_id:
                    row = connection.execute(
                        "select 1 from public.household_members"
                        " where household_id = %s and user_id = %s and left_at is null",
                        (household_id, new_admin_user_id),
                    ).fetchone()
                    if row is None:
                        raise MemberNotFound()
                    connection.execute(
                        "update public.households set admin_user_id = %s where id = %s",
                        (new_admin_user_id, household_id),
                    )
                return self._load(
                    connection, user_id=admin_user_id, household_id=household_id
                )

    def close(self, *, user_id: str, household_id: str) -> HouseholdRecord:
        with self.connection() as connection:
            with connection.transaction():
                household = self._require_admin(
                    connection, user_id=user_id, household_id=household_id
                )
                self._close_locked(connection, household_id=household_id)
                # Caller is no longer an active member after close; return closed view.
                row = connection.execute(
                    "select id, name, status, admin_user_id, created_by, created_at, closed_at"
                    " from public.households where id = %s",
                    (household_id,),
                ).fetchone()
                assert row is not None
                return HouseholdRecord(
                    version=household["version"],
                    id=str(row[0]),
                    name=row[1],
                    status=row[2],
                    admin_user_id=str(row[3]) if row[3] is not None else None,
                    created_by=str(row[4]) if row[4] is not None else None,
                    created_at=row[5],
                    closed_at=row[6],
                    members=[],
                )

    def create_grant(
        self,
        *,
        user_id: str,
        household_id: str,
        account_id: str,
        permission: Permission,
        recipient_membership_id: str,
    ) -> AccountGrantRecord:
        with self.connection() as c, c.transaction():
            h = self._require_member_row(c, user_id=user_id, household_id=household_id)
            owner = c.execute(
                "select id from public.household_members where household_id=%s and user_id=%s and left_at is null",
                (household_id, user_id),
            ).fetchone()[0]
            if (
                self._accounts.owned_account(user_id=user_id, account_id=account_id)
                is None
            ):
                raise AccountNotOwned()
            recipient = c.execute(
                "select id from public.household_members where id=%s and household_id=%s and user_id<>%s and left_at is null",
                (recipient_membership_id, h["id"], user_id),
            ).fetchone()
            if not recipient:
                raise MemberNotFound()
            row = c.execute(
                "select id from public.household_account_grants where household_id=%s and account_id=%s and recipient_membership_id=%s and revoked_at is null",
                (household_id, account_id, recipient_membership_id),
            ).fetchone()
            gid = str(row[0]) if row else str(uuid4())
            if row:
                c.execute(
                    "update public.household_account_grants set permission=%s where id=%s",
                    (permission, gid),
                )
            else:
                c.execute(
                    "insert into public.household_account_grants(id,household_id,account_id,owner_user_id,owner_membership_id,recipient_membership_id,permission,created_at) values(%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        gid,
                        household_id,
                        account_id,
                        user_id,
                        owner,
                        recipient_membership_id,
                        permission,
                        self._clock(),
                    ),
                )
            return self._grant(c, gid)

    def _grant(self, c, gid):
        row = c.execute(
            "select id,household_id,account_id,owner_user_id,owner_membership_id,recipient_membership_id,permission,created_at,revoked_at from public.household_account_grants where id=%s",
            (gid,),
        ).fetchone()
        if row is None:
            raise GrantNotFound()
        return AccountGrantRecord(
            id=str(row[0]),
            household_id=str(row[1]),
            account_id=str(row[2]),
            owner_user_id=str(row[3]),
            owner_membership_id=str(row[4]),
            recipient_membership_id=str(row[5]),
            permission=row[6],
            created_at=row[7],
            revoked_at=row[8],
        )

    def update_grant(
        self, *, user_id: str, household_id: str, grant_id: str, permission: Permission
    ) -> AccountGrantRecord:
        with self.connection() as c, c.transaction():
            self._require_member_row(c, user_id=user_id, household_id=household_id)
            grant = self._grant(c, grant_id)
            if grant.household_id != household_id or grant.revoked_at:
                raise GrantNotFound()
            if grant.owner_user_id != user_id:
                raise AccountNotOwned()
            c.execute(
                "update public.household_account_grants set permission=%s where id=%s",
                (permission, grant_id),
            )
            return self._grant(c, grant_id)

    def revoke_grant(self, *, user_id: str, household_id: str, grant_id: str) -> None:
        with self.connection() as c, c.transaction():
            h = self._require_member_row(c, user_id=user_id, household_id=household_id)
            grant = self._grant(c, grant_id)
            if grant.household_id != household_id or grant.revoked_at:
                raise GrantNotFound()
            if grant.owner_user_id != user_id and h["admin_user_id"] != user_id:
                raise AdminRequired()
            c.execute(
                "update public.household_account_grants set revoked_at=%s where id=%s",
                (self._clock(), grant_id),
            )

    def replace_grants(
        self, *, user_id: str, household_id: str, account_id: str, recipients: list
    ) -> None:
        with self.connection() as c, c.transaction():
            self._require_member_row(c, user_id=user_id, household_id=household_id)
            if (
                self._accounts.owned_account(user_id=user_id, account_id=account_id)
                is None
            ):
                raise AccountNotOwned()
            if len({r.membership_id for r in recipients}) != len(recipients):
                raise MemberNotFound()
            for recipient in recipients:
                self.create_grant(
                    user_id=user_id,
                    household_id=household_id,
                    account_id=account_id,
                    permission=recipient.permission,
                    recipient_membership_id=recipient.membership_id,
                )
            c.execute(
                "update public.household_account_grants set revoked_at=%s where household_id=%s and account_id=%s and revoked_at is null and not(recipient_membership_id=any(%s::uuid[]))",
                (
                    self._clock(),
                    household_id,
                    account_id,
                    [r.membership_id for r in recipients],
                ),
            )

    def list_shared_accounts(
        self, *, user_id: str, household_id: str
    ) -> list[SharedAccountView]:
        from .access import resolve

        with self.connection() as c, c.transaction():
            h = self._require_member_row(c, user_id=user_id, household_id=household_id)
            scope = resolve(c, user_id, h, {"id": h["membership_id"]})
            views = []
            for aid, access in scope.accounts.items():
                account = self._accounts.account_by_id(account_id=aid)
                if account is not None:
                    grant = c.execute(
                        "select id from public.household_account_grants where household_id=%s and account_id=%s and revoked_at is null order by id limit 1",
                        (household_id, aid),
                    ).fetchone()
                    views.append(
                        SharedAccountView(
                            grant_id=str(grant[0]),
                            account_id=aid,
                            owner_user_id=access.owner_id,
                            permission=access.permission,
                            **account.model_dump(exclude={"id", "user_id"}),
                        )
                    )
            return views

    def _close_locked(self, connection, *, household_id: str) -> None:  # noqa: ANN001
        now = self._clock()
        from .planning_retention import retain_membership
        from .planning_store import archive_owner

        for (member,) in connection.execute(
            "select user_id from public.household_members where household_id=%s and left_at is null order by user_id",
            (household_id,),
        ).fetchall():
            retain_membership(
                connection, household_id, str(member), now, self._accounts._repository
            )
        for (owner,) in connection.execute(
            "select distinct owner_user_id from public.household_plan_bindings where household_id=%s and departed_at is null and revoked_at is null order by owner_user_id",
            (household_id,),
        ).fetchall():
            archive_owner(
                connection, household_id, str(owner), now, self._accounts._repository
            )
        connection.execute(
            "update public.households set status = 'closed', closed_at = %s"
            " where id = %s and status = 'active'",
            (now, household_id),
        )
        connection.execute(
            "update public.household_members set left_at = %s"
            " where household_id = %s and left_at is null",
            (now, household_id),
        )
        connection.execute(
            "update public.household_invitations set revoked_at = %s"
            " where household_id = %s and revoked_at is null and accepted_at is null",
            (now, household_id),
        )
        connection.execute(
            "update public.household_account_grants set revoked_at = %s"
            " where household_id = %s and revoked_at is null",
            (now, household_id),
        )

    def _end_membership(
        self,
        connection,
        *,
        household_id: str,
        user_id: str,  # noqa: ANN001
    ) -> None:
        now = self._clock()
        from .planning_retention import retain_membership
        from .planning_store import archive_owner

        retain_membership(
            connection, household_id, user_id, now, self._accounts._repository
        )
        archive_owner(connection, household_id, user_id, now, self._accounts._repository)
        connection.execute(
            "update public.household_members set left_at = %s"
            " where household_id = %s and user_id = %s and left_at is null",
            (now, household_id, user_id),
        )
        connection.execute(
            "update public.household_account_grants set revoked_at = %s"
            " where household_id = %s and revoked_at is null and (owner_user_id = %s or recipient_membership_id in (select id from public.household_members where household_id=%s and user_id=%s))",
            (now, household_id, user_id, household_id, user_id),
        )

    def _require_admin(
        self,
        connection,
        *,
        user_id: str,
        household_id: str,  # noqa: ANN001
    ) -> dict[str, Any]:
        household = self._require_member_row(
            connection, user_id=user_id, household_id=household_id
        )
        if str(household["admin_user_id"]) != user_id:
            raise AdminRequired()
        return household

    def _require_member_row(
        self,
        connection,
        *,
        user_id: str,
        household_id: str,  # noqa: ANN001
    ) -> dict[str, Any]:
        row = connection.execute(
            "select id,name,status,admin_user_id,created_by,created_at,closed_at,version from public.households where id=%s for update",
            (household_id,),
        ).fetchone()
        if row is None or row[2] != "active":
            raise HouseholdNotFound()
        # Read membership after obtaining the household lock, including after waits.
        member = connection.execute(
            "select id from public.household_members where household_id=%s and user_id=%s and left_at is null",
            (household_id, user_id),
        ).fetchone()
        if member is None:
            raise HouseholdNotFound()
        return {
            "id": str(row[0]),
            "name": row[1],
            "status": row[2],
            "admin_user_id": str(row[3]) if row[3] is not None else None,
            "created_by": str(row[4]) if row[4] is not None else None,
            "created_at": row[5],
            "closed_at": row[6],
            "version": row[7],
            "membership_id": str(member[0]),
        }

    def _load(
        self,
        connection,
        *,
        user_id: str,
        household_id: str,  # noqa: ANN001
    ) -> HouseholdRecord:
        household = self._require_member_row(
            connection, user_id=user_id, household_id=household_id
        )
        members = connection.execute(
            "select user_id, joined_at,id,display_name from public.household_members"
            " where household_id = %s and left_at is null order by joined_at asc",
            (household_id,),
        ).fetchall()
        return HouseholdRecord(
            version=household["version"],
            membership_id=household["membership_id"],
            admin_membership_id=next(
                (str(m[2]) for m in members if str(m[0]) == household["admin_user_id"]),
                None,
            ),
            invitations=self._invitations(connection, household_id)
            if household["admin_user_id"] == user_id
            else [],
            shares=self._shares(connection, user_id, household_id),
            id=household["id"],
            name=household["name"],
            status=household["status"],
            admin_user_id=household["admin_user_id"],
            created_by=household["created_by"],
            created_at=household["created_at"],
            closed_at=household["closed_at"],
            members=[
                MemberRecord(
                    membership_id=str(row[2]),
                    display_name=row[3],
                    is_self=str(row[0]) == user_id,
                    is_admin=str(row[0]) == household["admin_user_id"],
                    user_id=str(row[0]),
                    role=(
                        "admin" if str(row[0]) == household["admin_user_id"] else "member"
                    ),
                    joined_at=row[1],
                )
                for row in members
            ],
        )

    def _invitations(self, c, hid):
        return [
            InvitationMetadata(
                id=str(r[0]),
                expires_at=r[1],
                state="accepted"
                if r[3]
                else "revoked"
                if r[2]
                else "expired"
                if r[1] <= self._clock()
                else "pending",
            )
            for r in c.execute(
                "select id,expires_at,revoked_at,accepted_at from public.household_invitations where household_id=%s order by created_at",
                (hid,),
            ).fetchall()
        ]

    def _shares(self, c, actor, hid):
        values = {}
        for aid, mid, permission in c.execute(
            "select account_id,recipient_membership_id,permission from public.household_account_grants where household_id=%s and owner_user_id=%s and revoked_at is null order by account_id,id",
            (hid, actor),
        ).fetchall():
            values.setdefault(str(aid), []).append(
                Recipient(membership_id=str(mid), permission=permission)
            )
        return [
            AccountShare(account_id=aid, recipients=recipients)
            for aid, recipients in values.items()
        ]
