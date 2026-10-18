from dataclasses import dataclass
from uuid import uuid4

import pytest
from argus.api.business import require_business_person, require_business_surface
from argus.api.routers.business_lifecycle import require_lifecycle_ready
from argus.api.routers.business_transfer import require_transfer, router
from argus.domain.business.lifecycle import BusinessLifecycleError
from argus.domain.business.transfer import TransferDetails
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests import test_business_lifecycle_postgres as lifecycle
from tests import test_financial_accounts_postgres as shared


@dataclass
class Person:
    person_id: str


class Service:
    def __init__(self):
        self.calls = []
        self.error = None
        self.result = TransferDetails(
            str(uuid4()),
            str(uuid4()),
            str(uuid4()),
            str(uuid4()),
            "pending",
            business_name="Taller Luna",
            owner_name="Ana",
            target_name="Rosa",
            role="target",
        )

    def request(self, **kwargs):
        return self._called("request", kwargs)

    def accept(self, **kwargs):
        return self._called("accept", kwargs)

    def decline(self, **kwargs):
        return self._called("decline", kwargs)

    def cancel(self, **kwargs):
        return self._called("withdraw", kwargs)

    def discover(self, **kwargs):
        self.calls.append(("discover", kwargs))
        return (self.result,)

    def _called(self, kind, kwargs):
        self.calls.append((kind, kwargs))
        if self.error:
            raise BusinessLifecycleError(self.error)
        return self.result


@pytest.fixture
def client():
    app = FastAPI()

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = "synthetic-transfer-route"
        return await call_next(request)

    app.include_router(router, prefix="/api/v1")
    service = Service()
    person = Person(str(uuid4()))
    app.dependency_overrides[require_business_surface] = lambda: None
    app.dependency_overrides[require_business_person] = lambda: person
    app.dependency_overrides[require_transfer] = lambda: service
    with TestClient(app) as transport:
        yield transport, service, person, app


def test_transfer_readiness_denial_precedes_transport(client):
    transport, service, _, _ = client
    reply = transport.post(
        f"/api/v1/business/ownership-transfers/{service.result.id}/accept"
    )
    assert reply.status_code == 404 and not service.calls


def test_request_passes_actual_actor_target_and_original_key(client):
    transport, service, person, app = client
    app.dependency_overrides[require_lifecycle_ready] = lambda: None
    target = str(uuid4())
    reply = transport.post(
        f"/api/v1/business/spaces/{service.result.space_id}/ownership-transfers",
        headers={"Idempotency-Key": "same-request"},
        json={"target_grant_id": target, "confirmation": "Taller Luna"},
    )
    assert reply.status_code == 200
    assert reply.json()["id"] == service.result.id
    assert reply.headers["cache-control"] == "no-store"
    assert service.calls == [
        (
            "request",
            dict(
                owner_id=person.person_id,
                space_id=service.result.space_id,
                target_grant_id=target,
                confirmation="Taller Luna",
                idempotency_key="same-request",
            ),
        )
    ]


@pytest.mark.parametrize("action", ["accept", "decline", "withdraw"])
def test_terminal_commands_derive_authenticated_actor(client, action):
    transport, service, person, app = client
    app.dependency_overrides[require_lifecycle_ready] = lambda: None
    reply = transport.post(
        f"/api/v1/business/ownership-transfers/{service.result.id}/{action}"
    )
    assert reply.status_code == 200
    actor = "owner_id" if action == "withdraw" else "actor_id"
    assert service.calls == [
        (action, {actor: person.person_id, "transfer_id": service.result.id})
    ]


@pytest.mark.parametrize(
    "code,status",
    [
        ("business_transfer_target_invalid", 409),
        ("business_transfer_not_pending", 409),
        ("business_transfer_pending", 409),
        ("business_transfer_expired", 409),
        ("business_record_not_found", 404),
    ],
)
def test_known_domain_refusals_remain_private(client, code, status):
    transport, service, _, app = client
    app.dependency_overrides[require_lifecycle_ready] = lambda: None
    service.error = code
    reply = transport.post(
        f"/api/v1/business/ownership-transfers/{service.result.id}/accept"
    )
    assert reply.status_code == status
    assert reply.headers["cache-control"] == "no-store"


world = lifecycle.world
users = lifecycle.users


def test_transfer_link_discovery_is_authenticated_read_only(client):
    transport, service, person, app = client
    app.dependency_overrides[require_lifecycle_ready] = lambda: None
    reply = transport.get("/api/v1/business/ownership-transfers")
    assert reply.status_code == 200
    assert reply.headers["cache-control"] == "no-store"
    assert reply.json()["transfers"][0]["id"] == service.result.id
    assert service.calls == [("discover", {"actor_id": person.person_id})]


@pytest.mark.skipif(not shared.DSN, reason="Disposable database required")
def test_expired_get_discovery_does_not_change_history_or_send_email(client, world):
    from argus.domain.business.transfer import PostgresBusinessTransfer

    from tests.test_business_transfer_mail_postgres import expire

    transport, _, person, app = client
    pool, space, people, _, member = world
    service = PostgresBusinessTransfer(pool)
    pending = service.request(
        owner_id=people["owner"],
        space_id=space.id,
        target_grant_id=member.id,
        confirmation=space.name,
        idempotency_key="read-link",
    )
    expire(world, pending)
    person.person_id = people["other"]
    app.dependency_overrides[require_lifecycle_ready] = lambda: None
    app.dependency_overrides[require_transfer] = lambda: service
    for _ in range(2):
        reply = transport.get("/api/v1/business/ownership-transfers")
        assert reply.json()["transfers"][0]["status"] == "expired"
    with pool.connection() as db:
        assert db.execute(
            "select status,resolved_at from public.business_ownership_transfers where id=%s",
            (pending.id,),
        ).fetchone() == ("pending", None)
        assert (
            db.execute(
                "select count(*) from public.business_transfer_mail_outbox where transfer_id=%s",
                (pending.id,),
            ).fetchone()[0]
            == 1
        )


@pytest.mark.skipif(not shared.DSN, reason="Disposable database required")
def test_transfer_http_accept_saves_current_owner_and_preserves_custody(client, world):
    from argus.domain.business.transfer import PostgresBusinessTransfer

    transport, _, person, app = client
    pool, space, people, _, member = world
    app.dependency_overrides[require_lifecycle_ready] = lambda: None
    app.dependency_overrides[require_transfer] = lambda: PostgresBusinessTransfer(pool)
    person.person_id = people["owner"]
    pending = transport.post(
        f"/api/v1/business/spaces/{space.id}/ownership-transfers",
        headers={"Idempotency-Key": "route-transfer"},
        json={"target_grant_id": member.id, "confirmation": space.name},
    )
    assert pending.status_code == 200
    person.person_id = people["other"]
    reply = transport.post(
        f"/api/v1/business/ownership-transfers/{pending.json()['id']}/accept"
    )
    assert reply.status_code == 200 and reply.json()["status"] == "accepted"
    with pool.connection() as db:
        assert db.execute(
            "select current_owner_id::text,created_by::text from public.spaces where id=%s",
            (space.id,),
        ).fetchone() == (people["other"], people["owner"])


@pytest.mark.skipif(not shared.DSN, reason="Disposable database required")
def test_transfer_http_wrong_recipient_leaves_request_pending(client, world):
    from argus.domain.business.transfer import PostgresBusinessTransfer

    transport, _, person, app = client
    pool, space, people, _, member = world
    app.dependency_overrides[require_lifecycle_ready] = lambda: None
    app.dependency_overrides[require_transfer] = lambda: PostgresBusinessTransfer(pool)
    person.person_id = people["owner"]
    pending = transport.post(
        f"/api/v1/business/spaces/{space.id}/ownership-transfers",
        headers={"Idempotency-Key": "route-wrong"},
        json={"target_grant_id": member.id, "confirmation": space.name},
    )
    person.person_id = people["guest"]
    reply = transport.post(
        f"/api/v1/business/ownership-transfers/{pending.json()['id']}/accept"
    )
    assert reply.status_code == 404
    with pool.connection() as db:
        assert (
            db.execute(
                "select status from public.business_ownership_transfers where id=%s",
                (pending.json()["id"],),
            ).fetchone()[0]
            == "pending"
        )
