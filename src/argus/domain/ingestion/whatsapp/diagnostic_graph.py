"""Allowlisted metadata for the private, two-request diagnostic."""

from __future__ import annotations

import logging
import re
from contextvars import ContextVar

import httpx

from argus.domain.ingestion.whatsapp.media import _graph_cause, graph_error

_active = ContextVar("whatsapp_private_request", default=False)
ID = re.compile(r"[0-9]{1,32}")
WORD = re.compile(r"[A-Za-z0-9_-]{1,128}")
SCOPES = frozenset(
    {
        "business_management",
        "whatsapp_business_management",
        "whatsapp_business_messaging",
        "public_profile",
    }
)


class _PrivateRequest(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not _active.get()


for _name in (
    "httpx",
    "httpcore",
    "httpcore.connection",
    "httpcore.http11",
    "httpcore.http2",
    "httpcore.proxy",
    "httpcore.socks",
):
    logging.getLogger(_name).addFilter(_PrivateRequest())


def matches(value: object, pattern: re.Pattern[str]) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _json(response: httpx.Response) -> dict:
    if len(response.content) > 65536:
        return {}
    try:
        value = response.json()
        return value if isinstance(value, dict) else {}
    except (ValueError, UnicodeError):
        return {}


def response_summary(response: httpx.Response) -> dict:
    result: dict = {
        "http_status": response.status_code
        if 100 <= response.status_code <= 599
        else "unknown"
    }
    body = _json(response)
    error = body.get("error")
    if isinstance(error, dict):
        fields = graph_error(response)
        result.update(
            {key: fields[key] for key in ("code", "error_subcode") if key in fields}
        )
        result["type"] = (
            fields.get("type")
            if fields.get("type") in {"OAuthException", "GraphMethodException"}
            else "unknown"
        )
        result["cause"] = _graph_cause(response, fields.get("code", "unknown"))
        if matches(error.get("fbtrace_id"), WORD):
            result["trace_id"] = error["fbtrace_id"]
    for source, target in (
        ("x-fb-request-id", "request_id"),
        ("x-fb-trace-id", "trace_id"),
    ):
        if matches(response.headers.get(source), WORD):
            result[target] = response.headers[source]
    return result


def identity(response: httpx.Response, app: str, subject: str) -> dict:
    result = response_summary(response)
    body = _json(response)
    data = body.get("data")
    if response.status_code != 200 or "error" in body or not isinstance(data, dict):
        return {**result, "matched": False}
    for key in ("app_id", "user_id"):
        if matches(data.get(key), ID):
            result[key] = data[key]
    result["valid"] = data.get("is_valid") is True
    result["type"] = (
        data.get("type")
        if data.get("type") in {"SYSTEM_USER", "USER", "PAGE", "APP"}
        else "unknown"
    )
    scopes = data.get("scopes")
    result["scopes"] = (
        sorted({s for s in scopes if isinstance(s, str) and s in SCOPES})
        if isinstance(scopes, list)
        else []
    )
    for key in ("expires_at", "data_access_expires_at"):
        value = data.get(key)
        if (
            isinstance(value, int)
            and not isinstance(value, bool)
            and 0 <= value <= 9999999999
        ):
            result[key] = value
    result["matched"] = bool(
        result["valid"]
        and result["type"] != "unknown"
        and result.get("app_id") == app
        and result.get("user_id") == subject
    )
    return result


def metadata(response: httpx.Response, media_id: str, max_bytes: int) -> dict:
    result = response_summary(response)
    body = _json(response)
    result["id_match"] = body.get("id") == media_id
    if matches(body.get("id"), ID):
        result["id"] = body["id"]
    if body.get("mime_type") == "application/pdf":
        result["mime_type"] = "application/pdf"
    size = body.get("file_size")
    if isinstance(size, int) and not isinstance(size, bool) and 0 <= size <= max_bytes:
        result["file_size"] = size
    result["matched"] = bool(
        response.status_code == 200
        and "error" not in body
        and result["id_match"]
        and "mime_type" in result
        and "file_size" in result
    )
    return result
