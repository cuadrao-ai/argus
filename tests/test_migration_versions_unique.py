"""Every Supabase migration has its own version (#789, PR #794).

Two PRs that each take the same timestamp both pass on their own and collide
only after both merge. The production migration gate refuses such a tree at
deploy time (``_unique_by_version``); this runs the same parsing and the same
uniqueness rule on the checked-out tree in backend-checks, so the collision
fails CI on the PR that introduces it instead.
"""

from __future__ import annotations

import pytest

from scripts.ops.production_migration_gate import (
    CandidateMigration,
    MigrationGateError,
    _unique_by_version,
)
from tests.test_decision_attachment_migration import ROOT

MIGRATIONS = ROOT / "supabase" / "migrations"


def _candidates() -> list[CandidateMigration]:
    return [
        CandidateMigration.from_source(
            path.relative_to(ROOT).as_posix(), path.read_text(encoding="utf-8")
        )
        for path in sorted(MIGRATIONS.glob("*.sql"))
    ]


def test_migration_versions_are_unique() -> None:
    candidates = _candidates()
    assert candidates
    _unique_by_version(candidates, source="candidate")


def test_a_duplicate_version_is_refused() -> None:
    first, second = _candidates()[:2]
    clash = CandidateMigration.from_source(
        f"supabase/migrations/{first.version}_another_change.sql", second.source
    )
    with pytest.raises(MigrationGateError, match="duplicate candidate migration"):
        _unique_by_version([first, clash], source="candidate")
