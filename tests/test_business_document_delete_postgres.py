from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
from argus.api.business_drafts import (
    DraftContext,
    overview_with_drafts,
    receipt_detail,
    receipt_summaries,
    require_drafts,
)
from argus.api.business_receipt_activity import counts, unreviewed_days
from argus.api.routers.business_drafts import router
from argus.domain.business.activity.queries import read_activity
from argus.domain.business.contracts.activity import ActivityFilters
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.contracts.deletion import DeletedDocument
from argus.domain.business.transactions import transaction
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests import test_business_actions_postgres as shared
from tests import test_business_receipt_activity_postgres as receipts
from tests.business.test_business_api import RECEIPT

users = shared.users
actions = shared.actions
pytestmark = [shared.pytestmark, pytest.mark.owner_acts]


def _client(service, context):
    from argus.api.app_setup import add_core_middleware_and_handlers

    app = FastAPI()
    add_core_middleware_and_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[require_drafts] = lambda: DraftContext(
        service, context.actor.actor_id, str(context.actor.space_id), context.grant_id
    )
    return TestClient(app)


def _act(client, document_id, action, key=None):
    return client.post(
        f"/api/v1/business/drafts/{document_id}/{action}",
        json={},
        headers={"Idempotency-Key": key or str(uuid4())},
    )


def _ready(actions):
    service, context, cid, draft, web = receipts.ready(actions)
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.financial_source_connections set lease_until=null,lease_holder=null where id=%s",
            (cid,),
        )
    return service, context, cid, draft, web


def _unread(actions):
    from tests.test_business_receipt_views_postgres import _web

    service, context, _ = actions
    web = _web(service, context)
    receipt = asyncio.run(
        web.service.upload(
            web.scope,
            content=RECEIPT,
            filename="documento.png",
            media_type="image/png",
            consent=False,
        )
    )
    return service, context, receipt.id, None, web


def _captured_purchase(service, context, *, approve=False):
    from argus.domain.business.contracts.actions import (
        ApproveExpense,
        CaptureNote,
        ReviewDraft,
    )
    from argus.domain.business.contracts.facts import BusinessFactPatch

    created = service.capture(
        context, CaptureNote(text="Compra independiente"), str(uuid4())
    )
    assert created.outcome == "applied"
    reviewed = service.review(
        context,
        created.draft_id,
        ReviewDraft(
            version=created.version,
            facts=BusinessFactPatch.model_validate(
                {
                    name: {"state": "known", "value": value}
                    for name, value in {
                        "kind": "expense",
                        "amount": "800.50",
                        "currency": "DOP",
                        "occurred_on": "2026-09-03",
                        "counterparty": "Compra independiente",
                    }.items()
                }
            ),
        ),
        str(uuid4()),
    )
    assert reviewed.outcome == "applied"
    if approve:
        approved = service.approve(
            context,
            created.draft_id,
            ApproveExpense(
                action="record_expense",
                version=reviewed.version,
                approve_anyway=True,
            ),
            str(uuid4()),
        )
        assert approved.outcome == "applied", approved
    return created.draft_id


@pytest.mark.parametrize("prepared", [False, True])
def test_owner_delete_restore_counts_history_and_exact_replay(actions, prepared):
    from datetime import date

    service, context, cid, draft_id, web = (_ready if prepared else _unread)(actions)
    _captured_purchase(service, context, approve=True)
    client = _client(service, context)
    target = draft_id or cid
    before = receipt_detail(web, web.service.receipt(web.scope, cid))
    before_rows = receipt_summaries(web, "all")
    before_counts = counts(web, before_rows)
    before_days = unreviewed_days(web, before_rows)
    before_home = overview_with_drafts(web, date(2026, 1, 1), date(2026, 12, 31))
    before_money = web.service.expenses(web.scope, date(2026, 1, 1), date(2026, 12, 31))
    assert before_money and before_home["totals"]
    assert before["delete_available"] is True
    key = str(uuid4())
    deleted = _act(client, target, "delete", key)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"document_id": str(target), "deleted": True}
    assert _act(client, target, "delete", key).json() == deleted.json()
    rows = receipt_summaries(web, "all")
    [view] = [row for row in rows if row["id"] == cid]
    marker = DeletedDocument.model_validate(view["deleted"])
    assert marker.actor.id == context.actor.actor_id
    assert marker.previous_state.group == before["bandeja_group"]["group"]
    assert view["status"] == "dismissed"
    assert view["bandeja_group"]["group"] == "eliminados"
    assert view["restore_available"] and not view["delete_available"]
    assert not view["preparable"] and not view["enterable"]
    assert cid not in {row["id"] for row in receipt_summaries(web, "inbox")}
    assert (
        counts(web, rows)["pending_review_count"]
        == before_counts["pending_review_count"] - 1
    )
    assert counts(web, rows)["bandeja_eliminados_count"] == 1
    assert len(unreviewed_days(web, rows)) == len(before_days) - 1
    home = overview_with_drafts(web, date(2026, 1, 1), date(2026, 12, 31))
    assert (
        home["awaiting_review"] + home["needs_attention"]
        == before_home["awaiting_review"] + before_home["needs_attention"] - 1
    )
    assert home["totals"] == before_home["totals"]
    assert (
        web.service.expenses(web.scope, date(2026, 1, 1), date(2026, 12, 31))
        == before_money
    )
    restore_key = str(uuid4())
    restored = _act(client, target, "restore", restore_key)
    assert restored.status_code == 200, restored.text
    assert _act(client, target, "restore", restore_key).json() == restored.json()
    after = receipt_detail(web, web.service.receipt(web.scope, cid))
    assert after["deleted"] is None
    assert after["status"] == before["status"]
    assert after["bandeja_group"]["group"] == before["bandeja_group"]["group"]
    for name in ("merchant", "amount", "currency", "occurred_on", "evidence", "filename"):
        assert after[name] == before[name]
    assert (
        counts(web, receipt_summaries(web, "all"))["pending_review_count"]
        == before_counts["pending_review_count"]
    )
    assert unreviewed_days(web, receipt_summaries(web, "all")) == before_days
    assert (
        web.service.expenses(web.scope, date(2026, 1, 1), date(2026, 12, 31))
        == before_money
    )
    assert (
        overview_with_drafts(web, date(2026, 1, 1), date(2026, 12, 31))["totals"]
        == before_home["totals"]
    )
    feed = read_activity(service.authority, context, limit=25, filters=ActivityFilters())
    changes = [
        item
        for item in feed.items
        if item.action in ("delete_document", "restore_document")
    ]
    assert [item.action for item in changes] == ["restore_document", "delete_document"]
    assert all(item.object is not None and item.object.label for item in changes)
    with service.authority.pool.connection() as db:
        assert (
            db.execute(
                "select count(*) from public.business_action_receipts where space_id=%s and command->>'action' in ('delete_document','restore_document')",
                (context.actor.space_id,),
            ).fetchone()[0]
            == 2
        )


@pytest.mark.parametrize("role", ["admin", "editor", "viewer"])
@pytest.mark.parametrize("prepared", [False, True])
def test_only_owner_can_delete_or_restore(actions, users, role, prepared):
    service, context, cid, draft_id, web = (_ready if prepared else _unread)(actions)
    capabilities = ["read"] if role == "viewer" else ["read", "prepare"]
    with service.authority.pool.connection() as db:
        db.execute(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,business_role,capabilities) values(%s,%s,%s,%s,%s)",
            (
                context.actor.space_id,
                users["other"],
                context.owner_id,
                role,
                capabilities,
            ),
        )
    other = service.resolve_actor(
        TrustedActor(
            actor_id=users["other"], actor_kind="member", space_id=context.actor.space_id
        )
    )
    client = _client(service, other)
    for action in ("delete", "restore"):
        refused = _act(client, draft_id or cid, action)
        assert (refused.status_code, refused.json()["code"]) == (
            403,
            "business_permission_denied",
        )
    assert receipt_detail(web, web.service.receipt(web.scope, cid))["deleted"] is None
    if prepared:
        view = service.dossier(other, draft_id)
        assert not view.delete_available and not view.restore_available


@pytest.mark.parametrize("status", ["preparing"])
def test_reading_document_cannot_be_deleted(actions, status):
    service, context, cid, _, _ = _unread(actions)
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.financial_document_extractions set draft=jsonb_set(draft,'{status}',to_jsonb(%s::text)) where connection_id=%s",
            (status, cid),
        )
    refused = _act(_client(service, context), cid, "delete")
    assert (refused.status_code, refused.json()["code"]) == (
        422,
        "business_document_reading",
    )


def test_accepted_draft_cannot_be_deleted(actions):
    from argus.domain.business.contracts.actions import ApproveExpense

    service, context, _, draft, _ = _ready(actions)
    view = service.dossier(context, UUID(str(draft)))
    approved = service.approve(
        context,
        draft,
        ApproveExpense(
            action="record_expense", version=view.version, approve_anyway=True
        ),
        str(uuid4()),
    )
    assert approved.outcome == "applied", approved
    refused = _act(_client(service, context), draft, "delete")
    assert (refused.status_code, refused.json()["code"]) == (
        422,
        "business_document_not_open",
    )


@pytest.mark.parametrize("prepared", [False, True])
def test_repeat_upload_keeps_deleted_and_prepare_is_refused(actions, prepared):
    from argus.api.business import (
        require_business_document_write,
        require_business_surface,
    )
    from argus.api.routers.business import router as business_router

    service, context, cid, _, web = _unread(actions)
    if prepared:
        from datetime import datetime, timezone

        from argus.domain.business.actions import sources
        from argus.domain.business.contracts.dossier import AttachmentSource

        draft_id = _captured_purchase(service, context)
        source_id = service.record_source(
            context,
            str(uuid4()),
            AttachmentSource(
                id=uuid4(),
                channel="web",
                received_at=datetime.now(timezone.utc),
                connection_id=UUID(cid),
                filename="documento.png",
                media_type="image/png",
            ),
        )
        with transaction(service.authority, context) as tx:
            sources.attach(tx, str(draft_id), (source_id,))
    client = _client(service, context)
    client.app.include_router(business_router, prefix="/api/v1")
    client.app.dependency_overrides[require_business_document_write] = lambda: web
    client.app.dependency_overrides[require_business_surface] = lambda: None
    assert _act(client, cid, "delete").status_code == 200
    repeated = client.post(
        "/api/v1/business/receipts",
        content=RECEIPT,
        headers={
            "Content-Type": "image/png",
            "X-Document-Filename": "other.png",
            "Idempotency-Key": str(uuid4()),
        },
    )
    assert repeated.status_code == 200, repeated.text
    view = repeated.json()
    assert view["id"] == cid and view["replayed"] and view["deleted"]
    assert view["bandeja_group"]["group"] == "eliminados"
    assert view["restore_available"] and not view["delete_available"]
    assert len(receipt_summaries(web, "all")) == 1
    if not prepared:
        with pytest.raises(Exception, match="business_document_deleted"):
            web.service.queue(web.scope, cid)
    assert receipt_detail(web, web.service.receipt(web.scope, cid))["deleted"]


def test_deleted_draft_leaves_duplicate_checks_and_returns(actions):
    from dataclasses import replace

    from argus.domain.business.duplicates import pending_duplicates

    service, context, _, draft, _ = _ready(actions)
    with transaction(service.authority, context) as tx:
        original = tx.imports.event(str(draft))
        other = replace(original, id=str(uuid4()), possible_duplicates=(original.id,))
        tx.imports.put_event(other)
        assert str(draft) in pending_duplicates(tx.imports, other)
    client = _client(service, context)
    assert _act(client, draft, "delete").status_code == 200
    with transaction(service.authority, context) as tx:
        assert str(draft) not in pending_duplicates(tx.imports, other)
    assert _act(client, draft, "restore").status_code == 200
    with transaction(service.authority, context) as tx:
        assert str(draft) in pending_duplicates(tx.imports, other)


def test_unsettled_action_never_reports_success(actions):
    from argus.domain.business.actions import plans
    from argus.domain.business.contracts.deletion import DocumentCommand

    service, context, cid, _, web = _unread(actions)
    key = str(uuid4())
    with transaction(service.authority, context) as tx:
        plans.start_receipt(
            tx, key, DocumentCommand(action="delete_document", document_id=UUID(cid))
        )
    response = _act(_client(service, context), cid, "delete", key)
    assert (response.status_code, response.json()["code"]) == (
        409,
        "business_action_unsettled",
    )
    assert receipt_detail(web, web.service.receipt(web.scope, cid))["deleted"] is None


def test_queued_without_permission_is_saved_unread_and_deletable(actions):
    service, context, cid, _, web = _unread(actions)
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.financial_document_extractions set draft=jsonb_set(draft,'{status}','\"queued\"') where connection_id=%s",
            (cid,),
        )
    before = receipt_detail(web, web.service.receipt(web.scope, cid))
    assert not before["read_pending"]
    assert before["delete_available"]
    assert _act(_client(service, context), cid, "delete").status_code == 200


def test_restore_does_not_restore_an_unmarked_dismissal(actions):
    from dataclasses import replace

    service, context, _, draft_id, web = _ready(actions)
    with transaction(service.authority, context) as tx:
        event = tx.imports.event(str(draft_id))
        tx.imports.put_event(replace(event, state="dismissed"))
    refused = _act(_client(service, context), draft_id, "restore")
    assert (refused.status_code, refused.json()["code"]) == (
        422,
        "business_document_not_deleted",
    )
    assert counts(web, receipt_summaries(web, "all"))["bandeja_eliminados_count"] == 0


def test_action_key_cannot_be_reused_for_another_operation(actions):
    service, context, cid, _, _ = _unread(actions)
    client = _client(service, context)
    key = str(uuid4())
    assert _act(client, cid, "delete", key).status_code == 200
    refused = _act(client, cid, "restore", key)
    assert (refused.status_code, refused.json()["code"]) == (
        409,
        "business_action_conflict",
    )


def test_standalone_capture_stays_reachable_and_counted_in_eliminados(actions):
    from tests.test_business_receipt_views_postgres import _web

    service, context, _ = actions
    web = _web(service, context)
    draft_id = _captured_purchase(service, context)
    client = _client(service, context)
    before = service.captures_page(context, view="inbox")["items"]
    assert [row["draft_id"] for row in before] == [draft_id]
    assert _act(client, draft_id, "delete").status_code == 200
    assert service.captures_page(context, view="inbox")["items"] == []
    deleted = service.captures_page(context, view="eliminados")["items"]
    assert [row["draft_id"] for row in deleted] == [draft_id]
    assert deleted[0]["restore_available"]
    assert deleted[0]["bandeja_group"]["group"] == "eliminados"
    assert counts(web, receipt_summaries(web, "all"))["bandeja_eliminados_count"] == 1
    assert _act(client, draft_id, "restore").status_code == 200
    assert service.captures_page(context, view="eliminados")["items"] == []
    assert (
        service.captures_page(context, view="inbox")["items"][0]["text"]
        == before[0]["text"]
    )


def test_shared_attachment_cannot_hide_an_approved_sibling(actions):
    service, context, cid, draft, _ = _ready(actions)
    sibling = _captured_purchase(service, context, approve=True)
    with service.authority.pool.connection() as db:
        db.execute(
            "insert into public.business_draft_sources(space_id,draft_id,source_id) select space_id,%s,source_id from public.business_draft_sources where draft_id=%s",
            (sibling, draft),
        )
    client = _client(service, context)
    for target in (cid, draft):
        response = _act(client, target, "delete")
        assert (response.status_code, response.json()["code"]) == (
            422,
            "business_document_ambiguous",
        )
    assert service.dossier(context, sibling).review_state == "accepted"


def test_other_business_document_is_not_found(actions, users):
    from psycopg.types.json import Jsonb

    from tests.test_business_spaces_migration_postgres import connection, space

    service, context, cid, _, _ = _unread(actions)
    with service.authority.pool.connection() as db:
        other_space = space(db, users["other"])
        other_cid = connection(db, users["other"], other_space)
        original = db.execute(
            "select draft from public.financial_document_extractions where connection_id=%s",
            (cid,),
        ).fetchone()[0]
        db.execute(
            "insert into public.financial_document_extractions(connection_id,user_id,draft) values(%s,%s,%s)",
            (
                other_cid,
                users["other"],
                Jsonb({**original, "connection_id": str(other_cid)}),
            ),
        )
    for action in ("delete", "restore"):
        refused = _act(_client(service, context), other_cid, action)
        assert (refused.status_code, refused.json()["code"]) == (
            404,
            "business_record_not_found",
        )


def test_queued_with_live_consent_is_reading_and_cannot_be_deleted(actions, monkeypatch):
    from argus.domain.business.receipt_consent import (
        SCOPE_VERSION,
        BusinessReceiptConsentStore,
    )
    from argus.domain.ingestion.whatsapp import receipt_consent
    from psycopg.types.json import Jsonb

    route = {
        "gateway": "fixture",
        "interpretation": [{"model": "fixture-reader"}],
        "reply": [],
    }
    monkeypatch.setattr(receipt_consent, "receipt_provider_route", lambda: route)
    service, context, cid, _, web = _unread(actions)
    permission = BusinessReceiptConsentStore(service.authority.pool)
    space, owner = str(context.actor.space_id), str(context.owner_id)
    accepted = permission.set(
        space,
        owner,
        enabled=True,
        version=SCOPE_VERSION,
        disclosure_token=permission.status(space, owner)["disclosure_token"],
    )
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.financial_document_extractions set draft=draft || %s where connection_id=%s",
            (
                Jsonb(
                    {
                        "status": "queued",
                        "consent": True,
                        "business_reading_consent_id": accepted["consent_id"],
                    }
                ),
                cid,
            ),
        )
    web.service.documents.business_receipt_consent = permission
    view = receipt_detail(web, web.service.receipt(web.scope, cid))
    assert view["read_pending"] and not view["delete_available"]
    refused = _act(_client(service, context), cid, "delete")
    assert (refused.status_code, refused.json()["code"]) == (
        422,
        "business_document_reading",
    )


@pytest.mark.parametrize("by_draft", [False, True])
def test_legacy_single_purchase_marker_stays_reachable(actions, by_draft):
    from tests.test_business_receipt_views_postgres import _web
    from tests.test_business_single_candidate_postgres import _saved

    service, context, _, cid, _, batch = _saved(actions, "expense")
    web = _web(service, context)
    service.imports.submit(
        user_id=context.owner_id,
        connection_id=cid,
        candidates=batch.candidates,
        scope=context.scope,
    )
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.financial_source_connections set lease_until=null,lease_holder=null where id=%s",
            (cid,),
        )
        db.execute(
            "update public.financial_document_extractions set draft=jsonb_set(draft,'{status}','\"review_ready\"') where connection_id=%s",
            (cid,),
        )
    before = receipt_detail(web, web.service.receipt(web.scope, cid))
    target = before["draft_id"] if by_draft else cid
    assert target is not None
    client = _client(service, context)
    assert _act(client, target, "delete").status_code == 200
    row = receipt_detail(web, web.service.receipt(web.scope, cid))
    assert row["deleted"] and row["bandeja_group"]["group"] == "eliminados"
    assert row["restore_available"]
    assert counts(web, receipt_summaries(web, "all"))["bandeja_eliminados_count"] == 1
    feed = read_activity(service.authority, context, limit=25, filters=ActivityFilters())
    deleted_action = next(item for item in feed.items if item.action == "delete_document")
    assert deleted_action.object.label == before["filename"]
    assert deleted_action.object.kind == "receipt" and str(
        deleted_action.object.id
    ) == str(cid)
    assert _act(client, target, "restore").status_code == 200
    restored = receipt_detail(web, web.service.receipt(web.scope, cid))
    assert restored["deleted"] is None
    assert restored["status"] == before["status"]


def _multiple_purchases(actions):
    from tests.test_business_receipt_views_postgres import _web
    from tests.test_business_single_candidate_postgres import _saved

    service, context, _, cid, _, batch = _saved(actions, "expense")
    first = batch.candidates[0]
    second = first.model_copy(
        update={
            "source": first.source.model_copy(update={"external_id": str(uuid4())}),
            "amount": "750.50",
        }
    )
    service.imports.submit(
        user_id=context.owner_id,
        connection_id=cid,
        candidates=(first, second),
        scope=context.scope,
    )
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.financial_source_connections set lease_until=null,lease_holder=null where id=%s",
            (cid,),
        )
        db.execute(
            "update public.financial_document_extractions set draft=jsonb_set(draft,'{status}','\"review_ready\"') where connection_id=%s",
            (cid,),
        )
    with transaction(service.authority, context) as tx:
        events = tuple(tx.imports.events(("open",)))
    assert len(events) == 2
    return service, context, cid, _web(service, context), events


@pytest.mark.parametrize("previous", ["open", "dismissed"])
def test_multiple_unapproved_purchases_use_one_marker_and_restore_exact_states(
    actions, previous
):
    from dataclasses import replace

    from argus.domain.business.duplicates import (
        flag_receipt_duplicates,
        pending_duplicates,
    )

    service, context, cid, web, events = _multiple_purchases(actions)
    events = (events[0], replace(events[1], state=previous))
    with transaction(service.authority, context) as tx:
        tx.imports.put_event(events[1])
    expected_duplicates = {event.id for event in events if event.state == "open"}
    before = receipt_detail(web, web.service.receipt(web.scope, cid))
    assert before["draft_id"] is None and before["delete_available"]
    with transaction(service.authority, context) as tx:
        other = replace(
            events[0],
            id=str(uuid4()),
            possible_duplicates=tuple(event.id for event in events),
        )
        tx.imports.put_event(other)
        assert set(pending_duplicates(tx.imports, other)) == expected_duplicates
    client = _client(service, context)
    assert _act(client, cid, "delete").status_code == 200
    view = receipt_detail(web, web.service.receipt(web.scope, cid))
    marker = DeletedDocument.model_validate(view["deleted"])
    assert marker.previous_state.events == {event.id: event.state for event in events}
    assert view["bandeja_group"]["group"] == "eliminados"
    assert counts(web, receipt_summaries(web, "all"))["pending_review_count"] == 0
    with transaction(service.authority, context) as tx:
        for original in events:
            dismissed = tx.imports.event(original.id)
            assert dismissed.state == "dismissed"
            assert dismissed.resolution == original.resolution
        assert pending_duplicates(tx.imports, other) == ()
        assert flag_receipt_duplicates(tx.imports, other.id) == ()
    assert _act(client, cid, "restore").status_code == 200
    restored = receipt_detail(web, web.service.receipt(web.scope, cid))
    assert restored["deleted"] is None and restored["status"] == before["status"]
    assert counts(web, receipt_summaries(web, "all"))["pending_review_count"] == 1
    with transaction(service.authority, context) as tx:
        for original in events:
            current = tx.imports.event(original.id)
            assert (current.state, current.resolution, current.possible_duplicates) == (
                original.state,
                original.resolution,
                original.possible_duplicates,
            )
        assert set(pending_duplicates(tx.imports, other)) == expected_duplicates


@pytest.mark.parametrize("state", ["accepting", "accepted"])
def test_multiple_purchases_refuse_any_recorded_constituent_without_changes(
    actions, state
):
    from dataclasses import replace
    from datetime import datetime, timezone

    from argus.domain.recording.money_schemas import MoneyRequest, UnstatedFunding

    service, context, cid, web, events = _multiple_purchases(actions)
    selected = events[0]
    if state == "accepted":
        request = MoneyRequest(
            kind="expense",
            amount="33254.91",
            occurred_at=datetime(2026, 10, 9, tzinfo=timezone.utc),
            unstated_funding=UnstatedFunding(
                owner_space_id=context.actor.space_id, currency="DOP"
            ),
        )
        preview = service.imports.money.preview(
            user_id=context.owner_id, request=request, scope=context.scope
        )
        request = request.model_copy(update={"preview_token": preview["preview_token"]})
        service.imports.accept(
            user_id=context.owner_id,
            event_id=selected.id,
            version=selected.version,
            idempotency_key=str(uuid4()),
            scope=context.scope,
            request=request,
        )
    else:
        with transaction(service.authority, context) as tx:
            tx.imports.put_event(replace(selected, state=state))
    with transaction(service.authority, context) as tx:
        before_events = tuple(tx.imports.event(event.id) for event in events)
    before = receipt_detail(web, web.service.receipt(web.scope, cid))
    assert not before["delete_available"]
    refused = _act(_client(service, context), cid, "delete")
    assert (refused.status_code, refused.json()["code"]) == (
        422,
        "business_document_not_open",
    )
    assert receipt_detail(web, web.service.receipt(web.scope, cid)) == before
    with transaction(service.authority, context) as tx:
        assert tuple(tx.imports.event(event.id) for event in events) == before_events


def test_message_only_draft_is_reachable_in_eliminados(actions):
    from tests.test_business_receipt_views_postgres import _web

    service, context, _ = actions
    draft_id, _ = shared.create(service, context)
    before = service.dossier(context, draft_id)
    assert before.delete_available
    client = _client(service, context)
    assert _act(client, draft_id, "delete").status_code == 200
    deleted = service.captures_page(context, view="eliminados")["items"]
    assert [row["draft_id"] for row in deleted] == [draft_id]
    assert deleted[0]["text"] == before.sources[0].text
    assert deleted[0]["source_id"] == before.sources[0].id
    assert deleted[0]["restore_available"]
    web = _web(service, context)
    assert counts(web, receipt_summaries(web, "all"))["bandeja_eliminados_count"] == 1
    assert _act(client, draft_id, "restore").status_code == 200
    assert service.captures_page(context, view="eliminados")["items"] == []
    restored = service.dossier(context, draft_id)
    assert restored.facts == before.facts and restored.sources == before.sources
    assert restored.review_state == "open"
