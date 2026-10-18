"""Ownership changes preserve custody and require live member acceptance."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import psycopg
import pytest
from argus.domain.business.authority import ActionError, authorize
from argus.domain.business.lifecycle import (
    BusinessLifecycleError,
    PostgresBusinessLifecycle,
)
from argus.domain.business.receipt_consent import BusinessReceiptConsentStore
from argus.domain.business.scope import resolve_business_scope
from argus.domain.business.spaces import PostgresSpaceStore
from argus.domain.business.transfer import PostgresBusinessTransfer

from tests import test_business_attachment_preparation_postgres as bridge_fixture
from tests import test_business_lifecycle_postgres as lifecycle
from tests import test_financial_accounts_postgres as shared
from tests.test_business_lifecycle_postgres import _actor

actions = bridge_fixture.actions
world = lifecycle.world
users = lifecycle.users

pytestmark = pytest.mark.skipif(not shared.DSN, reason="Disposable database required")


def _request(world, key="transfer-1", **changes):
    pool, space, people, _, member = world
    args = dict(
        owner_id=people["owner"],
        space_id=space.id,
        target_grant_id=member.id,
        confirmation=space.name,
        idempotency_key=key,
    )
    args.update(changes)
    return PostgresBusinessTransfer(pool).request(**args)


def test_accept_changes_authority_and_preserves_storage_and_other_access(world):
    pool, space, people, access, member = world
    transfer = _request(world)
    assert transfer.status == "pending"
    assert PostgresSpaceStore(pool).open_space(people["owner"]).id == space.id
    accepted = PostgresBusinessTransfer(pool).accept(
        actor_id=people["other"], transfer_id=transfer.id
    )
    assert accepted.status == "accepted"
    assert (
        PostgresBusinessTransfer(pool).accept(
            actor_id=people["other"], transfer_id=transfer.id
        )
        == accepted
    )
    with psycopg.connect(shared.DSN) as db:
        assert db.execute(
            "select created_by::text,current_owner_id::text from public.spaces where id=%s",
            (space.id,),
        ).fetchone() == (people["owner"], people["other"])
        new = authorize(db, _actor(people["other"], space.id))
        new.require("approve")
        assert new.context.owner_id == people["owner"]
        assert new.context.current_owner_id == people["other"]
        with pytest.raises(ActionError):
            authorize(db, _actor(people["owner"], space.id)).require("approve")
    assert access.granted(people["other"], member.id).role == "owner"
    assert access.spaces_for(people["owner"])[0].role == "accountant"
    assert access.spaces_for(people["owner"])[0].capabilities == ("read", "prepare")
    scope = resolve_business_scope(PostgresSpaceStore(pool), people["other"])
    assert scope.person_id == people["owner"] and scope.acting_as_owner
    assert PostgresSpaceStore(pool).open_space(people["owner"]) is None
    access.give(space.id, people["other"], "new-member@example.test")
    with pytest.raises(LookupError):
        access.list(space.id, people["owner"])
    closed = PostgresBusinessLifecycle(pool).close(
        owner_id=people["other"],
        space_id=space.id,
        confirmation=space.name,
        idempotency_key="after-transfer",
    )
    assert closed.closed_at is not None


def test_request_name_and_target_are_checked(world):
    with pytest.raises(BusinessLifecycleError, match="business_name_mismatch"):
        _request(world, confirmation="Wrong")
    pool, _, people, _, _ = world
    with pytest.raises(BusinessLifecycleError, match="business_record_not_found"):
        _request(world, owner_id=people["other"])
    with pytest.raises(BusinessLifecycleError, match="business_transfer_target_invalid"):
        _request(world, target_grant_id=str(UUID(int=1)))


def test_cancel_and_late_accept_do_not_change_owner(world):
    pool, space, people, _, _ = world
    command = _request(world)
    service = PostgresBusinessTransfer(pool)
    cancelled = service.cancel(owner_id=people["owner"], transfer_id=command.id)
    assert cancelled.status == "cancelled"
    assert service.cancel(owner_id=people["owner"], transfer_id=command.id) == cancelled
    with pytest.raises(BusinessLifecycleError, match="business_transfer_not_pending"):
        service.accept(actor_id=people["other"], transfer_id=command.id)
    assert PostgresSpaceStore(pool).open_space(people["owner"]).id == space.id


@pytest.mark.parametrize(
    "bad_target", ["revoked", "expired", "anonymous", "banned", "owns_business"]
)
def test_target_rechecked_at_acceptance(world, bad_target):
    pool, space, people, _, member = world
    command = _request(world)
    with psycopg.connect(shared.DSN) as db:
        if bad_target == "revoked":
            db.execute(
                "update public.business_client_grants set revoked_at=now() where id=%s",
                (member.id,),
            )
        elif bad_target == "expired":
            db.execute(
                "update public.business_client_grants set created_at=now()-interval '1 day',expires_at=now()-interval '1 second' where id=%s",
                (member.id,),
            )
        elif bad_target == "anonymous":
            db.execute(
                "update auth.users set is_anonymous=true where id=%s", (people["other"],)
            )
        elif bad_target == "banned":
            db.execute(
                "update auth.users set banned_until=now()+interval '1 day' where id=%s",
                (people["other"],),
            )
    if bad_target == "owns_business":
        PostgresSpaceStore(pool).create(people["other"], "Another business")
    with pytest.raises(BusinessLifecycleError, match="business_transfer_target_invalid"):
        PostgresBusinessTransfer(pool).accept(
            actor_id=people["other"], transfer_id=command.id
        )
    assert PostgresSpaceStore(pool).open_space(people["owner"]).id == space.id


def test_replay_and_accept_race_converge(world):
    pool, _, people, _, _ = world
    command = _request(world)
    assert _request(world) == command
    with pytest.raises(BusinessLifecycleError, match="idempotency_conflict"):
        _request(world, confirmation="Other")
    service = PostgresBusinessTransfer(pool)
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = tuple(
            workers.map(
                lambda _: service.accept(
                    actor_id=people["other"], transfer_id=command.id
                ),
                range(2),
            )
        )
    assert results[0] == results[1] and results[0].status == "accepted"


def test_nonmember_and_wrong_acceptor_are_denied(world):
    pool, _, people, _, _ = world
    command = _request(world)
    for wrong in (people["owner"], people["guest"]):
        with pytest.raises(BusinessLifecycleError, match="business_record_not_found"):
            PostgresBusinessTransfer(pool).accept(actor_id=wrong, transfer_id=command.id)


def test_new_owner_must_supply_own_receipt_consent(world):
    pool, space, people, _, _ = world
    permissions = BusinessReceiptConsentStore(
        pool, route_resolver=lambda: {"provider": "fake", "model": "fake"}
    )
    shown = permissions.status(space.id, people["owner"])
    old = permissions.set(
        space.id,
        people["owner"],
        actor_id=people["owner"],
        enabled=True,
        version=1,
        disclosure_token=shown["disclosure_token"],
    )
    command = _request(world)
    PostgresBusinessTransfer(pool).accept(
        actor_id=people["other"], transfer_id=command.id
    )
    shown = permissions.status(space.id, people["owner"])
    assert not shown["enabled"]
    assert not permissions.enabled(space.id, people["owner"], old["consent_id"])
    with pytest.raises(ActionError):
        permissions.set(
            space.id,
            people["owner"],
            actor_id=people["owner"],
            enabled=True,
            version=1,
            disclosure_token=shown["disclosure_token"],
        )
    new = permissions.set(
        space.id,
        people["owner"],
        actor_id=people["other"],
        enabled=True,
        version=1,
        disclosure_token=shown["disclosure_token"],
    )
    assert new["enabled"] and new["consent_id"] != old["consent_id"]
    assert permissions.enabled(space.id, people["owner"], new["consent_id"])
    assert not permissions.enabled(space.id, people["other"])


def test_close_cancels_transfer_and_accept_cannot_reopen(world):
    pool, space, people, _, _ = world
    command = _request(world)
    PostgresBusinessLifecycle(pool).close(
        owner_id=people["owner"],
        space_id=space.id,
        confirmation=space.name,
        idempotency_key="close-pending",
    )
    with pytest.raises(BusinessLifecycleError, match="business_transfer_not_pending"):
        PostgresBusinessTransfer(pool).accept(
            actor_id=people["other"], transfer_id=command.id
        )
    assert PostgresSpaceStore(pool).open_space(people["other"]) is None


def test_transfer_storage_is_service_only_and_history_cannot_be_rewritten(world):
    _, _, _, _, _ = world
    command = _request(world)
    with psycopg.connect(shared.DSN) as db:
        for role in ("anon", "authenticated"):
            assert not db.execute(
                "select has_table_privilege(%s,'public.business_ownership_transfers','SELECT')",
                (role,),
            ).fetchone()[0]
        with pytest.raises(
            psycopg.errors.CheckViolation, match="business_transfer_history_immutable"
        ):
            db.execute(
                "update public.business_ownership_transfers set confirmation='Changed' where id=%s",
                (command.id,),
            )


@pytest.mark.owner_acts
def test_transferred_receipt_reads_reviews_history_and_original_are_scoped(
    actions, users
):
    from hashlib import sha256

    from argus.api.business_drafts import receipt_detail, scoped_legacy
    from argus.domain.business.access import PostgresAccessStore
    from argus.domain.business.contracts.actions import ReviewDraft
    from argus.domain.business.contracts.facts import BusinessFactPatch
    from argus.domain.business.scope import BusinessScope
    from fastapi import FastAPI
    from starlette.requests import Request

    from tests import test_business_attachment_preparation_postgres as bridge
    from tests import test_business_receipt_views_postgres as views
    from tests import test_business_single_candidate_postgres as single

    saved = single._saved(actions, "expense")
    bridge.bind(saved)
    finished = bridge.finish(saved)
    assert finished.outcome == "applied"
    service, old, _, cid, _, _ = saved
    pool = service.authority.pool
    with pool.connection() as db:
        email = db.execute(
            "update auth.users set email_confirmed_at=now() where id=%s returning email",
            (users["other"],),
        ).fetchone()[0]
        before = db.execute(
            "select source_bytes,preparation_binding from public.financial_document_extractions where connection_id=%s",
            (cid,),
        ).fetchone()
        sources = db.execute(
            "select id,source_key,text_content,connection_id from public.business_sources where space_id=%s order by id",
            (old.actor.space_id,),
        ).fetchall()
    _, listing = PostgresAccessStore(pool).give(
        str(old.actor.space_id), old.owner_id, email
    )
    target = next(g for g in listing.grants if g.grantee_id == users["other"])
    transfer = PostgresBusinessTransfer(pool).request(
        owner_id=old.owner_id,
        space_id=str(old.actor.space_id),
        target_grant_id=target.id,
        confirmation=old.space_name,
        idempotency_key="receipt-transfer",
    )
    PostgresBusinessTransfer(pool).accept(
        actor_id=users["other"], transfer_id=transfer.id
    )
    current = service.context_for_receipt(
        UUID(users["other"]), UUID(cid), space_id=old.actor.space_id
    )
    assert service.dossier(current, finished.draft_id).version == finished.version
    base = views._web(service, old)
    assert not base.scope.acting_as_owner
    app = FastAPI()
    app.state.financial_accounts_pool = pool
    request = Request(
        {
            "type": "http",
            "app": app,
            "method": "GET",
            "path": "/business/receipts",
            "path_params": {},
            "headers": [],
            "state": {"request_id": "transfer-receipt"},
        }
    )
    scope = BusinessScope(
        old.owner_id, old.scope, actor_id=users["other"], grant_id=target.id, role="owner"
    )
    web = scoped_legacy(
        request, base.service.documents, base.service.documents.hub, users["other"], scope
    )
    assert web.scope.acting_as_owner and web.scope.person_id == old.owner_id
    detail = receipt_detail(web, web.service.receipt(web.scope, cid))
    assert detail["id"] == cid
    result = service.review(
        current,
        finished.draft_id,
        ReviewDraft(
            version=finished.version,
            facts=BusinessFactPatch(
                counterparty={"state": "known", "value": "Reviewed by new owner"}
            ),
        ),
        "new-owner-review",
    )
    assert result.outcome == "applied"
    former = service.context_for_receipt(
        UUID(old.owner_id), UUID(cid), space_id=old.actor.space_id
    )
    edited = service.review(
        former,
        finished.draft_id,
        ReviewDraft(
            version=result.version,
            facts=BusinessFactPatch(
                counterparty={"state": "known", "value": "Former owner can edit"}
            ),
        ),
        "former-owner-edit",
    )
    assert edited.outcome == "applied"
    with pool.connection() as db:
        after = db.execute(
            "select source_bytes,preparation_binding from public.financial_document_extractions where connection_id=%s",
            (cid,),
        ).fetchone()
        assert sha256(bytes(after[0])).digest() == sha256(bytes(before[0])).digest()
        assert after[1] == before[1]
        assert (
            db.execute(
                "select id,source_key,text_content,connection_id from public.business_sources where space_id=%s and id=any(%s) order by id",
                (old.actor.space_id, [row[0] for row in sources]),
            ).fetchall()
            == sources
        )
        with pytest.raises(ActionError):
            authorize(db, former.actor).require("approve")
    with pytest.raises(ActionError, match="business_record_not_found"):
        service.context_for_receipt(
            UUID(users["guest"]), UUID(cid), space_id=old.actor.space_id
        )
