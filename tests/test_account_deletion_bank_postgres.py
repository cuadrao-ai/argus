"""An owner with a bank account, lines, a suggestion and an outcome deletes
their account, and every bank row goes with the Business space.

``business_bank_accounts.account_id`` is a NO ACTION key to
``financial_accounts``. The ``auth.users`` cascade reaches
``financial_accounts`` before ``spaces`` (the older key fires first), so while
the key was checked immediately the binding still existed and the delete was
refused. 20261021065000 checks it at commit, after the spaces cascade took the
binding. Proven three ways: the bare cascade (rolled back), the
AccountDeletionService run, and POST /account/delete. Deleting the account
while the binding exists is still refused.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import jwt
import psycopg
import pytest
from argus.api import dependencies
from argus.api import state as api_state
from argus.api.main import app
from argus.api.routers import account as account_route
from argus.api.schemas import User
from fastapi.testclient import TestClient

from tests.household.financial_fixtures import DSN, NOW
from tests.household.financial_fixtures import lane as lane  # noqa: F401 - fixture
from tests.test_account_deletion_api_postgres import (
    SECRET,
    URL,
    _bearer,
    _session,
    _token,
)
from tests.test_account_deletion_fk_census_postgres import (
    _invite_code_secret,  # noqa: F401 - autouse fixture (#794 invite codes)
)
from tests.test_account_deletion_postgres import SqlAuthAdmin, _service
from tests.test_business_bank_matching_postgres import _binding, _import, _line
from tests.test_business_spaces_migration_postgres import account, space

pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL required")

BANK_TABLES = (
    "business_bank_accounts",
    "business_bank_imports",
    "business_bank_lines",
    "business_bank_suggestions",
    "business_bank_line_outcomes",
)


def _bank_rows(db, owner: str) -> tuple[str, str]:  # noqa: ANN001
    """A Business space with a bank binding, an import, a line, a suggestion
    and an outcome the owner recorded. Returns (space id, account id)."""
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
    db.execute(
        "insert into public.business_bank_line_outcomes"
        " (space_id, line_id, kind, reason, create_key, created_by)"
        " values (%s, %s, 'no_receipt', 'cargo_banco', 'k1', %s)",
        (space_id, line_id, owner),
    )
    return space_id, account_id


def _assert_gone(db, owner: str, space_id: str, account_id: str) -> None:  # noqa: ANN001
    assert db.execute(
        "select count(*) from auth.users where id = %s", (owner,)
    ).fetchone() == (0,)
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


@pytest.fixture
def owner(lane):  # noqa: ANN001, ANN201, F811
    """A committed Business owner with bank rows. Teardown removes whatever a
    failed deletion left: the space first (its cascade takes the bank rows,
    which the outcomes guard allows), then the auth user. A cleanup failure
    raises, so a leak fails the test run instead of hiding."""
    user_id = lane[2][0]
    with psycopg.connect(DSN) as db, db.transaction():
        db.execute(
            "insert into public.profiles (id, email) values (%s, %s)",
            (user_id, f"household-{user_id}@example.test"),
        )
        space_id, account_id = _bank_rows(db, user_id)
    try:
        yield user_id, space_id, account_id
    finally:
        with psycopg.connect(DSN) as db, db.transaction():
            db.execute("delete from public.spaces where id = %s", (space_id,))
            db.execute(
                "delete from argus_private.account_deletion_runs where user_id = %s",
                (user_id,),
            )
            db.execute("delete from auth.users where id = %s", (user_id,))


def test_an_owner_with_bank_rows_is_deleted_and_the_bank_rows_go_with_the_space(
    lane,  # noqa: ANN001, F811
) -> None:
    user_id = lane[2][0]
    with psycopg.connect(DSN) as db, db.transaction(force_rollback=True):
        space_id, account_id = _bank_rows(db, user_id)

        # The Admin API delete is one statement in its own transaction.
        db.execute("delete from auth.users where id = %s", (user_id,))
        db.execute("set constraints all immediate")

        _assert_gone(db, user_id, space_id, account_id)


def test_deleting_the_account_while_the_binding_exists_is_still_refused(
    lane,  # noqa: ANN001, F811
) -> None:
    user_id = lane[2][0]
    with psycopg.connect(DSN) as db, db.transaction(force_rollback=True):
        _, account_id = _bank_rows(db, user_id)
        with (
            pytest.raises(
                psycopg.errors.ForeignKeyViolation,
                match="business_bank_accounts_account_id_fkey",
            ),
            db.transaction(),
        ):
            db.execute(
                "delete from public.financial_accounts where id = %s", (account_id,)
            )
            db.execute("set constraints all immediate")


def test_the_deletion_service_deletes_an_owner_with_bank_rows(lane, owner) -> None:  # noqa: ANN001, F811
    user_id, space_id, account_id = owner
    admin = SqlAuthAdmin()

    outcome = _service(lane, admin).delete_account(user_id=user_id)

    assert outcome.status == "done"
    assert admin.deleted == [user_id]
    with psycopg.connect(DSN) as db:
        _assert_gone(db, user_id, space_id, account_id)


@pytest.fixture
def route(monkeypatch):  # noqa: ANN001, ANN201
    """POST /account/delete on the disposable database. GoTrue's /user is a
    mock that returns the token's subject; mock auth is off."""
    gateway = MagicMock()
    gateway.get_auth_user_from_token.side_effect = lambda raw: {
        "id": _subject(raw),
        "email": f"{_subject(raw)}@example.test",
    }
    gateway.get_or_create_profile_for_auth_user.side_effect = lambda user, **_: User(
        id=user["id"], email=user["email"], created_at=NOW, updated_at=NOW
    )
    monkeypatch.setenv(account_route.FLAG, "true")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.delenv("ARGUS_MOCK_AUTH", raising=False)
    monkeypatch.delenv("NEXT_PUBLIC_MOCK_AUTH", raising=False)
    monkeypatch.setattr(api_state, "DATABASE_URL", DSN)
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    monkeypatch.setattr(dependencies, "permanent_account_access_allowed", lambda *_: True)
    account_route._per_account.reset()
    try:
        yield TestClient(app)
    finally:
        account_route._per_account.reset()


def _subject(raw: str) -> str:
    return jwt.decode(raw, options={"verify_signature": False})["sub"]


def test_the_api_deletes_an_owner_with_bank_rows(lane, owner, route) -> None:  # noqa: ANN001, F811
    user_id, space_id, account_id = owner
    admin = SqlAuthAdmin()
    with patch.object(
        account_route, "account_deletion_service", return_value=_service(lane, admin)
    ):
        response = route.post(
            URL,
            json={"confirm": True},
            headers=_bearer(_token(user_id, _session(user_id))),
        )

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "done", "pending": []}
    assert admin.deleted == [user_id]
    with psycopg.connect(DSN) as db:
        _assert_gone(db, user_id, space_id, account_id)
