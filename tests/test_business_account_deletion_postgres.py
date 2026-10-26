"""Actual account-deletion command, synthetic PostgreSQL and fake external adapters."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from argus.api.account_deletion_runtime import household_repository
from argus.domain.account_deletion.service import (
    AccountDeletionRejected,
    AccountDeletionService,
    subject_hash,
)
from argus.domain.business.custody_graph import retained_dependencies
from argus.domain.business.lifecycle import PostgresBusinessLifecycle
from argus.domain.business.transfer import PostgresBusinessTransfer
from argus.observability.analytics_deletion import RecordingAnalyticsDeletion

from tests import test_business_custody_graph_postgres as graph

users = graph.users
actions = graph.actions
prepared = graph.prepared
custody = graph.custody
pytestmark = [graph.pytestmark, pytest.mark.owner_acts]


class Auth(graph.FakeAuth):
    def lock_user(self, user):
        pass


def command(w, *, auth=None, images=None, apple=None):
    return AccountDeletionService(
        households=household_repository(w["pool"]),
        auth_admin=auth if auth is not None else Auth(),
        revoker=None,
        apple=apple,
        analytics=RecordingAnalyticsDeletion(),
        allow_fake_analytics=True,
        source_objects=w["objects"],
        profile_images=images,
        clock=lambda: datetime.now(timezone.utc),
    )


def close_owned_business(pool, user_id: str):
    """Give a synthetic owner its grant and explicitly close its open Business."""
    from argus.domain.business.access import ensure_owner_grant
    from argus.domain.business.spaces import PostgresSpaceStore

    with pool.connection() as db:
        space_id = db.execute(
            "select id::text from public.spaces where current_owner_id=%s and kind='business' and closed_at is null",
            (user_id,),
        ).fetchone()[0]
        ensure_owner_grant(db, space_id, user_id)
    space = PostgresSpaceStore(pool).open_space(user_id)
    return PostgresBusinessLifecycle(pool).close(
        owner_id=user_id,
        space_id=space.id,
        confirmation=space.name,
        idempotency_key="erasure-fixture-close",
    )


def erase_open_owner(pool, user_id: str):
    """Explicitly close the fixture's open Business, then erase the person."""
    close_owned_business(pool, user_id)
    return command({"pool": pool, "objects": graph.FakeObjects()}).delete_account(
        user_id=user_id
    )


def release_custodian(space_id: str) -> None:
    """Drop a handed-off Business and its placeholder after an erasure test."""

    import psycopg

    with psycopg.connect(graph.DSN) as db:
        custodian = db.execute(
            "select created_by::text from public.spaces where id=%s", (space_id,)
        ).fetchone()
        db.execute(
            "delete from argus_private.business_purge_runs where space_id=%s",
            (space_id,),
        )
        for table in (
            "business_custody_changes",
            "business_custody_objects",
            "business_custody_moves",
            "business_departure_aliases",
        ):
            db.execute(
                f"delete from argus_private.{table} where space_id=%s", (space_id,)
            )
        db.execute(
            "delete from argus_private.business_custody_reservations where space_id=%s",
            (space_id,),
        )
        db.execute("delete from public.spaces where id=%s", (space_id,))
        if custodian is not None:
            db.execute("delete from auth.users where id=%s", (custodian[0],))


def close(w):
    return PostgresBusinessLifecycle(w["pool"]).close(
        owner_id=w["old"],
        space_id=w["space"],
        confirmation="Colmado",
        idempotency_key="close-account-deletion",
    )


def transfer(w, *, accept=True):
    with w["pool"].connection() as db:
        db.execute(
            "update auth.users set email_confirmed_at=now() where id=%s",
            (w["users"]["other"],),
        )
        target = db.execute(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities) values(%s,%s,%s,array['read','prepare']) returning id::text",
            (w["space"], w["users"]["other"], w["old"]),
        ).fetchone()[0]
    service = PostgresBusinessTransfer(w["pool"])
    pending = service.request(
        owner_id=w["old"],
        space_id=w["space"],
        target_grant_id=target,
        confirmation="Colmado",
        idempotency_key="transfer-account-deletion",
    )
    if accept:
        service.accept(actor_id=w["users"]["other"], transfer_id=pending.id)


@pytest.mark.parametrize("transferred", [False, True])
def test_claimed_account_deletion_preserves_graph_and_erases_real_identity(
    custody, transferred
):
    w = custody
    if transferred:
        transfer(w)
        deadline = None
    else:
        deadline = close(w).closed_at
    with w["pool"].connection() as db:
        source = db.execute(
            "select source_sha256,rebuilt_sha256,batch from public.financial_document_extractions where connection_id=%s",
            (w["cid"],),
        ).fetchone()
        revisions = db.execute(
            "select draft_id,version,before_facts,after_facts,source_ids from public.business_draft_revisions where space_id=%s order by draft_id,version",
            (w["space"],),
        ).fetchall()
    outcome = command(w).delete_account(user_id=w["old"])
    assert outcome.status == "done"
    assert not Auth().user_exists(w["old"])
    with w["pool"].connection() as db:
        assert retained_dependencies(db, w["old"]) == ()
        saved = db.execute(
            "select created_by::text,current_owner_id::text,closed_at from public.spaces where id=%s",
            (w["space"],),
        ).fetchone()
        assert saved[0] != w["old"] and saved[2] == deadline
        assert saved[1] == (w["users"]["other"] if transferred else None)
        assert (
            db.execute(
                "select source_sha256,rebuilt_sha256,batch from public.financial_document_extractions where connection_id=%s",
                (w["cid"],),
            ).fetchone()
            == source
        )
        assert (
            db.execute(
                "select draft_id,version,before_facts,after_facts,source_ids from public.business_draft_revisions where space_id=%s order by draft_id,version",
                (w["space"],),
            ).fetchall()
            == revisions
        )
        assert db.execute(
            "select departing_user_id,claim_id,identity_cleaned_at from argus_private.business_custody_moves where space_id=%s",
            (w["space"],),
        ).fetchone()[:2] == (None, None)
        assert (
            db.execute(
                "select count(*) from argus_private.business_custody_objects where space_id=%s and source_path is not null",
                (w["space"],),
            ).fetchone()[0]
            == 0
        )
        assert db.execute(
            "select user_id,subject_hash,analytics_distinct_id,status from argus_private.account_deletion_runs where id=%s",
            (outcome.run_id,),
        ).fetchone() == (None, None, None, "done")
        for path, digest in db.execute(
            "select destination_path,sha256 from argus_private.business_custody_objects where space_id=%s",
            (w["space"],),
        ):
            from hashlib import sha256

            assert sha256(w["objects"].rows[path]).hexdigest() == digest
    assert not any(w["old"] in path for path in w["objects"].rows)


def test_failed_copy_does_not_erase_or_detach_and_retry_finishes(custody, monkeypatch):
    w = custody
    close(w)
    before = graph._snapshot(w)
    put = w["objects"].put
    monkeypatch.setattr(
        w["objects"],
        "put",
        lambda *args: (_ for _ in ()).throw(RuntimeError("copy unavailable")),
    )
    service = command(w)
    with pytest.raises(RuntimeError, match="copy unavailable"):
        service.delete_account(user_id=w["old"])
    assert graph._snapshot(w) == before
    assert not w["objects"].erased and Auth().user_exists(w["old"])
    monkeypatch.setattr(w["objects"], "put", put)
    assert service.delete_account(user_id=w["old"]).status == "done"


def test_auth_success_without_absence_never_settles_identity_maps(custody):
    w = custody
    close(w)

    class DeferredAuth(Auth):
        def delete_user(self, user):
            pass

    with pytest.raises(RuntimeError, match="auth_not_deleted"):
        command(w, auth=DeferredAuth()).delete_account(user_id=w["old"])
    with w["pool"].connection() as db:
        assert db.execute(
            "select identity_cleaned_at from argus_private.business_custody_moves where space_id=%s",
            (w["space"],),
        ).fetchone() == (None,)
        assert db.execute(
            "select status from argus_private.account_deletion_runs where user_id=%s",
            (w["old"],),
        ).fetchone() == ("data_deleted",)
    assert command(w).delete_account(user_id=w["old"]).status == "done"


def test_new_owner_can_close_then_delete_after_original_custodian_has_left(custody):
    w = custody
    transfer(w)
    assert command(w).delete_account(user_id=w["old"]).status == "done"
    other = w["users"]["other"]
    PostgresBusinessLifecycle(w["pool"]).close(
        owner_id=other,
        space_id=w["space"],
        confirmation="Colmado",
        idempotency_key="second-owner-close",
    )
    assert command(w).delete_account(user_id=other).status == "done"
    with w["pool"].connection() as db:
        assert retained_dependencies(db, other) == ()
        assert db.execute(
            "select current_owner_id from public.spaces where id=%s", (w["space"],)
        ).fetchone() == (None,)
        assert (
            db.execute(
                "select count(*) from argus_private.business_departure_aliases where space_id=%s and identity_cleaned_at is not null",
                (w["space"],),
            ).fetchone()[0]
            == 1
        )


def test_departing_pending_target_removes_personal_mail_without_moving_custody(custody):
    w = custody
    other = w["users"]["other"]
    with w["pool"].connection() as db:
        db.execute("update auth.users set email_confirmed_at=now() where id=%s", (other,))
        grant = db.execute(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities) values(%s,%s,%s,array['read','prepare']) returning id::text",
            (w["space"], other, w["old"]),
        ).fetchone()[0]
    pending = PostgresBusinessTransfer(w["pool"]).request(
        owner_id=w["old"],
        space_id=w["space"],
        target_grant_id=grant,
        confirmation="Colmado",
        idempotency_key="departing-target",
    )
    with w["pool"].connection() as db:
        assert (
            db.execute(
                "select count(*) from public.business_transfer_mail_outbox where transfer_id=%s",
                (pending.id,),
            ).fetchone()[0]
            == 1
        )
    original = dict(w["objects"].rows)
    assert command(w).delete_account(user_id=other).status == "done"
    assert w["objects"].rows == original
    with w["pool"].connection() as db:
        assert retained_dependencies(db, other) == ()
        assert db.execute(
            "select created_by::text,current_owner_id::text,closed_at from public.spaces where id=%s",
            (w["space"],),
        ).fetchone() == (w["old"], w["old"], None)
        assert (
            db.execute(
                "select count(*) from public.business_transfer_mail_outbox where transfer_id=%s",
                (pending.id,),
            ).fetchone()[0]
            == 0
        )
        target, status = db.execute(
            "select target_id::text,status from public.business_ownership_transfers where id=%s",
            (pending.id,),
        ).fetchone()
        assert target != other and status == "cancelled"


def test_departing_member_history_stays_anonymous_and_current_owner_can_read(custody):
    from uuid import UUID

    from argus.domain.business.authority import ActionError, authorize
    from argus.domain.business.contracts.authority import TrustedActor

    from tests import test_business_actions_postgres as actions_fixture

    w = custody
    other = w["users"]["other"]
    from argus.domain.business.access import PostgresAccessStore
    from argus.domain.business.memberships import MembershipError
    from argus.domain.business.roles import BusinessRole

    access = PostgresAccessStore(w["pool"])
    with w["pool"].connection() as db:
        email = db.execute(
            "update auth.users set email_confirmed_at=now() where id=%s returning email",
            (other,),
        ).fetchone()[0]
    _, listing = access.give(w["space"], w["old"], email, BusinessRole.EDITOR)
    original = listing.invites[0]
    grant = access.accept_invite(other, w["space"], original.id)
    upgrade = access.change_role(w["space"], w["old"], grant, BusinessRole.ADMIN).invites[
        0
    ]
    access.accept_invite(other, w["space"], upgrade.id)
    pending = access.change_role(w["space"], w["old"], grant, BusinessRole.OWNER).invites[0]
    actor = TrustedActor(
        actor_id=UUID(other), actor_kind="member", space_id=UUID(w["space"])
    )
    context = w["service"].resolve_actor(actor)
    actions_fixture.create(w["service"], context)
    with w["pool"].connection() as db:
        before = db.execute(
            "select count(*) from public.business_action_receipts where space_id=%s and actor_id=%s",
            (w["space"], other),
        ).fetchone()[0]
    assert before > 0
    assert command(w).delete_account(user_id=other).status == "done"
    with w["pool"].connection() as db:
        invitations = db.execute(
            "select id::text,recipient_id::text,accepted_at is not null,revoked_at is not null,target_grant_id::text from public.business_access_invites where id=any(%s::uuid[]) order by accepted_at nulls last",
            ([original.id, upgrade.id, pending.id],),
        ).fetchall()
        assert len(invitations) == 3
        assert invitations[0][0] == original.id and invitations[0][2] is True
        assert invitations[1][0] == upgrade.id and invitations[1][2] is True
        assert invitations[2][0] == pending.id and invitations[2][3] is True
        assert invitations[1][4] == grant
        assert invitations[0][1] == invitations[1][1] and invitations[0][1] != other
        db.execute(
            "update auth.users set email=%s,email_confirmed_at=now(),is_anonymous=false where id=%s",
            (email, w["users"]["guest"]),
        )
    assert access.invitations_for(w["users"]["guest"]) == ()
    for invitation in (original, upgrade, pending):
        with pytest.raises(MembershipError):
            access.accept_invite(w["users"]["guest"], w["space"], invitation.id)
    with w["pool"].connection() as db:
        assert retained_dependencies(db, other) == ()
        alias = db.execute(
            "select actor_id from argus_private.business_departure_aliases where space_id=%s",
            (w["space"],),
        ).fetchone()[0]
        assert (
            db.execute(
                "select count(*) from public.business_action_receipts where space_id=%s and actor_id=%s",
                (w["space"], alias),
            ).fetchone()[0]
            == before
        )
        assert (
            db.execute(
                "select count(*) from public.business_action_receipts where space_id=%s and actor_id=%s",
                (w["space"], w["old"]),
            ).fetchone()[0]
            > 0
        )
        with pytest.raises(ActionError, match="business_record_not_found"):
            authorize(db, actor)
        authorize(
            db,
            TrustedActor(
                actor_id=UUID(w["old"]), actor_kind="member", space_id=UUID(w["space"])
            ),
        ).require("approve")


def test_every_closed_business_moves_before_shared_old_prefix_is_erased(custody):
    from tests.test_business_spaces_migration_postgres import connection, space

    w = custody
    deadline = close(w).closed_at
    with w["pool"].connection() as db:
        second = space(db, w["old"])
        cid = connection(db, w["old"], second)
        db.execute(
            "insert into public.financial_document_extractions(connection_id,user_id,draft,source_bucket,source_path,source_sha256,source_size_bytes,source_media_type) select %s,user_id,jsonb_set(draft,'{connection_id}',to_jsonb(%s::text)),source_bucket,source_path,source_sha256,source_size_bytes,source_media_type from public.financial_document_extractions where connection_id=%s",
            (cid, cid, w["cid"]),
        )
        db.execute(
            "update public.spaces set closed_at=%s where id=%s", (deadline, second)
        )
    try:
        assert command(w).delete_account(user_id=w["old"]).status == "done"
        with w["pool"].connection() as db:
            assert (
                db.execute(
                    "select count(*) from public.spaces where id=any(%s::uuid[]) and closed_at=%s and current_owner_id is null and created_by<>%s",
                    ([w["space"], second], deadline, w["old"]),
                ).fetchone()[0]
                == 2
            )
            paths = db.execute(
                "select source_path from public.financial_document_extractions where connection_id=any(%s::uuid[])",
                ([w["cid"], cid],),
            ).fetchall()
            assert len(paths) == 2 and all(w["objects"].rows[path] for (path,) in paths)
        assert not any(w["old"] in path for path in w["objects"].rows)
    finally:
        with w["pool"].connection() as db:
            placeholder = db.execute(
                "select custodian_id from argus_private.business_custody_reservations where space_id=%s",
                (second,),
            ).fetchone()
            for table in (
                "business_custody_moves",
                "business_custody_objects",
                "business_custody_reservations",
            ):
                db.execute(
                    f"delete from argus_private.{table} where space_id=%s", (second,)
                )
            db.execute("delete from public.spaces where id=%s", (second,))
            if placeholder:
                db.execute("delete from auth.users where id=%s", placeholder)
                db.execute(
                    "delete from argus_private.account_placeholders where id=%s",
                    placeholder,
                )


def test_provider_credentials_are_captured_before_business_custody_clears_them(custody):
    from argus.domain.account_deletion.service import AccountDeletionIncomplete

    from tests.test_account_deletion_postgres import FakeRevoker

    w = custody
    with w["pool"].connection() as db:
        cid = db.execute(
            "insert into public.financial_source_connections(user_id,owner_space_id,source,external_ref,secret_ciphertext) values(%s,%s,'gmail','synthetic-provider-grant',%s) returning id::text",
            (w["old"], w["space"], b"synthetic sealed token"),
        ).fetchone()[0]
    close(w)
    service = command(w)
    with pytest.raises(AccountDeletionIncomplete) as pending:
        service.delete_account(user_id=w["old"])
    assert pending.value.pending == ["gmail"]
    with w["pool"].connection() as db:
        assert db.execute(
            "select external_ref,secret_ciphertext from argus_private.account_deletion_revocations where source_ref=%s",
            (cid,),
        ).fetchone() == ("synthetic-provider-grant", b"synthetic sealed token")
        assert db.execute(
            "select secret_ciphertext from public.financial_source_connections where id=%s",
            (cid,),
        ).fetchone() == (None,)
    revoker = FakeRevoker()
    service._revoker = revoker
    assert service.delete_account(user_id=w["old"]).status == "done"
    assert revoker.calls == [("gmail", cid, b"synthetic sealed token")]


@pytest.mark.parametrize("departing", ["owner", "member"])
def test_closed_member_mail_transport_is_removed_with_the_departing_person(
    custody, departing
):
    w = custody
    with w["pool"].connection() as db:
        db.execute(
            "update auth.users set email_confirmed_at=now() where id=%s",
            (w["users"]["other"],),
        )
        db.execute(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities) values(%s,%s,%s,array['read','prepare'])",
            (w["space"], w["users"]["other"], w["old"]),
        )
    close(w)
    with w["pool"].connection() as db:
        assert (
            db.execute(
                "select count(*) from public.business_close_mail_outbox where space_id=%s and kind='member_closed'",
                (w["space"],),
            ).fetchone()[0]
            == 1
        )
    person = w["old"] if departing == "owner" else w["users"]["other"]
    assert command(w).delete_account(user_id=person).status == "done"
    with w["pool"].connection() as db:
        assert not db.execute(
            "select 1 from public.business_close_mail_outbox where owner_id=%s or recipient_id=%s",
            (person, person),
        ).fetchone()
        assert db.execute(
            "select closed_at from public.spaces where id=%s", (w["space"],)
        ).fetchone()[0]
        assert db.execute(
            "select 1 from public.financial_document_extractions where connection_id=%s",
            (w["cid"],),
        ).fetchone()


@pytest.mark.parametrize("owner_state", ["original", "pending", "transferred"])
@pytest.mark.parametrize("with_code", [False, True])
def test_open_current_owner_refused_before_deletion_effects(
    custody, owner_state, with_code
):
    w = custody
    person = w["old"]
    if owner_state == "pending":
        transfer(w, accept=False)
    elif owner_state == "transferred":
        transfer(w)
        person = w["users"]["other"]
    before = graph._snapshot(w)
    auth, apple = MagicMock(), MagicMock()
    service = command(w, auth=auth, apple=apple)
    with pytest.raises(AccountDeletionRejected, match="business_owner_must_exit"):
        service.delete_account(
            user_id=person,
            **({"apple_authorization_code": "synthetic-code"} if with_code else {}),
        )
    assert graph._snapshot(w) == before
    auth.assert_not_called()
    assert not auth.mock_calls and not apple.mock_calls
    assert not w["objects"].erased
    with w["pool"].connection() as db:
        assert (
            db.execute(
                "select 1 from argus_private.account_deletion_runs where user_id=%s",
                (person,),
            ).fetchone()
            is None
        )
        assert (
            db.execute(
                "select 1 from argus_private.business_custody_reservations where space_id=%s",
                (w["space"],),
            ).fetchone()
            is None
        )
        assert db.execute(
            "select closed_at from public.spaces where id=%s", (w["space"],)
        ).fetchone() == (None,)


@pytest.mark.parametrize("expired_claim", [False, True])
def test_legacy_started_open_owner_run_resumes_same_run(custody, expired_claim):
    from uuid import uuid4

    w = custody
    with w["pool"].connection() as db:
        run_id = db.execute(
            "insert into argus_private.account_deletion_runs"
            " (subject_hash,user_id,analytics_distinct_id,status,steps,claim_id,claimed_until)"
            " values(%s,%s,'synthetic-legacy','started','{}',%s,case when %s then now()-interval '1 second' else null end) returning id::text",
            (
                subject_hash(w["old"]),
                w["old"],
                str(uuid4()) if expired_claim else None,
                expired_claim,
            ),
        ).fetchone()[0]
    outcome = command(w).delete_account(user_id=w["old"])
    assert outcome.status == "done" and outcome.run_id == run_id
    assert not Auth().user_exists(w["old"])
    with w["pool"].connection() as db:
        assert db.execute(
            "select status from argus_private.account_deletion_runs where id=%s",
            (run_id,),
        ).fetchone() == ("done",)
        assert db.execute(
            "select closed_at is not null,current_owner_id from public.spaces where id=%s",
            (w["space"],),
        ).fetchone() == (True, None)
        assert retained_dependencies(db, w["old"]) == ()


def test_owner_admission_query_failure_never_reports_progress(custody, monkeypatch):
    from contextlib import contextmanager

    from argus.domain.account_deletion.apple import AccountDeletionAdmissionError

    w = custody
    auth = MagicMock()
    service = command(w, auth=auth)
    connection = service._households.connection

    class UnavailableOwnership:
        def __init__(self, db):
            self.db = db

        def __getattr__(self, name):
            return getattr(self.db, name)

        def execute(self, query, *args, **kwargs):
            if "select 1 from public.spaces" in query:
                raise RuntimeError("synthetic ownership query unavailable")
            return self.db.execute(query, *args, **kwargs)

    @contextmanager
    def unavailable():
        with connection() as db:
            yield UnavailableOwnership(db)

    monkeypatch.setattr(service._households, "connection", unavailable)
    with pytest.raises(
        AccountDeletionAdmissionError, match="account_deletion_unavailable"
    ):
        service.delete_account(user_id=w["old"])
    assert not auth.mock_calls and not w["objects"].erased
    with w["pool"].connection() as db:
        assert (
            db.execute(
                "select 1 from argus_private.account_deletion_runs where user_id=%s",
                (w["old"],),
            ).fetchone()
            is None
        )
