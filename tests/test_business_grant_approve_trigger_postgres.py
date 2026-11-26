"""The database derives legacy grant capabilities from each canonical Business role."""

from __future__ import annotations

from typing import get_args

import psycopg
import pytest
from argus.domain.business.contracts.authority import Capability
from argus.domain.business.roles import ROLE_PERMISSIONS, BusinessRole
from psycopg import Connection

from tests import test_financial_accounts_postgres as shared
from tests.test_business_spaces_migration_postgres import space

users = shared.users
pytestmark = pytest.mark.skipif(not shared.DSN, reason="Disposable database required")

GRANT = (
    "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities)"
    " values (%s,%s,%s,%s) returning id"
)


def test_legacy_approve_cannot_widen_a_grant(users) -> None:  # noqa: ANN001
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
            psycopg.errors.CheckViolation, match="business_grant_role_required"
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
        db.execute(
            "update public.business_client_grants set capabilities=ARRAY['read','prepare','approve'] where id=%s",
            (accountant_grant,),
        )
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


@pytest.mark.parametrize("role", list(BusinessRole))
def test_grant_trigger_matches_role_permissions(users, role: BusinessRole) -> None:  # noqa: ANN001
    with Connection.connect(shared.DSN) as db:
        business = space(db, users["owner"])
        db.execute(GRANT, (business, users["owner"], users["owner"], ["approve"]))
        # A caller-supplied array may neither grant nor suppress a role's capabilities.
        grant_id, capabilities = db.execute(
            "insert into public.business_client_grants"
            " (space_id, grantee_id, issuer_id, business_role, capabilities)"
            " values (%s,%s,%s,%s,%s) returning id, capabilities",
            (business, users["other"], users["owner"], role.value, ["read"]),
        ).fetchone()
        expected = ROLE_PERMISSIONS[role].intersection(get_args(Capability))
        assert set(capabilities) == expected
        can_approve = role in (BusinessRole.OWNER, BusinessRole.ADMIN)
        assert ("approve" in capabilities) == can_approve
        (updated,) = db.execute(
            "update public.business_client_grants set capabilities=%s where id=%s"
            " returning capabilities",
            (["approve"], grant_id),
        ).fetchone()
        assert set(updated) == expected
