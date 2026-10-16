from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations/20261016154607_adopt_staging_rls_auto_enable.sql"
OBSERVED = (
    ROOT
    / "docs/reports/evidence/cuadrao-business/lane08-rls-forward/staging-artifact.json"
)
DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not DSN, reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured"
)


@pytest.fixture
def db():
    assert urlparse(DSN).hostname in {"localhost", "127.0.0.1", "::1"}
    with psycopg.connect(DSN) as conn, conn.transaction(force_rollback=True):
        yield conn


def artifact(db):
    function = db.execute(
        "select pg_get_functiondef(oid), pg_get_userbyid(proowner), proacl::text[], proconfig "
        "from pg_proc where oid=to_regprocedure('public.rls_auto_enable()')"
    ).fetchone()
    trigger = db.execute(
        "select evtevent, evtenabled, evttags, evtfoid::regprocedure::text, "
        "pg_get_userbyid(evtowner) from pg_event_trigger where evtname='ensure_rls'"
    ).fetchone()
    return function, trigger


def test_adopted_artifact_matches_staging(db):
    observed = json.loads(OBSERVED.read_text())
    function, trigger = artifact(db)
    assert function is not None
    assert function[0] == observed["function"]["definition"]
    assert function[1] == "postgres"
    assert set(function[2]) == set(observed["function"]["acl"])
    assert function[3] == ["search_path=pg_catalog"]
    assert trigger == (
        "ddl_command_end",
        "O",
        ["CREATE TABLE", "CREATE TABLE AS", "SELECT INTO"],
        "rls_auto_enable()",
        "postgres",
    )


def test_reapply_preserves_existing_artifact_and_identity(db):
    before = artifact(db)
    identity = db.execute(
        "select oid, evtfoid from pg_event_trigger where evtname='ensure_rls'"
    ).fetchone()
    assert identity is not None
    for _ in range(2):
        db.execute(MIGRATION.read_text())
        assert artifact(db) == before
        assert (
            db.execute(
                "select oid, evtfoid from pg_event_trigger where evtname='ensure_rls'"
            ).fetchone()
            == identity
        )


def test_unexpected_existing_trigger_stops_adoption(db):
    db.execute("alter event trigger ensure_rls disable")
    with (
        pytest.raises(
            psycopg.errors.RaiseException, match="differs from the observed staging"
        ),
        db.transaction(),
    ):
        db.execute(MIGRATION.read_text())
    assert db.execute(
        "select evtenabled from pg_event_trigger where evtname='ensure_rls'"
    ).fetchone() == ("D",)


@pytest.mark.parametrize(
    "statement",
    [
        'create table public."RLS probe" (id int)',
        'create table public."RLS probe" as select 1 as id',
        'select 1 as id into public."RLS probe"',
        'create table public."RLS probe" (id int) partition by range (id)',
    ],
)
def test_new_public_tables_enable_rls(db, statement):
    db.execute(statement)
    assert db.execute(
        "select relrowsecurity from pg_class where oid='public.\"RLS probe\"'::regclass"
    ).fetchone() == (True,)


def test_private_and_temporary_tables_are_unchanged(db):
    db.execute("create schema rls_probe_private")
    db.execute("create table rls_probe_private.probe (id int)")
    db.execute("create temporary table rls_probe_temp (id int)")
    for relation in ("rls_probe_private.probe", "pg_temp.rls_probe_temp"):
        assert db.execute(
            "select relrowsecurity from pg_class where oid=%s::regclass", (relation,)
        ).fetchone() == (False,)


def test_public_table_has_no_client_access_without_policy(db):
    db.execute("create table public.rls_probe_access (id int)")
    db.execute("insert into public.rls_probe_access values (1)")
    db.execute("grant select on public.rls_probe_access to anon, authenticated")
    for role in ("anon", "authenticated"):
        with db.transaction():
            db.execute(
                psycopg.sql.SQL("set local role {}").format(psycopg.sql.Identifier(role))
            )
            assert db.execute("select * from public.rls_probe_access").fetchall() == []
        db.execute("reset role")
