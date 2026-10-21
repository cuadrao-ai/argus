"""Postgres evidence for goal owner serialization, atomic receipts and RLS."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from argus.domain.owner_scope import PERSONAL
from argus.domain.planning import storage
from argus.domain.planning.goal_schemas import (
    AllocationWrite,
    ContributionRecord,
    ContributionRelease,
)
from argus.domain.recording.errors import RecordingInputError, StaleVersion
from argus.domain.recording.money_schemas import MoneyRequest
from argus.domain.recording.schemas import account_response
from argus.domain.recording.service import FinancialAccountService

from tests import test_financial_accounts_postgres as shared
from tests.financial_accounts.test_goals import allocate, link, setup_goal, versions
from tests.financial_accounts.test_loop_commands import NOW
from tests.financial_accounts.test_personal_money import account, save

repository = shared.repository
users = shared.users
pytestmark = pytest.mark.skipif(
    not shared.DSN, reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured"
)


@pytest.fixture
def scene(repository, users):
    return FinancialAccountService(repository, lambda: NOW), users["owner"], None


def test_concurrent_different_goals_cannot_assign_same_capacity(scene):
    service, aid, a = setup_goal(scene)
    _, _, b = setup_goal(scene, aid)

    def assign(values):
        goal, amount = values
        try:
            return allocate(scene, service, [(goal, aid, amount)])
        except RecordingInputError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(assign, [(a, "700"), (b, "500")]))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert "goal_backing_shortfall" in results
    total = sum(int(service.get(scene[1], g["id"])["supported_minor"]) for g in [a, b])
    assert total in {50000, 70000}


def test_same_allocation_receipt_replays_concurrently_before_cas(scene):
    service, aid, g = setup_goal(scene)
    body = AllocationWrite.model_validate(
        {
            "changes": [
                {
                    "goal_id": g["id"],
                    "expected_version": 1,
                    "account_id": aid,
                    "amount": "600",
                }
            ],
            "expected_account_versions": versions(scene, aid),
        }
    )
    with ThreadPoolExecutor(max_workers=6) as workers:
        results = list(
            workers.map(
                lambda _: service.allocate(scene[1], body, "lost-response"), range(6)
            )
        )
    assert sum(not r["replayed"] for r in results) == 1
    assert all(r["goals"][0]["supported_minor"] == "60000" for r in results)
    assert service.get(scene[1], g["id"])["goal"]["version"] == 2
    save(scene, kind="expense", account_id=aid, amount="500")
    assert (
        service.allocate(scene[1], body, "lost-response")["goals"][0]["supported_minor"]
        == "60000"
    )
    assert service.get(scene[1], g["id"])["supported_minor"] == "50000"


@pytest.mark.parametrize(
    "first",
    [None, "allocate", "record"],
    ids=["concurrent", "allocation_first", "expense_first"],
)
def test_recording_and_allocation_share_owner_serialization(scene, first):
    service, aid, g = setup_goal(scene)

    def operation(kind):
        try:
            return (
                allocate(scene, service, [(g, aid, "900")])
                if kind == "allocate"
                else save(scene, kind="expense", account_id=aid, amount="200")
            )
        except StaleVersion:
            assert kind == "allocate"
            return "stale_version"
        except RecordingInputError as error:
            assert kind == "allocate" and error.code == "goal_backing_shortfall"
            return error.code

    operations = ["record", "allocate"] if first == "record" else ["allocate", "record"]
    if first is None:
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(operation, operations))
    else:
        results = list(map(operation, operations))
    outcomes = dict(zip(operations, results, strict=True))
    assert isinstance(outcomes["record"], dict)
    if first == "allocate":
        assert isinstance(outcomes["allocate"], dict)
    elif first == "record":
        assert outcomes["allocate"] == "goal_backing_shortfall"
    else:
        assert isinstance(outcomes["allocate"], dict) or outcomes["allocate"] in {
            "stale_version",
            "goal_backing_shortfall",
        }
    actual = service.get(scene[1], g["id"])
    expected = (
        ("90000", "80000") if isinstance(outcomes["allocate"], dict) else ("0", "0")
    )
    assert (actual["assigned_minor"], actual["supported_minor"]) == expected
    stored = scene[0].get(user_id=scene[1], account_id=aid, scope=PERSONAL)
    assert account_response(stored).balance.amount_minor == 80000
    assert len(stored.expenses) == 1 and stored.expenses[0].current.amount_minor == 20000


def confirmed(scene, service, g, source, aid):
    body = ContributionRecord(
        expected_version=g["version"],
        activity=MoneyRequest(
            kind="transfer",
            source_account_id=source,
            destination_account_id=aid,
            amount="200",
            occurred_at=NOW,
        ),
    )
    preview = service.preview(scene[1], g["id"], body)["money"]
    return body.model_copy(
        update={
            "activity": MoneyRequest.model_validate(
                preview["reviewed_request"]
            ).model_copy(update={"preview_token": preview["preview_token"]})
        }
    )


def test_contribution_atomic_rollback_exact_retry_and_release_persists(
    scene, repository, monkeypatch
):
    service, aid, g = setup_goal(scene)
    source = account(scene, amount="1000")
    body = confirmed(scene, service, g, source, aid)
    original = storage.persist

    def fail(connection, owner, money):
        original(connection, owner, money)
        raise RuntimeError("synthetic commit failure")

    monkeypatch.setattr(storage, "persist", fail)
    with pytest.raises(RuntimeError, match="synthetic commit failure"):
        service.record(scene[1], g["id"], body, "record")
    with repository._pool.connection() as connection:
        for table in ["financial_activity_groups", "financial_plan_links"]:
            assert (
                connection.execute(
                    f"select count(*) from public.{table} where user_id=%s", (scene[1],)
                ).fetchone()[0]
                == 0
            )
        assert (
            connection.execute(
                "select count(*) from public.financial_plan_receipts where user_id=%s and scope like 'goal.record:%%'",
                (scene[1],),
            ).fetchone()[0]
            == 0
        )
    monkeypatch.setattr(storage, "persist", original)
    with ThreadPoolExecutor(max_workers=4) as workers:
        results = list(
            workers.map(
                lambda _: service.record(scene[1], g["id"], body, "record"), range(4)
            )
        )
    assert sum(not r["replayed"] for r in results) == 1
    assert len({r["activity"]["activity_id"] for r in results}) == 1
    claim = results[0]["goal"]["contributions"][0]
    service.release(
        scene[1], g["id"], claim["id"], ContributionRelease(expected_version=2), "release"
    )
    with repository._pool.connection() as connection:
        assert (
            connection.execute(
                "select count(*) from public.financial_plan_links where user_id=%s",
                (scene[1],),
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "select count(*) from public.financial_activity_groups where user_id=%s",
                (scene[1],),
            ).fetchone()[0]
            == 1
        )
    assert service.get(scene[1], g["id"])["supported_minor"] == "0"


def test_new_goal_rls_and_owner_qualified_claim_foreign_keys(scene, repository, users):
    from psycopg.errors import ForeignKeyViolation, InsufficientPrivilege
    from psycopg.types.json import Jsonb

    service, aid, g = setup_goal(scene)
    source = account(scene, amount="1000")
    entry = save(
        scene,
        kind="transfer",
        source_account_id=source,
        destination_account_id=aid,
        amount="200",
    )["activity"]
    linked = link(scene, service, g, entry)
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
                for table in ["financial_goals", "financial_plan_links"]:
                    assert (
                        connection.execute(
                            f"select count(*) from public.{table}"
                        ).fetchone()[0]
                        == count
                    )
            connection.execute("reset role")
        with pytest.raises(InsufficientPrivilege), connection.transaction():
            shared._set_authenticated_claims(
                connection, user_id=users["owner"], is_anonymous=False
            )
            connection.execute(
                "update public.financial_goals set body=body where user_id=%s",
                (users["owner"],),
            )
        connection.execute("reset role")
        other_scene = (scene[0], users["other"], None)
        _, other_dest, other_goal = setup_goal(other_scene)
        other_source = account(other_scene, amount="1000")
        other_entry = save(
            other_scene,
            kind="transfer",
            source_account_id=other_source,
            destination_account_id=other_dest,
            amount="100",
        )["activity"]
        for goal_id, activity_id in [
            (g["id"], other_entry["activity_id"]),
            (other_goal["id"], entry["activity_id"]),
        ]:
            with pytest.raises(ForeignKeyViolation), connection.transaction():
                connection.execute(
                    "insert into public.financial_plan_links(user_id,claim_id,goal_id,activity_id,activity_revision,snapshot,attribution) values(%s,%s,%s,%s,1,%s,%s)",
                    (
                        users["other"],
                        str(uuid4()),
                        goal_id,
                        activity_id,
                        Jsonb({}),
                        Jsonb({"counting": True}),
                    ),
                )
    assert linked["goal"]["supported_minor"] == "20000"
