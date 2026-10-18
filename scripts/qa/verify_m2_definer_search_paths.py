"""Compare M2 to the repo-built catalog snapshot, then test a disposable database."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/reports/evidence/cleanup-m2-definer-paths"
MIGRATION = ROOT / "supabase/migrations/20261018040000_harden_definer_search_paths.sql"
QUERY = """
select n.nspname as schema, p.proname as name,
  pg_get_function_identity_arguments(p.oid) as identity_arguments,
  pg_get_functiondef(p.oid) as definition, p.prosrc as source,
  p.proacl::text as acl, pg_get_userbyid(p.proowner) as owner,
  p.proconfig as config, p.prosecdef as security_definer,
  p.prorettype::regtype::text as result_type, p.provolatile as volatility,
  p.proisstrict as strict, p.proparallel as parallel, p.proleakproof as leakproof,
  pg_get_function_arguments(p.oid) as arguments
from pg_proc p join pg_namespace n on n.oid=p.pronamespace
where p.prosecdef and n.nspname in ('public','argus_private')
"""


def key(row: dict) -> tuple:
    return row["schema"], row["name"], row["identity_arguments"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()
    parsed = urlparse(args.database_url)
    if parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.path != "/m2_testdb":
        parser.error("Use only the M2-owned local disposable m2_testdb")
    baseline = json.loads((EVIDENCE / "repo-before.json").read_text())
    with psycopg.connect(args.database_url, row_factory=dict_row) as connection:
        before = {key(row): row for row in connection.execute(QUERY).fetchall()}
        for row in baseline:
            local = before[key(row)]
            for field in ("definition", "acl", "owner", "config"):
                assert local[field] == row[field], (key(row), field)
        connection.execute(
            (ROOT / "supabase/tests/m2-definer-search-paths.sql").read_text()
        )
        connection.execute(MIGRATION.read_text())
        after = {key(row): row for row in connection.execute(QUERY).fetchall()}
        assert before.keys() == after.keys(), "Functions were added or removed"
        targets = {key(row) for row in baseline}
        for identity, old in before.items():
            new = after[identity]
            if identity not in targets:
                assert old == new, identity
                continue
            assert new["definition"] == re.sub(
                r" SET search_path TO [^\n]+", " SET search_path TO ''", old["definition"]
            ), identity
            assert new["config"] == ['search_path=""'] + [
                item for item in old["config"] if not item.startswith("search_path=")
            ], identity
            for field in old.keys() - {"config", "definition"}:
                assert old[field] == new[field], (identity, field)
        connection.commit()
        connection.execute(
            (ROOT / "supabase/tests/m2-definer-search-paths.sql").read_text()
        )
        print(
            json.dumps(
                {
                    "target_functions": len(targets),
                    "source_acl_signature_equal": True,
                    "unrelated_definers_equal": True,
                    "before_after_behavior": "PASS",
                    "staging_writes": 0,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
