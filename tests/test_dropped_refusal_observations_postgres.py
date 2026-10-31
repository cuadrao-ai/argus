"""Real-Postgres proof that the refusal evidence store is gone and nothing else moved.

Set ``ARGUS_DISPOSABLE_DATABASE_URL`` only to an isolated Supabase Postgres
database with every checked-in migration applied; never point it at shared or
production data.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import pytest

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DSN,
    reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured",
)

psycopg = pytest.importorskip("psycopg")

DROPPED = ("public.refusal_observations", "public.refusal_log")
KEPT = (
    "public.argus_memory_vectors",
    "public.profiles",
    "public.spaces",
    "public.conversations",
    "public.messages",
    "public.chat_turn_lifecycles",
    "public.business_customers",
    "public.business_invoices",
    "public.financial_accounts",
    "public.context_packets",
    "public.run_context_packets",
    "public.collection_strategies",
)


@pytest.fixture(scope="module")
def cursor() -> Iterator[Any]:
    with psycopg.connect(DSN, autocommit=True) as connection:
        with connection.cursor() as cursor:
            yield cursor


def _exists(cursor: Any, name: str) -> bool:
    cursor.execute("select to_regclass(%s) is not null", (name,))
    return cursor.fetchone()[0]


@pytest.mark.parametrize("name", DROPPED)
def test_dropped_relation_is_gone(cursor: Any, name: str) -> None:
    assert not _exists(cursor, name)


def test_pair_validation_function_is_gone(cursor: Any) -> None:
    cursor.execute(
        "select to_regprocedure('public.validate_refusal_observation_pair()') is null"
    )
    assert cursor.fetchone()[0]


@pytest.mark.parametrize("name", KEPT)
def test_kept_relation_still_exists(cursor: Any, name: str) -> None:
    assert _exists(cursor, name)


def test_no_routine_body_names_a_dropped_relation(cursor: Any) -> None:
    cursor.execute(
        """
        select p.oid::regprocedure::text
          from pg_proc as p
          join pg_namespace as n on n.oid = p.pronamespace
         where n.nspname not in ('pg_catalog', 'information_schema')
           and p.prosrc ~ '\\m(refusal_observations|refusal_log)\\M'
        """
    )
    assert cursor.fetchall() == []


def test_every_foreign_key_targets_a_live_table(cursor: Any) -> None:
    cursor.execute(
        """
        select c.conname
          from pg_constraint as c
          left join pg_class as target on target.oid = c.confrelid
         where c.contype = 'f'
           and (target.oid is null or target.relkind not in ('r', 'p'))
        """
    )
    assert cursor.fetchall() == []
