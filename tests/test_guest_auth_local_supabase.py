"""Local-Supabase proof for real anonymous Auth identity persistence."""

from __future__ import annotations

import os
import re
import secrets
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from html import unescape
from threading import Barrier, Event
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import httpx
import jwt
import psycopg
import pytest
from argus.api import state as api_state
from argus.api.main import app
from argus.api.routers import auth as auth_router
from argus.api.schemas import GuestPendingAction, Message
from argus.domain.guest_cleanup import cleanup_expired_guest_workspaces
from argus.domain.owner_scope import PERSONAL
from argus.domain.store import utcnow
from argus.domain.username_signup import serialized_username_signup
from fastapi.testclient import TestClient
from supabase_auth.errors import AuthApiError

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


def _parse_postgrest_utc_timestamp(value: str) -> datetime:
    match = re.fullmatch(
        r"(?P<base>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})"
        r"\.(?P<fraction>\d{1,6})(?:Z|\+00(?::00)?)",
        value,
    )
    if match is None:
        raise ValueError("expected a UTC timestamp with microsecond precision")
    fraction = match.group("fraction").ljust(6, "0")
    return datetime.fromisoformat(f"{match.group('base')}.{fraction}+00:00")


def test_postgrest_utc_timestamp_normalizes_fraction_width() -> None:
    assert _parse_postgrest_utc_timestamp(
        "2026-07-26T07:57:19.59304+00:00"
    ) == _parse_postgrest_utc_timestamp("2026-07-26T07:57:19.593040+00:00")


def test_postgrest_utc_timestamp_rejects_real_differences_and_invalid_input() -> None:
    baseline = _parse_postgrest_utc_timestamp("2026-07-26T07:57:19.593040Z")
    assert baseline != _parse_postgrest_utc_timestamp("2026-07-26T07:57:19.593041+00")
    with pytest.raises(ValueError):
        _parse_postgrest_utc_timestamp("2026-07-26T07:57:19.593040-05:00")
    with pytest.raises(ValueError):
        _parse_postgrest_utc_timestamp("not-a-timestamp")


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


def test_real_anonymous_identity_survives_reload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED", "false")
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    gateway = _gateway()

    user_id: str | None = None
    try:
        with (
            patch.object(api_state, "supabase_gateway", gateway),
            patch.object(api_state, "DATABASE_URL", LOCAL_DATABASE_URL),
            TestClient(app) as client,
        ):
            created = client.post(
                "/api/v1/auth/guest",
                json={"age_confirmed_at": "2026-01-01T00:00:00Z", "captcha_token": "local-captcha-proof", "language": "en"},
                headers={"origin": "http://localhost:3000"},
            )
            assert created.status_code == 200
            user = created.json()["user"]
            user_id = str(user["id"])
            assert user["is_anonymous"] is True
            assert user.get("email") in {None, ""}
            assert client.cookies.get("sb-auth-token")

            reloaded = client.post(
                "/api/v1/auth/guest",
                json={"age_confirmed_at": "2026-01-01T00:00:00Z", "captcha_token": "local-captcha-proof", "language": "en"},
                headers={"origin": "http://localhost:3000"},
            )
            assert reloaded.status_code == 200
            assert reloaded.json()["reused"] is True
            assert reloaded.json()["user"]["id"] == user_id

            profile = gateway.get_user(user_id=user_id)
            workspace = gateway.get_active_guest_workspace(
                user_id=user_id,
                at=profile.created_at,
            )
            assert profile.email is None
            assert workspace is not None
            assert workspace.user_id == user_id
    finally:
        if user_id:
            gateway.delete_auth_user(user_id)


def test_real_guest_terminal_message_settles_visitor_day_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED", "false")
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    gateway = _gateway()
    user_id: str | None = None
    try:
        with (
            patch.object(api_state, "supabase_gateway", gateway),
            patch.object(api_state, "DATABASE_URL", LOCAL_DATABASE_URL),
            TestClient(app, base_url="http://localhost:3000") as client,
        ):
            created = client.post(
                "/api/v1/auth/guest",
                json={"age_confirmed_at": "2026-01-01T00:00:00Z", "captcha_token": "local-captcha-proof", "language": "en"},
                headers={"origin": "http://localhost:3000"},
            )
            assert created.status_code == 200
            user_id = str(created.json()["user"]["id"])
            workspace = gateway.get_active_guest_workspace(
                user_id=user_id,
                at=datetime.now(timezone.utc),
            )
            assert workspace is not None

            created_conversation = client.post("/api/v1/conversations", json={})
            assert created_conversation.status_code == 200
            conversation_id = created_conversation.json()["conversation"]["id"]
            turn_id = str(uuid4())
            request_id = f"request-{turn_id}"
            accepted = gateway.accept_chat_turn(
                user_id=user_id,
                conversation_id=conversation_id,
                request_id=request_id,
                message=Message(
                    id=turn_id,
                    conversation_id=conversation_id,
                    role="user",
                    content="Test this idea.",
                    metadata={},
                    created_at=utcnow(),
                ),
            )
            assistant = Message(
                id=str(uuid4()),
                conversation_id=conversation_id,
                role="assistant",
                content="Ready to review.",
                metadata={
                    "agent_runtime_turn": {
                        "turn_id": turn_id,
                        "request_id": request_id,
                        "status": "completed",
                        "terminal": True,
                    }
                },
                created_at=utcnow(),
            )
            visitor_key = f"visitor-test:{turn_id[:8]}"
            # The terminal transaction's visitor-keyed settlement path, driven
            # directly: no product path settles conversation any more.
            settlement = {
                "resource": "chat_messages",
                "limits": [("day", 10)],
                "visitor_key": visitor_key,
            }

            first = gateway.finalize_chat_turn(
                user_id=user_id,
                conversation_id=conversation_id,
                turn_id=accepted.id,
                request_id=request_id,
                message=assistant,
                to_status="completed",
                failure_code=None,
                retryable=False,
                settle_usage=settlement,
            )
            replay = gateway.finalize_chat_turn(
                user_id=user_id,
                conversation_id=conversation_id,
                turn_id=accepted.id,
                request_id=request_id,
                message=assistant,
                to_status="completed",
                failure_code=None,
                retryable=False,
                settle_usage=settlement,
            )

            account_counters = (
                gateway.client.table("usage_counters")
                .select("period,used_count")
                .eq("user_id", user_id)
                .eq("resource", "chat_messages")
                .execute()
                .data
            )
            visitor_counters = (
                gateway.client.table("visitor_usage_counters")
                .select("period,used_count,limit_count")
                .eq("visitor_key", visitor_key)
                .eq("resource", "chat_messages")
                .execute()
                .data
            )
            lifecycle = (
                gateway.client.table("chat_turn_lifecycles")
                .select("status,assistant_message_id")
                .eq("turn_id", turn_id)
                .single()
                .execute()
                .data
            )

            assert replay == first
            assert lifecycle == {
                "status": "completed",
                "assistant_message_id": assistant.id,
            }
            # The unit lands on the visitor, not the renewable workspace, and
            # the replayed finalization above must not have charged it twice.
            assert account_counters == []
            assert visitor_counters == [
                {"period": "day", "used_count": 1, "limit_count": 10}
            ]
    finally:
        if user_id:
            with suppress(Exception):
                gateway.delete_auth_user(user_id)


def test_expired_real_anonymous_session_renews_with_fresh_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED", "false")
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    gateway = _gateway()
    expired_user_id: str | None = None
    renewed_user_id: str | None = None
    try:
        expired_auth = gateway.sign_in_anonymously(
            captcha_token="local-captcha-proof",
            language="en",
        )
        expired_user = expired_auth["user"]
        expired_user_id = str(expired_user["id"])
        expired_profile = gateway.get_or_create_profile_for_auth_user(expired_user)
        created_at = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=8)
        gateway.client.table("guest_workspaces").insert(
            {
                "user_id": expired_profile.id,
                "created_at": created_at.isoformat(),
            }
        ).execute()
        access_token = str(expired_auth["session"]["access_token"])

        with (
            patch.object(api_state, "supabase_gateway", gateway),
            patch.object(api_state, "DATABASE_URL", LOCAL_DATABASE_URL),
            TestClient(app) as client,
        ):
            client.cookies.set("sb-auth-token", access_token)
            renewed = client.post(
                "/api/v1/auth/guest",
                json={"age_confirmed_at": "2026-01-01T00:00:00Z", "captcha_token": "local-captcha-proof", "language": "en"},
                headers={"origin": "http://localhost:3000"},
            )

        assert renewed.status_code == 200
        assert renewed.json()["reused"] is False
        renewed_user = renewed.json()["user"]
        renewed_user_id = str(renewed_user["id"])
        assert renewed_user_id != expired_user_id
        assert renewed_user["is_anonymous"] is True
        assert renewed_user.get("email") in {None, ""}
        workspace = gateway.get_active_guest_workspace(
            user_id=renewed_user_id,
            at=datetime.now(timezone.utc),
        )
        assert workspace is not None
    finally:
        for user_id in (expired_user_id, renewed_user_id):
            if user_id:
                with suppress(Exception):
                    gateway.delete_auth_user(user_id)


def test_cleanup_deletes_real_anonymous_auth_user_through_admin() -> None:
    gateway = _gateway()
    auth_user_id: str | None = None
    aggregate_id: str | None = None
    try:
        auth_result = gateway.sign_in_anonymously(
            captcha_token="local-captcha-proof",
            language="en",
        )
        auth_user = auth_result["user"]
        auth_user_id = str(auth_user["id"])
        profile = gateway.get_or_create_profile_for_auth_user(auth_user)
        conversation = gateway.create_conversation(
            scope=PERSONAL,
            user_id=profile.id,
            title="expired guest proof",
            title_source="system_default",
            language="en",
        )
        gateway.client.table("messages").insert(
            {
                "conversation_id": conversation.id,
                "user_id": profile.id,
                "role": "user",
                "content": "private cleanup proof",
            }
        ).execute()
        gateway.client.table("backtest_runs").insert(
            {
                "user_id": profile.id,
                "conversation_id": conversation.id,
                "status": "completed",
                "asset_class": "equity",
                "symbols": ["AAPL"],
                "benchmark_symbol": "SPY",
                "config_snapshot": {},
            }
        ).execute()
        aggregate = (
            gateway.client.table("cost_ledger_entries")
            .insert(
                {
                    "source": "api_turn",
                    "service": "local-proof",
                    "provider": "local-proof",
                    "feature_area": "guest_cleanup",
                    "user_id": profile.id,
                    "conversation_id": conversation.id,
                    "correlation_id": f"guest-cleanup-{profile.id}",
                    "billable_unit": "unknown",
                    "status": "succeeded",
                }
            )
            .execute()
            .data[0]
        )
        aggregate_id = str(aggregate["id"])
        created_at = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=8)
        gateway.client.table("guest_workspaces").insert(
            {
                "user_id": profile.id,
                "conversation_id": conversation.id,
                "created_at": created_at.isoformat(),
                "expires_at": (created_at + timedelta(days=7)).isoformat(),
            }
        ).execute()

        result = cleanup_expired_guest_workspaces(
            gateway,
            limit=100,
            dry_run=False,
        )

        assert result.auth_deleted >= 1
        with pytest.raises(AuthApiError):
            gateway.client.auth.admin.get_user_by_id(auth_user_id)
        assert gateway.get_user(user_id=auth_user_id) is None
        for table in (
            "conversations",
            "messages",
            "backtest_runs",
            "guest_workspaces",
        ):
            assert (
                gateway.client.table(table)
                .select("*")
                .eq("user_id", auth_user_id)
                .execute()
                .data
                == []
            )
        preserved_aggregate = (
            gateway.client.table("cost_ledger_entries")
            .select("user_id,conversation_id")
            .eq("id", aggregate["id"])
            .single()
            .execute()
            .data
        )
        assert preserved_aggregate == {"user_id": None, "conversation_id": None}
    finally:
        if auth_user_id:
            with suppress(Exception):
                gateway.delete_auth_user(auth_user_id)
        if aggregate_id:
            with psycopg.connect(LOCAL_DATABASE_URL, autocommit=True) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "delete from public.cost_ledger_entries where id = %s",
                        (aggregate_id,),
                    )


def test_signup_taken_username_creates_no_auth_user_or_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED", "false")
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    gateway = _gateway()
    suffix = secrets.token_hex(6)
    existing_email = f"username-owner-{suffix}@example.test"
    fresh_email = f"username-conflict-{suffix}@example.test"
    username = f"portfolio{suffix}"
    existing_user_id: str | None = None
    try:
        created_existing = gateway.client.auth.admin.create_user(
            {
                "email": existing_email,
                "password": f"Existing-{secrets.token_urlsafe(18)}",
                "email_confirm": True,
                "user_metadata": {"username": username},
            }
        )
        assert created_existing.user is not None
        existing_user_id = str(created_existing.user.id)
        gateway.get_or_create_profile_for_auth_user(
            created_existing.user.model_dump(mode="json")
        )
        gateway.client.table("private_alpha_allowlist").insert(
            {"email": fresh_email}
        ).execute()

        with (
            patch.object(api_state, "supabase_gateway", gateway),
            patch.object(api_state, "DATABASE_URL", LOCAL_DATABASE_URL),
            TestClient(app, base_url="http://localhost:3000") as client,
        ):
            response = client.post(
                "/api/v1/auth/signup",
                json={
                    "age_confirmed_at": "2026-01-01T00:00:00Z",
                    "email": fresh_email,
                    "password": f"Fresh-{secrets.token_urlsafe(18)}",
                    "captcha_token": "local-captcha-proof",
                    "username": username.upper(),
                    "language": "en",
                },
            )

        assert response.status_code == 400, response.json()
        assert response.json()["code"] == "auth_signup_failed"
        with psycopg.connect(LOCAL_DATABASE_URL) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select count(*) from auth.users where lower(email) = %s",
                    (fresh_email,),
                )
                assert cursor.fetchone()[0] == 0
                cursor.execute(
                    "select count(*) from public.profiles where lower(email) = %s",
                    (fresh_email,),
                )
                assert cursor.fetchone()[0] == 0
    finally:
        with suppress(Exception):
            gateway.client.table("private_alpha_allowlist").delete().eq(
                "email", fresh_email
            ).execute()
        if existing_user_id:
            with suppress(Exception):
                gateway.delete_auth_user(existing_user_id)


def test_username_availability_treats_pattern_characters_as_literals() -> None:
    gateway = _gateway()
    suffix = secrets.token_hex(6)
    email = f"username-literal-{suffix}@example.test"
    username_pairs = [
        (f"underscore_{suffix}", f"underscoreX{suffix}"),
        (f"percent%{suffix}", f"percentX{suffix}"),
        (f"star*{suffix}", f"starX{suffix}"),
    ]
    user_id: str | None = None
    try:
        created = gateway.client.auth.admin.create_user(
            {
                "email": email,
                "password": f"Literal-{secrets.token_urlsafe(18)}",
                "email_confirm": True,
                "user_metadata": {"username": username_pairs[0][1]},
            }
        )
        assert created.user is not None
        user_id = str(created.user.id)
        gateway.get_or_create_profile_for_auth_user(created.user.model_dump(mode="json"))

        for literal_username, pattern_match_username in username_pairs:
            gateway.client.table("profiles").update(
                {"username": pattern_match_username}
            ).eq("id", user_id).execute()
            with serialized_username_signup(
                LOCAL_DATABASE_URL,
                f"username-probe-{suffix}@example.test",
                literal_username,
            ) as available:
                assert available.username_available is True
            gateway.client.table("profiles").update({"username": literal_username}).eq(
                "id", user_id
            ).execute()
            with serialized_username_signup(
                LOCAL_DATABASE_URL,
                f"username-probe-{suffix}@example.test",
                literal_username,
            ) as available:
                assert available.username_available is False
        with serialized_username_signup(
            LOCAL_DATABASE_URL,
            email,
            username_pairs[-1][0],
        ) as existing_email_prevalidation:
            assert existing_email_prevalidation.auth_user_exists is True
            assert existing_email_prevalidation.username_available is False
    finally:
        if user_id:
            with suppress(Exception):
                gateway.delete_auth_user(user_id)


def test_concurrent_same_username_signup_calls_auth_only_for_winner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED", "false")
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    gateway = _gateway()
    suffix = secrets.token_hex(6)
    first_email = f"username-race-first-{suffix}@example.test"
    second_email = f"username-race-second-{suffix}@example.test"
    username = f"serialized{suffix}"
    password = f"Serialized-{secrets.token_urlsafe(18)}"
    first_provider_complete = Event()
    release_first_signup = Event()
    second_provider_called = Event()
    original_signup = gateway.signup

    def paused_signup(**kwargs: Any) -> dict[str, Any]:
        result = original_signup(**kwargs)
        if kwargs["email"] == first_email:
            first_provider_complete.set()
            if not release_first_signup.wait(timeout=10):
                raise RuntimeError("concurrent signup test did not release first request")
        elif kwargs["email"] == second_email:
            second_provider_called.set()
        return result

    gateway.signup = paused_signup  # type: ignore[method-assign]
    try:
        gateway.client.table("private_alpha_allowlist").insert(
            [{"email": first_email}, {"email": second_email}]
        ).execute()
        payload = {
            "age_confirmed_at": "2026-01-01T00:00:00Z",
            "password": password,
            "captcha_token": "local-captcha-proof",
            "username": username,
            "language": "en",
        }
        with (
            patch.object(api_state, "supabase_gateway", gateway),
            patch.object(api_state, "DATABASE_URL", LOCAL_DATABASE_URL),
            TestClient(app, base_url="http://localhost:3000") as first_client,
            TestClient(app, base_url="http://localhost:3000") as second_client,
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            first = executor.submit(
                first_client.post,
                "/api/v1/auth/signup",
                json={**payload, "email": first_email},
            )
            assert first_provider_complete.wait(timeout=10)
            second = executor.submit(
                second_client.post,
                "/api/v1/auth/signup",
                json={**payload, "email": second_email},
            )
            try:
                assert not second_provider_called.wait(timeout=0.5)
            finally:
                release_first_signup.set()
            first_response = first.result(timeout=10)
            second_response = second.result(timeout=10)

        assert first_response.status_code == 200, first_response.json()
        assert second_response.status_code == 400, second_response.json()
        assert second_response.json()["code"] == "auth_signup_failed"
        assert gateway.get_user(user_id=str(first_response.json()["user"]["id"]))
        with psycopg.connect(LOCAL_DATABASE_URL) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select count(*) from auth.users where lower(email) = %s",
                    (second_email,),
                )
                assert cursor.fetchone()[0] == 0
    finally:
        release_first_signup.set()
        with suppress(Exception):
            gateway.client.table("private_alpha_allowlist").delete().in_(
                "email", [first_email, second_email]
            ).execute()
        with psycopg.connect(LOCAL_DATABASE_URL) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select id::text from auth.users where lower(email) = any(%s)",
                    ([first_email, second_email],),
                )
                user_ids = [row[0] for row in cursor.fetchall()]
        for user_id in user_ids:
            with suppress(Exception):
                gateway.delete_auth_user(user_id)


def test_signup_creates_profile_before_first_login_claims_pending_handoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED", "false")
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    gateway = _gateway()
    email = f"first-login-claim-{secrets.token_hex(6)}@example.test"
    password = f"FirstLogin-{secrets.token_urlsafe(18)}"
    source_user_id: str | None = None
    destination_user_id: str | None = None
    conversation_id: str | None = None
    try:
        gateway.client.table("private_alpha_allowlist").insert({"email": email}).execute()

        guest = gateway.sign_in_anonymously(
            captcha_token="local-captcha-proof",
            language="en",
        )
        guest_user = guest["user"]
        source_user_id = str(guest_user["id"])
        guest_profile = gateway.get_or_create_profile_for_auth_user(guest_user)
        gateway.create_guest_workspace(
            user_id=source_user_id,
            created_at=guest_profile.created_at,
        )
        conversation = gateway.create_conversation(
            scope=PERSONAL,
            user_id=source_user_id,
            title="First login claim proof",
            title_source="system_default",
            language="en",
        )
        conversation_id = conversation.id

        with (
            patch.object(api_state, "supabase_gateway", gateway),
            patch.object(api_state, "DATABASE_URL", LOCAL_DATABASE_URL),
            TestClient(app, base_url="http://localhost:3000") as guest_client,
            TestClient(app, base_url="http://localhost:3000") as signup_client,
        ):
            guest_client.cookies.set(
                "sb-auth-token",
                str(guest["session"]["access_token"]),
            )
            guest_client.cookies.set(
                "sb-refresh-token",
                str(guest["session"]["refresh_token"]),
            )
            handoff = guest_client.post(
                "/api/v1/auth/guest/handoffs",
                json={
                    "destination_email": email,
                    "source_conversation_id": conversation_id,
                    "pending_action": {
                        "reason": "keep_history",
                        "conversation_id": conversation_id,
                        "action_id": "first-login-keep-history",
                    },
                },
                headers={"origin": "http://localhost:3000"},
            )
            assert handoff.status_code == 201, handoff.json()

            signed_up = signup_client.post(
                "/api/v1/auth/signup",
                json={
                    "age_confirmed_at": "2026-01-01T00:00:00Z",
                    "email": email,
                    "password": password,
                    "captcha_token": "local-captcha-proof",
                    "language": "en",
                },
            )
            assert signed_up.status_code == 200, signed_up.json()
            destination_user_id = str(signed_up.json()["user"]["id"])
            if signed_up.json()["session"] is None:
                assert LOCAL_MAILPIT_URL
                import httpx

                confirmation = httpx.get(
                    _confirmation_url(_mailpit_message_for(email)),
                    follow_redirects=False,
                    timeout=10,
                )
                assert confirmation.status_code == 303

            signed_in = guest_client.post(
                "/api/v1/auth/login",
                json={
                    "email": email,
                    "password": password,
                    "captcha_token": "local-captcha-proof",
                },
            )

        assert signed_in.status_code == 200, signed_in.json()
        assert signed_in.json()["guest_claim"] == {
            "conversation_id": conversation_id,
            "pending_action": GuestPendingAction(
                reason="keep_history",
                conversation_id=conversation_id,
                action_id="first-login-keep-history",
            ).model_dump(mode="json"),
        }
        assert gateway.get_user(user_id=destination_user_id) is not None
        transferred = (
            gateway.client.table("conversations")
            .select("id,user_id")
            .eq("id", conversation_id)
            .single()
            .execute()
            .data
        )
        assert transferred == {
            "id": conversation_id,
            "user_id": destination_user_id,
        }
    finally:
        if destination_user_id:
            with suppress(Exception):
                gateway.delete_auth_user(destination_user_id)
        if source_user_id:
            with suppress(Exception):
                gateway.delete_auth_user(source_user_id)
        with suppress(Exception):
            gateway.client.table("private_alpha_allowlist").delete().eq(
                "email", email
            ).execute()


def test_existing_account_claim_preserves_same_conversation_and_deletes_source_only_after_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED", "false")
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    gateway = _gateway()
    email = f"block3-claim-{secrets.token_hex(6)}@example.test"
    password = f"Block3-{secrets.token_urlsafe(18)}"
    source_user_id: str | None = None
    destination_user_id: str | None = None
    conversation_id: str | None = None
    try:
        created_destination = gateway.client.auth.admin.create_user(
            {
                "email": email,
                "password": password,
                "email_confirm": True,
            }
        )
        assert created_destination.user is not None
        destination_user_id = str(created_destination.user.id)
        gateway.get_or_create_profile_for_auth_user(
            created_destination.user.model_dump(mode="json")
        )
        gateway.client.table("private_alpha_allowlist").insert({"email": email}).execute()

        guest = gateway.sign_in_anonymously(
            captcha_token="local-captcha-proof",
            language="en",
        )
        guest_user = guest["user"]
        source_user_id = str(guest_user["id"])
        guest_profile = gateway.get_or_create_profile_for_auth_user(guest_user)
        gateway.create_guest_workspace(
            user_id=source_user_id,
            created_at=guest_profile.created_at,
        )
        conversation = gateway.create_conversation(
            scope=PERSONAL,
            user_id=source_user_id,
            title="Claim proof",
            title_source="system_default",
            language="en",
        )
        conversation_id = conversation.id
        user_message_id = str(uuid4())
        assistant_message_id = str(uuid4())
        # Bulk inserts share one transaction now(); tie-broken order is luck.
        seeded_at = datetime.now(timezone.utc)
        gateway.client.table("messages").insert(
            [
                {
                    "id": user_message_id,
                    "conversation_id": conversation_id,
                    "user_id": source_user_id,
                    "role": "user",
                    "content": "One guest message",
                    "created_at": seeded_at.isoformat(),
                },
                {
                    "id": assistant_message_id,
                    "conversation_id": conversation_id,
                    "user_id": source_user_id,
                    "role": "assistant",
                    "content": "One durable response",
                    "created_at": (seeded_at + timedelta(seconds=1)).isoformat(),
                },
            ]
        ).execute()
        gateway.client.table("chat_turn_lifecycles").insert(
            {
                "turn_id": user_message_id,
                "user_id": source_user_id,
                "conversation_id": conversation_id,
                "assistant_message_id": assistant_message_id,
                "request_id": f"request-{user_message_id}",
                "status": "completed",
                "terminal_at": datetime.now(timezone.utc).isoformat(),
            }
        ).execute()
        assert gateway.private_alpha_email_allowed(email) is True

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
            handoff = client.post(
                "/api/v1/auth/guest/handoffs",
                json={
                    "destination_email": email,
                    "source_conversation_id": conversation_id,
                    "pending_action": {
                        "reason": "keep_history",
                        "conversation_id": conversation_id,
                        "action_id": "keep-history-1",
                    },
                },
                headers={"origin": "http://localhost:3000"},
            )
            assert handoff.status_code == 201, handoff.json()
            handoff_id = handoff.json()["handoff_id"]
            handoff_secret = client.cookies.get("argus-guest-handoff")
            assert handoff_secret

            signed_in = client.post(
                "/api/v1/auth/login",
                json={
                    "email": email,
                    "password": password,
                    "captcha_token": "local-captcha-proof",
                },
            )
            assert signed_in.status_code == 200
            claimed = signed_in.json()["guest_claim"]
            assert claimed["conversation_id"] == conversation_id
            assert claimed["pending_action"]["action_id"] == "keep-history-1"
            client.cookies.set("argus-guest-handoff-id", handoff_id)
            client.cookies.set("argus-guest-handoff", handoff_secret)
            reconciled = client.post(
                "/api/v1/auth/login",
                json={
                    "email": email,
                    "password": password,
                    "captcha_token": "local-captcha-proof",
                },
            )
            assert reconciled.status_code == 200
            assert reconciled.json()["guest_claim"] == claimed
            replay = client.post(
                f"/api/v1/auth/guest/handoffs/{handoff_id}/claim",
                headers={"origin": "http://localhost:3000"},
            )
            assert replay.status_code == 409
            assert replay.json()["code"] == "guest_handoff_consumed"

            reloaded = client.get("/api/v1/me")

        assert reloaded.status_code == 200
        assert reloaded.json()["account_kind"] == "registered"
        assert reloaded.json()["user"]["id"] == destination_user_id
        transferred = (
            gateway.client.table("conversations")
            .select("id,user_id")
            .eq("id", conversation_id)
            .single()
            .execute()
            .data
        )
        assert transferred == {
            "id": conversation_id,
            "user_id": destination_user_id,
        }
        messages = (
            gateway.client.table("messages")
            .select("id,user_id,content")
            .eq("conversation_id", conversation_id)
            .order("created_at")
            .execute()
            .data
        )
        assert [row["content"] for row in messages] == [
            "One guest message",
            "One durable response",
        ]
        assert all(row["user_id"] == destination_user_id for row in messages)
        lifecycle = (
            gateway.client.table("chat_turn_lifecycles")
            .select("turn_id,user_id,conversation_id,assistant_message_id,status")
            .eq("turn_id", user_message_id)
            .single()
            .execute()
            .data
        )
        assert lifecycle == {
            "turn_id": user_message_id,
            "user_id": destination_user_id,
            "conversation_id": conversation_id,
            "assistant_message_id": assistant_message_id,
            "status": "completed",
        }
        source_auth = gateway.client.auth.admin.get_user_by_id(source_user_id)
        assert source_auth.user is not None
        assert source_auth.user.is_anonymous is True
        gateway.client.table("guest_workspaces").update(
            {
                "updated_at": (
                    datetime.now(timezone.utc) - timedelta(minutes=20)
                ).isoformat()
            }
        ).eq("user_id", source_user_id).execute()
        cleanup = cleanup_expired_guest_workspaces(
            gateway,
            limit=25,
            dry_run=False,
        )
        assert cleanup.auth_deleted == 1
        with pytest.raises(AuthApiError):
            gateway.client.auth.admin.get_user_by_id(source_user_id)
        lifecycle_after_cleanup = (
            gateway.client.table("chat_turn_lifecycles")
            .select("turn_id,user_id")
            .eq("turn_id", user_message_id)
            .single()
            .execute()
            .data
        )
        assert lifecycle_after_cleanup == {
            "turn_id": user_message_id,
            "user_id": destination_user_id,
        }
    finally:
        if destination_user_id:
            with suppress(Exception):
                gateway.delete_auth_user(destination_user_id)
        if source_user_id:
            with suppress(Exception):
                gateway.delete_auth_user(source_user_id)


def test_concurrent_logins_keep_identities_and_leave_refresh_to_the_client() -> None:
    gateway = _gateway()
    suffix = secrets.token_hex(6)
    password = f"Isolation-{secrets.token_urlsafe(18)}"
    user_ids: dict[str, str] = {}
    try:
        for index in range(6):
            email = f"session-isolation-{index}-{suffix}@example.test"
            created = gateway.client.auth.admin.create_user(
                {"email": email, "password": password, "email_confirm": True}
            )
            user_ids[email] = created.user.id

        def login(email: str) -> dict[str, Any]:
            return gateway.login(
                email=email, password=password, captcha_token="local-captcha-proof"
            )

        earlier = login(next(iter(user_ids)))
        start = Barrier(len(user_ids))

        def concurrent_login(email: str) -> tuple[str, dict[str, Any]]:
            start.wait(timeout=10)
            return email, login(email)

        with ThreadPoolExecutor(max_workers=len(user_ids)) as pool:
            results = dict(pool.map(concurrent_login, user_ids))

        subjects = {
            email: jwt.decode(
                result["session"]["access_token"], options={"verify_signature": False}
            )["sub"]
            for email, result in results.items()
        }
        assert subjects == user_ids

        refreshed = httpx.post(
            f"{LOCAL_URL}/auth/v1/token",
            params={"grant_type": "refresh_token"},
            json={"refresh_token": earlier["session"]["refresh_token"]},
            headers={"apikey": LOCAL_ANON_KEY},
            timeout=30,
        )
        assert refreshed.status_code == 200
        assert refreshed.json()["user"]["id"] == user_ids[next(iter(user_ids))]
    finally:
        for user_id in user_ids.values():
            with suppress(Exception):
                gateway.client.auth.admin.delete_user(user_id)
