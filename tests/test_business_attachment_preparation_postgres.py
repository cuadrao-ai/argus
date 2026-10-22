from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from uuid import UUID, uuid4

import pytest
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.actions import (
    ExistingDraft,
    ReviewDraft,
    canonical_input_hash,
)
from argus.domain.ingestion.contract import Attachment
from argus.domain.ingestion.documents.extractor import batch_from_result
from argus.domain.ingestion.documents.models import DocumentDraft, ExtractionResult
from psycopg.types.json import Jsonb

from tests import test_business_actions_postgres as shared
from tests.test_business_actions_postgres import create
from tests.test_business_spaces_migration_postgres import connection

actions = shared.actions
users = shared.users
pytestmark = shared.pytestmark


@pytest.fixture
def prepared(actions):
    service, context, grant = actions
    content = b"synthetic receipt 250.50 DOP"
    digest = sha256(content).hexdigest()
    now = datetime.now(timezone.utc)
    holder = str(uuid4())
    with service.authority.pool.connection() as db:
        connection_id = connection(db, context.owner_id, context.actor.space_id)
        draft = DocumentDraft(
            connection_id=connection_id,
            filename="receipt.txt",
            media_type="text/plain",
            sha256=digest,
            size_bytes=len(content),
            consent=True,
            created_at=now,
            updated_at=now,
        )
        result = ExtractionResult.model_validate(
            dict(
                complete=True,
                readable=True,
                pages_read=[1],
                observations=[
                    dict(
                        page=1,
                        row=1,
                        evidence="transaction",
                        amount="250.50",
                        currency="DOP",
                        direction="outflow",
                        kind_hint="expense",
                        merchant="Synthetic shop",
                    )
                ],
                receipt=dict(payment_status="paid", total="250.50", currency="DOP"),
            )
        )
        batch = batch_from_result(result, digest, connection_id, now, 1)
        attachment = Attachment(
            external_id=digest,
            sha256=digest,
            media_type=draft.media_type,
            size_bytes=len(content),
            filename=draft.filename,
        )
        batch = batch.model_copy(
            update={
                "metadata": {"sha256": digest},
                "candidates": tuple(
                    c.model_copy(update={"attachments": (attachment,)})
                    for c in batch.candidates
                ),
            }
        )
        db.execute(
            "insert into public.financial_document_extractions"
            " (connection_id,user_id,draft,source_bytes,batch) values (%s,%s,%s,%s,%s)",
            (
                connection_id,
                context.owner_id,
                Jsonb(draft.model_dump(mode="json")),
                content,
                Jsonb(batch.model_dump(mode="json")),
            ),
        )
        db.execute(
            "update public.financial_source_connections set lease_holder=%s,"
            " lease_until=%s where id=%s",
            (holder, now + timedelta(minutes=3), connection_id),
        )
    return service, context, grant, connection_id, holder, batch


def bind(prepared, target=None):
    service, context, _, cid, _, _ = prepared
    return service.capture_attachment_preparation(context, UUID(cid), target=target)


def finish(prepared, digest=None):
    service, context, _, cid, holder, batch = prepared
    return service.prepare_attachment(
        user_id=context.owner_id,
        connection_id=cid,
        scope=context.scope,
        holder=holder,
        attempt_id=None,
        expected_batch_sha256=canonical_input_hash(batch) if digest is None else digest,
    )


def test_exact_saved_batch_creates_one_unverified_draft_and_replays(
    prepared, monkeypatch
):
    service, context, _, _, _, batch = prepared
    binding = bind(prepared)
    monkeypatch.setattr(
        service.imports.money, "write", lambda **kw: pytest.fail("capture wrote money")
    )
    result = finish(prepared)
    assert result.outcome == "applied"
    assert finish(prepared).draft_id == result.draft_id
    dossier = service.dossier(context, result.draft_id)
    assert len(dossier.history) == 1
    assert Decimal(dossier.facts.amount.value) == Decimal("250.50")
    assert dossier.facts.amount.verified is False
    assert dossier.facts.fiscal.rnc.state == "unknown"
    with service.authority.pool.connection() as db:
        command = db.execute(
            "select command from public.business_action_receipts"
            " where idempotency_key=%s",
            (str(binding.binding_id),),
        ).fetchone()[0]
    assert command["batch_sha256"] == canonical_input_hash(batch)
    assert command["binding"]["target"] is None


@pytest.mark.parametrize(
    "change", ["revoked", "expired", "readonly", "issuer", "consent", "source", "lease"]
)
def test_changed_original_authority_or_source_refuses_before_draft(prepared, change):
    service, context, grant, cid, _, _ = prepared
    bind(prepared)
    with service.authority.pool.connection() as db:
        if change == "revoked":
            db.execute(
                "update public.business_client_grants set revoked_at=now() where id=%s",
                (grant,),
            )
        elif change == "expired":
            db.execute(
                "update public.business_client_grants set created_at=now()-interval '2 days', expires_at=now()-interval '1 day' where id=%s",
                (grant,),
            )
        elif change == "readonly":
            db.execute(
                "update public.business_client_grants set capabilities=array['read'] where id=%s",
                (grant,),
            )
        elif change == "issuer":
            db.execute(
                "update public.business_client_grants set issuer_id=grantee_id where id=%s",
                (grant,),
            )
        elif change in {"consent", "source"}:
            field = "consent" if change == "consent" else "source_available"
            db.execute(
                "update public.financial_document_extractions set draft=jsonb_set(draft,%s,'false') where connection_id=%s",
                ([field], cid),
            )
        else:
            db.execute(
                "update public.financial_source_connections set lease_until=now()-interval '1 second' where id=%s",
                (cid,),
            )
    with pytest.raises(ActionError):
        finish(prepared)
    with service.authority.pool.connection() as db:
        assert (
            db.execute(
                "select count(*) from public.business_draft_revisions where space_id=%s",
                (context.actor.space_id,),
            ).fetchone()[0]
            == 0
        )


@pytest.mark.parametrize("batch_change", ["unsaved", "wrong_source"])
def test_invalid_saved_batch_refuses(prepared, batch_change):
    service, _, _, cid, _, batch = prepared
    with service.authority.pool.connection() as db:
        changed = (
            None
            if batch_change == "unsaved"
            else Jsonb(
                batch.model_copy(update={"metadata": {"sha256": "f" * 64}}).model_dump(
                    mode="json"
                )
            )
        )
        db.execute(
            "update public.financial_document_extractions set batch=%s where connection_id=%s",
            (changed, cid),
        )
    bind(prepared)
    with pytest.raises(ActionError):
        finish(prepared)


def test_stale_explicit_target_cannot_create_another_draft(prepared):
    service, context, _, _, _, _ = prepared
    draft_id, version = create(service, context)
    bind(prepared, ExistingDraft(draft_id=draft_id, version=version))
    service.review(
        context,
        draft_id,
        ReviewDraft(
            version=version, facts={"amount": {"state": "known", "value": "900"}}
        ),
        str(uuid4()),
    )
    with pytest.raises(ActionError, match="stale_version"):
        finish(prepared)
    assert len(service.dossier(context, draft_id).history) == 2


@pytest.mark.parametrize("change", ["revoked", "issuer", "consent"])
def test_completion_recheck_rolls_back_draft_and_receipt(prepared, monkeypatch, change):
    from argus.domain.business.actions import mutations

    service, context, grant, cid, _, _ = prepared
    binding = bind(prepared)
    original = mutations.prepare_attachment

    def change_during_write(tx, *args):
        result = original(tx, *args)
        if change == "revoked":
            tx.rows(
                "update public.business_client_grants set revoked_at=now() where id=%s",
                (grant,),
            )
        elif change == "issuer":
            tx.rows(
                "update public.business_client_grants set issuer_id=grantee_id where id=%s",
                (grant,),
            )
        else:
            tx.rows(
                "update public.financial_document_extractions set draft=jsonb_set(draft,'{consent}','false') where connection_id=%s",
                (cid,),
            )
        return result

    monkeypatch.setattr(mutations, "prepare_attachment", change_during_write)
    with pytest.raises(ActionError):
        finish(prepared)
    with service.authority.pool.connection() as db:
        assert (
            db.execute(
                "select count(*) from public.business_draft_revisions where space_id=%s",
                (context.actor.space_id,),
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "select count(*) from public.business_action_receipts where idempotency_key=%s",
                (str(binding.binding_id),),
            ).fetchone()[0]
            == 0
        )


def test_wrong_well_formed_batch_digest_refuses_before_writes(prepared):
    service, context, _, _, _, batch = prepared
    binding = bind(prepared)
    changed = batch.model_copy(
        update={"metadata": {**batch.metadata, "extra": "changed"}}
    )
    for digest in ("f" * 64, canonical_input_hash(changed)):
        with pytest.raises(ActionError, match="business_preparation_batch_changed"):
            finish(prepared, digest)
    with service.authority.pool.connection() as db:
        assert (
            db.execute(
                "select count(*) from public.business_action_receipts where idempotency_key=%s",
                (str(binding.binding_id),),
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "select count(*) from public.business_draft_revisions where space_id=%s",
                (context.actor.space_id,),
            ).fetchone()[0]
            == 0
        )


def test_new_grant_does_not_rescue_revoked_original(prepared):
    service, context, grant, _, _, _ = prepared
    bind(prepared)
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.business_client_grants set revoked_at=now() where id=%s",
            (grant,),
        )
        db.execute(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities) values (%s,%s,%s,array['read','prepare'])",
            (context.actor.space_id, context.actor.actor_id, context.owner_id),
        )
    with pytest.raises(ActionError):
        finish(prepared)


def test_disconnected_source_refuses_completion(prepared):
    service, _, _, cid, _, _ = prepared
    bind(prepared)
    from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository

    PostgresConnectionRepository(service.authority.pool).disconnect(
        user_id=prepared[1].owner_id, connection_id=cid, now=datetime.now(timezone.utc)
    )
    with pytest.raises(ActionError):
        finish(prepared)


@pytest.mark.owner_acts
def test_approve_refuses_a_body_that_names_other_ids(prepared):
    service, context, _, cid, _, _ = prepared
    bind(prepared)
    draft_id = finish(prepared).draft_id
    assert str(draft_id) != str(cid)
    foreign = str(uuid4())
    refused = post_approve(
        service,
        context,
        draft_id,
        extra={"document_id": foreign, "source_id": foreign, "connection_id": foreign},
    )
    assert refused.status_code == 422, refused.text


def post_approve(service, context, draft_id, *, version=1, extra=None):
    from argus.api.business_drafts import DraftContext, require_drafts
    from argus.api.email_intake import configure_email_intake, email_intake
    from argus.api.routers.business_drafts import router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = "approve-origin"
        return await call_next(request)

    app.include_router(router)
    app.dependency_overrides[require_drafts] = lambda: DraftContext(
        service, context.actor.actor_id, str(context.actor.space_id)
    )
    previous = email_intake()
    configure_email_intake(None)
    try:
        with TestClient(app) as drafts:
            return drafts.post(
                f"/business/drafts/{draft_id}/approve",
                json={"version": version, "action": "record_expense", **(extra or {})},
                headers={"Idempotency-Key": str(uuid4())},
            )
    finally:
        configure_email_intake(previous)


def stored_origin(service, draft_id):
    with service.authority.pool.connection() as db:
        return db.execute(
            "select s.origin from public.business_draft_sources l "
            "join public.business_sources s on s.id=l.source_id and s.space_id=l.space_id "
            "where l.draft_id=%s",
            (draft_id,),
        ).fetchone()[0]


@pytest.mark.owner_acts
def test_email_origin_with_no_delivery_is_refused(prepared):
    service, context, _, cid, _, _ = prepared
    space = str(context.actor.space_id)
    with service.authority.pool.connection() as db:
        db.execute(
            "insert into public.business_sources"
            " (space_id,kind,channel,source_key,connection_id,received_at,origin)"
            " values (%s,'attachment','web',%s,%s,now(),'email')",
            (space, f"attachment:{cid}", cid),
        )
        assert (
            db.execute(
                "select count(*) from public.business_email_deliveries where space_id=%s",
                (space,),
            ).fetchone()[0]
            == 0
        )
    with pytest.raises(ActionError, match="email_sender_unauthorized"):
        bind(prepared)
    with service.authority.pool.connection() as db:
        assert db.execute(
            "select count(*) from public.business_draft_sources where space_id=%s",
            (space,),
        ).fetchone() == (0,)


@pytest.mark.owner_acts
def test_upload_origin_with_no_delivery_still_approves(prepared):
    service, context, _, _, _, _ = prepared
    bind(prepared)
    draft_id = finish(prepared).draft_id
    assert stored_origin(service, draft_id) == "direct"
    reviewed = service.review(
        context,
        draft_id,
        ReviewDraft(
            version=1,
            facts={
                "occurred_on": {"state": "known", "value": "2026-10-01"},
                "funding": {"state": "known", "value": {"kind": "owner_funds"}},
                "business_share": {"state": "known", "value": {"kind": "all"}},
            },
        ),
        str(uuid4()),
    )
    assert reviewed.outcome == "applied", reviewed
    approved = post_approve(service, context, draft_id, version=reviewed.version)
    assert approved.status_code == 200, approved.text


def test_nonexistent_target_refuses_binding(prepared):
    with pytest.raises(ActionError):
        bind(prepared, ExistingDraft(draft_id=uuid4(), version=1))


@pytest.mark.owner_acts
def test_accepted_target_refuses_completion(prepared):
    service, context, _, _, _, _ = prepared
    from argus.domain.business.contracts.actions import ApproveExpense

    from tests.test_business_actions_postgres import ready

    draft_id = ready(service, context)
    bind(prepared, ExistingDraft(draft_id=draft_id, version=1))
    result = service.approve(
        context,
        draft_id,
        ApproveExpense(version=1, action="record_expense"),
        str(uuid4()),
    )
    assert result.outcome == "applied", result
    with pytest.raises(ActionError) as denied:
        finish(prepared)
    assert denied.value.code in {"stale_version", "recorded_correction_unsupported"}


def link_prepared_email(prepared):
    from argus.domain.ingestion.email_intake.models import EmailDeliveryPart
    from argus.domain.ingestion.email_intake.store import PostgresEmailStore

    service, context, grant, cid, _, _ = prepared
    store = PostgresEmailStore(service.authority.pool)
    route = store.create_route(
        recipient=f"recibos-{uuid4().hex[:8]}@recibos.example.test",
        space_id=str(context.actor.space_id),
        principal_id=context.owner_id,
        granted_by=str(context.actor.actor_id),
        grant_id=str(grant),
    )
    sender = "proveedor@example.test"
    store.upsert_sender(route.space_id, "address", sender, "authorized")
    delivery = store.enqueue(
        "resend",
        str(uuid4()),
        (route.recipient,),
        route_id=route.id,
        space_id=route.space_id,
        principal_id=route.principal_id,
    )
    claimed = store.claim(delivery_id=delivery.id)
    store.update(claimed, sender=sender)
    store.stamp_route(claimed, auth_result="aligned")
    store.put_part(
        claimed,
        EmailDeliveryPart("receipt", "recibo.png", "image/png", "captured", cid, None),
    )
    return store, route


@pytest.mark.parametrize("stage", ["before_provider", "before_commit"])
def test_sender_removed_after_binding_stops_preparation(prepared, stage):
    service, context, _, cid, holder, _ = prepared
    store, route = link_prepared_email(prepared)
    bind(prepared)
    with service.authority.pool.connection() as db:
        db.execute(
            "delete from public.business_email_senders where space_id=%s",
            (route.space_id,),
        )
    with pytest.raises(ActionError, match="email_sender_unauthorized"):
        if stage == "before_provider":
            service.check_attachment_preparation(
                user_id=context.owner_id,
                connection_id=cid,
                scope=context.scope,
                holder=holder,
                attempt_id=None,
            )
        else:
            finish(prepared)
    with service.authority.pool.connection() as db:
        assert db.execute(
            "select count(*) from public.business_draft_revisions where space_id=%s",
            (route.space_id,),
        ).fetchone() == (0,)
        assert db.execute(
            "select count(*) from public.business_action_receipts where space_id=%s and command->>'action'='prepare_attachment'",
            (route.space_id,),
        ).fetchone() == (0,)


@pytest.mark.owner_acts
def test_orphan_email_source_without_connection_still_blocks_approval(prepared):
    service, context, _, _, _, _ = prepared
    bind(prepared)
    draft_id = finish(prepared).draft_id
    with service.authority.pool.connection() as db:
        source_id = db.execute(
            "insert into public.business_sources(space_id,kind,channel,source_key,text_content,received_at,origin)"
            " values(%s,'message','web',%s,'Synthetic legacy email',now(),'email') returning id",
            (context.actor.space_id, f"attachment:{uuid4()}"),
        ).fetchone()[0]
        db.execute(
            "insert into public.business_draft_sources(space_id,draft_id,source_id) values(%s,%s,%s)",
            (context.actor.space_id, draft_id, source_id),
        )
    denied = post_approve(service, context, draft_id, version=1)
    assert (denied.status_code, denied.json()["detail"]["code"]) == (
        403,
        "email_sender_unauthorized",
    )


@pytest.mark.owner_acts
@pytest.mark.parametrize("wrong", ["space", "connection"])
def test_unrelated_upload_ledger_cannot_authorize_email(prepared, users, wrong):
    from argus.domain.business.authority import authorize
    from argus.domain.business.contracts.authority import TrustedActor
    from argus.domain.business.transactions import record_legacy_action

    from tests.test_business_spaces_migration_postgres import space

    service, context, grant, cid, _, _ = prepared
    with service.authority.pool.connection() as db:
        db.execute(
            "insert into public.business_sources(space_id,kind,channel,source_key,connection_id,received_at,origin) values(%s,'attachment','web',%s,%s,now(),'email')",
            (context.actor.space_id, f"attachment:{cid}", cid),
        )
        if wrong == "space":
            other_space = space(db, users["other"])
            other_grant = db.execute(
                "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities) values(%s,%s,%s,array['read','prepare','approve']) returning id",
                (other_space, users["other"], users["other"]),
            ).fetchone()[0]
            live = authorize(
                db,
                TrustedActor(
                    actor_id=users["other"], actor_kind="member", space_id=other_space
                ),
                other_grant,
            )
            subjects = [cid]
        else:
            live = authorize(db, context.actor, grant)
            subjects = [connection(db, context.owner_id, context.actor.space_id)]
        record_legacy_action(db, live, "receipt_upload", subjects, str(uuid4()))
    with pytest.raises(ActionError, match="email_sender_unauthorized"):
        bind(prepared)
    with service.authority.pool.connection() as db:
        foreign = connection(db, users["other"])
    with pytest.raises(ActionError, match="business_record_not_found"):
        service.capture_attachment_preparation(context, UUID(foreign), target=None)


@pytest.mark.owner_acts
def test_legacy_default_direct_origin_does_not_authorize_linked_email(prepared):
    service, context, _, cid, holder, _ = prepared
    bind(prepared)
    draft_id = finish(prepared).draft_id
    store, route = link_prepared_email(prepared)
    assert stored_origin(service, draft_id) == "direct"
    with service.authority.pool.connection() as db:
        db.execute(
            "delete from public.business_email_senders where space_id=%s",
            (route.space_id,),
        )
    with pytest.raises(ActionError, match="email_sender_unauthorized"):
        service.check_attachment_preparation(
            user_id=context.owner_id,
            connection_id=cid,
            scope=context.scope,
            holder=holder,
            attempt_id=None,
        )
    denied = post_approve(service, context, draft_id, version=1)
    assert (denied.status_code, denied.json()["detail"]["code"]) == (
        403,
        "email_sender_unauthorized",
    )
