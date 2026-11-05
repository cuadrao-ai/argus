"""Plaid webhook verification, exactly as Plaid documents it.

1. The ``Plaid-Verification`` header is a JWS. Its header must say ``ES256``;
   any other algorithm (including ``none`` and HMAC) is refused before any key
   lookup.
2. The ``kid`` names a key fetched from ``/webhook_verification_key/get`` and
   cached (``webhook_keys``). A key whose ``expired_at`` is set is refused.
3. The signature is checked with that key, ES256 only.
4. ``iat`` must be within five minutes of now (old or far-future tokens fail).
5. ``request_body_sha256`` must equal the SHA-256 of the exact raw body bytes,
   compared in constant time.

Steps 4 and 5 also run on the unverified claims before any key lookup, so a
stale or mismatched token costs no Plaid call; they run again on the verified
claims. Every refusal raises the same ``WebhookRejected`` so a caller cannot
tell why; the reason is logged as a short code. A token seen before inside its
validity window is reported as a duplicate so the caller can skip repeated
work; a caller whose handling then fails calls ``release`` so a retried
delivery of that token is processed instead of skipped.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import jwt

from argus.domain.ingestion.plaid.webhook_keys import (
    FETCH_BUDGET,
    KEY_TTL,
    MAX_AGE,
    UNKNOWN_KID_TTL,
    KeyStore,
    VerificationUnavailable,
    WebhookRejected,
    reject,
)

__all__ = [
    "FETCH_BUDGET",
    "KEY_TTL",
    "MAX_AGE",
    "UNKNOWN_KID_TTL",
    "VerificationUnavailable",
    "VerifiedWebhook",
    "WebhookRejected",
    "WebhookVerifier",
]

ALGORITHM = "ES256"
MAX_TOKEN_CHARS = 4096
MAX_BODY_BYTES = 64 * 1024
_MAX_SEEN = 2048


@dataclass(frozen=True)
class VerifiedWebhook:
    payload: dict[str, Any]
    duplicate: bool


class WebhookVerifier:
    def __init__(
        self,
        fetch_key: Callable[[str], dict[str, Any]],
        *,
        clock: Callable[[], datetime],
        key_ttl=KEY_TTL,  # noqa: ANN001
    ) -> None:
        self._clock = clock
        self._keys = KeyStore(fetch_key, clock=clock, key_ttl=key_ttl)
        self._seen: dict[str, datetime] = {}
        self._lock = threading.Lock()

    def verify(self, token: str | None, body: bytes) -> VerifiedWebhook:
        if not token or len(token) > MAX_TOKEN_CHARS or len(body) > MAX_BODY_BYTES:
            raise reject("malformed")
        try:
            header = jwt.get_unverified_header(token)
            unverified = jwt.decode(token, options={"verify_signature": False})
        except jwt.PyJWTError:
            raise reject("malformed") from None
        if header.get("alg") != ALGORITHM:
            raise reject("algorithm")
        kid = header.get("kid")
        if not isinstance(kid, str) or not 0 < len(kid) <= 128:
            raise reject("kid")
        now = self._clock()
        self._claims(unverified, body, now)
        jwk = self._keys.get(kid)
        if jwk.get("expired_at") is not None:
            raise reject("expired_key")
        try:
            key = jwt.PyJWK(jwk, algorithm=ALGORITHM).key
            claims = jwt.decode(
                token,
                key=key,
                algorithms=[ALGORITHM],
                options={"verify_iat": False, "verify_exp": False, "verify_aud": False},
            )
        except (jwt.PyJWTError, ValueError, TypeError):
            raise reject("signature") from None
        issued = self._claims(claims, body, now)
        try:
            payload = json.loads(body)
        except ValueError:
            raise reject("body") from None
        if not isinstance(payload, dict):
            raise reject("body")
        return VerifiedWebhook(payload, self._remember(token, issued + MAX_AGE, now))

    @staticmethod
    def _claims(claims: dict[str, Any], body: bytes, now: datetime) -> datetime:
        iat = claims.get("iat")
        if not isinstance(iat, int) or isinstance(iat, bool):
            raise reject("iat")
        issued = datetime.fromtimestamp(iat, tz=now.tzinfo)
        if issued < now - MAX_AGE or issued > now + MAX_AGE:
            raise reject("iat")
        claimed = claims.get("request_body_sha256")
        actual = hashlib.sha256(body).hexdigest()
        if not isinstance(claimed, str) or not hmac.compare_digest(
            claimed.encode(), actual.encode()
        ):
            raise reject("body_hash")
        return issued

    def release(self, token: str) -> None:
        """Forget a token whose handling failed, so its retry is not a duplicate."""

        with self._lock:
            self._seen.pop(_digest(token), None)

    def _remember(self, token: str, until: datetime, now: datetime) -> bool:
        digest = _digest(token)
        with self._lock:
            for seen, expiry in list(self._seen.items()):
                if expiry <= now:
                    del self._seen[seen]
            if digest in self._seen:
                return True
            if len(self._seen) >= _MAX_SEEN:
                self._seen.pop(next(iter(self._seen)))
            self._seen[digest] = until
            return False


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
