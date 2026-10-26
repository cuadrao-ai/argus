"""Bounded media download from Meta's trusted hosts.

1. ``GET https://graph.facebook.com/{version}/{media-id}`` returns a short-lived
   URL, the MIME type and the size. Only the Graph host is ever asked.
2. The URL is fetched only when it is HTTPS on an allowlisted Meta CDN host,
   with the bearer token, no redirects, a Content-Length check and a streaming
   cap. A URL that 404s once is re-requested once, since it lives 5 minutes.

A 404 or 410 from either step means the media is gone: ``MediaUnavailable``
with ``expired=True``. The person can send it again.
"""

from __future__ import annotations

import hmac
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from loguru import logger

GRAPH_HOST = "graph.facebook.com"
DOWNLOAD_HOSTS = frozenset({"lookaside.fbsbx.com"})
DOWNLOAD_HOST_SUFFIXES = (".fbcdn.net",)
ACCEPTED_MEDIA_TYPES = frozenset({"application/pdf", "image/jpeg", "image/png"})
_GONE = frozenset({404, 410})
_TIMEOUT = httpx.Timeout(10.0)
_META_HOSTS = (GRAPH_HOST, *DOWNLOAD_HOSTS, *DOWNLOAD_HOST_SUFFIXES)


class _DropMetaRequestLines(logging.Filter):
    """httpx logs each request URL at INFO; Meta URLs carry media ids."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return not any(host in message for host in _META_HOSTS)


_httpx_logger = logging.getLogger("httpx")
if not any(isinstance(f, _DropMetaRequestLines) for f in _httpx_logger.filters):
    _httpx_logger.addFilter(_DropMetaRequestLines())


_GRAPH_NUMBER = re.compile(r"[0-9]{1,10}")
_GRAPH_WORD = re.compile(r"[A-Za-z0-9_]{1,40}")
_SAFE_GRAPH_LOG_VALUES = {
    "graph_code": frozenset(
        {
            "0",
            "3",
            "10",
            "100",
            "104",
            "190",
            "200",
            "131005",
            "131008",
            "131009",
            "131026",
        }
    ),
    "graph_error_subcode": frozenset({"463"}),
    "graph_type": frozenset({"GraphMethodException", "OAuthException"}),
}
_GRAPH_CAUSES = {
    "0": "authentication_failed",
    "3": "capability_or_permissions",
    "10": "permission_required",
    "190": "token_invalid_or_expired",
    "131005": "permission_required",
    "131008": "required_parameter_missing",
    "131009": "invalid_parameter",
    "131026": "undeliverable",
}
_MEDIA_STEPS = frozenset({"locate", "download"})
_MEDIA_REASONS = frozenset({"bad_media_id", "status", "transport", "payload"})
_SAFE_GRAPH_CAUSES = frozenset(
    {
        "unknown",
        "ambiguous",
        "appsecret_proof_invalid",
        "authentication_failed",
        "capability_or_permissions",
        "permission_required",
        "token_invalid_or_expired",
        "access_token_missing",
        "required_parameter_missing",
        "invalid_parameter",
        "undeliverable",
    }
)


def safe_graph_log_value(name: str, value: object) -> str:
    allowed = _SAFE_GRAPH_LOG_VALUES.get(name, frozenset())
    if isinstance(value, (int, str)) and not isinstance(value, bool):
        candidate = str(value)
        if candidate in allowed:
            return candidate
    return "unknown"


def graph_error(response: httpx.Response) -> dict[str, str]:
    """Return only bounded Graph code, subcode and type fields."""

    try:
        error = response.json().get("error") or {}
        found = {}
        for key, shape in (
            ("code", _GRAPH_NUMBER),
            ("error_subcode", _GRAPH_NUMBER),
            ("type", _GRAPH_WORD),
        ):
            value = error.get(key)
            if isinstance(value, (int, str)) and not isinstance(value, bool):
                found[key] = str(value) if shape.fullmatch(str(value)) else "unknown"
        return found
    except (ValueError, AttributeError):
        return {}


def _graph_cause(response: httpx.Response, code: str) -> str:
    if code == "100":
        try:
            error = response.json().get("error") or {}
            provider_type = error.get("type")
            if (
                isinstance(provider_type, str)
                and provider_type in {"GraphMethodException", "OAuthException"}
                and error.get("message")
                == "Invalid appsecret_proof provided in the API argument"
            ):
                return "appsecret_proof_invalid"
        except (ValueError, AttributeError):
            pass
        return "ambiguous"
    if code == "200":
        try:
            error = response.json().get("error") or {}
            if error.get("message") == "Provide valid app ID":
                return "access_token_missing"
        except (ValueError, AttributeError):
            pass
        return "unknown"
    if code == "104":
        return "ambiguous"
    return _GRAPH_CAUSES.get(code, "unknown")


def _unavailable(step: str, reason: str, **fields: str | int) -> MediaUnavailable:
    safe_step = step if step in _MEDIA_STEPS else "unknown"
    safe_reason = reason if reason in _MEDIA_REASONS else "unknown"
    safe_fields: dict[str, str | int] = {}
    for name, value in fields.items():
        if (
            name == "http_status"
            and isinstance(value, int)
            and not isinstance(value, bool)
            and 100 <= value <= 599
        ):
            safe_fields[name] = value
        elif name in {"graph_code", "graph_error_subcode"}:
            safe_fields[name] = safe_graph_log_value(name, value)
        elif name == "graph_type":
            safe_fields[name] = safe_graph_log_value(name, value)
        elif (
            name == "graph_cause"
            and isinstance(value, str)
            and value in _SAFE_GRAPH_CAUSES
        ):
            safe_fields[name] = value

    diagnostics = [f"step={safe_step}", f"reason={safe_reason}"]
    diagnostics.extend(f"{name}={value}" for name, value in safe_fields.items())
    logger.warning(
        f"WhatsApp media unavailable: {' '.join(diagnostics)}",
        step=safe_step,
        reason=safe_reason,
        **safe_fields,
    )
    return MediaUnavailable("whatsapp_media_unavailable")


class MediaRejected(Exception):
    """The media can never be captured: wrong type or too large."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class MediaUnavailable(Exception):
    """The media could not be fetched now; sending it again can succeed."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class FetchedMedia:
    content: bytes
    mime_type: str


def trusted_download_url(url: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    return (
        parts.scheme == "https"
        and parts.port is None
        and not parts.username
        and not parts.password
        and (host in DOWNLOAD_HOSTS or host.endswith(DOWNLOAD_HOST_SUFFIXES))
    )


class GraphMedia:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        access_token: str,
        graph_api_version: str,
        max_bytes: int,
    ) -> None:
        self._client = client
        self._headers = {"Authorization": f"Bearer {access_token}"}
        self._version = graph_api_version
        self._max_bytes = max_bytes

    async def diagnose_once(
        self,
        *,
        media_id: str,
        app_id: str,
        subject_id: str,
        runtime_token: str,
        selected_token: str,
        expires_at: int,
        on_attempt: Callable[[int], None] | None = None,
    ) -> dict:
        """Use this initialized client for identity and metadata only, with no retry."""
        from argus.domain.ingestion.whatsapp import diagnostic_graph as safe

        header = self._headers.get("Authorization", "")
        bearer = header.removeprefix("Bearer ") if header.startswith("Bearer ") else ""
        result = {
            "header_matches_runtime": hmac.compare_digest(
                bearer.encode(), runtime_token.encode()
            ),
            "header_matches_selected": hmac.compare_digest(
                bearer.encode(), selected_token.encode()
            ),
            "get_attempts": 0,
        }
        if (
            not bearer
            or time.time() >= expires_at
            or not all(safe.matches(v, safe.ID) for v in (media_id, app_id, subject_id))
        ):
            return {**result, "outcome": "invalid_runtime"}

        def finish(outcome: str) -> dict:
            import json

            candidate = {**result, "outcome": outcome}
            encoded = json.dumps(candidate)
            if any(
                value and value in encoded
                for value in (bearer, runtime_token, selected_token)
            ):
                return {
                    "outcome": "unsafe_response_stopped",
                    "get_attempts": result["get_attempts"],
                }
            return candidate

        private = safe._active.set(True)
        try:
            result["get_attempts"] = 1
            if on_attempt is not None:
                on_attempt(1)
            response = await self._client.get(
                f"https://{GRAPH_HOST}/{self._version}/debug_token",
                params={"input_token": bearer},
                headers=self._headers,
                timeout=_TIMEOUT,
                follow_redirects=False,
            )
            result["identity"] = safe.identity(response, app_id, subject_id)
            if not result["identity"]["matched"]:
                return finish("identity_stopped")
            if time.time() >= expires_at:
                return finish("expired")
            result["get_attempts"] = 2
            if on_attempt is not None:
                on_attempt(2)
            response = await self._client.get(
                f"https://{GRAPH_HOST}/{self._version}/{media_id}",
                headers=self._headers,
                timeout=_TIMEOUT,
                follow_redirects=False,
            )
            result["media"] = safe.metadata(response, media_id, self._max_bytes)
            return finish("metadata_observed")
        except Exception:
            return finish("transport_or_payload_stopped")
        finally:
            safe._active.reset(private)

    async def fetch(self, media_id: str) -> FetchedMedia:
        if not media_id.isascii() or not media_id.isdigit():
            raise _unavailable("locate", "bad_media_id")
        for _ in range(2):
            url, mime_type = await self._locate(media_id)
            content = await self._download(url)
            if content is not None:
                return FetchedMedia(content, mime_type)
        raise MediaUnavailable("whatsapp_media_expired")

    async def _locate(self, media_id: str) -> tuple[str, str]:
        try:
            response = await self._client.get(
                f"https://{GRAPH_HOST}/{self._version}/{media_id}",
                headers=self._headers,
                timeout=_TIMEOUT,
                follow_redirects=False,
            )
        except httpx.HTTPError:
            raise _unavailable("locate", "transport") from None
        if response.status_code in _GONE:
            raise MediaUnavailable("whatsapp_media_expired")
        if response.status_code != 200:
            error = graph_error(response)
            graph_code = error.get("code", "unknown")
            raise _unavailable(
                "locate",
                "status",
                http_status=response.status_code,
                graph_code=graph_code,
                graph_cause=_graph_cause(response, graph_code),
                **{
                    f"graph_{key}": value
                    for key, value in error.items()
                    if key != "code"
                },
            )
        try:
            meta = response.json()
            url, mime_type = str(meta["url"]), str(meta["mime_type"])
            size = int(meta.get("file_size") or 0)
        except (ValueError, KeyError, TypeError):
            raise _unavailable("locate", "payload") from None
        mime_type = mime_type.split(";", 1)[0].strip().lower()
        if mime_type not in ACCEPTED_MEDIA_TYPES:
            raise MediaRejected("whatsapp_media_unsupported")
        if size > self._max_bytes:
            raise MediaRejected("whatsapp_media_too_large")
        if not trusted_download_url(url):
            raise MediaUnavailable("whatsapp_media_untrusted")
        return url, mime_type

    async def _download(self, url: str) -> bytes | None:
        """The bytes, or ``None`` when the short-lived URL has already expired."""

        try:
            async with self._client.stream(
                "GET",
                url,
                headers=self._headers,
                timeout=_TIMEOUT,
                follow_redirects=False,
            ) as response:
                if response.status_code in _GONE:
                    return None
                if response.status_code != 200:
                    raise _unavailable(
                        "download", "status", http_status=response.status_code
                    )
                declared = response.headers.get("content-length")
                if declared is not None and (
                    not declared.isdigit() or int(declared) > self._max_bytes
                ):
                    raise MediaRejected("whatsapp_media_too_large")
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > self._max_bytes:
                        raise MediaRejected("whatsapp_media_too_large")
                return bytes(content)
        except httpx.HTTPError:
            raise _unavailable("download", "transport") from None
