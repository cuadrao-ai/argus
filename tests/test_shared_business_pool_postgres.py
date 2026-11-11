"""Management operations keep the grant lock without reacquiring its pool."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import date
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from argus.api import (
    bank_matching,
    business_spaces,
    email_intake,
    financial_accounts,
    profile_images,
)
from argus.api.business import BusinessContext, require_business_management
from argus.api.routers import business, business_logo
from argus.api.routers import email_intake as email_routes
from argus.domain.business.access import PostgresAccessStore
from argus.domain.business.scope import BusinessScope
from argus.domain.business.service import BusinessService
from argus.domain.business.spaces import PostgresSpaceStore
from argus.domain.ingestion.email_intake.service import (
    EmailCapture,
    grant_route_authority,
)
from argus.domain.ingestion.email_intake.store import PostgresEmailStore
from argus.domain.owner_scope import BusinessSpace
from argus.domain.profile_images import ProfileImages
from argus.domain.profile_images.objects import InMemoryProfileImageObjects
from argus.domain.profile_images.store import PostgresProfileImageStore
from fastapi import HTTPException, Request, Response
from psycopg_pool import ConnectionPool

from tests import test_business_actions_postgres as shared_actions

actions = shared_actions.actions
users = shared_actions.users
shared = shared_actions.shared

pytestmark = [
    pytest.mark.skipif(not shared.DSN, reason="Disposable PostgreSQL required"),
    pytest.mark.owner_acts,
]


@pytest.fixture
def management(actions, monkeypatch):
    service, actor, grant = actions
    with ConnectionPool(shared.DSN, min_size=2, max_size=2, timeout=0.5) as pool:
        scope = BusinessScope(
            person_id=actor.owner_id,
            owner=BusinessSpace(str(actor.actor.space_id)),
            actor_id=str(actor.actor.actor_id),
            grant_id=str(grant),
        )
        context = BusinessContext(
            scope, BusinessService(Mock(), service.imports, lambda _: frozenset())
        )
        monkeypatch.setattr(service.imports.money.accounts._repository, "_pool", pool)
        runtime = EmailCapture(
            PostgresEmailStore(pool),
            Mock(),
            grant_route_authority(pool),
            Mock(),
            lambda: True,
        )
        runtime.store.create_route(
            recipient=f"{uuid4().hex}@receipts.example.test",
            space_id=scope.owner.space_id,
            principal_id=scope.person_id,
            granted_by=scope.acting_person_id,
            grant_id=scope.grant_id,
        )
        monkeypatch.setattr(email_intake, "_runtime", runtime)
        monkeypatch.setattr(business_spaces, "_spaces", PostgresSpaceStore(pool))
        monkeypatch.setattr(business_spaces, "_access", PostgresAccessStore(pool))
        monkeypatch.setattr(
            profile_images,
            "_images",
            ProfileImages(PostgresProfileImageStore(pool), InMemoryProfileImageObjects()),
        )
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/business",
                "headers": [],
                "app": SimpleNamespace(
                    state=SimpleNamespace(financial_accounts_pool=pool)
                ),
            }
        )
        request.state.request_id = str(uuid4())
        yield pool, request, context


def create_account(request, context):
    return business.create_account(
        request,
        Response(),
        business.CreateBusinessAccount(
            type="checking", currency="DOP", nickname=uuid4().hex
        ),
        idempotency_key=uuid4().hex,
        context=context,
    )


@pytest.mark.parametrize("operation", ["email", "account", "logo"])
def test_two_management_requests_reuse_their_grant_connections(management, operation):
    pool, request, context = management
    ready = Barrier(2, timeout=3)

    def run():
        with contextmanager(require_business_management)(request, context) as guarded:
            ready.wait()
            if operation == "email":
                result = email_routes.create_receiving_address(
                    request, Response(), guarded
                )
                assert result["receiving_address"] is not None
            elif operation == "account":
                result = create_account(request, guarded)
                assert result["currency"] == "DOP"
                return result["id"]
            else:
                assert business_logo.delete_logo(request, guarded).status_code == 204
                assert (
                    business_logo._payload(
                        request, context.scope.owner.space_id, guarded.connection
                    )["id"]
                    == context.scope.owner.space_id
                )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(run) for _ in range(2)]
        for future in futures:
            account_id = future.result(timeout=4)
            if operation == "account":
                assert (
                    context.service.imports.money.accounts.get(
                        user_id=context.scope.person_id,
                        account_id=account_id,
                        scope=context.scope.owner,
                    ).account.id
                    == account_id
                )
    assert pool.get_stats().get("requests_waiting", 0) == 0


def test_management_failure_rolls_back_account_write(management):
    pool, request, context = management
    with pytest.raises(RuntimeError, match="abort"):
        with contextmanager(require_business_management)(request, context) as guarded:
            result = create_account(request, guarded)
            raise RuntimeError("abort")
    with pool.connection() as connection:
        assert (
            connection.execute(
                "select id from public.financial_accounts where id = %s", (result["id"],)
            ).fetchone()
            is None
        )
    # A failed request returns its slot and cannot leave a borrowed connection behind.
    with contextmanager(require_business_management)(request, context) as guarded:
        assert create_account(request, guarded)["currency"] == "DOP"


def test_management_invalid_grant_denies_before_writing(management):
    pool, request, context = management
    denied = replace(context, scope=replace(context.scope, grant_id=str(uuid4())))
    with pytest.raises(HTTPException) as error:
        with contextmanager(require_business_management)(request, denied):
            pytest.fail("Invalid grant reached the route")
    assert error.value.status_code == 403
    assert pool.get_stats().get("requests_waiting", 0) == 0


@pytest.mark.parametrize("callback", ["account", "catalog"])
def test_bank_callbacks_reuse_authorized_transaction(
    management, actions, monkeypatch, callback
):
    from argus.domain.business.bank.service import bank_matching_service

    pool, request, context = management
    _, actor, grant = actions
    account_id = UUID(create_account(request, context)["id"])
    monkeypatch.setattr(bank_matching, "business_bank_matching_enabled", lambda: True)
    monkeypatch.setattr(
        financial_accounts, "_service", context.service.imports.money.accounts
    )
    bank_matching.start_bank_matching(request.app)
    service = bank_matching_service()
    assert service is not None
    ready = Barrier(2, timeout=3)

    def run():
        with service.store.authorized_transaction(actor.actor, grant, "prepare"):
            ready.wait()
            if callback == "account":
                found = service.account_of(
                    actor.actor.space_id, UUID(actor.owner_id), account_id
                )
                assert found.account_id == account_id
            else:
                assert (
                    service.catalog.approved_targets(
                        actor.actor.space_id,
                        kind="receipt",
                        period_start=date(2026, 1, 1),
                        period_end=date(2026, 12, 31),
                    )
                    == ()
                )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(run) for _ in range(2)]
            for future in futures:
                future.result(timeout=4)
    finally:
        bank_matching.stop_bank_matching(request.app)


def test_concurrent_refund_dossiers_reuse_owner_transaction(management, actions, monkeypatch):
    from threading import local

    from argus.domain.business.contracts.actions import ReviewDraft
    from argus.domain.business.contracts.facts import BusinessFactPatch

    pool, _, _ = management
    service, actor, _ = actions
    draft, version = shared_actions.create(service, actor)
    service.review(
        actor, draft,
        ReviewDraft(version=version, facts=BusinessFactPatch.model_validate({
            "kind": {"state": "known", "value": "refund"},
            "currency": {"state": "known", "value": "DOP"},
            "occurred_on": {"state": "known", "value": "2026-10-01"},
        })), str(uuid4()),
    )
    monkeypatch.setattr(service.authority, "pool", pool)
    ready, seen = Barrier(2, timeout=3), local()
    getconn = pool.getconn

    def acquire(*args, **kwargs):
        connection = getconn(*args, **kwargs)
        if not getattr(seen, "arrived", False):
            seen.arrived = True
            ready.wait()
        return connection

    monkeypatch.setattr(pool, "getconn", acquire)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(service.dossier, actor, draft) for _ in range(2)]
        for future in futures:
            result = future.result(timeout=4)
            assert result.facts.kind.value == "refund"
            assert result.refund_candidates == ()
