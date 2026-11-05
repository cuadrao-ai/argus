"""Table density is a per-person profile preference, kept by the server.

Normal until the person chooses. Only compacto, normal and amplio are stored,
and choosing one leaves every other profile field as it was.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from argus.api import state as api_state
from argus.api.main import app
from argus.api.routers import auth as auth_router
from fastapi.testclient import TestClient
from psycopg import Connection

from tests.local_supabase_support import local_supabase_gateway
from tests.test_financial_accounts_api_postgres import ORIGIN, _login

pytestmark = pytest.mark.skipif(
    not os.getenv("ARGUS_LOCAL_SUPABASE_URL"), reason="isolated local Supabase required"
)


def test_density_is_normal_until_chosen_and_kept_per_person(monkeypatch) -> None:  # noqa: ANN001
    auth_router.reset_auth_attempt_limiter_for_tests()
    for name, value in {
        "CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED": "true",
        "NEXT_PUBLIC_MOCK_AUTH": "false",
        "CUADRAO_MOCK_AUTH": "false",
        "ARGUS_DEV_MEMORY_FALLBACK": "false",
    }.items():
        monkeypatch.setenv(name, value)
    gateway = local_supabase_gateway()
    created: list[str] = []
    dsn = os.environ["ARGUS_DISPOSABLE_DATABASE_URL"]
    try:
        with (
            patch.object(api_state, "supabase_gateway", gateway),
            patch.object(api_state, "DATABASE_URL", dsn),
            TestClient(app, base_url="http://localhost:3000") as client,
        ):
            headers = {**_login(client, gateway, "density", created), **ORIGIN}
            other = {**_login(client, gateway, "density-other", created), **ORIGIN}
            first = client.get("/api/v1/me", headers=headers).json()["user"]
            assert first["table_density"] == "normal"
            client.patch("/api/v1/me", json={"country": "DO"}, headers=headers)

            chosen = client.patch(
                "/api/v1/me", json={"table_density": "compacto"}, headers=headers
            )
            assert chosen.status_code == 200, chosen.text
            assert chosen.json()["user"]["table_density"] == "compacto"
            fresh = TestClient(app, base_url="http://localhost:3000")
            profile = fresh.get("/api/v1/me", headers=headers).json()["user"]
            assert (profile["table_density"], profile["country"]) == ("compacto", "DO")
            assert (
                client.get("/api/v1/me", headers=other).json()["user"]["table_density"]
                == "normal"
            )

            for bad in ("denso", None):
                refused = client.patch(
                    "/api/v1/me", json={"table_density": bad}, headers=headers
                )
                assert refused.status_code == 422, refused.text
            profile = client.get("/api/v1/me", headers=headers).json()["user"]
            assert profile["table_density"] == "compacto"
    finally:
        for user_id in created:
            try:
                gateway.delete_auth_user(user_id)
            except Exception:  # noqa: BLE001
                pass


def test_the_database_keeps_only_the_three_densities() -> None:
    with Connection.connect(os.environ["ARGUS_DISPOSABLE_DATABASE_URL"]) as db:
        default = db.execute(
            "select column_default, is_nullable from information_schema.columns"
            " where table_schema = 'public' and table_name = 'profiles'"
            " and column_name = 'table_density'"
        ).fetchone()
        assert default == ("'normal'::text", "NO")
        check = db.execute(
            "select pg_get_constraintdef(oid) from pg_constraint"
            " where conname = 'profiles_table_density_check'"
        ).fetchone()[0]
        assert check == (
            "CHECK ((table_density = ANY "
            "(ARRAY['compacto'::text, 'normal'::text, 'amplio'::text])))"
        )
