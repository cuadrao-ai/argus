"""Over HTTP, on the real app, Auth and Postgres: ``GET /business/setup`` reads
each step from the Business's saved facts, leaves out a step whose feature is
off, and answers only someone who may manage the Business."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from argus.api import state as api_state
from argus.api.main import app
from argus.api.routers import auth as auth_router
from fastapi.testclient import TestClient
from psycopg import Connection

from tests import test_financial_accounts_postgres as shared
from tests.business_cleanup import delete_spaces
from tests.local_supabase_support import local_supabase_gateway
from tests.test_business_scope_switch_routes_postgres import (
    API,
    ENV,
    _as,
    _grant,
    _person,
)
from tests.test_business_scope_switch_routes_postgres import (
    pytestmark as _local_supabase,
)

pytestmark = _local_supabase


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """Alice opens a Business under the default name; Bob has no access yet."""

    auth_router.reset_auth_attempt_limiter_for_tests()
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(
        "argus.domain.business.invite_email.send_resend_email",
        lambda **message: "fake-receipt",
    )
    gateway = local_supabase_gateway()
    created: list[str] = []
    try:
        with (
            patch.object(api_state, "supabase_gateway", gateway),
            patch.object(api_state, "DATABASE_URL", shared.DSN),
            patch.object(api_state, "PERSISTENCE_MODE", "supabase"),
            TestClient(app, base_url="http://localhost:3000") as client,
        ):
            people = {
                label: _person(client, gateway, label, created)
                for label in ("alice", "bob")
            }
            started = client.post(
                f"{API}/business/space", json={}, headers=people["alice"].headers
            )
            assert started.status_code == 201, started.text
            people["alice"].space_id = started.json()["id"]
            yield SimpleNamespace(client=client, **people)
    finally:
        with Connection.connect(shared.DSN) as db:
            db.execute(
                "delete from public.business_client_grants where grantee_id=any(%s::uuid[]) or issuer_id=any(%s::uuid[])",
                (created, created),
            )
            db.execute("set constraints all deferred")
            delete_spaces(db, "created_by=any(%s::uuid[])", (created,))
        for user_id in created:
            try:
                gateway.delete_auth_user(user_id)
            except Exception:  # noqa: BLE001
                pass


def _steps(world, headers: dict) -> dict[str, dict]:  # noqa: ANN001
    response = world.client.get(f"{API}/business/setup", headers=headers)
    assert response.status_code == 200, response.text
    return {step["key"]: step for step in response.json()["steps"]}


def _profile(world, name: str, previous: str, tax_id: dict | None, before: dict | None):  # noqa: ANN001, ANN202
    saved = world.client.patch(
        f"{API}/business/fiscal-profile",
        json={"name": name, "previous_name": previous, "tax_id": tax_id, "previous_tax_id": before},
        headers={**world.alice.headers, "Idempotency-Key": str(uuid4())},
    )
    assert saved.status_code == 200, saved.text


def test_each_step_follows_the_saved_facts(world):  # noqa: ANN001
    alice = world.alice
    steps = _steps(world, alice.headers)
    # Email receiving and WhatsApp are off on this server: their steps are not sent.
    assert "receiving_address" not in steps
    assert "whatsapp" not in steps
    assert steps["created"] == {"key": "created", "required": True, "done": True}
    assert steps["fiscal_identity"] == {"key": "fiscal_identity", "required": True, "done": False}
    assert steps["team"] == {"key": "team", "required": False, "done": False}

    reading = world.client.get(f"{API}/business/receipt-reading", headers=alice.headers).json()
    if reading["available"]:
        assert steps["receipt_reading"] == {"key": "receipt_reading", "required": True, "done": reading["enabled"]}
    else:
        assert "receipt_reading" not in steps

    rnc = {"type": "rnc", "value": "199990013"}
    _profile(world, "Mi negocio", "Mi negocio", rnc, None)
    assert _steps(world, alice.headers)["fiscal_identity"]["done"] is False, "a default name is not a legal name"
    _profile(world, "Ferretería Prueba", "Mi negocio", rnc, rnc)
    assert _steps(world, alice.headers)["fiscal_identity"]["done"] is True

    grant = _grant(world, alice, world.bob)
    assert _steps(world, alice.headers)["team"]["done"] is True

    refused = world.client.get(f"{API}/business/setup", headers=_as(world.bob, grant))
    assert refused.status_code == 403, "setup is configuration: read and prepare may not read it"


def test_setup_is_complete_when_every_required_step_is_done(world):  # noqa: ANN001
    rnc = {"type": "rnc", "value": "199990013"}
    _profile(world, "Ferretería Prueba", "Mi negocio", rnc, None)
    steps = _steps(world, world.alice.headers).values()
    open_required = [step["key"] for step in steps if step["required"] and not step["done"]]
    reading = world.client.get(f"{API}/business/receipt-reading", headers=world.alice.headers).json()
    assert open_required == (["receipt_reading"] if reading["available"] else [])
