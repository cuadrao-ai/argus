from __future__ import annotations

import json
from uuid import UUID

import pytest
from argus.api.business import (
    BusinessPerson,
    require_business,
    require_business_person,
    require_business_surface,
)
from argus.api.business_drafts import DraftContext, scoped_legacy, stored_drafts
from argus.api.routers.business import router as receipts_router
from argus.api.routers.business_manual import router as captures_router
from argus.domain.business.activity.queries import read_activity
from argus.domain.business.contracts.activity import ActivityFilters
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.scope import resolve_business_scope
from argus.domain.business.spaces import PostgresSpaceStore
from faker import Faker
from fastapi import FastAPI
from starlette.requests import Request

from tests import test_business_account_deletion_postgres as departure
from tests import test_business_document_delete_postgres as documents
from tests.document_sources_support import source_objects
from tests.test_business_single_candidate_postgres import _saved

users = documents.users
actions = documents.actions
pytestmark = documents.pytestmark


def _target(actions, kind):
    if kind in ("bridged", "unread"):
        return (documents._ready if kind == "bridged" else documents._unread)(actions)
    if kind == "capture":
        service, context, _ = actions
        return (
            service,
            context,
            None,
            documents._captured_purchase(service, context),
            None,
        )
    if kind == "generic_multiple":
        service, context, cid, web, _ = documents._multiple_purchases(actions)
        return service, context, cid, None, web
    service, context, _, cid, _, batch = _saved(actions, "expense")
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
    return service, context, cid, None, None


def _reader_client(service, context, web):
    client = documents._client(service, context)
    client.app.include_router(receipts_router, prefix="/api/v1")
    client.app.include_router(captures_router, prefix="/api/v1")
    spaces = PostgresSpaceStore(service.authority.pool)
    drafts = DraftContext(service, context.actor.actor_id, str(context.actor.space_id))
    client.app.dependency_overrides[stored_drafts] = lambda: drafts
    client.app.dependency_overrides[require_business_person] = lambda: BusinessPerson(
        str(context.actor.actor_id), spaces
    )
    client.app.dependency_overrides[require_business_surface] = lambda: None
    if web is not None:
        app = FastAPI()
        app.state.financial_accounts_pool = service.authority.pool
        request = Request(
            {
                "type": "http",
                "app": app,
                "method": "GET",
                "path": "/business/receipts",
                "headers": [],
            }
        )
        reader = scoped_legacy(
            request,
            web.service.documents,
            web.service.documents.hub,
            str(context.actor.actor_id),
            resolve_business_scope(spaces, str(context.actor.actor_id)),
        )
        client.app.dependency_overrides[require_business] = lambda: reader
    return client


@pytest.mark.parametrize(
    "kind", ["bridged", "unread", "generic_single", "generic_multiple", "capture"]
)
def test_deleted_document_actor_is_anonymous_after_owner_account_departure(
    actions, users, kind
):
    from tests.test_business_receipt_views_postgres import _web

    service, original, cid, draft_id, web = _target(actions, kind)
    pool, space, former = (
        service.authority.pool,
        str(original.actor.space_id),
        original.owner_id,
    )
    former_name = Faker("es").name()
    with pool.connection() as db:
        db.execute(
            "update public.profiles set display_name=%s where id=%s",
            (former_name, former),
        )
    if web is None and cid is not None:
        web = _web(service, original)
    client = documents._client(service, original)
    target = draft_id or cid
    for action in ("delete", "restore", "delete"):
        response = documents._act(client, target, action)
        assert response.status_code == 200, response.text
    w = {
        "pool": pool,
        "space": space,
        "old": former,
        "users": users,
        "objects": source_objects(),
    }
    try:
        departure.transfer(w)
        assert departure.command(w).delete_account(user_id=former).status == "done"
        current = service.resolve_actor(
            TrustedActor(
                actor_id=UUID(users["other"]), actor_kind="member", space_id=UUID(space)
            )
        )
        client = _reader_client(service, current, web)
        if cid is None:
            responses = [
                client.get("/api/v1/business/captures?view=eliminados"),
                client.get(f"/api/v1/business/drafts/{draft_id}/dossier"),
            ]
        else:
            responses = [
                client.get("/api/v1/business/receipts?view=all"),
                client.get(f"/api/v1/business/receipts/{cid}"),
            ]
        with pool.connection() as db:
            alias = db.execute(
                "select deleted_actor_id::text from argus_private.business_custody_reservations where space_id=%s",
                (space,),
            ).fetchone()[0]
            ledger = db.execute(
                "select actor_id::text,actor,command->>'action' from public.business_action_receipts"
                " where space_id=%s and command->>'action' in ('delete_document','restore_document')",
                (space,),
            ).fetchall()
        assert len(ledger) == 3
        assert {row[2] for row in ledger} == {"delete_document", "restore_document"}
        assert all(
            row[0] == alias and row[1]["display_name"] == "Exmiembro" for row in ledger
        )
        for response in responses:
            assert response.status_code == 200, response.text
            body = response.json()
            view = body["items"][0] if "items" in body else body
            if cid is not None or "items" in body:
                assert view["bandeja_group"]["group"] == "eliminados"
            assert view["deleted"]["actor"] == {
                "actor_id": alias,
                "display_name": "Exmiembro",
            }
            assert former not in response.text and former_name not in response.text
        feed = read_activity(
            service.authority, current, limit=25, filters=ActivityFilters()
        )
        history = [
            item
            for item in feed.items
            if item.action in ("delete_document", "restore_document")
        ]
        assert len(history) == 3
        assert all(item.actor.display_name == "Exmiembro" for item in history)
        assert former not in json.dumps(feed.model_dump(mode="json"))
        assert documents._act(client, target, "restore").status_code == 200
    finally:
        departure.release_custodian(space)
