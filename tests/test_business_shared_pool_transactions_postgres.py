"""Borrowing preserves transaction, response, and external-cleanup boundaries."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from threading import Barrier, Event, current_thread, local
from unittest.mock import Mock
from uuid import uuid4

import pytest
from argus.api import profile_images
from argus.api.business import (
    require_business_document_write,
    require_business_management,
)
from argus.api.routers import business, business_logo
from argus.api.routers import email_intake as email_routes
from argus.domain.business.contracts.actions import ApproveExpense, ReviewDraft
from argus.domain.business.contracts.facts import BusinessFactPatch
from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository
from argus.domain.ingestion.contract import ImportCandidate, SourceRef
from argus.domain.ingestion.reconcile.service import ReconciliationService
from argus.domain.ingestion.reconcile.store_postgres import PostgresImportStore
from argus.domain.owner_scope import PERSONAL
from argus.domain.profile_images import ProfileImageStorageUnavailable
from argus.domain.profile_images import business as logo_subject
from argus.domain.recording import canonical_groups
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from tests import test_business_actions_postgres as shared_actions
from tests import test_business_shared_pool_postgres as shared_pool
from tests.profile_images.pictures import png

actions = shared_actions.actions
users = shared_actions.users
management = shared_pool.management
pytestmark = [
    pytest.mark.owner_acts,
    pytest.mark.skipif(
        not shared_actions.shared.DSN, reason="Disposable PostgreSQL required"
    ),
]



@pytest.mark.parametrize("management", [False], indirect=True)
def test_concurrent_first_receiving_address_requests_share_live_route(
    management, monkeypatch
):
    from argus.domain.ingestion.email_intake.store import PostgresEmailStore

    pool, _, context = management
    store = PostgresEmailStore(pool)
    space_id = context.scope.owner.space_id
    assert store.route_for_space(space_id) is None
    monkeypatch.setenv("CUADRAO_BUSINESS_EMAIL_DOMAIN", "recibos.example.test")
    monkeypatch.setattr(
        email_routes, "ingestion_hub", lambda: Mock(sink=context.service.imports)
    )
    monkeypatch.setattr(email_routes, "email_receiving_available", lambda: True)
    create_route = PostgresEmailStore.create_route
    ready = Barrier(2, timeout=5)

    def concurrent_create(self, **kwargs):
        # Both HTTP requests must pass the no-address read before either inserts.
        ready.wait()
        return create_route(self, **kwargs)

    monkeypatch.setattr(PostgresEmailStore, "create_route", concurrent_create)
    app = FastAPI()
    app.state.financial_accounts_pool = pool
    app.dependency_overrides[require_business_document_write] = lambda: context
    app.add_api_route(
        "/business/email", email_routes.create_receiving_address,
        methods=["POST"], status_code=201,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    client.post, "/business/email",
                    json={"alias": "recibos" + uuid4().hex[:12]},
                )
                for _ in range(2)
            ]
            responses = [future.result(timeout=10) for future in futures]
    assert [response.status_code for response in responses] == [201, 201]
    addresses = [response.json()["receiving_address"] for response in responses]
    assert addresses[0] is not None and addresses[0] == addresses[1]
    assert all(response.json()["enabled"] for response in responses)
    route = store.route_for_space(space_id)
    assert route is not None and route.recipient == addresses[0]
    with pool.connection() as connection:
        assert connection.execute(
            "select count(*) from public.business_email_routes where space_id=%s and active",
            (space_id,),
        ).fetchone()[0] == 1
    assert pool.get_stats().get("requests_waiting", 0) == 0


def test_refund_dossier_is_coherent_while_money_approval_commits(
    management, actions, monkeypatch
):
    pool, _, _ = management
    service, actor, _ = actions
    expense = shared_actions.ready(service, actor)
    refund, version = shared_actions.create(service, actor)
    service.review(
        actor,
        refund,
        ReviewDraft(
            version=version,
            facts=BusinessFactPatch.model_validate(
                {
                    "kind": {"state": "known", "value": "refund"},
                    "currency": {"state": "known", "value": "DOP"},
                    "occurred_on": {"state": "known", "value": "2026-10-01"},
                }
            ),
        ),
        str(uuid4()),
    )
    monkeypatch.setattr(service.authority, "pool", pool)
    staged, proceed, committed = Event(), Event(), Event()
    write = service.imports.money.write

    def paused_write(*args, **kwargs):
        staged.set()
        assert proceed.wait(3)
        result = write(*args, **kwargs)
        committed.set()
        return result

    monkeypatch.setattr(service.imports.money, "write", paused_write)
    reader = current_thread()
    load = canonical_groups.load_owner

    def interleaved_load(*args, **kwargs):
        result = load(*args, **kwargs)
        if current_thread() is reader:
            proceed.set()
            committed.wait(0.2)
        return result

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            service.approve,
            actor,
            expense,
            ApproveExpense(version=1, action="record_expense"),
            str(uuid4()),
        )
        assert staged.wait(3)
        monkeypatch.setattr(canonical_groups, "load_owner", interleaved_load)
        try:
            result = service.dossier(actor, refund)
            assert result.facts.kind.value == "refund"
        finally:
            proceed.set()
        assert future.result(timeout=3).outcome == "applied"


def test_lost_logo_delete_reply_cannot_restore_metadata(management, monkeypatch):
    pool, request, context = management
    images = profile_images.profile_images()
    subject = logo_subject(context.scope.owner.space_id)
    images.replace(subject, png(), "image/png")
    remove = images.objects.remove

    def lost_reply(path):
        remove(path)
        raise ProfileImageStorageUnavailable("Synthetic lost delete response")

    monkeypatch.setattr(images.objects, "remove", lost_reply)
    with pytest.raises(HTTPException) as error:
        with contextmanager(require_business_management)(request, context) as guarded:
            business_logo.delete_logo(request, guarded)
    assert error.value.status_code == 503
    with pool.connection() as connection:
        assert (
            connection.execute(
                "select 1 from public.business_logos where space_id=%s", (subject.id,)
            ).fetchone()
            is None
        )
    assert subject.path not in images.objects.objects


@pytest.mark.parametrize("cancelled", [False, True])
def test_rolled_back_logo_delete_keeps_its_object(management, cancelled):
    import asyncio

    _, request, context = management
    images = profile_images.profile_images()
    subject = logo_subject(context.scope.owner.space_id)
    images.replace(subject, png(), "image/png")
    failure = asyncio.CancelledError if cancelled else RuntimeError
    with pytest.raises(failure):
        with contextmanager(require_business_management)(request, context) as guarded:
            business_logo.delete_logo(request, guarded)
            raise failure()
    assert images.url(subject) is not None
    assert subject.path in images.objects.objects


@pytest.mark.parametrize("operation", ["account", "email", "logo"])
def test_management_response_waits_for_guard_commit(management, operation):
    pool, _, context = management

    class FailedCommit:
        def __init__(self, connection):
            self.connection = connection
            self.depth = 0

        def __getattr__(self, name):
            return getattr(self.connection, name)

        @contextmanager
        def transaction(self):
            self.depth += 1
            try:
                with self.connection.transaction():
                    yield
                    if self.depth == 1:
                        raise RuntimeError("Synthetic commit rejection")
            finally:
                self.depth -= 1

    class CommitFailingPool:
        @contextmanager
        def connection(self):
            with pool.connection() as connection:
                yield FailedCommit(connection)

    app = FastAPI()
    app.state.financial_accounts_pool = CommitFailingPool()
    app.dependency_overrides[require_business_document_write] = lambda: context
    endpoint = {
        "account": business.create_account,
        "email": email_routes.stop_receiving,
        "logo": business_logo.delete_logo,
    }[operation]
    app.add_api_route("/operation", endpoint, methods=["POST"], status_code=201)
    nickname = str(uuid4())
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/operation",
            json={"type": "checking", "currency": "DOP", "nickname": nickname},
            headers={"Idempotency-Key": str(uuid4())},
        )
    assert response.status_code == 500
    with pool.connection() as connection:
        assert (
            connection.execute(
                "select 1 from public.financial_accounts where nickname=%s", (nickname,)
            ).fetchone()
            is None
        )


@pytest.mark.parametrize("business_scoped", [False, True])
def test_two_intake_submissions_reuse_the_live_source_connection(
    users, monkeypatch, business_scoped
):
    now = datetime.now(timezone.utc)
    with ConnectionPool(
        shared_actions.shared.DSN, min_size=2, max_size=2, timeout=0.5
    ) as pool:
        sources = PostgresConnectionRepository(pool)
        jobs = []
        for user in (users["owner"], users["other"]):
            scope = PERSONAL
            if business_scoped:
                from argus.domain.business.spaces import PostgresSpaceStore
                from argus.domain.owner_scope import BusinessSpace

                space, _ = PostgresSpaceStore(pool).create(user, "Synthetic Business")
                scope = BusinessSpace(space.id)
            source = sources.create(
                user_id=user,
                source="statement",
                external_ref=str(uuid4()),
                label=None,
                now=now,
                scope=scope,
            )
            candidate = ImportCandidate(
                source=SourceRef(
                    source="statement",
                    connection_id=source.id,
                    external_id="proof",
                    observed_at=now,
                ),
                evidence="transaction",
                amount="10",
                currency="DOP",
                direction="outflow",
            )
            jobs.append((user, source.id, candidate, scope))
        service = ReconciliationService(
            PostgresImportStore(pool), Mock(), lambda: now, connections=sources
        )
        ready, seen = Barrier(2, timeout=3), local()
        getconn = pool.getconn

        def acquire(*args, **kwargs):
            connection = getconn(*args, **kwargs)
            if not getattr(seen, "arrived", False):
                seen.arrived = True
                ready.wait()
            return connection

        monkeypatch.setattr(pool, "getconn", acquire)

        def submit(job):
            user, source, candidate, scope = job
            return service.submit(
                user_id=user, connection_id=source, candidates=[candidate], scope=scope
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(submit, job) for job in jobs]
            for future in futures:
                assert future.result(timeout=4).recorded == 1


def test_two_invite_deliveries_borrow_labels_without_losing_claims(users, monkeypatch):
    from types import SimpleNamespace

    from argus.api import business_invite_delivery, business_spaces
    from argus.domain.business.access import PostgresAccessStore
    from argus.domain.business.roles import BusinessRole
    from argus.domain.business.spaces import PostgresSpaceStore

    with ConnectionPool(
        shared_actions.shared.DSN, min_size=2, max_size=2, timeout=0.5
    ) as pool:
        spaces, access = PostgresSpaceStore(pool), PostgresAccessStore(pool)
        monkeypatch.setattr(business_spaces, "_spaces", spaces)
        monkeypatch.setattr(business_spaces, "_access", access)
        monkeypatch.setattr(
            business_invite_delivery, "invitations_available", lambda: True
        )
        send = Mock()
        monkeypatch.setattr(business_invite_delivery, "send_invite_email", send)
        jobs = []
        for owner in (users["owner"], users["other"]):
            space, _ = spaces.create(owner, "Synthetic Business")
            _, listing = access.give(
                space.id, owner, f"invite-{uuid4().hex}@example.test", BusinessRole.VIEWER
            )
            jobs.append((listing, listing.invites[0], space.id, owner))
        ready = Barrier(2, timeout=3)
        original = business_invite_delivery._send_invite

        def synchronized_send(*args, **kwargs):
            ready.wait()
            return original(*args, **kwargs)

        monkeypatch.setattr(business_invite_delivery, "_send_invite", synchronized_send)
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    business_invite_delivery.deliver_invite, SimpleNamespace(), *job
                )
                for job in jobs
            ]
            assert [future.result(timeout=4) for future in futures] == [
                "accepted",
                "accepted",
            ]
        assert send.call_count == 2
        # Already accepted claims are replayed without sending again.
        for job in jobs:
            assert (
                business_invite_delivery.deliver_invite(SimpleNamespace(), *job)
                == "accepted"
            )
        assert send.call_count == 2


def test_concurrent_expense_receipt_reads_use_the_grant_connection(
    management, actions, monkeypatch
):
    from dataclasses import replace
    from datetime import date

    from argus.domain.business import transactions

    from tests.test_business_receipt_views_postgres import _web

    pool, _, _ = management
    service, actor, _ = actions
    expense = shared_actions.ready(service, actor)
    approved = service.approve(
        actor, expense, ApproveExpense(version=1, action="record_expense"), str(uuid4())
    )
    assert approved.outcome == "applied"
    now = datetime.now(timezone.utc)
    source = PostgresConnectionRepository(pool).create(
        user_id=actor.owner_id,
        source="statement",
        external_ref=str(uuid4()),
        label=None,
        now=now,
        scope=actor.scope,
    )
    candidate = ImportCandidate(
        source=SourceRef(
            source="statement",
            connection_id=source.id,
            external_id="receipt-link",
            observed_at=now,
        ),
        evidence="transaction",
        amount="850",
        currency="DOP",
        direction="outflow",
    )
    service.imports.submit(
        user_id=actor.owner_id,
        connection_id=source.id,
        candidates=[candidate],
        scope=actor.scope,
    )
    with service.imports.store.transaction(actor.owner_id, scope=actor.scope) as tx:
        observation = tx.observation(source.id, "receipt-link")
        tx.put_observation(replace(observation, event_id=str(expense)))
    monkeypatch.setattr(service.authority, "pool", pool)
    web = _web(service, actor)
    ready = Barrier(2, timeout=3)
    lock = transactions.lock_owner

    def synchronized_lock(connection, owner):
        ready.wait()
        lock(connection, owner)

    monkeypatch.setattr(transactions, "lock_owner", synchronized_lock)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                web.service.expenses, web.scope, date(2026, 10, 1), date(2026, 10, 31)
            )
            for _ in range(2)
        ]
        for future in futures:
            [result] = future.result(timeout=4)
            assert result["id"] == str(approved.activity_id)
