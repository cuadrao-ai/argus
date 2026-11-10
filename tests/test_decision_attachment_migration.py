"""Guard for the decision attachment migration.

The DecisionNote validator and the table constraints state one rule: a row
attaches to exactly one of an evidence artifact or a stored computation, and
the idea lineage travels with the artifact. This pins the migration text to
that rule and to its promotion classification, so a rewrite cannot quietly
widen it into a data rewrite.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / (
    "supabase/migrations_archive/20260908120000_decision_notes_attach_to_computations.sql"
)


def _normalized(text: str) -> str:
    return " ".join(text.lower().split())


def _statements(text: str) -> list[str]:
    body = "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("--")
    )
    return [_normalized(part) for part in body.split(";") if part.strip()]


def test_migration_relaxes_lineage_and_adds_the_computation_attachment() -> None:
    statements = _statements(MIGRATION.read_text(encoding="utf-8"))

    for column in ("idea_id", "idea_version_id", "evidence_artifact_id"):
        assert (
            f"alter table public.decision_notes alter column {column} drop not null"
            in statements
        )
    assert any(
        "add column if not exists source_message_id uuid references "
        "public.messages(id) on delete set null"
        in statement
        and "add column if not exists computation jsonb" in statement
        for statement in statements
    )
    assert any(
        "add constraint decision_notes_attachment_check check "
        "((evidence_artifact_id is not null) <> (computation is not null))" in statement
        for statement in statements
    )
    assert any(
        "add constraint decision_notes_evidence_lineage_check" in statement
        and "((evidence_artifact_id is null) = (idea_id is null))" in statement
        and "((evidence_artifact_id is null) = (idea_version_id is null))" in statement
        for statement in statements
    )
    assert any(
        "add constraint decision_notes_user_message_unique unique "
        "(user_id, source_message_id)" in statement
        for statement in statements
    )


def test_migration_rewrites_no_rows_and_removes_no_objects() -> None:
    statements = _statements(MIGRATION.read_text(encoding="utf-8"))

    assert all(
        statement.startswith("alter table public.decision_notes")
        for statement in statements
    )
    # A row rewrite would start a statement; an FK's "on delete" clause does not.
    for verb in ("update", "delete", "truncate", "insert"):
        assert not any(statement.startswith(verb) for statement in statements), verb
    for removal in ("drop constraint", "drop column", "drop table", "drop index"):
        assert not any(removal in statement for statement in statements), removal


def test_migration_gate_classification_is_owed_to_drop_not_null_alone() -> None:
    sys.path.insert(0, str(ROOT / "scripts" / "ops"))
    from production_migration_gate import classify_migration

    source = MIGRATION.read_text(encoding="utf-8")
    classification, requirement = classify_migration(source)
    assert classification == "destructive"
    assert requirement == "maintenance_backup_and_founder_approval_required"

    # Every other statement is additive; only the NOT NULL relaxations carry the
    # word the classifier reads as destructive.
    without_relaxations = "\n".join(
        statement + ";"
        for statement in source.split(";")
        if "drop not null" not in statement.lower()
    )
    assert classify_migration(without_relaxations) == (
        "additive",
        "human_review_and_live_readback",
    )
