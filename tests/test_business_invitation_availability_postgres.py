"""Business invitation readiness on production routes and real Postgres."""

from __future__ import annotations

import os
import secrets
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import psycopg
import pytest
from argus.api import state as api_state
from argus.api.main import app
from argus.api.routers import auth as auth_router
from fastapi.testclient import TestClient

from tests import test_financial_accounts_postgres as shared
from tests.local_supabase_support import local_supabase_gateway
from tests.test_financial_accounts_api_postgres import ORIGIN

pytestmark = pytest.mark.skipif(
    not (shared.DSN and os.getenv("ARGUS_LOCAL_SUPABASE_URL")),
    reason="local Supabase proof variables are not configured",
)
API = "/api/v1"
ENV = {
    "CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED": "true",
    "NEXT_PUBLIC_MOCK_AUTH": "false",
    "CUADRAO_MOCK_AUTH": "false",
    "ARGUS_DEV_MEMORY_FALLBACK": "false",
    "ARGUS_BUSINESS_PILOT_ENABLED": "true",
    "CUADRAO_BUSINESS_INVITE_ADMISSION_ENABLED": "true",
    "CUADRAO_BUSINESS_INVITE_EMAIL_ENABLED": "true",
    "CUADRAO_APP_ORIGIN": "https://app.example.test",
}


def _login(client: TestClient, gateway, label: str, created: list[str]) -> dict:  # noqa: ANN001
    email = f"invite-cap-{label}-{secrets.token_hex(4)}@example.test"
    password = f"Pw-{secrets.token_urlsafe(18)}"
    user = gateway.client.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    )
    assert user.user is not None
    created.append(str(user.user.id))
    response = client.post(
        f"{API}/auth/login",
        json={"email": email, "password": password, "captcha_token": "local-captcha-proof"},
        headers=ORIGIN,
    )
    assert response.status_code == 200, response.text
    token = response.json()["session"]["access_token"]
    return {
        "id": str(user.user.id),
        "email": email,
        "headers": {"Authorization": f"Bearer {token}", **ORIGIN},
    }


def _invite_snapshot(db: psycopg.Connection, space_id: str) -> tuple:
    invites = db.execute(
        "select id::text, email, delivery_state, expires_at, supersedes_id::text"
        " from public.business_access_invites where space_id=%s order by created_at",
        (space_id,),
    ).fetchall()
    commands = db.execute(
        "select command_key from argus_private.business_invitation_commands"
        " where space_id=%s order by command_key",
        (space_id,),
    ).fetchall()
    ledger = db.execute(
        "select command->>'action', idempotency_key"
        " from public.business_action_receipts"
        " where space_id=%s and turn_key is null order by created_at, idempotency_key",
        (space_id,),
    ).fetchall()
    return invites, commands, ledger


def _invite_counts(db: psycopg.Connection, space_id: str) -> tuple[int, int, int]:
    invites = db.execute(
        "select count(*) from public.business_access_invites where space_id=%s",
        (space_id,),
    ).fetchone()[0]
    commands = db.execute(
        "select count(*) from argus_private.business_invitation_commands where space_id=%s",
        (space_id,),
    ).fetchone()[0]
    ledger = db.execute(
        "select count(*) from public.business_action_receipts"
        " where space_id=%s and command->>'action'='invite_access'",
        (space_id,),
    ).fetchone()[0]
    return invites, commands, ledger


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    auth_router.reset_auth_attempt_limiter_for_tests()
    created: list[str] = []
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    gateway = local_supabase_gateway()
    monkeypatch.setattr(
        "argus.domain.business.invite_email.send_resend_email",
        lambda **message: "fake-receipt",
    )
    try:
        with (
            patch.object(api_state, "supabase_gateway", gateway),
            patch.object(api_state, "DATABASE_URL", shared.DSN),
            patch.object(api_state, "PERSISTENCE_MODE", "supabase"),
            TestClient(app, base_url="http://localhost:3000") as client,
        ):
            owner_a = _login(client, gateway, "owner-a", created)
            owner_b = _login(client, gateway, "owner-b", created)
            started_a = client.post(
                f"{API}/business/space",
                json={"name": "Negocio A"},
                headers=owner_a["headers"],
            )
            started_b = client.post(
                f"{API}/business/space",
                json={"name": "Negocio B"},
                headers=owner_b["headers"],
            )
            assert started_a.status_code == 201 and started_b.status_code == 201
            yield SimpleNamespace(
                client=client,
                gateway=gateway,
                owner_a={**owner_a, "space_id": started_a.json()["id"]},
                owner_b={**owner_b, "space_id": started_b.json()["id"]},
                created=created,
            )
    finally:
        with psycopg.connect(shared.DSN) as db:
            for user_id in created:
                db.execute(
                    "delete from public.business_client_grants where grantee_id=%s or issuer_id=%s",
                    (user_id, user_id),
                )
            db.execute(
                "delete from auth.users where id = any(%s::uuid[])", (created,)
            )


@pytest.mark.parametrize(
    ("email_on", "admission_on", "origin_on", "expect_available"),
    [
        (False, False, False, False),
        (True, False, False, False),
        (False, True, True, False),
        (True, True, False, False),
        (True, True, True, True),
    ],
)
def test_capability_projection_matches_configuration(
    world,
    monkeypatch: pytest.MonkeyPatch,
    email_on: bool,
    admission_on: bool,
    origin_on: bool,
    expect_available: bool,
) -> None:
    monkeypatch.setenv(
        "CUADRAO_BUSINESS_INVITE_EMAIL_ENABLED", "true" if email_on else "false"
    )
    monkeypatch.setenv(
        "CUADRAO_BUSINESS_INVITE_ADMISSION_ENABLED", "true" if admission_on else "false"
    )
    if origin_on:
        monkeypatch.setenv("CUADRAO_APP_ORIGIN", "https://app.example.test")
    else:
        monkeypatch.delenv("CUADRAO_APP_ORIGIN", raising=False)
        monkeypatch.delenv("ARGUS_APP_ORIGIN", raising=False)
    spaces = world.client.get(f"{API}/business/spaces", headers=world.owner_a["headers"])
    access = world.client.get(f"{API}/business/access", headers=world.owner_a["headers"])
    assert spaces.status_code == 200 and access.status_code == 200
    assert spaces.json()["invitations_available"] is expect_available
    assert access.json()["invitations_available"] is expect_available


def test_invitations_off_refuse_before_mutation(
    world, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CUADRAO_BUSINESS_INVITE_EMAIL_ENABLED", "false")
    space_id = world.owner_a["space_id"]
    with psycopg.connect(shared.DSN) as db:
        before = _invite_counts(db, space_id)
        before_rows = _invite_snapshot(db, space_id)
    refused = world.client.post(
        f"{API}/business/access",
        json={"email": f"guest-{uuid4().hex[:8]}@example.test"},
        headers=world.owner_a["headers"],
    )
    assert refused.status_code == 409
    assert refused.json()["code"] == "business_invitations_unavailable"
    batch = world.client.post(
        f"{API}/business/access/invitations",
        json={
            "recipients": [
                {
                    "email": f"batch-{uuid4().hex[:8]}@example.test",
                    "role": "editor",
                    "command_key": str(uuid4()),
                }
            ]
        },
        headers=world.owner_a["headers"],
    )
    assert batch.status_code == 409
    resent = world.client.post(
        f"{API}/business/access/invites/{uuid4()}/resend",
        headers=world.owner_a["headers"],
    )
    assert resent.status_code == 409
    assert resent.json()["code"] == "business_invitations_unavailable"
    with psycopg.connect(shared.DSN) as db:
        after = _invite_counts(db, space_id)
        after_rows = _invite_snapshot(db, space_id)
    assert after == before
    assert after_rows == before_rows


def test_invitations_off_blocks_resend_of_existing_invite_without_mutation(
    world, monkeypatch: pytest.MonkeyPatch
) -> None:
    email = f"stale-{uuid4().hex[:8]}@example.test"
    space_id = world.owner_a["space_id"]
    created = world.client.post(
        f"{API}/business/access",
        json={"email": email},
        headers=world.owner_a["headers"],
    )
    assert created.status_code == 201, created.text
    invite_id = created.json()["invites"][0]["id"]
    with psycopg.connect(shared.DSN) as db:
        before = _invite_snapshot(db, space_id)
    monkeypatch.setenv("CUADRAO_BUSINESS_INVITE_EMAIL_ENABLED", "false")
    resent = world.client.post(
        f"{API}/business/access/invites/{invite_id}/resend",
        headers=world.owner_a["headers"],
    )
    assert resent.status_code == 409
    with psycopg.connect(shared.DSN) as db:
        after = _invite_snapshot(db, space_id)
    assert after == before


def test_create_idempotency_replays_without_extra_mutation(world) -> None:
    key = str(uuid4())
    email = f"replay-{uuid4().hex[:8]}@example.test"
    space_id = world.owner_a["space_id"]
    body = {"email": email}
    first = world.client.post(
        f"{API}/business/access",
        json=body,
        headers={**world.owner_a["headers"], "Idempotency-Key": key},
    )
    assert first.status_code == 201, first.text
    with psycopg.connect(shared.DSN) as db:
        before = _invite_snapshot(db, space_id)
    second = world.client.post(
        f"{API}/business/access",
        json=body,
        headers={**world.owner_a["headers"], "Idempotency-Key": key},
    )
    assert second.status_code == 200, second.text
    with psycopg.connect(shared.DSN) as db:
        after = _invite_snapshot(db, space_id)
    assert after == before


def test_foreign_owner_cannot_resend_another_business_invite(
    world, monkeypatch: pytest.MonkeyPatch
) -> None:
    sends: list[str] = []
    monkeypatch.setattr(
        "argus.domain.business.invite_email.send_resend_email",
        lambda **message: sends.append(message["recipient"]) or "fake-receipt",
    )
    created = world.client.post(
        f"{API}/business/access",
        json={"email": f"tenant-{uuid4().hex[:8]}@example.test"},
        headers=world.owner_a["headers"],
    )
    assert created.status_code == 201
    invite_id = created.json()["invites"][0]["id"]
    resent = world.client.post(
        f"{API}/business/access/invites/{invite_id}/resend",
        headers=world.owner_b["headers"],
    )
    assert resent.status_code == 404
    assert len(sends) == 1


def test_configured_on_create_and_resend_persist(world) -> None:
    email = f"live-{uuid4().hex[:8]}@example.test"
    space_id = world.owner_a["space_id"]
    created = world.client.post(
        f"{API}/business/access",
        json={"email": email},
        headers=world.owner_a["headers"],
    )
    assert created.status_code == 201, created.text
    assert created.json()["invite_delivery"] == "accepted"
    [invite] = created.json()["invites"]
    resent = world.client.post(
        f"{API}/business/access/invites/{invite['id']}/resend",
        headers=world.owner_a["headers"],
    )
    assert resent.status_code == 200, resent.text
    assert resent.json()["invite_delivery"] == "accepted"
    with psycopg.connect(shared.DSN) as db:
        invites, commands, ledger = _invite_counts(db, space_id)
    assert invites >= 1 and ledger >= 1
