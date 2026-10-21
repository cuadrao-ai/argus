"""Exercise the read-only census on an empty, explicitly named local database."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.pq import TransactionStatus

ROOT = Path(__file__).resolve().parents[1]
CENSUS_SQL = (ROOT / "scripts/ops/research_spine_census.sql").read_text()
DSN = os.getenv("ARGUS_RESEARCH_CENSUS_TEST_DSN", "")


@unittest.skipUnless(DSN, "ARGUS_RESEARCH_CENSUS_TEST_DSN is not configured")
class ResearchSpineCensusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        options = conninfo_to_dict(DSN)
        if options.get("host") not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Census tests require an isolated local database")
        if not options.get("dbname", "").startswith("cleanup_m11_"):
            raise ValueError("Census test database must start with cleanup_m11_")
        cls.connection = psycopg.connect(DSN, autocommit=True)
        occupied = cls.connection.execute(
            "SELECT count(*) FROM pg_class WHERE relnamespace = 'public'::regnamespace"
            " AND relkind IN ('r', 'p', 'v', 'm')"
        ).fetchone()[0]
        if occupied:
            cls.connection.close()
            raise ValueError("Census tests require an empty public schema")
        cls.connection.execute(
            """
            CREATE TABLE public.ideas (id integer PRIMARY KEY);
            CREATE TABLE public.backtest_runs (id integer PRIMARY KEY);
            CREATE TABLE public.public_excerpt_snapshots (id integer PRIMARY KEY);
            CREATE TABLE public.cost_ledger_entries (id integer PRIMARY KEY);
            CREATE TABLE public.kept_memory (
                id integer REFERENCES public.ideas(id)
            );
            CREATE TABLE public.kept_chat (id integer PRIMARY KEY);
            CREATE VIEW public.kept_chat_view AS SELECT id FROM public.backtest_runs;
            CREATE INDEX backtest_runs_census_idx ON public.backtest_runs(id);
            CREATE FUNCTION public.revoke_census_excerpt() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                DELETE FROM public.public_excerpt_snapshots WHERE id = OLD.id;
                RETURN OLD;
            END;
            $$;
            CREATE TRIGGER revoke_census_excerpt BEFORE DELETE ON public.kept_chat
                FOR EACH ROW EXECUTE FUNCTION public.revoke_census_excerpt();
            CREATE FUNCTION public.census_row_input(public.cost_ledger_entries)
            RETURNS boolean LANGUAGE sql AS $$ SELECT $1 IS NOT NULL $$;
            """
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.execute(
            """
            DROP VIEW public.kept_chat_view;
            DROP TABLE public.kept_chat;
            DROP FUNCTION public.revoke_census_excerpt();
            DROP FUNCTION public.census_row_input(public.cost_ledger_entries);
            DROP TABLE public.kept_memory;
            DROP TABLE public.ideas;
            DROP TABLE public.backtest_runs;
            DROP TABLE public.public_excerpt_snapshots;
            DROP TABLE public.cost_ledger_entries;
            """
        )
        cls.connection.close()

    def tearDown(self) -> None:
        self.connection.execute("ROLLBACK")

    def census(self) -> dict:
        cursor = self.connection.execute(CENSUS_SQL)
        while cursor.description is None:
            self.assertTrue(cursor.nextset(), "Census returned no result")
        result = cursor.fetchone()[0]
        while cursor.nextset():
            pass
        self.assertEqual(self.connection.info.transaction_status, TransactionStatus.IDLE)
        return result

    def test_empty_tables_still_have_kept_dependencies(self) -> None:
        result = self.census()
        self.assertEqual(result["read_only"], "on")
        self.assertEqual(
            self.connection.execute("SELECT count(*) FROM public.ideas").fetchone()[0],
            0,
        )
        self.assertTrue(
            any(
                fk["source"] == "kept_memory" and fk["target"] == "ideas"
                for fk in result["foreign_keys"]
            )
        )
        self.assertIn(
            {"view": "kept_chat_view", "target": "backtest_runs"}, result["views"]
        )
        self.assertTrue(
            any(trigger["table"] == "kept_chat" for trigger in result["triggers"])
        )

    def test_missing_tables_are_reported_and_indexes_are_excluded(self) -> None:
        result = self.census()
        self.assertIn("collection_strategies", result["missing_targets"])
        self.assertEqual(
            {table["table"] for table in result["tables"]},
            {"ideas", "backtest_runs", "public_excerpt_snapshots", "cost_ledger_entries"},
        )

    def test_row_type_argument_is_a_dependency_without_body_reference(self) -> None:
        result = self.census()
        function = next(
            row
            for row in result["functions"]
            if row["function"].startswith("census_row_input(")
        )
        self.assertEqual(function["matched_targets"], ["cost_ledger_entries"])

    def test_read_only_transaction_rejects_an_accidental_write(self) -> None:
        query = CENSUS_SQL.replace(
            "ROLLBACK;", "INSERT INTO public.ideas VALUES (1);\nROLLBACK;"
        )
        with self.assertRaises(psycopg.errors.ReadOnlySqlTransaction):
            cursor = self.connection.execute(query)
            while cursor.nextset():
                pass
        self.connection.execute("ROLLBACK")
        self.assertEqual(
            self.connection.execute("SELECT count(*) FROM public.ideas").fetchone()[0],
            0,
        )


if __name__ == "__main__":
    unittest.main()
