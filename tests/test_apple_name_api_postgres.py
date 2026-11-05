from __future__ import annotations

import json
import os
from unittest.mock import patch
from uuid import uuid4

import psycopg
import pytest
from argus.api import state as api_state
from argus.api.main import app
from argus.api.routers import auth as auth_router
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from tests.local_supabase_support import local_supabase_gateway
from tests.test_apple_name_deletion_postgres import (
    build_apple_service,
    deletion_service,
    profile,
)
from tests.test_financial_accounts_api_postgres import ORIGIN, _login

pytestmark = pytest.mark.skipif(
    not os.getenv("ARGUS_LOCAL_SUPABASE_URL"), reason="isolated Supabase Auth required"
)


def test_signed_auth_name_retry_relaunch_and_explicit_clear(monkeypatch):
    auth_router.reset_auth_attempt_limiter_for_tests()
    for flag in ("NEXT_PUBLIC_MOCK_AUTH", "CUADRAO_MOCK_AUTH", "ARGUS_DEV_MEMORY_FALLBACK"):
        monkeypatch.setenv(flag, "false")
    monkeypatch.setenv("CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_APPLE_REVOCATION_CAPTURE_ENABLED", "true")
    gateway = local_supabase_gateway()
    created = []
    dsn = os.environ["ARGUS_DISPOSABLE_DATABASE_URL"]
    try:
        with (
            patch.object(api_state, "supabase_gateway", gateway),
            patch.object(api_state, "DATABASE_URL", dsn),
            TestClient(app, base_url="http://localhost:3000") as client,
        ):
            headers = {**_login(client, gateway, "apple-name", created), **ORIGIN}
            user_id = created[0]
            subject = str(uuid4())
            with psycopg.connect(dsn) as connection:
                connection.execute(
                    "insert into auth.identities (id,user_id,provider,provider_id,identity_data,created_at,updated_at,last_sign_in_at) "
                    "values (%s,%s,'apple',%s,%s::jsonb,now(),now(),now())",
                    (str(uuid4()), user_id, subject, json.dumps({"sub": subject})),
                )
            saved = client.post(
                "/api/v1/me/apple-name",
                json={"display_name": "  María 李  "},
                headers=headers,
            )
            assert saved.status_code == 200
            assert saved.json()["apple_identity"] == {"subject": subject}
            assert saved.json()["user"]["display_name"] == "María 李"
            assert saved.json()["user"]["preferred_name"] is None
            retry = client.post(
                "/api/v1/me/apple-name",
                json={"display_name": "Other name"},
                headers=headers,
            )
            assert retry.status_code == 200
            assert retry.json()["apple_identity"] == {"subject": subject}
            assert retry.json()["user"]["display_name"] == "María 李"
            assert (
                client.patch(
                    "/api/v1/me", json={"display_name": None}, headers=headers
                ).status_code
                == 200
            )
            retry = client.post(
                "/api/v1/me/apple-name",
                json={"display_name": "Other name"},
                headers=headers,
            )
            assert retry.status_code == 200
            assert retry.json()["apple_identity"] == {"subject": subject}
            assert retry.json()["user"]["display_name"] is None
            with TestClient(app, base_url="http://localhost:3000") as restarted:
                assert (
                    restarted.get("/api/v1/me", headers=headers).json()["user"][
                        "display_name"
                    ]
                    is None
                )
            assert "name_initialization_closed" not in saved.json()["user"]
            denied = client.post(
                "/api/v1/me/apple-name",
                json={"display_name": "Other account", "user_id": str(uuid4())},
                headers=headers,
            )
            assert denied.status_code == 422
            from argus.domain.account_deletion.service import subject_hash

            with ConnectionPool(dsn, min_size=0, max_size=2) as pool:
                apple, provider = build_apple_service(user_id, pool)
                try:
                    deletion_service(pool, apple)._claim(user_id, subject_hash(user_id))
                    with psycopg.connect(dsn) as connection:
                        before = profile(connection, user_id)
                    with patch(
                        "argus.api.routers.profile_apple_name.initialize_apple_display_name"
                    ) as command:
                        denied = client.post(
                            "/api/v1/me/apple-name",
                            json={"display_name": "Later name"},
                            headers=headers,
                        )
                    assert denied.status_code == 401
                    command.assert_not_called()
                    with psycopg.connect(dsn) as connection:
                        assert profile(connection, user_id) == before
                    assert provider.calls == []
                finally:
                    apple.close()
    finally:
        for user_id in created:
            with psycopg.connect(dsn) as connection:
                connection.execute(
                    "delete from auth.identities where user_id=%s and provider='apple'",
                    (user_id,),
                )
                connection.execute(
                    "delete from public.apple_sign_in_credentials where user_id=%s",
                    (user_id,),
                )
                connection.execute(
                    "delete from argus_private.account_deletion_runs where user_id=%s",
                    (user_id,),
                )
            gateway.client.auth.admin.delete_user(user_id)
