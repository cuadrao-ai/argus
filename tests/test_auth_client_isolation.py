"""The API's Supabase Auth calls leave no user state behind (native proof A14).

The gateway is built by the production factory and pointed at a local HTTP
server that answers like Supabase Auth and records every request it receives.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
from argus.domain.supabase_gateway import SupabaseGateway

ANON_KEY = "anon-key-for-isolation-test"
SERVICE_KEY = "service-key-for-isolation-test"
PUBLIC_AUTHORIZATION = f"Bearer {ANON_KEY}"
# supabase-py refreshes 10 s before expiry, but only when more than 10 s remain,
# so a 12 s token is refreshed 1 to 2 s after sign-in by a client that keeps it.
SHORT_EXPIRY_SECONDS = 12


@dataclass
class FakeAuth:
    requests: list[dict[str, str]] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, **entry: str) -> None:
        with self.lock:
            self.requests.append(entry)

    def grants(self, grant: str) -> list[dict[str, str]]:
        return [r for r in self.requests if r.get("grant_type") == grant]


def _session(email: str | None) -> dict[str, object]:
    subject = email or f"anonymous-{uuid.uuid4().hex[:8]}"
    now = int(time.time())
    return {
        "access_token": f"access-for-{subject}",
        "refresh_token": f"refresh-for-{subject}-{uuid.uuid4().hex[:6]}",
        "token_type": "bearer",
        "expires_in": SHORT_EXPIRY_SECONDS,
        "expires_at": now + SHORT_EXPIRY_SECONDS,
        "user": {
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, subject)),
            "aud": "authenticated",
            "role": "authenticated",
            "email": email,
            "is_anonymous": email is None,
            "app_metadata": {},
            "user_metadata": {},
            "created_at": "2026-09-28T00:00:00Z",
        },
    }


def _handler(fake: FakeAuth) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            return

        def do_POST(self) -> None:
            url = urlparse(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            fake.record(
                path=url.path,
                grant_type=parse_qs(url.query).get("grant_type", [""])[0],
                authorization=self.headers.get("Authorization", ""),
            )
            payload = (
                {}
                if url.path.endswith("/resend")
                else _session(body.get("email") or body.get("refresh_token"))
            )
            encoded = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return Handler


class _Server(ThreadingHTTPServer):
    request_queue_size = 64


@pytest.fixture
def fake_auth() -> Iterator[tuple[FakeAuth, SupabaseGateway]]:
    fake = FakeAuth()
    server = _Server(("127.0.0.1", 0), _handler(fake))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address[:2]
    with patch.dict(
        os.environ,
        {
            "SUPABASE_URL": f"http://{host}:{port}",
            "SUPABASE_SERVICE_ROLE_KEY": SERVICE_KEY,
            "SUPABASE_ANON_KEY": ANON_KEY,
            "DATABASE_URL": "postgresql://unused@127.0.0.1:9/unused",
        },
    ):
        gateway = SupabaseGateway.from_env()
    try:
        yield fake, gateway
    finally:
        server.shutdown()
        server.server_close()
        if gateway.history_reader is not None:
            gateway.history_reader.pool.close()


def _login(gateway: SupabaseGateway, email: str) -> dict[str, object]:
    return gateway.login(email=email, password="password-1", captcha_token="captcha")


def test_each_auth_call_carries_only_the_public_key(fake_auth) -> None:
    fake, gateway = fake_auth

    _login(gateway, "alice@example.com")
    _login(gateway, "bob@example.com")
    gateway.signup(email="carol@example.com", password="password-1", captcha_token="c")
    gateway.resend_signup_confirmation(email="carol@example.com", captcha_token="c")
    gateway.sign_in_anonymously(captcha_token="c", language="en")

    assert [r["authorization"] for r in fake.requests] == [PUBLIC_AUTHORIZATION] * 5


def test_argus_never_refreshes_a_session_it_returned(fake_auth) -> None:
    fake, gateway = fake_auth

    _login(gateway, "alice@example.com")
    gateway.sign_in_anonymously(captcha_token="c", language="en")
    time.sleep(3)

    assert fake.grants("refresh_token") == []


def test_concurrent_sign_ins_send_no_user_token_and_return_their_own_identity(
    fake_auth,
) -> None:
    fake, gateway = fake_auth
    _login(gateway, "earlier@example.com")
    emails = [f"user-{index}@example.com" for index in range(12)]
    start = threading.Barrier(len(emails))
    results: dict[str, dict[str, object]] = {}

    def sign_in(email: str) -> None:
        start.wait()
        results[email] = _login(gateway, email)

    threads = [threading.Thread(target=sign_in, args=(email,)) for email in emails]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    returned = {
        email: (result["user"]["email"], result["session"]["access_token"])
        for email, result in results.items()
    }
    assert returned == {email: (email, f"access-for-{email}") for email in emails}
    assert {r["authorization"] for r in fake.requests} == {PUBLIC_AUTHORIZATION}


def test_explicit_refresh_uses_public_key_and_keeps_no_cross_user_session(
    fake_auth,
) -> None:
    fake, gateway = fake_auth
    results = [
        gateway.refresh_browser_session(email)
        for email in ("alice@example.com", "bob@example.com")
    ]
    assert [result["user"]["email"] for result in results] == [
        "alice@example.com",
        "bob@example.com",
    ]
    assert [request["authorization"] for request in fake.grants("refresh_token")] == [
        PUBLIC_AUTHORIZATION
    ] * 2
    # Refresh must not alter the service client or the next user's auth call.
    later = _login(gateway, "carol@example.com")
    assert later["user"]["email"] == "carol@example.com"
    assert fake.requests[-1]["authorization"] == PUBLIC_AUTHORIZATION
    assert gateway._auth().get_session() is None
