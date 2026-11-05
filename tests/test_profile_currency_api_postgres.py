from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from argus.api import state as api_state
from argus.api.main import app
from argus.api.routers import auth as auth_router
from fastapi.testclient import TestClient

from tests.local_supabase_support import local_supabase_gateway
from tests.test_financial_accounts_api_postgres import ORIGIN, _login

pytestmark = pytest.mark.skipif(
    not os.getenv("ARGUS_LOCAL_SUPABASE_URL"), reason="isolated local Supabase required"
)


def test_currency_roundtrip_preserves_concurrent_preference(monkeypatch):
    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    monkeypatch.setenv("ARGUS_DEV_MEMORY_FALLBACK", "false")
    gateway = local_supabase_gateway()
    created = []
    try:
        with (
            patch.object(api_state, "supabase_gateway", gateway),
            patch.object(
                api_state, "DATABASE_URL", os.environ["ARGUS_DISPOSABLE_DATABASE_URL"]
            ),
            TestClient(app, base_url="http://localhost:3000") as client,
        ):
            headers = _login(client, gateway, "currency", created)
            user_id = created[0]
            initial = client.patch(
                "/api/v1/me", json={"country": "DO"}, headers={**headers, **ORIGIN}
            )
            assert initial.status_code == 200
            assert initial.json()["user"]["currency"] == "DOP"
            original_read = gateway.get_user

            original_write = gateway.update_user

            def concurrent_edit_then_write(user_id, updates):
                gateway.client.table("profiles").update(
                    {"display_name": "Later user edit"}
                ).eq("id", user_id).execute()
                return original_write(user_id, updates)

            with patch.object(
                gateway, "update_user", side_effect=concurrent_edit_then_write
            ):
                saved = client.patch(
                    "/api/v1/me",
                    json={"currency_override": "USD"},
                    headers={**headers, **ORIGIN},
                )
            assert saved.status_code == 200
            assert saved.json()["user"]["display_name"] == "Later user edit"
            for reader in (client, TestClient(app, base_url="http://localhost:3000")):
                profile = reader.get("/api/v1/me", headers=headers).json()["user"]
                assert (
                    profile["country"],
                    profile["currency_override"],
                    profile["currency"],
                ) == ("DO", "USD", "USD")
            before = original_read(user_id=user_id)
            refused = client.patch(
                "/api/v1/me",
                json={"currency_override": "INVALID"},
                headers={**headers, **ORIGIN},
            )
            assert refused.status_code == 422
            assert original_read(user_id=user_id) == before
            with TestClient(app, base_url="http://localhost:3000") as stranger:
                refused = stranger.patch(
                    "/api/v1/me", json={"currency_override": "EUR"}, headers=ORIGIN
                )
            assert refused.status_code == 401
            assert original_read(user_id=user_id) == before
    finally:
        for user_id in created:
            gateway.client.auth.admin.delete_user(user_id)
