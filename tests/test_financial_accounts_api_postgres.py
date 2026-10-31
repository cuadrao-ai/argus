"""Financial accounts through the real API, Auth and Postgres.

Needs the local Supabase proof variables (``ARGUS_LOCAL_SUPABASE_URL``,
``ARGUS_LOCAL_SUPABASE_ANON_KEY``, ``ARGUS_LOCAL_SUPABASE_SERVICE_ROLE_KEY``)
and ``ARGUS_DISPOSABLE_DATABASE_URL``. A real anonymous session is refused, two
real registered sessions cannot see each other, and every write lands in the
disposable database through the production repository.
"""

from __future__ import annotations

import os
import secrets
from contextlib import suppress
from unittest.mock import patch
from uuid import uuid4

import pytest
from argus.api import state as api_state
from argus.api.main import app
from argus.api.routers import auth as auth_router
from fastapi.testclient import TestClient

from tests.local_supabase_support import local_supabase_gateway

LOCAL_SUPABASE_URL = os.getenv("ARGUS_LOCAL_SUPABASE_URL", "").strip()
LOCAL_ANON_KEY = os.getenv("ARGUS_LOCAL_SUPABASE_ANON_KEY", "").strip()
LOCAL_SERVICE_ROLE_KEY = os.getenv("ARGUS_LOCAL_SUPABASE_SERVICE_ROLE_KEY", "").strip()
LOCAL_DATABASE_URL = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not (
        LOCAL_SUPABASE_URL
        and LOCAL_ANON_KEY
        and LOCAL_SERVICE_ROLE_KEY
        and LOCAL_DATABASE_URL
    ),
    reason="local Supabase proof variables are not configured",
)

psycopg = pytest.importorskip("psycopg")
ORIGIN = {"origin": "http://localhost:3000"}


def _login(client: TestClient, gateway, label: str, created: list[str]) -> dict[str, str]:  # noqa: ANN001
    email = f"fin-{label}-{secrets.token_hex(4)}@example.test"
    password = f"Pw-{secrets.token_urlsafe(18)}"
    user = gateway.client.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    )
    assert user.user is not None
    created.append(str(user.user.id))
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": password,
            "captcha_token": "local-captcha-proof",
        },
        headers=ORIGIN,
    )
    assert response.status_code == 200, response.text
    token = response.json()["session"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_real_sessions_create_reopen_edit_and_stay_isolated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("ARGUS_FINANCIAL_ACCOUNTS_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    gateway = local_supabase_gateway()
    created_users: list[str] = []
    try:
        with (
            patch.object(api_state, "supabase_gateway", gateway),
            patch.object(api_state, "DATABASE_URL", LOCAL_DATABASE_URL),
            patch.object(api_state, "PERSISTENCE_MODE", "supabase"),
            TestClient(app, base_url="http://localhost:3000") as client,
        ):
            # A real anonymous session is a guest: refused before any read or write.
            guest = client.post(
                "/api/v1/auth/guest",
                json={"age_confirmed_at": "2026-01-01T00:00:00Z", "captcha_token": "local-captcha-proof", "language": "en"},
                headers=ORIGIN,
            )
            assert guest.status_code == 200, guest.text
            created_users.append(str(guest.json()["user"]["id"]))
            guest_headers = {
                "Authorization": f"Bearer {guest.json()['session']['access_token']}"
            }
            refused = client.post(
                "/api/v1/financial-accounts",
                json={"type": "cash", "currency": "DOP", "amount": "1"},
                headers={**guest_headers, "Idempotency-Key": "guest-try"},
            )
            assert (refused.status_code, refused.json()["code"]) == (
                403,
                "account_conversion_required",
            )
            assert (
                client.get(
                    "/api/v1/financial-accounts", headers=guest_headers
                ).status_code
                == 403
            )

            alice = _login(client, gateway, "alice", created_users)
            bob = _login(client, gateway, "bob", created_users)

            body = {
                "type": "checking",
                "currency": "DOP",
                "nickname": "Cuenta nomina",
                "amount": "12500.00",
                "as_of": "2026-09-01T09:00:00-04:00",
            }
            created = client.post(
                "/api/v1/financial-accounts",
                json=body,
                headers={**alice, "Idempotency-Key": "real-create"},
            )
            assert created.status_code == 201, created.text
            account = created.json()
            assert account["balance"]["amount_minor"] == 1_250_000
            assert account["balance"]["as_of"] == "2026-09-01T09:00:00-04:00"

            reopened = client.get(
                f"/api/v1/financial-accounts/{account['id']}", headers=alice
            )
            assert reopened.status_code == 200
            assert reopened.json() == account

            replay = client.post(
                "/api/v1/financial-accounts",
                json=body,
                headers={**alice, "Idempotency-Key": "real-create"},
            )
            assert replay.status_code == 200
            assert replay.json() == account
            conflict = client.post(
                "/api/v1/financial-accounts",
                json={**body, "amount": "1.00"},
                headers={**alice, "Idempotency-Key": "real-create"},
            )
            assert (conflict.status_code, conflict.json()["code"]) == (
                409,
                "idempotency_conflict",
            )

            blank_cash = client.post(
                "/api/v1/financial-accounts",
                json={"type": "cash", "currency": "USD"},
                headers={**alice, "Idempotency-Key": str(uuid4())},
            )
            assert blank_cash.status_code == 201
            assert blank_cash.json()["balance"]["state"] == "known"
            assert blank_cash.json()["balance"]["amount_minor"] == 0
            assert blank_cash.json()["opening"]["amount_minor"] == 0
            assert client.get(
                f"/api/v1/financial-accounts/{blank_cash.json()['id']}", headers=alice
            ).json() == blank_cash.json()

            unknown = client.post(
                "/api/v1/financial-accounts",
                json={"type": "property", "currency": "USD"},
                headers={**alice, "Idempotency-Key": str(uuid4())},
            )
            assert unknown.status_code == 201
            assert unknown.json()["balance"]["state"] == "unknown"
            assert unknown.json()["balance"]["amount_minor"] is None
            assert unknown.json()["opening"] is None

            # Bob holds a real registered session and still sees nothing of Alice's.
            assert client.get("/api/v1/financial-accounts", headers=bob).json() == {
                "accounts": []
            }
            for response in (
                client.get(f"/api/v1/financial-accounts/{account['id']}", headers=bob),
                client.patch(
                    f"/api/v1/financial-accounts/{account['id']}",
                    json={"expected_version": 1, "nickname": "Mine"},
                    headers=bob,
                ),
                client.put(
                    f"/api/v1/financial-accounts/{account['id']}/opening",
                    json={
                        "expected_version": 1,
                        "expected_revision": 1,
                        "amount": "0",
                        "reason": "drain",
                    },
                    headers=bob,
                ),
            ):
                assert (response.status_code, response.json()["code"]) == (
                    404,
                    "financial_account_not_found",
                )

            edited = client.patch(
                f"/api/v1/financial-accounts/{account['id']}",
                json={"expected_version": 1, "nickname": "Nomina", "type": "savings"},
                headers=alice,
            )
            assert edited.status_code == 200, edited.text
            assert (
                edited.json()["nickname"],
                edited.json()["type"],
                edited.json()["version"],
            ) == (
                "Nomina",
                "savings",
                2,
            )
            stale = client.patch(
                f"/api/v1/financial-accounts/{account['id']}",
                json={"expected_version": 1, "nickname": "Otra"},
                headers=alice,
            )
            assert (stale.status_code, stale.json()["code"]) == (409, "stale_version")

            corrected = client.put(
                f"/api/v1/financial-accounts/{account['id']}/opening",
                json={
                    "expected_version": 2,
                    "expected_revision": 1,
                    "amount": "12000.00",
                    "reason": "typo",
                },
                headers=alice,
            )
            assert corrected.status_code == 200, corrected.text
            assert corrected.json()["balance"]["amount_minor"] == 1_200_000
            assert corrected.json()["version"] == 3
            assert [
                (item["revision"], item["amount_minor"], item["reason"])
                for item in corrected.json()["opening"]["revisions"]
            ] == [(1, 1_250_000, None), (2, 1_200_000, "typo")]

            listed = client.get("/api/v1/financial-accounts", headers=alice).json()[
                "accounts"
            ]
            assert sorted(item["id"] for item in listed) == sorted(
                [account["id"], blank_cash.json()["id"], unknown.json()["id"]]
            )

        with psycopg.connect(LOCAL_DATABASE_URL) as connection:
            alice_id = created_users[1]
            rows = connection.execute(
                "select count(*) from public.financial_accounts where user_id = %s",
                (alice_id,),
            ).fetchone()
            assert rows == (3,)
            revisions = connection.execute(
                "select record_id::text, revision, amount_minor, reason, recorded_by::text"
                " from public.financial_record_revisions where user_id = %s order by record_id, revision",
                (alice_id,),
            ).fetchall()
            assert revisions == sorted([
                (account["opening"]["record_id"], 1, 1_250_000, None, alice_id),
                (account["opening"]["record_id"], 2, 1_200_000, "typo", alice_id),
                (blank_cash.json()["opening"]["record_id"], 1, 0, None, alice_id),
            ])
            guest_rows = connection.execute(
                "select count(*) from public.financial_accounts where user_id = %s",
                (created_users[0],),
            ).fetchone()
            assert guest_rows == (0,)
    finally:
        for user_id in created_users:
            with suppress(Exception):
                gateway.delete_auth_user(user_id)
