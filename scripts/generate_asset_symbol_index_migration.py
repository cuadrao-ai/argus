from __future__ import annotations

from pathlib import Path

from argus.domain.search_sql_text import symbol_normalizer_expression
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT
    / "supabase"
    / "migrations_archive"
    / "20260730070000_add_asset_symbol_prefix_indexes.sql"
)
FUNCTION_NAME = "public.argus_search_symbol_casefold"


def render_migration() -> str:
    casefold = symbol_normalizer_expression(
        sql.Identifier("source_text")
    ).as_string()
    indexes = "\n\n".join(
        (
            "create index if not exists "
            f"idx_backtest_runs_owner_symbol_{slot}_prefix\n"
            "on public.backtest_runs (\n"
            "  user_id,\n"
            f'  (btrim({FUNCTION_NAME}(symbols[{slot}])) collate "C")\n'
            ")\n"
            f"where status = 'completed' and symbols[{slot}] is not null;"
        )
        for slot in range(1, 6)
    )
    rollback = "\n".join(
        (
            "-- drop index if exists "
            f"public.idx_backtest_runs_owner_symbol_{slot}_prefix;"
        )
        for slot in range(1, 6)
    )
    return (
        "-- Index raw-casefolded canonical symbol slots before Omnisearch "
        "rollup hydration.\n\n"
        f"create or replace function {FUNCTION_NAME}(source_text text)\n"
        "returns text\n"
        "language sql\n"
        "immutable\n"
        "strict\n"
        "parallel safe\n"
        "as $function$\n"
        f"  select {casefold};\n"
        "$function$;\n\n"
        f"{indexes}\n\n"
        "-- Rollback:\n"
        f"{rollback}\n"
        f"-- drop function if exists {FUNCTION_NAME}(text);\n"
    )


def main() -> None:
    MIGRATION.write_text(render_migration(), encoding="utf-8")


if __name__ == "__main__":
    main()
