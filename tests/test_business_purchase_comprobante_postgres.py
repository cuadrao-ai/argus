"""One purchase comprobante per Business and supplier (20261101000200).

SQL fixtures only, each case inside a rolled-back transaction. The generated
columns project the saved facts the way the code normalizes them, the partial
unique index refuses a second accepting or accepted purchase with one supplier
RNC and comprobante in one Business, and the migration's guard stops with a
named error while such duplicates already exist.
"""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from argus.domain.business.actions.fiscal import PURCHASE_COMPROBANTE_INDEX
from psycopg.types.json import Jsonb

from tests import test_business_spaces_migration_postgres as migration
from tests import test_financial_accounts_postgres as shared

users = shared.users
db = migration.db
space = migration.space
pytestmark = pytest.mark.skipif(not shared.DSN, reason="Disposable database required")
MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "supabase/migrations/20261101000200_business_purchase_comprobante_once.sql"
)
SUPPLIER = "131000002"
NCF = "B0100000001"


def event(
    db,
    user,
    owner_space,
    *,
    kind="expense",
    rnc=SUPPLIER,
    ncf=NCF,
    ecf=None,
    state="accepted",
):  # noqa: ANN001
    fiscal = {}
    if rnc is not None:
        fiscal["rnc"] = {"state": "known", "value": rnc}
    if ncf is not None:
        fiscal["ncf"] = {"state": "known", "value": ncf}
    if ecf is not None:
        fiscal["ecf"] = {"state": "known", "value": ecf}
    facts = {"fiscal": fiscal}
    if kind is not None:
        facts["kind"] = {"state": "known", "value": kind}
    event_id = str(uuid4())
    db.execute(
        "insert into public.financial_import_events"
        " (id,user_id,owner_space_id,state,evidence,resolution,activity_id,created_at,updated_at,version)"
        " values (%s,%s,%s,%s,'transaction',%s,%s,now(),now(),1)",
        (
            event_id,
            user,
            owner_space,
            state,
            Jsonb({"business": {"schema_version": "1", "facts": facts}}),
            str(uuid4()) if state == "accepted" else None,
        ),
    )
    return event_id


def projected(db, event_id) -> tuple:  # noqa: ANN001
    return db.execute(
        "select business_kind,business_rnc,business_fiscal_number"
        " from public.financial_import_events where id=%s",
        (event_id,),
    ).fetchone()


@pytest.mark.parametrize(
    "read,expected",
    [
        (dict(), ("expense", SUPPLIER, NCF)),
        (dict(rnc="1-31-00000-2", ncf=" b0100000001 "), ("expense", SUPPLIER, NCF)),
        (dict(rnc="000-00000-0"), ("expense", None, NCF)),
        (dict(rnc="131000002 9"), ("expense", None, NCF)),
        (dict(ncf="B01"), ("expense", SUPPLIER, None)),
        (dict(ncf=NCF, ecf="E320000000001"), ("expense", SUPPLIER, "E320000000001")),
        (dict(ncf=NCF, ecf=""), ("expense", SUPPLIER, NCF)),
        (dict(kind=None, rnc=None, ncf=None), (None, None, None)),
    ],
    ids=[
        "as_printed",
        "dashed_and_lower",
        "zero_rnc",
        "run_on_rnc",
        "short_ncf",
        "ecf_first",
        "empty_ecf",
        "nothing",
    ],
)
def test_the_generated_columns_project_the_facts_as_the_code_reads_them(
    db, users, read, expected
):  # noqa: ANN001
    owner = users["owner"]
    assert (
        projected(db, event(db, owner, space(db, owner), state="open", **read))
        == expected
    )


def test_one_business_keeps_one_purchase_per_supplier_and_comprobante(db, users):  # noqa: ANN001
    owner = users["owner"]
    first = space(db, owner)
    event(db, owner, first)
    # Another Business may hold the same supplier and number.
    event(db, users["other"], space(db, users["other"]))
    # The same Business may hold it again only while open, or as a sale.
    event(db, owner, first, state="open")
    event(db, owner, first, kind="income")
    with pytest.raises(psycopg.errors.UniqueViolation) as refused, db.transaction():
        event(db, owner, first, rnc="1-31-00000-2", ncf=" b0100000001 ")
    assert refused.value.diag.constraint_name == PURCHASE_COMPROBANTE_INDEX
    with pytest.raises(psycopg.errors.UniqueViolation), db.transaction():
        event(db, owner, first, state="accepting")
    # Without a supplier or a number the index does not apply.
    event(db, owner, first, rnc=None)
    event(db, owner, first, ncf="B01")


def guard() -> str:
    text = MIGRATION.read_text(encoding="utf-8")
    return re.search(r"do \$\$.*?end \$\$;", text, re.S).group(0)


def test_the_migration_stops_with_a_named_error_while_duplicates_exist(db, users):  # noqa: ANN001
    owner = users["owner"]
    first = space(db, owner)
    db.execute(f"drop index public.{PURCHASE_COMPROBANTE_INDEX}")
    kept = event(db, owner, first)
    event(db, owner, first)
    with (
        pytest.raises(
            psycopg.errors.RaiseException,
            match="business_purchase_comprobante_duplicates_present: 1 Business",
        ),
        db.transaction(),
    ):
        db.execute(guard())
    db.execute(
        "delete from public.financial_import_events where owner_space_id=%s and id<>%s",
        (first, kept),
    )
    db.execute(guard())
