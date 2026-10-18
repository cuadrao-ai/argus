"""Hermetic transport contract. The production lifecycle gate remains closed."""

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from argus.api.business import require_business_person, require_business_surface
from argus.api.routers import business_lifecycle as transport
from argus.domain.business.lifecycle import BusinessLifecycleError, LifecycleResult
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.test_business_lifecycle_postgres import shared, users, world  # noqa: F401

SPACE = str(uuid4())
ACTOR = str(uuid4())
CLOSED = datetime(2026, 10, 18, tzinfo=timezone.utc)


class Service:
    def __init__(self):
        self.calls = []
        self.error = None

    def close(self, **command):
        return self.command("close", command)

    def reopen(self, **command):
        return self.command("reopen", command)

    def command(self, action, command):
        self.calls.append((action, command))
        if self.error:
            raise BusinessLifecycleError(self.error)
        return LifecycleResult(
            SPACE, "Taller Luna", CLOSED if action == "close" else None
        )

    def closed_spaces(self, owner_id):
        self.calls.append(("list", owner_id))
        return (LifecycleResult(SPACE, "Taller Luna", CLOSED),)


@pytest.fixture
def client():
    app = FastAPI()

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = "lifecycle-test"
        return await call_next(request)

    service = Service()
    app.include_router(transport.router, prefix="/api/v1")
    app.dependency_overrides[require_business_surface] = lambda: None
    app.dependency_overrides[require_business_person] = lambda: SimpleNamespace(
        person_id=ACTOR
    )
    app.dependency_overrides[transport.require_lifecycle] = lambda: service
    app.dependency_overrides[transport.require_lifecycle_ready] = lambda: None
    with TestClient(app) as browser:
        yield browser, service, app


def test_gate_cannot_be_enabled_by_mounting_the_router(client):
    browser, service, app = client
    del app.dependency_overrides[transport.require_lifecycle_ready]
    response = browser.post(
        f"/api/v1/business/spaces/{SPACE}/close",
        json={"confirmation": "Taller Luna"},
        headers={"Idempotency-Key": "close-1"},
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "business_unavailable"
    assert response.headers["cache-control"] == "no-store"
    assert service.calls == []


@pytest.mark.parametrize("action", ["close", "reopen"])
def test_command_uses_authenticated_actor_and_preserves_key(client, action):
    browser, service, _ = client
    body = {"confirmation": "Taller Luna"} if action == "close" else None
    response = browser.post(
        f"/api/v1/business/spaces/{SPACE}/{action}",
        json=body,
        headers={"Idempotency-Key": "command-1"},
    )
    assert response.status_code == 200, response.text
    command = {"owner_id": ACTOR, "space_id": SPACE, "idempotency_key": "command-1"}
    if action == "close":
        command["confirmation"] = "Taller Luna"
    assert service.calls == [(action, command)]
    assert response.json()["space_id"] == SPACE
    assert (response.json()["reopen_until"] is not None) == (action == "close")
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "code,status",
    [
        ("business_name_mismatch", 422),
        ("invalid_idempotency_key", 422),
        ("business_record_not_found", 404),
        ("business_reopen_expired", 409),
        ("business_already_open", 409),
        ("idempotency_conflict", 409),
    ],
)
def test_domain_refusals_are_private_typed_problems(client, code, status):
    browser, service, _ = client
    service.error = code
    response = browser.post(
        f"/api/v1/business/spaces/{SPACE}/close",
        json={"confirmation": "Taller Luna"},
        headers={"Idempotency-Key": "close-1"},
    )
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "body,key",
    [
        ({}, "key"),
        ({"confirmation": 4}, "key"),
        ({"confirmation": "Luna", "owner_id": ACTOR}, "key"),
        ({"confirmation": "Luna"}, None),
    ],
)
def test_invalid_commands_never_reach_the_service(client, body, key):
    browser, service, _ = client
    headers = {"Idempotency-Key": key} if key else {}
    response = browser.post(
        f"/api/v1/business/spaces/{SPACE}/close", json=body, headers=headers
    )
    assert response.status_code == 422
    assert service.calls == []


def test_owner_identity_cannot_be_selected_in_query_or_payload(client):
    browser, service, _ = client
    response = browser.get("/api/v1/business/closed-spaces?owner_id=someone-else")
    assert response.status_code == 200
    assert service.calls == [("list", ACTOR)]
    assert response.json()["spaces"][0]["space_id"] == SPACE


@pytest.mark.skipif(not shared.DSN, reason="Disposable database required")
@pytest.mark.parametrize("actor", ["owner", "other", "guest", "missing"])
def test_real_database_route_enforces_owner_and_closed_member_access(
    client,
    world,  # noqa: F811
    actor,
):
    from argus.domain.business.lifecycle import PostgresBusinessLifecycle

    browser, _, app = client
    pool, space, identities, access, _ = world
    actor_id = identities.get(actor, str(uuid4()))
    app.dependency_overrides[require_business_person] = lambda: SimpleNamespace(
        person_id=actor_id
    )
    app.dependency_overrides[transport.require_lifecycle] = (
        lambda: PostgresBusinessLifecycle(pool)
    )
    result = browser.post(
        f"/api/v1/business/spaces/{space.id}/close",
        json={"confirmation": space.name},
        headers={"Idempotency-Key": "route-close"},
    )
    if actor == "owner":
        assert result.status_code == 200, result.text
        assert access.spaces_for(identities["other"]) == ()
        listed = browser.get("/api/v1/business/closed-spaces")
        assert [item["space_id"] for item in listed.json()["spaces"]] == [space.id]
        reopened = browser.post(
            f"/api/v1/business/spaces/{space.id}/reopen",
            headers={"Idempotency-Key": "route-reopen"},
        )
        assert reopened.status_code == 200, reopened.text
        assert access.spaces_for(identities["other"])
    else:
        assert result.status_code == 404
        assert result.json()["detail"]["code"] == "business_record_not_found"
        assert browser.get("/api/v1/business/closed-spaces").json() == {"spaces": []}
