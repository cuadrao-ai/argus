"""Visitor-scoped allowances: counters for callers with no durable account.

A guest workspace mints a fresh user_id whenever a session restarts, so
account-keyed guest allowances reset with it. Visitor counters key on a
keyed digest of the client identity instead and live in
``visitor_usage_counters`` (no profile FK). One digest, one table, shared by
every metered guest resource.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timezone
from typing import Any

from argus.domain.usage_limits import align_usage_period

VISITOR_USAGE_TABLE = "visitor_usage_counters"
_VISITOR_SUBJECT_PREFIX = "visitor:"
_SESSION_SUBJECT_PREFIX = "session:"
_REGISTERED_SUBJECT_PREFIX = "user:"


def visitor_digest(identity: str) -> str:
    """Keyed digest, never the raw value: the counter tells visitors apart
    without retaining addresses, and keying defeats brute-forcing IPv4."""
    secret = os.getenv("CUADRAO_VISITOR_KEY_SECRET", "argus-visitor-key").encode()
    return hmac.new(secret, identity.encode(), hashlib.sha256).hexdigest()[:32]


def visitor_key_for(client_identity: str | None) -> str:
    """Fails closed to one shared bucket when the identity is missing:
    an unmetered allowance is the worse failure."""
    identity = (client_identity or "").strip() or "unknown"
    return f"{_VISITOR_SUBJECT_PREFIX}{visitor_digest(identity)}"


def guest_session_compute_key(user_id: str | None) -> str:
    """Visitor-table subject for one authenticated guest workspace.

    The session id is already an opaque UUID, so it is stored as-is rather
    than re-hashed. Fails closed to one shared bucket when the id is missing.
    """
    identity = (user_id or "").strip() or "unknown"
    return f"{_SESSION_SUBJECT_PREFIX}{identity}"


def registered_account_usage_key(user_id: str | None) -> str:
    """Visitor-table subject for one signed-in account.

    The account id is already an opaque UUID, so it is stored as-is rather
    than re-hashed. Fails closed to one shared bucket when the id is missing.
    """
    identity = (user_id or "").strip() or "unknown"
    return f"{_REGISTERED_SUBJECT_PREFIX}{identity}"


def is_registered_account_usage_key(visitor_key: str | None) -> bool:
    return bool(visitor_key) and visitor_key.startswith(_REGISTERED_SUBJECT_PREFIX)


def read_visitor_used(
    client: Any,
    *,
    visitor_key: str,
    resource: str,
    period: str,
    now: datetime,
) -> int:
    start, _ = align_usage_period(now, period)
    rows = (
        client.table(VISITOR_USAGE_TABLE)
        .select("used_count")
        .eq("visitor_key", visitor_key)
        .eq("resource", resource)
        .eq("period", period)
        .eq("period_start", start.isoformat())
        .limit(1)
        .execute()
        .data
    )
    return int(rows[0].get("used_count", 0)) if rows else 0


def visitor_within_limits(
    client: Any,
    *,
    visitor_key: str,
    resource: str,
    limits: list[tuple[str, int]],
    now: datetime,
) -> bool:
    for period, limit_count in limits:
        used = read_visitor_used(
            client,
            visitor_key=visitor_key,
            resource=resource,
            period=period,
            now=now,
        )
        if used >= limit_count:
            return False
    return True


def settle_visitor_usage(
    client: Any,
    *,
    visitor_key: str,
    resource: str,
    limits: list[tuple[str, int]],
    now: datetime | None = None,
) -> None:
    at = now or datetime.now(timezone.utc)
    windows = []
    for period, limit_count in limits:
        start, end = align_usage_period(at, period)
        windows.append(
            {
                "period": period,
                "limit": limit_count,
                "period_start": start.isoformat(),
                "period_end": end.isoformat(),
            }
        )
    client.rpc(
        "settle_visitor_usage",
        {
            "p_visitor_key": visitor_key,
            "p_resource": resource,
            "p_windows": windows,
        },
    ).execute()


def purge_expired_visitor_usage(
    client: Any,
    *,
    before: datetime | None = None,
) -> int:
    """Delete counters whose window has passed. Returns the row count."""
    at = before or datetime.now(timezone.utc)
    purged = client.rpc(
        "purge_expired_visitor_usage",
        {"p_before": at.isoformat()},
    ).execute()
    return int(getattr(purged, "data", 0) or 0)


def settle_memory_visitor_usage(
    counters: dict[tuple[str, str, str], dict[str, Any]],
    *,
    visitor_key: str,
    resource: str,
    limits: list[tuple[str, int]],
    now: datetime | None = None,
) -> None:
    """In-memory twin of the database-owned visitor settlement."""
    at = now or datetime.now(timezone.utc)
    for period, limit_count in limits:
        start, end = align_usage_period(at, period)
        key = (visitor_key, resource, period)
        row = counters.get(key)
        if row is None or row.get("period_start") != start:
            counters[key] = {
                "period_start": start,
                "period_end": end,
                "used_count": 1,
                "limit_count": limit_count,
            }
        else:
            row["used_count"] = int(row.get("used_count", 0)) + 1
            row["limit_count"] = limit_count


def read_memory_visitor_used(
    counters: dict[tuple[str, str, str], dict[str, Any]],
    *,
    visitor_key: str,
    resource: str,
    period: str,
    now: datetime | None = None,
) -> int:
    at = now or datetime.now(timezone.utc)
    start, _ = align_usage_period(at, period)
    row = counters.get((visitor_key, resource, period))
    if row is None or row.get("period_start") != start:
        return 0
    return int(row.get("used_count", 0))


def memory_visitor_within_limits(
    counters: dict[tuple[str, str, str], dict[str, Any]],
    *,
    visitor_key: str,
    resource: str,
    limits: list[tuple[str, int]],
    now: datetime | None = None,
) -> bool:
    for period, limit_count in limits:
        used = read_memory_visitor_used(
            counters,
            visitor_key=visitor_key,
            resource=resource,
            period=period,
            now=now,
        )
        if used >= limit_count:
            return False
    return True
