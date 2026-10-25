from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID

import psycopg
import pytest
from argus.domain.business.access import PostgresAccessStore
from argus.domain.business.authority import ActionError, authorize
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.memberships import MembershipError
from argus.domain.business.roles import ROLE_PERMISSIONS, BusinessRole
from argus.domain.business.spaces import PostgresSpaceStore
from psycopg_pool import ConnectionPool

from tests import test_business_actions_postgres as action_fixtures
from tests import test_financial_accounts_postgres as shared

actions = action_fixtures.actions

users = shared.users
pytestmark = pytest.mark.skipif(not shared.DSN, reason="Disposable database required")


@pytest.fixture
def pool():
    with ConnectionPool(shared.DSN, min_size=0, max_size=4) as pool:
        yield pool


def invite_member(pool, users, role):
    spaces, access = PostgresSpaceStore(pool), PostgresAccessStore(pool)
    space, _ = spaces.create(users["owner"], "Colmado")
    with psycopg.connect(shared.DSN) as db:
        email = db.execute(
            "update auth.users set email_confirmed_at=now() where id=%s returning email",
            (users["other"],),
        ).fetchone()[0]
    _, listing = access.give(space.id, users["owner"], email, role)
    invite = listing.invites[0]
    return access, space, invite


@pytest.mark.parametrize("role", list(BusinessRole))
def test_explicit_acceptance_enforces_selected_role(pool, users, role):
    access, space, invite = invite_member(pool, users, role)
    assert invite.requested_role == role
    assert access.spaces_for(users["other"]) == ()
    assert access.accept_invites(users["other"]) == 0
    grant = access.accept_invite(users["other"], space.id, invite.id)
    assert access.accept_invite(users["other"], space.id, invite.id) == grant
    with psycopg.connect(shared.DSN) as db:
        actor = TrustedActor(
            actor_id=UUID(users["other"]), actor_kind="member", space_id=UUID(space.id)
        )
        current = authorize(db, actor)
        assert current.permissions == ROLE_PERMISSIONS[role]
        assert current.context.owner_id == users["owner"]
        assert current.context.is_current_owner == (role == BusinessRole.OWNER)
        agent = authorize(db, actor.model_copy(update={"actor_kind": "owner_via_agent"}))
        assert "approve" not in agent.permissions


def test_coowner_can_already_own_another_business(pool, users):
    own, _ = PostgresSpaceStore(pool).create(users["other"], "Otro")
    access, shared_space, invite = invite_member(pool, users, BusinessRole.OWNER)
    access.accept_invite(users["other"], shared_space.id, invite.id)
    assert {g.space_id for g in access.spaces_for(users["other"])} == {
        own.id,
        shared_space.id,
    }
    assert PostgresSpaceStore(pool).open_space(users["other"]).id == own.id


def test_revoke_is_immediate_and_accept_replay_cannot_restore(pool, users):
    access, space, invite = invite_member(pool, users, BusinessRole.OWNER)
    grant = access.accept_invite(users["other"], space.id, invite.id)
    assert access.revoke_grant(space.id, users["owner"], grant) == "revoked"
    assert access.capabilities(space.id, users["other"]) == ()
    with pytest.raises(MembershipError, match="business_grant_not_live"):
        access.accept_invite(users["other"], space.id, invite.id)
    assert not access.ensure_owner_grant(space.id, users["other"])


def test_admin_cannot_assign_owner_or_modify_an_owner(pool, users):
    access, space, invite = invite_member(pool, users, BusinessRole.ADMIN)
    access.accept_invite(users["other"], space.id, invite.id)
    with pytest.raises(MembershipError):
        access.give(space.id, users["other"], "third@example.test", BusinessRole.OWNER)
    owner_grant = next(
        g.id for g in access.list(space.id, users["owner"]).grants if g.owner
    )
    with pytest.raises(MembershipError):
        access.revoke_grant(space.id, users["other"], owner_grant)


@pytest.mark.parametrize(
    "mutation", ["revoked_at=clock_timestamp()", "business_role='viewer'"]
)
@pytest.mark.parametrize("isolation", ["read committed", "repeatable read"])
def test_database_concurrent_owner_removal_never_leaves_zero(
    pool, users, isolation, mutation
):
    access, space, invite = invite_member(pool, users, BusinessRole.OWNER)
    other = access.accept_invite(users["other"], space.id, invite.id)
    owner = next(
        g.id
        for g in access.list(space.id, users["owner"]).grants
        if g.grantee_id == users["owner"]
    )
    barrier = Barrier(2)

    def remove(grant):
        with psycopg.connect(shared.DSN) as db:
            try:
                db.execute(f"set transaction isolation level {isolation}")
                db.execute(
                    "select count(*) from public.business_client_grants where space_id=%s",
                    (space.id,),
                ).fetchone()
                barrier.wait(timeout=10)
                db.execute(
                    f"update public.business_client_grants set {mutation} where id=%s",
                    (grant,),
                )
                db.commit()
                return "committed"
            except (
                psycopg.errors.CheckViolation,
                psycopg.errors.SerializationFailure,
                psycopg.errors.DeadlockDetected,
            ):
                db.rollback()
                return "refused"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(remove, [owner, other]))
    assert sorted(results) == ["committed", "refused"]
    with psycopg.connect(shared.DSN) as db:
        assert (
            db.execute(
                "select count(*) from public.business_client_grants where space_id=%s and business_role='owner' and revoked_at is null",
                (space.id,),
            ).fetchone()[0]
            == 1
        )


def test_invite_binds_known_account_and_current_verified_email(pool, users):
    access, space, invite = invite_member(pool, users, BusinessRole.OWNER)
    with pytest.raises(MembershipError):
        access.accept_invite(users["owner"], space.id, invite.id)
    with pytest.raises(MembershipError):
        access.accept_invite(users["other"], str(UUID(int=42)), invite.id)
    with psycopg.connect(shared.DSN) as db:
        original = db.execute(
            "select email from auth.users where id=%s", (users["other"],)
        ).fetchone()[0]
        db.execute(
            "update auth.users set email=%s where id=%s",
            ("changed@example.test", users["other"]),
        )
        db.execute(
            "update auth.users set email=%s,email_confirmed_at=now(),is_anonymous=false where id=%s",
            (original, users["guest"]),
        )
    for person in ("other", "guest"):
        assert access.invitations_for(users[person]) == ()
        with pytest.raises(MembershipError):
            access.accept_invite(users[person], space.id, invite.id)


def test_unconfirmed_recipient_cannot_accept(pool, users):
    access, space, invite = invite_member(pool, users, BusinessRole.EDITOR)
    with psycopg.connect(shared.DSN) as db:
        db.execute(
            "update auth.users set email_confirmed_at=null where id=%s", (users["other"],)
        )
    with pytest.raises(MembershipError, match="business_invite_recipient_required"):
        access.accept_invite(users["other"], space.id, invite.id)
    assert access.spaces_for(users["other"]) == ()


def test_canceled_command_replay_and_expired_generation_are_terminal(pool, users):
    spaces, access = PostgresSpaceStore(pool), PostgresAccessStore(pool)
    space, _ = spaces.create(users["owner"], "Colmado")
    with psycopg.connect(shared.DSN) as db:
        email = db.execute(
            "update auth.users set email_confirmed_at=now() where id=%s returning email",
            (users["other"],),
        ).fetchone()[0]
    _, listing = access.give(
        space.id, users["owner"], email, BusinessRole.VIEWER, "one-person"
    )
    original = listing.invites[0]
    access.revoke_invite(space.id, users["owner"], original.id)
    assert (
        access.give(space.id, users["owner"], email, BusinessRole.VIEWER, "one-person")[0]
        is False
    )
    assert (
        access.invitation_command(space.id, users["owner"], "one-person")["state"]
        == "revoked"
    )
    assert access.resend(space.id, users["owner"], original.id) is None
    _, listing = access.give(
        space.id, users["owner"], email, BusinessRole.VIEWER, "explicit-new"
    )
    expired = listing.invites[0]
    with psycopg.connect(shared.DSN) as db:
        db.execute(
            "update public.business_access_invites set created_at=clock_timestamp()-interval '8 days',expires_at=clock_timestamp()-interval '1 day' where id=%s",
            (expired.id,),
        )
    fresh = access.resend(space.id, users["owner"], expired.id).invites[0]
    assert fresh.id != expired.id
    with pytest.raises(MembershipError):
        access.accept_invite(users["other"], space.id, expired.id)
    access.accept_invite(users["other"], space.id, fresh.id)


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_membership_invitation_and_command_tables_are_not_client_accessible(
    pool, users, role
):
    with psycopg.connect(shared.DSN) as db:
        for table in (
            "public.business_client_grants",
            "public.business_access_invites",
            "argus_private.business_invitation_commands",
        ):
            for operation in ("select * from", "delete from"):
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    with db.transaction():
                        db.execute(f"set local role {role}")
                        db.execute(f"{operation} {table}")


def test_demoted_default_owner_cannot_heal_or_approve(pool, users):
    access, space, invitation = invite_member(pool, users, BusinessRole.OWNER)
    other = access.accept_invite(users["other"], space.id, invitation.id)
    owner = next(
        g.id
        for g in access.list(space.id, users["owner"]).grants
        if g.grantee_id == users["owner"]
    )
    access.change_role(space.id, users["other"], owner, BusinessRole.VIEWER)
    assert not access.ensure_owner_grant(space.id, users["owner"])
    assert access.granted(users["owner"], owner).business_role == BusinessRole.VIEWER
    with psycopg.connect(shared.DSN) as db:
        actor = TrustedActor(
            actor_id=UUID(users["owner"]), actor_kind="member", space_id=UUID(space.id)
        )
        with pytest.raises(ActionError):
            authorize(db, actor).require("approve")
        assert db.execute(
            "select created_by::text,current_owner_id::text from public.spaces where id=%s",
            (space.id,),
        ).fetchone() == (users["owner"], users["owner"])
    with pytest.raises(MembershipError):
        access.revoke_grant(space.id, users["owner"], other)


def test_owner_membership_cannot_expire(pool, users):
    access, space, invitation = invite_member(pool, users, BusinessRole.OWNER)
    grant = access.accept_invite(users["other"], space.id, invitation.id)
    with psycopg.connect(shared.DSN) as db:
        with pytest.raises(
            psycopg.errors.CheckViolation, match="business_owner_cannot_expire"
        ):
            db.execute(
                "update public.business_client_grants set expires_at=clock_timestamp()+interval '1 second' where id=%s",
                (grant,),
            )


def test_actor_is_rechecked_after_waiting_for_business_lock(pool, users, monkeypatch):
    from threading import Event

    from argus.domain.business import access as access_module

    access, space, invitation = invite_member(pool, users, BusinessRole.OWNER)
    other = access.accept_invite(users["other"], space.id, invitation.id)
    owner = next(
        g.id
        for g in access.list(space.id, users["owner"]).grants
        if g.grantee_id == users["owner"]
    )
    waiting = Event()
    original_lock = access_module._lock

    def observe_lock(connection, space_id):
        waiting.set()
        original_lock(connection, space_id)

    monkeypatch.setattr(access_module, "_lock", observe_lock)
    with ThreadPoolExecutor(max_workers=1) as executor:
        with psycopg.connect(shared.DSN) as db:
            db.execute("select id from public.spaces where id=%s for update", (space.id,))
            future = executor.submit(access.revoke_grant, space.id, users["other"], owner)
            assert waiting.wait(timeout=5)
            db.execute(
                "update public.business_client_grants set business_role='viewer' where id=%s",
                (other,),
            )
        with pytest.raises(MembershipError, match="business_permission_denied"):
            future.result(timeout=5)
    assert access.granted(users["owner"], owner).business_role == BusinessRole.OWNER


def test_owner_promotion_preserves_membership_until_recipient_accepts(pool, users):
    access, space, invitation = invite_member(pool, users, BusinessRole.EDITOR)
    grant = access.accept_invite(users["other"], space.id, invitation.id)
    listing = access.change_role(space.id, users["owner"], grant, BusinessRole.OWNER)
    upgrade = listing.invites[0]
    assert upgrade.requested_role == BusinessRole.OWNER
    assert access.granted(users["other"], grant).business_role == BusinessRole.EDITOR
    assert access.accept_invite(users["other"], space.id, upgrade.id) == grant
    assert access.granted(users["other"], grant).business_role == BusinessRole.OWNER


def test_stale_owner_promotion_cannot_restore_removed_membership(pool, users):
    access, space, invitation = invite_member(pool, users, BusinessRole.EDITOR)
    grant = access.accept_invite(users["other"], space.id, invitation.id)
    upgrade = access.change_role(
        space.id, users["owner"], grant, BusinessRole.OWNER
    ).invites[0]
    access.revoke_grant(space.id, users["owner"], grant)
    with pytest.raises(MembershipError, match="business_invite_membership_changed"):
        access.accept_invite(users["other"], space.id, upgrade.id)
    assert access.spaces_for(users["other"]) == ()


def test_pending_inviter_losing_owner_cannot_add_owner(pool, users):
    access, space, invitation = invite_member(pool, users, BusinessRole.OWNER)
    other = access.accept_invite(users["other"], space.id, invitation.id)
    with psycopg.connect(shared.DSN) as db:
        db.execute(
            "update auth.users set email='third@example.test',is_anonymous=false,email_confirmed_at=now() where id=%s",
            (users["guest"],),
        )
    _, listing = access.give(
        space.id, users["other"], "third@example.test", BusinessRole.OWNER
    )
    pending = listing.invites[0]
    access.change_role(space.id, users["owner"], other, BusinessRole.EDITOR)
    with pytest.raises(MembershipError, match="business_permission_denied"):
        access.accept_invite(users["guest"], space.id, pending.id)


def test_coowner_closes_and_reopens_selected_business_without_changing_own(
    pool, users, monkeypatch
):
    from argus.domain.business.lifecycle import PostgresBusinessLifecycle

    monkeypatch.setattr(
        "argus.domain.business.close_mail.deliver_close_mail", lambda *a: None
    )
    own, _ = PostgresSpaceStore(pool).create(users["other"], "Otro")
    access, space, invitation = invite_member(pool, users, BusinessRole.OWNER)
    access.accept_invite(users["other"], space.id, invitation.id)
    lifecycle = PostgresBusinessLifecycle(pool)
    assert (
        lifecycle.close(
            owner_id=users["other"],
            space_id=space.id,
            confirmation=space.name,
            idempotency_key="shared-close",
        ).closed_at
        is not None
    )
    assert PostgresSpaceStore(pool).open_space(users["other"]).id == own.id
    assert (
        lifecycle.reopen(
            owner_id=users["other"], space_id=space.id, idempotency_key="shared-reopen"
        ).closed_at
        is None
    )
    assert PostgresSpaceStore(pool).open_space(users["other"]).id == own.id
    with psycopg.connect(shared.DSN) as db:
        assert db.execute(
            "select created_by::text,current_owner_id::text from public.spaces where id=%s",
            (space.id,),
        ).fetchone() == (users["owner"], users["owner"])


def test_delivery_claim_survives_crash_and_does_not_send_again(pool, users):
    access, space, invite = invite_member(pool, users, BusinessRole.VIEWER)
    calls = []

    class SyntheticCrash(BaseException):
        pass

    def crash():
        calls.append(invite.id)
        raise SyntheticCrash()

    with pytest.raises(SyntheticCrash):
        access.deliver_invitation(space.id, users["owner"], invite.id, crash)
    assert (
        access.deliver_invitation(space.id, users["owner"], invite.id, crash)
        == "uncertain"
    )
    assert calls == [invite.id]


def test_concurrent_delivery_claims_converge_and_failed_send_retries(pool, users):
    access, space, invite = invite_member(pool, users, BusinessRole.VIEWER)
    calls = []
    assert (
        access.deliver_invitation(space.id, users["owner"], invite.id, lambda: "failed")
        == "failed"
    )

    def send():
        calls.append(invite.id)
        return "accepted"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: access.deliver_invitation(
                    space.id, users["owner"], invite.id, send
                ),
                range(2),
            )
        )
    assert set(results) <= {"accepted", "uncertain"}
    assert "accepted" in results
    assert calls == [invite.id]


def test_legacy_zero_history_backfill_never_heals_revoked_or_demoted_owners(pool, users):
    from pathlib import Path

    from tests.test_business_spaces_migration_postgres import space as legacy_space

    sql = Path(
        "supabase/migrations/20261025182039_business_membership_roles.sql"
    ).read_text()
    backfill = sql[
        sql.index(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,business_role,capabilities)"
        ) : sql.index(
            "alter table public.business_client_grants add constraint business_membership_role"
        )
    ]
    with psycopg.connect(shared.DSN) as db:
        business = legacy_space(db, users["owner"])
        db.execute(backfill)
        assert db.execute(
            "select business_role from public.business_client_grants where space_id=%s",
            (business,),
        ).fetchall() == [("owner",)]
        assert db.execute(
            "select count(*) from public.business_access_invites where space_id=%s",
            (business,),
        ).fetchone() == (0,)
        assert db.execute(
            "select count(*) from public.business_receipt_reading_consents where space_id=%s",
            (business,),
        ).fetchone() == (0,)
        db.commit()
        for mutation in ("revoked_at=clock_timestamp()", "business_role='viewer'"):
            with pytest.raises(
                psycopg.errors.CheckViolation,
                match="business_owner_history_requires_review",
            ):
                with db.transaction():
                    db.execute(
                        f"update public.business_client_grants set {mutation} where space_id=%s",
                        (business,),
                    )
                    db.execute(backfill)


@pytest.mark.owner_acts
def test_both_owners_approve_shared_records_without_moving_custody(actions, users):
    from argus.domain.business.contracts.actions import ApproveExpense

    from tests.test_business_actions_postgres import ready

    service, first, _ = actions
    pool = service.authority.pool
    own, _ = PostgresSpaceStore(pool).create(users["other"], "Otro")
    access = PostgresAccessStore(pool)
    with pool.connection() as db:
        email = db.execute(
            "update auth.users set email_confirmed_at=now() where id=%s returning email",
            (users["other"],),
        ).fetchone()[0]
    _, listing = access.give(
        str(first.actor.space_id), users["owner"], email, BusinessRole.OWNER
    )
    invitation = listing.invites[0]
    accepted = access.accept_invite(
        users["other"], str(first.actor.space_id), invitation.id
    )
    second = service.resolve_actor(
        TrustedActor(
            actor_id=UUID(users["other"]),
            actor_kind="member",
            space_id=first.actor.space_id,
        )
    )
    for actor in (first, second):
        draft = ready(service, first)
        result = service.approve(
            actor,
            draft,
            ApproveExpense(version=1, action="record_expense"),
            str(actor.actor.actor_id),
        )
        assert result.outcome == "applied", result
        with pool.connection() as db:
            assert db.execute(
                "select user_id::text,owner_space_id from public.financial_import_events where id=%s",
                (draft,),
            ).fetchone() == (users["owner"], first.actor.space_id)
    assert PostgresSpaceStore(pool).open_space(users["other"]).id == own.id
    access.revoke_grant(str(first.actor.space_id), users["owner"], accepted)
    replay = service.approve(
        second,
        draft,
        ApproveExpense(version=1, action="record_expense"),
        str(second.actor.actor_id),
    )
    assert replay.outcome != "applied"


@pytest.mark.parametrize(
    "current,requested,pending",
    [
        (BusinessRole.VIEWER, BusinessRole.ADMIN, True),
        (BusinessRole.EDITOR, BusinessRole.ADMIN, True),
        (BusinessRole.ADMIN, BusinessRole.OWNER, True),
        (BusinessRole.OWNER, BusinessRole.ADMIN, False),
        (BusinessRole.VIEWER, BusinessRole.EDITOR, False),
    ],
)
def test_promotion_and_demotion_acceptance_boundary(
    pool, users, current, requested, pending
):
    access, space, invitation = invite_member(pool, users, current)
    grant = access.accept_invite(users["other"], space.id, invitation.id)
    listing = access.change_role(space.id, users["owner"], grant, requested)
    assert access.granted(users["other"], grant).business_role == (
        current if pending else requested
    )
    if pending:
        assert listing.invites[0].requested_role == requested
        assert (
            access.accept_invite(users["other"], space.id, listing.invites[0].id) == grant
        )
        assert access.granted(users["other"], grant).business_role == requested
    else:
        assert listing.invites == ()


def test_pending_admin_upgrade_cannot_restore_membership_after_immediate_role_change(
    pool, users
):
    access, space, invitation = invite_member(pool, users, BusinessRole.VIEWER)
    grant = access.accept_invite(users["other"], space.id, invitation.id)
    upgrade = access.change_role(
        space.id, users["owner"], grant, BusinessRole.ADMIN
    ).invites[0]
    access.change_role(space.id, users["owner"], grant, BusinessRole.EDITOR)
    with pytest.raises(MembershipError, match="business_invite_membership_changed"):
        access.accept_invite(users["other"], space.id, upgrade.id)
    assert access.granted(users["other"], grant).business_role == BusinessRole.EDITOR


def test_coowner_consent_has_actual_actor_and_is_invalidated_by_role_loss(pool, users):
    from tests.business_reading_support import reading_setting

    access, space, invitation = invite_member(pool, users, BusinessRole.OWNER)
    setting = reading_setting(pool)
    assert not setting.status(space.id, users["owner"])["enabled"]
    grant = access.accept_invite(users["other"], space.id, invitation.id)
    assert not setting.status(space.id, users["owner"])["enabled"]
    shown = setting.status(space.id, users["owner"])
    arguments = dict(
        actor_id=users["other"],
        enabled=True,
        version=1,
        disclosure_token=shown["disclosure_token"],
        idempotency_key="explicit-coowner-consent",
    )
    assert setting.set(space.id, users["owner"], **arguments)["enabled"]
    with pool.connection() as db:
        before = db.execute(
            "select id::text,owner_id::text,consented_at,revoked_at from public.business_receipt_reading_consents where space_id=%s",
            (space.id,),
        ).fetchone()
        assert before[1] == users["other"] and before[3] is None
    access.change_role(space.id, users["owner"], grant, BusinessRole.EDITOR)
    assert not setting.status(space.id, users["owner"])["enabled"]
    with pytest.raises(ActionError, match="business_permission_denied"):
        setting.set(space.id, users["owner"], **arguments)
    with pool.connection() as db:
        after = db.execute(
            "select id::text,owner_id::text,consented_at,revoked_at from public.business_receipt_reading_consents where space_id=%s",
            (space.id,),
        ).fetchone()
        assert after[:3] == before[:3] and after[3] is not None


def test_pending_invitation_issuer_and_recipient_cannot_be_rebound(pool, users):
    access, space, invitation = invite_member(pool, users, BusinessRole.OWNER)
    with psycopg.connect(shared.DSN) as db:
        for column, value in [("issuer_id", users["other"]), ("recipient_id", None)]:
            with pytest.raises(
                psycopg.errors.CheckViolation, match="business_invite_recipient_immutable"
            ):
                with db.transaction():
                    db.execute(
                        f"update public.business_access_invites set {column}=%s where id=%s",
                        (value, invitation.id),
                    )
        with pytest.raises(
            psycopg.errors.CheckViolation,
            match="business_custody_identity_detachment_required",
        ):
            with db.transaction():
                db.execute("delete from auth.users where id=%s", (users["other"],))


def test_each_accepted_upgrade_keeps_a_distinct_audit_receipt(pool, users):
    access, space, invitation = invite_member(pool, users, BusinessRole.EDITOR)
    grant = access.accept_invite(users["other"], space.id, invitation.id)
    first = access.change_role(
        space.id, users["owner"], grant, BusinessRole.ADMIN
    ).invites[0]
    access.accept_invite(users["other"], space.id, first.id)
    second = access.change_role(
        space.id, users["owner"], grant, BusinessRole.OWNER
    ).invites[0]
    access.accept_invite(users["other"], space.id, second.id)
    access.accept_invite(users["other"], space.id, second.id)
    with pool.connection() as db:
        rows = db.execute(
            "select command->>'invite_id' from public.business_action_receipts where space_id=%s and command->>'action'='accept_invite'",
            (space.id,),
        ).fetchall()
        assert {row[0] for row in rows} == {invitation.id, first.id, second.id}
        assert len(rows) == 3


def test_expired_upgrade_resend_refuses_changed_membership(pool, users):
    access, space, invitation = invite_member(pool, users, BusinessRole.VIEWER)
    grant = access.accept_invite(users["other"], space.id, invitation.id)
    upgrade = access.change_role(
        space.id, users["owner"], grant, BusinessRole.ADMIN
    ).invites[0]
    access.change_role(space.id, users["owner"], grant, BusinessRole.EDITOR)
    with pool.connection() as db:
        db.execute(
            "update public.business_access_invites set created_at=clock_timestamp()-interval '8 days',expires_at=clock_timestamp()-interval '1 day' where id=%s",
            (upgrade.id,),
        )
    with pytest.raises(MembershipError, match="business_invite_membership_changed"):
        access.resend(space.id, users["owner"], upgrade.id)
    assert access.granted(users["other"], grant).business_role == BusinessRole.EDITOR


@pytest.mark.parametrize("database_role", ["postgres", "service_role"])
def test_terminal_invitation_rewrite_requires_real_custody_claim(
    pool, users, database_role
):
    access, space, invitation = invite_member(pool, users, BusinessRole.EDITOR)
    access.accept_invite(users["other"], space.id, invitation.id)
    with psycopg.connect(shared.DSN) as db, db.transaction(force_rollback=True):
        db.execute(
            "select set_config('argus.business_custody_space',%s,true)", (space.id,)
        )
        db.execute(
            "select set_config('argus.business_departure_actor',%s,true)",
            (users["owner"],),
        )
        db.execute(
            "insert into argus_private.business_custody_changes(space_id,table_name,old_row,new_row)"
            " select space_id,'business_access_invites',to_jsonb(i),to_jsonb(i)||jsonb_build_object('historical_issuer_id',%s::text)"
            " from public.business_access_invites i where id=%s",
            (users["other"], invitation.id),
        )
        db.execute("set local role " + database_role)
        for column in ("historical_issuer_id", "issuer_id", "recipient_id"):
            with pytest.raises((psycopg.errors.CheckViolation, psycopg.errors.InsufficientPrivilege)), db.transaction():
                db.execute(
                    f"update public.business_access_invites set {column}=%s where id=%s",
                    (
                        users["owner"] if column == "recipient_id" else users["other"],
                        invitation.id,
                    ),
                )
        assert db.execute(
            "select historical_issuer_id,accepted_at is not null,requested_role from public.business_access_invites where id=%s",
            (invitation.id,),
        ).fetchone() == (None, True, "editor")


@pytest.mark.parametrize("mutation", ["delete", "demote", "revoke"])
@pytest.mark.parametrize("consenting_member", ["owner", "other"])
def test_membership_loss_invalidates_only_that_owners_original_consents(
    pool, users, mutation, consenting_member
):
    from psycopg.types.json import Jsonb

    from tests.business_reading_support import reading_setting

    access, space, invitation = invite_member(pool, users, BusinessRole.OWNER)
    removed_grant = access.accept_invite(users["other"], space.id, invitation.id)
    actor = users[consenting_member]
    actor_grant = next(
        g for g in access.list(space.id, actor).grants if g.grantee_id == actor
    )
    setting = reading_setting(pool)
    shown = setting.status(space.id, users["owner"])
    setting.set(
        space.id,
        users["owner"],
        actor_id=actor,
        enabled=True,
        version=1,
        disclosure_token=shown["disclosure_token"],
        idempotency_key="explicit-owner-reading",
    )
    with pool.connection() as db:
        db.execute(
            "insert into public.business_ai_consents(space_id,owner_id,consenting_actor_id,grant_id,issuer_id,scope_version,purpose,disclosure,route,route_hash,idempotency_key,input_hash) values(%s,%s,%s,%s,%s,1,'business_ai_receipt_reading','Synthetic disclosure',%s,%s,'explicit-owner-ai',%s)",
            (
                space.id,
                actor,
                actor,
                actor_grant.id,
                users["owner"],
                Jsonb({"provider": "fake"}),
                "1" * 64,
                "2" * 64,
            ),
        )

    def consent_rows():
        with pool.connection() as db:
            return tuple(
                db.execute(query, (space.id,)).fetchone()[0]
                for query in (
                    "select to_jsonb(c) from public.business_receipt_reading_consents c where space_id=%s",
                    "select to_jsonb(c) from public.business_ai_consents c where space_id=%s",
                )
            )

    before = consent_rows()
    assert all(row["owner_id"] == actor and row["revoked_at"] is None for row in before)
    if mutation == "delete":
        with pool.connection() as db:
            db.execute(
                "delete from public.business_client_grants where id=%s", (removed_grant,)
            )
    elif mutation == "demote":
        access.change_role(space.id, users["owner"], removed_grant, BusinessRole.EDITOR)
    else:
        access.revoke_grant(space.id, users["owner"], removed_grant)
    should_remain_enabled = consenting_member == "owner"
    assert setting.status(space.id, users["owner"])["enabled"] == should_remain_enabled
    after = consent_rows()
    for original, saved in zip(before, after, strict=True):
        assert (saved["revoked_at"] is None) == should_remain_enabled
        assert {k: v for k, v in saved.items() if k != "revoked_at"} == {
            k: v for k, v in original.items() if k != "revoked_at"
        }
    assert "approve" in access.capabilities(space.id, users["owner"])
    assert "approve" not in access.capabilities(space.id, users["other"])
