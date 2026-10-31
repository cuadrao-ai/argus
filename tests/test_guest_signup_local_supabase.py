"""Issue 480 real-Supabase proof for guest signup handoffs."""

from __future__ import annotations

import hashlib
import os
import re
import secrets
from contextlib import suppress
from datetime import datetime, timezone
from html import unescape
from typing import Any
from unittest.mock import patch

import psycopg
import pytest
from argus.api import state as api_state
from argus.api.main import app
from argus.api.routers import auth as auth_router
from argus.domain.owner_scope import PERSONAL
from fastapi.testclient import TestClient

from supabase import create_client
from tests.local_supabase_support import local_supabase_gateway as _gateway

LOCAL_URL = os.getenv("ARGUS_LOCAL_SUPABASE_URL", "").strip()
LOCAL_ANON_KEY = os.getenv("ARGUS_LOCAL_SUPABASE_ANON_KEY", "").strip()
LOCAL_SERVICE_KEY = os.getenv("ARGUS_LOCAL_SUPABASE_SERVICE_ROLE_KEY", "").strip()
LOCAL_DATABASE_URL = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()
LOCAL_MAILPIT_URL = os.getenv("ARGUS_LOCAL_MAILPIT_URL", "").strip()
LOCAL_AUTH_CONFIRMATIONS = (
    os.getenv("ARGUS_LOCAL_AUTH_EMAIL_CONFIRMATIONS_ENABLED", "").strip().lower()
    == "true"
)

pytestmark = pytest.mark.skipif(
    not all((LOCAL_URL, LOCAL_ANON_KEY, LOCAL_SERVICE_KEY, LOCAL_DATABASE_URL)),
    reason="local Supabase Auth proof is not configured",
)


def _mailpit_messages() -> list[dict[str, Any]]:
    import httpx

    response = httpx.get(f"{LOCAL_MAILPIT_URL}/api/v1/messages", timeout=10)
    response.raise_for_status()
    payload = response.json()
    messages = payload.get("messages")
    if not isinstance(messages, list):
        raise AssertionError("Mailpit returned an unexpected message list.")
    return [dict(message) for message in messages]


def _mailpit_message_for(email: str) -> dict[str, Any]:
    import httpx

    normalized = email.casefold()
    summaries = _mailpit_messages()
    summary = next(
        (
            message
            for message in summaries
            if any(
                str(recipient.get("Address") or "").casefold() == normalized
                for recipient in message.get("To") or []
            )
        ),
        None,
    )
    if summary is None:
        raise AssertionError(f"Mailpit has no message for {email}.")
    response = httpx.get(
        f"{LOCAL_MAILPIT_URL}/api/v1/message/{summary['ID']}", timeout=10
    )
    response.raise_for_status()
    return dict(response.json())


def _confirmation_url(message: dict[str, Any]) -> str:
    text = unescape(str(message.get("Text") or ""))
    url = next(
        (
            candidate
            for candidate in re.findall(r"https?://[^\s)]+", text)
            if "type=signup" in candidate
        ),
        None,
    )
    if url is None:
        raise AssertionError("The signup email has no confirmation URL.")
    return url


def _auth_audit_actions_for_user(user_id: str) -> list[str]:
    """Return Auth actions whether GoTrue records the user as actor or subject."""
    with psycopg.connect(LOCAL_DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "select payload ->> 'action' from auth.audit_log_entries "
                "where payload ->> 'actor_id' = %s "
                "or payload -> 'traits' ->> 'user_id' = %s "
                "order by created_at",
                (user_id, user_id),
            )
            return [str(row[0]) for row in cursor.fetchall()]


def test_real_guest_signup_replays_after_claim_commits_but_response_is_lost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    gateway = _gateway()
    email = f"guest-signup-{secrets.token_hex(6)}@example.test"
    password = f"Block3-{secrets.token_urlsafe(18)}"
    source_user_id: str | None = None
    destination_user_id: str | None = None
    conversation_id: str | None = None
    real_claim = gateway.claim_guest_workspace_handoff
    claim_attempts = 0

    def lose_first_claim_response(**kwargs: object) -> dict[str, object]:
        nonlocal claim_attempts
        claim_attempts += 1
        claimed = real_claim(**kwargs)  # type: ignore[arg-type]
        if claim_attempts == 1:
            raise RuntimeError("simulated_response_loss_after_claim")
        return claimed

    try:
        with (
            patch.object(api_state, "supabase_gateway", gateway),
            patch.object(api_state, "DATABASE_URL", LOCAL_DATABASE_URL),
            patch.object(
                gateway,
                "claim_guest_workspace_handoff",
                side_effect=lose_first_claim_response,
            ),
            TestClient(app, base_url="http://localhost:3000") as client,
        ):
            guest = client.post(
                "/api/v1/auth/guest",
                json={"age_confirmed_at": "2026-01-01T00:00:00Z", "captcha_token": "local-captcha-proof", "language": "en"},
                headers={"origin": "http://localhost:3000"},
            )
            assert guest.status_code == 200
            source_user_id = str(guest.json()["user"]["id"])
            conversation = client.post(
                "/api/v1/conversations",
                json={"title": "Signup handoff proof", "language": "en"},
            )
            assert conversation.status_code == 200
            conversation_id = str(conversation.json()["conversation"]["id"])
            gateway.client.table("messages").insert(
                {
                    "conversation_id": conversation_id,
                    "user_id": source_user_id,
                    "role": "user",
                    "content": "Preserve this exact message",
                }
            ).execute()

            prepared = client.post(
                "/api/v1/auth/guest/handoffs",
                json={
                    "handoff_kind": "new_account_signup",
                    "destination_email": email,
                    "source_conversation_id": conversation_id,
                },
                headers={"origin": "http://localhost:3000"},
            )
            assert prepared.status_code == 201
            signup_payload = {
                "age_confirmed_at": "2026-01-01T00:00:00Z",
                "email": email,
                "password": password,
                "captcha_token": "local-captcha-proof",
                "language": "en",
                "display_name": "Local signup proof",
            }
            first_signup = client.post(
                "/api/v1/auth/guest/signup",
                json=signup_payload,
                headers={"origin": "http://localhost:3000"},
            )
            if first_signup.status_code == 200:
                assert first_signup.json()["session"] is None
                destination_user_id = str(first_signup.json()["user"]["id"])
                assert LOCAL_MAILPIT_URL
                import httpx

                confirmation = httpx.get(
                    _confirmation_url(_mailpit_message_for(email)),
                    follow_redirects=False,
                    timeout=10,
                )
                assert confirmation.status_code == 303
                interrupted = client.post(
                    "/api/v1/auth/guest/signup",
                    json=signup_payload,
                    headers={"origin": "http://localhost:3000"},
                )
            else:
                interrupted = first_signup
            assert interrupted.status_code == 400

            signed_up = client.post(
                "/api/v1/auth/guest/signup",
                json=signup_payload,
                headers={"origin": "http://localhost:3000"},
            )

            assert signed_up.status_code == 200
            assert signed_up.json()["reconciled"] is True
            assert signed_up.json()["guest_claim"]["conversation_id"] == conversation_id
            destination_user_id = str(signed_up.json()["user"]["id"])
            assert destination_user_id != source_user_id
            assert signed_up.json()["user"]["email"] == email
            assert claim_attempts == 2
            access_token = str(signed_up.json()["session"]["access_token"])
            reloaded = client.get(
                "/api/v1/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )

        assert reloaded.status_code == 200
        assert reloaded.json()["account_kind"] == "registered"
        assert reloaded.json()["user"]["id"] == destination_user_id
        verified = gateway.get_auth_user_from_token(access_token)
        assert str(verified["id"]) == destination_user_id
        assert verified["is_anonymous"] is False
        assert str(verified["email"]).lower() == email
        preserved = (
            gateway.client.table("conversations")
            .select("id,user_id")
            .eq("id", conversation_id)
            .single()
            .execute()
            .data
        )
        assert preserved == {
            "id": conversation_id,
            "user_id": destination_user_id,
        }
        messages = (
            gateway.client.table("messages")
            .select("id,user_id,content")
            .eq("conversation_id", conversation_id)
            .execute()
            .data
        )
        assert len(messages) == 1
        assert messages[0]["user_id"] == destination_user_id
        assert messages[0]["content"] == "Preserve this exact message"
        workspace = (
            gateway.client.table("guest_workspaces")
            .select("status,claimed_by,conversation_id")
            .eq("user_id", source_user_id)
            .single()
            .execute()
            .data
        )
        assert workspace == {
            "status": "claimed",
            "claimed_by": destination_user_id,
            "conversation_id": conversation_id,
        }
        with psycopg.connect(LOCAL_DATABASE_URL) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select is_anonymous, email from auth.users where id = %s",
                    (source_user_id,),
                )
                assert cursor.fetchone() == (True, None)
            audit_actions = _auth_audit_actions_for_user(destination_user_id)
            assert "user_signedup" in audit_actions
            assert "user_modified" not in audit_actions
    finally:
        if destination_user_id:
            with suppress(Exception):
                gateway.delete_auth_user(destination_user_id)
        if source_user_id:
            with suppress(Exception):
                gateway.delete_auth_user(source_user_id)


def test_real_guest_signup_refuses_an_existing_permanent_account_without_merging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    gateway = _gateway()
    email = f"existing-guest-signup-{secrets.token_hex(6)}@example.test"
    existing_user_id: str | None = None
    source_user_id: str | None = None
    conversation_id: str | None = None
    try:
        created = gateway.client.auth.admin.create_user(
            {
                "email": email,
                "password": f"Existing-{secrets.token_urlsafe(18)}",
                "email_confirm": True,
                "user_metadata": {"language": "en"},
            }
        )
        assert created.user is not None
        existing_user_id = str(created.user.id)
        gateway.get_or_create_profile_for_auth_user(created.user.model_dump(mode="json"))

        with (
            patch.object(api_state, "supabase_gateway", gateway),
            patch.object(api_state, "DATABASE_URL", LOCAL_DATABASE_URL),
            TestClient(app, base_url="http://localhost:3000") as client,
        ):
            guest = client.post(
                "/api/v1/auth/guest",
                json={"age_confirmed_at": "2026-01-01T00:00:00Z", "captcha_token": "local-captcha-proof", "language": "en"},
                headers={"origin": "http://localhost:3000"},
            )
            assert guest.status_code == 200
            source_user_id = str(guest.json()["user"]["id"])
            conversation = client.post(
                "/api/v1/conversations",
                json={"title": "Existing account refusal", "language": "en"},
            )
            assert conversation.status_code == 200
            conversation_id = str(conversation.json()["conversation"]["id"])
            prepared = client.post(
                "/api/v1/auth/guest/handoffs",
                json={
                    "handoff_kind": "new_account_signup",
                    "destination_email": email,
                    "source_conversation_id": conversation_id,
                },
                headers={"origin": "http://localhost:3000"},
            )
            assert prepared.status_code == 201

            refused = client.post(
                "/api/v1/auth/guest/signup",
                json={
                    "age_confirmed_at": "2026-01-01T00:00:00Z",
                    "email": email,
                    "password": f"Wrong-{secrets.token_urlsafe(18)}",
                    "captcha_token": "local-captcha-proof",
                    "language": "en",
                },
                headers={"origin": "http://localhost:3000"},
            )

        assert refused.status_code == 409
        assert refused.json()["code"] == "account_exists_use_login"
        with psycopg.connect(LOCAL_DATABASE_URL) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select count(*) from auth.users where lower(email) = %s",
                    (email,),
                )
                assert cursor.fetchone()[0] == 1
                cursor.execute(
                    "select status, claimed_by, conversation_id::text "
                    "from public.guest_workspaces where user_id = %s",
                    (source_user_id,),
                )
                assert cursor.fetchone() == ("active", None, conversation_id)
                cursor.execute(
                    "select user_id::text from public.conversations where id = %s",
                    (conversation_id,),
                )
                assert cursor.fetchone()[0] == source_user_id
                cursor.execute(
                    "select destination_user_id from public.guest_workspace_handoffs "
                    "where source_user_id = %s",
                    (source_user_id,),
                )
                assert cursor.fetchone()[0] is None
    finally:
        if source_user_id:
            with suppress(Exception):
                gateway.delete_auth_user(source_user_id)
        if existing_user_id:
            with suppress(Exception):
                gateway.delete_auth_user(existing_user_id)


def test_real_confirmed_login_repairs_missing_signup_profile_before_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    gateway = _gateway()
    email = f"guest-profile-repair-{secrets.token_hex(6)}@example.test"
    password = f"Profile-repair-{secrets.token_urlsafe(18)}"
    source_user_id: str | None = None
    destination_user_id: str | None = None
    conversation_id: str | None = None
    try:
        with (
            patch.object(api_state, "supabase_gateway", gateway),
            patch.object(api_state, "DATABASE_URL", LOCAL_DATABASE_URL),
            TestClient(app, base_url="http://localhost:3000") as client,
        ):
            guest = client.post(
                "/api/v1/auth/guest",
                json={"age_confirmed_at": "2026-01-01T00:00:00Z", "captcha_token": "local-captcha-proof", "language": "en"},
                headers={"origin": "http://localhost:3000"},
            )
            assert guest.status_code == 200
            source_user_id = str(guest.json()["user"]["id"])
            conversation = client.post(
                "/api/v1/conversations",
                json={"title": "Profile repair", "language": "en"},
            )
            assert conversation.status_code == 200
            conversation_id = str(conversation.json()["conversation"]["id"])
            prepared = client.post(
                "/api/v1/auth/guest/handoffs",
                json={
                    "handoff_kind": "new_account_signup",
                    "destination_email": email,
                    "source_conversation_id": conversation_id,
                },
                headers={"origin": "http://localhost:3000"},
            )
            assert prepared.status_code == 201

            signed_up = gateway.signup(
                email=email,
                password=password,
                captcha_token="local-captcha-proof",
                language="en",
                guest_signup_handoff={
                    "handoff_id": prepared.json()["handoff_id"],
                    "proof": hashlib.sha256(
                        str(client.cookies.get("argus-guest-handoff")).encode("utf-8")
                    ).hexdigest(),
                },
            )
            destination_user_id = str(signed_up["user"]["id"])
            gateway.client.auth.admin.update_user_by_id(
                destination_user_id,
                {"email_confirm": True},
            )
            assert gateway.get_user(user_id=destination_user_id) is None

            logged_in = client.post(
                "/api/v1/auth/login",
                json={
                    "email": email,
                    "password": password,
                    "captcha_token": "local-captcha-proof",
                },
                headers={"origin": "http://localhost:3000"},
            )

        assert logged_in.status_code == 200, logged_in.json()
        assert logged_in.json()["user"]["id"] == destination_user_id
        assert logged_in.json()["guest_claim"]["conversation_id"] == conversation_id
        assert gateway.get_user(user_id=destination_user_id) is not None
        assert (
            gateway.client.table("conversations")
            .select("user_id")
            .eq("id", conversation_id)
            .single()
            .execute()
            .data["user_id"]
            == destination_user_id
        )
    finally:
        if destination_user_id:
            with suppress(Exception):
                gateway.delete_auth_user(destination_user_id)
        if source_user_id:
            with suppress(Exception):
                gateway.delete_auth_user(source_user_id)


@pytest.mark.skipif(
    not (LOCAL_MAILPIT_URL and LOCAL_AUTH_CONFIRMATIONS),
    reason="local Supabase email-change proof is not configured",
)
def test_real_email_change_keeps_email_change_template_with_old_address() -> None:
    import httpx

    gateway = _gateway()
    old_email = f"old-address-{secrets.token_hex(6)}@example.test"
    new_email = f"new-address-{secrets.token_hex(6)}@example.test"
    password = f"Email-change-{secrets.token_urlsafe(18)}"
    user_id: str | None = None
    try:
        created = gateway.client.auth.admin.create_user(
            {
                "email": old_email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {"language": "es-419"},
            }
        )
        assert created.user is not None
        user_id = str(created.user.id)
        auth_client = create_client(LOCAL_URL, LOCAL_ANON_KEY)
        signed_in = auth_client.auth.sign_in_with_password(
            {"email": old_email, "password": password}
        )
        assert signed_in.session is not None

        updated = auth_client.auth.update_user({"email": new_email})
        assert updated.user is not None
        message = _mailpit_message_for(new_email)
        message_text = unescape(str(message.get("Text") or ""))
        assert message["Subject"] == "Argus: confirma tu nuevo correo"
        assert f"de {old_email} a {new_email}" in message_text

        audit_actions = _auth_audit_actions_for_user(user_id)
        assert "user_modified" in audit_actions
        auth_logs = httpx.get(f"{LOCAL_MAILPIT_URL}/api/v1/messages", timeout=10)
        assert auth_logs.status_code == 200
    finally:
        if user_id:
            with suppress(Exception):
                gateway.delete_auth_user(user_id)


def test_disabled_public_email_cannot_prepare_real_guest_signup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    gateway = _gateway()
    email = f"disabled-link-{secrets.token_hex(6)}@example.test"
    user_id: str | None = None
    conversation_id: str | None = None
    try:
        gateway.client.table("private_alpha_allowlist").insert(
            {
                "email": email,
                "disabled_at": datetime.now(timezone.utc).isoformat(),
            }
        ).execute()
        guest = gateway.sign_in_anonymously(
            captcha_token="local-captcha-proof",
            language="en",
        )
        auth_user = guest["user"]
        user_id = str(auth_user["id"])
        profile = gateway.get_or_create_profile_for_auth_user(auth_user)
        gateway.create_guest_workspace(
            user_id=profile.id,
            created_at=profile.created_at,
        )
        conversation = gateway.create_conversation(
            scope=PERSONAL,
            user_id=user_id,
            title="Disabled identity proof",
            title_source="system_default",
            language="en",
        )
        conversation_id = conversation.id

        with (
            patch.object(api_state, "supabase_gateway", gateway),
            patch.object(api_state, "DATABASE_URL", LOCAL_DATABASE_URL),
            TestClient(app, base_url="http://localhost:3000") as client,
        ):
            client.cookies.set(
                "sb-auth-token",
                str(guest["session"]["access_token"]),
            )
            client.cookies.set(
                "sb-refresh-token",
                str(guest["session"]["refresh_token"]),
            )
            response = client.post(
                "/api/v1/auth/guest/handoffs",
                json={
                    "handoff_kind": "new_account_signup",
                    "destination_email": email,
                    "source_conversation_id": conversation_id,
                },
                headers={"origin": "http://localhost:3000"},
            )

        assert response.status_code == 401
        assert response.json()["code"] == "unauthorized"
        with psycopg.connect(LOCAL_DATABASE_URL) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select is_anonymous, email from auth.users where id = %s",
                    (user_id,),
                )
                assert cursor.fetchone() == (True, None)
                cursor.execute(
                    "select count(*) from auth.users where lower(email) = %s",
                    (email,),
                )
                assert cursor.fetchone()[0] == 0
                cursor.execute(
                    "select status, claimed_by, conversation_id::text"
                    " from public.guest_workspaces where user_id = %s",
                    (user_id,),
                )
                assert cursor.fetchone() == ("active", None, conversation_id)
                cursor.execute(
                    "select user_id::text from public.conversations where id = %s",
                    (conversation_id,),
                )
                assert cursor.fetchone()[0] == user_id
    finally:
        with suppress(Exception):
            gateway.client.table("private_alpha_allowlist").delete().eq(
                "email", email
            ).execute()
        if user_id:
            with suppress(Exception):
                gateway.delete_auth_user(user_id)
