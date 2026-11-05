"""Shared fakes for the Sign in with Apple tests: a generated key, a scripted
Apple token/revoke endpoint, and identity tokens shaped like Apple's."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import parse_qs

import httpx
import jwt
from argus.domain.apple_sign_in.config import ISSUER, AppleSignInConfig
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

TEAM_ID = "TEAM123456"
KEY_ID = "KEY1234567"
BUNDLE_ID = "ai.cuadrao.test"
SUBJECT = "001234.abcdef0123456789abcdef0123456789.0420"


def generated_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def pem(key: ec.EllipticCurvePrivateKey) -> str:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def config(key: ec.EllipticCurvePrivateKey | None = None) -> AppleSignInConfig:
    return AppleSignInConfig(
        team_id=TEAM_ID,
        key_id=KEY_ID,
        client_id=BUNDLE_ID,
        private_key=key or generated_key(),
    )


def id_token(*, sub: str = SUBJECT, aud: str = BUNDLE_ID, iss: str = ISSUER) -> str:
    # Apple signs with RS256; the client relies on TLS for the back channel,
    # so any signature works here. A throwaway HMAC keeps the shape real.
    return jwt.encode({"iss": iss, "aud": aud, "sub": sub}, "x" * 32, algorithm="HS256")


@dataclass
class FakeApple:
    """Scripted ``appleid.apple.com``. Each queue entry is (status, json body)."""

    public_key: ec.EllipticCurvePublicKey
    token_responses: list[tuple[int, object]] = field(default_factory=list)
    revoke_responses: list[tuple[int, object]] = field(default_factory=list)
    calls: list[tuple[str, dict[str, str]]] = field(default_factory=list)
    issued: list[str] = field(default_factory=list)
    # The httpx timeout each request carried, in call order.
    timeouts: list[dict[str, float | None]] = field(default_factory=list)
    # Raised (not an HTTP answer) on a revoke call: an unexpected client failure.
    revoke_raises: Exception | None = None

    def grant(
        self, *, sub: str = SUBJECT, aud: str = BUNDLE_ID, iss: str = ISSUER
    ) -> str:
        refresh = f"r.apple-refresh-{len(self.issued)}"
        self.issued.append(refresh)
        self.token_responses.append(
            (
                200,
                {
                    "access_token": "a.apple-access",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                    "refresh_token": refresh,
                    "id_token": id_token(sub=sub, aud=aud, iss=iss),
                },
            )
        )
        return refresh

    def __call__(self, request: httpx.Request) -> httpx.Response:
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        self.calls.append((request.url.path, form))
        self.timeouts.append(dict(request.extensions.get("timeout") or {}))
        if request.url.path == "/auth/revoke" and self.revoke_raises is not None:
            raise self.revoke_raises
        secret = jwt.decode(
            form["client_secret"],
            self.public_key,
            algorithms=["ES256"],
            audience=ISSUER,
            issuer=TEAM_ID,
        )
        assert secret["sub"] == form["client_id"]
        queue = (
            self.token_responses
            if request.url.path == "/auth/token"
            else self.revoke_responses
        )
        status, body = queue.pop(0) if queue else (200, None)
        if body is None:
            return httpx.Response(status)
        return httpx.Response(status, json=body)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)
