"""Canonical residual storage preserves Personal goals and owner isolation."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import pytest
from argus.domain.owner_scope import PERSONAL
from argus.domain.planning import storage
from argus.domain.planning.goal_schemas import AllocationWrite, ContributionRecord
from argus.domain.recording.errors import (
    AccountNotFound,
    IdempotencyConflict,
    StaleVersion,
)
from argus.domain.recording.money_schemas import MoneyRequest
from argus.domain.recording.service import FinancialAccountService
from psycopg.errors import (
    CheckViolation,
    ForeignKeyViolation,
    InsufficientPrivilege,
    NotNullViolation,
    NumericValueOutOfRange,
    UniqueViolation,
)
from psycopg.types.json import Jsonb

from tests import test_financial_accounts_postgres as shared
from tests.financial_accounts.test_goals import allocate, link, setup_goal, versions
from tests.financial_accounts.test_loop_commands import NOW
from tests.financial_accounts.test_personal_money import account, save

repository = shared.repository
users = shared.users
pytestmark = pytest.mark.skipif(
    not shared.DSN, reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured"
)
MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "supabase/migrations/20261001190000_goal_residual_allocations.sql"
)


@pytest.fixture
def scene(repository, users):
    return FinancialAccountService(repository, lambda: NOW), users["owner"], None


def test_residual_rows_reopen_with_exact_amounts_and_allocation_order(scene, repository):
    service, destination, goal = setup_goal(scene)
    extra = account(scene, amount="200")
    result = allocate(
        scene, service, [(goal, extra, "12.34"), (goal, destination, "56.78")]
    )
    expected = [
        {"account_id": extra, "unlinked_minor": 1234},
        {"account_id": destination, "unlinked_minor": 5678},
    ]
    reopened = service.get(scene[1], goal["id"])
    assert reopened["goal"]["allocations"] == expected
    assert reopened["supported_minor"] == "6912"
    assert result["goals"][0]["goal"]["allocations"] == expected
    with repository._pool.connection() as connection:
        body = connection.execute(
            "select body from public.financial_goals where id=%s", (goal["id"],)
        ).fetchone()[0]
        assert "allocations" not in body
        rows = connection.execute(
            "select account_id,unlinked_minor,ordinal from public.financial_goal_allocations "
            "where goal_id=%s order by ordinal",
            (goal["id"],),
        ).fetchall()
        assert [(str(aid), amount, ordinal) for aid, amount, ordinal in rows] == [
            (extra, 1234, 0),
            (destination, 5678, 1),
        ]


@contextmanager
def legacy_schema(repository):
    """Rehearse the cutover without retaining any schema or fixture changes."""
    with repository._pool.connection() as connection:
        with connection.transaction(force_rollback=True):
            connection.execute("set local lock_timeout='5s'")
            # Reconstruct the pre-cutover schema only within this rollback rehearsal.
            # The later immutable-history trigger must not observe synthetic legacy bodies.
            connection.execute(
                "alter table public.financial_goals disable trigger goal_revision"
            )
            connection.execute(
                "alter table public.financial_goals "
                "drop constraint financial_goals_no_json_allocations"
            )
            connection.execute(
                "update public.financial_goals g set body=jsonb_set(body,'{allocations}', "
                "coalesce((select jsonb_agg(jsonb_build_object('account_id',a.account_id, "
                "'unlinked_minor',a.unlinked_minor) order by a.ordinal) "
                "from public.financial_goal_allocations a where a.goal_id=g.id "
                "and a.goal_owner_id=g.user_id and a.account_owner_id=g.user_id),'[]'))"
            )
            connection.execute("drop table public.financial_goal_allocations")
            yield connection


def migration_body():
    header, begin, body = MIGRATION.read_text().partition("\nbegin;\n")
    assert begin and all(
        not line.strip() or line.lstrip().startswith("--") for line in header.splitlines()
    )
    body, commit, footer = body.rpartition("\ncommit;")
    assert commit and not footer.strip()
    return body


def legacy_allocations(connection, gid, allocations):
    connection.execute(
        "update public.financial_goals set body=jsonb_set(body,'{allocations}',%s) "
        "where id=%s",
        (Jsonb(allocations), gid),
    )


def test_backfill_preserves_explicit_zero_large_integer_and_list_order(scene, repository):
    _, destination, goal = setup_goal(scene)
    _, _, empty_goal = setup_goal(scene, destination)
    extra = account(scene)
    expected = [
        {"account_id": extra, "unlinked_minor": 9223372036854775807},
        {"account_id": destination, "unlinked_minor": 0},
    ]
    with legacy_schema(repository) as connection:
        legacy_allocations(connection, goal["id"], expected)
        connection.execute(migration_body(), prepare=False)
        goals = storage.load(connection, scene[1])["goals"]
        current = goals[goal["id"]]
        assert current["allocations"] == expected
        assert current["version"] == goal["version"]
        assert goals[empty_goal["id"]]["allocations"] == []
        assert (
            connection.execute(
                "select count(*) from public.financial_goal_allocations where goal_owner_id=%s",
                (scene[1],),
            ).fetchone()[0]
            == 2
        )
        assert not connection.execute(
            "select body ? 'allocations' from public.financial_goals where id=%s",
            (goal["id"],),
        ).fetchone()[0]


@pytest.mark.parametrize(
    "amount,error",
    [
        (None, CheckViolation),
        (1.5, CheckViolation),
        ("137", CheckViolation),
        (-1, CheckViolation),
        (9223372036854775808, NumericValueOutOfRange),
    ],
)
def test_invalid_backfill_rolls_back_without_replacing_amounts(
    scene, repository, amount, error
):
    _, destination, goal = setup_goal(scene)
    original = [{"account_id": destination, "unlinked_minor": amount}]
    with legacy_schema(repository) as connection:
        legacy_allocations(connection, goal["id"], original)
        with pytest.raises(error), connection.transaction():
            connection.execute(migration_body(), prepare=False)
        assert (
            connection.execute(
                "select body->'allocations' from public.financial_goals where id=%s",
                (goal["id"],),
            ).fetchone()[0]
            == original
        )
        assert (
            connection.execute(
                "select to_regclass('public.financial_goal_allocations')"
            ).fetchone()[0]
            is None
        )


def test_backfill_rejects_foreign_private_account_instead_of_relabeling_owner(
    scene, repository, users
):
    _, _, goal = setup_goal(scene)
    foreign = account((scene[0], users["other"], None))
    with legacy_schema(repository) as connection:
        legacy_allocations(
            connection, goal["id"], [{"account_id": foreign, "unlinked_minor": 137}]
        )
        with pytest.raises(ForeignKeyViolation), connection.transaction():
            connection.execute(migration_body(), prepare=False)


@pytest.mark.parametrize("shape", ["missing", None, {}, "not an array"])
def test_missing_null_or_nonarray_legacy_allocations_cannot_become_empty(
    scene, repository, shape
):
    _, _, goal = setup_goal(scene)
    with legacy_schema(repository) as connection:
        if shape == "missing":
            connection.execute(
                "update public.financial_goals set body=body-'allocations' where id=%s",
                (goal["id"],),
            )
        else:
            legacy_allocations(connection, goal["id"], shape)
        original = connection.execute(
            "select body from public.financial_goals where id=%s", (goal["id"],)
        ).fetchone()[0]
        with pytest.raises(CheckViolation), connection.transaction():
            connection.execute(migration_body(), prepare=False)
        assert (
            connection.execute(
                "select body from public.financial_goals where id=%s", (goal["id"],)
            ).fetchone()[0]
            == original
        )
        assert (
            connection.execute(
                "select to_regclass('public.financial_goal_allocations')"
            ).fetchone()[0]
            is None
        )


def test_duplicate_legacy_account_references_are_rejected_without_summing(
    scene, repository
):
    _, destination, goal = setup_goal(scene)
    original = [
        {"account_id": destination, "unlinked_minor": 137},
        {"account_id": destination, "unlinked_minor": 263},
    ]
    with legacy_schema(repository) as connection:
        legacy_allocations(connection, goal["id"], original)
        with pytest.raises(UniqueViolation), connection.transaction():
            connection.execute(migration_body(), prepare=False)
        assert (
            connection.execute(
                "select body->'allocations' from public.financial_goals where id=%s",
                (goal["id"],),
            ).fetchone()[0]
            == original
        )


def test_fully_included_contribution_keeps_explicit_zero_residual_without_double_credit(
    scene, repository
):
    service, destination, goal = setup_goal(scene)
    source = account(scene, amount="1000")
    actual = save(
        scene,
        kind="transfer",
        source_account_id=source,
        destination_account_id=destination,
        amount="200",
    )["activity"]
    allocate(scene, service, [(goal, destination, "200")])
    current = service.get(scene[1], goal["id"])["goal"]
    linked = link(scene, service, current, actual, "included", key="included-zero")
    assert linked["goal"]["supported_minor"] == "20000"
    assert linked["goal"]["goal"]["allocations"] == [
        {"account_id": destination, "unlinked_minor": 0}
    ]
    assert link(scene, service, current, actual, "included", key="included-zero")[
        "replayed"
    ]
    with repository._pool.connection() as connection:
        assert connection.execute(
            "select unlinked_minor from public.financial_goal_allocations where goal_id=%s",
            (goal["id"],),
        ).fetchall() == [(0,)]


@pytest.mark.parametrize(
    "change,error",
    [
        ("wrong_goal_owner", ForeignKeyViolation),
        ("wrong_account_owner", ForeignKeyViolation),
        ("foreign_account", CheckViolation),
        ("negative", CheckViolation),
        ("unknown", NotNullViolation),
        ("duplicate_account", UniqueViolation),
    ],
)
def test_allocation_rows_enforce_true_owners_and_exact_nonnegative_amounts(
    scene, repository, users, change, error
):
    service, destination, goal = setup_goal(scene)
    foreign = account((scene[0], users["other"], None))
    row = [goal["id"], scene[1], destination, scene[1], 137, 0]
    if change == "wrong_goal_owner":
        row[1] = row[3] = users["other"]
        row[2] = foreign
    elif change == "wrong_account_owner":
        row[2] = foreign
    elif change == "foreign_account":
        row[2], row[3] = foreign, users["other"]
    elif change == "negative":
        row[4] = -1
    elif change == "unknown":
        row[4] = None
    else:
        allocate(scene, service, [(goal, destination, "1.37")])
        row[5] = 1
    with repository._pool.connection() as connection:
        with pytest.raises(error), connection.transaction():
            connection.execute(
                "insert into public.financial_goal_allocations "
                "(goal_id,goal_owner_id,account_id,account_owner_id,unlinked_minor,ordinal) "
                "values(%s,%s,%s,%s,%s,%s)",
                row,
            )


def test_owner_read_rls_and_service_only_writes_keep_private_rows_isolated(
    scene, repository, users
):
    service, destination, goal = setup_goal(scene)
    allocate(scene, service, [(goal, destination, "1.37")])
    with repository._pool.connection() as connection:
        for actor, anonymous, count in [
            (scene[1], False, 1),
            (users["other"], False, 0),
            (scene[1], True, 0),
        ]:
            with connection.transaction():
                shared._set_authenticated_claims(
                    connection, user_id=actor, is_anonymous=anonymous
                )
                assert (
                    connection.execute(
                        "select count(*) from public.financial_goal_allocations"
                    ).fetchone()[0]
                    == count
                )
        with pytest.raises(InsufficientPrivilege), connection.transaction():
            shared._set_authenticated_claims(
                connection, user_id=scene[1], is_anonymous=False
            )
            connection.execute(
                "update public.financial_goal_allocations set unlinked_minor=0"
            )
        with pytest.raises(CheckViolation), connection.transaction():
            legacy_allocations(connection, goal["id"], [])
    with pytest.raises(AccountNotFound):
        service.get(users["other"], goal["id"])


def test_concurrent_response_loss_retries_preserve_one_allocation_and_receipt(
    scene, repository
):
    service, destination, goal = setup_goal(scene)
    body = AllocationWrite.model_validate(
        dict(
            changes=[
                dict(
                    goal_id=goal["id"],
                    expected_version=goal["version"],
                    account_id=destination,
                    amount="1.37",
                )
            ],
            expected_account_versions=versions(scene, destination),
        )
    )
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(
            executor.map(
                lambda _: service.allocate(scene[1], body, "lost-response"), range(4)
            )
        )
    assert sum(not result["replayed"] for result in results) == 1
    assert all(result["goals"][0]["supported_minor"] == "137" for result in results)
    with pytest.raises(StaleVersion):
        service.allocate(scene[1], body, "stale-version")
    changed = body.model_copy(
        update={"changes": [body.changes[0].model_copy(update={"amount": "2"})]}
    )
    with pytest.raises(IdempotencyConflict):
        service.allocate(scene[1], changed, "lost-response")
    with repository._pool.connection() as connection:
        assert connection.execute(
            "select unlinked_minor from public.financial_goal_allocations where goal_id=%s",
            (goal["id"],),
        ).fetchall() == [(137,)]
        assert (
            connection.execute(
                "select count(*) from public.financial_plan_receipts "
                "where user_id=%s and scope='goal.allocate'",
                (scene[1],),
            ).fetchone()[0]
            == 1
        )
    assert service.get(scene[1], goal["id"])["goal"]["version"] == 2


def test_failure_after_residual_write_rolls_back_money_goal_claim_and_receipt(
    scene, repository, monkeypatch
):
    from argus.domain.planning import goal_allocations

    source = account(scene, amount="1000")
    destination = account(scene, amount="0")
    service, _, funding_goal = setup_goal(scene, source)
    _, _, goal = setup_goal(scene, destination)
    allocate(scene, service, [(funding_goal, source, "900")])
    body = ContributionRecord(
        expected_version=goal["version"],
        activity=MoneyRequest(
            kind="transfer",
            source_account_id=source,
            destination_account_id=destination,
            amount="100",
            occurred_at=NOW,
        ),
    )
    preview = service.preview(scene[1], goal["id"], body)["money"]
    body = body.model_copy(
        update={
            "activity": MoneyRequest.model_validate(
                preview["reviewed_request"]
            ).model_copy(update={"preview_token": preview["preview_token"]})
        }
    )
    original = goal_allocations.persist

    def fail_after_write(connection, owner, goals):
        original(connection, owner, goals)
        raise RuntimeError("synthetic allocation persistence failure")

    monkeypatch.setattr(goal_allocations, "persist", fail_after_write)
    with pytest.raises(RuntimeError, match="synthetic allocation persistence failure"):
        service.record(scene[1], goal["id"], body, "retry-record")
    assert service.get(scene[1], funding_goal["id"])["supported_minor"] == "90000"
    assert service.get(scene[1], goal["id"])["goal"]["version"] == 1
    assert (
        scene[0].get(user_id=scene[1], account_id=source, scope=PERSONAL).account.version
        == 1
    )
    assert (
        scene[0]
        .get(user_id=scene[1], account_id=destination, scope=PERSONAL)
        .account.version
        == 1
    )
    with repository._pool.connection() as connection:
        for table in ["financial_activity_groups", "financial_plan_links"]:
            assert (
                connection.execute(
                    "select count(*) from public." + table + " where user_id=%s",
                    (scene[1],),
                ).fetchone()[0]
                == 0
            )
        assert (
            connection.execute(
                "select count(*) from public.financial_plan_receipts "
                "where user_id=%s and scope=%s",
                (scene[1], "goal.record:" + goal["id"]),
            ).fetchone()[0]
            == 0
        )
    monkeypatch.setattr(goal_allocations, "persist", original)
    result = service.record(scene[1], goal["id"], body, "retry-record")
    assert result["goal"]["supported_minor"] == "10000"
    assert service.record(scene[1], goal["id"], body, "retry-record")["replayed"]
