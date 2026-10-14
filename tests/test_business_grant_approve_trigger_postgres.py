"""Approval is the owner's alone, in the database: a client grant that carries
approve for anyone but the space's creator is refused on insert and on update,
whoever writes it; the owner's own grant keeps all three capabilities and an
accountant's grant keeps read and prepare."""

from __future__ import annotations

import psycopg
import pytest
from psycopg import Connection

from tests import test_financial_accounts_postgres as shared
from tests.test_business_spaces_migration_postgres import space

users = shared.users
pytestmark = pytest.mark.skipif(not shared.DSN, reason="Disposable database required")

GRANT = (
    "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities)"
    " values (%s,%s,%s,%s) returning id"
)


def test_the_database_refuses_approve_on_anyone_but_the_owner(users) -> None:  # noqa: ANN001
    with Connection.connect(shared.DSN) as db:
        business = space(db, users["owner"])
        owner_grant = db.execute(
            GRANT,
            (business, users["owner"], users["owner"], ["read", "prepare", "approve"]),
        ).fetchone()[0]
        accountant_grant = db.execute(
            GRANT, (business, users["other"], users["owner"], ["read", "prepare"])
        ).fetchone()[0]
        db.commit()
        # Insert with approve for an accountant: refused, nothing written.
        with pytest.raises(
            psycopg.errors.CheckViolation, match="business_grant_approve_owner_only"
        ):
            db.execute(
                GRANT,
                (
                    business,
                    users["other"],
                    users["owner"],
                    ["read", "prepare", "approve"],
                ),
            )
        db.rollback()
        # Update that adds approve to the accountant's row: refused, the row unchanged.
        with pytest.raises(
            psycopg.errors.CheckViolation, match="business_grant_approve_owner_only"
        ):
            db.execute(
                "update public.business_client_grants set capabilities=ARRAY['read','prepare','approve']"
                " where id=%s",
                (accountant_grant,),
            )
        db.rollback()
        rows = {
            str(row[0]): list(row[1])
            for row in db.execute(
                "select id, capabilities from public.business_client_grants where space_id=%s",
                (business,),
            ).fetchall()
        }
        assert rows == {
            str(owner_grant): ["read", "prepare", "approve"],
            str(accountant_grant): ["read", "prepare"],
        }
        # The owner's own row may still be written with approve, and narrowed and widened again.
        db.execute(
            "update public.business_client_grants set capabilities=ARRAY['read','prepare'] where id=%s",
            (owner_grant,),
        )
        db.execute(
            "update public.business_client_grants set capabilities=ARRAY['read','prepare','approve']"
            " where id=%s",
            (owner_grant,),
        )
        db.commit()
