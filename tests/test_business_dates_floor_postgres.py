"""The storage floor, applied only inside disposable local database schemas."""

import os
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import psycopg
import pytest
from argus.domain.business import ledger
from argus.domain.business.annotations import EditCurrentNote, edit_note
from argus.domain.business.contracts.actions import ReviewDraft
from argus.domain.business.contracts.dgii import PurchaseReview
from argus.domain.business.contracts.facts import BusinessFactPatch
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from tests import test_business_actions_postgres as shared

users = shared.users
actions = shared.actions
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
        for role in ("anon", "authenticated", "service_role"):
            if not db.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                db.execute(f"CREATE ROLE {role}")
        db.execute(f"CREATE SCHEMA {schema}")
        for name, field in [
            ("business_bank_lines", "occurred_on"),
            ("business_bank_line_outcomes", "applied_settled_on"),
            ("business_document_settlements", "settled_on"),
        ]:
            db.execute(f"CREATE TABLE {schema}.{name} (id int primary key, metadata text, {field} date)")
        db.execute(f"CREATE TABLE {schema}.business_draft_revisions (id int primary key, metadata text, draft_id int, version int, after_due_on date)")
        db.execute(f"CREATE TABLE {schema}.business_invoice_revisions (id int primary key, metadata text, invoice_id int, version int, data jsonb)")
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


@pytest.mark.parametrize("table,parent,column,field", [
    ("business_draft_revisions", "draft_id", "after_due_on", None),
    ("business_invoice_revisions", "invoice_id", "data", "issued_on"),
    ("business_invoice_revisions", "invoice_id", "data", "due_on"),
])
def test_appended_revision_keeps_its_parents_old_date_but_cannot_assert_one(table, parent, column, field):
    def value(day):
        return day if field is None else Jsonb({field: day, "note": uuid4().hex})

    insert = f"INSERT INTO SCHEMA.{table} (id,{parent},version,{column}) VALUES (%s,%s,%s,%s)"
    with database() as (db, schema):
        insert = insert.replace("SCHEMA", schema)
        db.execute(insert, (1, 7, 1, value("1999-12-31")))
        db.execute(insert, (2, 7, 2, value("2000-01-01")))
        db.execute(insert, (3, 8, 1, value("1999-12-31")))
        db.execute(migration().replace("public.", schema + "."))
        # The base is the parent's latest earlier revision, never an older one.
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            db.execute(insert, (4, 7, 3, value("1999-12-31")))
        db.execute(insert, (5, 8, 2, value("1999-12-31")))
        db.execute(insert, (6, 8, 3, value("1999-12-31")))
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            db.execute(insert, (7, 8, 4, value("1999-01-01")))
        # Another parent's old date, and a first revision, are fresh input.
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            db.execute(insert, (8, 9, 1, value("1999-12-31")))
        db.execute(insert, (9, 8, 4, value(None)))
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            db.execute(insert, (10, 8, 5, value("1999-12-31")))


def legacy_due_on(service, draft_id, day):
    """Store a due date as a row written before the floor existed holds it."""
    floors = [
        ("financial_import_events", "business_import_dates_floor"),
        ("business_draft_revisions", "business_draft_due_date_floor"),
        ("business_draft_revisions", "business_revision_immutable"),
    ]
    with service.authority.pool.connection() as db, db.transaction():
        for table, trigger in floors:
            db.execute(f"alter table public.{table} disable trigger {trigger}")
        db.execute(
            "update public.financial_import_events set resolution=jsonb_set("
            "resolution,'{business,due_on}',to_jsonb(%s::text)) where id=%s",
            (day, draft_id),
        )
        seeded = db.execute(
            "update public.business_draft_revisions r set after_due_on=%s where draft_id=%s"
            " and version=(select max(version) from public.business_draft_revisions where draft_id=r.draft_id)",
            (day, draft_id),
        )
        assert seeded.rowcount == 1
        for table, trigger in floors:
            db.execute(f"alter table public.{table} enable trigger {trigger}")


def due_dates(service, draft_id):
    with service.authority.pool.connection() as db:
        return db.execute(
            "select before_due_on::text, after_due_on::text from public.business_draft_revisions"
            " where draft_id=%s order by version",
            (draft_id,),
        ).fetchall()


@shared.pytestmark
@pytest.mark.owner_acts
def test_draft_with_an_old_due_date_still_takes_edits_and_notes(actions):
    service, context, _ = actions
    draft_id, version = shared.create(service, context)
    legacy_due_on(service, draft_id, "1999-12-31")

    # save_revision: another field changes, the due date is copied forward.
    amount = BusinessFactPatch(amount={"state": "known", "value": "900"})
    edited = service.review(context, draft_id, ReviewDraft(version=version, facts=amount), str(uuid4()))
    assert edited.outcome == "applied", edited
    # save_annotation: a note changes nothing else.
    noted = edit_note(
        service.authority, context, draft_id,
        EditCurrentNote(expected_version=edited.version, note="Pagar al suplidor"), str(uuid4()),
    )
    assert due_dates(service, draft_id)[-2:] == [("1999-12-31", "1999-12-31")] * 2

    # The application refuses a new old date before storage is asked.
    with pytest.raises(ValidationError):
        ReviewDraft(version=noted.version, due_on={"state": "known", "value": "1999-01-01"})
    # Storage refuses it from any writer that skips the application.
    with service.authority.pool.connection() as db:
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            db.execute(
                "insert into public.business_draft_revisions"
                " (space_id,draft_id,version,actor,after_facts,before_due_on,after_due_on)"
                " select space_id,draft_id,version+1,actor,after_facts,after_due_on,%s"
                " from public.business_draft_revisions where draft_id=%s and version=%s",
                ("1999-01-01", draft_id, noted.version),
            )
    cleared = service.review(
        context, draft_id, ReviewDraft(version=noted.version, due_on={"state": "unknown"}), str(uuid4())
    )
    assert cleared.outcome == "applied", cleared
    assert due_dates(service, draft_id)[-1] == ("1999-12-31", None)


def paid_bill_read_on(service, draft_id, day):
    """A paid bill whose date the reader took from the paper, with no declaration yet."""
    with service.authority.pool.connection() as db:
        seeded = db.execute(
            "update public.financial_import_events set resolution=jsonb_set(jsonb_set("
            "resolution,'{business,bill_mark}','\"Factura pagada\"'),'{business,facts,occurred_on}',"
            "jsonb_build_object('state','known','value',%s::text,'origin','extracted','verified',false,"
            "'source_ids',resolution#>'{business,facts,amount,source_ids}')) where id=%s",
            (day, draft_id),
        )
        assert seeded.rowcount == 1


@shared.pytestmark
@pytest.mark.owner_acts
@pytest.mark.parametrize("accepted", [False, True])
def test_category_review_copies_only_an_accepted_read_date_into_the_payment_date(actions, accepted):
    service, context, _ = actions
    draft_id, version = shared.create(service, context)
    read = (ledger.today() - timedelta(days=30)).isoformat() if accepted else "0026-10-05"
    paid_bill_read_on(service, draft_id, read)

    # The person pays in cash and submits no date: paid_on follows the read.
    request = ReviewDraft(version=version, purchase=PurchaseReview(category="02", payment_method="01"))
    reviewed = service.review(context, draft_id, request, str(uuid4()))
    assert reviewed.outcome == "applied", reviewed
    view = service.dossier(context, draft_id)
    assert view.dgii.category == "02"
    assert view.dgii.paid_on == (date.fromisoformat(read) if accepted else None)
    assert view.inheritance["paid_on"].value == (read if accepted else None)
    # The read stays as evidence and still asks the person to correct it.
    assert (view.facts.occurred_on.value.isoformat(), view.facts.occurred_on.origin) == (read, "extracted")
    asks = [item.code for item in view.blockers if item.field == "occurred_on"]
    assert asks == ([] if accepted else ["business_date_before_minimum"])

    # A person asserting the same old date is refused before storage, and by storage.
    typed = ReviewDraft(version=reviewed.version, purchase=PurchaseReview(paid_on="0026-10-05"))
    refused = service.review(context, draft_id, typed, str(uuid4()))
    assert (refused.outcome, refused.code) == ("invalid_input", "business_date_before_minimum")
    with service.authority.pool.connection() as db:
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            db.execute(
                "update public.financial_import_events set resolution=jsonb_set("
                "resolution,'{business,dgii,paid_on}','\"0026-10-05\"') where id=%s",
                (draft_id,),
            )


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_storage_floor_function_is_not_client_executable(role):
    with database() as (db, schema):
        db.execute(migration().replace("public.", schema + "."))
        assert not db.execute("SELECT has_function_privilege(%s,%s,'EXECUTE')", (role, f"{schema}.enforce_business_date_floor()")).fetchone()[0]
        assert db.execute("SELECT has_function_privilege('service_role',%s,'EXECUTE')", (f"{schema}.enforce_business_date_floor()",)).fetchone()[0]
