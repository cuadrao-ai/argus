"""In-memory household store for hermetic tests and memory persistence mode."""

from __future__ import annotations

import hashlib
import secrets
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Protocol
from uuid import uuid4

from argus.domain.backtest_admission import canonical_hash
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
    find_code,
    format_code,
    new_code,
    normalize_code,
)
from argus.domain.household.schemas import (
    AcceptanceResult,
    AccountGrantRecord,
    AccountShare,
    CommandResult,
    HouseholdRecord,
    InvitationCreated,
    InvitationMetadata,
    InvitationPreview,
    MemberRecord,
    OwnedAccountRef,
    Permission,
    Recipient,
    SharedAccountView,
)
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.errors import IdempotencyConflict, StaleVersion

INVITE_TTL = timedelta(days=7)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def code_hasher(hasher: CodeHasher | None) -> CodeHasher:
    """The injected hasher, or the one the environment configures (fail closed)."""
    return hasher if hasher is not None else CodeHasher.from_env()


def locate_secret(
    connection,  # noqa: ANN001
    token: str | None,
    code: str | None,
    hasher: CodeHasher | None,
) -> tuple[str, str]:
    """Which column to match and its value, for a link token or a typed code.

    A token matches its SHA-256 digest. A code is resolved through the private
    digest table to the invitation id, so no client-readable table holds it.
    """
    if token is not None:
        return "token_hash", hash_token(token)
    found = find_code(connection, code, code_hasher(hasher))
    if found is None:
        raise InvitationNotFound()
    return "id", found


@dataclass
class _Member:
    id: str
    display_name: str
    user_id: str
    joined_at: datetime
    left_at: datetime | None = None


@dataclass
class _Invitation:
    id: str
    household_id: str
    token_hash: str
    created_by: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    accepted_by: str | None = None
    accepted_at: datetime | None = None
    accepted_membership_id: str | None = None
    code_hash: str | None = None


@dataclass
class _Grant:
    owner_membership_id: str
    recipient_membership_id: str
    id: str
    household_id: str
    account_id: str
    owner_user_id: str
    permission: Permission
    created_at: datetime
    revoked_at: datetime | None = None


@dataclass
class _Household:
    id: str
    name: str | None
    status: str
    created_by: str
    admin_user_id: str
    created_at: datetime
    closed_at: datetime | None = None
    version: int = 1
    members: list[_Member] = field(default_factory=list)
    invitations: list[_Invitation] = field(default_factory=list)
    grants: list[_Grant] = field(default_factory=list)


class AccountLookup(Protocol):
    def owned_account(
        self, *, user_id: str, account_id: str
    ) -> OwnedAccountRef | None: ...

    def account_by_id(self, *, account_id: str) -> OwnedAccountRef | None: ...


class InMemoryHouseholdRepository:
    def __init__(
        self,
        accounts: AccountLookup,
        *,
        clock=_utcnow,  # noqa: ANN001
        code_hasher: CodeHasher | None = None,
    ) -> None:
        self._accounts = accounts
        self._clock = clock
        self._hasher = code_hasher
        self._households: dict[str, _Household] = {}
        self._invites_by_hash: dict[str, str] = {}
        self._codes: dict[str, str] = {}
        self._receipts = {}
        self._lock = RLock()

    def create_household(
        self, *, user_id: str, name: str | None, display_name: str = "Member"
    ) -> HouseholdRecord:
        now = self._clock()
        hid = str(uuid4())
        household = _Household(
            id=hid,
            name=_trim_name(name),
            status="active",
            created_by=user_id,
            admin_user_id=user_id,
            created_at=now,
            members=[
                _Member(
                    id=str(uuid4()),
                    display_name=display_name,
                    user_id=user_id,
                    joined_at=now,
                )
            ],
        )
        self._households[hid] = household
        return self._view(household, user_id)

    def list_households(self, *, user_id: str) -> list[HouseholdRecord]:
        return [
            self._view(household, user_id)
            for household in self._households.values()
            if household.status == "active"
            and any(m.user_id == user_id and m.left_at is None for m in household.members)
        ]

    def get_household(self, *, user_id: str, household_id: str) -> HouseholdRecord:
        household = self._require_member(user_id=user_id, household_id=household_id)
        return self._view(household, user_id)

    def create_invitation(self, *, user_id: str, household_id: str) -> InvitationCreated:
        household = self._require_admin(user_id=user_id, household_id=household_id)
        now = self._clock()
        hasher = code_hasher(self._hasher)
        token = secrets.token_urlsafe(32)
        code = new_code()
        while any(d in self._codes for d in hasher.candidates(code)):
            code = new_code()
        invite = _Invitation(
            id=str(uuid4()),
            household_id=household.id,
            token_hash=hash_token(token),
            created_by=user_id,
            created_at=now,
            expires_at=now + INVITE_TTL,
            code_hash=hasher.digest(code),
        )
        household.invitations.append(invite)
        self._invites_by_hash[invite.token_hash] = household.id
        self._codes[invite.code_hash] = invite.token_hash
        return InvitationCreated(
            id=invite.id,
            household_id=household.id,
            expires_at=invite.expires_at,
            token=token,
            code=format_code(code),
        )

    def _token_hash(self, token: str | None, code: str | None) -> str:
        if token is not None:
            return hash_token(token)
        hasher = code_hasher(self._hasher)
        normalized = normalize_code(code or "")
        found = None
        if normalized is not None:
            found = next(
                (
                    self._codes[d]
                    for d in hasher.candidates(normalized)
                    if d in self._codes
                ),
                None,
            )
        if found is None:
            raise InvitationNotFound()
        return found

    def revoke_invitation(
        self, *, user_id: str, household_id: str, invitation_id: str
    ) -> None:
        household = self._require_admin(user_id=user_id, household_id=household_id)
        invite = next((i for i in household.invitations if i.id == invitation_id), None)
        if invite is None:
            raise InvitationNotFound()
        if invite.accepted_at is not None:
            raise InvitationConsumed()
        if invite.revoked_at is None:
            invite.revoked_at = self._clock()

    def preview_invitation(
        self, *, user_id: str, token: str | None = None, code: str | None = None
    ) -> InvitationPreview:
        token_hash = self._token_hash(token, code)
        hid = self._invites_by_hash.get(token_hash)
        if hid is None:
            raise InvitationNotFound()
        h = self._households[hid]
        i = next(i for i in h.invitations if i.token_hash == token_hash)
        return InvitationPreview(
            name=h.name,
            expires_at=i.expires_at,
            available=i.accepted_at is None
            and i.revoked_at is None
            and h.status == "active"
            and i.expires_at > self._clock(),
        )

    def accept_invitation(
        self,
        *,
        user_id: str,
        token: str | None = None,
        display_name: str = "Member",
        code: str | None = None,
    ) -> AcceptanceResult:
        token_hash = self._token_hash(token, code)
        hid = self._invites_by_hash.get(token_hash)
        if hid is None:
            raise InvitationNotFound()
        h = self._households[hid]
        i = next(i for i in h.invitations if i.token_hash == token_hash)
        if i.accepted_at is not None:
            if i.accepted_by != user_id or i.accepted_membership_id is None:
                raise InvitationConsumed()
            m = next(m for m in h.members if m.id == i.accepted_membership_id)
            return AcceptanceResult(
                household_id=hid,
                membership_id=m.id,
                state="active"
                if m.left_at is None and h.status == "active"
                else "departed",
            )
        if i.revoked_at is not None:
            raise InvitationRevoked()
        if i.expires_at <= self._clock():
            raise InvitationExpired()
        if h.status != "active":
            raise HouseholdClosed()
        m = next(
            (m for m in h.members if m.user_id == user_id and m.left_at is None), None
        )
        if m is None:
            m = _Member(
                id=str(uuid4()),
                display_name=display_name,
                user_id=user_id,
                joined_at=self._clock(),
            )
            h.members.append(m)
        i.accepted_by = user_id
        i.accepted_at = self._clock()
        i.accepted_membership_id = m.id
        return AcceptanceResult(household_id=hid, membership_id=m.id, state="active")

    def leave(self, *, user_id: str, household_id: str) -> None:
        household = self._require_member(user_id=user_id, household_id=household_id)
        if household.admin_user_id == user_id:
            raise MustTransferOrClose()
        self._end_membership(household, user_id)

    def remove_member(
        self, *, admin_user_id: str, household_id: str, member_user_id: str
    ) -> None:
        household = self._require_admin(user_id=admin_user_id, household_id=household_id)
        if member_user_id == admin_user_id:
            raise MustTransferOrClose()
        member = next(
            (
                m
                for m in household.members
                if m.user_id == member_user_id and m.left_at is None
            ),
            None,
        )
        if member is None:
            raise MemberNotFound()
        self._end_membership(household, member_user_id)

    def transfer_admin(
        self, *, admin_user_id: str, household_id: str, new_admin_user_id: str
    ) -> HouseholdRecord:
        household = self._require_admin(user_id=admin_user_id, household_id=household_id)
        if new_admin_user_id == admin_user_id:
            return self._view(household, admin_user_id)
        member = next(
            (
                m
                for m in household.members
                if m.user_id == new_admin_user_id and m.left_at is None
            ),
            None,
        )
        if member is None:
            raise MemberNotFound()
        household.admin_user_id = new_admin_user_id
        return self._view(household, admin_user_id)

    def close(self, *, user_id: str, household_id: str) -> HouseholdRecord:
        household = self._require_admin(user_id=user_id, household_id=household_id)
        now = self._clock()
        household.status = "closed"
        household.closed_at = now
        for member in household.members:
            if member.left_at is None:
                member.left_at = now
        for invite in household.invitations:
            if invite.revoked_at is None and invite.accepted_at is None:
                invite.revoked_at = now
        for grant in household.grants:
            if grant.revoked_at is None:
                grant.revoked_at = now
        return self._view(household, user_id)

    def create_grant(
        self,
        *,
        user_id: str,
        household_id: str,
        account_id: str,
        permission: Permission,
        recipient_membership_id: str,
    ) -> AccountGrantRecord:
        household = self._require_member(user_id=user_id, household_id=household_id)
        account = self._accounts.owned_account(user_id=user_id, account_id=account_id)
        if account is None:
            raise AccountNotOwned()
        owner = next(
            m for m in household.members if m.user_id == user_id and m.left_at is None
        )
        recipient = next(
            (
                m
                for m in household.members
                if m.id == recipient_membership_id
                and m.user_id != user_id
                and m.left_at is None
            ),
            None,
        )
        if recipient is None:
            raise MemberNotFound()
        existing = next(
            (
                g
                for g in household.grants
                if g.account_id == account_id
                and g.recipient_membership_id == recipient_membership_id
                and g.revoked_at is None
            ),
            None,
        )
        now = self._clock()
        if existing is not None:
            if existing.owner_user_id != user_id:
                raise AccountNotOwned()
            existing.permission = permission
            return self._grant_view(existing)
        grant = _Grant(
            owner_membership_id=owner.id,
            recipient_membership_id=recipient_membership_id,
            id=str(uuid4()),
            household_id=household.id,
            account_id=account_id,
            owner_user_id=user_id,
            permission=permission,
            created_at=now,
        )
        household.grants.append(grant)
        return self._grant_view(grant)

    def update_grant(
        self,
        *,
        user_id: str,
        household_id: str,
        grant_id: str,
        permission: Permission,
    ) -> AccountGrantRecord:
        household = self._require_member(user_id=user_id, household_id=household_id)
        grant = next(
            (g for g in household.grants if g.id == grant_id and g.revoked_at is None),
            None,
        )
        if grant is None:
            raise GrantNotFound()
        if grant.owner_user_id != user_id:
            raise AccountNotOwned()
        grant.permission = permission
        return self._grant_view(grant)

    def revoke_grant(self, *, user_id: str, household_id: str, grant_id: str) -> None:
        household = self._require_member(user_id=user_id, household_id=household_id)
        grant = next(
            (g for g in household.grants if g.id == grant_id and g.revoked_at is None),
            None,
        )
        if grant is None:
            raise GrantNotFound()
        if grant.owner_user_id != user_id and household.admin_user_id != user_id:
            raise AdminRequired()
        grant.revoked_at = self._clock()

    def list_shared_accounts(
        self, *, user_id: str, household_id: str
    ) -> list[SharedAccountView]:
        household = self._require_member(user_id=user_id, household_id=household_id)
        views: list[SharedAccountView] = []
        member = next(
            m for m in household.members if m.user_id == user_id and m.left_at is None
        )
        seen = set()
        for grant in household.grants:
            if (
                grant.revoked_at is not None
                or grant.account_id in seen
                or (
                    grant.owner_membership_id != member.id
                    and grant.recipient_membership_id != member.id
                )
            ):
                continue
            seen.add(grant.account_id)
            account = self._accounts.account_by_id(account_id=grant.account_id)
            if account is None or account.user_id != grant.owner_user_id:
                continue
            views.append(
                SharedAccountView(
                    grant_id=grant.id,
                    account_id=account.id,
                    owner_user_id=account.user_id,
                    permission=grant.permission,
                    type=account.type,
                    currency=account.currency,
                    nickname=account.nickname,
                    archived=account.archived,
                    ownership_share_bps=account.ownership_share_bps,
                )
            )
        views.sort(key=lambda item: (item.owner_user_id, item.account_id))
        return views

    def _end_membership(self, household: _Household, user_id: str) -> None:
        now = self._clock()
        for member in household.members:
            if member.user_id == user_id and member.left_at is None:
                member.left_at = now
        for grant in household.grants:
            recipient = next(
                m for m in household.members if m.id == grant.recipient_membership_id
            )
            if (
                grant.owner_user_id == user_id or recipient.user_id == user_id
            ) and grant.revoked_at is None:
                grant.revoked_at = now

    def _require_member(self, *, user_id: str, household_id: str) -> _Household:
        household = self._households.get(household_id)
        if household is None:
            raise HouseholdNotFound()
        if household.status != "active":
            raise HouseholdNotFound()
        if not any(m.user_id == user_id and m.left_at is None for m in household.members):
            raise HouseholdNotFound()
        return household

    def _require_admin(self, *, user_id: str, household_id: str) -> _Household:
        household = self._require_member(user_id=user_id, household_id=household_id)
        if household.admin_user_id != user_id:
            raise AdminRequired()
        return household

    def _view(self, household: _Household, actor: str) -> HouseholdRecord:
        members = [
            MemberRecord(
                membership_id=m.id,
                display_name=m.display_name,
                is_self=m.user_id == actor,
                is_admin=m.user_id == household.admin_user_id,
                user_id=m.user_id,
                role="admin" if m.user_id == household.admin_user_id else "member",
                joined_at=m.joined_at,
            )
            for m in household.members
            if m.left_at is None
        ]
        members.sort(key=lambda item: item.joined_at)
        shares = {}
        for g in household.grants:
            if g.owner_user_id == actor and g.revoked_at is None:
                shares.setdefault(g.account_id, []).append(
                    Recipient(
                        membership_id=g.recipient_membership_id, permission=g.permission
                    )
                )
        return HouseholdRecord(
            version=household.version,
            membership_id=next((m.membership_id for m in members if m.is_self), None),
            admin_membership_id=next(
                (m.membership_id for m in members if m.is_admin), None
            ),
            invitations=[
                InvitationMetadata(
                    id=i.id,
                    expires_at=i.expires_at,
                    state="accepted"
                    if i.accepted_at
                    else "revoked"
                    if i.revoked_at
                    else "expired"
                    if i.expires_at <= self._clock()
                    else "pending",
                )
                for i in household.invitations
            ]
            if actor == household.admin_user_id
            else [],
            shares=[
                AccountShare(account_id=aid, recipients=rs) for aid, rs in shares.items()
            ],
            id=household.id,
            name=household.name,
            status=household.status,  # type: ignore[arg-type]
            admin_user_id=household.admin_user_id,
            created_by=household.created_by,
            created_at=household.created_at,
            closed_at=household.closed_at,
            members=members,
        )

    @staticmethod
    def _grant_view(grant: _Grant) -> AccountGrantRecord:
        return AccountGrantRecord(
            owner_membership_id=grant.owner_membership_id,
            recipient_membership_id=grant.recipient_membership_id,
            id=grant.id,
            household_id=grant.household_id,
            account_id=grant.account_id,
            owner_user_id=grant.owner_user_id,
            permission=grant.permission,
            created_at=grant.created_at,
            revoked_at=grant.revoked_at,
        )

    def replace_grants(self, *, user_id, household_id, account_id, recipients):
        h = self._require_member(user_id=user_id, household_id=household_id)
        if self._accounts.owned_account(user_id=user_id, account_id=account_id) is None:
            raise AccountNotOwned()
        if len({r.membership_id for r in recipients}) != len(recipients):
            raise MemberNotFound()
        for r in recipients:
            self.create_grant(
                user_id=user_id,
                household_id=household_id,
                account_id=account_id,
                permission=r.permission,
                recipient_membership_id=r.membership_id,
            )
        for g in h.grants:
            if (
                g.account_id == account_id
                and g.recipient_membership_id not in {r.membership_id for r in recipients}
                and g.revoked_at is None
            ):
                g.revoked_at = self._clock()

    def execute(self, *, actor, operation, key, body, household_id, action):
        with self._lock:
            identity = canonical_hash(body)
            receipt = self._receipts.get((actor, operation, key))
            if receipt:
                if receipt[0] != identity:
                    raise IdempotencyConflict()
                _, hid, mid, iid = receipt
                h = self._households[hid]
                m = next((m for m in h.members if m.id == mid), None)
                invitation = None
                if iid:
                    if not m or m.left_at or h.admin_user_id != actor:
                        raise AdminRequired()
                    i = next(i for i in h.invitations if i.id == iid)
                    invitation = InvitationCreated(
                        id=i.id, household_id=hid, expires_at=i.expires_at, token=None
                    )
                return CommandResult(
                    household_id=hid,
                    membership_id=mid,
                    state="active"
                    if m and m.left_at is None and h.status == "active"
                    else "departed",
                    replayed=True,
                    invitation=invitation,
                )
            if household_id:
                h = self._require_member(user_id=actor, household_id=household_id)
                if body.get("expected_version") != h.version:
                    raise StaleVersion()
            before = deepcopy((self._households, self._invites_by_hash, self._codes))
            try:
                value = action()
                hid = household_id or (
                    value.household_id
                    if isinstance(value, AcceptanceResult)
                    else value.id
                )
                h = self._households[hid]
                mid = (
                    value.membership_id
                    if isinstance(value, AcceptanceResult)
                    else next(
                        (m.id for m in reversed(h.members) if m.user_id == actor), None
                    )
                )
                i = value if isinstance(value, InvitationCreated) else None
                if household_id or isinstance(value, AcceptanceResult):
                    h.version += 1
                self._receipts[(actor, operation, key)] = (
                    identity,
                    hid,
                    mid,
                    i.id if i else None,
                )
                m = next((m for m in h.members if m.id == mid), None)
                return CommandResult(
                    household_id=hid,
                    membership_id=mid,
                    state="active"
                    if m and m.left_at is None and h.status == "active"
                    else "departed",
                    replayed=False,
                    invitation=i,
                )
            except Exception:
                self._households, self._invites_by_hash, self._codes = before
                raise


def _trim_name(name: str | None) -> str | None:
    if name is None:
        return None
    trimmed = name.strip()
    return trimmed or None


def _ref_from_stored(stored) -> OwnedAccountRef:  # noqa: ANN001
    facts = stored.account
    return OwnedAccountRef(
        id=facts.id,
        user_id=facts.user_id,
        type=facts.type,
        currency=facts.currency,
        nickname=facts.nickname,
        archived=facts.archived,
        ownership_share_bps=facts.ownership_share_bps,
    )


class FinancialAccountLookup:
    """Adapts a financial-account repository into OwnedAccountRef lookups."""

    def __init__(self, repository) -> None:  # noqa: ANN001
        self._repository = repository

    def owned_account(self, *, user_id: str, account_id: str) -> OwnedAccountRef | None:
        stored = self._repository.get_account(
            user_id=user_id, account_id=account_id, scope=PERSONAL
        )
        if stored is None:
            return None
        return _ref_from_stored(stored)

    def account_by_id(self, *, account_id: str) -> OwnedAccountRef | None:
        getter = getattr(self._repository, "get_any_account", None)
        if getter is None:
            return None
        stored = getter(account_id=account_id)
        if stored is None:
            return None
        return _ref_from_stored(stored)
