"""Management operations keep the grant lock without reacquiring its pool."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from argus.api import business_spaces, email_intake, profile_images
from argus.api.business import BusinessContext, require_business_management
from argus.api.routers import business, business_logo
from argus.api.routers import email_intake as email_routes
from argus.domain.business.access import PostgresAccessStore
from argus.domain.business.scope import BusinessScope
from argus.domain.business.service import BusinessService
from argus.domain.business.spaces import PostgresSpaceStore
from argus.domain.ingestion.email_intake.service import EmailCapture, grant_route_authority
from argus.domain.ingestion.email_intake.store import PostgresEmailStore
from argus.domain.owner_scope import BusinessSpace
from argus.domain.profile_images import ProfileImages
from argus.domain.profile_images.objects import InMemoryProfileImageObjects
from argus.domain.profile_images.store import PostgresProfileImageStore
from fastapi import Request, Response
from psycopg_pool import ConnectionPool

from tests.test_business_actions_postgres import actions as actions
from tests.test_business_actions_postgres import shared
from tests.test_business_actions_postgres import users as users

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
        context = BusinessContext(scope, BusinessService(Mock(), service.imports, lambda _: frozenset()))
        monkeypatch.setattr(service.imports.money.accounts._repository, "_pool", pool)
        runtime = EmailCapture(PostgresEmailStore(pool), Mock(), grant_route_authority(pool), Mock(), lambda: True)
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
        monkeypatch.setattr(profile_images, "_images", ProfileImages(PostgresProfileImageStore(pool), InMemoryProfileImageObjects()))
        request = Request({"type": "http", "method": "POST", "path": "/business", "headers": [], "app": SimpleNamespace(state=SimpleNamespace(financial_accounts_pool=pool))})
        request.state.request_id = str(uuid4())
        yield pool, request, context


def create_account(request, context):
    return business.create_account(
        request,
        Response(),
        business.CreateBusinessAccount(type="checking", currency="DOP", nickname=uuid4().hex),
        idempotency_key=uuid4().hex,
        context=context,
    )


@pytest.mark.parametrize("operation", ["email", "account", "logo"])
def test_two_management_requests_reuse_their_grant_connections(management, operation):
    pool, request, context = management
    ready = Barrier(2, timeout=3)

    def run():
        permission = require_business_management(request, context)
        guarded = next(permission)
        try:
            ready.wait()
            if operation == "email":
                result = email_routes.create_receiving_address(request, Response(), guarded)
                assert result["receiving_address"] is not None
            elif operation == "account":
                assert create_account(request, guarded)["currency"] == "DOP"
            else:
                assert business_logo.delete_logo(request, guarded).status_code == 204
        finally:
            permission.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(run) for _ in range(2)]
        for future in futures:
            future.result(timeout=4)
    assert pool.get_stats().get("requests_waiting", 0) == 0
