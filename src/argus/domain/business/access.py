"""Who may act in a Business: the owner's own grant and named accountants.

The grant row in ``public.business_client_grants`` stays the only authority.
This module only creates, lists and revokes those rows, plus the pending
invites that become one when a confirmed email signs in. Every change writes
one ``business_action_receipts`` row, so the ledger shows who gave or took
access and when. The owner always holds read, prepare and approve on their
own space; everyone else holds read and prepare at most, and approve is never
handed to an agent.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal, Protocol
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from argus.domain.business.contracts.actions import canonical_input_hash
from argus.domain.business.contracts.authority import ActorProvenance
from argus.domain.business.contracts.facts import Contract

OWNER_CAPABILITIES = ("read", "prepare", "approve")
MEMBER_CAPABILITIES = ("read", "prepare")
INVITE_LIFETIME = timedelta(days=14)
MAX_EMAIL_LENGTH = 254

AccessAction = Literal[
    "owner_grant",
    "grant_access",
    "invite_access",
    "accept_invite",
    "revoke_grant",
    "revoke_invite",
]
RevokeGrantResult = Literal["revoked", "own_grant", "missing"]


class AccessCommand(Contract):
    """The ledger record of one access change."""

    action: AccessAction
    grant_id: UUID | None = None
    invite_id: UUID | None = None
    email: str | None = None


@dataclass(frozen=True)
class AccessGrant:
    id: str
    grantee_id: str
    email: str | None
    display_name: str
    capabilities: tuple[str, ...]
    created_at: datetime
    owner: bool


@dataclass(frozen=True)
class AccessInvite:
    id: str
    email: str
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class AccessList:
    grants: tuple[AccessGrant, ...]
    invites: tuple[AccessInvite, ...]


class InvalidEmail(ValueError):
    pass


def normalize_email(value: str) -> str:
    """One lowercased address with an ``@`` inside, or ``InvalidEmail``."""

    email = value.strip().lower()
    local, separator, domain = email.partition("@")
    if not separator or not local or not domain or any(c.isspace() for c in email):
        raise InvalidEmail("invalid_email")
    if len(email) > MAX_EMAIL_LENGTH:
        raise InvalidEmail("invalid_email")
    return email


class AccessStore(Protocol):
    def ensure_owner_grant(self, space_id: str, owner_id: str) -> bool:
        """The owner's live grant, inserted when missing. True when inserted."""
        ...

    def list(self, space_id: str, owner_id: str) -> AccessList: ...

    def give(self, space_id: str, owner_id: str, email: str) -> tuple[bool, AccessList]:
        """A read+prepare grant for a confirmed account, else a pending invite.

        Returns ``(created, list)``; a replay returns ``False`` and the same list.
        """
        ...

    def revoke_grant(
        self, space_id: str, owner_id: str, grant_id: str
    ) -> RevokeGrantResult: ...

    def revoke_invite(self, space_id: str, owner_id: str, invite_id: str) -> bool: ...

    def accept_invites(self, user_id: str) -> int:
        """Turn the live invites for this person's confirmed email into grants."""
        ...


def _label(display_name: str | None, username: str | None) -> str:
    return (display_name or "").strip() or (username or "").strip() or "Member"


def _lock(connection: Connection, space_id: str) -> None:
    connection.execute(
        "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"business_access:{space_id}",),
    )


def _profiles(connection: Connection, *ids: str) -> dict[str, str]:
    with connection.cursor(row_factory=dict_row) as cursor:
        rows = cursor.execute(
            "select id::text, display_name, username from public.profiles where id = any(%s::uuid[])",
            (list(ids),),
        ).fetchall()
    found = {row["id"]: _label(row["display_name"], row["username"]) for row in rows}
    return {person: found.get(person, "Member") for person in ids}


def _record(
    connection: Connection,
    *,
    space_id: str,
    actor_id: str,
    grant_id: str,
    issuer_id: str,
    command: AccessCommand,
) -> None:
    """One ledger row per change; the key makes a repeat a no-op."""

    labels = _profiles(connection, actor_id, issuer_id)
    actor = ActorProvenance(
        actor_id=UUID(actor_id),
        actor_kind="member",
        display_name=labels[actor_id],
        grant_id=UUID(grant_id),
        issuer_id=UUID(issuer_id),
        issuer_display_name=labels[issuer_id],
    )
    subject = command.grant_id or command.invite_id
    connection.execute(
        "insert into public.business_action_receipts"
        " (space_id, actor_id, actor, idempotency_key, input_hash, command, outcome)"
        " values (%s, %s, %s, %s, %s, %s, %s) on conflict do nothing",
        (
            space_id,
            actor_id,
            Jsonb(actor.model_dump(mode="json")),
            f"access:{command.action}:{subject}",
            canonical_input_hash(command),
            Jsonb(command.model_dump(mode="json", exclude_none=True)),
            Jsonb({"outcome": "applied"}),
        ),
    )


def _live_grant(connection: Connection, space_id: str, grantee_id: str) -> str | None:
    row = connection.execute(
        "select id::text from public.business_client_grants"
        " where space_id=%s and grantee_id=%s and revoked_at is null"
        " and (expires_at is null or expires_at > now())"
        " order by created_at limit 1",
        (space_id, grantee_id),
    ).fetchone()
    return row[0] if row else None


def _owner_grant_id(connection: Connection, space_id: str, owner_id: str) -> str:
    grant = _live_grant(connection, space_id, owner_id)
    if grant is None:
        grant = ensure_owner_grant(connection, space_id, owner_id) or ""
    if not grant:  # pragma: no cover - the owner lost the space meanwhile
        raise LookupError("business_space_missing")
    return grant


def ensure_owner_grant(
    connection: Connection, space_id: str, owner_id: str
) -> str | None:
    """Insert the owner's grant inside the caller's transaction.

    Returns the new grant id, or ``None`` when a live one already exists or the
    space is not this person's open Business. The receipt is written only on
    insert, so a heal that finds the grant leaves no trace.
    """

    _lock(connection, space_id)
    row = connection.execute(
        "insert into public.business_client_grants (space_id, grantee_id, issuer_id, capabilities)"
        " select s.id, s.created_by, s.created_by, %s::text[] from public.spaces s"
        " where s.id=%s and s.created_by=%s and s.kind='business' and s.closed_at is null"
        " and not exists (select 1 from public.business_client_grants g"
        "   where g.space_id=s.id and g.grantee_id=s.created_by and g.revoked_at is null"
        "   and (g.expires_at is null or g.expires_at > now()))"
        " returning id::text",
        (list(OWNER_CAPABILITIES), space_id, owner_id),
    ).fetchone()
    if row is None:
        return None
    _record(
        connection,
        space_id=space_id,
        actor_id=owner_id,
        grant_id=row[0],
        issuer_id=owner_id,
        command=AccessCommand(action="owner_grant", grant_id=UUID(row[0])),
    )
    return row[0]


class PostgresAccessStore:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    def ensure_owner_grant(self, space_id: str, owner_id: str) -> bool:
        with self.pool.connection() as connection, connection.transaction():
            return ensure_owner_grant(connection, space_id, owner_id) is not None

    def _owned(self, connection: Connection, space_id: str, owner_id: str) -> bool:
        return (
            connection.execute(
                "select 1 from public.spaces where id=%s and created_by=%s"
                " and kind='business' and closed_at is null",
                (space_id, owner_id),
            ).fetchone()
            is not None
        )

    def _list(self, connection: Connection, space_id: str, owner_id: str) -> AccessList:
        with connection.cursor(row_factory=dict_row) as cursor:
            grants = cursor.execute(
                "select g.id::text, g.grantee_id::text, u.email, p.display_name, p.username,"
                " g.capabilities, g.created_at from public.business_client_grants g"
                " join auth.users u on u.id=g.grantee_id"
                " left join public.profiles p on p.id=g.grantee_id"
                " where g.space_id=%s and g.revoked_at is null"
                " and (g.expires_at is null or g.expires_at > now())"
                " order by (g.grantee_id = %s::uuid) desc, g.created_at, g.id",
                (space_id, owner_id),
            ).fetchall()
            invites = cursor.execute(
                "select id::text, email, created_at, expires_at from public.business_access_invites"
                " where space_id=%s and revoked_at is null and accepted_at is null and expires_at > now()"
                " order by created_at, id",
                (space_id,),
            ).fetchall()
        return AccessList(
            tuple(
                AccessGrant(
                    row["id"],
                    row["grantee_id"],
                    row["email"],
                    _label(row["display_name"], row["username"]),
                    tuple(row["capabilities"]),
                    row["created_at"],
                    row["grantee_id"] == owner_id,
                )
                for row in grants
            ),
            tuple(
                AccessInvite(
                    row["id"], row["email"], row["created_at"], row["expires_at"]
                )
                for row in invites
            ),
        )

    def list(self, space_id: str, owner_id: str) -> AccessList:
        with self.pool.connection() as connection:
            if not self._owned(connection, space_id, owner_id):
                raise LookupError("business_space_missing")
            return self._list(connection, space_id, owner_id)

    def give(self, space_id: str, owner_id: str, email: str) -> tuple[bool, AccessList]:
        email = normalize_email(email)
        with self.pool.connection() as connection, connection.transaction():
            if not self._owned(connection, space_id, owner_id):
                raise LookupError("business_space_missing")
            owner_grant = _owner_grant_id(connection, space_id, owner_id)
            # Only a confirmed, non-anonymous account matches; nothing about the
            # account reaches the owner beyond the row the list shows.
            account = connection.execute(
                "select id::text from auth.users where lower(email)=%s"
                " and email_confirmed_at is not null and coalesce(is_anonymous, false)=false"
                " order by created_at limit 1",
                (email,),
            ).fetchone()
            created = False
            if account is not None:
                grantee = account[0]
                if _live_grant(connection, space_id, grantee) is None:
                    grant = connection.execute(
                        "insert into public.business_client_grants (space_id, grantee_id, issuer_id, capabilities)"
                        " values (%s, %s, %s, %s::text[]) returning id::text",
                        (space_id, grantee, owner_id, list(MEMBER_CAPABILITIES)),
                    ).fetchone()[0]
                    connection.execute(
                        "update public.business_access_invites set accepted_at=now(), accepted_grant_id=%s"
                        " where space_id=%s and email=%s and revoked_at is null and accepted_at is null",
                        (grant, space_id, email),
                    )
                    _record(
                        connection,
                        space_id=space_id,
                        actor_id=owner_id,
                        grant_id=owner_grant,
                        issuer_id=owner_id,
                        command=AccessCommand(
                            action="grant_access", grant_id=UUID(grant), email=email
                        ),
                    )
                    created = True
            else:
                # One pending row per Business and email. A live one stays as it
                # is; an expired one is re-issued in place with a fresh window
                # and its own receipt; a revoked or accepted one no longer holds
                # the slot, so a new row is born.
                invite = connection.execute(
                    "insert into public.business_access_invites (space_id, issuer_id, email, expires_at)"
                    " values (%s, %s, %s, now() + %s)"
                    " on conflict (space_id, email) where revoked_at is null and accepted_at is null"
                    " do update set issuer_id=excluded.issuer_id, created_at=now(),"
                    " expires_at=excluded.expires_at"
                    " where public.business_access_invites.expires_at <= now()"
                    " returning id::text",
                    (space_id, owner_id, email, INVITE_LIFETIME),
                ).fetchone()
                if invite is not None:
                    _record(
                        connection,
                        space_id=space_id,
                        actor_id=owner_id,
                        grant_id=owner_grant,
                        issuer_id=owner_id,
                        command=AccessCommand(
                            action="invite_access", invite_id=UUID(invite[0]), email=email
                        ),
                    )
                    created = True
            return created, self._list(connection, space_id, owner_id)

    def revoke_grant(
        self, space_id: str, owner_id: str, grant_id: str
    ) -> RevokeGrantResult:
        with self.pool.connection() as connection, connection.transaction():
            if not self._owned(connection, space_id, owner_id):
                raise LookupError("business_space_missing")
            _lock(connection, space_id)
            row = connection.execute(
                "select grantee_id::text from public.business_client_grants"
                " where id=%s and space_id=%s and revoked_at is null",
                (grant_id, space_id),
            ).fetchone()
            if row is None:
                return "missing"
            if row[0] == owner_id:
                return "own_grant"
            connection.execute(
                "update public.business_client_grants set revoked_at=now() where id=%s and space_id=%s",
                (grant_id, space_id),
            )
            _record(
                connection,
                space_id=space_id,
                actor_id=owner_id,
                grant_id=_owner_grant_id(connection, space_id, owner_id),
                issuer_id=owner_id,
                command=AccessCommand(action="revoke_grant", grant_id=UUID(grant_id)),
            )
            return "revoked"

    def revoke_invite(self, space_id: str, owner_id: str, invite_id: str) -> bool:
        with self.pool.connection() as connection, connection.transaction():
            if not self._owned(connection, space_id, owner_id):
                raise LookupError("business_space_missing")
            row = connection.execute(
                "update public.business_access_invites set revoked_at=now()"
                " where id=%s and space_id=%s and revoked_at is null and accepted_at is null"
                " returning email",
                (invite_id, space_id),
            ).fetchone()
            if row is None:
                return False
            _record(
                connection,
                space_id=space_id,
                actor_id=owner_id,
                grant_id=_owner_grant_id(connection, space_id, owner_id),
                issuer_id=owner_id,
                command=AccessCommand(
                    action="revoke_invite", invite_id=UUID(invite_id), email=row[0]
                ),
            )
            return True

    def accept_invites(self, user_id: str) -> int:
        with self.pool.connection() as connection, connection.transaction():
            person = connection.execute(
                "select lower(email) from auth.users where id=%s and email_confirmed_at is not null"
                " and coalesce(is_anonymous, false)=false and email is not null",
                (user_id,),
            ).fetchone()
            if person is None:
                return 0
            with connection.cursor(row_factory=dict_row) as cursor:
                invites = cursor.execute(
                    "select i.id::text, i.space_id::text, i.issuer_id::text, i.email"
                    " from public.business_access_invites i join public.spaces s on s.id=i.space_id"
                    " where i.email=%s and i.revoked_at is null and i.accepted_at is null and i.expires_at > now()"
                    " and s.created_by=i.issuer_id and s.kind='business' and s.closed_at is null"
                    " order by i.created_at for update of i",
                    (person[0],),
                ).fetchall()
            accepted = 0
            for invite in invites:
                _lock(connection, invite["space_id"])
                grant = _live_grant(connection, invite["space_id"], user_id)
                if grant is None:
                    grant = connection.execute(
                        "insert into public.business_client_grants (space_id, grantee_id, issuer_id, capabilities)"
                        " values (%s, %s, %s, %s::text[]) returning id::text",
                        (
                            invite["space_id"],
                            user_id,
                            invite["issuer_id"],
                            list(MEMBER_CAPABILITIES),
                        ),
                    ).fetchone()[0]
                connection.execute(
                    "update public.business_access_invites set accepted_at=now(), accepted_grant_id=%s where id=%s",
                    (grant, invite["id"]),
                )
                _record(
                    connection,
                    space_id=invite["space_id"],
                    actor_id=user_id,
                    grant_id=grant,
                    issuer_id=invite["issuer_id"],
                    command=AccessCommand(
                        action="accept_invite",
                        invite_id=UUID(invite["id"]),
                        grant_id=UUID(grant),
                        email=invite["email"],
                    ),
                )
                accepted += 1
            return accepted


class InMemoryAccessStore:
    """The same rules without Postgres: the local app and the offline suite.

    Accounts are the emails the test registers through ``confirm``; no email
    is ever confirmed on its own.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._grants: list[dict] = []
        self._invites: list[dict] = []
        self._accounts: dict[str, str] = {}
        self.ledger: list[AccessCommand] = []

    def confirm(self, user_id: str, email: str) -> None:
        with self._lock:
            self._accounts[normalize_email(email)] = user_id

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _live(self, space_id: str, grantee_id: str) -> dict | None:
        return next(
            (
                g
                for g in self._grants
                if g["space_id"] == space_id
                and g["grantee_id"] == grantee_id
                and g["revoked_at"] is None
            ),
            None,
        )

    def _insert_grant(
        self,
        space_id: str,
        grantee_id: str,
        issuer_id: str,
        capabilities: tuple[str, ...],
    ) -> dict:
        grant = {
            "id": str(uuid4()),
            "space_id": space_id,
            "grantee_id": grantee_id,
            "issuer_id": issuer_id,
            "capabilities": capabilities,
            "created_at": self._now(),
            "revoked_at": None,
        }
        self._grants.append(grant)
        return grant

    def ensure_owner_grant(self, space_id: str, owner_id: str) -> bool:
        with self._lock:
            if self._live(space_id, owner_id) is not None:
                return False
            grant = self._insert_grant(space_id, owner_id, owner_id, OWNER_CAPABILITIES)
            self.ledger.append(
                AccessCommand(action="owner_grant", grant_id=UUID(grant["id"]))
            )
            return True

    def capabilities(self, space_id: str, grantee_id: str) -> tuple[str, ...]:
        with self._lock:
            grant = self._live(space_id, grantee_id)
            return grant["capabilities"] if grant else ()

    def _list(self, space_id: str, owner_id: str) -> AccessList:
        now = self._now()
        emails = {user: email for email, user in self._accounts.items()}
        grants = sorted(
            (
                g
                for g in self._grants
                if g["space_id"] == space_id and g["revoked_at"] is None
            ),
            key=lambda g: (g["grantee_id"] != owner_id, g["created_at"]),
        )
        invites = [
            i
            for i in self._invites
            if i["space_id"] == space_id
            and i["revoked_at"] is None
            and i["accepted_at"] is None
            and i["expires_at"] > now
        ]
        return AccessList(
            tuple(
                AccessGrant(
                    g["id"],
                    g["grantee_id"],
                    emails.get(g["grantee_id"]),
                    "Member",
                    g["capabilities"],
                    g["created_at"],
                    g["grantee_id"] == owner_id,
                )
                for g in grants
            ),
            tuple(
                AccessInvite(i["id"], i["email"], i["created_at"], i["expires_at"])
                for i in invites
            ),
        )

    def list(self, space_id: str, owner_id: str) -> AccessList:
        with self._lock:
            return self._list(space_id, owner_id)

    def give(self, space_id: str, owner_id: str, email: str) -> tuple[bool, AccessList]:
        email = normalize_email(email)
        with self._lock:
            account = self._accounts.get(email)
            created = False
            if account is not None:
                if self._live(space_id, account) is None:
                    grant = self._insert_grant(
                        space_id, account, owner_id, MEMBER_CAPABILITIES
                    )
                    for invite in self._invites:
                        if (
                            invite["space_id"] == space_id
                            and invite["email"] == email
                            and invite["revoked_at"] is None
                            and invite["accepted_at"] is None
                        ):
                            invite["accepted_at"] = self._now()
                    self.ledger.append(
                        AccessCommand(
                            action="grant_access", grant_id=UUID(grant["id"]), email=email
                        )
                    )
                    created = True
            else:
                # The same rule as Postgres: one pending row per Business and
                # email; live stays, expired is re-issued in place, revoked or
                # accepted no longer holds the slot.
                pending = next(
                    (
                        i
                        for i in self._invites
                        if i["space_id"] == space_id
                        and i["email"] == email
                        and i["revoked_at"] is None
                        and i["accepted_at"] is None
                    ),
                    None,
                )
                if pending is not None and pending["expires_at"] > self._now():
                    invite = None
                elif pending is not None:
                    pending["issuer_id"] = owner_id
                    pending["created_at"] = self._now()
                    pending["expires_at"] = self._now() + INVITE_LIFETIME
                    invite = pending
                else:
                    invite = {
                        "id": str(uuid4()),
                        "space_id": space_id,
                        "issuer_id": owner_id,
                        "email": email,
                        "created_at": self._now(),
                        "expires_at": self._now() + INVITE_LIFETIME,
                        "accepted_at": None,
                        "revoked_at": None,
                    }
                    self._invites.append(invite)
                if invite is not None:
                    self.ledger.append(
                        AccessCommand(
                            action="invite_access",
                            invite_id=UUID(invite["id"]),
                            email=email,
                        )
                    )
                    created = True
            return created, self._list(space_id, owner_id)

    def revoke_grant(
        self, space_id: str, owner_id: str, grant_id: str
    ) -> RevokeGrantResult:
        with self._lock:
            grant = next(
                (
                    g
                    for g in self._grants
                    if g["id"] == grant_id
                    and g["space_id"] == space_id
                    and g["revoked_at"] is None
                ),
                None,
            )
            if grant is None:
                return "missing"
            if grant["grantee_id"] == owner_id:
                return "own_grant"
            grant["revoked_at"] = self._now()
            self.ledger.append(
                AccessCommand(action="revoke_grant", grant_id=UUID(grant_id))
            )
            return "revoked"

    def revoke_invite(self, space_id: str, owner_id: str, invite_id: str) -> bool:
        with self._lock:
            invite = next(
                (
                    i
                    for i in self._invites
                    if i["id"] == invite_id
                    and i["space_id"] == space_id
                    and i["revoked_at"] is None
                    and i["accepted_at"] is None
                ),
                None,
            )
            if invite is None:
                return False
            invite["revoked_at"] = self._now()
            self.ledger.append(
                AccessCommand(
                    action="revoke_invite",
                    invite_id=UUID(invite_id),
                    email=invite["email"],
                )
            )
            return True

    def accept_invites(self, user_id: str) -> int:
        with self._lock:
            email = next((e for e, u in self._accounts.items() if u == user_id), None)
            if email is None:
                return 0
            accepted = 0
            for invite in self._invites:
                if (
                    invite["email"] != email
                    or invite["revoked_at"] is not None
                    or invite["accepted_at"] is not None
                    or invite["expires_at"] <= self._now()
                ):
                    continue
                grant = self._live(invite["space_id"], user_id) or self._insert_grant(
                    invite["space_id"], user_id, invite["issuer_id"], MEMBER_CAPABILITIES
                )
                invite["accepted_at"] = self._now()
                self.ledger.append(
                    AccessCommand(
                        action="accept_invite",
                        invite_id=UUID(invite["id"]),
                        grant_id=UUID(grant["id"]),
                        email=email,
                    )
                )
                accepted += 1
            return accepted
