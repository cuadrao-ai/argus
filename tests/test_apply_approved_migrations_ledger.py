"""The apply tool names a missing migration ledger instead of failing raw (#1789, #1890).

A reset production has no ``supabase_migrations.schema_migrations`` until the
reset step recreates it. The tool checks for the table before it reads the
ledger and says what to create.
"""

from __future__ import annotations

import pytest

from scripts.ops import apply_approved_migrations as applier


class _Cursor:
    def __init__(self, row: tuple[object, ...]) -> None:
        self.row = row

    def fetchone(self) -> tuple[object, ...]:
        return self.row


class _Connection:
    def __init__(self, ledger_table: str | None, can_insert: bool = True) -> None:
        self.ledger_table, self.can_insert = ledger_table, can_insert

    def execute(self, sql: str, params: object = None) -> _Cursor:
        assert "to_regclass" in sql and params == (applier._LEDGER_TABLE,) * 2
        return _Cursor((self.ledger_table, self.can_insert))


def test_a_missing_ledger_table_is_named_with_the_statement_that_creates_it() -> None:
    with pytest.raises(applier.ApplyError) as refusal:
        applier.check_ledger_table(_Connection(None))
    message = str(refusal.value)
    assert message.startswith(
        "the migration ledger table supabase_migrations.schema_migrations is missing; "
        "create it first: create schema if not exists supabase_migrations; create table "
        "supabase_migrations.schema_migrations (version text primary key, statements "
        "text[], name text)"
    )


def test_a_ledger_table_the_user_cannot_write_is_named_too() -> None:
    with pytest.raises(applier.ApplyError, match="cannot insert into supabase_migrations"):
        applier.check_ledger_table(_Connection(applier._LEDGER_TABLE, can_insert=False))


def test_a_present_writable_ledger_table_passes_silently() -> None:
    applier.check_ledger_table(_Connection(applier._LEDGER_TABLE))
