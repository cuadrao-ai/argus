"""The ``route_receipts.tier`` check, rendered from the runtime's tier owner.

``OpenRouterModelTier`` is the one owner of every tier a route receipt carries.
The migration that installs the active check is pinned to this rendering, and
the real-Postgres suite compares the applied check with the same owner, so a
tier added to the runtime without a migration fails CI.
"""

from __future__ import annotations

from typing import get_args

from argus.llm.openrouter_tasks import OpenRouterModelTier

TIER_CHECK_CONSTRAINT_NAME = "route_receipts_tier_check"


def render_tier_check_constraint() -> str:
    """Replace the tier check without scanning under an exclusive lock.

    ``ADD ... NOT VALID`` takes a brief ACCESS EXCLUSIVE lock and does not scan.
    ``COMMIT`` releases that lock. ``VALIDATE CONSTRAINT`` then scans under
    SHARE UPDATE EXCLUSIVE, which allows reads and writes. ``DROP ... IF EXISTS``
    lets a re-run replace the check instead of failing.
    """
    tiers = ", ".join(f"'{tier}'" for tier in get_args(OpenRouterModelTier))
    return f"""alter table public.route_receipts
  drop constraint if exists {TIER_CHECK_CONSTRAINT_NAME},
  add constraint {TIER_CHECK_CONSTRAINT_NAME}
    check (tier in ({tiers})) not valid;
commit;
alter table public.route_receipts
  validate constraint {TIER_CHECK_CONSTRAINT_NAME};"""
