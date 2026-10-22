from __future__ import annotations

from contextlib import nullcontext
from uuid import UUID

import pytest
from argus.domain.business.authority import authorize
from argus.domain.business.bank.model import BankMatchingError
from argus.domain.business.bank.movements_store import _ACCOUNTS, _accounts, bank_session
from argus.domain.business.bank.store_postgres import PostgresBankStore
from argus.domain.business.contracts.authority import TrustedActor

from tests import test_business_bank_matching_postgres as bank_tables
from tests.test_business_bank_matching_postgres import (
    BANK_TABLES,
    _as,
    _binding,
    _grant,
    psycopg,
)
from tests.test_business_spaces_migration_postgres import account, space

db = bank_tables.db
users = bank_tables.users
pytestmark = bank_tables.pytestmark


class _Pool:
    def __init__(self, connection) -> None:  # noqa: ANN001
        self.connection = lambda: nullcontext(connection)


@pytest.mark.parametrize("table", BANK_TABLES)
@pytest.mark.parametrize("role", ["anon", "authenticated"])
@pytest.mark.parametrize("operation", ["select", "insert", "update"])
def test_clients_cannot_reach_bank_tables(db, users, table, role, operation) -> None:  # noqa: ANN001
    owner = users["owner"]
    business = space(db, owner)
    _grant(db, business, owner, ["read", "prepare", "approve"])
    queries = {
        "select": f"select * from public.{table}",
        "insert": f"insert into public.{table} default values",
        "update": f"update public.{table} set space_id=space_id",
    }
    with pytest.raises(psycopg.errors.InsufficientPrivilege), db.transaction():
        with db.cursor() as cursor:
            _as(cursor, owner)
            cursor.execute(f"set local role {role}")
            cursor.execute(queries[operation])


@pytest.mark.parametrize(
    "kind", ["personal", "own_personal", "foreign_business", "wrong_custodian"]
)
def test_server_cannot_bind_an_account_outside_business(db, users, kind) -> None:  # noqa: ANN001
    owner, other = users["owner"], users["other"]
    business = space(db, owner)
    foreign = space(db, other)
    db.execute("set constraints all deferred")
    account_id = account(
        db,
        owner if kind == "own_personal" else other,
        None
        if kind in {"personal", "own_personal"}
        else foreign
        if kind == "foreign_business"
        else business,
    )
    with (
        pytest.raises(psycopg.errors.CheckViolation, match="account_not_in_space"),
        db.transaction(),
    ):
        _binding(db, business, account_id)


def _legacy_binding(db, business, account_id) -> str:  # noqa: ANN001
    db.execute("set local session_replication_role=replica")
    binding = _binding(db, business, account_id)
    db.execute("set local session_replication_role=origin")
    return binding


def test_old_invalid_binding_never_exposes_foreign_account_metadata(db, users) -> None:  # noqa: ANN001
    owner, other = users["owner"], users["other"]
    business = space(db, owner)
    foreign = account(db, other)
    _legacy_binding(db, business, foreign)
    assert db.execute(_ACCOUNTS, (business,)).fetchall() == []


@pytest.mark.parametrize("surface", ["account", "movements", "session"])
def test_old_invalid_binding_refuses_processing_without_deleting_it(
    db, users, surface
) -> None:  # noqa: ANN001
    owner, other = users["owner"], users["other"]
    business = space(db, owner)
    foreign = account(db, other)
    binding = _legacy_binding(db, business, foreign)
    _grant(db, business, owner, ["read", "prepare", "approve"])
    pool = _Pool(db)
    actor = TrustedActor(
        actor_id=UUID(owner), space_id=UUID(business), actor_kind="member"
    )
    context = authorize(db, actor).context
    with pytest.raises(BankMatchingError, match="account_not_in_space"):
        if surface == "account":
            PostgresBankStore(pool).get_account(UUID(business))
        elif surface == "movements":
            _accounts(db, business)
        else:
            with bank_session(pool, context, "prepare"):
                pytest.fail("an invalid binding reached the write session")
    assert db.execute(
        "select account_id::text from public.business_bank_accounts where id=%s",
        (binding,),
    ).fetchone() == (foreign,)


def test_valid_manual_binding_survives_current_owner_transfer_and_custody_rewrite(
    db, users
) -> None:  # noqa: ANN001
    owner, other = users["owner"], users["other"]
    business = space(db, owner)
    account_id = account(db, owner, business)
    binding = _binding(db, business, account_id)
    db.execute(
        "update public.spaces set current_owner_id=%s where id=%s", (other, business)
    )
    assert PostgresBankStore(_Pool(db)).get_account(UUID(business)).id == UUID(binding)
    db.execute("set constraints all deferred")
    db.execute(
        "update public.financial_accounts set user_id=%s where id=%s", (other, account_id)
    )
    db.execute("update public.spaces set created_by=%s where id=%s", (other, business))
    db.execute("set constraints all immediate")
    assert PostgresBankStore(_Pool(db)).get_account(UUID(business)).id == UUID(binding)


def test_server_role_can_check_and_read_a_valid_binding(db, users) -> None:  # noqa: ANN001
    owner = users["owner"]
    business = space(db, owner)
    account_id = account(db, owner, business)
    with db.transaction():
        db.execute("set local role service_role")
        binding = _binding(db, business, account_id)
        assert db.execute(
            "select argus_private.business_bank_account_in_space(%s,%s)",
            (business, account_id),
        ).fetchone() == (True,)
        assert PostgresBankStore(_Pool(db)).get_account(UUID(business)).id == UUID(
            binding
        )
        assert len(_accounts(db, business)) == 1


def test_prepare_client_cannot_insert_a_foreign_binding(db, users) -> None:  # noqa: ANN001
    owner, other = users["owner"], users["other"]
    business = space(db, owner)
    foreign = account(db, other)
    _grant(db, business, owner, ["read", "prepare"])
    with pytest.raises(psycopg.errors.InsufficientPrivilege), db.transaction():
        with db.cursor() as cursor:
            _as(cursor, owner)
            _binding(db, business, foreign)


def test_server_cannot_retarget_a_valid_binding_to_foreign_account(db, users) -> None:  # noqa: ANN001
    owner, other = users["owner"], users["other"]
    business = space(db, owner)
    binding = _binding(db, business, account(db, owner, business))
    foreign = account(db, other)
    with (
        pytest.raises(psycopg.errors.CheckViolation, match="account_not_in_space"),
        db.transaction(),
    ):
        db.execute(
            "update public.business_bank_accounts set account_id=%s where id=%s",
            (foreign, binding),
        )
