"""Required database proof for Plan atomicity, races and owner isolation."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from argus.domain.owner_scope import PERSONAL
from argus.domain.planning import storage
from argus.domain.planning.schemas import LinkWrite
from argus.domain.recording.errors import RecordingInputError
from argus.domain.recording.service import FinancialAccountService

from tests import test_financial_accounts_postgres as shared
from tests.financial_accounts.test_loop_commands import NOW
from tests.financial_accounts.test_personal_money import save
from tests.financial_accounts.test_plan import confirmed, setup_plan

repository = shared.repository
users = shared.users
pytestmark = pytest.mark.skipif(
    not shared.DSN, reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured"
)


@pytest.fixture
def scene(repository, users):
    return FinancialAccountService(repository, lambda: NOW), users["owner"], None


def test_response_loss_concurrent_retries_write_one_activity_and_link(scene, repository):
    planner, aid, _, occurrence = setup_plan(scene)
    body = confirmed(planner, scene[1], occurrence)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(
            pool.map(
                lambda _: planner.fulfill(scene[1], occurrence["id"], body, "retry"),
                range(6),
            )
        )
    assert sum(not r["replayed"] for r in results) == 1
    assert len({r["activity"]["activity_id"] for r in results}) == 1
    with repository._pool.connection() as connection:
        assert (
            connection.execute(
                "select count(*) from public.financial_plan_links where user_id=%s",
                (scene[1],),
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "select count(*) from public.financial_activity_groups where user_id=%s",
                (scene[1],),
            ).fetchone()[0]
            == 1
        )
    assert planner.read(scene[1])["currencies"][0]["starting_minor"] == "5000"


def test_different_keys_cannot_pay_the_same_occurrence_twice(scene):
    planner, _, _, occurrence = setup_plan(scene)
    body = confirmed(planner, scene[1], occurrence)

    def pay(key):
        try:
            return planner.fulfill(scene[1], occurrence["id"], body, key)
        except RecordingInputError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(pay, ["first", "second"]))
    assert sum(isinstance(r, dict) for r in results) == 1
    assert "occurrence_already_linked" in results


def test_two_occurrences_cannot_link_the_same_activity_concurrently(scene):
    planner, aid, _, first = setup_plan(scene)
    second = setup_plan(scene, aid=aid)[3]
    actual = save(scene, kind="expense", account_id=aid, amount="30")["activity"]
    body = LinkWrite(
        expected_version=1, activity_id=actual["activity_id"], activity_revision=1
    )

    def link(row):
        try:
            return planner.link(scene[1], row["id"], body, str(uuid4()))
        except RecordingInputError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(link, [first, second]))
    assert sum(isinstance(r, dict) for r in results) == 1
    assert "activity_already_linked" in results


def test_link_failure_rolls_back_actual_record_versions_and_receipt(
    scene, repository, monkeypatch
):
    planner, aid, _, occurrence = setup_plan(scene)
    body = confirmed(planner, scene[1], occurrence)
    original = storage.persist

    def fail_after_activity(connection, user_id, money):
        original(connection, user_id, money)
        raise RuntimeError("synthetic link failure")

    monkeypatch.setattr(storage, "persist", fail_after_activity)
    with pytest.raises(RuntimeError, match="synthetic link failure"):
        planner.fulfill(scene[1], occurrence["id"], body, "rollback")
    with repository._pool.connection() as connection:
        for table in ("financial_activity_groups", "financial_plan_links"):
            assert (
                connection.execute(
                    f"select count(*) from public.{table} where user_id=%s", (scene[1],)
                ).fetchone()[0]
                == 0
            )
        assert (
            connection.execute(
                "select count(*) from public.financial_plan_receipts where user_id=%s and scope like 'fulfill:%%'",
                (scene[1],),
            ).fetchone()[0]
            == 0
        )
    assert (
        scene[0].get(user_id=scene[1], account_id=aid, scope=PERSONAL).account.version
        == 1
    )
    monkeypatch.setattr(storage, "persist", original)
    assert not planner.fulfill(scene[1], occurrence["id"], body, "rollback")["replayed"]


def test_rls_no_client_writes_and_owner_qualified_activity_fk(scene, repository, users):
    from psycopg.errors import ForeignKeyViolation, InsufficientPrivilege

    planner, _, expectation, occurrence = setup_plan(scene)
    actual = planner.fulfill(
        scene[1], occurrence["id"], confirmed(planner, scene[1], occurrence), "pay"
    )["activity"]
    with repository._pool.connection() as connection:
        for owner, guest, expected in [
            (users["owner"], False, 1),
            (users["other"], False, 0),
            (users["owner"], True, 0),
        ]:
            with connection.transaction():
                shared._set_authenticated_claims(
                    connection, user_id=owner, is_anonymous=guest
                )
                for table in (
                    "financial_expectations",
                    "financial_plan_selections",
                    "financial_plan_links",
                ):
                    assert (
                        connection.execute(
                            f"select count(*) from public.{table}"
                        ).fetchone()[0]
                        == expected
                    )
            connection.execute("reset role")
        with pytest.raises(InsufficientPrivilege), connection.transaction():
            shared._set_authenticated_claims(
                connection, user_id=users["owner"], is_anonymous=False
            )
            connection.execute(
                "update public.financial_expectations set body=body where user_id=%s",
                (users["owner"],),
            )
        connection.execute("reset role")
        with pytest.raises(ForeignKeyViolation), connection.transaction():
            connection.execute(
                "insert into public.financial_plan_links(user_id,occurrence_id,expectation_id,activity_id,activity_revision,snapshot) values(%s,%s,%s,%s,%s,'{}')",
                (
                    users["other"],
                    str(uuid4()),
                    expectation["id"],
                    actual["activity_id"],
                    1,
                ),
            )
