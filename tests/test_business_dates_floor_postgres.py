"""The storage floor, applied only inside disposable local database schemas."""

import os
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]


def migration():
    paths = list((ROOT / "supabase/migrations").glob("*_business_dates_floor.sql"))
    assert len(paths) == 1
    return paths[0].read_text()


@contextmanager
def database():
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
            db.execute(f"CREATE TABLE {schema}.{name} (id int primary key, metadata text, {field} date)")
        db.execute(f"CREATE TABLE {schema}.business_invoice_revisions (id int primary key, metadata text, data jsonb)")
        db.execute(f"CREATE TABLE {schema}.financial_import_events (id int primary key, metadata text, anchor_on date, resolution jsonb default '{{\"business\":{{}}}}')")
        yield db, schema


def test_floor_migration_has_no_data_cleanup_or_validation_scan():
    sql = migration()
    assert "VALIDATE CONSTRAINT" not in sql
    assert "UPDATE public." not in sql
    assert "DELETE FROM" not in sql


@pytest.mark.parametrize("field", ["issued_on", "due_on"])
@pytest.mark.parametrize("value", [None, "", "2000-01-01"])
def test_invoice_incomplete_and_floor_dates_are_allowed(field, value):
    with database() as (db, schema):
        db.execute(migration().replace("public.", schema + "."))
        db.execute(f"INSERT INTO {schema}.business_invoice_revisions (id,data) VALUES (1,%s)", (Jsonb({field: value}),))


@pytest.mark.parametrize("origin", ["extracted", "qr_decoded", "matched"])
def test_reader_evidence_survives_but_person_asserting_it_must_correct_it(origin):
    document = {"business": {"facts": {"occurred_on": {"value": "0026-10-05", "origin": origin}}}}
    with database() as (db, schema):
        db.execute(migration().replace("public.", schema + "."))
        db.execute(f"INSERT INTO {schema}.financial_import_events (id,resolution) VALUES (1,%s)", (Jsonb(document),))
        document["business"]["facts"]["occurred_on"]["origin"] = "member_set"
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            db.execute(f"UPDATE {schema}.financial_import_events SET resolution=%s WHERE id=1", (Jsonb(document),))


def test_other_products_are_exempt_but_moving_into_business_checks_the_date():
    with database() as (db, schema):
        db.execute(migration().replace("public.", schema + "."))
        db.execute(f"INSERT INTO {schema}.financial_import_events (id,anchor_on,resolution) VALUES (1,'0026-10-05','{{}}')")
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            db.execute(f"UPDATE {schema}.financial_import_events SET resolution='{{\"business\":{{}}}}' WHERE id=1")


@pytest.mark.parametrize("table,column,path", [
    ("business_bank_lines", "occurred_on", None),
    ("business_bank_line_outcomes", "applied_settled_on", None),
    ("business_document_settlements", "settled_on", None),
    ("business_draft_revisions", "after_due_on", None),
    ("business_invoice_revisions", "data", "issued_on"),
    ("business_invoice_revisions", "data", "due_on"),
    ("financial_import_events", "anchor_on", None),
    ("financial_import_events", "resolution", "business.due_on"),
    ("financial_import_events", "resolution", "business.dgii.paid_on"),
    ("financial_import_events", "resolution", "business.dgii.withheld_on"),
    ("financial_import_events", "resolution", "business.facts.occurred_on.value"),
])
@pytest.mark.parametrize("upsert", [False, True])
def test_grandfathered_metadata_updates_keep_dates_but_date_changes_fail(table, column, path, upsert):
    def value(day):
        if path is None:
            return day
        result = {}
        target = result
        names = path.split(".")
        for name in names[:-1]:
            target[name] = {}
            target = target[name]
        target[names[-1]] = day
        if names[-1] == "value":
            target["origin"] = "member_set"
        return Jsonb(result)

    with database() as (db, schema):
        db.execute(f"INSERT INTO {schema}.{table} (id,{column}) VALUES (1,%s)", (value("0026-10-05"),))
        db.execute(migration().replace("public.", schema + "."))
        if upsert:
            query = f"INSERT INTO {schema}.{table} (id,metadata,{column}) VALUES (1,'deleted',%s) ON CONFLICT(id) DO UPDATE SET metadata=excluded.metadata,{column}=excluded.{column}"
            db.execute(query, (value("0026-10-05"),))
        else:
            query = f"UPDATE {schema}.{table} SET metadata='deleted',{column}=%s WHERE id=1"
            db.execute(query, (value("0026-10-05"),))
        assert db.execute(f"SELECT metadata FROM {schema}.{table} WHERE id=1").fetchone()[0] == "deleted"
        if path is not None:
            db.execute(f"UPDATE {schema}.{table} SET {column}=jsonb_set({column}, '{{note}}', '\"edited\"') WHERE id=1")
        db.execute(f"INSERT INTO {schema}.{table} (id,{column}) VALUES (3,%s)", (value(None),))
        # Restoring metadata is equally safe; a different bad date is not.
        db.execute(f"UPDATE {schema}.{table} SET metadata='restored' WHERE id=1")
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            db.execute(query, (value("1999-12-31"),))
        db.execute(query, (value("2000-01-01"),))
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            db.execute(f"INSERT INTO {schema}.{table} (id,{column}) VALUES (2,%s)", (value("0026-10-05"),))
