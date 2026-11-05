"""Bounded HTTP client for Google OAuth and the Gmail API (no SDK).

Every call has a 30 second timeout, no redirects and a response-size cap read
in a stream, so a hostile or broken response cannot exhaust memory. 429 and
5xx answers are retried a bounded number of times with backoff (honoring a
short ``Retry-After``); the caller decides what a final failure means.

Failures become ``GmailError`` carrying only the HTTP status and Google's
structured reason codes, never a request body or a provider message, so a
token cannot leak through an exception or a log line.
"""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from argus.domain.ingestion.gmail.config import (
    GMAIL_API,
    REVOKE_URL,
    TOKEN_URL,
    GmailConfig,
)

TIMEOUT_SECONDS = 30.0
MAX_JSON_BYTES = 4 * 1024 * 1024
RETRYABLE = frozenset({429, 500, 502, 503, 504})
MAX_ATTEMPTS = 3
MAX_RETRY_AFTER_SECONDS = 8.0
_ID_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")


class GmailError(RuntimeError):
    def __init__(
        self, *, status: int | None, reason: str, reasons: frozenset[str] = frozenset()
    ) -> None:
        super().__init__(f"gmail {status}/{reason}")
        self.status = status
        self.reason = reason
        self.reasons = reasons | {reason}


@dataclass(frozen=True)
class TokenGrant:
    access_token: str = field(repr=False)
    refresh_token: str | None = field(repr=False)
    scopes: frozenset[str]
    # Set by Google only for time-limited grants; the refresh token then
    # stops working after this many seconds.
    refresh_expires_in: int | None = None


@dataclass(frozen=True)
class Profile:
    email: str
    history_id: str


class GmailClient:
    def __init__(
        self,
        config: GmailConfig,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = MAX_ATTEMPTS,
    ) -> None:
        self.config = config
        self._sleep = sleep
        self._attempts = max(1, max_attempts)
        self._http = httpx.Client(
            timeout=TIMEOUT_SECONDS, follow_redirects=False, transport=transport
        )

    def close(self) -> None:
        self._http.close()

    # OAuth -----------------------------------------------------------------

    def exchange_code(self, *, code: str, verifier: str) -> TokenGrant:
        payload = self._call(
            "POST",
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "redirect_uri": self.config.redirect_uri,
            },
            retry=False,
        )
        access = _text(payload, "access_token")
        refresh = payload.get("refresh_token")
        scopes = payload.get("scope")
        lifetime = payload.get("refresh_token_expires_in")
        return TokenGrant(
            access_token=access,
            refresh_token=refresh if isinstance(refresh, str) and refresh else None,
            scopes=frozenset(scopes.split()) if isinstance(scopes, str) else frozenset(),
            refresh_expires_in=lifetime
            if isinstance(lifetime, int) and not isinstance(lifetime, bool)
            else None,
        )

    def refresh(self, refresh_token: str) -> str:
        payload = self._call(
            "POST",
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
            },
        )
        return _text(payload, "access_token")

    def revoke(self, token: str) -> None:
        self._call("POST", REVOKE_URL, data={"token": token}, expect_json=False)

    # Gmail -----------------------------------------------------------------

    def profile(self, access: str) -> Profile:
        payload = self._call("GET", f"{GMAIL_API}/profile", token=access)
        return Profile(_text(payload, "emailAddress"), _text(payload, "historyId"))

    def list_messages(
        self, access: str, *, query: str, page_token: str | None, max_results: int
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"q": query, "maxResults": max_results}
        if page_token:
            params["pageToken"] = page_token
        return self._call("GET", f"{GMAIL_API}/messages", params=params, token=access)

    def get_message(
        self, access: str, message_id: str, *, fmt: str, headers: tuple[str, ...] = ()
    ) -> dict[str, Any]:
        params: list[tuple[str, str]] = [("format", fmt)]
        params.extend(("metadataHeaders", name) for name in headers)
        return self._call(
            "GET",
            f"{GMAIL_API}/messages/{_safe_id(message_id)}",
            params=params,
            token=access,
        )

    def get_attachment(
        self, access: str, message_id: str, attachment_id: str, *, max_bytes: int
    ) -> bytes:
        payload = self._call(
            "GET",
            f"{GMAIL_API}/messages/{_safe_id(message_id)}/attachments/"
            f"{_safe_id(attachment_id, limit=2048)}",
            token=access,
            # base64url inflates by 4/3; leave room for the JSON envelope.
            max_bytes=max_bytes * 4 // 3 + 4096,
        )
        return decode_base64url(_text(payload, "data"))

    def list_history(
        self,
        access: str,
        *,
        start_history_id: str,
        page_token: str | None,
        max_results: int,
    ) -> dict[str, Any]:
        params: list[tuple[str, str]] = [
            ("startHistoryId", start_history_id),
            ("maxResults", str(max_results)),
            ("historyTypes", "messageAdded"),
            ("historyTypes", "labelRemoved"),
        ]
        if page_token:
            params.append(("pageToken", page_token))
        return self._call("GET", f"{GMAIL_API}/history", params=params, token=access)

    # Transport ---------------------------------------------------------------

    def _call(
        self,
        method: str,
        url: str,
        *,
        params: Any = None,
        data: dict[str, str] | None = None,
        token: str | None = None,
        retry: bool = True,
        expect_json: bool = True,
        max_bytes: int = MAX_JSON_BYTES,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        attempts = self._attempts if retry else 1
        for attempt in range(attempts):
            last = attempt == attempts - 1
            try:
                status, body, retry_after = self._send(
                    method, url, params, data, headers, max_bytes
                )
            except httpx.HTTPError:
                if last:
                    raise GmailError(status=None, reason="unreachable") from None
                self._sleep(_backoff(attempt, None))
                continue
            if status in RETRYABLE and not last:
                self._sleep(_backoff(attempt, retry_after))
                continue
            payload = _json(body)
            if status != 200:
                raise _error(status, payload)
            if not expect_json:
                return {}
            if not isinstance(payload, dict):
                raise GmailError(status=status, reason="malformed_response")
            return payload
        raise GmailError(status=None, reason="unreachable")  # pragma: no cover

    def _send(
        self,
        method: str,
        url: str,
        params: Any,
        data: dict[str, str] | None,
        headers: dict[str, str],
        max_bytes: int,
    ) -> tuple[int, bytes, str | None]:
        with self._http.stream(
            method, url, params=params, data=data, headers=headers
        ) as response:
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > max_bytes:
                    raise GmailError(
                        status=response.status_code, reason="response_too_large"
                    )
            return response.status_code, bytes(body), response.headers.get("Retry-After")


def decode_base64url(data: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    except (ValueError, TypeError):
        raise GmailError(status=200, reason="malformed_response") from None


def _safe_id(value: str, limit: int = 64) -> str:
    """Provider ids go into URL paths; only their own alphabet is accepted."""

    if not value or len(value) > limit or not set(value) <= _ID_CHARS:
        raise GmailError(status=None, reason="malformed_id")
    return value


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


def _text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str) or not value:
        raise GmailError(status=200, reason="malformed_response")
    return value


def _code(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    cleaned = "".join(ch for ch in value if ch.isascii() and (ch.isalnum() or ch == "_"))
    return cleaned[:64] or None


def _error(status: int, payload: object) -> GmailError:
    reasons: list[str] = []
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, str):
            # OAuth endpoints: {"error": "invalid_grant", ...}
            reasons.append(error)
        elif isinstance(error, dict):
            for item in error.get("details") or ():
                if isinstance(item, dict):
                    reasons.append(item.get("reason"))
            for item in error.get("errors") or ():
                if isinstance(item, dict):
                    reasons.append(item.get("reason"))
            reasons.append(error.get("status"))
    codes = [code for code in (_code(r) for r in reasons) if code]
    primary = codes[0] if codes else f"http_{status}"
    return GmailError(status=status, reason=primary, reasons=frozenset(codes))
