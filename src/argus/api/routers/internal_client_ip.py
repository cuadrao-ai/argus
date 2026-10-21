"""Ops-gated, read-only report of how the API resolved a caller's IP (#694).

Built for one purpose: the forged-header check at the promotion that carries #674.
It answers what the request carried and which address the single client-IP owner
(`argus.api.client_ip.resolve_client_ip`) chose, so a forged `CF-Connecting-IP`,
`True-Client-IP` or `X-Forwarded-For` can be seen to win or lose. It changes nothing.

It is off unless `ARGUS_CLIENT_IP_ECHO_ENABLED` is true, and even then it answers a
byte-identical 404 without the ops token. Turn it off, or remove this module, after
the check. It is left out of the OpenAPI document on purpose.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from argus.api.client_ip import resolve_client_ip, trusted_client_ip_header_name
from argus.api.ops_contract import CLIENT_IP_ECHO_PATH
from argus.api.routers.ops import _require_ops_authorization

CLIENT_IP_ECHO_ENV = "ARGUS_CLIENT_IP_ECHO_ENABLED"
_ECHOED_HEADERS = (
    "cf-connecting-ip",
    "cf-connecting-o2o",
    "true-client-ip",
    "x-forwarded-for",
    "x-real-ip",
    "host",
)

router = APIRouter(tags=["ops"])


def _enabled() -> bool:
    return os.getenv(CLIENT_IP_ECHO_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


@router.get(CLIENT_IP_ECHO_PATH, include_in_schema=False)
def client_ip_report(
    request: Request,
    response: Response,
    _: None = Depends(_require_ops_authorization),
) -> dict[str, object]:
    if not _enabled():
        raise HTTPException(status_code=404, detail="Not found")
    response.headers["Cache-Control"] = "no-store"
    peer = request.client.host if request.client and request.client.host else None
    return {
        "resolved_client_ip": resolve_client_ip(request),
        "trusted_header": trusted_client_ip_header_name(),
        "socket_peer": peer,
        "headers": {name: request.headers.get(name) for name in _ECHOED_HEADERS},
    }
