import json
import os
from uuid import uuid4

import psycopg
import pytest
from argus.api import state as api_state
from argus.api.dependencies import current_user
from argus.api.guest_access import registered_account_context, store_account_context
from argus.api.routers import profile
from argus.api.schemas import User
from argus.domain.store import utcnow
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="disposable PostgreSQL not configured")


@pytest.fixture
def owners(monkeypatch):
    ids = [str(uuid4()), str(uuid4())]
    with psycopg.connect(DSN) as connection:
        for user_id in ids:
            connection.execute(
                "insert into auth.users (id, email) values (%s, %s)",
                (user_id, f"session-{user_id}@example.test"),
            )
        for user_id, subject in zip(
            ids, ["session-owner-apple", "session-other-apple"], strict=True
        ):
            connection.execute(
                "insert into auth.identities (id,user_id,provider,provider_id,identity_data) values (%s,%s,'apple',%s,%s::jsonb)",
                (str(uuid4()), user_id, subject, json.dumps({"sub": subject})),
            )
    monkeypatch.setattr(api_state, "DATABASE_URL", DSN)
    monkeypatch.setattr(api_state, "supabase_gateway", None)
    app = FastAPI()
    app.include_router(profile.router)

    def authenticated_owner(request: Request):
        user_id = request.headers["X-Synthetic-Owner"]
        assert user_id in ids
        store_account_context(request, registered_account_context(user_id))
        request.state.request_id = "profile-apple-postgres"
        return User(
            id=user_id,
            email=f"session-{user_id}@example.test",
            created_at=utcnow(),
            updated_at=utcnow(),
        )

    app.dependency_overrides[current_user] = authenticated_owner
    yield ids, TestClient(app)
    with psycopg.connect(DSN) as connection:
        connection.execute(
            "delete from auth.identities where user_id = any(%s::uuid[])", (ids,)
        )
        connection.execute("delete from auth.users where id = any(%s::uuid[])", (ids,))


@pytest.mark.parametrize("method", ["GET", "PATCH"])
def test_me_reads_only_authenticated_owners_linked_subject(owners, method):
    ids, client = owners
    for user_id, subject in zip(
        ids, ["session-owner-apple", "session-other-apple"], strict=True
    ):
        response = client.request(
            method, "/api/v1/me",
            headers={"X-Synthetic-Owner": user_id},
            **({"json": {"currency_override": "USD"}} if method == "PATCH" else {}),
        )
        assert response.status_code == 200
        assert response.json()["user"]["id"] == user_id
        assert response.json()["apple_identity"] == {"subject": subject}


@pytest.mark.parametrize("mutation", ["absent", "malformed", "conflicting"])
def test_me_distinguishes_absence_from_unverifiable_identity(owners, mutation):
    ids, client = owners
    with psycopg.connect(DSN) as connection:
        if mutation == "absent":
            connection.execute("delete from auth.identities where user_id=%s", (ids[0],))
        elif mutation == "malformed":
            connection.execute(
                "update auth.identities set identity_data='{}'::jsonb where user_id=%s",
                (ids[0],),
            )
        else:
            connection.execute(
                "insert into auth.identities (id,user_id,provider,provider_id,identity_data) values (%s,%s,'apple','conflicting-session-subject','{\"sub\":\"conflicting-session-subject\"}'::jsonb)",
                (str(uuid4()), ids[0]),
            )
    response = client.get("/api/v1/me", headers={"X-Synthetic-Owner": ids[0]})
    if mutation == "absent":
        assert response.status_code == 200
        assert response.json()["apple_identity"] is None
    else:
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "apple_identity_unavailable"


def test_real_local_auth_session_only_exposes_its_owner(monkeypatch):
    if not os.getenv("ARGUS_LOCAL_SUPABASE_URL"):
        pytest.skip("isolated local Supabase Auth not configured")
    from urllib.parse import urlsplit

    import httpx
    from argus.api.main import app

    from tests.local_supabase_support import local_supabase_gateway

    origin = os.environ["ARGUS_LOCAL_SUPABASE_URL"]
    assert urlsplit(origin).hostname in {"127.0.0.1", "localhost"}
    headers = {
        "apikey": os.environ["ARGUS_LOCAL_SUPABASE_SERVICE_ROLE_KEY"],
        "Authorization": "Bearer " + os.environ["ARGUS_LOCAL_SUPABASE_SERVICE_ROLE_KEY"],
    }
    ids, tokens, emails = [], [], []
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    monkeypatch.setenv("ARGUS_DEV_MEMORY_FALLBACK", "false")
    monkeypatch.setattr(api_state, "DATABASE_URL", DSN)
    monkeypatch.setattr(api_state, "supabase_gateway", local_supabase_gateway())
    try:
        for index in range(2):
            email = f"apple-session-proof-{uuid4()}@example.test"
            password = str(uuid4()) + "Aa!"
            response = httpx.post(
                origin + "/auth/v1/admin/users",
                headers=headers,
                json={"email": email, "password": password, "email_confirm": True},
                timeout=5,
            )
            assert response.status_code == 200, "local Auth creation failed"
            user_id = response.json()["id"]
            ids.append(user_id)
            emails.append(email)
            login = httpx.post(
                origin + "/auth/v1/token?grant_type=password",
                headers={"apikey": os.environ["ARGUS_LOCAL_SUPABASE_ANON_KEY"]},
                json={"email": email, "password": password},
                timeout=5,
            )
            assert login.status_code == 200, "local Auth sign-in failed"
            tokens.append(login.json()["access_token"])
            subject = f"local-session-owner-{index}"
            with psycopg.connect(DSN) as connection:
                connection.execute(
                    "insert into public.private_alpha_allowlist (email, role) values (%s, 'user')",
                    (email,),
                )
                connection.execute(
                    "insert into auth.identities (id,user_id,provider,provider_id,identity_data,created_at,updated_at,last_sign_in_at) values (%s,%s,'apple',%s,%s::jsonb,now(),now(),now())",
                    (
                        str(uuid4()),
                        user_id,
                        subject,
                        json.dumps({"sub": subject, "email": email}),
                    ),
                )
        client = TestClient(app)
        anonymous = client.get("/api/v1/me")
        assert anonymous.status_code == 401
        assert "local-session-owner" not in anonymous.text
        for index, token in enumerate(tokens):
            result = client.get(
                "/api/v1/me",
                headers={"Authorization": "Bearer " + token},
                params={"user_id": ids[1 - index]},
            )
            assert result.status_code == 200, f"owner profile status {result.status_code}"
            assert result.json()["user"]["id"] == ids[index]
            assert result.json()["apple_identity"] == {
                "subject": f"local-session-owner-{index}"
            }
            assert f"local-session-owner-{1-index}" not in result.text
    finally:
        with psycopg.connect(DSN) as connection:
            connection.execute(
                "delete from public.private_alpha_allowlist where email=any(%s)",
                (emails,),
            )
            connection.execute(
                "delete from auth.identities where user_id=any(%s::uuid[]) and provider='apple'",
                (ids,),
            )
        for user_id in ids:
            response = httpx.delete(
                origin + "/auth/v1/admin/users/" + user_id, headers=headers, timeout=5
            )
            assert response.status_code == 200, "local Auth fixture cleanup failed"
