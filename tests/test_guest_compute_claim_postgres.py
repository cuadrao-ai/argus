"""Real-Postgres proof for the atomic guest compute claim.

Skip-gated on ``ARGUS_DISPOSABLE_DATABASE_URL``. The in-memory suite already
covers the race; this locks the production transaction under simultaneous
claims.
"""

from __future__ import annotations

import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from argus.domain.usage_limits import (
    GUEST_COMPUTE_CEILING_RESOURCE,
    GUEST_COMPUTE_DAILY_CEILING,
)
from argus.domain.visitor_usage import guest_session_compute_key

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()

psycopg = pytest.importorskip("psycopg")

needs_database = pytest.mark.skipif(
    not DSN,
    reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured",
)


def _connect():
    return psycopg.connect(DSN, autocommit=True)


def _keys() -> tuple[str, str]:
    return (
        f"visitor:compute-proof-{secrets.token_hex(12)}",
        guest_session_compute_key(f"00000000-0000-4000-8000-{secrets.token_hex(6)}"),
    )


def _claim(
    visitor_key: str,
    session_key: str,
    *,
    visitor_limit: int = GUEST_COMPUTE_DAILY_CEILING,
    session_limit: int = 2,
    barrier: Barrier | None = None,
) -> dict:
    if barrier is not None:
        barrier.wait(timeout=5)
    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "select public.claim_guest_compute_usage(%s, %s, %s, %s, %s)",
            (
                visitor_key,
                session_key,
                GUEST_COMPUTE_CEILING_RESOURCE,
                visitor_limit,
                session_limit,
            ),
        )
        row = cursor.fetchone()
    assert row is not None
    return row[0]


def _used(key: str) -> int:
    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "select used_count from public.visitor_usage_counters"
            " where visitor_key = %s and resource = %s and period = 'day'",
            (key, GUEST_COMPUTE_CEILING_RESOURCE),
        )
        row = cursor.fetchone()
    return int(row[0]) if row else 0


def _delete(*keys: str) -> None:
    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "delete from public.visitor_usage_counters"
            " where visitor_key = any(%s)",
            (list(keys),),
        )


@needs_database
def test_simultaneous_claims_cannot_both_take_the_final_slot() -> None:
    visitor_key, session_key = _keys()
    try:
        assert _claim(visitor_key, session_key, session_limit=2)["available"] is True
        simultaneous = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda _: _claim(
                        visitor_key,
                        session_key,
                        session_limit=2,
                        barrier=simultaneous,
                    ),
                    range(2),
                )
            )
        accepted = [item for item in results if item.get("available") is True]
        assert len(accepted) == 1
        assert _used(visitor_key) == 2
        assert _used(session_key) == 2
    finally:
        _delete(visitor_key, session_key)
