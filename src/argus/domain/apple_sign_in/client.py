"""Bounded HTTP client for Apple's token and revoke endpoints (no SDK).

Every call mints a fresh client secret, has a 30 second timeout, no redirects
and a response-size cap read in a stream. Failures become ``AppleError``
carrying only the HTTP status and Apple's OAuth ``error`` code, never a request
body, a token or a provider message, so a credential cannot leak through an
exception or a log line.

The authorization-code exchange is not retried: Apple's codes are single use,
so a retry after an ambiguous failure would only ever see ``invalid_grant``.
Revocation is idempotent and is retried on 429/5xx with bounded backoff. A
caller on a user's request path (the capture route's compensating revoke) can
ask for one short attempt instead, so that request stays well under 10 seconds.

The identity token in the exchange response arrives over TLS directly from
Apple's token endpoint, so its signature check is replaced by TLS server
validation (OpenID Connect Core 3.1.3.7, step 6). Its issuer, audience and
subject are still checked before the caller trusts it.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import jwt

from argus.domain.apple_sign_in.client_secret import client_secret
from argus.domain.apple_sign_in.config import (
    ISSUER,
    REVOKE_URL,
    TOKEN_URL,
    AppleSignInConfig,
)

TIMEOUT_SECONDS = 30.0
# The compensating revoke inside a capture request: one attempt, two seconds per
# phase, so the extra call can't hold the person's request for long.
DISCARD_TIMEOUT_SECONDS = 2.0
MAX_JSON_BYTES = 64 * 1024
RETRYABLE = frozenset({429, 500, 502, 503, 504})
MAX_ATTEMPTS = 3
MAX_RETRY_AFTER_SECONDS = 8.0
MAX_CODE_LENGTH = 512


class AppleError(RuntimeError):
    def __init__(self, *, status: int | None, reason: str) -> None:
        super().__init__(f"apple {status}/{reason}")
        self.status = status
        self.reason = reason

    @property
    def invalid_grant(self) -> bool:
        """The code was expired, already used, or issued to another client."""

        return self.status == 400 and self.reason == "invalid_grant"


@dataclass(frozen=True)
class AppleGrant:
    refresh_token: str = field(repr=False)
    subject: str


class AppleAuthClient:
    def __init__(
        self,
        config: AppleSignInConfig,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = MAX_ATTEMPTS,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self._sleep = sleep
        self._monotonic = monotonic
        self._attempts = max(1, max_attempts)
        self._http = httpx.Client(
            timeout=TIMEOUT_SECONDS, follow_redirects=False, transport=transport
        )

    def close(self) -> None:
        self._http.close()

    def exchange_code(self, code: str) -> AppleGrant:
        if not code or len(code) > MAX_CODE_LENGTH or not code.isascii():
            raise AppleError(status=None, reason="malformed_code")
        payload = self._call(
            TOKEN_URL,
            {
                "client_id": self.config.client_id,
                "client_secret": client_secret(self.config),
                "code": code,
                "grant_type": "authorization_code",
            },
            retry=False,
        )
        refresh = payload.get("refresh_token")
        if not isinstance(refresh, str) or not refresh:
            raise AppleError(status=200, reason="missing_refresh_token")
        return AppleGrant(refresh_token=refresh, subject=self._subject(payload))

    def revoke(
        self,
        refresh_token: str,
        *,
        client_id: str,
        timeout: float | None = None,
        attempts: int | None = None,
    ) -> None:
        """Apple answers 200 for a revoked token and for one it no longer knows
        (RFC 7009), so 200 is the only proof and every other answer raises.
        ``client_id`` is the client the token was issued to, as stored.
        ``timeout`` and ``attempts`` narrow this one call (the defaults are the
        client's 30 seconds and three attempts)."""

        self._call(
            REVOKE_URL,
            {
                "client_id": client_id,
                "client_secret": client_secret(self.config, client_id=client_id),
                "token": refresh_token,
                "token_type_hint": "refresh_token",
            },
            expect_json=False,
            timeout=timeout,
            attempts=attempts,
        )

    def _subject(self, payload: dict[str, Any]) -> str:
        token = payload.get("id_token")
        if not isinstance(token, str) or not token:
            raise AppleError(status=200, reason="missing_id_token")
        try:
            claims = jwt.decode(
                token,
                options={
                    "verify_signature": False,
                    "verify_exp": False,
                    "verify_aud": False,
                    "verify_iss": False,
                },
            )
        except jwt.PyJWTError:
            raise AppleError(status=200, reason="malformed_id_token") from None
        subject = claims.get("sub")
        if (
            claims.get("iss") != ISSUER
            or claims.get("aud") != self.config.client_id
            or not isinstance(subject, str)
            or not subject
        ):
            raise AppleError(status=200, reason="unexpected_id_token")
        return subject

    def _call(
        self,
        url: str,
        data: dict[str, str],
        *,
        retry: bool = True,
        expect_json: bool = True,
        timeout: float | None = None,
        attempts: int | None = None,
    ) -> dict[str, Any]:
        if not retry:
            attempts = 1
        attempts = max(1, min(attempts or self._attempts, self._attempts))
        for attempt in range(attempts):
            last = attempt == attempts - 1
            try:
                status, body, retry_after = self._send(url, data, timeout)
            except httpx.HTTPError:
                if last:
                    raise AppleError(status=None, reason="unreachable") from None
                self._sleep(_backoff(attempt, None))
                continue
            if status in RETRYABLE and not last:
                self._sleep(_backoff(attempt, retry_after))
                continue
            payload = _json(body)
            if status != 200:
                raise AppleError(status=status, reason=_reason(status, payload))
            if not expect_json:
                return {}
            if not isinstance(payload, dict):
                raise AppleError(status=status, reason="malformed_response")
            return payload
        raise AppleError(status=None, reason="unreachable")  # pragma: no cover

    def _send(
        self, url: str, data: dict[str, str], timeout: float | None
    ) -> tuple[int, bytes, str | None]:
        # httpx's timeouts bound each phase and each read, not the whole
        # request: a response trickled in small chunks would never trip them.
        # One request may take ``timeout`` seconds in total, checked when the
        # headers arrive and after every body chunk.
        limit = timeout or TIMEOUT_SECONDS
        deadline = self._monotonic() + limit
        with self._http.stream(
            "POST",
            url,
            data=data,
            headers={"Accept": "application/json"},
            timeout=httpx.Timeout(timeout or TIMEOUT_SECONDS),
        ) as response:
            self._check(deadline)
            body = bytearray()
            for chunk in response.iter_bytes():
                self._check(deadline)
                body.extend(chunk)
                if len(body) > MAX_JSON_BYTES:
                    raise AppleError(
                        status=response.status_code, reason="response_too_large"
                    )
            return response.status_code, bytes(body), response.headers.get("Retry-After")

    def _check(self, deadline: float) -> None:
        if self._monotonic() > deadline:
            raise httpx.ReadTimeout("Apple response exceeded its total deadline")


def _backoff(attempt: int, retry_after: str | None) -> float:
    if retry_after is not None:
        try:
            return max(0.0, min(float(retry_after), MAX_RETRY_AFTER_SECONDS))
        except ValueError:
            pass
    return min(0.5 * (2**attempt), MAX_RETRY_AFTER_SECONDS)


def _json(body: bytes) -> object:
    try:
        return json.loads(body) if body else None
    except ValueError:
        return None


def _reason(status: int, payload: object) -> str:
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, str):
        cleaned = "".join(
            ch for ch in error if ch.isascii() and (ch.isalnum() or ch == "_")
        )[:64]
        if cleaned:
            return cleaned
    return f"http_{status}"
