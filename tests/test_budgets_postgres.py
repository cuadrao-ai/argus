"""Budget replay, unique scope, rollback and read isolation on real Postgres."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from argus.domain.planning import storage
from argus.domain.planning.budget_schemas import BudgetEdit
from argus.domain.planning.budgets import BudgetScopeConflict
from argus.domain.recording.errors import AccountNotFound
from argus.domain.recording.service import FinancialAccountService
from psycopg.errors import InsufficientPrivilege, UniqueViolation
from psycopg.types.json import Jsonb

from tests import test_financial_accounts_postgres as shared
from tests.financial_accounts.test_budgets import setup_budget
from tests.financial_accounts.test_loop_commands import NOW

repository = shared.repository
users = shared.users
pytestmark = pytest.mark.skipif(
    not shared.DSN, reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured"
)


@pytest.fixture
def scene(repository, users):
    return FinancialAccountService(repository, lambda: NOW), users["owner"], None


def test_concurrent_replay_and_scope_race(scene):
    service, _, budget, body = setup_budget(scene)
    command = BudgetEdit(expected_version=1, limit="160")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda _: service.edit(scene[1], budget["id"], command, "lost-response"),
                range(4),
            )
        )
    assert sum(not r["replayed"] for r in results) == 1
    assert all(r["budget"]["version"] == 2 for r in results)
    service.edit(
        scene[1], budget["id"], BudgetEdit(expected_version=2, archived=True), "archive"
    )

    def create(key):
        try:
            return service.create(scene[1], body, key)
        except BudgetScopeConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(create, ["one", "two"]))
    assert sum(r is not None for r in results) == 1


def test_registered_owner_select_service_writes_and_storage_duplicate_guard(
    scene, repository, users
):
    service, _, budget, _ = setup_budget(scene)
    with pytest.raises(AccountNotFound):
        service.edit(
            users["other"],
            budget["id"],
            BudgetEdit(expected_version=1, limit="1"),
            "other",
        )
    with repository._pool.connection() as connection:
        for owner, guest, count in [
            (users["owner"], False, 1),
            (users["other"], False, 0),
            (users["owner"], True, 0),
        ]:
            with connection.transaction():
                shared._set_authenticated_claims(
                    connection, user_id=owner, is_anonymous=guest
                )
                assert (
                    connection.execute(
                        "select count(*) from public.financial_budgets"
                    ).fetchone()[0]
                    == count
                )
            connection.execute("reset role")
        with pytest.raises(InsufficientPrivilege), connection.transaction():
            shared._set_authenticated_claims(
                connection, user_id=users["owner"], is_anonymous=False
            )
            connection.execute("update public.financial_budgets set body=body")
        connection.execute("reset role")
        with pytest.raises(InsufficientPrivilege), connection.transaction():
            shared._set_authenticated_claims(
                connection, user_id=users["owner"], is_anonymous=False
            )
            connection.execute("select * from public.financial_plan_receipts")
        connection.execute("reset role")
        duplicate = budget | {"id": str(uuid4())}
        with pytest.raises(UniqueViolation), connection.transaction():
            connection.execute(
                "insert into public.financial_budgets(id,user_id,body) values(%s,%s,%s)",
                (duplicate["id"], scene[1], Jsonb(duplicate)),
            )


def test_failure_after_definition_write_rolls_back_definition_and_receipt(
    scene, repository, monkeypatch
):
    service, _, budget, _ = setup_budget(scene)
    original = storage.jsonable_encoder

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic receipt failure")

    monkeypatch.setattr(storage, "jsonable_encoder", fail)
    command = BudgetEdit(expected_version=1, limit="160")
    with pytest.raises(RuntimeError, match="synthetic receipt failure"):
        service.edit(scene[1], budget["id"], command, "rollback")
    assert service.get(scene[1], budget["id"])["budget"]["limit_minor"] == 15000
    monkeypatch.setattr(storage, "jsonable_encoder", original)
    assert not service.edit(scene[1], budget["id"], command, "rollback")["replayed"]
