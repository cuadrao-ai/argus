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
INVITE_LIFETIME = timedelta(days=7)
MAX_EMAIL_LENGTH = 254

AccessAction = Literal[
    "owner_grant",
    "grant_access",
    "invite_access",
    "accept_invite",
    "revoke_grant",
    "revoke_invite",
    "access_seen",
]
RevokeGrantResult = Literal["revoked", "own_grant", "missing"]


class AccessCommand(Contract):
    """The ledger record of one access change."""

    action: AccessAction
    grant_id: UUID | None = None
    invite_id: UUID | None = None
    email: str | None = None
    # An invite re-issued after expiry keeps its row and gets a new window: the
    # window makes the re-issue its own ledger row.
    expires_at: datetime | None = None


@dataclass(frozen=True)
class GrantedSpace:
    """One Business a person may enter, through one live grant of theirs."""

    space_id: str
    name: str
    grant_id: str
    owner_id: str
    capabilities: tuple[str, ...]

    @property
    def role(self) -> str:
        return "owner" if self.current_owner_id == self.grantee_id else "accountant"

    grantee_id: str = ""
    current_owner_id: str = ""

    def __post_init__(self) -> None:
        # What the grant lets this person do: approve is the owner's alone,
        # whatever a row says, so the listing never reports it for anyone else.
        if self.role != "owner" and "approve" in self.capabilities:
            object.__setattr__(
                self,
                "capabilities",
                tuple(c for c in self.capabilities if c != "approve"),
            )


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
    state: Literal["pending", "expired"] = "pending"


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

    def resend(self, space_id: str, owner_id: str, invite_id: str) -> AccessList | None:
        """An explicit owner request gives one pending invite a fresh window."""
        ...

    def revoke_grant(
        self, space_id: str, owner_id: str, grant_id: str
    ) -> RevokeGrantResult: ...

    def revoke_invite(self, space_id: str, owner_id: str, invite_id: str) -> bool: ...

    def accept_invites(self, user_id: str) -> int:
        """Turn the live invites for this person's confirmed email into grants."""
        ...

    def spaces_for(self, person_id: str) -> tuple[GrantedSpace, ...]:
        """Every open Business where this person holds a live read grant, their
        own first; the name comes from the space, never from the client."""
        ...

    def capabilities(self, space_id: str, grantee_id: str) -> tuple[str, ...]:
        """What this person's live grant on the space allows, or nothing."""
        ...

    def granted(self, person_id: str, grant_id: str) -> GrantedSpace | None:
        """One live grant of this person, by id, or None: a grant that is not
        theirs, revoked or expired answers the same None."""
        ...

    def seen_grants(self, person_id: str) -> frozenset[str]:
        """Grants whose one-time "you now have access" line this person dismissed."""
        ...

    def mark_seen(self, person_id: str, grant_id: str) -> None:
        """Record the dismissal once, as this person's own ledger row."""
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
    if command.expires_at is not None:
        subject = f"{subject}:{command.expires_at.timestamp():.6f}"
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
        " select s.id, s.current_owner_id, s.current_owner_id, %s::text[] from public.spaces s"
        " where s.id=%s and s.current_owner_id=%s and s.kind='business' and s.closed_at is null"
        " and not exists (select 1 from public.business_client_grants g"
        "   where g.space_id=s.id and g.grantee_id=s.current_owner_id and g.revoked_at is null"
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
                "select 1 from public.spaces where id=%s and current_owner_id=%s"
                " and kind='business' and closed_at is null for share",
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
                "select id::text, email, created_at, expires_at,"
                " case when expires_at > clock_timestamp() then 'pending' else 'expired' end as state"
                " from public.business_access_invites"
                " where space_id=%s and revoked_at is null and accepted_at is null"
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
                    row["id"],
                    row["email"],
                    row["created_at"],
                    row["expires_at"],
                    row["state"],
                )
                for row in invites
            ),
        )

    def list(self, space_id: str, owner_id: str) -> AccessList:
        with self.pool.connection() as connection:
            if not self._owned(connection, space_id, owner_id):
                raise LookupError("business_space_missing")
            return self._list(connection, space_id, owner_id)

    # Live means: not revoked or expired, the Business open, the person not
    # anonymous, and the issuer still holding owner access: an issuer whose own
    # owner grant was revoked, with no live one since, ends every grant they gave.
    _GRANTED = (
        "select g.id::text, g.space_id::text, s.name, s.created_by::text, g.capabilities, s.current_owner_id::text"
        " from public.business_client_grants g join public.spaces s on s.id=g.space_id"
        " join auth.users u on u.id=g.grantee_id"
        " where g.grantee_id=%s and g.revoked_at is null"
        " and (g.expires_at is null or g.expires_at > clock_timestamp())"
        " and 'read'=any(g.capabilities) and s.kind='business' and s.closed_at is null"
        " and coalesce(u.is_anonymous,false)=false"
        " and not exists (select 1 from public.business_client_grants lost"
        "   where lost.space_id=g.space_id and lost.grantee_id=g.issuer_id"
        "   and lost.issuer_id=lost.grantee_id"
        "   and (lost.revoked_at is not null"
        "     or (lost.expires_at is not null and lost.expires_at <= clock_timestamp()))"
        "   and not exists (select 1 from public.business_client_grants own"
        "     where own.space_id=lost.space_id and own.grantee_id=lost.grantee_id"
        "     and own.issuer_id=own.grantee_id and own.revoked_at is null"
        "     and (own.expires_at is null or own.expires_at > clock_timestamp())))"
    )

    def capabilities(self, space_id: str, grantee_id: str) -> tuple[str, ...]:
        from argus.domain.business.authority import ActionError, authorize
        from argus.domain.business.contracts.authority import TrustedActor

        actor = TrustedActor(
            actor_id=UUID(grantee_id), actor_kind="member", space_id=UUID(space_id)
        )
        with self.pool.connection() as connection, connection.transaction():
            try:
                return tuple(sorted(authorize(connection, actor).capabilities))
            except ActionError:
                return ()

    def spaces_for(self, person_id: str) -> tuple[GrantedSpace, ...]:
        with self.pool.connection() as connection:
            rows = connection.execute(
                self._GRANTED
                + " order by (s.current_owner_id=%s::uuid) desc, s.name, g.created_at",
                (person_id, person_id),
            ).fetchall()
        return tuple(
            GrantedSpace(space, name, grant, owner, tuple(caps), person_id, current_owner)
            for grant, space, name, owner, caps, current_owner in rows
        )

    def granted(self, person_id: str, grant_id: str) -> GrantedSpace | None:
        with self.pool.connection() as connection:
            row = connection.execute(
                self._GRANTED + " and g.id=%s", (person_id, grant_id)
            ).fetchone()
        if row is None:
            return None
        grant, space, name, owner, caps, current_owner = row
        return GrantedSpace(
            space, name, grant, owner, tuple(caps), person_id, current_owner
        )

    def seen_grants(self, person_id: str) -> frozenset[str]:
        with self.pool.connection() as connection:
            rows = connection.execute(
                "select command->>'grant_id' from public.business_action_receipts"
                " where actor_id=%s and turn_key is null and command->>'action'='access_seen'",
                (person_id,),
            ).fetchall()
        return frozenset(row[0] for row in rows if row[0])

    def mark_seen(self, person_id: str, grant_id: str) -> None:
        found = self.granted(person_id, grant_id)
        if found is None or found.role == "owner":
            # Not this person's live grant, or their own Business: nothing to dismiss.
            return
        from argus.domain.business.authority import authorize
        from argus.domain.business.contracts.authority import TrustedActor

        with self.pool.connection() as connection, connection.transaction():
            auth = authorize(
                connection,
                TrustedActor(
                    actor_id=UUID(person_id),
                    actor_kind="member",
                    space_id=UUID(found.space_id),
                ),
                UUID(grant_id),
            )
            command = AccessCommand(action="access_seen", grant_id=UUID(grant_id))
            connection.execute(
                "insert into public.business_action_receipts"
                " (space_id, actor_id, actor, idempotency_key, input_hash, command, outcome)"
                " values (%s, %s, %s, %s, %s, %s, %s) on conflict do nothing",
                (
                    found.space_id,
                    person_id,
                    Jsonb(auth.provenance.model_dump(mode="json")),
                    f"access:seen:{grant_id}",
                    canonical_input_hash(command),
                    Jsonb(command.model_dump(mode="json", exclude_none=True)),
                    Jsonb({"outcome": "applied"}),
                ),
            )

    def give(self, space_id: str, owner_id: str, email: str) -> tuple[bool, AccessList]:
        email = normalize_email(email)
        with self.pool.connection() as connection, connection.transaction():
            if not self._owned(connection, space_id, owner_id):
                raise LookupError("business_space_missing")
            _lock(connection, space_id)
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
                    " returning id::text, expires_at",
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
                            action="invite_access",
                            invite_id=UUID(invite[0]),
                            email=email,
                            expires_at=invite[1],
                        ),
                    )
                    created = True
            return created, self._list(connection, space_id, owner_id)

    def resend(self, space_id: str, owner_id: str, invite_id: str) -> AccessList | None:
        with self.pool.connection() as connection, connection.transaction():
            _lock(connection, space_id)
            if not self._owned(connection, space_id, owner_id):
                return None
            row = connection.execute(
                "update public.business_access_invites set created_at=statement_timestamp(),"
                " expires_at=statement_timestamp() + %s"
                " where id=%s and space_id=%s and issuer_id=%s"
                " and accepted_at is null and revoked_at is null returning email, expires_at",
                (INVITE_LIFETIME, invite_id, space_id, owner_id),
            ).fetchone()
            if row is None:
                return None
            _record(
                connection,
                space_id=space_id,
                actor_id=owner_id,
                grant_id=_owner_grant_id(connection, space_id, owner_id),
                issuer_id=owner_id,
                command=AccessCommand(
                    action="invite_access",
                    invite_id=UUID(invite_id),
                    email=row[0],
                    expires_at=row[1],
                ),
            )
            return self._list(connection, space_id, owner_id)

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
                    " where i.email=%s and i.revoked_at is null and i.accepted_at is null and i.expires_at > clock_timestamp()"
                    " and s.current_owner_id=i.issuer_id and s.kind='business' and s.closed_at is null"
                    " order by i.created_at",
                    (person[0],),
                ).fetchall()
            accepted = 0
            for invite in invites:
                _lock(connection, invite["space_id"])
                live = connection.execute(
                    "select 1 from public.business_access_invites i join public.spaces s on s.id=i.space_id"
                    " where i.id=%s and i.revoked_at is null and i.accepted_at is null"
                    " and i.expires_at > clock_timestamp() and s.current_owner_id=i.issuer_id"
                    " and s.kind='business' and s.closed_at is null for update of i",
                    (invite["id"],),
                ).fetchone()
                if live is None:
                    continue
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

    def _granted(self, grant: dict) -> GrantedSpace:
        # The in-memory rows know no names (the route asks the space store)
        # and no owners: the owner issued the grant, or holds a self-issued one.
        return GrantedSpace(
            grant["space_id"],
            "",
            grant["id"],
            grant["issuer_id"],
            tuple(grant["capabilities"]),
            grant["grantee_id"],
            grant["issuer_id"],
        )

    def _issuer_live(self, grant: dict) -> bool:
        """The issuer still holds owner access: an issuer whose own owner grant
        was revoked, with no live one since, has ended every grant they gave."""

        own = [
            g
            for g in self._grants
            if g["space_id"] == grant["space_id"]
            and g["grantee_id"] == grant["issuer_id"]
            and g["issuer_id"] == g["grantee_id"]
        ]
        return not own or any(g["revoked_at"] is None for g in own)

    def spaces_for(self, person_id: str) -> tuple[GrantedSpace, ...]:
        with self._lock:
            rows = [
                g
                for g in self._grants
                if g["grantee_id"] == person_id
                and g["revoked_at"] is None
                and "read" in g["capabilities"]
                and self._issuer_live(g)
            ]
        rows.sort(key=lambda g: (g["issuer_id"] != g["grantee_id"], g["created_at"]))
        return tuple(self._granted(g) for g in rows)

    def granted(self, person_id: str, grant_id: str) -> GrantedSpace | None:
        with self._lock:
            grant = next(
                (
                    g
                    for g in self._grants
                    if g["id"] == grant_id
                    and g["grantee_id"] == person_id
                    and g["revoked_at"] is None
                    and "read" in g["capabilities"]
                    and self._issuer_live(g)
                ),
                None,
            )
        return self._granted(grant) if grant else None

    def seen_grants(self, person_id: str) -> frozenset[str]:
        with self._lock:
            return frozenset(
                str(c.grant_id)
                for c in self.ledger
                if c.action == "access_seen" and c.email == person_id
            )

    def mark_seen(self, person_id: str, grant_id: str) -> None:
        found = self.granted(person_id, grant_id)
        if found is None or found.role == "owner":
            return
        with self._lock:
            if any(
                c.action == "access_seen" and str(c.grant_id) == grant_id
                for c in self.ledger
            ):
                return
            # The in-memory ledger has no actor column: the person rides in ``email``.
            self.ledger.append(
                AccessCommand(
                    action="access_seen", grant_id=UUID(grant_id), email=person_id
                )
            )

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
                AccessInvite(
                    i["id"],
                    i["email"],
                    i["created_at"],
                    i["expires_at"],
                    "pending" if i["expires_at"] > now else "expired",
                )
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
                            expires_at=invite["expires_at"],
                        )
                    )
                    created = True
            return created, self._list(space_id, owner_id)

    def resend(self, space_id: str, owner_id: str, invite_id: str) -> AccessList | None:
        with self._lock:
            invite = next(
                (
                    i
                    for i in self._invites
                    if i["id"] == invite_id
                    and i["space_id"] == space_id
                    and i["issuer_id"] == owner_id
                    and i["accepted_at"] is None
                    and i["revoked_at"] is None
                ),
                None,
            )
            if invite is None:
                return None
            now = self._now()
            invite["created_at"], invite["expires_at"] = now, now + INVITE_LIFETIME
            self.ledger.append(
                AccessCommand(
                    action="invite_access",
                    invite_id=UUID(invite_id),
                    email=invite["email"],
                    expires_at=invite["expires_at"],
                )
            )
            return self._list(space_id, owner_id)

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
