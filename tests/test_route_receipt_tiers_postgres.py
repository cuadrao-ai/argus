"""Route receipts persist for every model tier the runtime declares (#605).

A result_summary receipt from the runtime's own receipt builder, and the cost
ledger row derived from it, go through both production writers: the API turn
over PostgREST and the Render workflow over SQL. The database's tier check is
read back and compared with the runtime's tier set.

Set ``ARGUS_DISPOSABLE_DATABASE_URL`` plus ``ARGUS_LOCAL_SUPABASE_URL`` and
``ARGUS_LOCAL_SUPABASE_SERVICE_ROLE_KEY`` to run locally.
"""

from __future__ import annotations

import os
from typing import get_args

import pytest
from argus.llm.openrouter_tasks import OpenRouterModelTier
from argus.observability.route_receipt_tiers import TIER_CHECK_CONSTRAINT_NAME
from faker import Faker

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()
LOCAL_URL = os.getenv("ARGUS_LOCAL_SUPABASE_URL", "").strip()
LOCAL_SERVICE_KEY = os.getenv("ARGUS_LOCAL_SUPABASE_SERVICE_ROLE_KEY", "").strip()

pytestmark = pytest.mark.skipif(
    not (DSN and LOCAL_URL and LOCAL_SERVICE_KEY),
    reason="disposable local Supabase is not configured",
)
psycopg = pytest.importorskip("psycopg")

fake = Faker()


def _connect():
    return psycopg.connect(DSN, autocommit=True)












def test_tier_check_admits_exactly_the_runtime_tiers() -> None:
    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            select tier_check.conname, tier_check.convalidated,
                   pg_get_constraintdef(tier_check.oid)
            from pg_constraint tier_check
            join pg_attribute tier_column
              on tier_column.attrelid = tier_check.conrelid
             and tier_column.attnum = any(tier_check.conkey)
            where tier_check.conrelid = 'public.route_receipts'::regclass
              and tier_check.contype = 'c'
              and tier_column.attname = 'tier'
            """
        )
        checks = cursor.fetchall()

    tiers = ", ".join(f"'{tier}'::text" for tier in get_args(OpenRouterModelTier))
    assert checks == [
        (TIER_CHECK_CONSTRAINT_NAME, True, f"CHECK ((tier = ANY (ARRAY[{tiers}])))")
    ]
