"""Trusted client-IP resolution for visitor keys and edge rate limits.

Render sits behind Cloudflare. The first ``X-Forwarded-For`` hop is
client-controlled: Cloudflare and Render append to whatever the caller sent.
The single owner of client IP for keying and rate limits is the header
Cloudflare actually overwrites on the path to origin, configurable via
``ARGUS_TRUSTED_CLIENT_IP_HEADER`` and defaulting to ``CF-Connecting-IP``.
When that header is absent (local dev and tests), the socket peer is used.
``X-Forwarded-For`` is never consulted.

A trusted value of ``ip:port`` has its port stripped. A dotted IPv4 with
leading zeros is rejected to the socket peer with its own log line
(``client_ip_rejected_non_canonical``) instead of being guessed at, because
leading zeros read as octal in some parsers and decimal in others.
"""

from __future__ import annotations

import ipaddress
import os
import threading
import time

from fastapi import Request
from loguru import logger

DEFAULT_TRUSTED_CLIENT_IP_HEADER = "CF-Connecting-IP"
TRUSTED_CLIENT_IP_HEADER_ENV = "ARGUS_TRUSTED_CLIENT_IP_HEADER"
FALLBACK_WARN_INTERVAL_SECONDS = 60.0

_FALLBACK_WARN_LOCK = threading.Lock()
# One throttle window per reason, so one noisy reason cannot hide another.
_last_fallback_warn_at: dict[str, float] = {}
_FALLBACK_WARN_MESSAGES = {
    "missing": "Trusted client-IP header missing; using socket peer",
    "invalid": "Trusted client-IP header present but invalid; using socket peer",
    "non_canonical": "client_ip_rejected_non_canonical",
}


def trusted_client_ip_header_name() -> str:
    raw = os.getenv(TRUSTED_CLIENT_IP_HEADER_ENV, "").strip()
    return raw or DEFAULT_TRUSTED_CLIENT_IP_HEADER


def reset_trusted_header_fallback_warning_for_tests() -> None:
    with _FALLBACK_WARN_LOCK:
        _last_fallback_warn_at.clear()


def _hosted_runtime() -> bool:
    persistence = os.getenv("CUADRAO_PERSISTENCE_MODE", "memory").strip().lower()
    if persistence != "supabase":
        return False
    return os.getenv("ARGUS_DEV_MEMORY_FALLBACK", "").strip().lower() != "true"


def _warn_trusted_header_fallback(
    *, header_name: str, peer: str, reason: str
) -> None:
    if not _hosted_runtime():
        return
    now = time.monotonic()
    with _FALLBACK_WARN_LOCK:
        last = _last_fallback_warn_at.get(reason)
        if last is not None and now - last < FALLBACK_WARN_INTERVAL_SECONDS:
            return
        _last_fallback_warn_at[reason] = now
    logger.warning(_FALLBACK_WARN_MESSAGES[reason], header=header_name, peer=peer)


def _parse_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    candidate = value.strip()
    if candidate.startswith("[") and "]" in candidate:
        candidate = candidate[1 : candidate.index("]")]
    try:
        return ipaddress.ip_address(candidate)
    except ValueError:
        return None


def _strip_ipv4_port(value: str) -> str:
    """Drop a numeric ``:port`` from a dotted IPv4 value.

    Bracketed IPv6 (``[addr]:port``) is handled by ``_parse_ip``. A bare
    IPv6 address has several colons and is returned unchanged.
    """
    host, separator, port = value.rpartition(":")
    is_port = port.isascii() and port.isdigit()
    if separator and ":" not in host and "." in host and is_port:
        return host
    return value


def _is_non_canonical_ipv4(value: str) -> bool:
    """Dotted decimal IPv4 where an octet carries a leading zero."""
    octets = value.split(".")
    return (
        len(octets) == 4
        and all(octet.isascii() and octet.isdigit() for octet in octets)
        and any(len(octet) > 1 and octet.startswith("0") for octet in octets)
    )


def canonical_client_ip(value: str) -> str | None:
    """Validate an address and return the visitor-key form.

    IPv4 stays per-address. IPv6 is grouped by its /64 so rotating
    addresses inside one prefix cannot mint a fresh guest cap. IPv4-mapped
    IPv6 follows the embedded IPv4 address. Garbage is rejected.
    """
    parsed = _parse_ip(value)
    if parsed is None:
        return None
    if isinstance(parsed, ipaddress.IPv6Address):
        mapped = parsed.ipv4_mapped
        if mapped is not None:
            return str(mapped)
        network = ipaddress.ip_network(f"{parsed}/64", strict=False)
        return str(network)
    return str(parsed)


def resolve_client_ip(request: Request) -> str:
    """The one client-IP read every visitor key and IP limiter must use."""
    header_name = trusted_client_ip_header_name()
    raw = request.headers.get(header_name)
    reason = "missing"
    if raw:
        value = _strip_ipv4_port(raw.split(",", 1)[0].strip())
        if value:
            if _is_non_canonical_ipv4(value):
                reason = "non_canonical"
            else:
                parsed = canonical_client_ip(value)
                if parsed is not None:
                    return parsed
                reason = "invalid"
    peer = request.client.host if request.client and request.client.host else "unknown"
    parsed_peer = canonical_client_ip(peer) if peer != "unknown" else None
    _warn_trusted_header_fallback(
        header_name=header_name,
        peer=peer,
        reason=reason,
    )
    # A missing peer is unknown. A present non-IP peer (TestClient, unix
    # socket) stays that stable identity instead of collapsing every
    # unparseable caller into one shared bucket.
    return parsed_peer or peer
