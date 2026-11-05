"""Real-Postgres proof for the atomic signed-in compute claim.

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
from argus.domain.usage_limits import REGISTERED_COMPUTE_CEILING_RESOURCE
from argus.domain.visitor_usage import registered_account_usage_key

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()

psycopg = pytest.importorskip("psycopg")

needs_database = pytest.mark.skipif(
    not DSN,
    reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured",
)


def _connect():
    return psycopg.connect(DSN, autocommit=True)


def _account_key() -> str:
    return registered_account_usage_key(
        f"00000000-0000-4000-8000-{secrets.token_hex(6)}"
    )


def _claim(
    account_key: str,
    *,
    limit: int = 2,
    barrier: Barrier | None = None,
) -> dict:
    if barrier is not None:
        barrier.wait(timeout=5)
    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "select public.claim_registered_compute_usage(%s, %s, %s)",
            (account_key, REGISTERED_COMPUTE_CEILING_RESOURCE, limit),
        )
        row = cursor.fetchone()
    assert row is not None
    return row[0]


def _used(key: str) -> int:
    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "select used_count from public.visitor_usage_counters"
            " where visitor_key = %s and resource = %s and period = 'day'",
            (key, REGISTERED_COMPUTE_CEILING_RESOURCE),
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
def test_simultaneous_registered_claims_cannot_both_take_the_final_slot() -> None:
    account_key = _account_key()
    try:
        assert _claim(account_key, limit=2)["available"] is True
        simultaneous = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda _: _claim(
                        account_key,
                        limit=2,
                        barrier=simultaneous,
                    ),
                    range(2),
                )
            )
        accepted = [item for item in results if item.get("available") is True]
        assert len(accepted) == 1
        assert _used(account_key) == 2
    finally:
        _delete(account_key)
