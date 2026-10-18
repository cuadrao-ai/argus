"""Custody deletion uses actual PostgreSQL and local fake Auth/Storage only."""

from __future__ import annotations

import json
import os
from hashlib import sha256
from uuid import uuid4

import psycopg
import pytest
from argus.domain.business.authority import ActionError, authorize
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.contracts.recovery import SenderLease
from argus.domain.business.custody_graph import (
    FAMILIES,
    PostgresBusinessCustodyGraph,
    _hash,
    retained_dependencies,
)
from argus.domain.business.custody_objects import (
    CustodyReservation,
    PostgresBusinessCustodyCopies,
)
from argus.domain.business.lifecycle import PostgresBusinessLifecycle
from argus.domain.business.transfer import PostgresBusinessTransfer
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from tests import test_business_actions_postgres as actions_fixture
from tests import test_business_attachment_preparation_postgres as bridge
from tests import test_financial_accounts_postgres as shared

users = shared.users
actions = actions_fixture.actions
prepared = bridge.prepared

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL required")


def test_unclaimed_move_is_rejected():
    with ConnectionPool(DSN, min_size=0, max_size=2) as pool:
        with pytest.raises(RuntimeError, match="claim"):
            PostgresBusinessCustodyGraph(pool).detach(
                space_id=str(uuid4()),
                departing_user_id=str(uuid4()),
                reservation=CustodyReservation(*(str(uuid4()) for _ in range(3))),
                deletion_run_id=str(uuid4()),
                claim_id=str(uuid4()),
            )


class FakeObjects:
    bucket = "financial-document-sources"

    def __init__(self):
        self.rows = {}
        self.erased = []

    def get(self, path):
        return self.rows.get(path)

    def put(self, path, content, media):
        self.rows[path] = content

    def delete(self, prefix):
        self.erased.append(prefix)
        self.rows = {p: b for p, b in self.rows.items() if prefix not in p}


class FakeAuth:
    def user_exists(self, user):
        with psycopg.connect(DSN) as db:
            return bool(
                db.execute("select 1 from auth.users where id=%s", (user,)).fetchone()
            )

    def create_placeholder(self, *, user_id, email):
        with psycopg.connect(DSN) as db:
            db.execute(
                "insert into auth.users(id,email,is_anonymous,email_confirmed_at,banned_until,raw_app_meta_data) values(%s,%s,false,now(),now()+interval '100 years','{\"placeholder\":true}')",
                (user_id, email),
            )

    def delete_user(self, user):
        with psycopg.connect(DSN) as db:
            db.execute("delete from auth.users where id=%s", (user,))


@pytest.fixture
def custody(prepared, users, request):
    service, context, grant, cid, _, _ = prepared
    pool = service.authority.pool
    old = str(context.owner_id)
    space = str(context.actor.space_id)
    original = b"synthetic receipt 250.50 DOP"
    digest = sha256(original).hexdigest()
    rebuilt = b"synthetic rebuilt image"
    objects = FakeObjects()
    source = f"sealed/{old}/{digest}"
    rebuilt_path = f"rebuilt/{old}/{digest}"
    objects.rows = {source: original, rebuilt_path: rebuilt}
    if getattr(request, "param", "objects") != "inline":
        with pool.connection() as db:
            db.execute(
                "update public.financial_document_extractions set source_bytes=null,source_bucket=%s,source_path=%s,source_sha256=%s,source_size_bytes=%s,source_media_type=%s,rebuilt_bucket=%s,rebuilt_path=%s,rebuilt_sha256=%s,rebuilt_size_bytes=%s,rebuilt_media_type=%s where connection_id=%s",
                (
                    objects.bucket,
                    source,
                    digest,
                    len(original),
                    "text/plain",
                    objects.bucket,
                    rebuilt_path,
                    sha256(rebuilt).hexdigest(),
                    len(rebuilt),
                    "image/png",
                    cid,
                ),
            )
    binding = bridge.bind(prepared)
    result = bridge.finish(prepared)
    assert result.outcome == "applied"
    # A separate action adds a saved plan, source links and revision history.
    actions_fixture.create(service, context)
    with pool.connection() as db:
        _seed_financial(db, old, space, cid)
        transport = _seed_transport(db, old, space, cid, grant)
    yield dict(
        pool=pool,
        space=space,
        old=old,
        cid=cid,
        objects=objects,
        binding=binding,
        users=users,
        transport=transport,
        service=service,
        context=context,
    )
    with pool.connection() as db:
        db.execute("set constraints all deferred")
        scope = PostgresBusinessCustodyGraph._scope(db, space, old, lock=False)
        db.execute(
            "delete from public.financial_activity_groups where id=any(%s::uuid[])",
            (scope["activities"],),
        )
        ids = [
            r[0]
            for r in db.execute(
                "select custodian_id from argus_private.business_custody_reservations where space_id=%s",
                (space,),
            )
        ]
        db.execute(
            "delete from argus_private.business_custody_changes where space_id=%s",
            (space,),
        )
        db.execute(
            "delete from argus_private.business_custody_moves where space_id=%s", (space,)
        )
        db.execute(
            "delete from argus_private.business_custody_objects where space_id=%s",
            (space,),
        )
        db.execute(
            "delete from argus_private.business_custody_reservations where space_id=%s",
            (space,),
        )
        db.execute("delete from public.spaces where id=%s", (space,))
        for pid in ids:
            db.execute("delete from auth.users where id=%s", (pid,))
            db.execute(
                "delete from argus_private.account_placeholders where id=%s", (pid,)
            )


def _seed_financial(db, old, space, cid):
    db.execute("set constraints financial_activity_current_revision_fk deferred")
    account, asset, debt = (str(uuid4()) for _ in range(3))
    for aid, kind in ((account, "cash"), (asset, "property"), (debt, "other_debt")):
        db.execute(
            "insert into public.financial_accounts(id,user_id,owner_space_id,type,currency) values(%s,%s,%s,%s,%s)",
            (aid, old, space, kind, "DOP"),
        )
    db.execute(
        "insert into public.financial_asset_details(account_id,user_id,related_debt_account_id) values(%s,%s,%s)",
        (asset, old, debt),
    )
    db.execute(
        "insert into public.financial_asset_changes(account_id,user_id,account_version,previous_share_bps,ownership_share_bps,related_debt_account_id,recorded_by,idempotency_key,identity_hash) values(%s,%s,2,10000,10000,%s,%s,'asset','asset-hash')",
        (asset, old, debt, old),
    )
    db.execute(
        "insert into public.financial_account_idempotency(user_id,operation_scope,idempotency_key,identity_hash,account_id) values(%s,'financial_accounts.create','account','account-hash',%s)",
        (old, account),
    )
    records = []
    for funded in (False, True, False):
        record, activity = str(uuid4()), str(uuid4())
        records.append(record)
        db.execute(
            "insert into public.financial_records(id,user_id,account_id,owner_space_id,funding,currency,record_kind) values(%s,%s,%s,%s,%s,%s,%s)",
            (
                record,
                old,
                None if funded else account,
                space if funded else None,
                "owner_funds" if funded else None,
                "DOP" if funded else None,
                "expense",
            ),
        )
        db.execute(
            "insert into public.financial_record_revisions(record_id,user_id,revision,amount_minor,as_of,as_of_zone,reason,recorded_by,details) values(%s,%s,1,25050,now(),'America/Santo_Domingo','receipt expense',%s,%s)",
            (
                record,
                old,
                old,
                Jsonb({"source_id": cid, "note": "preserve fiscal detail"}),
            ),
        )
        db.execute(
            "insert into public.financial_activity_groups(id,user_id,kind,current_revision) values(%s,%s,'expense',1)",
            (activity, old),
        )
        db.execute(
            "insert into public.financial_activity_revisions(activity_id,user_id,revision) values(%s,%s,1)",
            (activity, old),
        )
        db.execute(
            "insert into public.financial_activity_memberships(activity_id,user_id,activity_revision,record_id,record_revision,record_owner_id,role) values(%s,%s,1,%s,1,%s,'single')",
            (activity, old, record, old),
        )
        db.execute(
            "insert into public.financial_activity_receipts(user_id,scope,idempotency_key,identity_hash,activity_id,revision,affected_accounts) values(%s,'expense',%s,'original-hash',%s,1,%s)",
            (old, record, activity, [] if funded else [account]),
        )
        if not funded:
            db.execute(
                "insert into public.financial_operation_receipts(user_id,account_id,idempotency_key,identity_hash,record_id,revision,kind) values(%s,%s,%s,'original-hash',%s,1,'expense')",
                (old, account, record, record),
            )
    db.execute(
        "insert into public.financial_observation_coverage(account_id,user_id,observation_id,observation_revision,activity_id,activity_revision,included) values(%s,%s,%s,1,%s,1,true)",
        (account, old, records[0], records[2]),
    )
    db.execute(
        "insert into public.financial_import_account_links(user_id,connection_id,account_key,account_id,created_at) values(%s,%s,'cash',%s,now())",
        (old, cid, account),
    )
    event = db.execute(
        "select id from public.financial_import_events where owner_space_id=%s limit 1",
        (space,),
    ).fetchone()[0]
    db.execute(
        "insert into public.financial_import_observations(id,user_id,event_id,connection_id,source,external_id,fingerprint,candidate,live,revisions,first_seen_at,updated_at) values(%s,%s,%s,%s,'statement','synthetic','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','{}',true,1,now(),now())",
        (uuid4(), old, event, cid),
    )
    conversation = str(uuid4())
    db.execute(
        "insert into public.conversations(id,user_id,owner_space_id,title) values(%s,%s,%s,'Business receipt question')",
        (conversation, old, space),
    )
    db.execute(
        "insert into public.messages(id,conversation_id,user_id,role,content,metadata) values(%s,%s,%s,'user','Why is this expense 250.50?',%s)",
        (
            uuid4(),
            conversation,
            old,
            Jsonb({"actor_id": old, "display_name": "Original person"}),
        ),
    )
    message = db.execute(
        "select id from public.messages where conversation_id=%s", (conversation,)
    ).fetchone()[0]
    db.execute(
        "insert into public.chat_turn_lifecycles(turn_id,user_id,conversation_id,request_id) values(%s,%s,%s,'synthetic')",
        (message, old, conversation),
    )
    db.execute(
        "insert into public.conversation_read_states(conversation_id,user_id) values(%s,%s)",
        (conversation, old),
    )
    db.execute(
        "insert into public.checkpoints(thread_id,checkpoint_id,checkpoint,metadata) values(%s,'checkpoint','{}',%s)",
        (conversation, Jsonb({"user_id": old})),
    )
    db.execute(
        "insert into public.checkpoint_blobs(thread_id,channel,version,type,blob) values(%s,'input','1','bytes',%s)",
        (conversation, old.encode()),
    )
    db.execute(
        "insert into public.checkpoint_writes(thread_id,checkpoint_id,task_id,idx,channel,blob) values(%s,'checkpoint','task',0,'input',%s)",
        (conversation, old.encode()),
    )


def _seed_transport(db, old, space, cid, grant):
    digest = "b" * 64
    route = Jsonb({"provider": "synthetic", "model": "local-only"})
    db.execute(
        "insert into public.business_ai_consents(space_id,owner_id,consenting_actor_id,grant_id,issuer_id,scope_version,purpose,disclosure,route,route_hash,idempotency_key,input_hash) values(%s,%s,%s,%s,%s,1,'business_ai_receipt_reading','Synthetic permission',%s,%s,'consent',%s)",
        (space, old, old, grant, old, route, digest, digest),
    )
    db.execute(
        "insert into public.business_receipt_reading_consents(space_id,owner_id,scope_version,route,idempotency_key,request_hash,disclosure) values(%s,%s,1,%s,'reading',%s,'Synthetic permission')",
        (space, old, route, digest),
    )
    db.execute(
        "insert into public.business_receipt_consent_commands(space_id,owner_id,idempotency_key,request_hash) values(%s,%s,'command',%s)",
        (space, old, digest),
    )
    db.execute(
        "insert into public.business_receipt_read_states(space_id,person_id,connection_id,completion_cursor) values(%s,%s,%s,%s)",
        (space, old, cid, digest),
    )
    event = db.execute(
        "select id from public.financial_import_events where owner_space_id=%s limit 1",
        (space,),
    ).fetchone()[0]
    source = db.execute(
        "select id from public.business_sources where space_id=%s limit 1", (space,)
    ).fetchone()[0]
    db.execute(
        "insert into public.business_questions(space_id,draft_id,field,asked_of,channel,state,prompt,allowed_answers,answer_source_id) values(%s,%s,'amount','owner','web','answered','How much?',array['known'],%s)",
        (space, event, source),
    )
    email_route = db.execute(
        "insert into public.business_email_routes(recipient,space_id,principal_id,granted_by,grant_id) values(%s,%s,%s,%s,%s) returning id",
        (f"{uuid4()}@synthetic.invalid", space, old, old, grant),
    ).fetchone()[0]
    delivery = db.execute(
        "insert into public.business_email_deliveries(provider,external_id,recipients,route_id,space_id,principal_id,original_document_id,sender,text_body) values('resend',%s,'[\"private@synthetic.invalid\"]',%s,%s,%s,%s,'private@synthetic.invalid','personal transport text') returning id",
        (str(uuid4()), email_route, space, old, cid),
    ).fetchone()[0]
    db.execute(
        "insert into public.business_email_parts(delivery_id,id,filename,media_type,state,document_id) values(%s,'part','receipt.txt','text/plain','captured',%s)",
        (delivery, cid),
    )
    db.execute(
        "insert into public.business_email_daily_usage(route_id,day,messages,bytes_used) values(%s,current_date,1,10)",
        (email_route,),
    )
    sender = sha256(str(uuid4()).encode()).digest()
    link = db.execute(
        "insert into public.whatsapp_sender_links(destination_owner_id,destination_space_id,wa_id_hash,last4,reply_language,status,linked_at) values(%s,%s,%s,'1234','es-419','active',clock_timestamp()) returning id",
        (old, space, sender),
    ).fetchone()[0]
    consent = db.execute(
        "insert into public.business_whatsapp_ai_consents(sender_link_id,space_id,owner_id,sender_hash,consenting_actor_id,grant_id,issuer_id,scope_version,purpose,disclosure,route,route_hash,idempotency_key,input_hash) values(%s,%s,%s,%s,%s,%s,%s,2,'business_whatsapp_receipt_reading','Synthetic permission',%s,%s,'whatsapp',%s) returning id",
        (link, space, old, sender, old, grant, old, route, digest, digest),
    ).fetchone()[0]
    message_key = sha256(str(uuid4()).encode()).digest()
    db.execute(
        "insert into public.whatsapp_inbound_messages(id,provider_message_key,sender_hash,destination_owner_id,status,received_at,updated_at,sender_link_id,destination_space_id,sent_at,transport_envelope,transport_key_id,composition_state,ai_consent_id) values(%s,%s,%s,%s,'captured',now(),now(),%s,%s,now(),%s,%s,'completed',%s)",
        (
            uuid4(),
            message_key,
            sender,
            old,
            link,
            space,
            b"\x01" + b"synthetic private phone and envelope",
            "c" * 32,
            consent,
        ),
    )
    db.execute(
        "insert into public.whatsapp_outbox(provider_message_key,reply_index,body) values(%s,0,'Private pending reply')",
        (message_key,),
    )
    db.execute(
        "insert into public.whatsapp_reply_days(sender_hash,day,owner_id,sent_count) values(%s,current_date,%s,1)",
        (sender, old),
    )
    db.execute(
        "insert into public.whatsapp_reply_groups(sender_hash,owner_id,link_id,failed_count,samples,last_sent_at,send_after) values(%s,%s,%s,1,'[\"private sample\"]',now(),now())",
        (sender, old, link),
    )
    db.execute(
        "insert into public.whatsapp_reply_attempts(sender_hash,token,owner_id,link_id,day,failed_count,samples,last_sent_at,expires_at,retries) values(%s,%s,%s,%s,current_date,1,'[\"private sample\"]',now(),now()+interval '1 hour',0)",
        (sender, uuid4(), old, link),
    )
    return dict(
        link=link,
        sender=sender,
        message_key=message_key,
        delivery=delivery,
        email_route=email_route,
    )


def claim(world):
    run, token = str(uuid4()), str(uuid4())
    with world["pool"].connection() as db:
        db.execute(
            "insert into argus_private.account_deletion_runs(id,subject_hash,user_id,analytics_distinct_id,status,claim_id,claimed_until) values(%s,%s,%s,'synthetic','started',%s,now()+interval '15 minutes')",
            (run, sha256(run.encode()).hexdigest(), world["old"], token),
        )
    return run, token


@pytest.mark.owner_acts
@pytest.mark.parametrize("transferred", [False, True])
def test_receipt_graph_survives_closed_or_transferred_custodian_deletion(
    custody, transferred
):
    w = custody
    with w["pool"].connection() as db:
        before = db.execute(
            "select source_sha256,rebuilt_sha256,batch,draft,source_bytes from public.financial_document_extractions where connection_id=%s",
            (w["cid"],),
        ).fetchone()
        source_ids = db.execute(
            "select id from public.business_sources where space_id=%s order by id",
            (w["space"],),
        ).fetchall()
        revisions = db.execute(
            "select draft_id,version,before_facts,after_facts,source_ids from public.business_draft_revisions where space_id=%s order by draft_id,version",
            (w["space"],),
        ).fetchall()
        financial = {
            t: db.execute(
                f"select to_jsonb(t)-'user_id'-'record_owner_id'-'recorded_by' from public.{t} t order by 1"
            ).fetchall()
            for t in (
                "financial_record_revisions",
                "financial_activity_memberships",
                "financial_activity_receipts",
                "financial_operation_receipts",
                "financial_observation_coverage",
                "financial_asset_changes",
            )
        }
        conversations = [
            r[0]
            for r in db.execute(
                "select id::text from public.conversations where owner_space_id=%s",
                (w["space"],),
            )
        ]
        queued = db.execute(
            "select t.turn_key,l.space_id,l.sender_hash,l.holder,l.fence,l.lease_until from public.business_turns t join public.business_sender_leases l on l.space_id=t.space_id and l.sender_hash=t.sender_hash where t.space_id=%s limit 1",
            (w["space"],),
        ).fetchone()
        if transferred:
            db.execute(
                "update auth.users set email_confirmed_at=now() where id=%s",
                (w["users"]["other"],),
            )
            target = db.execute(
                "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities) values(%s,%s,%s,array['read','prepare']) returning id",
                (w["space"], w["users"]["other"], w["old"]),
            ).fetchone()[0]
    transfer_id = None
    if transferred:
        transfer = PostgresBusinessTransfer(w["pool"])
        pending = transfer.request(
            owner_id=w["old"],
            space_id=w["space"],
            target_grant_id=str(target),
            confirmation="Colmado",
            idempotency_key="transfer",
        )
        transfer_id = transfer.accept(
            actor_id=w["users"]["other"], transfer_id=pending.id
        ).id
    if not transferred:
        PostgresBusinessLifecycle(w["pool"]).close(
            owner_id=w["old"],
            space_id=w["space"],
            confirmation="Colmado",
            idempotency_key="close",
        )
    with w["pool"].connection() as db:
        deadline = db.execute(
            "select closed_at from public.spaces where id=%s", (w["space"],)
        ).fetchone()[0]
    reservation = PostgresBusinessCustodyCopies(
        w["pool"], w["objects"], FakeAuth()
    ).prepare(space_id=w["space"], departing_user_id=w["old"])
    with w["pool"].connection() as db:
        db.execute(
            "insert into argus_private.business_custody_objects(space_id,source_path,destination_path,sha256,size_bytes,media_type) values(%s,%s,%s,%s,6,'text/plain')",
            (
                w["space"],
                f"sealed/{w['old']}/orphan",
                f"sealed/{reservation.custodian_id}/orphan",
                sha256(b"orphan").hexdigest(),
            ),
        )
    run, token = claim(w)
    writer = PostgresBusinessCustodyGraph(w["pool"])
    args = dict(
        space_id=w["space"],
        departing_user_id=w["old"],
        reservation=reservation,
        deletion_run_id=run,
        claim_id=token,
    )
    assert writer.detach(**args).moved
    assert not writer.detach(**args).moved
    with w["pool"].connection() as db:
        assert not retained_dependencies(db, w["old"])
        after = db.execute(
            "select source_sha256,rebuilt_sha256,batch,draft,source_bytes from public.financial_document_extractions where connection_id=%s",
            (w["cid"],),
        ).fetchone()
        assert after == before
        assert (
            db.execute(
                "select id from public.business_sources where space_id=%s order by id",
                (w["space"],),
            ).fetchall()
            == source_ids
        )
        assert (
            db.execute(
                "select draft_id,version,before_facts,after_facts,source_ids from public.business_draft_revisions where space_id=%s order by draft_id,version",
                (w["space"],),
            ).fetchall()
            == revisions
        )
        assert db.execute(
            "select created_by::text,current_owner_id::text,closed_at from public.spaces where id=%s",
            (w["space"],),
        ).fetchone() == (
            reservation.custodian_id,
            w["users"]["other"] if transferred else None,
            deadline,
        )
        rows = db.execute(
            "select actor_id::text,actor,command,input_hash from public.business_action_receipts where space_id=%s",
            (w["space"],),
        ).fetchall()
        assert rows and all(r[0] == reservation.deleted_actor_id for r in rows)
        assert all(w["old"] not in str(r) for r in rows)
        assert all(r[3] == _hash(r[2]) for r in rows)
        for table, snapshot in financial.items():
            assert (
                db.execute(
                    f"select to_jsonb(t)-'user_id'-'record_owner_id'-'recorded_by' from public.{table} t order by 1"
                ).fetchall()
                == snapshot
            )
        assert db.execute(
            "select owner_id::text,consenting_actor_id::text,revoked_at is not null,invalidated_by_transfer_id::text from public.business_ai_consents where space_id=%s",
            (w["space"],),
        ).fetchone() == (
            reservation.deleted_actor_id,
            reservation.deleted_actor_id,
            True,
            transfer_id,
        )
        assert db.execute(
            "select owner_id::text,consenting_actor_id::text,revoked_at is not null from public.business_whatsapp_ai_consents where space_id=%s",
            (w["space"],),
        ).fetchone() == (reservation.custodian_id, reservation.deleted_actor_id, True)
        assert db.execute(
            "select destination_owner_id::text,last4,status from public.whatsapp_sender_links where destination_space_id=%s",
            (w["space"],),
        ).fetchone() == (reservation.custodian_id, "0000", "revoked")
        for table, key, value in (
            ("business_email_routes", "space_id", w["space"]),
            ("business_email_deliveries", "space_id", w["space"]),
            ("business_email_parts", "delivery_id", w["transport"]["delivery"]),
            ("business_email_daily_usage", "route_id", w["transport"]["email_route"]),
            ("whatsapp_inbound_messages", "destination_space_id", w["space"]),
            ("whatsapp_outbox", "provider_message_key", w["transport"]["message_key"]),
            ("whatsapp_reply_attempts", "link_id", w["transport"]["link"]),
            ("whatsapp_reply_groups", "link_id", w["transport"]["link"]),
            ("whatsapp_reply_days", "sender_hash", w["transport"]["sender"]),
        ):
            assert (
                db.execute(
                    f"select count(*) from public.{table} where {key}=%s", (value,)
                ).fetchone()[0]
                == 0
            )
        for table in ("checkpoints", "checkpoint_writes", "checkpoint_blobs"):
            assert (
                db.execute(
                    f"select count(*) from public.{table} where thread_id=any(%s)",
                    (conversations,),
                ).fetchone()[0]
                == 0
            )
        assert db.execute(
            "select metadata,content from public.messages where user_id=%s",
            (reservation.custodian_id,),
        ).fetchone() == (
            {"actor_id": reservation.deleted_actor_id, "display_name": "Exmiembro"},
            "Why is this expense 250.50?",
        )
        with pytest.raises(ActionError):
            authorize(
                db,
                TrustedActor(
                    actor_id=reservation.custodian_id,
                    actor_kind="member",
                    space_id=w["space"],
                ),
            )
        with db.transaction():
            db.execute("set local role authenticated")
            db.execute(
                "select set_config('request.jwt.claims',%s,true)",
                (
                    json.dumps(
                        {
                            "sub": reservation.custodian_id,
                            "role": "authenticated",
                            "is_anonymous": False,
                        }
                    ),
                ),
            )
            assert (
                db.execute("select count(*) from public.financial_accounts").fetchone()[0]
                == 0
            )
            with pytest.raises(psycopg.errors.InsufficientPrivilege), db.transaction():
                db.execute("select count(*) from public.messages")
    with pytest.raises(RuntimeError, match="auth_not_deleted"):
        writer.complete_identity_cleanup(
            space_id=w["space"], deletion_run_id=run, claim_id=token
        )
    lease = SenderLease(
        space_id=queued[1],
        sender_hash=queued[2],
        holder=queued[3],
        fence=queued[4],
        lease_until=queued[5],
    )
    stale = w["service"].execute(w["context"], queued[0], 0, lease=lease)
    assert stale.outcome in ("not_found", "permission_denied")
    w["objects"].delete(w["old"])
    with w["pool"].connection() as db:
        paths = db.execute(
            "select source_path,rebuilt_path from public.financial_document_extractions where connection_id=%s",
            (w["cid"],),
        ).fetchone()
        assert all(w["objects"].get(path) is not None for path in paths)
    FakeAuth().delete_user(w["old"])
    writer.complete_identity_cleanup(
        space_id=w["space"], deletion_run_id=run, claim_id=token
    )
    writer.complete_identity_cleanup(
        space_id=w["space"], deletion_run_id=run, claim_id=token
    )
    with w["pool"].connection() as db:
        assert (
            db.execute(
                "select count(*) from argus_private.business_custody_objects where space_id=%s and source_path is null",
                (w["space"],),
            ).fetchone()[0]
            == 3
        )
        assert db.execute(
            "select departing_user_id,claim_id from argus_private.business_custody_moves where space_id=%s",
            (w["space"],),
        ).fetchone() == (None, None)
        assert db.execute(
            "select count(*) from public.business_action_receipts where space_id=%s",
            (w["space"],),
        ).fetchone()[0] == len(rows)


def _closed_args(w):
    PostgresBusinessLifecycle(w["pool"]).close(
        owner_id=w["old"],
        space_id=w["space"],
        confirmation="Colmado",
        idempotency_key="close",
    )
    reservation = PostgresBusinessCustodyCopies(
        w["pool"], w["objects"], FakeAuth()
    ).prepare(space_id=w["space"], departing_user_id=w["old"])
    run, token = claim(w)
    return dict(
        space_id=w["space"],
        departing_user_id=w["old"],
        reservation=reservation,
        deletion_run_id=run,
        claim_id=token,
    )


@pytest.mark.owner_acts
def test_transfer_outbox_pii_is_removed_before_canonical_history_is_anonymized(custody):
    w = custody
    with w["pool"].connection() as db:
        db.execute(
            "update auth.users set email_confirmed_at=now() where id=any(%s::uuid[])",
            ([w["old"], w["users"]["other"]],),
        )
        target = db.execute(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities) values(%s,%s,%s,array['read','prepare']) returning id::text",
            (w["space"], w["users"]["other"], w["old"]),
        ).fetchone()[0]
    service = PostgresBusinessTransfer(w["pool"])
    transfer = service.request(
        owner_id=w["old"],
        space_id=w["space"],
        target_grant_id=target,
        confirmation="Colmado",
        idempotency_key="privacy-request",
    )
    service.decline(actor_id=w["users"]["other"], transfer_id=transfer.id)
    with w["pool"].connection() as db:
        assert "business_transfer_mail_outbox" in retained_dependencies(db, w["old"])
        assert (
            db.execute(
                "select count(*) from public.business_transfer_mail_outbox where transfer_id=%s",
                (transfer.id,),
            ).fetchone()[0]
            == 2
        )
        db.execute(
            "update public.business_transfer_mail_outbox set first_attempt_at=clock_timestamp(),payload=%s where transfer_id=%s",
            (
                Jsonb(
                    {
                        "html": "Synthetic departing member name and email",
                        "text": "Private recipient detail",
                        "subject": "Private",
                    }
                ),
                transfer.id,
            ),
        )
    args = _closed_args(w)
    PostgresBusinessCustodyGraph(w["pool"]).detach(**args)
    with w["pool"].connection() as db:
        assert not db.execute(
            "select 1 from public.business_transfer_mail_outbox where transfer_id=%s",
            (transfer.id,),
        ).fetchone()
        assert not retained_dependencies(db, w["old"])
        owner, target_id, status = db.execute(
            "select owner_id::text,target_id::text,status from public.business_ownership_transfers where id=%s",
            (transfer.id,),
        ).fetchone()
        assert owner == args["reservation"].deleted_actor_id
        assert target_id == w["users"]["other"] and status == "declined"


def _snapshot(w):
    with w["pool"].connection() as db:
        scope = PostgresBusinessCustodyGraph._scope(db, w["space"], w["old"], lock=False)
        rows = {}
        for table, predicate in FAMILIES.items():
            for name in (
                "records",
                "activities",
                "accounts",
                "connections",
                "events",
                "conversations",
            ):
                predicate = predicate.replace(
                    f"any(%({name})s)", f"any(%({name})s::uuid[])"
                )
            rows[table] = db.execute(
                f"select to_jsonb(t) from public.{table} t where {predicate} order by to_jsonb(t)::text",
                scope,
            ).fetchall()
        rows["space"] = db.execute(
            "select to_jsonb(s) from public.spaces s where id=%s", (w["space"],)
        ).fetchall()
        return rows


@pytest.mark.owner_acts
@pytest.mark.parametrize(
    "failure",
    [
        "missing_copy",
        "wrong_digest",
        "wrong_size",
        "wrong_destination",
        "unbanned_placeholder",
        "expired_claim",
        "cross_scope",
    ],
)
def test_failure_keeps_the_entire_saved_graph_and_old_objects(custody, failure):
    w = custody
    args = _closed_args(w)
    with w["pool"].connection() as db:
        if failure == "missing_copy":
            db.execute(
                "update argus_private.business_custody_objects set verified_at=null where space_id=%s",
                (w["space"],),
            )
        elif failure == "wrong_digest":
            db.execute(
                "update argus_private.business_custody_objects set sha256=%s where space_id=%s",
                ("0" * 64, w["space"]),
            )
        elif failure == "wrong_size":
            db.execute(
                "update argus_private.business_custody_objects set size_bytes=size_bytes+1 where space_id=%s",
                (w["space"],),
            )
        elif failure == "wrong_destination":
            db.execute(
                "update argus_private.business_custody_objects set destination_path='sealed/wrong-owner/fake' where space_id=%s",
                (w["space"],),
            )
        elif failure == "unbanned_placeholder":
            db.execute(
                "update auth.users set banned_until=null where id=%s",
                (args["reservation"].custodian_id,),
            )
        elif failure == "expired_claim":
            db.execute(
                "update argus_private.account_deletion_runs set claimed_until=clock_timestamp()-interval '1 second' where id=%s",
                (args["deletion_run_id"],),
            )
        elif failure == "cross_scope":
            foreign = str(uuid4())
            account = db.execute(
                "insert into public.financial_accounts(user_id,type,currency) values(%s,'cash','DOP') returning id",
                (w["old"],),
            ).fetchone()[0]
            db.execute(
                "insert into public.financial_records(id,user_id,account_id,record_kind) values(%s,%s,%s,'expense')",
                (foreign, w["old"], account),
            )
            db.execute(
                "insert into public.financial_record_revisions(record_id,user_id,revision,amount_minor,as_of,as_of_zone) values(%s,%s,1,100,now(),'UTC')",
                (foreign, w["old"]),
            )
            activity = db.execute(
                "select id from public.financial_activity_groups where user_id=%s limit 1",
                (w["old"],),
            ).fetchone()[0]
            db.execute(
                "insert into public.financial_activity_memberships(activity_id,user_id,activity_revision,record_id,record_revision,record_owner_id,role) values(%s,%s,1,%s,1,%s,'destination')",
                (activity, w["old"], foreign, w["old"]),
            )
    before = _snapshot(w)
    with pytest.raises(RuntimeError):
        PostgresBusinessCustodyGraph(w["pool"]).detach(**args)
    assert _snapshot(w) == before
    assert not w["objects"].erased
    assert FakeAuth().user_exists(w["old"])
    if failure == "missing_copy":
        PostgresBusinessCustodyCopies(w["pool"], w["objects"], FakeAuth()).prepare(
            space_id=w["space"], departing_user_id=w["old"]
        )
        assert PostgresBusinessCustodyGraph(w["pool"]).detach(**args).moved


@pytest.mark.owner_acts
def test_service_role_cannot_forge_a_deletion_writer(custody):
    w = custody
    args = _closed_args(w)
    with w["pool"].connection() as db:
        with db.transaction():
            db.execute("set local role service_role")
            db.execute(
                "select set_config('argus.business_custody_space',%s,true)", (w["space"],)
            )
            db.execute("select set_config('argus.locked_history_writer','deletion',true)")
            with pytest.raises(psycopg.errors.InsufficientPrivilege), db.transaction():
                db.execute(
                    "insert into argus_private.business_custody_changes(space_id,table_name,old_row,new_row) values(%s,'spaces','{}','{}')",
                    (w["space"],),
                )
            with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
                db.execute(
                    "update public.business_sources set text_content='changed fiscal source' where space_id=%s",
                    (w["space"],),
                )
    assert PostgresBusinessCustodyGraph(w["pool"]).detach(**args).moved


@pytest.mark.owner_acts
def test_shared_original_in_another_business_blocks_erase_until_both_move(custody):
    from tests.test_business_spaces_migration_postgres import connection

    w = custody
    args = _closed_args(w)
    other = str(uuid4())
    p2 = None
    with w["pool"].connection() as db:
        db.execute(
            "insert into public.spaces(id,kind,name,created_by,closed_at) values(%s,'business','Second Business',%s,now())",
            (other, w["old"]),
        )
        cid2 = connection(db, w["old"], other)
        db.execute(
            "insert into public.financial_document_extractions(connection_id,user_id,draft,source_bucket,source_path,source_media_type,source_size_bytes,source_sha256,rebuilt_bucket,rebuilt_path,rebuilt_media_type,rebuilt_size_bytes,rebuilt_sha256) select %s,user_id,jsonb_set(draft,'{connection_id}',to_jsonb(%s::text)),source_bucket,source_path,source_media_type,source_size_bytes,source_sha256,rebuilt_bucket,rebuilt_path,rebuilt_media_type,rebuilt_size_bytes,rebuilt_sha256 from public.financial_document_extractions where connection_id=%s",
            (cid2, cid2, w["cid"]),
        )
        before = db.execute(
            "select to_jsonb(d) from public.financial_document_extractions d where connection_id=%s",
            (cid2,),
        ).fetchone()[0]
    try:
        writer = PostgresBusinessCustodyGraph(w["pool"])
        assert writer.detach(**args).moved
        with w["pool"].connection() as db:
            assert (
                db.execute(
                    "select to_jsonb(d) from public.financial_document_extractions d where connection_id=%s",
                    (cid2,),
                ).fetchone()[0]
                == before
            )
            assert retained_dependencies(db, w["old"])
        second = PostgresBusinessCustodyCopies(
            w["pool"], w["objects"], FakeAuth()
        ).prepare(space_id=other, departing_user_id=w["old"])
        p2 = second.custodian_id
        assert second.custodian_id != args["reservation"].custodian_id
        assert second.deleted_actor_id != args["reservation"].deleted_actor_id
        assert writer.detach(**dict(args, space_id=other, reservation=second)).moved
        with w["pool"].connection() as db:
            assert not retained_dependencies(db, w["old"])
            paths = db.execute(
                "select source_path,source_sha256 from public.financial_document_extractions where connection_id=any(%s::uuid[]) order by connection_id",
                ([w["cid"], cid2],),
            ).fetchall()
        w["objects"].delete(w["old"])
        assert len({p for p, _ in paths}) == 2
        assert all(
            sha256(w["objects"].get(path)).hexdigest() == digest for path, digest in paths
        )
        FakeAuth().delete_user(w["old"])
        for s in (w["space"], other):
            writer.complete_identity_cleanup(
                space_id=s,
                deletion_run_id=args["deletion_run_id"],
                claim_id=args["claim_id"],
            )
    finally:
        with w["pool"].connection() as db:
            db.execute(
                "delete from argus_private.business_custody_changes where space_id=%s",
                (other,),
            )
            db.execute(
                "delete from argus_private.business_custody_moves where space_id=%s",
                (other,),
            )
            db.execute(
                "delete from argus_private.business_custody_objects where space_id=%s",
                (other,),
            )
            db.execute(
                "delete from argus_private.business_custody_reservations where space_id=%s",
                (other,),
            )
            db.execute("delete from public.spaces where id=%s", (other,))
            if p2:
                db.execute("delete from auth.users where id=%s", (p2,))
                db.execute(
                    "delete from argus_private.account_placeholders where id=%s", (p2,)
                )


@pytest.mark.owner_acts
def test_auth_delete_cannot_bypass_retained_business_history(custody):
    with pytest.raises(psycopg.errors.CheckViolation, match="detachment_required"):
        FakeAuth().delete_user(custody["old"])
    assert FakeAuth().user_exists(custody["old"])
    with custody["pool"].connection() as db:
        assert retained_dependencies(db, custody["old"])


@pytest.mark.owner_acts
@pytest.mark.parametrize("custody", ["inline"], indirect=True)
def test_legacy_inline_original_survives_account_delete(custody):
    w = custody
    args = _closed_args(w)
    writer = PostgresBusinessCustodyGraph(w["pool"])
    with w["pool"].connection() as db:
        before = db.execute(
            "select source_bytes,draft from public.financial_document_extractions where connection_id=%s",
            (w["cid"],),
        ).fetchone()
    assert writer.detach(**args).moved
    w["objects"].delete(w["old"])
    FakeAuth().delete_user(w["old"])
    writer.complete_identity_cleanup(
        space_id=w["space"],
        deletion_run_id=args["deletion_run_id"],
        claim_id=args["claim_id"],
    )
    with w["pool"].connection() as db:
        after = db.execute(
            "select source_bytes,draft from public.financial_document_extractions where connection_id=%s",
            (w["cid"],),
        ).fetchone()
        assert before == after
        assert sha256(bytes(after[0])).hexdigest() == after[1]["sha256"]
