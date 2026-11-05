"""Real-Postgres proof for the Household lane invites (decisions 1-5, 12, 13).

Set ``ARGUS_DISPOSABLE_DATABASE_URL`` only to an isolated Supabase Postgres
database with every checked-in migration applied. Proves what the in-memory
twin cannot: link token and code for one invitation, single use, the who-
invited-whom record and its anonymity after account deletion, the 10-invite
quota and founder grants, the beta/household split, the founder group link cap
under concurrent redemption, the code gate, the network numbers, and the
absence of any client read or write path on the new tables.
"""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DSN, reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured"
)

psycopg = pytest.importorskip("psycopg")
psycopg_pool = pytest.importorskip("psycopg_pool")
pydantic = pytest.importorskip("pydantic")

from argus.domain.household.errors import (  # noqa: E402
    AdminRequired,
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
from argus.domain.household.invite_codes import CodeHasher, InviteSettings  # noqa: E402
from argus.domain.household.invite_schemas import (  # noqa: E402
    CreateGroupLinkRequest,
    QuotaGrantRequest,
)
from argus.domain.household.invites import PostgresInviteStore  # noqa: E402
from argus.domain.household.postgres import PostgresHouseholdRepository  # noqa: E402
from argus.domain.household.repository import FinancialAccountLookup  # noqa: E402
from argus.domain.household.schemas import CreateHouseholdRequest  # noqa: E402
from argus.domain.household.service import HouseholdService  # noqa: E402
from argus.domain.recording.errors import IdempotencyConflict  # noqa: E402
from argus.domain.recording.postgres_repository import (  # noqa: E402
    PostgresFinancialAccountRepository,
)

NEW_TABLES = (
    "beta_invitations",
    "invite_referrals",
    "beta_admissions",
    "beta_invite_quota_grants",
    "invite_sender_refs",
)


class Clock:
    def __init__(self) -> None:
        self.now = datetime.now(timezone.utc).replace(microsecond=0)

    def __call__(self) -> datetime:
        return self.now


TEST_CODE_SECRET = "postgres-invite-tests-code-secret-0123456789"
TEST_HASHER = CodeHasher.from_secrets(TEST_CODE_SECRET)


class Lane:
    def __init__(self, pool, users, clock, settings, hasher=TEST_HASHER) -> None:  # noqa: ANN001
        self.pool = pool
        self.users = users
        self.clock = clock
        self.settings = settings
        self.hasher = hasher
        self.store = PostgresInviteStore(
            pool, settings=settings, clock=clock, code_hasher=hasher
        )
        self.households = HouseholdService(
            PostgresHouseholdRepository(
                pool,
                FinancialAccountLookup(PostgresFinancialAccountRepository(pool)),
                clock=clock,
                code_hasher=hasher,
            ),
            invite_settings=settings,
        )
        self.invitation_ids: set[str] = set()
        self.referral_ids: set[str] = set()

    @property
    def founder(self) -> str:
        return self.users[0]

    def beta(self, user: str, key: str | None = None):  # noqa: ANN201
        created = self.store.create_beta(
            user_id=user, key=key or str(uuid4()), request_hash="{}"
        )
        self.invitation_ids.add(created.invitation.id)
        return created

    def group_link(self, cap: int, *, days: int = 7, label: str = "Chat", key=None):  # noqa: ANN001, ANN201
        created = self.store.create_group_link(
            user_id=self.founder,
            request=CreateGroupLinkRequest(
                source_label=label,
                cap=cap,
                expires_at=self.clock.now + timedelta(days=days),
            ),
            key=key or str(uuid4()),
            request_hash=f"group:{label}:{cap}:{days}",
        )
        self.invitation_ids.add(created.invitation.id)
        return created.invitation

    def household(self, admin: str) -> str:
        return self.households.create(
            user_id=admin, request=CreateHouseholdRequest(name="Casa")
        ).id

    def row(self, sql: str, *args):  # noqa: ANN002, ANN201
        with self.pool.connection() as c:
            return c.execute(sql, args).fetchone()

    def numbers(self):  # noqa: ANN201
        return self.store.network(user_id=self.founder)


def _users(pool, count: int) -> list[str]:  # noqa: ANN001
    ids = [str(uuid4()) for _ in range(count)]
    with pool.connection() as c:
        for uid in ids:
            c.execute(
                "insert into auth.users(id,email,is_anonymous) values(%s,%s,false)",
                (uid, f"invite-{uid}@example.test"),
            )
    return ids


def _make_lane(count: int = 6, **settings) -> Lane:  # noqa: ANN003
    pool = psycopg_pool.ConnectionPool(DSN, min_size=1, max_size=30, open=True)
    users = _users(pool, count)
    clock = Clock()
    defaults = {
        "founder_user_id": users[0],
        "waitlist_url": "https://cuadrao.ai/waitlist",
    }
    return Lane(pool, users, clock, InviteSettings(**(defaults | settings)))


def _cleanup(lane: Lane) -> None:
    users = lane.users
    with lane.pool.connection() as c, c.transaction():
        hids = [
            r[0]
            for r in c.execute(
                "select id from public.households where created_by=any(%s::uuid[])",
                (users,),
            ).fetchall()
        ]
        invitations = list(lane.invitation_ids) + [
            str(r[0])
            for r in c.execute(
                "select id from public.beta_invitations where created_by=any(%s::uuid[])",
                (users,),
            ).fetchall()
        ]
        c.execute(
            "delete from public.invite_referrals where id=any(%s::uuid[])"
            " or beta_invitation_id=any(%s::uuid[])"
            " or sender_user_id=any(%s::uuid[]) or acceptor_user_id=any(%s::uuid[])"
            " or household_invitation_id in"
            " (select id from public.household_invitations where household_id=any(%s::uuid[]))",
            (list(lane.referral_ids), invitations, users, users, hids),
        )
        c.execute(
            "delete from public.beta_invitations where id=any(%s::uuid[])", (invitations,)
        )
        for table in (
            "household_command_receipts",
            "household_account_grants",
            "household_invitations",
            "household_members",
        ):
            column = (
                "actor_id" if table == "household_command_receipts" else "household_id"
            )
            values = users if column == "actor_id" else hids
            c.execute(
                f"delete from public.{table} where {column}=any(%s::uuid[])",  # noqa: S608
                (values,),
            )
        c.execute("delete from public.households where id=any(%s::uuid[])", (hids,))
        c.execute("delete from auth.users where id=any(%s::uuid[])", (users,))
    lane.pool.close()


@pytest.fixture
def lane():
    value = _make_lane()
    try:
        yield value
    finally:
        _cleanup(value)


@pytest.fixture
def gated():
    value = _make_lane(gate_enabled=True)
    try:
        yield value
    finally:
        _cleanup(value)


# -- Household invitations: link, code, single use, record, beta admission ---


def test_household_invite_link_and_code_resolve_to_one_single_use_invitation(lane):
    admin, member, other, outsider = lane.users[1:5]
    hid = lane.household(admin)
    quota_before = lane.store.sent(user_id=admin).quota
    invite = lane.households.invite(user_id=admin, household_id=hid)
    assert invite.code and len(invite.code) == 14 and invite.code[4::5] == "--"
    assert invite.link == "argus-household://invite#" + invite.token

    by_token = lane.households.preview_invitation(user_id=member, token=invite.token)
    by_code = lane.households.preview_invitation(user_id=member, code=invite.code)
    typed = invite.code.lower().replace("-", " ")
    assert (
        by_token
        == by_code
        == lane.households.preview_invitation(user_id=member, code=typed)
    )
    assert by_code.available and by_code.name == "Casa"
    assert lane.store.preview(token=None, code=invite.code).kind == "household"

    accepted = lane.households.accept(user_id=member, code=invite.code)
    # A lost response retried by link token or code gives the same membership.
    assert lane.households.accept(user_id=member, token=invite.token) == accepted
    assert lane.households.accept(user_id=member, code=invite.code) == accepted
    with pytest.raises(InvitationConsumed):
        lane.households.accept(user_id=other, code=invite.code)
    with pytest.raises(InvitationNotFound):
        lane.households.accept(user_id=other, code="ZZZZ-ZZZZ-ZZZZ")
    with pytest.raises(HouseholdInvitationKind):
        lane.store.redeem(user_id=other, token=None, code=invite.code)

    # Household invites do not use the 10, and they let the invitee into the beta.
    assert lane.store.sent(user_id=admin).quota == quota_before
    assert lane.row(
        "select via from public.beta_admissions where user_id=%s", member
    ) == ("household_invitation",)
    referral = lane.row(
        "select kind,sender_user_id,acceptor_user_id,accepted_at is not null"
        " from public.invite_referrals where household_invitation_id=%s",
        invite.id,
    )
    assert referral[0] == "household"
    assert str(referral[1]) == admin and str(referral[2]) == member and referral[3]
    sent = lane.store.sent(user_id=admin).invitations
    assert [(s.kind, s.state) for s in sent] == [("household", "accepted")]
    assert sent[0].accepted_at is not None  # the inviter's "accepted" record

    # Only the current admin creates household invites; a third user sees 404.
    with pytest.raises(AdminRequired):
        lane.households.invite(user_id=member, household_id=hid)
    from argus.domain.household.errors import HouseholdNotFound

    with pytest.raises(HouseholdNotFound):
        lane.households.get(user_id=outsider, household_id=hid)


def test_household_revoke_and_expiry_keep_existing_errors_by_code(lane):
    admin, member = lane.users[1:3]
    hid = lane.household(admin)
    revoked = lane.households.invite(user_id=admin, household_id=hid)
    lane.households.revoke_invitation(
        user_id=admin, household_id=hid, invitation_id=revoked.id
    )
    with pytest.raises(InvitationRevoked):
        lane.households.accept(user_id=member, code=revoked.code)
    expiring = lane.households.invite(user_id=admin, household_id=hid)
    lane.clock.now += timedelta(days=8)
    with pytest.raises(InvitationExpired):
        lane.households.accept(user_id=member, code=expiring.code)


def test_universal_link_flag_builds_cuadrao_link_with_secret_in_fragment():
    lane = _make_lane(universal_link_enabled=True)
    try:
        admin = lane.users[1]
        hid = lane.household(admin)
        invite = lane.households.invite(user_id=admin, household_id=hid)
        assert invite.link == "https://cuadrao.ai/invite#" + invite.token
        beta = lane.beta(admin).invitation
        assert beta.link == "https://cuadrao.ai/invite#" + beta.token
    finally:
        _cleanup(lane)


# -- Beta invites: single use, quota, revoke, expiry, idempotency ------------


def test_beta_invite_single_use_and_already_admitted_keeps_it_unused(lane):
    sender, invitee, other = lane.users[1:4]
    created = lane.beta(sender).invitation
    assert created.link is None and created.code and created.token
    assert lane.store.preview(token=created.token, code=None).available
    first = lane.store.redeem(user_id=invitee, token=None, code=created.code)
    assert first.outcome == "admitted" and not first.replayed
    replay = lane.store.redeem(user_id=invitee, token=created.token, code=None)
    assert replay.replayed and replay.admitted
    with pytest.raises(InvitationConsumed):
        lane.store.redeem(user_id=other, token=None, code=created.code)

    unused = lane.beta(sender).invitation
    already = lane.store.redeem(user_id=invitee, token=None, code=unused.code)
    assert already.outcome == "already_admitted"
    assert lane.row(
        "select use_count from public.beta_invitations where id=%s", unused.id
    ) == (0,)
    assert lane.store.redeem(user_id=other, token=None, code=unused.code).admitted


def test_beta_revoke_expiry_and_create_retry(lane):
    sender, invitee = lane.users[1:3]
    key = str(uuid4())
    first = lane.beta(sender, key)
    retry = lane.beta(sender, key)
    assert retry.invitation.id == first.invitation.id and retry.invitation.replayed
    assert retry.invitation.token is None and retry.invitation.code is None
    assert retry.quota.used == 1
    lane.store.revoke(user_id=sender, invitation_id=first.invitation.id)
    with pytest.raises(InvitationRevoked):
        lane.store.redeem(user_id=invitee, token=None, code=first.invitation.code)
    with pytest.raises(InvitationNotFound):
        lane.store.revoke(user_id=invitee, invitation_id=first.invitation.id)
    expiring = lane.beta(sender).invitation
    lane.clock.now += timedelta(days=8)
    with pytest.raises(InvitationExpired):
        lane.store.redeem(user_id=invitee, token=None, code=expiring.code)
    states = {
        s.invitation_id: s.state for s in lane.store.sent(user_id=sender).invitations
    }
    assert states == {first.invitation.id: "revoked", expiring.id: "expired"}


def test_eleventh_beta_invite_is_refused_until_the_founder_grants_more(lane):
    sender, stranger = lane.users[1:3]
    for _ in range(10):
        lane.beta(sender)
    with pytest.raises(BetaQuotaExhausted):
        lane.beta(sender)
    with pytest.raises(FounderRequired):
        lane.store.grant_quota(
            user_id=stranger,
            request=QuotaGrantRequest(user_id=sender, extra=1),
            key=str(uuid4()),
            request_hash="g",
        )
    key = str(uuid4())
    grant = lane.store.grant_quota(
        user_id=lane.founder,
        request=QuotaGrantRequest(user_id=sender, extra=1),
        key=key,
        request_hash="g",
    )
    again = lane.store.grant_quota(
        user_id=lane.founder,
        request=QuotaGrantRequest(user_id=sender, extra=1),
        key=key,
        request_hash="g",
    )
    assert again.replayed and again.id == grant.id
    with pytest.raises(IdempotencyConflict):
        lane.store.grant_quota(
            user_id=lane.founder,
            request=QuotaGrantRequest(user_id=sender, extra=2),
            key=key,
            request_hash="different",
        )
    eleventh = lane.beta(sender)
    assert eleventh.quota.limit == 11 and eleventh.quota.remaining == 0
    with pytest.raises(BetaQuotaExhausted):
        lane.beta(sender)


def test_concurrent_creates_cannot_pass_the_quota(lane):
    sender = lane.users[1]
    barrier = threading.Barrier(15)

    def create(_):  # noqa: ANN001, ANN202
        barrier.wait()
        try:
            lane.beta(sender)
            return "ok"
        except BetaQuotaExhausted:
            return "full"

    with ThreadPoolExecutor(max_workers=15) as pool:
        outcomes = list(pool.map(create, range(15)))
    assert outcomes.count("ok") == 10 and outcomes.count("full") == 5


def test_concurrent_redemptions_of_one_beta_code_admit_one_person(lane):
    sender = lane.users[1]
    invitees = _users(lane.pool, 8)
    lane.users.extend(invitees)
    code = lane.beta(sender).invitation.code
    barrier = threading.Barrier(len(invitees))

    def redeem(user):  # noqa: ANN001, ANN202
        barrier.wait()
        try:
            return lane.store.redeem(user_id=user, token=None, code=code).outcome
        except InvitationConsumed:
            return "consumed"

    with ThreadPoolExecutor(max_workers=len(invitees)) as pool:
        outcomes = list(pool.map(redeem, invitees))
    assert outcomes.count("admitted") == 1 and outcomes.count("consumed") == 7


# -- Founder group link: cap, concurrency, expiry, beta only -----------------


def test_group_link_requested_by_anyone_but_the_founder_is_refused(lane):
    with pytest.raises(FounderRequired):
        lane.store.create_group_link(
            user_id=lane.users[1],
            request=CreateGroupLinkRequest(
                source_label="Chat", cap=5, expires_at=lane.clock.now + timedelta(days=1)
            ),
            key=str(uuid4()),
            request_hash="x",
        )
    with pytest.raises(FounderRequired):
        lane.store.group_links(user_id=lane.users[1])
    with pytest.raises(FounderRequired):
        lane.store.network(user_id=lane.users[1])


def test_group_link_cap_holds_under_concurrent_redemption(lane):
    cap = 5
    link = lane.group_link(cap, label="Grupo 400")
    assert link.cap == cap and link.code and link.token
    people = _users(lane.pool, 20)
    lane.users.extend(people)
    barrier = threading.Barrier(len(people))

    def tap(user):  # noqa: ANN001, ANN202
        barrier.wait()
        try:
            return lane.store.redeem(user_id=user, token=link.token, code=None).outcome
        except GroupLinkFull:
            return "waitlist"

    with ThreadPoolExecutor(max_workers=len(people)) as pool:
        outcomes = list(pool.map(tap, people))
    assert outcomes.count("admitted") == cap
    assert outcomes.count("waitlist") == len(people) - cap
    assert lane.row(
        "select use_count,overflow_count from public.beta_invitations where id=%s",
        link.id,
    ) == (cap, len(people) - cap)
    admitted = [p for p, o in zip(people, outcomes, strict=True) if o == "admitted"]
    rows = lane.row(
        "select count(*),count(distinct acceptor_user_id),count(sender_user_id)"
        " from public.invite_referrals where beta_invitation_id=%s",
        link.id,
    )
    # Each redemption is its own row; the link, not a person, is the inviter.
    assert rows == (cap, cap, 0)
    # A replay by an admitted person does not take another place.
    assert lane.store.redeem(user_id=admitted[0], token=None, code=link.code).replayed
    # Beta only: no household membership was created.
    assert lane.row(
        "select count(*) from public.household_members where user_id=any(%s::uuid[])",
        people,
    ) == (0,)
    view = next(
        v for v in lane.store.group_links(user_id=lane.founder) if v.id == link.id
    )
    assert view.state == "full" and view.redeemed == cap


def test_expired_or_revoked_group_link_admits_no_one(lane):
    a, b = lane.users[1:3]
    expiring = lane.group_link(10, days=1, label="Expiring")
    revoked = lane.group_link(10, label="Revoked")
    lane.store.revoke_group_link(user_id=lane.founder, link_id=revoked.id)
    with pytest.raises(InvitationRevoked):
        lane.store.redeem(user_id=a, token=None, code=revoked.code)
    lane.clock.now += timedelta(days=2)
    with pytest.raises(InvitationExpired):
        lane.store.redeem(user_id=b, token=expiring.token, code=None)
    with pytest.raises(IdempotencyConflict):
        key = str(uuid4())
        lane.group_link(3, label="Same key", key=key)
        lane.group_link(4, label="Same key", key=key)


def test_group_link_closed_mid_redeem_is_not_counted_as_full(lane, monkeypatch):
    """Codex P2: a revoke or expiry after the open check is not overflow."""
    revoked = lane.group_link(5, label="Revoked mid-tap")
    expiring = lane.group_link(5, days=1, label="Expires mid-tap")
    a, b = lane.users[1:3]
    original = lane.store._check_open
    action = {}

    def check_then_close(revoked_at, expires_at):  # noqa: ANN001, ANN202
        original(revoked_at, expires_at)
        action.pop("run")()

    monkeypatch.setattr(lane.store, "_check_open", check_then_close)

    def revoke() -> None:
        # Another connection revokes between the open check and the guarded update.
        lane.store.revoke_group_link(user_id=lane.founder, link_id=revoked.id)

    def expire() -> None:
        lane.clock.now += timedelta(days=2)

    action["run"] = revoke
    with pytest.raises(InvitationRevoked):
        lane.store.redeem(user_id=a, token=None, code=revoked.code)
    action["run"] = expire
    with pytest.raises(InvitationExpired):
        lane.store.redeem(user_id=b, token=expiring.token, code=None)
    for link in (revoked, expiring):
        assert lane.row(
            "select use_count,overflow_count from public.beta_invitations where id=%s",
            link.id,
        ) == (0, 0)
    assert lane.row(
        "select count(*) from public.beta_admissions where user_id=any(%s::uuid[])",
        [a, b],
    ) == (0,)


def test_blank_group_link_label_is_refused_before_insert(lane):
    """Codex P2: a whitespace label is a validation error, never a 500."""
    with pytest.raises(pydantic.ValidationError):
        CreateGroupLinkRequest(
            source_label="   ", cap=3, expires_at=lane.clock.now + timedelta(days=1)
        )
    smuggled = CreateGroupLinkRequest.model_construct(
        source_label="   ", cap=3, expires_at=lane.clock.now + timedelta(days=1)
    )
    with pytest.raises(InviteRuleViolation):
        lane.store.create_group_link(
            user_id=lane.founder, request=smuggled, key=str(uuid4()), request_hash="x"
        )
    assert lane.row(
        "select count(*) from public.beta_invitations where created_by=%s"
        " and kind='group_link'",
        lane.founder,
    ) == (0,)


# -- Gate ---------------------------------------------------------------------


def test_gate_sends_people_without_a_code_to_the_waitlist(gated):
    newcomer, invitee = gated.users[1:3]
    access = gated.store.access(user_id=newcomer)
    assert access.gate_enabled and not access.admitted
    assert access.waitlist_url == "https://cuadrao.ai/waitlist"
    with pytest.raises(BetaInviteRequired):
        gated.beta(newcomer)
    assert gated.store.access(user_id=gated.founder).admitted
    code = gated.beta(gated.founder).invitation.code
    gated.store.redeem(user_id=invitee, token=None, code=code)
    assert gated.store.access(user_id=invitee).admitted
    assert gated.beta(invitee).invitation.code


def test_gate_off_keeps_todays_behavior(lane):
    access = lane.store.access(user_id=lane.users[1])
    assert not access.gate_enabled and access.admitted


# -- Network numbers and the anonymous record after deletion ------------------


def test_numbers_split_kinds_and_survive_account_deletion(lane):
    a, b, c, d, admin = lane.users[1:6]
    before = lane.numbers()
    # Chain: A invites B, B invites C, C never accepts. One unused invite from A.
    b_code = lane.beta(a).invitation.code
    lane.store.redeem(user_id=b, token=None, code=b_code)
    lane.beta(b)
    lane.beta(a)
    # Household invite, counted apart from beta.
    hid = lane.household(admin)
    hinv = lane.households.invite(user_id=admin, household_id=hid)
    lane.households.accept(user_id=d, code=hinv.code)
    link = lane.group_link(3, label="Primos")
    lane.store.redeem(user_id=c, token=link.token, code=None)

    after = lane.numbers()
    assert after.beta.sent - before.beta.sent == 3
    assert after.beta.accepted - before.beta.accepted == 1
    assert after.beta.invitees_who_invited - before.beta.invitees_who_invited == 1
    assert after.household.sent - before.household.sent == 1
    assert after.household.accepted - before.household.accepted == 1
    mine = next(g for g in after.group_links if g.id == link.id)
    assert (mine.source_label, mine.redeemed, mine.cap) == ("Primos", 1, 3)

    with lane.pool.connection() as conn:
        lane.referral_ids.update(
            str(r[0])
            for r in conn.execute(
                "select id from public.invite_referrals where sender_user_id=any(%s::uuid[])"
                " or acceptor_user_id=any(%s::uuid[])",
                (lane.users, lane.users),
            ).fetchall()
        )
    # Delete the acceptor, then the sender.
    with lane.pool.connection() as conn:
        conn.execute("delete from auth.users where id=%s", (b,))
        conn.execute("delete from auth.users where id=%s", (a,))
    final = lane.numbers()
    for kind in ("beta", "household"):
        old, new = getattr(after, kind), getattr(final, kind)
        assert (old.sent, old.senders, old.accepted, old.invitees_who_invited) == (
            new.sent,
            new.senders,
            new.accepted,
            new.invitees_who_invited,
        )
    with lane.pool.connection() as conn:
        for table in (*NEW_TABLES, "household_invitations"):
            for uid in (a, b):
                hit = conn.execute(
                    f"select count(*) from public.{table} t where t::text like %s",  # noqa: S608
                    (f"%{uid}%",),
                ).fetchone()[0]
                assert hit == 0, f"{table} still holds a deleted user id"
        # The chain survives: the row that admitted B still has B's onward invite.
        chain = conn.execute(
            "select count(*) from public.invite_referrals r"
            " join public.invite_referrals o on o.inviter_origin_id=r.id"
            " where r.id=any(%s::uuid[]) and r.kind='beta'",
            (list(lane.referral_ids),),
        ).fetchone()[0]
        assert chain == 1


def test_clients_cannot_read_or_write_the_new_tables(lane):
    uid = lane.users[1]
    lane.beta(uid)
    with lane.pool.connection() as conn:
        for table in NEW_TABLES:
            for statement in (
                f"select * from public.{table}",  # noqa: S608
                f"delete from public.{table}",  # noqa: S608
            ):
                for role in ("anon", "authenticated"):
                    with pytest.raises(psycopg.errors.InsufficientPrivilege):
                        with conn.transaction():
                            conn.execute(f"set local role {role}")
                            conn.execute(
                                "select set_config('request.jwt.claims', %s, true)",
                                (f'{{"sub":"{uid}","role":"{role}"}}',),
                            )
                            conn.execute(statement)
        policies = conn.execute(
            "select tablename, array_agg(cmd order by cmd) from pg_policies"
            " where schemaname='public' and tablename=any(%s) group by tablename",
            (list(NEW_TABLES),),
        ).fetchall()
        assert {t: sorted(c) for t, c in policies} == {
            t: ["DELETE", "INSERT", "SELECT", "UPDATE"] for t in NEW_TABLES
        }
        rls = conn.execute(
            "select relname from pg_class where relname=any(%s) and relrowsecurity",
            (list(NEW_TABLES),),
        ).fetchall()
        assert {r[0] for r in rls} == set(NEW_TABLES)


def test_null_auth_uid_owns_nothing_and_is_never_the_founder(lane):
    """Priya (b): a null auth.uid(), as under service_role, is never an owner.

    Rows whose owner went null (sender deleted, group-link redemptions that
    have no sender) must stay invisible to a session without a JWT subject,
    and a missing caller id must never pass the store's owner or founder
    checks, even when no founder is configured.
    """
    owner, gone, joiner = lane.users[1:4]
    lane.beta(owner)
    lane.beta(gone)
    link = lane.group_link(3, label="Null owner")
    lane.store.redeem(user_id=joiner, token=None, code=link.code)
    with lane.pool.connection() as conn:
        conn.execute("delete from auth.users where id=%s", (gone,))
        orphaned = conn.execute(
            "select (select count(*) from public.beta_invitations where created_by is null"
            " and id=any(%s::uuid[])),"
            " (select count(*) from public.invite_referrals where sender_user_id is null"
            " and beta_invitation_id=%s)",
            (list(lane.invitation_ids), link.id),
        ).fetchone()
        assert orphaned[0] >= 1 and orphaned[1] == 1

        def visible(role: str, claims: str) -> dict[str, int]:
            seen: dict[str, int] = {}
            try:
                with conn.transaction():
                    # Temporarily open SELECT so only RLS decides what is visible.
                    for table in NEW_TABLES:
                        conn.execute(
                            f"grant select on public.{table} to anon, authenticated"  # noqa: S608
                        )
                    conn.execute(f"set local role {role}")
                    conn.execute(
                        "select set_config('request.jwt.claims', %s, true)", (claims,)
                    )
                    conn.execute("select set_config('request.jwt.claim.sub', '', true)")
                    if claims == "" or '"sub"' not in claims:
                        assert conn.execute("select auth.uid()").fetchone()[0] is None
                    for table in NEW_TABLES:
                        seen[table] = conn.execute(
                            f"select count(*) from public.{table}"  # noqa: S608
                        ).fetchone()[0]
                    raise psycopg.Rollback()
            finally:
                conn.execute("reset role")
            return seen

        for role in ("anon", "authenticated"):
            for claims in (
                "",
                "{}",
                '{"role":"service_role"}',
                '{"role":"authenticated"}',
            ):
                assert visible(role, claims) == dict.fromkeys(NEW_TABLES, 0), (
                    role,
                    claims,
                )
        # The same temporary grant does show the owner their own rows, so the
        # zero above is RLS refusing a null subject, not a missing privilege.
        mine = visible("authenticated", f'{{"sub":"{owner}","role":"authenticated"}}')
        assert mine["beta_invitations"] == 1 and mine["invite_sender_refs"] == 0

    # The store takes the caller only from the verified JWT subject.
    for missing in (None, "", "   ", "not-a-uuid"):
        for call in (
            lambda m: lane.store.access(user_id=m),
            lambda m: lane.store.sent(user_id=m),
            lambda m: lane.store.create_beta(
                user_id=m, key=str(uuid4()), request_hash="{}"
            ),
            lambda m: lane.store.redeem(user_id=m, token=None, code=link.code),
            lambda m: lane.store.revoke(user_id=m, invitation_id=link.id),
            lambda m: lane.store.network(user_id=m),
            lambda m: lane.store.group_links(user_id=m),
        ):
            with pytest.raises(VerifiedUserRequired):
                call(missing)
    unset = PostgresInviteStore(
        lane.pool, settings=InviteSettings(founder_user_id=None), clock=lane.clock
    )
    assert not unset.settings.is_founder(None)
    assert not unset.settings.is_founder("")
    assert not lane.settings.is_founder(None)
    with pytest.raises(FounderRequired):
        unset.network(user_id=owner)
    assert lane.row(
        "select use_count from public.beta_invitations where id=%s", link.id
    ) == (1,)
