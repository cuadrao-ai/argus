"""Required real-Postgres atomicity and concurrent personal money proof."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.errors import (
    AccountNotFound,
    RecordingInputError,
    StaleVersion,
)
from argus.domain.recording.money_schemas import MoneyRequest
from argus.domain.recording.money_service import MoneyService
from argus.domain.recording.schemas import account_response
from argus.domain.recording.service import FinancialAccountService

from tests import test_financial_accounts_postgres as shared
from tests.financial_accounts.test_loop_commands import NOW
from tests.financial_accounts.test_personal_money import account, command, save

repository = shared.repository
users = shared.users
pytestmark = pytest.mark.skipif(
    not shared.DSN, reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured"
)


@pytest.fixture
def scene(repository, users):
    return FinancialAccountService(repository, lambda: NOW), users["owner"], None


def confirmed(money, user, body, aid=None):
    preview = money.preview(user_id=user, request=body, activity_id=aid, scope=PERSONAL)
    assert preview["ready"]
    return MoneyRequest.model_validate(preview["reviewed_request"]).model_copy(
        update={"preview_token": preview["preview_token"]}
    )


def test_concurrent_response_loss_retries_keep_one_pair_and_receipt(scene, repository):
    first, second = account(scene), account(scene)
    money, body = command(
        scene,
        kind="transfer",
        source_account_id=first,
        destination_account_id=second,
        amount="25",
    )
    with ThreadPoolExecutor(max_workers=6) as pool:
        receipts = list(
            pool.map(
                lambda _: money.write(
                    user_id=scene[1],
                    request=body,
                    idempotency_key="lost-response",
                    scope=PERSONAL,
                ),
                range(6),
            )
        )
    assert sum(not r["replayed"] for r in receipts) == 1
    assert len({r["activity"]["activity_id"] for r in receipts}) == 1
    with repository._pool.connection() as c:
        assert (
            c.execute(
                "select count(*) from public.financial_activity_receipts where user_id=%s",
                (scene[1],),
            ).fetchone()[0]
            == 1
        )
        assert (
            c.execute(
                "select count(*) from public.financial_activity_memberships where user_id=%s",
                (scene[1],),
            ).fetchone()[0]
            == 2
        )


def test_opposing_transfers_lock_sorted_accounts_and_stale_loser_writes_nothing(
    scene, repository
):
    first, second = account(scene), account(scene)
    commands = [
        command(
            scene,
            kind="transfer",
            source_account_id=a,
            destination_account_id=b,
            amount="25",
        )
        for a, b in [(first, second), (second, first)]
    ]

    def submit(item):
        money, body = item
        try:
            return money.write(
                user_id=scene[1],
                request=body,
                idempotency_key=str(uuid4()),
                scope=PERSONAL,
            )
        except StaleVersion:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, commands))
    assert sum(r is not None for r in results) == 1
    with repository._pool.connection() as c:
        assert (
            c.execute(
                "select count(*) from public.financial_activity_groups where user_id=%s",
                (scene[1],),
            ).fetchone()[0]
            == 1
        )
    balances = [
        account_response(
            scene[0].get(user_id=scene[1], account_id=aid, scope=PERSONAL)
        ).balance.amount_minor
        for aid in (first, second)
    ]
    assert sum(balances) == 20000


def test_second_leg_database_failure_rolls_back_every_record_and_receipt(
    scene, repository, monkeypatch
):
    from argus.domain.recording import money_postgres

    first, second = account(scene), account(scene)
    money, body = command(
        scene,
        kind="transfer",
        source_account_id=first,
        destination_account_id=second,
        amount="25",
    )
    original = money_postgres.persist

    def invalid_second(connection, user, result):
        mutations = dict(result.mutations)
        aid = sorted(mutations)[-1]
        mutation = mutations[aid]
        record = mutation.record
        bad = replace(record.current, recorded_by=str(uuid4()))
        mutations[aid] = replace(
            mutation, record=replace(record, revisions=(*record.revisions[:-1], bad))
        )
        original(connection, user, replace(result, mutations=mutations))

    monkeypatch.setattr(money_postgres, "persist", invalid_second)
    with pytest.raises(shared.psycopg.errors.ForeignKeyViolation):
        money.write(
            user_id=scene[1], request=body, idempotency_key="rollback", scope=PERSONAL
        )
    for aid in (first, second):
        current = scene[0].get(user_id=scene[1], account_id=aid, scope=PERSONAL)
        assert current.account.version == 1 and not current.expenses
    with repository._pool.connection() as c:
        for table in (
            "financial_activity_groups",
            "financial_activity_memberships",
            "financial_activity_receipts",
        ):
            assert (
                c.execute(
                    f"select count(*) from public.{table} where user_id=%s", (scene[1],)
                ).fetchone()[0]
                == 0
            )


def test_competing_refunds_cannot_exceed_purchase(scene):
    purchase_account, first, second = account(scene), account(scene), account(scene)
    purchase = save(scene, kind="expense", account_id=purchase_account, amount="40")[
        "activity"
    ]
    commands = [
        command(
            scene,
            kind="refund",
            account_id=aid,
            amount="30",
            purchase_activity_id=purchase["activity_id"],
        )
        for aid in (first, second)
    ]

    def submit(item):
        money, body = item
        try:
            return money.write(
                user_id=scene[1],
                request=body,
                idempotency_key=str(uuid4()),
                scope=PERSONAL,
            )
        except (StaleVersion, RecordingInputError):
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, commands))
    assert sum(r is not None for r in results) == 1
    assert (
        MoneyService(scene[0]).purchases(user_id=scene[1], scope=PERSONAL)["items"][0][
            "refunded_minor"
        ]
        == 3000
    )


def test_purchase_reduction_racing_refund_keeps_cap(scene):
    aid, dest = account(scene), account(scene)
    purchase = save(scene, kind="expense", account_id=aid, amount="40")["activity"]
    money, refund = command(
        scene,
        kind="refund",
        account_id=dest,
        amount="30",
        purchase_activity_id=purchase["activity_id"],
    )
    reduced = confirmed(
        money,
        scene[1],
        MoneyRequest(
            kind="expense",
            account_id=aid,
            amount="20",
            occurred_at=NOW - timedelta(days=2),
            expected_revision=1,
            reason="Correct amount",
        ),
        purchase["activity_id"],
    )

    def submit(item):
        body, activity_id = item
        try:
            return money.write(
                user_id=scene[1],
                request=body,
                activity_id=activity_id,
                idempotency_key=str(uuid4()),
                scope=PERSONAL,
            )
        except (StaleVersion, RecordingInputError):
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(submit, [(refund, None), (reduced, purchase["activity_id"])])
        )
    assert sum(r is not None for r in results) == 1
    current = money.purchases(user_id=scene[1], scope=PERSONAL)["items"][0]
    assert current["refunded_minor"] <= current["amount_minor"]


def test_refund_relink_reviews_old_and_new_purchase_dependencies(scene):
    original, new, dest, replacement = [account(scene) for _ in range(4)]
    old_purchase = save(scene, kind="expense", account_id=original, amount="40")[
        "activity"
    ]
    new_purchase = save(scene, kind="expense", account_id=new, amount="60")["activity"]
    refund = save(
        scene,
        kind="refund",
        account_id=dest,
        amount="30",
        purchase_activity_id=old_purchase["activity_id"],
    )["activity"]
    money = MoneyService(scene[0])
    body = MoneyRequest(
        kind="refund",
        account_id=replacement,
        amount="30",
        purchase_activity_id=new_purchase["activity_id"],
        occurred_at=NOW - timedelta(days=2),
        expected_revision=1,
        reason="Wrong purchase and destination",
    )
    reviewed = confirmed(money, scene[1], body, refund["activity_id"])
    assert set(reviewed.expected_versions) == {original, new, dest, replacement}
    result = money.write(
        user_id=scene[1],
        request=reviewed,
        activity_id=refund["activity_id"],
        idempotency_key="relink",
        scope=PERSONAL,
    )
    assert result["activity"]["purchase_activity_id"] == new_purchase["activity_id"]
    totals = {
        a["activity_id"]: a["refunded_minor"]
        for a in money.purchases(user_id=scene[1], scope=PERSONAL)["items"]
    }
    assert totals == {old_purchase["activity_id"]: 0, new_purchase["activity_id"]: 3000}
    assert (
        len(
            money.history(
                user_id=scene[1], activity_id=refund["activity_id"], scope=PERSONAL
            )["items"]
        )
        == 2
    )


def test_activity_rls_and_composite_membership_owner_keys(scene, repository, users):
    aid = account(scene)
    created = save(scene, kind="income", account_id=aid, amount="25")["activity"]
    money = MoneyService(scene[0])
    with pytest.raises(AccountNotFound):
        money.detail(
            user_id=users["other"], activity_id=created["activity_id"], scope=PERSONAL
        )
    with repository._pool.connection() as c:
        for identity, is_guest, expected in (
            (users["owner"], False, 1),
            (users["other"], False, 0),
            (users["guest"], True, 0),
        ):
            with c.transaction(force_rollback=True):
                shared._set_authenticated_claims(
                    c.cursor(), user_id=identity, is_anonymous=is_guest
                )
                for table in (
                    "financial_activity_groups",
                    "financial_activity_memberships",
                ):
                    assert (
                        c.execute(f"select count(*) from public.{table}").fetchone()[0]
                        == expected
                    )
                with pytest.raises(shared.psycopg.errors.InsufficientPrivilege):
                    c.execute("select * from public.financial_activity_receipts")
        with pytest.raises(shared.psycopg.errors.ForeignKeyViolation), c.transaction():
            c.execute(
                "insert into public.financial_activity_groups(id,user_id,kind,current_revision) values(%s,%s,%s,1)",
                (str(uuid4()), users["other"], "income"),
            )
            c.execute(
                "insert into public.financial_activity_memberships(activity_id,user_id,activity_revision,record_id,record_revision,role) values(%s,%s,2,%s,1,%s)",
                (
                    created["activity_id"],
                    users["other"],
                    created["legs"][0]["record_id"],
                    "single",
                ),
            )


def test_purchase_provenance_rejects_cross_owner_and_missing_revision(
    scene, repository, users
):
    aid = account(scene)
    purchase = save(scene, kind="expense", account_id=aid, amount="40")["activity"]
    refund = save(
        scene,
        kind="refund",
        account_id=aid,
        amount="20",
        purchase_activity_id=purchase["activity_id"],
    )["activity"]
    other_scene = (FinancialAccountService(repository, lambda: NOW), users["other"], None)
    other_account = account(other_scene)
    other_purchase = save(
        other_scene, kind="expense", account_id=other_account, amount="40"
    )["activity"]
    for target, revision in (
        (other_purchase["activity_id"], 1),
        (purchase["activity_id"], 999),
    ):
        with repository._pool.connection() as c:
            with (
                pytest.raises(shared.psycopg.errors.ForeignKeyViolation),
                c.transaction(),
            ):
                c.execute(
                    "update public.financial_record_revisions set details=jsonb_set(jsonb_set(details,'{purchase_activity_id}',to_jsonb(%s::text)),'{purchase_revision}',to_jsonb(%s::int)) where record_id=%s and revision=1",
                    (target, revision, refund["legs"][0]["record_id"]),
                )
    assert (
        MoneyService(scene[0]).detail(
            user_id=scene[1], activity_id=refund["activity_id"], scope=PERSONAL
        )["purchase_revision"]
        == 1
    )


def test_legacy_backfill_preserves_ids_coverage_hash_and_response_loss_receipt(
    scene, repository
):
    import json
    from pathlib import Path

    from argus.domain.recording.loop_schemas import ActivityRequest
    from argus.domain.recording.loop_service import token

    aid = account(scene)
    stored = scene[0].get(user_id=scene[1], account_id=aid, scope=PERSONAL)
    rid = str(uuid4())
    request = ActivityRequest(
        expected_version=1,
        amount="25",
        occurred_at=NOW - timedelta(days=10),
        category_id="shopping",
        coverage=[{"observation_id": stored.opening.id, "included": True}],
    )
    original_hash = token("activity", aid, None, request)
    with repository._pool.connection() as c:
        with c.transaction():
            c.execute(
                "insert into public.financial_records(id,account_id,user_id,record_kind,current_revision) values(%s,%s,%s,'expense',1)",
                (rid, aid, scene[1]),
            )
            c.execute(
                "insert into public.financial_record_revisions(record_id,user_id,revision,amount_minor,as_of,as_of_zone,recorded_by,details) values(%s,%s,1,-2500,%s,%s,%s,%s)",
                (
                    rid,
                    scene[1],
                    request.occurred_at,
                    request.time_zone,
                    scene[1],
                    json.dumps({"category_id": "shopping"}),
                ),
            )
            c.execute(
                "insert into public.financial_observation_coverage(account_id,user_id,observation_id,observation_revision,activity_id,activity_revision,included) values(%s,%s,%s,1,%s,1,true)",
                (aid, scene[1], stored.opening.id, rid),
            )
            c.execute(
                "insert into public.financial_operation_receipts(user_id,account_id,idempotency_key,identity_hash,record_id,revision,kind) values(%s,%s,'old-response-loss',%s,%s,1,'expense')",
                (scene[1], aid, original_hash, rid),
            )
            c.execute(
                "update public.financial_accounts set version=2 where id=%s", (aid,)
            )
            for name in (
                "20260929120000_personal_money_activities.sql",
                "20260929130000_personal_money_revision_integrity.sql",
            ):
                for statement in Path("supabase/migrations", name).read_text().split(";"):
                    if statement.strip().startswith(
                        "insert into public.financial_activity_"
                    ):
                        if (
                            "insert into public.financial_activity_memberships("
                            in statement
                        ):
                            c.execute(
                                "insert into public.financial_activity_revisions(activity_id,revision,user_id) values(%s,1,%s)",
                                (rid, scene[1]),
                            )
                        # Only this fixture is pre-upgrade data. Other owners may
                        # already have moved legs written by the current application.
                        target = statement.strip().split("(", 1)[0]
                        predicates = {
                            "insert into public.financial_activity_groups": " and user_id=%s and id=%s",
                            "insert into public.financial_activity_memberships": " and r.user_id=%s and r.id=%s",
                            "insert into public.financial_activity_revisions": " where user_id=%s and activity_id=%s",
                        }
                        c.execute(
                            statement + predicates[target] + " on conflict do nothing",
                            (scene[1], rid),
                        )
    replay = scene[0].loop.write_activity(
        user_id=scene[1],
        account_id=aid,
        request=request.model_copy(update={"preview_token": original_hash}),
        idempotency_key="old-response-loss",
    )
    assert replay.replayed and replay.record_id == rid and replay.revision == 1
    canonical = MoneyService(scene[0]).detail(
        user_id=scene[1], activity_id=rid, scope=PERSONAL
    )
    assert canonical["activity_id"] == rid and canonical["category_id"] == "shopping"
    assert canonical["legs"][0]["coverage"] == [
        {"observation_id": stored.opening.id, "included": True}
    ]
    assert account_response(replay.stored).balance.amount_minor == 10000
    with repository._pool.connection() as c:
        assert (
            c.execute(
                "select identity_hash from public.financial_operation_receipts where user_id=%s and account_id=%s",
                (scene[1], aid),
            ).fetchone()[0]
            == original_hash
        )
