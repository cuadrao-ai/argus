"""Guard for the route receipt tier migration.

``OpenRouterModelTier`` owns every tier; the migration's check is rendered from
it and must be exactly that rendering. A tier added to the runtime fails this
pin until a new migration installs the new rendering and is pinned here.
"""

from __future__ import annotations

from pathlib import Path

from argus.observability.route_receipt_tiers import (
    TIER_CHECK_CONSTRAINT_NAME,
    render_tier_check_constraint,
)

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT / "supabase/migrations/20261003120001_admit_vision_route_receipt_tier.sql"
)


def test_tier_check_is_exactly_the_rendering_of_the_runtime_tiers() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")
    rendered = render_tier_check_constraint()

    assert rendered in migration
    assert migration.count(f"add constraint {TIER_CHECK_CONSTRAINT_NAME}") == 1
    assert "not valid;" in rendered
    assert "\ncommit;\n" in rendered
    assert f"validate constraint {TIER_CHECK_CONSTRAINT_NAME};" in rendered
    assert f"drop constraint if exists {TIER_CHECK_CONSTRAINT_NAME}" in rendered
