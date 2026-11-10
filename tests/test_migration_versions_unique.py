"""Every Supabase migration has its own version (#789, PR #794).

Two PRs that each take the same timestamp both pass on their own and collide
only after both merge. The production migration gate refuses such a tree at
deploy time (``_unique_by_version``); this runs the same parsing and the same
uniqueness rule on the checked-out tree in backend-checks, so the collision
fails CI on the PR that introduces it instead.

The archive the baseline replaced (#1890) counts too: staging and production
ledgers still hold those versions, so a new file may not reuse one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ops.production_migration_gate import (
    CandidateMigration,
    MigrationGateError,
    _unique_by_version,
)
from tests.test_decision_attachment_migration import ROOT

MIGRATIONS = ROOT / "supabase" / "migrations"
ARCHIVE = ROOT / "supabase" / "migrations_archive"


def _candidate(path: Path) -> CandidateMigration:
    # The gate only parses live paths; archived files are read as if they were live.
    return CandidateMigration.from_source(
        f"supabase/migrations/{path.name}", path.read_text(encoding="utf-8")
    )


def _candidates() -> list[CandidateMigration]:
    paths = sorted(
        [*MIGRATIONS.glob("*.sql"), *ARCHIVE.glob("*.sql")], key=lambda p: p.name
    )
    return [_candidate(path) for path in paths]


def test_migration_versions_are_unique_across_live_and_archived_files() -> None:
    candidates = _candidates()
    assert len(candidates) > len(list(MIGRATIONS.glob("*.sql")))
    _unique_by_version(candidates, source="candidate")


def test_a_duplicate_version_is_refused() -> None:
    first, second = _candidates()[:2]
    clash = CandidateMigration.from_source(
        f"supabase/migrations/{first.version}_another_change.sql", second.source
    )
    with pytest.raises(MigrationGateError, match="duplicate candidate migration"):
        _unique_by_version([first, clash], source="candidate")


def test_a_new_file_cannot_reuse_an_archived_version() -> None:
    archived = _candidate(sorted(ARCHIVE.glob("*.sql"))[-1])
    clash = CandidateMigration.from_source(
        f"supabase/migrations/{archived.version}_another_change.sql", "select 1;"
    )
    with pytest.raises(MigrationGateError, match="duplicate candidate migration"):
        _unique_by_version([*_candidates(), clash], source="candidate")
