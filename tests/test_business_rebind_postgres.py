"""Known limit B on real Postgres: a receipt bound to a grant that was revoked
and re-issued is bound again by one owner action, with a ledger row, and the
preparation then finishes under the new grant. A live grant is never moved."""

from __future__ import annotations

from uuid import UUID

import pytest
from argus.domain.business.actions import BusinessActions
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.authority import TrustedActor

from tests import test_business_attachment_preparation_postgres as shared

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


def test_a_revoked_then_reissued_grant_is_rebound_by_the_owner_and_preparation_finishes(
    prepared, users
) -> None:  # noqa: ANN001
    service, context, grant, cid, _, _ = prepared
    binding = shared.bind(prepared)
    assert binding.actor.grant_id == grant
    owner = _owner(service, context)
    # While the old grant is live the binding is left alone.
    with pytest.raises(ActionError, match="business_preparation_binding_live"):
        service.rebind_attachment_preparation(owner, UUID(cid))
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.business_client_grants set revoked_at=now() where id=%s",
            (grant,),
        )
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


def test_only_the_owner_may_rebind(prepared, users) -> None:  # noqa: ANN001
    service, context, grant, cid, _, _ = prepared
    shared.bind(prepared)
    with pytest.raises(ActionError, match="business_owner_required"):
        service.rebind_attachment_preparation(context, UUID(cid))
    owner = _owner(service, context)
    with pytest.raises(ActionError, match="business_preparation_binding_missing"):
        service.rebind_attachment_preparation(owner, UUID(int=0))
