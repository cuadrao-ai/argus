"""Pin the bounded schema relaxation and its founder-owned promotion gate."""

from __future__ import annotations

from scripts.ops.production_migration_gate import classify_migration
from tests.test_decision_attachment_migration import ROOT, _statements

MIGRATION = (
    ROOT / "supabase/migrations_archive/20260909225701_retire_research_rail_ledger_status.sql"
)


def test_research_status_migration_only_relaxes_the_research_rail() -> None:
    statements = _statements(MIGRATION.read_text())
    assert statements == [
        "alter table public.cost_ledger_entries alter column status drop not null",
        "alter table public.cost_ledger_entries add constraint "
        "cost_ledger_entries_status_required check (status is not null or "
        "(source = 'research' and feature_area = 'research_rail'))",
    ]
    assert MIGRATION.name > "20260909183646_share_answer_receipt_selections.sql"


def test_research_status_migration_rewrites_no_rows_or_removes_objects() -> None:
    statements = _statements(MIGRATION.read_text())
    assert statements
    assert all(s.startswith("alter table public.cost_ledger_entries") for s in statements)
    for removal in ("drop column", "drop table", "drop constraint", "drop index"):
        assert not any(removal in s for s in statements)
    assert not any("grant " in s or "revoke " in s for s in statements)


def test_research_migration_is_destructive_only_because_of_drop_not_null() -> None:
    source = MIGRATION.read_text()
    assert classify_migration(source) == (
        "destructive",
        "maintenance_backup_and_founder_approval_required",
    )
    without_relaxation = "\n".join(
        s + ";" for s in _statements(source) if "drop not null" not in s
    )
    assert classify_migration(without_relaxation) == (
        "additive",
        "human_review_and_live_readback",
    )
