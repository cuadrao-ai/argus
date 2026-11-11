"""A Render workflow proof job is not conversation activity, on real Postgres.

The seeder writes the proof's scope and no conversation, so every activity
reader, which joins jobs to a conversation, cannot see it. A row the seeder
wrote before this contract (the column default made it a chat job) projects
``checking`` until the migration's reclassification statement moves it; the
statement is executed here as checked in.

Set ``ARGUS_DISPOSABLE_DATABASE_URL`` only to an isolated Supabase Postgres
database with all checked-in migrations applied.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from argus.api.conversation_activity import source_from_row
from argus.domain.conversation_activity import project_conversation_activity

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not DSN,
    reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured",
)
psycopg = pytest.importorskip("psycopg")

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT
    / "supabase/migrations_archive/20260905000000_workflow_proof_jobs_leave_conversations.sql"
)


def _connect():
    return psycopg.connect(DSN, autocommit=True)


def _proof_gateway():
    from workflows.proof import PostgresProofJobGateway

    return PostgresProofJobGateway(DSN)


def _seed_principal(gateway) -> str:
    from workflows.proof import proof_user_email

    user_id = str(uuid4())
    gateway.ensure_proof_profile(user_id=user_id, email=proof_user_email(user_id))
    return user_id


def _seed_conversation(connection, *, user_id: str) -> str:
    conversation_id = str(uuid4())
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into public.conversations (id, user_id, title, title_source)"
            " values (%s, %s, 'Render Workflow Proof', 'system_default')",
            (conversation_id, user_id),
        )
    return conversation_id


def _job_sources(connection, *, user_id: str, conversation_id: str) -> list[dict]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select sources from public.read_conversation_activity_sources(%s, %s)",
            (user_id, [conversation_id]),
        )
        row = cursor.fetchone()
    assert row is not None
    return [source for source in row[0] if source["source_kind"] == "backtest_job"]


def _trimmed_fraction_width(occurred_at: object) -> int:
    """How many fractional-second digits Postgres actually serialized."""

    fraction = re.search(r"\.(\d+)", str(occurred_at))
    assert fraction is not None, occurred_at
    return len(fraction.group(1))


def _projected_operation(conversation_id: str, sources: list[dict]) -> str:
    activity = project_conversation_activity(
        conversation_id=conversation_id,
        sources=[source_from_row(source) for source in sources],
        read_state=None,
    )
    return activity.operation.status


def _job_row(connection, job_id: str) -> tuple:
    with connection.cursor() as cursor:
        cursor.execute(
            "select status, operation_scope, conversation_id::text"
            " from public.backtest_jobs where id = %s",
            (job_id,),
        )
        return cursor.fetchone()


def _delete_identity(connection, user_id: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute("delete from auth.users where id = %s", (user_id,))


def _reclassification_statement() -> str:
    statements = "\n".join(
        line
        for line in MIGRATION.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("--")
    )
    match = re.search(r"update public\.backtest_jobs.*?;", statements, re.S)
    assert match is not None
    return match.group(0)


def test_seeded_proof_job_never_reads_as_conversation_activity() -> None:
    from workflows.proof import PROOF_OPERATION_SCOPE, run_workflow_proof

    gateway = _proof_gateway()
    with _connect() as connection:
        user_id = _seed_principal(gateway)
        try:
            # The legacy principal owned a conversation; a proof job written
            # under this contract cannot land in it or in any other.
            conversation_id = _seed_conversation(connection, user_id=user_id)
            row = gateway.create_proof_job(user_id=user_id, nonce="proof-nonce")
            assert row["operation_scope"] == PROOF_OPERATION_SCOPE
            assert row["conversation_id"] is None

            result = run_workflow_proof(
                gateway,
                job_id=str(row["id"]),
                nonce="proof-nonce",
                workflow_run_id="trn-test",
            )
            assert result["status"] == "succeeded"
            assert _job_row(connection, str(row["id"])) == (
                "succeeded",
                PROOF_OPERATION_SCOPE,
                None,
            )

            assert (
                _job_sources(connection, user_id=user_id, conversation_id=conversation_id)
                == []
            )
        finally:
            _delete_identity(connection, user_id)


def test_legacy_proof_row_projects_checking_until_reclassified() -> None:
    from workflows.proof import (
        PROOF_KIND,
        PROOF_OPERATION_SCOPE,
        PROOF_SEED_CREATED_BY,
    )

    gateway = _proof_gateway()
    with _connect() as connection:
        user_id = _seed_principal(gateway)
        try:
            conversation_id = _seed_conversation(connection, user_id=user_id)
            job_id = str(uuid4())
            # A succeeded row the reader cannot hydrate is projected from
            # updated_at, not finished_at, so that is the column that has to
            # carry the short fraction. Postgres trims trailing zeros, so
            # these microseconds serialize as five digits on every run.
            occurred_at = datetime.now(timezone.utc).replace(microsecond=123_450)
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.backtest_jobs
                      (id, user_id, conversation_id, operation_scope, payload_hash,
                       launch_payload, status, started_at, finished_at, updated_at,
                       execution_metadata)
                    values (%s, %s, %s, 'chat.run_backtest', 'sha256:legacy',
                            %s::jsonb, 'succeeded', %s, %s, %s, %s::jsonb)
                    """,
                    (
                        job_id,
                        user_id,
                        conversation_id,
                        json.dumps(
                            {
                                "kind": PROOF_KIND,
                                "nonce": "legacy",
                                "created_by": PROOF_SEED_CREATED_BY,
                            }
                        ),
                        occurred_at,
                        occurred_at,
                        occurred_at,
                        json.dumps({"workflow_proof": {"kind": PROOF_KIND}}),
                    ),
                )

            before = _job_sources(
                connection, user_id=user_id, conversation_id=conversation_id
            )
            assert [
                (source["status"], source["result_hydrateable"]) for source in before
            ] == [("succeeded", False)]
            assert _trimmed_fraction_width(before[0]["occurred_at"]) == 5
            assert _projected_operation(conversation_id, before) == "checking"

            with connection.cursor() as cursor:
                cursor.execute(_reclassification_statement())
                assert cursor.rowcount == 1
                # Idempotent on replay.
                cursor.execute(_reclassification_statement())
                assert cursor.rowcount == 0

            assert _job_row(connection, job_id) == (
                "succeeded",
                PROOF_OPERATION_SCOPE,
                None,
            )
            after = _job_sources(
                connection, user_id=user_id, conversation_id=conversation_id
            )
            assert after == []
            assert _projected_operation(conversation_id, after) == "idle"
        finally:
            _delete_identity(connection, user_id)


def test_chat_jobs_dispatched_to_the_proof_task_are_not_reclassified() -> None:
    """A proof-shadow deployment sends real chat jobs to the proof task with
    the proof launch kind; those rows have no seeder signature and keep their
    scope and conversation, because their settlement is owed to their run."""
    from workflows.proof import PROOF_KIND

    gateway = _proof_gateway()
    with _connect() as connection:
        user_id = _seed_principal(gateway)
        try:
            conversation_id = _seed_conversation(connection, user_id=user_id)
            job_id = str(uuid4())
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.backtest_jobs
                      (id, user_id, conversation_id, operation_scope, payload_hash,
                       launch_payload, status)
                    values (%s, %s, %s, 'chat.run_backtest', 'sha256:shadow',
                            %s::jsonb, 'succeeded')
                    """,
                    (
                        job_id,
                        user_id,
                        conversation_id,
                        json.dumps({"kind": PROOF_KIND, "source": "chat_runtime"}),
                    ),
                )
                cursor.execute(_reclassification_statement())
                assert cursor.rowcount == 0
            assert _job_row(connection, job_id) == (
                "succeeded",
                "chat.run_backtest",
                conversation_id,
            )
        finally:
            _delete_identity(connection, user_id)
