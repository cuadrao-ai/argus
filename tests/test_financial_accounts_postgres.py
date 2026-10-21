"""Real-Postgres proof for the financial accounts first slice.

Set ``ARGUS_DISPOSABLE_DATABASE_URL`` only to an isolated Supabase Postgres
database with every checked-in migration applied; never point it at shared or
production data. Proves what the in-memory twin cannot: the migration on top of
the integration schema, concurrent duplicate creates through the SQL function,
compare-and-set under lock, owner-only registered-only row-level security, and
the absence of any client write path.
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.errors import (
    AccountNotFound,
    IdempotencyConflict,
    RegisteredAccountRequired,
    StaleVersion,
)
from argus.domain.recording.records import OpeningWrite
from argus.domain.recording.repository import NewAccount

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DSN,
    reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured",
)

psycopg = pytest.importorskip("psycopg")
psycopg_pool = pytest.importorskip("psycopg_pool")

NOW = datetime(2026, 9, 1, 13, 0, tzinfo=timezone.utc)
CHECKING = NewAccount(
    type="checking", currency="DOP", nickname="Nomina", ownership_share_bps=10_000
)


def _opening(amount_minor: int, as_of: datetime = NOW) -> OpeningWrite:
    return OpeningWrite(
        amount_minor=amount_minor,
        as_of=as_of,
        time_zone="America/Santo_Domingo",
        reason=None,
    )


def _create_users(connection, *labels: tuple[str, bool]) -> dict[str, str]:  # noqa: ANN001
    ids = {}
    with connection.cursor() as cursor:
        for label, anonymous in labels:
            user_id = str(uuid4())
            email = None if anonymous else f"fin-{label}-{user_id}@example.test"
            cursor.execute(
                "insert into auth.users (id, email, is_anonymous) values (%s, %s, %s)",
                (user_id, email, anonymous),
            )
            cursor.execute(
                "insert into public.profiles (id, email, username) values (%s, %s, %s)",
                (user_id, email, f"fin-{label}-{user_id[:8]}"),
            )
            ids[label] = user_id
    connection.commit()
    return ids


def _delete_users(connection, ids: dict[str, str]) -> None:  # noqa: ANN001
    from tests.household.shared_cleanup import cleanup

    cleanup(connection, list(ids.values()))
    with connection.cursor() as cursor:
        cursor.execute("delete from auth.users where id = any(%s)", (list(ids.values()),))
    connection.commit()


@pytest.fixture
def users():
    with psycopg.connect(DSN) as connection:
        ids = _create_users(
            connection, ("owner", False), ("other", False), ("guest", True)
        )
        try:
            yield ids
        finally:
            _delete_users(connection, ids)


@pytest.fixture
def repository():
    from argus.domain.recording.postgres_repository import (
        PostgresFinancialAccountRepository,
    )

    pool = psycopg_pool.ConnectionPool(DSN, min_size=0, max_size=8, open=True)
    try:
        yield PostgresFinancialAccountRepository(pool)
    finally:
        pool.close()


def _set_authenticated_claims(cursor, *, user_id: str, is_anonymous: bool) -> None:  # noqa: ANN001
    cursor.execute("set local role authenticated")
    cursor.execute(
        "select set_config('request.jwt.claims', %s, true)",
        (
            json.dumps(
                {"sub": user_id, "role": "authenticated", "is_anonymous": is_anonymous}
            ),
        ),
    )


def test_migration_objects_exist_on_the_integration_schema() -> None:
    with psycopg.connect(DSN) as connection:
        tables = connection.execute(
            "select tablename from pg_tables where schemaname = 'public'"
            " and tablename like 'financial_%' order by 1"
        ).fetchall()
        assert {
            "financial_account_idempotency",
            "financial_accounts",
            "financial_activity_groups",
            "financial_activity_memberships",
            "financial_activity_receipts",
            "financial_activity_revisions",
            "financial_observation_coverage",
            "financial_operation_receipts",
            "financial_record_revisions",
            "financial_records",
        } <= {row[0] for row in tables}
        rls = connection.execute(
            "select relname, relrowsecurity from pg_class"
            " where relname like 'financial_%' and relkind = 'r' order by 1"
        ).fetchall()
        assert all(enabled for _, enabled in rls), rls
        functions = connection.execute(
            "select proname, prosecdef from pg_proc"
            " where proname in ('create_financial_account', 'write_financial_opening')"
        ).fetchall()
        assert sorted(functions) == [
            ("create_financial_account", True),
            ("write_financial_opening", True),
        ]


def test_create_reopen_replay_and_conflict(repository, users) -> None:  # noqa: ANN001
    owner = users["owner"]
    first = repository.create(
        user_id=owner,
        idempotency_key="create-nomina",
        identity_hash="sha256:a",
        account=CHECKING,
        opening=_opening(1_250_000),
        scope=PERSONAL,
    )
    assert first.created is True
    assert first.stored.account.version == 1
    assert first.stored.opening is not None
    assert first.stored.opening.current.amount_minor == 1_250_000
    assert first.stored.opening.current.as_of == NOW
    assert first.stored.opening.current.recorded_by == owner

    reopened = repository.get_account(
        user_id=owner, account_id=first.stored.account.id, scope=PERSONAL
    )
    assert reopened == first.stored

    again = repository.create(
        user_id=owner,
        idempotency_key="create-nomina",
        identity_hash="sha256:a",
        account=CHECKING,
        opening=_opening(1_250_000),
        scope=PERSONAL,
    )
    assert again.created is False
    assert again.stored == first.stored

    with pytest.raises(IdempotencyConflict):
        repository.create(
            user_id=owner,
            idempotency_key="create-nomina",
            identity_hash="sha256:b",
            account=CHECKING,
            opening=_opening(2_000_000),
            scope=PERSONAL,
        )
    assert [
        item.account.id
        for item in repository.list_accounts(user_id=owner, scope=PERSONAL)
    ] == [first.stored.account.id]

    unknown = repository.create(
        user_id=owner,
        idempotency_key="create-wallet",
        identity_hash="sha256:c",
        account=NewAccount("cash", "USD", None, 10_000),
        opening=None,
        scope=PERSONAL,
    )
    assert unknown.stored.opening is None
    assert len(repository.list_accounts(user_id=owner, scope=PERSONAL)) == 2


def test_concurrent_duplicate_creates_make_one_account(repository, users) -> None:  # noqa: ANN001
    owner = users["owner"]

    def attempt(_: int):
        return repository.create(
            user_id=owner,
            idempotency_key="race-key",
            identity_hash="sha256:race",
            account=CHECKING,
            opening=_opening(100),
            scope=PERSONAL,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(8)))
    assert sum(result.created for result in results) == 1
    assert len({result.stored.account.id for result in results}) == 1
    assert len(repository.list_accounts(user_id=owner, scope=PERSONAL)) == 1
    with psycopg.connect(DSN) as connection:
        count = connection.execute(
            "select count(*) from public.financial_accounts where user_id = %s", (owner,)
        ).fetchone()[0]
        assert count == 1


def test_edit_and_opening_compare_and_set_write_nothing_when_stale(
    repository,
    users,  # noqa: ANN001
) -> None:
    owner = users["owner"]
    created = repository.create(
        user_id=owner,
        idempotency_key="cas",
        identity_hash="sha256:cas",
        account=CHECKING,
        opening=_opening(1_250_000),
        scope=PERSONAL,
    ).stored
    account_id = created.account.id

    edited = repository.update_account(
        user_id=owner,
        account_id=account_id,
        expected_version=1,
        changes={"nickname": "Otra"},
        scope=PERSONAL,
    )
    assert (edited.account.nickname, edited.account.version) == ("Otra", 2)
    with pytest.raises(StaleVersion):
        repository.update_account(
            user_id=owner,
            account_id=account_id,
            expected_version=1,
            changes={"nickname": "x"},
            scope=PERSONAL,
        )
    assert (
        repository.get_account(user_id=owner, account_id=account_id, scope=PERSONAL)
        == edited
    )

    corrected = repository.write_opening(
        user_id=owner,
        account_id=account_id,
        expected_revision=1,
        expected_version=2,
        write=OpeningWrite(1_200_000, NOW, "America/Santo_Domingo", "typo"),
        scope=PERSONAL,
    )
    assert corrected.account.version == 3
    assert [
        (r.revision, r.amount_minor, r.reason) for r in corrected.opening.revisions
    ] == [
        (1, 1_250_000, None),
        (2, 1_200_000, "typo"),
    ]
    with pytest.raises(StaleVersion):
        repository.write_opening(
            user_id=owner,
            account_id=account_id,
            expected_revision=1,
            expected_version=3,
            write=OpeningWrite(1, NOW, "America/Santo_Domingo", "late"),
            scope=PERSONAL,
        )
    with pytest.raises(StaleVersion):
        repository.write_opening(
            user_id=owner,
            account_id=account_id,
            expected_revision=None,
            expected_version=3,
            write=OpeningWrite(1, NOW, "America/Santo_Domingo", None),
            scope=PERSONAL,
        )
    assert (
        repository.get_account(user_id=owner, account_id=account_id, scope=PERSONAL)
        == corrected
    )

    unknown = repository.create(
        user_id=owner,
        idempotency_key="cas-unknown",
        identity_hash="sha256:u",
        account=NewAccount("cash", "DOP", None, 10_000),
        opening=None,
        scope=PERSONAL,
    ).stored
    with pytest.raises(StaleVersion):
        repository.write_opening(
            user_id=owner,
            account_id=unknown.account.id,
            expected_revision=1,
            expected_version=1,
            write=OpeningWrite(5, NOW, "America/Santo_Domingo", "r"),
            scope=PERSONAL,
        )
    first_opening = repository.write_opening(
        user_id=owner,
        account_id=unknown.account.id,
        expected_revision=None,
        expected_version=1,
        write=OpeningWrite(525, NOW, "America/Santo_Domingo", None),
        scope=PERSONAL,
    )
    assert first_opening.opening.current.revision == 1
    assert first_opening.account.version == 2

    # An opening scaled and signed under one read of the account must not land
    # after the account moved (a concurrent currency or type edit on an empty
    # account), even when the revision basis still matches.
    moved = repository.create(
        user_id=owner,
        idempotency_key="cas-moved",
        identity_hash="sha256:m",
        account=NewAccount("cash", "USD", None, 10_000),
        opening=None,
        scope=PERSONAL,
    ).stored
    repository.update_account(
        user_id=owner,
        account_id=moved.account.id,
        expected_version=1,
        changes={"currency": "JPY"},
        scope=PERSONAL,
    )
    with pytest.raises(StaleVersion):
        repository.write_opening(
            user_id=owner,
            account_id=moved.account.id,
            expected_revision=None,
            expected_version=1,
            write=OpeningWrite(123, NOW, "America/Santo_Domingo", None),
            scope=PERSONAL,
        )
    assert (
        repository.get_account(
            user_id=owner, account_id=moved.account.id, scope=PERSONAL
        ).opening
        is None
    )


def test_another_user_cannot_reach_the_account_through_the_repository(
    repository,
    users,  # noqa: ANN001
) -> None:
    owner, other = users["owner"], users["other"]
    account_id = repository.create(
        user_id=owner,
        idempotency_key="iso",
        identity_hash="sha256:iso",
        account=CHECKING,
        opening=_opening(100),
        scope=PERSONAL,
    ).stored.account.id
    assert (
        repository.get_account(user_id=other, account_id=account_id, scope=PERSONAL)
        is None
    )
    assert repository.list_accounts(user_id=other, scope=PERSONAL) == []
    with pytest.raises(AccountNotFound):
        repository.update_account(
            user_id=other,
            account_id=account_id,
            expected_version=1,
            changes={"nickname": "x"},
            scope=PERSONAL,
        )
    with pytest.raises(AccountNotFound):
        repository.write_opening(
            user_id=other,
            account_id=account_id,
            expected_revision=1,
            expected_version=1,
            write=OpeningWrite(0, NOW, "America/Santo_Domingo", "drain"),
            scope=PERSONAL,
        )
    assert (
        repository.get_account(
            user_id=owner, account_id=account_id, scope=PERSONAL
        ).account.version
        == 1
    )


def test_storage_refuses_an_anonymous_owner(repository, users) -> None:  # noqa: ANN001
    guest = users["guest"]
    with pytest.raises(RegisteredAccountRequired):
        repository.create(
            user_id=guest,
            idempotency_key="guest",
            identity_hash="sha256:g",
            account=CHECKING,
            opening=None,
            scope=PERSONAL,
        )
    assert repository.list_accounts(user_id=guest, scope=PERSONAL) == []


def test_rls_reads_are_owner_only_and_registered_only_and_writes_have_no_client_path(
    repository,
    users,  # noqa: ANN001
) -> None:
    owner, other = users["owner"], users["other"]
    account_id = repository.create(
        user_id=owner,
        idempotency_key="rls",
        identity_hash="sha256:rls",
        account=CHECKING,
        opening=_opening(100),
        scope=PERSONAL,
    ).stored.account.id
    layers = (
        "select count(*) from public.financial_accounts where user_id = %s",
        "select count(*) from public.financial_records where user_id = %s",
        "select count(*) from public.financial_record_revisions where user_id = %s",
    )

    def visible(connection, *, as_user: str, is_anonymous: bool) -> list[int]:  # noqa: ANN001
        with connection.transaction(), connection.cursor() as cursor:
            _set_authenticated_claims(cursor, user_id=as_user, is_anonymous=is_anonymous)
            counts = []
            for statement in layers:
                cursor.execute(statement, (owner,))
                counts.append(cursor.fetchone()[0])
            return counts

    with psycopg.connect(DSN) as connection:
        assert visible(connection, as_user=owner, is_anonymous=False) == [1, 1, 1]
        assert visible(connection, as_user=other, is_anonymous=False) == [0, 0, 0]
        # Same id, anonymous claim: a guest reads nothing even about "itself".
        assert visible(connection, as_user=owner, is_anonymous=True) == [0, 0, 0]

        client_writes = (
            (
                "update public.financial_accounts set nickname = 'taken' where id = %s",
                (account_id,),
            ),
            ("delete from public.financial_accounts where id = %s", (account_id,)),
            (
                "insert into public.financial_accounts (user_id, type, currency)"
                " values (%s, 'cash', 'DOP')",
                (owner,),
            ),
            (
                "insert into public.financial_record_revisions"
                " (record_id, user_id, revision, amount_minor, as_of, as_of_zone, recorded_by)"
                " select id, user_id, 2, 0, now(), 'UTC', user_id"
                " from public.financial_records where account_id = %s",
                (account_id,),
            ),
            (
                "select public.create_financial_account(%s, 'k', 'h', 'cash', 'DOP', null, 10000, null, null, null)",
                (owner,),
            ),
            (
                "select public.write_financial_opening(%s, %s, 1, 1, 0, now(), 'UTC', 'drain')",
                (owner, account_id),
            ),
        )
        for statement, params in client_writes:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with connection.transaction(), connection.cursor() as cursor:
                    _set_authenticated_claims(cursor, user_id=owner, is_anonymous=False)
                    cursor.execute(statement, params)

    unchanged = repository.get_account(
        user_id=owner, account_id=account_id, scope=PERSONAL
    )
    assert unchanged.account.nickname == "Nomina"
    assert unchanged.account.version == 1
    assert unchanged.opening.current.revision == 1
