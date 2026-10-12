"""Known limit B on real Postgres: a receipt bound to a grant that was revoked
and re-issued is bound again by one owner action, with a ledger row, and the
preparation then finishes under the new grant. A live grant is never moved."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import UUID, uuid4

import psycopg
import pytest
from argus.domain.business.actions import BusinessActions
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.authority import TrustedActor
from psycopg.types.json import Jsonb

from tests import test_business_attachment_preparation_postgres as shared
from tests.test_business_spaces_migration_postgres import connection, space

actions = shared.actions
users = shared.users
prepared = shared.prepared
pytestmark = shared.pytestmark


def _owner(service: BusinessActions, context):  # noqa: ANN001
    # The shared fixture makes the space by SQL; give the owner the grant that
    # starting a space through the app gives them (#988).
    with service.authority.pool.connection() as db:
        db.execute(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities)"
            " select %s,%s,%s,ARRAY['read','prepare','approve'] where not exists"
            " (select 1 from public.business_client_grants where space_id=%s and grantee_id=%s and revoked_at is null)",
            (
                context.actor.space_id,
                context.owner_id,
                context.owner_id,
                context.actor.space_id,
                context.owner_id,
            ),
        )
    return service.resolve_actor(
        TrustedActor(
            actor_id=UUID(context.owner_id),
            actor_kind="member",
            space_id=context.actor.space_id,
        )
    )


def _ledger(service: BusinessActions, space_id) -> list[str]:  # noqa: ANN001
    with service.authority.pool.connection() as db:
        return [
            row[0]
            for row in db.execute(
                "select command->>'action' from public.business_action_receipts"
                " where space_id=%s and command->>'action'='rebind_attachment' order by created_at",
                (space_id,),
            ).fetchall()
        ]


def _end_grant(service: BusinessActions, grant, how: str) -> None:  # noqa: ANN001
    with service.authority.pool.connection() as db:
        if how == "revoked":
            db.execute(
                "update public.business_client_grants set revoked_at=now() where id=%s",
                (grant,),
            )
        else:
            db.execute(
                "update public.business_client_grants set created_at=now()-interval '2 days',"
                " expires_at=now()-interval '1 day' where id=%s",
                (grant,),
            )


@pytest.mark.parametrize("how", ["revoked", "expired"])
def test_a_dead_then_reissued_grant_is_rebound_by_the_owner_and_preparation_finishes(
    prepared, users, how
) -> None:  # noqa: ANN001
    service, context, grant, cid, _, _ = prepared
    binding = shared.bind(prepared)
    assert binding.actor.grant_id == grant
    owner = _owner(service, context)
    # While the old grant is live the binding is left alone.
    with pytest.raises(ActionError, match="business_preparation_binding_live"):
        service.rebind_attachment_preparation(owner, UUID(cid))
    _end_grant(service, grant, how)
    with service.authority.pool.connection() as db:
        db.execute(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities)"
            " values (%s,%s,%s,ARRAY['read','prepare'])",
            (context.actor.space_id, users["other"], users["owner"]),
        )
    # Under the old binding the preparation cannot even find its authority.
    with pytest.raises(ActionError, match="business_record_not_found"):
        shared.finish(prepared)
    rebound = service.rebind_attachment_preparation(owner, UUID(cid))
    assert rebound.binding_id != binding.binding_id
    assert (rebound.actor.actor_id, rebound.actor.actor_kind) == (
        UUID(context.owner_id),
        "extractor",
    )
    assert rebound.actor.grant_id == owner.grant_id
    assert (
        rebound.connection_id == binding.connection_id
        and rebound.source_sha256 == binding.source_sha256
    )
    assert _ledger(service, context.actor.space_id) == ["rebind_attachment"]
    # A replay of the owner action after the move is refused as live, not doubled.
    with pytest.raises(ActionError, match="business_preparation_binding_live"):
        service.rebind_attachment_preparation(owner, UUID(cid))
    assert _ledger(service, context.actor.space_id) == ["rebind_attachment"]
    # The preparation now finishes under the owner's grant.
    result = shared.finish(prepared)
    assert result.outcome == "applied", result
    view = service.dossier(owner, result.draft_id)
    assert view.history[-1].actor.grant_id == owner.grant_id


def test_only_the_owner_may_rebind_and_only_a_bound_receipt(prepared, users) -> None:  # noqa: ANN001
    service, context, grant, cid, _, _ = prepared
    owner = _owner(service, context)
    # Nothing is bound yet: there is nothing to move.
    with pytest.raises(ActionError, match="business_preparation_binding_missing"):
        service.rebind_attachment_preparation(owner, UUID(cid))
    with pytest.raises(ActionError, match="business_record_not_found"):
        service.rebind_attachment_preparation(owner, UUID(int=0))
    shared.bind(prepared)
    with pytest.raises(ActionError, match="business_owner_required"):
        service.rebind_attachment_preparation(context, UUID(cid))


def test_only_a_person_may_rebind_and_only_in_their_own_business(prepared, users) -> None:  # noqa: ANN001
    service, context, grant, cid, _, _ = prepared
    shared.bind(prepared)
    owner = _owner(service, context)
    # The owner's extractor identity is not a person.
    robot = replace(
        owner, actor=owner.actor.model_copy(update={"actor_kind": "extractor"})
    )
    with pytest.raises(ActionError, match="business_human_command_required"):
        service.rebind_attachment_preparation(robot, UUID(cid))
    # A receipt of another Business is not found from this one.
    with service.authority.pool.connection() as db:
        other_space = space(db, users["other"])
        foreign = connection(db, users["other"], other_space)
    with pytest.raises(ActionError, match="business_record_not_found"):
        service.rebind_attachment_preparation(owner, UUID(foreign))
    assert _ledger(service, context.actor.space_id) == []


def test_two_clicks_at_once_move_the_binding_once(prepared, users) -> None:  # noqa: ANN001
    service, context, grant, cid, _, _ = prepared
    shared.bind(prepared)
    owner = _owner(service, context)
    _end_grant(service, grant, "revoked")
    with service.authority.pool.connection() as db:
        db.execute(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities)"
            " values (%s,%s,%s,ARRAY['read','prepare'])",
            (context.actor.space_id, users["other"], users["owner"]),
        )

    def click(_: int):  # noqa: ANN202
        try:
            return service.rebind_attachment_preparation(owner, UUID(cid))
        except ActionError as error:
            return error.result.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(click, range(2)))
    outcomes = sorted(r if isinstance(r, str) else "moved" for r in results)
    assert outcomes == ["business_preparation_binding_live", "moved"]
    assert _ledger(service, context.actor.space_id) == ["rebind_attachment"]


def test_the_ledger_refuses_a_rebind_row_by_anything_but_a_person(
    prepared, users
) -> None:  # noqa: ANN001
    service, context, grant, cid, _, _ = prepared
    binding = shared.bind(prepared)
    actor = binding.actor.model_dump(mode="json")
    command = {
        "action": "rebind_attachment",
        "previous_binding_id": str(binding.binding_id),
        "previous_grant_id": str(binding.actor.grant_id),
        "binding": binding.model_dump(mode="json"),
    }

    def row(actor_kind: str) -> None:
        with service.authority.pool.connection() as db:
            db.execute(
                "insert into public.business_action_receipts"
                " (space_id,actor_id,actor,idempotency_key,input_hash,command,turn_key,action_index)"
                " values (%s,%s,%s,%s,%s,%s,null,null)",
                (
                    context.actor.space_id,
                    actor["actor_id"],
                    Jsonb({**actor, "actor_kind": actor_kind}),
                    str(uuid4()),
                    "c" * 64,
                    Jsonb(command),
                ),
            )

    with pytest.raises(psycopg.errors.CheckViolation, match="rebind_human"):
        row("extractor")
    row("member")


def test_the_route_answers_owner_200_accountant_403_and_bad_id_404(
    prepared, users, monkeypatch
) -> None:  # noqa: ANN001
    from argus.api import business as business_api
    from argus.api.business_drafts import scoped_legacy
    from argus.api.routers import business as routes
    from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository
    from argus.domain.ingestion.documents.service import DocumentsService
    from argus.domain.ingestion.documents.store_postgres import PostgresDocumentStore
    from argus.domain.ingestion.hub import IngestionHub
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from tests.document_sources_support import source_objects
    from tests.ingestion.whatsapp_support import RefusingExtractor

    service, context, grant, cid, _, _ = prepared
    shared.bind(prepared)
    _owner(service, context)
    _end_grant(service, grant, "revoked")
    with service.authority.pool.connection() as db:
        db.execute(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities)"
            " values (%s,%s,%s,ARRAY['read','prepare'])",
            (context.actor.space_id, users["other"], users["owner"]),
        )
    pool = service.authority.pool
    hub = IngestionHub(
        PostgresConnectionRepository(pool),
        box=None,
        sink=service.imports,
        clock=service.imports.clock,
    )
    documents = DocumentsService(
        hub, PostgresDocumentStore(pool, source_objects()), RefusingExtractor()
    )
    caller = {"id": users["owner"]}
    app = FastAPI()
    app.state.financial_accounts_pool = pool

    @app.middleware("http")
    async def request_id(request, call_next):  # noqa: ANN001, ANN202
        request.state.request_id = "synthetic-rebind"
        return await call_next(request)

    app.include_router(routes.router)
    app.dependency_overrides[business_api.require_business_surface] = lambda: None

    def document_context(request: Request):  # noqa: ANN202
        return scoped_legacy(request, documents, hub, caller["id"], None)

    app.dependency_overrides[business_api.require_business_document_write] = (
        document_context
    )
    monkeypatch.setattr(routes, "ingestion_hub", lambda: hub)
    with TestClient(app) as client:
        caller["id"] = users["other"]
        refused = client.post(f"/business/receipts/{cid}/rebind")
        assert refused.status_code == 403, refused.text
        assert refused.json()["detail"]["code"] == "business_owner_required"
        caller["id"] = users["owner"]
        missing = client.post("/business/receipts/not-a-uuid/rebind")
        assert missing.status_code == 404, missing.text
        moved = client.post(f"/business/receipts/{cid}/rebind")
        assert moved.status_code == 200, moved.text
        assert moved.json()["id"] == cid
    assert _ledger(service, context.actor.space_id) == ["rebind_attachment"]
