"""Actual account-deletion command, synthetic PostgreSQL and fake external adapters."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from argus.api.account_deletion_runtime import household_repository
from argus.domain.account_deletion.service import AccountDeletionService
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


def command(w, *, auth=None):
    return AccountDeletionService(
        households=household_repository(w["pool"]),
        auth_admin=auth or Auth(),
        revoker=None,
        analytics=RecordingAnalyticsDeletion(),
        allow_fake_analytics=True,
        source_objects=w["objects"],
        clock=lambda: datetime.now(timezone.utc),
    )


def close(w):
    return PostgresBusinessLifecycle(w["pool"]).close(
        owner_id=w["old"],
        space_id=w["space"],
        confirmation="Colmado",
        idempotency_key="close-account-deletion",
    )


def transfer(w):
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
    with w["pool"].connection() as db:
        db.execute(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities) values(%s,%s,%s,array['read','prepare'])",
            (w["space"], other, w["old"]),
        )
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
                "select count(*) from public.business_close_mail_outbox where space_id=%s",
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
