"""Canonical Business memberships, explicit invitations and legacy projections."""

from __future__ import annotations

import threading
from collections.abc import Callable
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
from argus.domain.business.memberships import (
    DeliveryState,
    InvitationCommandResult,
    MembershipError,
    PostgresMembershipCommands,
    RecipientInvitation,
)
from argus.domain.business.roles import (
    ROLE_PERMISSIONS,
    BusinessRole,
    legacy_capabilities,
    legacy_role,
    promotion_requires_acceptance,
)

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
    "change_role",
]
RevokeGrantResult = Literal["revoked", "own_grant", "missing"]


class AccessCommand(Contract):
    """The ledger record of one access change."""

    action: AccessAction
    grant_id: UUID | None = None
    invite_id: UUID | None = None
    email: str | None = None
    expires_at: datetime | None = None
    business_role: BusinessRole | None = None
    membership_version: int | None = None


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
        return legacy_role(self.business_role)

    grantee_id: str = ""
    current_owner_id: str = ""
    business_role: BusinessRole = BusinessRole.EDITOR

    @property
    def permissions(self) -> frozenset[str]:
        return ROLE_PERMISSIONS[self.business_role]

    def __post_init__(self) -> None:
        object.__setattr__(self, "capabilities", legacy_capabilities(self.business_role))


@dataclass(frozen=True)
class ClosedSpace:
    """A closed Business a person still holds a live grant on: the close paused
    their access; it was not removed. Distinct from a revoked or expired grant,
    which lists nothing."""

    space_id: str
    name: str
    grant_id: str
    role: Literal["owner", "accountant"]
    closed_at: datetime


@dataclass(frozen=True)
class AccessGrant:
    id: str
    grantee_id: str
    email: str | None
    display_name: str
    capabilities: tuple[str, ...]
    created_at: datetime
    owner: bool
    #: The grantee dismissed the "you now have access" line (their access_seen
    #: receipt), or is the owner. Until then the Business learns only their name.
    seen: bool = False
    business_role: BusinessRole = BusinessRole.EDITOR


@dataclass(frozen=True)
class AccessInvite:
    id: str
    email: str
    created_at: datetime
    expires_at: datetime
    state: Literal["pending", "expired"] = "pending"
    requested_role: BusinessRole = BusinessRole.EDITOR
    supersedes_id: str | None = None


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
        """Initialize a Business with no grant history. True when inserted."""
        ...

    def list(self, space_id: str, owner_id: str) -> AccessList: ...

    def give(
        self,
        space_id: str,
        owner_id: str,
        email: str,
        role: BusinessRole = BusinessRole.EDITOR,
        command_key: str | None = None,
    ) -> tuple[bool, AccessList]:
        """Create a pending invitation; exact replay creates nothing."""
        ...

    def resend(self, space_id: str, owner_id: str, invite_id: str) -> AccessList | None:
        """An explicit owner request gives one pending invite a fresh window."""
        ...

    def revoke_grant(
        self, space_id: str, owner_id: str, grant_id: str
    ) -> RevokeGrantResult: ...

    def revoke_invite(self, space_id: str, owner_id: str, invite_id: str) -> bool: ...

    def accept_invites(self, user_id: str) -> int:
        """Legacy read hook; never activates an invitation."""
        ...

    def accept_invite(self, user_id: str, space_id: str, invite_id: str) -> str: ...

    def change_role(
        self, space_id: str, actor_id: str, grant_id: str, role: BusinessRole
    ) -> AccessList: ...

    def invitations_for(self, user_id: str) -> tuple[RecipientInvitation, ...]: ...

    def invitation_command(
        self, space_id: str, actor_id: str, command_key: str
    ) -> InvitationCommandResult | None: ...

    def deliver_invitation(
        self,
        space_id: str,
        actor_id: str,
        invite_id: str,
        send: Callable[[], DeliveryState],
    ) -> DeliveryState: ...

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

    def closed_spaces_for(self, person_id: str) -> tuple[ClosedSpace, ...]:
        """Every closed Business where this person's grant is otherwise live."""
        ...

    def closed_grant(self, person_id: str, grant_id: str) -> ClosedSpace | None:
        """This person's grant, by id, when only the close keeps it from being live."""
        ...

    def seen_grants(self, person_id: str) -> frozenset[str]:
        """Grants whose one-time "you now have access" line this person dismissed."""
        ...

    def mark_seen(self, person_id: str, grant_id: str) -> None:
        """Record the dismissal once, as this person's own ledger row."""
        ...


def _closed(row: tuple, person_id: str) -> ClosedSpace:
    grant, space, name, _, _, current_owner, closed_at, business_role = row
    role = legacy_role(BusinessRole(business_role))
    return ClosedSpace(space, name, grant, role, closed_at)


def _label(display_name: str | None, username: str | None) -> str:
    return (display_name or "").strip() or (username or "").strip() or "Member"


def _lock(connection: Connection, space_id: str) -> None:
    connection.execute(
        "select id from public.spaces where id=%s for update",
        (space_id,),
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
    subject = command.invite_id or command.grant_id
    if command.membership_version is not None:
        subject = f"{subject}:{command.membership_version}"
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
    """Initialize the default Owner only when the Business has no grant history."""

    _lock(connection, space_id)
    row = connection.execute(
        "insert into public.business_client_grants (space_id, grantee_id, issuer_id, capabilities)"
        " select s.id, s.current_owner_id, s.current_owner_id, %s::text[] from public.spaces s"
        " where s.id=%s and s.current_owner_id=%s and s.kind='business' and s.closed_at is null"
        " and not exists (select 1 from public.business_client_grants g"
        "   where g.space_id=s.id)"
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


class PostgresAccessStore(PostgresMembershipCommands):
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    def ensure_owner_grant(self, space_id: str, owner_id: str) -> bool:
        with self.pool.connection() as connection, connection.transaction():
            return ensure_owner_grant(connection, space_id, owner_id) is not None

    def _owned(self, connection: Connection, space_id: str, owner_id: str) -> bool:
        from argus.domain.business.memberships import require_manager

        try:
            require_manager(connection, space_id, owner_id)
            return True
        except MembershipError:
            return False

    def _list(self, connection: Connection, space_id: str, owner_id: str) -> AccessList:
        with connection.cursor(row_factory=dict_row) as cursor:
            grants = cursor.execute(
                "select g.id::text, g.grantee_id::text, u.email, p.display_name, p.username,"
                " g.capabilities, g.created_at, g.business_role, g.grantee_id = %s::uuid or exists("
                "  select 1 from public.business_action_receipts r"
                "  where r.actor_id=g.grantee_id and r.turn_key is null"
                "  and r.command->>'action'='access_seen' and r.command->>'grant_id'=g.id::text"
                " ) as seen from public.business_client_grants g"
                " join auth.users u on u.id=g.grantee_id"
                " left join public.profiles p on p.id=g.grantee_id"
                " where g.space_id=%s and g.revoked_at is null"
                " and (g.expires_at is null or g.expires_at > now())"
                " order by (g.grantee_id = %s::uuid) desc, g.created_at, g.id",
                (owner_id, space_id, owner_id),
            ).fetchall()
            invites = cursor.execute(
                "select id::text, email, created_at, expires_at, requested_role, supersedes_id::text,"
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
                    row["business_role"] == "owner",
                    row["seen"],
                    BusinessRole(row["business_role"]),
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
                    BusinessRole(row["requested_role"]),
                    row["supersedes_id"],
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
    # A closed Business pauses every grant on it; the same grant reads as
    # closed, not removed, until the Business reopens or is purged.
    _LIVE_GRANTS = (
        "select g.id::text, g.space_id::text, s.name, s.created_by::text, g.capabilities, s.current_owner_id::text, s.closed_at, g.business_role"
        " from public.business_client_grants g join public.spaces s on s.id=g.space_id"
        " join auth.users u on u.id=g.grantee_id"
        " where g.grantee_id=%s and g.revoked_at is null"
        " and (g.expires_at is null or g.expires_at > clock_timestamp())"
        " and 'read'=any(g.capabilities) and s.kind='business' and s.closed_at {state}"
        " and coalesce(u.is_anonymous,false)=false"
    )
    _GRANTED = _LIVE_GRANTS.format(state="is null")
    _CLOSED = _LIVE_GRANTS.format(state="is not null")

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
            GrantedSpace(
                space,
                name,
                grant,
                owner,
                tuple(caps),
                person_id,
                current_owner,
                BusinessRole(role),
            )
            for grant, space, name, owner, caps, current_owner, _, role in rows
        )

    def granted(self, person_id: str, grant_id: str) -> GrantedSpace | None:
        with self.pool.connection() as connection:
            row = connection.execute(
                self._GRANTED + " and g.id=%s", (person_id, grant_id)
            ).fetchone()
        if row is None:
            return None
        grant, space, name, owner, caps, current_owner, _, role = row
        return GrantedSpace(
            space,
            name,
            grant,
            owner,
            tuple(caps),
            person_id,
            current_owner,
            BusinessRole(role),
        )

    def closed_spaces_for(self, person_id: str) -> tuple[ClosedSpace, ...]:
        with self.pool.connection() as connection:
            rows = connection.execute(
                self._CLOSED + " order by s.closed_at desc, s.id, g.created_at",
                (person_id,),
            ).fetchall()
        return tuple(_closed(row, person_id) for row in rows)

    def closed_grant(self, person_id: str, grant_id: str) -> ClosedSpace | None:
        with self.pool.connection() as connection:
            row = connection.execute(
                self._CLOSED + " and g.id=%s", (person_id, grant_id)
            ).fetchone()
        return _closed(row, person_id) if row else None

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


class InMemoryAccessStore:
    """The same rules without Postgres: the local app and the offline suite.

    Accounts are the emails the test registers through ``confirm``; no email
    is ever confirmed on its own.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._grants: list[dict] = []
        self._invites: list[dict] = []
        self._accounts: dict[str, str] = {}
        self.ledger: list[AccessCommand] = []
        self._commands: dict[tuple[str, str, str], tuple[str, BusinessRole]] = {}
        self._command_invites: dict[tuple[str, str, str], str | None] = {}

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
        role: BusinessRole = BusinessRole.EDITOR,
    ) -> dict:
        grant = {
            "id": str(uuid4()),
            "space_id": space_id,
            "grantee_id": grantee_id,
            "issuer_id": issuer_id,
            "capabilities": legacy_capabilities(role),
            "business_role": role,
            "membership_version": 0,
            "created_at": self._now(),
            "revoked_at": None,
        }
        self._grants.append(grant)
        return grant

    def ensure_owner_grant(self, space_id: str, owner_id: str) -> bool:
        with self._lock:
            if any(g["space_id"] == space_id for g in self._grants):
                return False
            grant = self._insert_grant(space_id, owner_id, owner_id, BusinessRole.OWNER)
            self.ledger.append(
                AccessCommand(action="owner_grant", grant_id=UUID(grant["id"]))
            )
            return True

    def capabilities(self, space_id: str, grantee_id: str) -> tuple[str, ...]:
        with self._lock:
            grant = self._live(space_id, grantee_id)
            return legacy_capabilities(grant["business_role"]) if grant else ()

    def _granted(self, grant: dict) -> GrantedSpace:
        return GrantedSpace(
            grant["space_id"],
            "",
            grant["id"],
            next(
                g["grantee_id"]
                for g in self._grants
                if g["space_id"] == grant["space_id"]
            ),
            legacy_capabilities(grant["business_role"]),
            grant["grantee_id"],
            grant["issuer_id"],
            grant["business_role"],
        )

    def spaces_for(self, person_id: str) -> tuple[GrantedSpace, ...]:
        with self._lock:
            rows = [
                g
                for g in self._grants
                if g["grantee_id"] == person_id
                and g["revoked_at"] is None
                and "read" in ROLE_PERMISSIONS[g["business_role"]]
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
                    and "read" in ROLE_PERMISSIONS[g["business_role"]]
                ),
                None,
            )
        return self._granted(grant) if grant else None

    def closed_spaces_for(self, person_id: str) -> tuple[ClosedSpace, ...]:
        # The local store keeps no Business spaces, so none is ever closed.
        return ()

    def closed_grant(self, person_id: str, grant_id: str) -> ClosedSpace | None:
        return None

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
                    legacy_capabilities(g["business_role"]),
                    g["created_at"],
                    g["business_role"] == BusinessRole.OWNER,
                    g["grantee_id"] == owner_id
                    or any(
                        c.action == "access_seen" and str(c.grant_id) == g["id"]
                        for c in self.ledger
                    ),
                    g["business_role"],
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
                    i["requested_role"],
                    i.get("supersedes_id"),
                )
                for i in invites
            ),
        )

    def list(self, space_id: str, owner_id: str) -> AccessList:
        with self._lock:
            self._manager(space_id, owner_id)
            return self._list(space_id, owner_id)

    def _manager(
        self, space_id: str, actor_id: str, role: BusinessRole | None = None
    ) -> dict:
        grant = self._live(space_id, actor_id)
        if grant is None or "manage" not in ROLE_PERMISSIONS[grant["business_role"]]:
            raise MembershipError("business_permission_denied")
        if role == BusinessRole.OWNER and grant["business_role"] != BusinessRole.OWNER:
            raise MembershipError("business_permission_denied")
        return grant

    def give(
        self,
        space_id: str,
        owner_id: str,
        email: str,
        role: BusinessRole = BusinessRole.EDITOR,
        command_key: str | None = None,
    ) -> tuple[bool, AccessList]:
        role, email = BusinessRole(role), normalize_email(email)
        if command_key is not None and (
            not command_key.strip() or len(command_key) > 200
        ):
            raise MembershipError("invalid_idempotency_key")
        with self._lock:
            self._manager(space_id, owner_id, role)
            identity = (space_id, owner_id, command_key)
            if command_key and identity in self._commands:
                if self._commands[identity] != (email, role):
                    raise MembershipError("idempotency_conflict")
                return False, self._list(space_id, owner_id)
            account = self._accounts.get(email)
            existing = self._live(space_id, account) if account else None
            if existing:
                if existing["business_role"] == role:
                    if command_key:
                        self._commands[identity] = (email, role)
                        self._command_invites[identity] = None
                    return False, self._list(space_id, owner_id)
                if account == owner_id:
                    raise MembershipError("business_self_role_change_forbidden")
                self._manager(space_id, owner_id, existing["business_role"])
                if not promotion_requires_acceptance(existing["business_role"], role):
                    raise MembershipError("business_role_change_requires_member_command")
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
            if pending and pending["expires_at"] > self._now():
                if pending["requested_role"] != role:
                    raise MembershipError("business_invite_role_conflict")
                if command_key:
                    self._commands[identity] = (email, role)
                    self._command_invites[identity] = pending["id"]
                return False, self._list(space_id, owner_id)
            if pending:
                pending["revoked_at"] = self._now()
            invite = {
                "id": str(uuid4()),
                "space_id": space_id,
                "issuer_id": owner_id,
                "email": email,
                "requested_role": role,
                "recipient_id": account,
                "created_at": self._now(),
                "expires_at": self._now() + INVITE_LIFETIME,
                "accepted_at": None,
                "accepted_grant_id": None,
                "target_grant_id": existing["id"] if existing else None,
                "target_version": existing["membership_version"] if existing else None,
                "revoked_at": None,
            }
            self._invites.append(invite)
            if command_key:
                self._commands[identity] = (email, role)
                self._command_invites[identity] = invite["id"]
            self.ledger.append(
                AccessCommand(
                    action="invite_access",
                    invite_id=UUID(invite["id"]),
                    email=email,
                    expires_at=invite["expires_at"],
                )
            )
            return True, self._list(space_id, owner_id)

    def resend(self, space_id: str, owner_id: str, invite_id: str) -> AccessList | None:
        with self._lock:
            self._manager(space_id, owner_id)
            replacement = next(
                (
                    i
                    for i in self._invites
                    if i.get("supersedes_id") == invite_id
                    and i["space_id"] == space_id
                    and i["accepted_at"] is None
                    and i["revoked_at"] is None
                    and i["expires_at"] > self._now()
                ),
                None,
            )
            if replacement:
                self._manager(space_id, owner_id, replacement["requested_role"])
                return self._list(space_id, owner_id)
            invite = next(
                (
                    i
                    for i in self._invites
                    if i["space_id"] == space_id
                    and i["id"] == invite_id
                    and i["revoked_at"] is None
                    and i["accepted_at"] is None
                ),
                None,
            )
            if invite is None:
                return None
            self._manager(space_id, owner_id, invite["requested_role"])
            if invite["expires_at"] <= self._now():
                if invite.get("target_grant_id"):
                    live = self._live(space_id, invite["recipient_id"])
                    if (
                        live is None
                        or live["id"] != invite["target_grant_id"]
                        or live["membership_version"] != invite["target_version"]
                    ):
                        raise MembershipError("business_invite_membership_changed")
                invite["revoked_at"] = self._now()
                replacement = dict(
                    invite,
                    id=str(uuid4()),
                    created_at=self._now(),
                    expires_at=self._now() + INVITE_LIFETIME,
                    revoked_at=None,
                    supersedes_id=invite_id,
                    delivery_state="pending",
                )
                replacement.pop("command_key", None)
                self._invites.append(replacement)
            return self._list(space_id, owner_id)

    def revoke_grant(
        self, space_id: str, owner_id: str, grant_id: str
    ) -> RevokeGrantResult:
        with self._lock:
            self._manager(space_id, owner_id)
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
            self._manager(space_id, owner_id, grant["business_role"])
            grant["revoked_at"] = self._now()
            grant["membership_version"] += 1
            self.ledger.append(
                AccessCommand(action="revoke_grant", grant_id=UUID(grant_id))
            )
            return "revoked"

    def change_role(
        self, space_id: str, actor_id: str, grant_id: str, role: BusinessRole
    ) -> AccessList:
        role = BusinessRole(role)
        with self._lock:
            self._manager(space_id, actor_id, role)
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
                raise MembershipError("business_access_not_found")
            if grant["grantee_id"] == actor_id:
                raise MembershipError("business_self_role_change_forbidden")
            self._manager(space_id, actor_id, grant["business_role"])
            if promotion_requires_acceptance(grant["business_role"], role):
                email = next(
                    e
                    for e, person in self._accounts.items()
                    if person == grant["grantee_id"]
                )
                return self.give(space_id, actor_id, email, role)[1]
            if grant["business_role"] == role:
                return self._list(space_id, actor_id)
            grant["membership_version"] += 1
            self.ledger.append(
                AccessCommand(
                    action="change_role",
                    grant_id=UUID(grant_id),
                    business_role=role,
                    membership_version=grant["membership_version"],
                )
            )
            grant["business_role"], grant["capabilities"] = (
                role,
                legacy_capabilities(role),
            )
            return self._list(space_id, actor_id)

    def revoke_invite(self, space_id: str, owner_id: str, invite_id: str) -> bool:
        with self._lock:
            self._manager(space_id, owner_id)
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
            self._manager(space_id, owner_id, invite["requested_role"])
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
        return 0

    def accept_invite(self, user_id: str, space_id: str, invite_id: str) -> str:
        with self._lock:
            email = next((e for e, u in self._accounts.items() if u == user_id), None)
            invite = next(
                (
                    i
                    for i in self._invites
                    if i["id"] == invite_id
                    and i["space_id"] == space_id
                    and i["email"] == email
                    and i.get("recipient_id") in (None, user_id)
                ),
                None,
            )
            if invite is None:
                raise MembershipError("business_invite_not_available")
            if invite["accepted_at"] is not None:
                grant = self._live(space_id, user_id)
                if grant is None or grant["id"] != invite["accepted_grant_id"]:
                    raise MembershipError("business_grant_not_live")
                return grant["id"]
            if invite["revoked_at"] is not None or invite["expires_at"] <= self._now():
                raise MembershipError("business_invite_not_available")
            self._manager(space_id, invite["issuer_id"], invite["requested_role"])
            live = self._live(space_id, user_id)
            if invite.get("target_grant_id"):
                if (
                    live is None
                    or live["id"] != invite["target_grant_id"]
                    or live["membership_version"] != invite["target_version"]
                ):
                    raise MembershipError("business_invite_membership_changed")
                grant = live
                grant["business_role"] = invite["requested_role"]
                grant["capabilities"] = legacy_capabilities(invite["requested_role"])
                grant["membership_version"] += 1
            else:
                if live:
                    raise MembershipError("business_membership_already_active")
                grant = self._insert_grant(
                    space_id, user_id, invite["issuer_id"], invite["requested_role"]
                )
            invite["accepted_at"], invite["accepted_grant_id"] = self._now(), grant["id"]
            self.ledger.append(
                AccessCommand(
                    action="accept_invite",
                    invite_id=UUID(invite_id),
                    grant_id=UUID(grant["id"]),
                    email=email,
                )
            )
            return grant["id"]

    def invitations_for(self, user_id: str) -> tuple[RecipientInvitation, ...]:
        with self._lock:
            email = next((e for e, u in self._accounts.items() if u == user_id), None)
            return tuple(
                {
                    "id": i["id"],
                    "space_id": i["space_id"],
                    "name": "",
                    "requested_role": i["requested_role"],
                    "expires_at": i["expires_at"],
                }
                for i in self._invites
                if i["email"] == email
                and i.get("recipient_id") in (None, user_id)
                and i["revoked_at"] is None
                and i["accepted_at"] is None
                and i["expires_at"] > self._now()
            )

    def deliver_invitation(
        self,
        space_id: str,
        actor_id: str,
        invite_id: str,
        send: Callable[[], DeliveryState],
    ) -> DeliveryState:
        with self._lock:
            self._manager(space_id, actor_id)
            invite = next(
                (
                    i
                    for i in self._invites
                    if i["id"] == invite_id
                    and i["space_id"] == space_id
                    and i["revoked_at"] is None
                    and i["accepted_at"] is None
                    and i["expires_at"] > self._now()
                ),
                None,
            )
            if invite is None:
                raise MembershipError("business_invite_not_available")
            self._manager(space_id, actor_id, invite["requested_role"])
            if invite.get("delivery_state") == "accepted":
                return "accepted"
            if invite.get("delivery_state") in ("sending", "uncertain"):
                return "uncertain"
            invite["delivery_state"] = "sending"
            try:
                invite["delivery_state"] = send()
            except Exception:
                invite["delivery_state"] = "uncertain"
            return invite["delivery_state"]

    def invitation_command(
        self, space_id: str, actor_id: str, command_key: str
    ) -> InvitationCommandResult | None:
        with self._lock:
            self._manager(space_id, actor_id)
            value = self._commands.get((space_id, actor_id, command_key))
            if value is None:
                return None
            invite = next(
                (
                    i
                    for i in self._invites
                    if i["id"]
                    == self._command_invites.get((space_id, actor_id, command_key))
                ),
                None,
            )
            if invite is None:
                return {"invite_id": None, "state": "already_member", "delivery": None}
            state = (
                "accepted"
                if invite["accepted_at"]
                else "revoked"
                if invite["revoked_at"]
                else "pending"
                if invite["expires_at"] > self._now()
                else "expired"
            )
            return {
                "invite_id": invite["id"],
                "state": state,
                "delivery": "uncertain"
                if invite.get("delivery_state") == "sending"
                else invite.get("delivery_state", "pending"),
            }
