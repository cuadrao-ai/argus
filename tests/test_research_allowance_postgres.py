"""Real-Postgres proofs for research provider admission.

Skip-gated on ``ARGUS_DISPOSABLE_DATABASE_URL``: point it at a disposable
Supabase-Postgres database with every migration applied, never production.
The in-memory proof reproduces the old read-then-settle race; this proof locks
the production transaction itself under two simultaneous claims. The release
proofs show that a failed provider attempt gives a guest back their own
question and never the shared ceiling's count (#609). The PostgREST round trip
also needs ``ARGUS_LOCAL_SUPABASE_URL`` and
``ARGUS_LOCAL_SUPABASE_SERVICE_ROLE_KEY``.
"""

from __future__ import annotations

import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from threading import Barrier

import pytest
from argus.api.chat.research_evidence import GLOBAL_CEILING_KEY, RESEARCH_USAGE_RESOURCE
from argus.domain.usage_limits import GUEST_RESEARCH_ALLOWANCE

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()
LOCAL_URL = os.getenv("ARGUS_LOCAL_SUPABASE_URL", "").strip()
LOCAL_SERVICE_KEY = os.getenv("ARGUS_LOCAL_SUPABASE_SERVICE_ROLE_KEY", "").strip()
MIGRATIONS = Path(__file__).parents[1] / "supabase/migrations_archive"

psycopg = pytest.importorskip("psycopg")

needs_database = pytest.mark.skipif(
    not DSN,
    reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured",
)


def _connect():
    return psycopg.connect(DSN, autocommit=True)


def _keys() -> tuple[str, str]:
    return (
        f"visitor:research-proof-{secrets.token_hex(12)}",
        f"global:research-proof-{secrets.token_hex(12)}",
    )


def _claim(
    visitor_key: str,
    global_key: str,
    *,
    barrier: Barrier | None = None,
) -> dict:
    with _connect() as connection, connection.cursor() as cursor:
        if barrier is not None:
            barrier.wait(timeout=5)
        cursor.execute(
            "select public.claim_research_usage(%s, %s, %s, %s, %s)",
            (visitor_key, RESEARCH_USAGE_RESOURCE, global_key, 5000, GUEST_RESEARCH_ALLOWANCE),
        )
        return cursor.fetchone()[0]


def _release(visitor_key: str, global_key: str, period_start: str) -> dict:
    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "select public.release_research_usage(%s, %s, %s, %s::timestamptz)",
            (visitor_key, RESEARCH_USAGE_RESOURCE, global_key, period_start),
        )
        return cursor.fetchone()[0]


def _used_count(visitor_key: str) -> int:
    """Today's count, by the UTC day the claim charges."""
    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "select used_count from public.visitor_usage_counters"
            " where visitor_key = %s and resource = %s and period = 'day'"
            " and period_start = date_trunc('day', now() at time zone 'utc')"
            " at time zone 'utc'",
            (visitor_key, RESEARCH_USAGE_RESOURCE),
        )
        row = cursor.fetchone()
        return row[0] if row else 0


def _delete_counts(*visitor_keys: str) -> None:
    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "delete from public.visitor_usage_counters" " where visitor_key = any(%s)",
            (list(visitor_keys),),
        )


@needs_database
def test_same_visitor_concurrent_claims_cannot_share_the_last_slot() -> None:
    visitor_key, global_key = _keys()
    try:
        for _ in range(GUEST_RESEARCH_ALLOWANCE - 1):
            assert _claim(visitor_key, global_key)["available"] is True

        simultaneous = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda _: _claim(visitor_key, global_key, barrier=simultaneous),
                    range(2),
                )
            )

        assert sum(result["available"] is True for result in results) == 1
        denied = next(result for result in results if result["available"] is False)
        assert denied["guest_exhausted"] is True
        assert _used_count(visitor_key) == GUEST_RESEARCH_ALLOWANCE
        assert _used_count(global_key) == GUEST_RESEARCH_ALLOWANCE
    finally:
        _delete_counts(visitor_key, global_key)


@needs_database
def test_a_failed_attempt_gives_the_guest_question_back_and_keeps_the_ceiling() -> None:
    visitor_key, global_key = _keys()
    try:
        claim = _claim(visitor_key, global_key)
        assert claim["available"] is True
        assert claim["period_start"]
        assert (_used_count(visitor_key), _used_count(global_key)) == (1, 1)

        assert _release(visitor_key, global_key, claim["period_start"]) == {
            "released": True
        }
        assert (_used_count(visitor_key), _used_count(global_key)) == (0, 1)

        # Nothing is left to return, and the count never goes below zero.
        assert _release(visitor_key, global_key, claim["period_start"]) == {
            "released": False
        }
        assert _used_count(visitor_key) == 0
    finally:
        _delete_counts(visitor_key, global_key)


@needs_database
def test_a_returned_question_can_be_asked_again_at_the_daily_limit() -> None:
    visitor_key, global_key = _keys()
    try:
        claims = [_claim(visitor_key, global_key) for _ in range(GUEST_RESEARCH_ALLOWANCE)]
        assert all(claim["available"] is True for claim in claims)
        assert _claim(visitor_key, global_key) == {
            "available": False,
            "guest_exhausted": True,
        }

        _release(visitor_key, global_key, claims[-1]["period_start"])

        assert _claim(visitor_key, global_key)["available"] is True
        assert _used_count(visitor_key) == GUEST_RESEARCH_ALLOWANCE
        assert _used_count(global_key) == GUEST_RESEARCH_ALLOWANCE + 1
    finally:
        _delete_counts(visitor_key, global_key)


@needs_database
def test_a_release_returns_only_the_day_the_claim_charged() -> None:
    visitor_key, global_key = _keys()
    try:
        claim = _claim(visitor_key, global_key)
        charged = datetime.fromisoformat(claim["period_start"])

        day_before = (charged - timedelta(days=1)).isoformat()
        assert _release(visitor_key, global_key, day_before) == {"released": False}
        assert _used_count(visitor_key) == 1
    finally:
        _delete_counts(visitor_key, global_key)


@needs_database
def test_a_release_can_never_return_the_shared_ceiling() -> None:
    visitor_key, global_key = _keys()
    try:
        claim = _claim(visitor_key, global_key)

        with pytest.raises(psycopg.errors.InvalidParameterValue):
            _release(global_key, global_key, claim["period_start"])

        assert _used_count(global_key) == 1
    finally:
        _delete_counts(visitor_key, global_key)


@pytest.mark.skipif(
    not (DSN and LOCAL_URL and LOCAL_SERVICE_KEY),
    reason="disposable local Supabase is not configured",
)
def test_the_api_gives_a_guest_question_back_through_postgrest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api import state as api_state
    from argus.api.chat.research_evidence import (
        claim_research_provider_attempt,
        release_research_provider_claim,
    )
    from argus.domain.supabase_gateway import SupabaseGateway

    from supabase import create_client

    monkeypatch.setenv("ARGUS_RESEARCH_RAIL_ENABLED", "true")
    monkeypatch.setattr(
        api_state,
        "supabase_gateway",
        SupabaseGateway(client=create_client(LOCAL_URL, LOCAL_SERVICE_KEY)),
    )
    guest, _ = _keys()
    ceiling_before = _used_count(GLOBAL_CEILING_KEY)
    try:
        admission = claim_research_provider_attempt(guest_visitor_key=guest)
        assert admission.available
        assert admission.period_start
        assert _used_count(guest) == 1

        assert release_research_provider_claim(admission, guest_visitor_key=guest) is True

        assert _used_count(guest) == 0
        assert _used_count(GLOBAL_CEILING_KEY) == ceiling_before + 1
        assert release_research_provider_claim(admission, guest_visitor_key=guest) is False
        assert _used_count(guest) == 0
    finally:
        _delete_counts(guest)


def test_claim_and_release_functions_are_service_role_only() -> None:
    for name in (
        "20260903000000_claim_research_usage.sql",
        "20260913230000_release_research_guest_claim.sql",
    ):
        migration = (MIGRATIONS / name).read_text().lower()
        assert "security definer" in migration, name
        assert "from public, anon, authenticated" in migration, name
        assert "to service_role" in migration, name
