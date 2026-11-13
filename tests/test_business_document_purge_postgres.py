from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

import psycopg
import pytest
from argus.api.business_drafts import receipt_summaries
from argus.api.business_receipt_activity import counts
from argus.api.documents import configure_documents
from argus.domain.business.actions.document_purge import DocumentExpiry, erase
from argus.domain.business.activity.queries import read_activity
from argus.domain.business.authority import ActionError, authorize
from argus.domain.business.contracts.activity import ActivityFilters
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.contracts.deletion import PURGE_AFTER, DeletedDocument
from argus.domain.business.transactions import record_legacy_action
from argus.domain.ingestion.documents.objects import InMemorySourceObjects

from tests import test_business_actions_postgres as shared
from tests import test_business_document_delete_postgres as deleting
from tests.document_sources_support import source_objects

users = shared.users
actions = shared.actions
pytestmark = [shared.pytestmark, pytest.mark.owner_acts]


@pytest.fixture
def live_objects():
    yield
    configure_documents(None)


def _deleted(actions, prepared: bool):
    service, context, cid, draft_id, web = (
        deleting._ready if prepared else deleting._unread
    )(actions)
    client = deleting._client(service, context)
    target = draft_id or cid
    assert deleting._act(client, target, "delete").status_code == 200
    return service, context, cid, draft_id, web, client, target


def _marker(web, cid: str) -> DeletedDocument:
    [row] = [row for row in receipt_summaries(web, "all") if row["id"] == cid]
    return DeletedDocument.model_validate(row["deleted"])


def _paths(db, cid: str) -> list[str]:
    row = db.execute(
        "select source_path,rebuilt_path from public.financial_document_extractions where connection_id=%s",
        (cid,),
    ).fetchone()
    return [path for path in row if path]


def _remaining(db, space, cid, draft_id) -> dict[str, int]:
    ids = [str(cid), *([str(draft_id)] if draft_id else [])]
    queries = {
        "uploads": "select count(*) from public.financial_source_connections where id=any(%s::uuid[])",
        "reads": "select count(*) from public.financial_document_extractions where connection_id=any(%s::uuid[])",
        "drafts": "select count(*) from public.financial_import_events where id=any(%s::uuid[])",
        "revisions": "select count(*) from public.business_draft_revisions where draft_id=any(%s::uuid[])",
        "sources": "select count(*) from public.business_sources where connection_id=any(%s::uuid[])",
        "links": "select count(*) from public.business_draft_sources where draft_id=any(%s::uuid[])",
    }
    return {name: db.execute(query, (ids,)).fetchone()[0] for name, query in queries.items()}


def _purges(service, context, action: str) -> list:
    feed = read_activity(service.authority, context, limit=25, filters=ActivityFilters())
    return [item for item in feed.items if item.action == action]


@pytest.mark.parametrize("prepared", [False, True])
def test_owner_purge_removes_the_document_and_keeps_one_nameless_entry(
    actions, prepared, live_objects
):
    service, context, cid, draft_id, web, client, target = _deleted(actions, prepared)
    configure_documents(web.service.documents)
    with service.authority.pool.connection() as db:
        paths = _paths(db, cid)
        live = authorize(db, context.actor, context.grant_id)
        record_legacy_action(db, live, "receipt_upload", [str(cid)], str(uuid4()))
    assert all(source_objects().get(path) for path in paths)
    assert paths or prepared
    key = str(uuid4())

    purged = deleting._act(client, target, "purge", key)

    assert purged.status_code == 200, purged.text
    assert purged.json() == {"document_id": str(target), "deleted": True}
    assert deleting._act(client, target, "purge", key).json() == purged.json()
    with service.authority.pool.connection() as db:
        assert set(_remaining(db, context.actor.space_id, cid, draft_id).values()) == {0}
        assert db.execute(
            "select reason,pending_objects from argus_private.business_document_purges where space_id=%s",
            (context.actor.space_id,),
        ).fetchall() == [("owner", [])]
    assert all(source_objects().get(path) is None for path in paths)
    assert cid not in {row["id"] for row in receipt_summaries(web, "all")}
    assert counts(web, receipt_summaries(web, "all"))["bandeja_eliminados_count"] == 0
    [entry] = _purges(service, context, "purge_document")
    assert entry.object is None and entry.actor.kind == "member"
    feed = read_activity(service.authority, context, limit=25, filters=ActivityFilters())
    older = [item for item in feed.items if item.action != "purge_document"]
    assert {"receipt_upload", "delete_document"} <= {item.action for item in older}
    named = [item.object for item in older if item.object is not None]
    assert {item.action for item in older if item.object is not None} >= {"delete_document"}
    for gone in named:
        assert gone.model_dump(mode="json") == {
            "kind": gone.kind,
            "id": str(gone.id),
            "label": None,
            "purged": True,
        }
    again = deleting._act(client, target, "purge")
    assert (again.status_code, again.json()) == (200, purged.json())
    assert len(_purges(service, context, "purge_document")) == 1


def test_purged_document_is_not_found_and_cannot_be_restored(actions):
    service, context, cid, draft_id, web, client, target = _deleted(actions, True)
    assert deleting._act(client, target, "purge").status_code == 200
    for action in ("restore", "delete"):
        refused = deleting._act(client, target, action)
        assert (refused.status_code, refused.json()["code"]) == (
            404,
            "business_document_purged",
        ), refused.text
    refused = deleting._act(client, cid, "restore")
    assert refused.json()["code"] == "business_document_purged"
    with pytest.raises(ActionError) as missing:
        service.dossier(context, draft_id)
    assert missing.value.code == "business_record_not_found"
    stale = client.get(f"/api/v1/business/drafts/{draft_id}/dossier")
    assert (stale.status_code, stale.json()["code"]) == (404, "business_record_not_found")
    with pytest.raises(Exception) as gone:
        web.service.receipt(web.scope, cid)
    assert "NotFound" in type(gone.value).__name__


def test_purge_needs_a_deleted_document_and_the_owner(actions, users):
    service, context, cid, draft_id, web = deleting._ready(actions)
    client = deleting._client(service, context)
    refused = deleting._act(client, draft_id, "purge")
    assert (refused.status_code, refused.json()["code"]) == (
        422,
        "business_document_not_deleted",
    )
    assert deleting._act(client, draft_id, "delete").status_code == 200
    with service.authority.pool.connection() as db:
        db.execute(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,business_role,capabilities) values(%s,%s,%s,'admin',%s)",
            (context.actor.space_id, users["other"], context.owner_id, ["read", "prepare"]),
        )
    admin = service.resolve_actor(
        TrustedActor(
            actor_id=users["other"], actor_kind="member", space_id=context.actor.space_id
        )
    )
    refused = deleting._act(deleting._client(service, admin), draft_id, "purge")
    assert (refused.status_code, refused.json()["code"]) == (
        403,
        "business_permission_denied",
    )
    assert _marker(web, cid) is not None


@pytest.mark.parametrize("prepared", [False, True])
def test_expiry_purges_on_day_seven_and_a_restore_before_keeps_it(actions, prepared):
    service, context, cid, draft_id, web, client, target = _deleted(actions, prepared)
    at = _marker(web, cid).at
    expiry = DocumentExpiry(service.authority.pool, source_objects(), every=timedelta(hours=1))

    # A run purges every due document in the database, so each check reads
    # this document's own rows rather than the run's totals.
    expiry.run(at + PURGE_AFTER - timedelta(minutes=1))
    assert _marker(web, cid) is not None
    assert deleting._act(client, target, "restore").status_code == 200
    expiry.run(at + PURGE_AFTER * 2)
    with service.authority.pool.connection() as db:
        assert _remaining(db, context.actor.space_id, cid, draft_id)["uploads"] == 1
    assert deleting._act(client, target, "delete").status_code == 200
    again = _marker(web, cid).at

    expiry.run(again + PURGE_AFTER)

    with service.authority.pool.connection() as db:
        assert set(_remaining(db, context.actor.space_id, cid, draft_id).values()) == {0}
    [entry] = _purges(service, context, "expire_document")
    assert entry.object is None and entry.actor.kind == "extractor"
    assert entry.occurred_at >= again
    assert _purges(service, context, "purge_document") == []
    refused = deleting._act(client, target, "restore")
    assert refused.json()["code"] == "business_document_purged"
    late = deleting._act(client, target, "purge")
    assert late.status_code == 200
    assert _purges(service, context, "purge_document") == []


def test_a_failed_erase_is_finished_by_the_next_run(actions, live_objects):
    service, context, cid, draft_id, web, client, target = _deleted(actions, False)
    shared_objects = source_objects()

    class Refusing(InMemorySourceObjects):
        def remove(self, path: str) -> None:
            raise RuntimeError("storage down")

    configure_documents(web.service.documents)
    web.service.documents.store.objects = Refusing()
    with service.authority.pool.connection() as db:
        paths = _paths(db, cid)

    assert deleting._act(client, target, "purge").status_code == 200

    with service.authority.pool.connection() as db:
        assert set(_remaining(db, context.actor.space_id, cid, draft_id).values()) == {0}
        [(pending,)] = db.execute(
            "select pending_objects from argus_private.business_document_purges where space_id=%s",
            (context.actor.space_id,),
        ).fetchall()
    assert paths and set(paths) <= set(pending)
    assert all(shared_objects.get(path) for path in paths)
    assert cid not in {row["id"] for row in receipt_summaries(web, "all")}

    run = DocumentExpiry(service.authority.pool, shared_objects, every=timedelta(hours=1))
    assert run.run(_marker_free_now())["left"] == 0

    assert all(shared_objects.get(path) is None for path in paths)
    assert erase(service.authority.pool, shared_objects, context.actor.space_id) == 0


def _marker_free_now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def test_shared_bytes_stay_for_the_other_document(actions):
    import asyncio
    from pathlib import Path

    service, context, cid, draft_id, web, client, target = _deleted(actions, False)
    other = asyncio.run(
        web.service.upload(
            web.scope,
            content=Path("tests/document_extraction_fixtures/hotel-ecf.pdf").read_bytes(),
            filename="otro.pdf",
            media_type="application/pdf",
            consent=False,
        )
    )
    with service.authority.pool.connection() as db:
        [path] = _paths(db, cid)
        db.execute(
            "update public.financial_document_extractions o set source_path=d.source_path,"
            "source_sha256=d.source_sha256,source_size_bytes=d.source_size_bytes,"
            "source_media_type=d.source_media_type from public.financial_document_extractions d"
            " where d.connection_id=%s and o.connection_id=%s",
            (cid, other.id),
        )
    assert deleting._act(client, target, "purge").status_code == 200
    assert erase(service.authority.pool, source_objects(), context.actor.space_id) == 0
    assert source_objects().get(path) is not None


def test_message_draft_purge_removes_its_text_and_revisions(actions):
    service, context, _ = actions
    draft_id, _ = shared.create(service, context)
    client = deleting._client(service, context)
    with service.authority.pool.connection() as db:
        sources = [
            row[0]
            for row in db.execute(
                "select source_id from public.business_draft_sources where draft_id=%s",
                (draft_id,),
            ).fetchall()
        ]
    assert sources
    assert deleting._act(client, draft_id, "delete").status_code == 200
    assert deleting._act(client, draft_id, "purge").status_code == 200
    with service.authority.pool.connection() as db:
        assert db.execute(
            "select count(*) from public.business_sources where id=any(%s::uuid[])",
            (sources,),
        ).fetchone()[0] == 0
        assert db.execute(
            "select count(*) from public.business_draft_revisions where draft_id=%s",
            (draft_id,),
        ).fetchone()[0] == 0
    assert service.captures_page(context, view="eliminados")["items"] == []


def test_evidence_stays_immutable_outside_a_purge(actions):
    service, context, _ = actions
    draft_id, _ = shared.create(service, context)
    with service.authority.pool.connection() as db:
        source = db.execute(
            "select source_id from public.business_draft_sources where draft_id=%s",
            (draft_id,),
        ).fetchone()[0]
        with pytest.raises(psycopg.errors.CheckViolation):
            db.execute("delete from public.business_sources where id=%s", (source,))
    with service.authority.pool.connection() as db, db.transaction():
        db.execute(
            "select set_config('argus.business_document_purge_space',%s,true)",
            (str(uuid4()),),
        )
        with pytest.raises(psycopg.errors.CheckViolation):
            db.execute("delete from public.business_sources where id=%s", (source,))
    with service.authority.pool.connection() as db, db.transaction():
        db.execute(
            "select set_config('argus.business_document_purge_space',%s,true)",
            (str(context.actor.space_id),),
        )
        with pytest.raises(psycopg.errors.CheckViolation):
            db.execute(
                "update public.business_sources set text_content='x' where id=%s",
                (source,),
            )


@pytest.mark.parametrize("role", ["anon", "authenticated"])
@pytest.mark.parametrize(
    "statement",
    [
        "select * from argus_private.business_document_purges",
        "delete from argus_private.business_document_purges",
        "insert into argus_private.business_document_purges(space_id,document_ids,reason)"
        " select id,array[id],'owner' from public.spaces limit 1",
    ],
)
def test_purge_records_are_closed_to_api_roles(actions, role, statement):
    service, _, _ = actions
    with service.authority.pool.connection() as db, db.transaction():
        db.execute(f"set local role {role}")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            db.execute(statement)
        raise psycopg.Rollback()


def test_expiry_query_reads_the_partial_indexes(actions):
    service, _, _ = actions
    with service.authority.pool.connection() as db:
        db.execute("set enable_seqscan=off")
        plans = [
            "\n".join(
                row[0]
                for row in db.execute(f"explain select 1 from {query}").fetchall()
            )
            for query in (
                "public.financial_import_events e where e.state='dismissed' and e.resolution ? 'deleted'",
                "public.financial_document_extractions d where (d.draft->>'status')='dismissed' and (d.draft->'resolution') ? 'deleted'",
            )
        ]
    assert "financial_import_events_deleted_idx" in plans[0]
    assert "financial_document_extractions_deleted_idx" in plans[1]


def test_purge_records_are_one_owner_of_the_purged_ids(actions):
    service, context, cid, draft_id, web, client, target = _deleted(actions, True)
    assert deleting._act(client, target, "purge").status_code == 200
    with service.authority.pool.connection() as db:
        [(ids,)] = db.execute(
            "select document_ids from argus_private.business_document_purges where space_id=%s",
            (context.actor.space_id,),
        ).fetchall()
    assert {UUID(str(cid)), UUID(str(draft_id))} <= set(ids)


def test_the_button_and_the_expiry_racing_end_in_one_purge(actions):
    from concurrent.futures import ThreadPoolExecutor

    service, context, cid, draft_id, web, client, target = _deleted(actions, False)
    at = _marker(web, cid).at
    expiry = DocumentExpiry(service.authority.pool, source_objects(), every=timedelta(hours=1))
    with ThreadPoolExecutor(max_workers=2) as pool:
        pressed = pool.submit(deleting._act, client, target, "purge")
        expired = pool.submit(expiry.run, at + PURGE_AFTER)
        assert pressed.result().status_code == 200, pressed.result().text
        assert expired.result()["failed"] == 0
    with service.authority.pool.connection() as db:
        assert db.execute(
            "select count(*) from argus_private.business_document_purges where space_id=%s",
            (context.actor.space_id,),
        ).fetchone()[0] == 1
        assert set(_remaining(db, context.actor.space_id, cid, draft_id).values()) == {0}
    def entries():
        return _purges(service, context, "purge_document") + _purges(
            service, context, "expire_document"
        )

    assert len(entries()) == 1
    expiry.run(at + PURGE_AFTER * 2)
    assert len(entries()) == 1
