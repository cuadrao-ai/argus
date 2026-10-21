"""Durability, concurrent admission and database ownership for financial records."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.errors import StaleVersion
from argus.domain.recording.loop_schemas import ActivityRequest
from argus.domain.recording.schemas import CreateFinancialAccountRequest
from argus.domain.recording.service import FinancialAccountService

from tests import test_financial_accounts_postgres as shared

DSN = shared.DSN
repository = shared.repository
users = shared.users
_set_authenticated_claims = shared._set_authenticated_claims


pytestmark = pytest.mark.skipif(
    not DSN, reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured"
)


def create(repository, owner):
    now = datetime.now(timezone.utc)
    service = FinancialAccountService(repository)
    account = service.create(
        user_id=owner,
        idempotency_key=str(uuid4()),
        request=CreateFinancialAccountRequest(
            type="checking", currency="USD", amount="1000", as_of=now - timedelta(days=10)
        ),
        scope=PERSONAL,
    ).stored
    request = ActivityRequest(
        expected_version=1,
        amount="10",
        occurred_at=now - timedelta(days=10),
        coverage=[{"observation_id": account.opening.id, "included": False}],
    )
    preview = service.loop.preview_activity(
        user_id=owner, account_id=account.account.id, request=request
    )
    return (
        service,
        account,
        request.model_copy(update={"preview_token": preview["preview_token"]}),
    )


def test_concurrent_response_loss_retry_writes_one_revision_and_receipt(
    repository, users
):
    service, account, request = create(repository, users["owner"])

    def submit(_):
        return service.loop.write_activity(
            user_id=users["owner"],
            account_id=account.account.id,
            request=request,
            idempotency_key="same",
        )

    with ThreadPoolExecutor(max_workers=6) as threads:
        results = list(threads.map(submit, range(6)))
    assert sum(not r.replayed for r in results) == 1
    assert len({r.record_id for r in results}) == 1
    reopened = repository.get_account(
        user_id=users["owner"], account_id=account.account.id, scope=PERSONAL
    )
    assert reopened.account.version == 2 and len(reopened.expenses) == 1
    with repository._pool.connection() as connection:
        assert (
            connection.execute(
                "select count(*) from public.financial_operation_receipts where account_id=%s",
                (account.account.id,),
            ).fetchone()[0]
            == 1
        )


def test_concurrent_distinct_writes_reject_stale_preview_without_partial_records(
    repository, users
):
    service, account, request = create(repository, users["owner"])

    def submit(key):
        try:
            return service.loop.write_activity(
                user_id=users["owner"],
                account_id=account.account.id,
                request=request,
                idempotency_key=key,
            )
        except StaleVersion:
            return None

    with ThreadPoolExecutor(max_workers=2) as threads:
        results = list(threads.map(submit, ("a", "b")))
    assert sum(r is not None for r in results) == 1
    reopened = repository.get_account(
        user_id=users["owner"], account_id=account.account.id, scope=PERSONAL
    )
    assert reopened.account.version == 2 and len(reopened.expenses) == 1


def test_new_tables_enforce_same_account_foreign_keys_and_owner_only_reads(
    repository, users
):
    import psycopg

    service, account, request = create(repository, users["owner"])
    expense = service.loop.write_activity(
        user_id=users["owner"],
        account_id=account.account.id,
        request=request,
        idempotency_key="first",
    )
    other_account = service.create(
        user_id=users["owner"],
        idempotency_key="another",
        request=CreateFinancialAccountRequest(type="cash", currency="USD", amount="1"),
        scope=PERSONAL,
    ).stored
    with repository._pool.connection() as connection:
        with pytest.raises(psycopg.errors.ForeignKeyViolation), connection.transaction():
            connection.execute(
                "insert into public.financial_observation_coverage(account_id,user_id,observation_id,observation_revision,activity_id,activity_revision,included) values(%s,%s,%s,1,%s,1,true)",
                (
                    account.account.id,
                    users["owner"],
                    other_account.opening.id,
                    expense.record_id,
                ),
            )
        for label, anonymous in (("owner", False), ("other", False), ("guest", True)):
            with connection.transaction():
                _set_authenticated_claims(
                    connection, user_id=users[label], is_anonymous=anonymous
                )
                with (
                    pytest.raises(psycopg.errors.InsufficientPrivilege),
                    connection.transaction(),
                ):
                    connection.execute(
                        "select * from public.financial_operation_receipts"
                    )
                assert connection.execute(
                    "select count(*) from public.financial_observation_coverage"
                ).fetchone()[0] == (1 if label == "owner" else 0)
                with (
                    pytest.raises(psycopg.errors.InsufficientPrivilege),
                    connection.transaction(),
                ):
                    connection.execute(
                        "insert into public.financial_observation_coverage(account_id,user_id,observation_id,observation_revision,activity_id,activity_revision,included) values(%s,%s,%s,1,%s,1,true)",
                        (
                            account.account.id,
                            users["owner"],
                            account.opening.id,
                            expense.record_id,
                        ),
                    )


def test_postgres_hydration_normalizes_uuid_before_loading_opening(repository, users):
    _, account, _ = create(repository, users["owner"])
    loaded = repository.get_account(
        user_id=users["owner"], account_id=account.account.id.upper(), scope=PERSONAL
    )
    assert loaded.opening is not None
    assert loaded.opening.current.amount_minor == 100000
