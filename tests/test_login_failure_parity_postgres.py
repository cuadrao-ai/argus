"""Real routed login failure parity on local Auth and Postgres admission stores."""

from __future__ import annotations

import os
import secrets
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from argus.api import state as api_state
from argus.api.main import app
from argus.api.routers import auth as auth_router
from faker import Faker
from fastapi.testclient import TestClient
from psycopg import Connection

from tests import test_financial_accounts_postgres as shared
from tests.local_supabase_support import local_supabase_gateway
from tests.test_financial_accounts_api_postgres import ORIGIN

pytestmark = pytest.mark.skipif(
    not (shared.DSN and os.getenv("ARGUS_LOCAL_SUPABASE_URL")),
    reason="local Supabase Auth proof variables are not configured",
)

API = "/api/v1"
ENV = {
    "CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED": "false",
    "CUADRAO_BUSINESS_INVITE_ADMISSION_ENABLED": "true",
    "NEXT_PUBLIC_MOCK_AUTH": "false",
    "CUADRAO_MOCK_AUTH": "false",
    "ARGUS_DEV_MEMORY_FALLBACK": "false",
}
CAPTCHA = "local-captcha-proof"
fake = Faker()
_EXPECTED = {
    "title": "Unauthorized",
    "status": 401,
    "detail": "Invalid email or password.",
    "code": "unauthorized",
}


def _public_body(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "request_id"}


def _allowlist(world: SimpleNamespace, email: str) -> None:
    world.allowlisted.append(email)
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "insert into public.private_alpha_allowlist (email, role) values (%s, 'user')",
            (email,),
        )


@pytest.fixture
def login_world(monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    auth_router.reset_auth_attempt_limiter_for_tests()
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    gateway = local_supabase_gateway()
    created: list[str] = []
    allowlisted: list[str] = []
    try:
        with (
            patch.object(api_state, "supabase_gateway", gateway),
            patch.object(api_state, "DATABASE_URL", shared.DSN),
            patch.object(api_state, "PERSISTENCE_MODE", "supabase"),
            TestClient(app, base_url="http://localhost:3000") as client,
        ):
            yield SimpleNamespace(
                client=client, gateway=gateway, created=created, allowlisted=allowlisted
            )
    finally:
        try:
            for user_id in created:
                gateway.client.auth.admin.delete_user(user_id)
        finally:
            if allowlisted:
                with Connection.connect(shared.DSN) as db:
                    db.execute(
                        "delete from public.private_alpha_allowlist where email = any(%s)",
                        (allowlisted,),
                    )


def _create_auth_user(world, *, email: str, password: str) -> str:  # noqa: ANN001
    user = world.gateway.client.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    )
    assert user.user is not None
    user_id = str(user.user.id)
    world.created.append(user_id)
    return user_id


def _login(world, *, email: str, password: str, captcha_token: str = CAPTCHA):  # noqa: ANN001, ANN201
    return world.client.post(
        f"{API}/auth/login",
        json={"email": email, "password": password, "captcha_token": captcha_token},
        headers=ORIGIN,
    )


def test_postgres_login_denial_and_wrong_password_share_one_public_contract(
    login_world,
) -> None:  # noqa: ANN001
    password = f"Pw-{secrets.token_urlsafe(18)}"
    admitted = fake.unique.email(domain="example.test").lower()
    denied = fake.unique.email(domain="example.test").lower()
    admitted_id = _create_auth_user(login_world, email=admitted, password=password)
    _create_auth_user(login_world, email=denied, password=password)
    _allowlist(login_world, admitted)

    wrong_password = _login(
        login_world,
        email=admitted,
        password=f"wrong-{password}",
    )
    denied_login = _login(login_world, email=denied, password=password)

    assert wrong_password.status_code == denied_login.status_code == 401
    assert _public_body(wrong_password.json()) == _public_body(denied_login.json())
    assert _public_body(wrong_password.json()) == {
        **_EXPECTED,
        "type": "https://api.argus.app/problems/unauthorized",
    }
    assert wrong_password.headers.get("set-cookie") is None
    assert denied_login.headers.get("set-cookie") is None

    admitted_login = _login(login_world, email=admitted, password=password)

    assert admitted_login.status_code == 200
    assert admitted_login.json()["user"]["id"] == admitted_id
    assert admitted_login.cookies.get("sb-auth-token")
    assert admitted_login.cookies.get("sb-refresh-token")
