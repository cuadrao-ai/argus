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
from uuid import uuid4

import pytest
from argus.domain.backtest_job_scopes import CHAT_RUN_SCOPE
from argus.llm.openrouter import (
    OpenRouterRouteReceipt,
    record_openrouter_route_receipt,
)
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


def _result_summary_receipt() -> OpenRouterRouteReceipt:
    from argus.agent_runtime.stages.explain import QuickTakeDraft

    prompt_tokens = fake.pyint(min_value=400, max_value=2400)
    completion_tokens = fake.pyint(min_value=40, max_value=700)
    return record_openrouter_route_receipt(
        task="result_summary",
        model_name=f"{fake.word()}/{fake.slug()}",
        mode="json_schema",
        schema_name=QuickTakeDraft.__name__,
        latency_ms=fake.pyint(min_value=300, max_value=30_000),
        outcome="succeeded",
        token_usage={
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
        usage_cost_usd=fake.pyfloat(min_value=0.0001, max_value=0.05, right_digits=6),
    )


def _seed_quick_take_turn(connection) -> dict[str, str]:
    """An owner's conversation with its request message, run and backtest job."""
    turn = {
        name: str(uuid4())
        for name in ("user_id", "conversation_id", "message_id", "run_id", "job_id")
    }
    email = f"route-tiers-{turn['user_id'][:8]}@argus.local"
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into auth.users (id, email) values (%s, %s)",
            (turn["user_id"], email),
        )
        cursor.execute(
            "insert into public.profiles (id, email) values (%s, %s)",
            (turn["user_id"], email),
        )
        cursor.execute(
            "insert into public.conversations (id, user_id, title) values (%s, %s, %s)",
            (turn["conversation_id"], turn["user_id"], fake.sentence(nb_words=4)),
        )
        cursor.execute(
            "insert into public.messages (id, conversation_id, user_id, role, content)"
            " values (%s, %s, %s, 'user', %s)",
            (
                turn["message_id"],
                turn["conversation_id"],
                turn["user_id"],
                fake.sentence(),
            ),
        )
        cursor.execute(
            """
            insert into public.backtest_runs
              (id, user_id, conversation_id, status, asset_class, symbols,
               benchmark_symbol, config_snapshot)
            values (%s, %s, %s, 'completed', 'equity', %s, 'SPY', '{}'::jsonb)
            """,
            (turn["run_id"], turn["user_id"], turn["conversation_id"], ["NFLX"]),
        )
        cursor.execute(
            """
            insert into public.backtest_jobs
              (id, user_id, operation_scope, idempotency_key, identity_hash,
               payload_hash, launch_payload, status, retryable, conversation_id)
            values (%s, %s, %s, %s, 'identity', 'payload', '{}'::jsonb,
                    'running', false, %s)
            """,
            (
                turn["job_id"],
                turn["user_id"],
                CHAT_RUN_SCOPE,
                f"key-{turn['job_id'][:8]}",
                turn["conversation_id"],
            ),
        )
    return turn


def _delete_turn(connection, turn: dict[str, str]) -> None:
    with connection.cursor() as cursor:
        for table in ("cost_ledger_entries", "route_receipts"):
            cursor.execute(
                f"delete from public.{table} where user_id = %s", (turn["user_id"],)
            )
        cursor.execute("delete from auth.users where id = %s", (turn["user_id"],))


def _render_workflow(turn: dict[str, str], receipt, monkeypatch) -> None:
    from workflows.backtest_job import (
        PostgresBacktestJobGateway,
        _persist_result_readout_route_receipts,
    )

    _persist_result_readout_route_receipts(
        PostgresBacktestJobGateway(DSN),
        receipts=[receipt],
        user_id=turn["user_id"],
        conversation_id=turn["conversation_id"],
        result_run_id=turn["run_id"],
        job_id=turn["job_id"],
        workflow_run_id=str(uuid4()),
    )


@pytest.mark.parametrize(
    ("persist", "ledger_source"),
    [(_render_workflow, "render_workflow")],
    ids=["render_workflow"],
)
def test_result_summary_receipt_and_its_cost_row_persist(
    persist, ledger_source, monkeypatch
) -> None:
    receipt = _result_summary_receipt()
    with _connect() as connection:
        turn = _seed_quick_take_turn(connection)
        try:
            persist(turn, receipt, monkeypatch)
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select receipt.task, receipt.tier, ledger.source, ledger.task,
                           ledger.metadata ->> 'tier', ledger.total_tokens
                    from public.route_receipts receipt
                    left join public.cost_ledger_entries ledger
                      on ledger.route_receipt_id = receipt.id
                    where receipt.user_id = %s
                    """,
                    (turn["user_id"],),
                )
                rows = cursor.fetchall()
        finally:
            _delete_turn(connection, turn)

    assert rows == [
        (
            receipt.task,
            receipt.tier,
            ledger_source,
            receipt.task,
            receipt.tier,
            receipt.token_usage["total_tokens"],
        )
    ]


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
