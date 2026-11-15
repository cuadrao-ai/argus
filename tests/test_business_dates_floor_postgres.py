"""The floor migration, applied only inside a disposable local database."""

import os
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[1]


def migration():
    paths = list((ROOT / "supabase/migrations").glob("*_business_dates_floor.sql"))
    assert len(paths) == 1
    return paths[0].read_text()


def test_floor_migration_is_forward_only_and_unvalidated():
    sql = migration()
    assert "NOT VALID" in sql
    assert "VALIDATE CONSTRAINT" not in sql
    assert "UPDATE " not in sql
    assert "DELETE " not in sql


@pytest.mark.parametrize("table,column", [
    ("business_bank_lines", "occurred_on"),
    ("business_bank_line_outcomes", "applied_settled_on"),
    ("business_document_settlements", "settled_on"),
    ("business_draft_revisions", "after_due_on"),
])
def test_existing_old_date_survives_but_new_old_date_is_refused(table, column):
    dsn = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "")
    if not dsn:
        pytest.skip("ARGUS_DISPOSABLE_DATABASE_URL is not configured")
    assert urlparse(dsn).hostname in {"127.0.0.1", "localhost", "::1"}
    schema = "dates_" + uuid4().hex
    with psycopg.connect(dsn) as db, db.transaction(force_rollback=True):
        db.execute(f"CREATE SCHEMA {schema}")
        for name, field in [
            ("business_bank_lines", "occurred_on"),
            ("business_bank_line_outcomes", "applied_settled_on"),
            ("business_document_settlements", "settled_on"),
            ("business_draft_revisions", "after_due_on"),
        ]:
            db.execute(f"CREATE TABLE {schema}.{name} ({field} date)")
        db.execute(f"CREATE TABLE {schema}.business_invoice_revisions (data jsonb)")
        db.execute(f"CREATE TABLE {schema}.financial_import_events (anchor_on date, resolution jsonb)")
        db.execute(f"INSERT INTO {schema}.{table} VALUES ('0026-10-05')")
        db.execute(migration().replace("public.", schema + "."))
        assert db.execute(f"SELECT count(*) FROM {schema}.{table}").fetchone()[0] == 1
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            db.execute(f"INSERT INTO {schema}.{table} VALUES ('1999-12-31')")
        db.execute(f"INSERT INTO {schema}.{table} VALUES ('2000-01-01'), (NULL)")
        assert db.execute("SELECT bool_and(NOT convalidated) FROM pg_constraint WHERE connamespace=%s::regnamespace", (schema,)).fetchone()[0]


@pytest.mark.parametrize("path", ["due_on", "dgii.paid_on", "dgii.withheld_on", "facts.occurred_on.value"])
def test_business_json_dates_use_the_floor_without_scanning_reader_evidence(path):
    from psycopg.types.json import Jsonb

    dsn = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "")
    if not dsn:
        pytest.skip("ARGUS_DISPOSABLE_DATABASE_URL is not configured")
    assert urlparse(dsn).hostname in {"127.0.0.1", "localhost", "::1"}
    schema = "dates_" + uuid4().hex
    document = {"business": {}}
    target = document["business"]
    names = path.split(".")
    for name in names[:-1]:
        target[name] = {}
        target = target[name]
    target[names[-1]] = "0026-10-05"
    if path.startswith("facts."):
        target["origin"] = "member_set"
    statement = migration().split("ALTER TABLE public.financial_import_events", 1)[1]
    with psycopg.connect(dsn) as db, db.transaction(force_rollback=True):
        db.execute(f"CREATE SCHEMA {schema}")
        db.execute(f"CREATE TABLE {schema}.business_invoice_revisions (data jsonb)")
        db.execute(f"CREATE TABLE {schema}.financial_import_events (anchor_on date, resolution jsonb)")
        db.execute(f"INSERT INTO {schema}.financial_import_events VALUES (NULL,%s)", (Jsonb(document),))
        db.execute(f"ALTER TABLE {schema}.financial_import_events" + statement)
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            db.execute(f"INSERT INTO {schema}.financial_import_events VALUES (NULL,%s)", (Jsonb(document),))
        target[names[-1]] = "2000-01-01"
        db.execute(f"INSERT INTO {schema}.financial_import_events VALUES (NULL,%s)", (Jsonb(document),))
        if path.startswith("facts."):
            target.update(value="0026-10-05", origin="extracted")
            db.execute(f"INSERT INTO {schema}.financial_import_events VALUES (NULL,%s)", (Jsonb(document),))


@pytest.mark.parametrize("field", ["issued_on", "due_on"])
def test_invoice_dates_reject_old_new_values_but_keep_existing_drafts(field):
    from psycopg.types.json import Jsonb

    dsn = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "")
    if not dsn:
        pytest.skip("ARGUS_DISPOSABLE_DATABASE_URL is not configured")
    assert urlparse(dsn).hostname in {"127.0.0.1", "localhost", "::1"}
    schema = "dates_" + uuid4().hex
    statement = next((part for part in migration().split(";") if "ALTER TABLE public.business_invoice_revisions" in part), "")
    with psycopg.connect(dsn) as db, db.transaction(force_rollback=True):
        db.execute(f"CREATE SCHEMA {schema}")
        db.execute(f"CREATE TABLE {schema}.business_invoice_revisions (data jsonb)")
        db.execute(f"INSERT INTO {schema}.business_invoice_revisions VALUES (%s)", (Jsonb({field: "0026-10-05"}),))
        if statement:
            db.execute(statement.replace("public.", schema + "."))
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            db.execute(f"INSERT INTO {schema}.business_invoice_revisions VALUES (%s)", (Jsonb({field: "1999-12-31"}),))
        for value in ("2000-01-01", "", None):
            db.execute(f"INSERT INTO {schema}.business_invoice_revisions VALUES (%s)", (Jsonb({field: value}),))
