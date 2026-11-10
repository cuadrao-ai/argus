"""Every retention purge declared in a migration must actually be run.

Most expiring tables are deleted by an owner's FK cascade. The exceptions are
the visitor-keyed tables, which are deliberately not FK-bound because the
subject is a visitor with no account, so nothing deletes their rows unless
something explicitly calls their purge. A purge that only tests and docs
reference is not a retention boundary: `expires_at` becomes metadata and the
IP-derived digests stay forever.

These assert the invariant (the purge is declared, registered, AND invoked)
rather than the mechanism, so the next unowned expiring table inherits the
guard without anyone remembering to write this file again.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from argus.domain.guest_cleanup import (
    EXPIRING_DATA_PURGES,
    cleanup_expired_guest_workspaces,
)

REPO_ROOT = Path(__file__).parents[1]
MIGRATIONS = REPO_ROOT / "supabase"

_PURGE_DEFINITION = re.compile(
    r"create\s+or\s+replace\s+function\s+public\.(purge_[a-z0-9_]+)\s*\(",
    re.IGNORECASE,
)


def _declared_purges() -> set[str]:
    names: set[str] = set()
    for migration in MIGRATIONS.glob("migrations*/*.sql"):
        names.update(_PURGE_DEFINITION.findall(migration.read_text(encoding="utf-8")))
    return names


class _RecordingGateway:
    """Records which purges the job actually reaches."""

    def __init__(self) -> None:
        self.purged: list[str] = []

    def claim_expired_guest_workspaces(
        self,
        *,
        limit: int,
        dry_run: bool,
    ) -> list[dict[str, object]]:
        return []

    def __getattr__(self, name: str):
        if not name.startswith("purge_"):
            raise AttributeError(name)

        def _purge(*, before=None) -> int:
            self.purged.append(name)
            return 0

        return _purge


def test_at_least_one_retention_purge_is_declared() -> None:
    """Guards the guard: a regex that silently matches nothing proves nothing."""
    assert _declared_purges()


@pytest.mark.parametrize("purge_name", sorted(_declared_purges()))
def test_every_declared_purge_is_registered_for_cleanup(purge_name: str) -> None:
    registered = {method_name for _, method_name in EXPIRING_DATA_PURGES}

    assert purge_name in registered, (
        f"{purge_name} is declared in a migration but is not in "
        "argus.domain.guest_cleanup.EXPIRING_DATA_PURGES, so nothing ever runs "
        "it. Register it there, or drop the retention claim from the migration "
        "and docs/DATA_MODEL.md."
    )


def test_the_cleanup_job_invokes_every_registered_purge() -> None:
    """Registration only counts if the job reaches it."""
    gateway = _RecordingGateway()

    result = cleanup_expired_guest_workspaces(gateway, limit=1, dry_run=False)

    assert gateway.purged == [method_name for _, method_name in EXPIRING_DATA_PURGES]
    assert result.purge_failed == 0


def test_a_dry_run_purges_nothing() -> None:
    gateway = _RecordingGateway()

    result = cleanup_expired_guest_workspaces(gateway, limit=1, dry_run=True)

    assert gateway.purged == []
    assert result.visitor_usage_purged == 0
    assert result.funnel_milestones_purged == 0


def test_a_failing_purge_is_counted_rather_than_swallowed() -> None:
    """A silent zero is how a retention boundary becomes documentation."""

    class _FailingGateway(_RecordingGateway):
        def __getattr__(self, name: str):
            if not name.startswith("purge_"):
                raise AttributeError(name)

            def _purge(*, before=None) -> int:
                raise RuntimeError("purge unavailable")

            return _purge

    result = cleanup_expired_guest_workspaces(_FailingGateway(), limit=1, dry_run=False)

    assert result.purge_failed == len(EXPIRING_DATA_PURGES)
    assert result.visitor_usage_purged == 0
