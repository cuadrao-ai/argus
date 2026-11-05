"""Money rows and their evidence never cascade from a Business.

Real PostgreSQL with every migration applied. ``20261101000100`` turns the
keys from the money tables to ``spaces`` into ON DELETE RESTRICT; the purge
removes those rows itself before the space (``MONEY_TABLES``). A person who
leaves never reaches them: the custody guard refuses the bare Auth delete and
the deletion command moves the Business to a placeholder.
"""

from __future__ import annotations

import psycopg
import pytest
from argus.domain.business.custody_graph import PostgresBusinessCustodyGraph
from argus.domain.business.purge import MONEY_TABLES, delete_money_rows
from psycopg import sql

from tests import test_business_account_deletion_postgres as deletion
from tests import test_business_custody_graph_postgres as graph

users = graph.users
actions = graph.actions
prepared = graph.prepared
custody = graph.custody
pytestmark = [graph.pytestmark, pytest.mark.owner_acts]
DSN = graph.DSN


def keys_to_spaces(db) -> dict[str, list[tuple[str, str]]]:  # noqa: ANN001
    """Every foreign key from a money table to spaces: table to (name, delete rule)."""

    rows = db.execute(
        "select c.conrelid::regclass::text, c.conname, c.confdeltype"
        " from pg_constraint c"
        " where c.contype='f' and c.confrelid='public.spaces'::regclass"
        " and c.conrelid::regclass::text=any(%s) order by 1, 2",
        ([table for table, _ in MONEY_TABLES],),
    ).fetchall()
    found: dict[str, list[tuple[str, str]]] = {table: [] for table, _ in MONEY_TABLES}
    for table, name, rule in rows:
        found[table].append((name, rule))
    return found


def counts(db, space: str) -> dict[str, int]:  # noqa: ANN001
    return {
        table: db.execute(
            sql.SQL("select count(*) from public.{} where {}=%s").format(
                sql.Identifier(table), sql.Identifier(column)
            ),
            (space,),
        ).fetchone()[0]
        for table, column in MONEY_TABLES
    }


def seed_settlement(db, w) -> None:  # noqa: ANN001
    """The custody fixture records money but settles and exports nothing;
    settle one receipt and record its 606 line as exported."""

    scope = PostgresBusinessCustodyGraph._scope(db, w["space"], w["old"], lock=False)
    db.execute(
        "insert into public.business_document_settlements(space_id,owner_id,activity_id,document_kind,status)"
        " values(%s,%s,%s,'receipt','pendiente') on conflict do nothing",
        (w["space"], w["old"], scope["activities"][0]),
    )
    db.execute(
        "insert into public.business_dgii_export_lines(space_id,activity_id,form,period,actor_id)"
        " values(%s,%s,'606','202610',%s)",
        (w["space"], scope["activities"][0], w["old"]),
    )


def test_every_key_from_a_money_table_to_spaces_restricts():
    with psycopg.connect(DSN) as db:
        found = keys_to_spaces(db)
    for table, keys in found.items():
        assert keys, f"{table} has no key to spaces"
        assert {rule for _, rule in keys} == {"r"}, (table, keys)


def test_a_space_delete_is_refused_until_the_purge_removes_the_money_rows(custody):
    w = custody
    with psycopg.connect(DSN) as db, db.transaction(force_rollback=True):
        seed_settlement(db, w)
        before = counts(db, w["space"])
        assert all(before.values()), before

        with (
            pytest.raises(psycopg.errors.ForeignKeyViolation) as refused,
            db.transaction(),
        ):
            db.execute("delete from public.spaces where id=%s", (w["space"],))
        named = {name for keys in keys_to_spaces(db).values() for name, _ in keys}
        assert refused.value.diag.constraint_name in named
        assert counts(db, w["space"]) == before

        db.execute("set constraints all deferred")
        db.execute(
            "delete from public.financial_activity_groups where id=any(%s::uuid[])",
            (
                PostgresBusinessCustodyGraph._scope(db, w["space"], w["old"], lock=False)[
                    "activities"
                ],
            ),
        )
        delete_money_rows(db, w["space"])
        db.execute("delete from public.spaces where id=%s", (w["space"],))
        db.execute("set constraints all immediate")
        assert not any(counts(db, w["space"]).values())


def test_business_money_survives_the_person_who_recorded_it_leaving(custody):
    w = custody
    with psycopg.connect(DSN) as db:
        seed_settlement(db, w)
        before = counts(db, w["space"])
        assert all(before.values()), before
        # The bare Auth delete is refused while the Business names the person.
        with (
            pytest.raises(
                psycopg.errors.CheckViolation,
                match="business_custody_identity_detachment_required",
            ),
            db.transaction(),
        ):
            db.execute("delete from auth.users where id=%s", (w["old"],))
        assert counts(db, w["space"]) == before

    # The deletion command moves the Business to a placeholder and deletes the person.
    deletion.close(w)
    assert deletion.command(w).delete_account(user_id=w["old"]).status == "done"
    assert deletion.Auth().user_exists(w["old"]) is False
    with psycopg.connect(DSN) as db:
        assert counts(db, w["space"]) == before
        custodian = db.execute(
            "select created_by::text from public.spaces where id=%s", (w["space"],)
        ).fetchone()[0]
        assert custodian != w["old"]
        # Every row now names the custodian, never the departed person.
        for table, column in MONEY_TABLES:
            if column != "owner_space_id":
                continue
            assert (
                db.execute(
                    sql.SQL(
                        "select count(*) from public.{} where owner_space_id=%s and user_id<>%s"
                    ).format(sql.Identifier(table)),
                    (w["space"], custodian),
                ).fetchone()[0]
                == 0
            ), table
