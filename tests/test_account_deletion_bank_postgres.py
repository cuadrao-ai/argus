"""An owner with a bank account, lines, a suggestion and an outcome deletes
their account. The closed Business keeps every bank row for its record
custodian, and the day-30 purge takes them with the Business space.

``business_bank_accounts.account_id`` is a NO ACTION key to
``financial_accounts``. A cascade can reach ``financial_accounts`` before the
binding (the older key fires first), so while the key was checked immediately
the binding still existed and the delete was refused. 20261021065000 checks it
at commit. Account deletion now keeps the Business, so the cascade that takes
the account and the binding runs when the space goes. Proven by the bare space
cascade (rolled back) and by the day-30 purge after the AccountDeletionService
run and after POST /account/delete. A bare Auth delete of an owner the Business
still names is refused. Deleting the account while the binding exists is still
refused.
"""

from __future__ import annotations

from datetime import timedelta
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
from argus.domain.business.purge import PostgresBusinessPurge
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

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
from tests.test_business_account_deletion_postgres import (
    Auth,
    close_owned_business,
    command,
    erase_open_owner,
    release_custodian,
)
from tests.test_business_bank_matching_postgres import _binding, _import, _line
from tests.test_business_custody_graph_postgres import FakeObjects
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


def _bank_counts(db, space_id: str) -> list[int]:  # noqa: ANN001
    return [
        db.execute(
            f"select count(*) from public.{table} where space_id = %s::uuid",
            (space_id,),
        ).fetchone()[0]
        for table in BANK_TABLES
    ]


def _assert_gone(db, space_id: str, account_id: str) -> None:  # noqa: ANN001
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


def _assert_kept_for_custodian(owner: str, space_id: str, account_id: str) -> None:
    """The owner's Auth row is gone; the closed Business, its account and every
    bank row stay under the record custodian."""
    with psycopg.connect(DSN) as db:
        assert db.execute(
            "select count(*) from auth.users where id = %s", (owner,)
        ).fetchone() == (0,)
        custodian, closed = db.execute(
            "select created_by::text, closed_at is not null from public.spaces"
            " where id = %s::uuid",
            (space_id,),
        ).fetchone()
        assert closed and custodian != owner
        assert db.execute(
            "select user_id::text from public.financial_accounts where id = %s::uuid",
            (account_id,),
        ).fetchone() == (custodian,)
        assert _bank_counts(db, space_id) == [1] * len(BANK_TABLES)
        assert db.execute(
            "select count(*) from public.business_bank_imports"
            " where space_id = %s::uuid and imported_by is null",
            (space_id,),
        ).fetchone() == (1,)
        assert db.execute(
            "select count(*) from public.business_bank_line_outcomes"
            " where space_id = %s::uuid and created_by is null",
            (space_id,),
        ).fetchone() == (1,)


def _purge_at_day_30(space_id: str, account_id: str) -> None:
    with ConnectionPool(DSN, min_size=1, max_size=4) as pool:
        with pool.connection() as db:
            db.execute(
                "update public.spaces set closed_at = clock_timestamp() - %s"
                " where id = %s::uuid",
                (timedelta(days=30), space_id),
            )
        PostgresBusinessPurge(pool, FakeObjects(), Auth()).purge(space_id=space_id)
    with psycopg.connect(DSN) as db:
        _assert_gone(db, space_id, account_id)


@pytest.fixture
def owner(lane):  # noqa: ANN001, ANN201, F811
    """A committed Business owner with bank rows. Teardown removes whatever a
    failed deletion or purge left: the custody rows, the space and its
    custodian (the space cascade takes the bank rows, which the outcomes guard
    allows), then the auth user. A cleanup failure raises, so a leak fails the
    test run instead of hiding."""
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
        release_custodian(space_id)
        with psycopg.connect(DSN) as db, db.transaction():
            db.execute("delete from public.spaces where id = %s", (space_id,))
            db.execute(
                "delete from argus_private.account_deletion_runs where user_id = %s",
                (user_id,),
            )
            db.execute("delete from auth.users where id = %s", (user_id,))


def test_a_bare_auth_delete_of_an_owner_with_bank_rows_is_refused(
    lane,  # noqa: ANN001, F811
) -> None:
    user_id = lane[2][0]
    with psycopg.connect(DSN) as db, db.transaction(force_rollback=True):
        space_id, _ = _bank_rows(db, user_id)
        with (
            pytest.raises(
                psycopg.errors.CheckViolation,
                match="business_custody_identity_detachment_required",
            ),
            db.transaction(),
        ):
            db.execute("delete from auth.users where id = %s", (user_id,))
        assert _bank_counts(db, space_id) == [1] * len(BANK_TABLES)


def test_the_space_cascade_takes_the_account_and_every_bank_row_at_commit(
    lane,  # noqa: ANN001, F811
) -> None:
    user_id = lane[2][0]
    with psycopg.connect(DSN) as db, db.transaction(force_rollback=True):
        space_id, account_id = _bank_rows(db, user_id)

        # The day-30 purge removes the Business with one space delete.
        db.execute("delete from public.spaces where id = %s", (space_id,))
        db.execute("set constraints all immediate")

        _assert_gone(db, space_id, account_id)


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


@pytest.mark.owner_acts
def test_the_deletion_service_deletes_an_owner_with_bank_rows(lane, owner) -> None:  # noqa: ANN001, F811
    user_id, space_id, account_id = owner

    with ConnectionPool(DSN, min_size=1, max_size=4) as pool:
        assert erase_open_owner(pool, user_id).status == "done"

    _assert_kept_for_custodian(user_id, space_id, account_id)
    _purge_at_day_30(space_id, account_id)


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
    monkeypatch.delenv("CUADRAO_MOCK_AUTH", raising=False)
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


@pytest.mark.owner_acts
def test_the_api_deletes_an_owner_with_bank_rows(lane, owner, route) -> None:  # noqa: ANN001, F811
    user_id, space_id, account_id = owner
    with ConnectionPool(DSN, min_size=1, max_size=4) as pool:
        close_owned_business(pool, user_id)
        service = command({"pool": pool, "objects": FakeObjects()})
        with patch.object(
            account_route, "account_deletion_service", return_value=service
        ):
            response = route.post(
                URL,
                json={"confirm": True},
                headers=_bearer(_token(user_id, _session(user_id))),
            )

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "done", "pending": []}
    _assert_kept_for_custodian(user_id, space_id, account_id)
    _purge_at_day_30(space_id, account_id)
