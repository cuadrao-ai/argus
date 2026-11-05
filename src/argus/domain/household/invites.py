"""Beta invites, the founder group link, beta admission and network numbers.

Decisions 1 to 5, 12 and 13 of the October 2 lane locks. Postgres only: the
record is durable and the numbers are computed in SQL from it.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from psycopg_pool import ConnectionPool

from argus.domain.household import invite_record as record
from argus.domain.household.errors import (
    BetaInviteRequired,
    BetaQuotaExhausted,
    FounderRequired,
    GroupLinkFull,
    HouseholdInvitationKind,
    InvitationConsumed,
    InvitationExpired,
    InvitationNotFound,
    InvitationRevoked,
    InviteRuleViolation,
    VerifiedUserRequired,
)
from argus.domain.household.invite_codes import (
    CodeHasher,
    InviteSettings,
    format_code,
    invite_link,
    store_code,
    unique_code,
)
from argus.domain.household.invite_schemas import (
    BetaAccess,
    BetaInviteCreated,
    BetaInviteCreatedResponse,
    CreateGroupLinkRequest,
    GroupLinkNumbers,
    GroupLinkView,
    InvitePreview,
    InviteQuota,
    KindNumbers,
    NetworkNumbers,
    QuotaGrantRequest,
    QuotaGrantResult,
    RedeemResult,
    SentInvite,
    SentInvitesResponse,
)
from argus.domain.household.repository import (
    INVITE_TTL,
    code_hasher,
    hash_token,
    locate_secret,
)
from argus.domain.recording.errors import IdempotencyConflict

GROUP_LINK_MAX_LIFETIME = timedelta(days=365)


def verified_user(user_id: str | None) -> str:
    """The caller is the verified JWT subject; a missing one owns nothing.

    Under service_role or an unauthenticated session auth.uid() is null. A
    null, empty or malformed id must never match a created_by, a sender or the
    founder, so every store entry point refuses it before touching a row.
    """
    if not isinstance(user_id, str) or not user_id.strip():
        raise VerifiedUserRequired()
    try:
        return str(UUID(user_id))
    except ValueError as exc:
        raise VerifiedUserRequired() from exc


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _share(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


def _lock(c, key: str) -> None:  # noqa: ANN001
    c.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))", (key,))


def _state(accepted_at, revoked_at, expires_at, now) -> str:  # noqa: ANN001
    if accepted_at is not None:
        return "accepted"
    if revoked_at is not None:
        return "revoked"
    if expires_at is not None and expires_at <= now:
        return "expired"
    return "pending"


class PostgresInviteStore:
    # The single-use path locks the row, then claims the use with a guarded
    # update whose row count is checked. Tests drop the lock to prove the
    # guarded update alone still admits one person.
    _single_use_lock = " for update"

    def __init__(
        self,
        pool: ConnectionPool,
        *,
        settings: InviteSettings | None = None,
        clock=_utcnow,  # noqa: ANN001
        code_hasher: CodeHasher | None = None,
    ) -> None:
        self._pool = pool
        self.settings = settings or InviteSettings.from_env()
        self._clock = clock
        self._hasher = code_hasher

    # -- Gate -------------------------------------------------------------
    def access(self, *, user_id: str) -> BetaAccess:
        user_id = verified_user(user_id)
        with self._pool.connection() as c:
            admitted = self._admitted(c, user_id)
        gate = self.settings.gate_enabled
        return BetaAccess(
            gate_enabled=gate,
            admitted=admitted or not gate,
            waitlist_url=self.settings.waitlist_url,
            testflight_url=self.settings.testflight_url,
        )

    def _admitted(self, c, user_id: str) -> bool:  # noqa: ANN001
        return (
            self.settings.is_founder(user_id) or record.admission(c, user_id) is not None
        )

    # -- Quota ------------------------------------------------------------
    def _quota(self, c, user_id: str) -> InviteQuota:  # noqa: ANN001
        extra, used = c.execute(
            "select (select coalesce(sum(extra),0) from public.beta_invite_quota_grants"
            " where user_id=%s),"
            " (select count(*) from public.beta_invitations where created_by=%s"
            " and kind='beta' and revoked_at is null and (use_count>0 or expires_at>%s))",
            (user_id, user_id, self._clock()),
        ).fetchone()
        limit = self.settings.quota + int(extra)
        return InviteQuota(limit=limit, used=int(used), remaining=max(0, limit - used))

    # -- Beta invites -----------------------------------------------------
    def create_beta(
        self, *, user_id: str, key: str, request_hash: str
    ) -> BetaInviteCreatedResponse:
        user_id = verified_user(user_id)
        with self._pool.connection() as c, c.transaction():
            _lock(c, user_id + ":beta-invite")
            replay = self._replay(c, user_id, key, request_hash)
            if replay is not None:
                return BetaInviteCreatedResponse(
                    invitation=replay, quota=self._quota(c, user_id)
                )
            if self.settings.gate_enabled and not self._admitted(c, user_id):
                raise BetaInviteRequired()
            if self._quota(c, user_id).remaining <= 0:
                raise BetaQuotaExhausted()
            created = self._insert(
                c,
                kind="beta",
                user_id=user_id,
                key=key,
                request_hash=request_hash,
                max_uses=1,
                expires_at=self._clock() + INVITE_TTL,
            )
            return BetaInviteCreatedResponse(
                invitation=created, quota=self._quota(c, user_id)
            )

    def _replay(self, c, user_id, key, request_hash) -> BetaInviteCreated | None:  # noqa: ANN001
        row = c.execute(
            "select id,kind,expires_at,request_hash,source_label,max_uses"
            " from public.beta_invitations where created_by=%s and idempotency_key=%s",
            (user_id, key),
        ).fetchone()
        if row is None:
            return None
        if row[3] != request_hash:
            raise IdempotencyConflict()
        return BetaInviteCreated(
            id=str(row[0]),
            kind=row[1],
            expires_at=row[2],
            source_label=row[4],
            cap=row[5] if row[1] == "group_link" else None,
            replayed=True,
        )

    def _insert(
        self,
        c,  # noqa: ANN001
        *,
        kind: str,
        user_id: str,
        key: str,
        request_hash: str,
        max_uses: int,
        expires_at: datetime,
        source_label: str | None = None,
    ) -> BetaInviteCreated:
        now = self._clock()
        token = secrets.token_urlsafe(32)
        code, code_digest = unique_code(c, code_hasher(self._hasher))
        iid = str(uuid4())
        c.execute(
            "insert into public.beta_invitations(id,kind,token_hash,created_by,"
            "source_label,max_uses,created_at,expires_at,idempotency_key,request_hash)"
            " values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                iid,
                kind,
                hash_token(token),
                user_id,
                source_label,
                max_uses,
                now,
                expires_at,
                key,
                request_hash,
            ),
        )
        store_code(c, code_digest, beta_invitation_id=iid)
        if kind == "beta":
            record.record_sent(
                c, kind="beta", sender=user_id, at=now, beta_invitation_id=iid
            )
        return BetaInviteCreated(
            id=iid,
            kind=kind,
            expires_at=expires_at,
            token=token,
            code=format_code(code),
            link=invite_link(token, household=False, settings=self.settings),
            source_label=source_label,
            cap=max_uses if kind == "group_link" else None,
        )

    def sent(self, *, user_id: str) -> SentInvitesResponse:
        user_id = verified_user(user_id)
        now = self._clock()
        with self._pool.connection() as c:
            rows = c.execute(
                "select r.id,r.kind,coalesce(r.beta_invitation_id,r.household_invitation_id),"
                " r.sent_at,r.accepted_at,coalesce(b.revoked_at,h.revoked_at),"
                " coalesce(b.expires_at,h.expires_at)"
                " from public.invite_referrals r"
                " left join public.beta_invitations b on b.id=r.beta_invitation_id"
                " left join public.household_invitations h on h.id=r.household_invitation_id"
                " where r.sender_user_id=%s and r.kind in ('beta','household')"
                " order by r.sent_at desc limit 200",
                (user_id,),
            ).fetchall()
            quota = self._quota(c, user_id)
        return SentInvitesResponse(
            quota=quota,
            invitations=[
                SentInvite(
                    id=str(r[0]),
                    kind=r[1],
                    invitation_id=str(r[2]) if r[2] else None,
                    state=_state(r[4], r[5], r[6], now),
                    sent_at=r[3],
                    expires_at=r[6],
                    accepted_at=r[4],
                )
                for r in rows
            ],
        )

    def revoke(self, *, user_id: str, invitation_id: str) -> None:
        user_id = verified_user(user_id)
        with self._pool.connection() as c, c.transaction():
            row = c.execute(
                "select use_count,revoked_at from public.beta_invitations"
                " where id=%s and created_by=%s and kind='beta' for update",
                (invitation_id, user_id),
            ).fetchone()
            if row is None:
                raise InvitationNotFound()
            if row[0] > 0:
                raise InvitationConsumed()
            if row[1] is None:
                c.execute(
                    "update public.beta_invitations set revoked_at=%s where id=%s",
                    (self._clock(), invitation_id),
                )

    # -- Preview and redeem ----------------------------------------------
    def preview(self, *, token: str | None, code: str | None) -> InvitePreview:
        now = self._clock()
        with self._pool.connection() as c:
            column, digest = locate_secret(c, token, code, self._hasher)
            row = c.execute(
                f"select kind,expires_at,revoked_at,use_count,max_uses"  # noqa: S608
                f" from public.beta_invitations where {column}=%s",
                (digest,),
            ).fetchone()
            if row is not None:
                return InvitePreview(
                    kind=row[0],
                    expires_at=row[1],
                    available=row[2] is None and row[1] > now and row[3] < row[4],
                )
            row = c.execute(
                f"select h.name,i.expires_at,i.revoked_at,i.accepted_at,h.status"  # noqa: S608
                f" from public.household_invitations i"
                f" join public.households h on h.id=i.household_id where i.{column}=%s",
                (digest,),
            ).fetchone()
        if row is None:
            raise InvitationNotFound()
        return InvitePreview(
            kind="household",
            household_name=row[0],
            expires_at=row[1],
            available=row[2] is None
            and row[3] is None
            and row[4] == "active"
            and row[1] > now,
        )

    def redeem(
        self, *, user_id: str, token: str | None, code: str | None
    ) -> RedeemResult:
        user_id = verified_user(user_id)
        full = False
        with self._pool.connection() as c, c.transaction():
            _lock(c, user_id + ":beta-redeem")
            column, digest = locate_secret(c, token, code, self._hasher)
            row = c.execute(
                f"select id,kind from public.beta_invitations where {column}=%s",  # noqa: S608
                (digest,),
            ).fetchone()
            if row is None:
                household = c.execute(
                    f"select 1 from public.household_invitations where {column}=%s",  # noqa: S608
                    (digest,),
                ).fetchone()
                raise HouseholdInvitationKind() if household else InvitationNotFound()
            iid, kind = str(row[0]), row[1]
            if kind == "beta":
                return self._redeem_single(c, user_id, iid)
            result = self._redeem_group(c, user_id, iid)
            if result is None:
                full = True
        if full:
            raise GroupLinkFull()
        return result

    def _check_open(self, revoked_at, expires_at) -> None:  # noqa: ANN001
        if revoked_at is not None:
            raise InvitationRevoked()
        if expires_at <= self._clock():
            raise InvitationExpired()

    def _redeem_single(self, c, user_id: str, iid: str) -> RedeemResult:  # noqa: ANN001
        use_count, revoked_at, expires_at = c.execute(
            "select use_count,revoked_at,expires_at from public.beta_invitations"
            " where id=%s" + self._single_use_lock,
            (iid,),
        ).fetchone()
        if use_count > 0:
            accepted = c.execute(
                "select acceptor_user_id from public.invite_referrals"
                " where beta_invitation_id=%s and kind='beta'",
                (iid,),
            ).fetchone()
            if accepted and accepted[0] is not None and str(accepted[0]) == user_id:
                return RedeemResult(
                    admitted=True, outcome="admitted", kind="beta", replayed=True
                )
            raise InvitationConsumed()
        self._check_open(revoked_at, expires_at)
        if self._admitted(c, user_id):
            # Already in: the invite stays unused for someone else.
            return RedeemResult(admitted=True, outcome="already_admitted", kind="beta")
        now = self._clock()
        claimed = c.execute(
            "update public.beta_invitations set use_count=1 where id=%s and use_count=0",
            (iid,),
        ).rowcount
        if claimed != 1:
            # Second guard behind the row lock: someone else took the one use.
            # Raising rolls back, so nothing below runs for the loser.
            raise InvitationConsumed()
        rid = c.execute(
            "update public.invite_referrals set acceptor_user_id=%s,accepted_at=%s"
            " where beta_invitation_id=%s and kind='beta' returning id",
            (user_id, now, iid),
        ).fetchone()[0]
        record.admit(c, user_id, "beta_invitation", str(rid), now)
        return RedeemResult(admitted=True, outcome="admitted", kind="beta")

    def _redeem_group(self, c, user_id: str, iid: str) -> RedeemResult | None:  # noqa: ANN001
        if c.execute(
            "select 1 from public.invite_referrals where beta_invitation_id=%s"
            " and kind='group_link' and acceptor_user_id=%s",
            (iid, user_id),
        ).fetchone():
            return RedeemResult(
                admitted=True, outcome="admitted", kind="group_link", replayed=True
            )
        revoked_at, expires_at = c.execute(
            "select revoked_at,expires_at from public.beta_invitations where id=%s",
            (iid,),
        ).fetchone()
        self._check_open(revoked_at, expires_at)
        if self._admitted(c, user_id):
            return RedeemResult(
                admitted=True, outcome="already_admitted", kind="group_link"
            )
        now = self._clock()
        # One locked step: concurrent taps re-check the cap on the new row version.
        taken = c.execute(
            "update public.beta_invitations set use_count=use_count+1"
            " where id=%s and revoked_at is null and expires_at>%s and use_count<max_uses"
            " returning use_count",
            (iid, now),
        ).fetchone()
        if taken is None:
            # The guarded update can miss for three reasons. Read the locked row
            # to tell them apart: only a full link counts as overflow.
            revoked_at, expires_at, use_count, max_uses = c.execute(
                "select revoked_at,expires_at,use_count,max_uses"
                " from public.beta_invitations where id=%s for update",
                (iid,),
            ).fetchone()
            if revoked_at is not None:
                raise InvitationRevoked()
            if expires_at <= now:
                raise InvitationExpired()
            if use_count < max_uses:  # pragma: no cover - the update would have won
                raise InviteRuleViolation("The link changed. Try again.")
            c.execute(
                "update public.beta_invitations set overflow_count=overflow_count+1"
                " where id=%s",
                (iid,),
            )
            return None
        rid = str(uuid4())
        c.execute(
            "insert into public.invite_referrals(id,kind,beta_invitation_id,"
            "acceptor_user_id,sent_at,accepted_at) values(%s,'group_link',%s,%s,%s,%s)",
            (rid, iid, user_id, now, now),
        )
        record.admit(c, user_id, "group_link", rid, now)
        return RedeemResult(admitted=True, outcome="admitted", kind="group_link")

    # -- Founder ----------------------------------------------------------
    def _founder(self, user_id: str) -> None:
        if not self.settings.is_founder(verified_user(user_id)):
            raise FounderRequired()

    def create_group_link(
        self,
        *,
        user_id: str,
        request: CreateGroupLinkRequest,
        key: str,
        request_hash: str,
    ) -> BetaInviteCreatedResponse:
        self._founder(user_id)
        label = (request.source_label or "").strip()
        if not label:
            raise InviteRuleViolation("A group link needs a source label.")
        now = self._clock()
        expires_at = request.expires_at
        if expires_at.tzinfo is None:
            raise InviteRuleViolation("The expiry date needs a time zone.")
        with self._pool.connection() as c, c.transaction():
            _lock(c, user_id + ":beta-invite")
            replay = self._replay(c, user_id, key, request_hash)
            if replay is not None:
                return BetaInviteCreatedResponse(invitation=replay)
            if not now < expires_at <= now + GROUP_LINK_MAX_LIFETIME:
                raise InviteRuleViolation(
                    "The expiry date must be in the future and within a year."
                )
            created = self._insert(
                c,
                kind="group_link",
                user_id=user_id,
                key=key,
                request_hash=request_hash,
                max_uses=request.cap,
                expires_at=expires_at,
                source_label=label,
            )
            return BetaInviteCreatedResponse(invitation=created)

    def group_links(self, *, user_id: str) -> list[GroupLinkView]:
        self._founder(user_id)
        now = self._clock()
        with self._pool.connection() as c:
            rows = c.execute(
                "select id,source_label,max_uses,use_count,overflow_count,expires_at,revoked_at"
                " from public.beta_invitations where kind='group_link'"
                " order by created_at desc"
            ).fetchall()
        return [
            GroupLinkView(
                id=str(r[0]),
                source_label=r[1],
                cap=r[2],
                redeemed=r[3],
                overflow=r[4],
                expires_at=r[5],
                revoked_at=r[6],
                state="revoked"
                if r[6]
                else "expired"
                if r[5] <= now
                else "full"
                if r[3] >= r[2]
                else "open",
            )
            for r in rows
        ]

    def revoke_group_link(self, *, user_id: str, link_id: str) -> None:
        self._founder(user_id)
        with self._pool.connection() as c, c.transaction():
            row = c.execute(
                "update public.beta_invitations set revoked_at=coalesce(revoked_at,%s)"
                " where id=%s and kind='group_link' returning id",
                (self._clock(), link_id),
            ).fetchone()
        if row is None:
            raise InvitationNotFound()

    def grant_quota(
        self, *, user_id: str, request: QuotaGrantRequest, key: str, request_hash: str
    ) -> QuotaGrantResult:
        self._founder(user_id)
        try:
            target = str(UUID(request.user_id))
        except ValueError:
            raise InviteRuleViolation("No such user.") from None
        with self._pool.connection() as c, c.transaction():
            _lock(c, user_id + ":beta-quota")
            row = c.execute(
                "select id,user_id,extra,request_hash from public.beta_invite_quota_grants"
                " where granted_by=%s and idempotency_key=%s",
                (user_id, key),
            ).fetchone()
            if row is not None:
                if row[3] != request_hash:
                    raise IdempotencyConflict()
                return QuotaGrantResult(
                    id=str(row[0]), user_id=str(row[1]), extra=row[2], replayed=True
                )
            exists = c.execute(
                "select 1 from auth.users where id=%s and coalesce(is_anonymous,false)=false",
                (target,),
            ).fetchone()
            if exists is None:
                raise InviteRuleViolation("No such user.")
            gid = str(uuid4())
            c.execute(
                "insert into public.beta_invite_quota_grants(id,user_id,granted_by,extra,"
                "created_at,idempotency_key,request_hash) values(%s,%s,%s,%s,%s,%s,%s)",
                (gid, target, user_id, request.extra, self._clock(), key, request_hash),
            )
        return QuotaGrantResult(id=gid, user_id=target, extra=request.extra)

    def network(self, *, user_id: str) -> NetworkNumbers:
        self._founder(user_id)
        onward = "exists(select 1 from public.invite_referrals o where o.inviter_origin_id=r.id)"
        with self._pool.connection() as c:
            kinds = {
                row[0]: row[1:]
                for row in c.execute(
                    "select r.kind,count(*),count(distinct r.sender_ref),count(r.accepted_at),"
                    f" count(*) filter (where r.accepted_at is not null and {onward})"
                    " from public.invite_referrals r"
                    " where r.kind in ('beta','household') group by r.kind"
                ).fetchall()
            }
            links = c.execute(
                "select b.id,b.source_label,b.max_uses,b.use_count,b.overflow_count,"
                " (select count(*) from public.invite_referrals r"
                f"  where r.beta_invitation_id=b.id and r.kind='group_link' and {onward})"
                " from public.beta_invitations b where b.kind='group_link'"
                " order by b.created_at"
            ).fetchall()

        def numbers(kind: str) -> KindNumbers:
            sent, senders, accepted, invited = kinds.get(kind, (0, 0, 0, 0))
            return KindNumbers(
                sent=sent,
                senders=senders,
                sent_per_sender=round(sent / senders, 4) if senders else None,
                accepted=accepted,
                accepted_share=_share(accepted, sent),
                invitees_who_invited=invited,
                invitees_who_invited_share=_share(invited, accepted),
            )

        return NetworkNumbers(
            beta=numbers("beta"),
            household=numbers("household"),
            group_links=[
                GroupLinkNumbers(
                    id=str(r[0]),
                    source_label=r[1],
                    cap=r[2],
                    redeemed=r[3],
                    overflow=r[4],
                    invitees_who_invited=r[5],
                    invitees_who_invited_share=_share(r[5], r[3]),
                )
                for r in links
            ],
        )
