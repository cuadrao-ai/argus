"""An owner with a bank account, lines, a suggestion and an outcome deletes
their account, and every bank row goes with the Business space.

Reproduces the Eval finding: ``business_bank_accounts.account_id`` is a
non-deferrable NO ACTION key to ``financial_accounts``. The ``auth.users``
cascade reaches ``financial_accounts`` before ``spaces`` (the older key fires
first), so the key is checked while the binding still exists and the delete
is refused. Rolled back, so nobody is deleted.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from tests import test_financial_accounts_postgres as shared
from tests.test_business_bank_matching_postgres import (
    _binding,
    _import,
    _line,
    _outcome,
)
from tests.test_business_spaces_migration_postgres import account, space

psycopg = pytest.importorskip("psycopg")
users = shared.users
pytestmark = pytest.mark.skipif(
    not shared.DSN, reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured"
)

BANK_TABLES = (
    "business_bank_accounts",
    "business_bank_imports",
    "business_bank_lines",
    "business_bank_suggestions",
    "business_bank_line_outcomes",
)


def test_an_owner_with_bank_rows_is_deleted_and_the_bank_rows_go_with_the_space(
    users,  # noqa: ANN001
) -> None:
    owner = users["owner"]
    with psycopg.connect(shared.DSN) as db, db.transaction(force_rollback=True):
        space_id = space(db, owner)
        account_id = account(db, owner, space_id)
        binding = _binding(db, space_id, account_id)
        line_id = _line(
            db, space_id, binding, _import(db, space_id, binding, owner), "c" * 64
        )
        db.execute(
            "insert into public.business_bank_suggestions"
            " (space_id, line_id, target_kind, target_id,"
            "  amount_score, date_score, merchant_score)"
            " values (%s, %s, 'receipt', %s, 1, 1, 1)",
            (space_id, line_id, str(uuid4())),
        )
        _outcome(db, space_id, line_id, "k1")

        # The Admin API delete is one statement in its own transaction.
        db.execute("delete from auth.users where id = %s", (owner,))
        db.execute("set constraints all immediate")

        assert db.execute(
            "select count(*) from public.spaces where id = %s::uuid", (space_id,)
        ).fetchone() == (0,)
        assert db.execute(
            "select count(*) from public.financial_accounts where id = %s::uuid",
            (account_id,),
        ).fetchone() == (0,)
        for table in BANK_TABLES:
            assert db.execute(
                f"select count(*) from public.{table} where space_id = %s::uuid",
                (space_id,),
            ).fetchone() == (0,), table
