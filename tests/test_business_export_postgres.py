import io
import json
from dataclasses import replace
from datetime import date, datetime, timezone
from uuid import UUID, uuid4
from zipfile import ZipFile

import pytest
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.actions import (
    ApproveExpense,
    ProposeActivity,
    ReviewDraft,
)
from argus.domain.business.contracts.dossier import AttachmentSource
from argus.domain.business.contracts.facts import BusinessFactPatch
from argus.domain.business.export import ExportPeriod, export_package
from argus.domain.ingestion.documents.models import DocumentDraft
from argus.domain.ingestion.documents.objects import InMemorySourceObjects
from argus.domain.ingestion.documents.store_postgres import PostgresDocumentStore

from tests import test_business_actions_postgres as shared
from tests.test_business_spaces_migration_postgres import connection

users = shared.users
actions = shared.actions
pytestmark = shared.pytestmark
PERIOD = ExportPeriod(date(2026, 10, 1), date(2026, 10, 31))


def unpack(content):
    with ZipFile(io.BytesIO(content)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


@pytest.mark.owner_acts
def test_read_only_export_uses_canonical_owner_funds_and_exact_sources(actions):
    service, context, _ = actions
    draft, version = shared.create(service, context)
    facts = BusinessFactPatch.model_validate(
        {
            name: {"state": "known", "value": value}
            for name, value in {
                "kind": "expense",
                "amount": "850",
                "currency": "DOP",
                "occurred_on": "2026-10-01",
                "funding": {"kind": "owner_funds"},
                "business_share": {"kind": "all"},
            }.items()
        }
    )
    assert (
        service.review(
            context, draft, ReviewDraft(version=version, facts=facts), "review"
        ).outcome
        == "applied"
    )
    approved = service.approve(
        context,
        draft,
        ApproveExpense(version=version + 1, action="record_expense"),
        "approve",
    )
    assert approved.outcome == "applied"
    before = service.dossier(context, draft)
    files = unpack(
        export_package(service.authority, context, PERIOD, InMemorySourceObjects())
    )
    manifest = json.loads(files["manifest.json"])
    assert len(manifest["records"]) == 1
    row = manifest["records"][0]
    assert (
        row["kind"],
        row["funding"],
        row["amount"],
        row["currency"],
        row["account_ids"],
    ) == ("expense", "owner_funds", "850.00", "DOP", "")
    assert row["draft_ids"] == str(draft)
    assert manifest["unresolved_drafts"] == []
    assert set(row["source_ids"].split(";")) == {
        str(source.id) for source in before.sources
    }
    assert service.dossier(context, draft) == before
    assert export_package(service.authority, context, PERIOD, InMemorySourceObjects())


def test_unknown_date_stays_outside_recorded_money_and_keeps_original(actions):
    service, context, _ = actions
    draft, _ = shared.create(service, context)
    files = unpack(
        export_package(service.authority, context, PERIOD, InMemorySourceObjects())
    )
    manifest = json.loads(files["manifest.json"])
    assert manifest["records"] == []
    assert manifest["unresolved_drafts"] == [
        {
            "draft_id": str(draft),
            "version": 1,
            "review_state": "open",
            "occurred_on": None,
            "reason": "date_unknown",
        }
    ]
    assert files[manifest["sources"][0]["file"]] == b"Paid 850 pesos"


def test_live_read_grant_required_and_no_foreign_owner_substitution(actions, users):
    service, context, grant = actions
    shared.create(service, context)
    with pytest.raises(ActionError, match="business_record_not_found"):
        export_package(
            service.authority,
            replace(context, owner_id=users["other"]),
            PERIOD,
            InMemorySourceObjects(),
        )
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.business_client_grants set capabilities=ARRAY['read'] where id=%s",
            (grant,),
        )
    assert export_package(service.authority, context, PERIOD, InMemorySourceObjects())
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.business_client_grants set revoked_at=now() where id=%s",
            (grant,),
        )
    with pytest.raises(ActionError, match="business_record_not_found"):
        export_package(service.authority, context, PERIOD, InMemorySourceObjects())


@pytest.fixture
def attachment(actions):
    import hashlib

    service, context, _ = actions
    with service.authority.pool.connection() as db:
        receipt = connection(db, context.owner_id, str(context.actor.space_id))
    content = b"%PDF-1.7 synthetic original\x00\xff"
    objects = InMemorySourceObjects()
    store = PostgresDocumentStore(service.authority.pool, objects)
    now = datetime.now(timezone.utc)
    assert store.capture(
        user_id=context.owner_id,
        draft=DocumentDraft(
            connection_id=receipt,
            filename="../original.pdf",
            media_type="application/pdf",
            sha256=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
            created_at=now,
            updated_at=now,
        ),
        content=content,
    )
    source_id = service.record_source(
        context,
        "attachment",
        AttachmentSource(
            id=uuid4(),
            channel="web",
            received_at=now,
            connection_id=UUID(receipt),
            filename="../original.pdf",
            media_type="application/pdf",
        ),
    )
    key, lease = shared.prepare(
        service,
        context,
        [
            ProposeActivity(
                facts=BusinessFactPatch(amount={"state": "unknown"}),
                source_ids=(source_id,),
            )
        ],
    )
    assert service.execute(context, key, 0, lease=lease).outcome == "applied"
    rebuilt = b"%PDF-1.7 rebuilt fixture"
    assert store.save_rebuilt(
        user_id=context.owner_id,
        connection_id=receipt,
        content=rebuilt,
        media_type="application/pdf",
    )
    return objects, source_id, rebuilt


@pytest.mark.parametrize("available", [True, False])
def test_canonical_attachment_rebuilt_or_individual_unavailability(
    actions, attachment, available
):
    service, context, _ = actions
    objects, source_id, content = attachment
    if not available:
        objects.objects.clear()
    files = unpack(export_package(service.authority, context, PERIOD, objects))
    manifest = json.loads(files["manifest.json"])
    source = manifest["sources"][0]
    assert source["availability"] == ("included" if available else "unavailable")
    if available:
        assert files[source["file"]] == content
        assert source["file"] == f"originals/{source_id}.pdf"
    else:
        assert source["file"] is None and not manifest["evidence_complete"]


@pytest.mark.parametrize("boundary", ["source", "release"])
def test_authorization_failure_aborts_instead_of_becoming_missing_evidence(
    actions, attachment, monkeypatch, boundary
):
    from argus.domain.business import authority

    service, context, _ = actions
    objects, _, _ = attachment
    original = authority.authorize
    count = 0

    def recheck(db, actor, grant_id=None):
        nonlocal count
        count += 1
        assert grant_id == context.grant_id
        if count == (2 if boundary == "source" else 3):
            raise ActionError("not_found", "business_record_not_found")
        return original(db, actor, grant_id)

    monkeypatch.setattr(authority, "authorize", recheck)
    with pytest.raises(ActionError, match="business_record_not_found"):
        export_package(service.authority, context, PERIOD, objects)
    assert count == (2 if boundary == "source" else 3)


def test_real_clock_grant_expiry_before_release_refuses_package(
    actions, attachment, monkeypatch
):
    import time

    service, context, grant = actions
    objects, _, _ = attachment
    with service.authority.pool.connection() as db:
        expiry = db.execute(
            "update public.business_client_grants set expires_at=clock_timestamp()+interval '2 seconds' where id=%s returning expires_at",
            (grant,),
        ).fetchone()[0]
    original = objects.get

    def delayed(path):
        content = original(path)
        time.sleep(max(0, (expiry - datetime.now(timezone.utc)).total_seconds()) + 0.1)
        return content

    monkeypatch.setattr(objects, "get", delayed)
    with pytest.raises(ActionError, match="business_record_not_found"):
        export_package(service.authority, context, PERIOD, objects)


def test_actual_export_api_read_only_accountant_anchor_and_no_fallback(actions, users):
    from types import SimpleNamespace

    from argus.api.business import BusinessPerson, require_business_person
    from argus.api.business_drafts import DraftContext, require_drafts
    from argus.api.documents import require_saved_documents
    from argus.api.routers.business_export import router
    from argus.domain.business.spaces import PostgresSpaceStore
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    service, context, grant = actions
    draft, _ = shared.create(service, context)
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.business_client_grants set capabilities=ARRAY['read'] where id=%s",
            (grant,),
        )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_drafts] = lambda: DraftContext(
        service, context.actor.actor_id
    )
    app.dependency_overrides[require_business_person] = lambda: BusinessPerson(
        str(context.actor.actor_id), PostgresSpaceStore(service.authority.pool)
    )
    app.dependency_overrides[require_saved_documents] = lambda: SimpleNamespace(
        store=SimpleNamespace(objects=InMemorySourceObjects())
    )

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = "export-pg"
        return await call_next(request)

    query = "start=2026-10-01&end=2026-10-31"
    with TestClient(app) as client:
        assert client.get(f"/business/exports?{query}").status_code == 404
        result = client.get(f"/business/exports?{query}&draft_id={draft}")
        assert result.status_code == 200
        manifest = json.loads(unpack(result.content)["manifest.json"])
        assert manifest["unresolved_drafts"][0]["draft_id"] == str(draft)
        assert (
            client.get(f"/business/exports?{query}&draft_id={uuid4()}").status_code == 404
        )
        with service.authority.pool.connection() as db:
            db.execute(
                "update public.business_client_grants set revoked_at=now() where id=%s",
                (grant,),
            )
        denied = client.get(f"/business/exports?{query}&draft_id={draft}")
        assert denied.status_code == 404 and denied.headers["cache-control"] == "no-store"
        assert not denied.content.startswith(b"PK")


def test_foreign_business_draft_and_source_never_enter_export(actions, users):
    from argus.domain.business.contracts.authority import TrustedActor

    from tests.test_business_spaces_migration_postgres import space

    service, context, _ = actions
    local, _ = shared.create(service, context)
    with service.authority.pool.connection() as db:
        foreign_space = space(db, users["other"])
        db.execute(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities) values(%s,%s,%s,ARRAY['read','prepare'])",
            (foreign_space, users["owner"], users["other"]),
        )
    foreign = service.resolve_actor(
        TrustedActor(actor_id=users["owner"], actor_kind="member", space_id=foreign_space)
    )
    foreign_draft, _ = shared.create(service, foreign)
    foreign_source = service.dossier(foreign, foreign_draft).sources[0].id
    with pytest.raises(ActionError, match="business_record_not_found"):
        service.context_for_draft(context.actor.actor_id, foreign_draft)
    content = export_package(service.authority, context, PERIOD, InMemorySourceObjects())
    manifest = json.loads(unpack(content)["manifest.json"])
    assert [row["draft_id"] for row in manifest["unresolved_drafts"]] == [str(local)]
    assert str(foreign_draft) not in json.dumps(manifest)
    assert str(foreign_source) not in json.dumps(manifest)


def test_revocation_waits_for_snapshot_grant_lock(actions, attachment, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from psycopg.errors import LockNotAvailable

    service, context, grant = actions
    objects, _, _ = attachment
    reading, release = Event(), Event()
    original = objects.get

    def held(path):
        reading.set()
        assert release.wait(5)
        return original(path)

    monkeypatch.setattr(objects, "get", held)
    with ThreadPoolExecutor(max_workers=1) as worker:
        exporting = worker.submit(
            export_package, service.authority, context, PERIOD, objects
        )
        try:
            assert reading.wait(5)
            with service.authority.pool.connection() as db:
                with pytest.raises(LockNotAvailable), db.transaction():
                    db.execute("set local lock_timeout='100ms'")
                    db.execute(
                        "update public.business_client_grants set revoked_at=now() where id=%s",
                        (grant,),
                    )
        finally:
            release.set()
        assert exporting.result(timeout=5).startswith(b"PK")
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.business_client_grants set revoked_at=now() where id=%s",
            (grant,),
        )
    with pytest.raises(ActionError, match="business_record_not_found"):
        export_package(service.authority, context, PERIOD, objects)


def test_export_never_falls_back_to_a_retained_original(actions, attachment):
    service, context, _ = actions
    objects, _, _ = attachment
    for path in list(objects.objects):
        if path.startswith("rebuilt/"):
            del objects.objects[path]
    assert any(path.startswith("sealed/") for path in objects.objects)
    files = unpack(export_package(service.authority, context, PERIOD, objects))
    manifest = json.loads(files["manifest.json"])
    source = manifest["sources"][0]
    assert source["availability"] == "unavailable"
    assert source["file"] is None
    assert not manifest["evidence_complete"]
    assert not any(name.startswith("originals/") for name in files)
