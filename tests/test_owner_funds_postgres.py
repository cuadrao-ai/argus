import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from argus.domain.owner_scope import PERSONAL, BusinessSpace
from argus.domain.recording.errors import AccountNotFound, IdempotencyConflict
from argus.domain.recording.money_reads import current_activities
from argus.domain.recording.money_service import MoneyService
from argus.domain.recording.schemas import CreateFinancialAccountRequest, account_response
from argus.domain.recording.service import FinancialAccountService

from tests import test_financial_accounts_postgres as shared
from tests.financial_accounts.test_loop_commands import NOW
from tests.financial_accounts.test_owner_funds import entered, reviewed

users = shared.users
repository = shared.repository
pytestmark = pytest.mark.skipif(
    not shared.DSN, reason="Disposable database not configured"
)


@pytest.fixture
def funded_scene(repository, users):
    scope = BusinessSpace(str(uuid4()))
    with repository._pool.connection() as connection:
        connection.execute(
            "insert into public.spaces(id,created_by,kind,name) values(%s,%s,'business','Owner funds proof')",
            (scope.space_id, users["owner"]),
        )
    return (
        MoneyService(FinancialAccountService(repository, lambda: NOW)),
        users["owner"],
        scope,
    )


def test_recovery_concurrency_and_no_account_effect(funded_scene, repository):
    money, user, scope = funded_scene
    ids = []
    for account_scope in [PERSONAL, scope]:
        row = money.accounts.create(
            user_id=user,
            scope=account_scope,
            idempotency_key=str(uuid4()),
            request=CreateFinancialAccountRequest(
                type="checking",
                currency="DOP",
                amount="2000",
                as_of=NOW - timedelta(days=5),
            ),
        )
        ids.append((account_scope, row.stored.account.id, account_response(row.stored)))
    request = reviewed(money, user, scope, entered(scope))
    frozen = request.model_dump_json()

    def submit(_):
        from argus.domain.recording.money_schemas import MoneyRequest

        restarted = MoneyService(FinancialAccountService(repository, lambda: NOW))
        return restarted.write(
            user_id=user,
            scope=scope,
            request=MoneyRequest.model_validate_json(frozen),
            idempotency_key="claim-original",
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts = list(pool.map(submit, range(4)))
    assert sum(not item["replayed"] for item in receipts) == 1
    assert len({item["activity"]["activity_id"] for item in receipts}) == 1
    for account_scope, aid, before in ids:
        assert (
            account_response(
                money.accounts.get(user_id=user, scope=account_scope, account_id=aid)
            )
            == before
        )
    rows = current_activities(money.accounts.list_accounts(user_id=user, scope=scope))
    assert rows == [receipts[0]["activity"]]
    assert (
        current_activities(money.accounts.list_accounts(user_id=user, scope=PERSONAL))
        == []
    )
    with repository._pool.connection() as connection:
        assert (
            connection.execute(
                "select count(*) from public.financial_records where user_id=%s and account_id is null",
                (user,),
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "select count(*) from public.financial_activity_receipts where user_id=%s",
                (user,),
            ).fetchone()[0]
            == 1
        )
    changed = reviewed(money, user, scope, entered(scope, amount="999"))
    with pytest.raises(IdempotencyConflict):
        money.write(
            user_id=user, scope=scope, request=changed, idempotency_key="claim-original"
        )


def test_owner_funded_rows_are_not_browser_readable(funded_scene, repository):
    money, user, scope = funded_scene
    request = reviewed(money, user, scope, entered(scope))
    money.write(user_id=user, scope=scope, request=request, idempotency_key="rls")
    with repository._pool.connection() as connection:
        with connection.transaction():
            connection.execute("set local role authenticated")
            connection.execute(
                "select set_config('request.jwt.claims', %s, true)",
                (
                    json.dumps(
                        {"sub": user, "role": "authenticated", "is_anonymous": False}
                    ),
                ),
            )
            for table in [
                "financial_records",
                "financial_record_revisions",
                "financial_activity_groups",
                "financial_activity_memberships",
                "financial_activity_revisions",
            ]:
                assert (
                    connection.execute(
                        f"select count(*) from public.{table} where user_id=%s", (user,)
                    ).fetchone()[0]
                    == 0
                )


def test_sql_scope_shape_rejects_personal_and_foreign_owner(
    funded_scene, repository, users
):
    money, user, scope = funded_scene
    with repository._pool.connection() as connection:
        for space, funding, currency, owner in [
            (None, "owner_funds", "DOP", user),
            (scope.space_id, None, "DOP", user),
            (scope.space_id, "owner_funds", None, user),
            (scope.space_id, "owner_funds", "DOP", users["other"]),
        ]:
            with pytest.raises(shared.psycopg.IntegrityError), connection.transaction():
                connection.execute(
                    "insert into public.financial_records(id,user_id,record_kind,owner_space_id,funding,currency) values(%s,%s,'expense',%s,%s,%s)",
                    (str(uuid4()), owner, space, funding, currency),
                )
    request = entered(scope)
    with pytest.raises(AccountNotFound):
        money.write_entered(
            user_id=users["other"],
            scope=scope,
            request=request,
            idempotency_key="foreign",
        )


def test_failure_before_receipt_rolls_back_effect_then_recovers(
    funded_scene, repository, monkeypatch
):
    from contextlib import contextmanager
    from types import SimpleNamespace

    money, user, scope = funded_scene
    request = reviewed(money, user, scope, entered(scope))
    original_pool = repository._pool

    class InterruptedConnection:
        def __init__(self, connection):
            self.connection = connection

        def __getattr__(self, name):
            return getattr(self.connection, name)

        def execute(self, query, params=None):
            if query.lstrip().startswith(
                "insert into public.financial_activity_receipts"
            ):
                raise RuntimeError("Interrupted before receipt commit")
            return self.connection.execute(query, params)

    @contextmanager
    def interrupted():
        with original_pool.connection() as connection:
            yield InterruptedConnection(connection)

    with monkeypatch.context() as patch:
        patch.setattr(repository, "_pool", SimpleNamespace(connection=interrupted))
        with pytest.raises(RuntimeError, match="Interrupted before receipt commit"):
            money.write(
                user_id=user,
                scope=scope,
                request=request,
                idempotency_key="recover-claim",
            )
    assert (
        current_activities(money.accounts.list_accounts(user_id=user, scope=scope)) == []
    )
    with original_pool.connection() as connection:
        for table in [
            "financial_records",
            "financial_record_revisions",
            "financial_activity_groups",
            "financial_activity_memberships",
            "financial_activity_revisions",
            "financial_activity_receipts",
        ]:
            assert (
                connection.execute(
                    f"select count(*) from public.{table} where user_id=%s", (user,)
                ).fetchone()[0]
                == 0
            )
    receipt = money.write(
        user_id=user, scope=scope, request=request, idempotency_key="recover-claim"
    )
    assert receipt["activity"]["amount_minor"] == 85000
    assert not receipt["replayed"]
