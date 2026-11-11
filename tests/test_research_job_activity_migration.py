"""Guard for the research-job activity migration.

The settle rule has one owner, ``argus.domain.job_settlement``. The SQL
function in this migration is rendered from it, so the checked-in text must be
exactly that rendering, and every activity reader must derive from the
function rather than restating the rule. The callers are pinned at the body
level: each replaced function must be the original migration's body with the
inline predicate swapped for the owner call (and, for the batch read, the
predicate hoisted into one CTE), so a body-level revert cannot hide behind an
unchanged signature.
"""

from __future__ import annotations

import re
from pathlib import Path

from argus.domain.job_settlement import (
    SQL_FUNCTION_NAME,
    SQL_FUNCTION_SIGNATURE,
    render_sql_function,
)

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations_archive/20260822000000_research_job_activity_settles.sql"
ORIGINAL = (
    ROOT / "supabase/migrations_archive/20260801000000_add_conversation_activity_read_states.sql"
)
OWNER_CALL = f"{SQL_FUNCTION_NAME}(j)"
INLINE_PREDICATE = re.compile(
    r"exists \(\s*select 1\s*from public\.backtest_runs as r\s*"
    r"join public\.evidence_artifacts as e.*?"
    r"->> 'idea_version_id' = e\.idea_version_id::text\s*\)",
    re.S,
)


def _normalized(text: str) -> str:
    return " ".join(text.lower().split())


def _function(sql: str, name: str, *, replaced: bool) -> str:
    head = f"create {'or replace ' if replaced else ''}function {name}("
    return sql.split(head, 1)[1].split("$$;", 1)[0]


def _head_and_body(function_text: str) -> tuple[str, str]:
    head, body = re.split(r"\nas \$\$", function_text, maxsplit=1)
    return head, body


def test_sql_owner_is_exactly_the_rendering_of_the_rule() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")
    rendered = render_sql_function()

    assert rendered in migration
    assert _normalized(rendered) in _normalized(migration)
    owner = _normalized(rendered)
    assert "never message prose" not in owner
    assert "content" not in owner.split("as $$", 1)[1]
    assert len(re.findall(r"\nas \$\$", rendered)) == 1


def test_sql_owner_is_private_parallel_safe_and_service_role_only() -> None:
    sql = _normalized(MIGRATION.read_text(encoding="utf-8"))

    assert SQL_FUNCTION_NAME.startswith("argus_private.")
    assert "revoke all on schema argus_private from public, anon, authenticated" in sql
    assert (
        f"revoke all on function {SQL_FUNCTION_SIGNATURE.lower()} "
        "from public, anon, authenticated"
    ) in sql
    assert (
        f"grant execute on function {SQL_FUNCTION_SIGNATURE.lower()} to service_role"
        in sql
    )
    assert "parallel safe" in _normalized(render_sql_function())


def test_every_activity_reader_derives_from_the_owner() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    for name in (
        "read_conversation_activity_sources",
        "mutate_conversation_activity_read_state",
        "baseline_conversation_activity_read_states",
    ):
        function = _function(sql, f"public.{name}", replaced=True)
        assert INLINE_PREDICATE.search(function) is None
        assert "evidence_artifacts" not in function
        assert "content" not in function
    # Only the owner states the run/evidence chain.
    assert sql.count("join public.evidence_artifacts as e") == 1


def test_mutation_and_baseline_bodies_are_the_originals_with_the_owner_substituted() -> (
    None
):
    sql = MIGRATION.read_text(encoding="utf-8")
    original = ORIGINAL.read_text(encoding="utf-8")

    for name in (
        "mutate_conversation_activity_read_state",
        "baseline_conversation_activity_read_states",
    ):
        replaced = _function(sql, f"public.{name}", replaced=True)
        base = _function(original, f"public.{name}", replaced=False)
        assert INLINE_PREDICATE.search(base) is not None
        expected = INLINE_PREDICATE.sub(OWNER_CALL, base)
        assert _normalized(replaced) == _normalized(expected), name
        assert replaced.count(OWNER_CALL) == 1


def test_batch_read_evaluates_the_owner_once_per_job_row() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    original = ORIGINAL.read_text(encoding="utf-8")
    replaced = _function(sql, "public.read_conversation_activity_sources", replaced=True)
    base = _function(
        original, "public.read_conversation_activity_sources", replaced=False
    )

    # Same signature and result shape as the original, and a body that was
    # actually compared (the split must find the body on both sides).
    replaced_head, replaced_body = _head_and_body(replaced)
    base_head, base_body = _head_and_body(base)
    assert replaced_head == base_head
    assert replaced_body != base_body
    # One evaluation, in one CTE, read by both job branches.
    assert replaced.count(OWNER_CALL) == 1
    assert replaced.count("with jobs as (") == 1
    assert replaced.count("from jobs as ranked") == 2
    assert "from public.backtest_jobs as j" in replaced.split("with jobs as (", 1)[1]
    # The branch filters the original stated inside each subquery now sit on
    # the shared rows, disjunctions intact.
    normalized = _normalized(replaced)
    assert (
        "where ranked.status in ('queued', 'running', 'succeeded') "
        "and ( ranked.status <> 'succeeded' or not ranked.result_hydrateable )"
    ) in normalized
    assert (
        "where ranked.status in ('succeeded', 'failed', 'canceled', 'expired') "
        "and ( ranked.status <> 'succeeded' or ranked.result_hydrateable )"
    ) in normalized
    # Everything outside the job branches is untouched: the chat_turn
    # branches, the read-state join, and the ordering.
    for fragment in (
        "from public.chat_turn_lifecycles as l",
        "left join public.conversation_read_states as rs",
        "order by source.occurred_at, source.source_kind_rank, source.source_id",
        "order by c.id;",
    ):
        assert fragment in replaced and fragment in base
    assert replaced_body.count("union all") == base_body.count("union all") == 3
