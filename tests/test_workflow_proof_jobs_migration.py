"""Guard for the workflow-proof scope migration.

Every ``operation_scope`` value has one owner, ``argus.domain.backtest_job_scopes``;
the migration's check constraint is rendered from it and must be exactly that
rendering. The seeder owns the proof's created_by signature and the
reclassification is keyed on it. The settle rule itself is untouched: this
migration must not restate or replace the owner function.
"""

from __future__ import annotations

from pathlib import Path

from argus.domain.backtest_admission import CHAT_RUN_SCOPE, DIRECT_RUN_SCOPE
from argus.domain.backtest_job_scopes import (
    OPERATION_SCOPES,
    PROOF_OPERATION_SCOPE,
    render_scope_check_constraint,
)
from argus.domain.job_settlement import RESEARCH_OPERATION_SCOPE, SQL_FUNCTION_NAME

from workflows import proof
from workflows.proof import PROOF_SEED_CREATED_BY

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT
    / "supabase/migrations_archive/20260905000000_workflow_proof_jobs_leave_conversations.sql"
)


def _normalized(text: str) -> str:
    return " ".join(text.lower().split())


def _statements(text: str) -> str:
    """The migration without its comment lines: what the database executes."""
    return _normalized(
        "\n".join(
            line for line in text.splitlines() if not line.lstrip().startswith("--")
        )
    )


def test_scope_check_is_exactly_the_rendering_of_the_scope_registry() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")

    assert render_scope_check_constraint() in migration
    assert migration.count("add constraint backtest_jobs_operation_scope_check") == 1


def test_every_scope_a_writer_stamps_derives_from_the_registry() -> None:
    # Each module keeps its historical name; the value comes from the one
    # tuple the constraint is rendered from, so the two cannot drift.
    assert OPERATION_SCOPES == (
        CHAT_RUN_SCOPE,
        DIRECT_RUN_SCOPE,
        RESEARCH_OPERATION_SCOPE,
        PROOF_OPERATION_SCOPE,
    )
    assert proof.PROOF_OPERATION_SCOPE is PROOF_OPERATION_SCOPE
    assert len(set(OPERATION_SCOPES)) == len(OPERATION_SCOPES)


def test_reclassification_is_keyed_on_the_seeder_signature() -> None:
    sql = _normalized(MIGRATION.read_text(encoding="utf-8"))

    assert (
        "update public.backtest_jobs set "
        f"operation_scope = '{PROOF_OPERATION_SCOPE}', "
        "conversation_id = null, updated_at = now() "
        f"where launch_payload ->> 'created_by' = '{PROOF_SEED_CREATED_BY}'"
    ) in sql
    # Idempotent: a replay finds nothing left to move.
    assert (
        f"and ( operation_scope <> '{PROOF_OPERATION_SCOPE}' "
        "or conversation_id is not null )"
    ) in sql
    # Only the seeder's rows move. Chat jobs a proof-shadow deployment sent to
    # the proof task keep their scope; their settlement is owed to their run.
    assert "launch_payload ->> 'kind'" not in sql


def test_settle_rule_owner_is_not_restated_here() -> None:
    sql = _statements(MIGRATION.read_text(encoding="utf-8"))

    assert SQL_FUNCTION_NAME not in sql
    assert "create or replace function" not in sql
    assert "evidence_artifacts" not in sql
