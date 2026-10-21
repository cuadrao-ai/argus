from concurrent.futures import ThreadPoolExecutor

import pytest
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.errors import AccountNotFound, StaleVersion

from tests import test_personal_money_postgres as shared
from tests.financial_accounts.test_personal_money import account, command, save

scene = shared.scene
repository = shared.repository
users = shared.users
pytestmark = shared.pytestmark


@pytest.fixture
def paired(scene, monkeypatch):
    monkeypatch.setenv("ARGUS_CROSS_CURRENCY_TRANSFERS_ENABLED", "true")
    source, dest = account(scene, currency="USD"), account(scene, currency="DOP")
    money, body = command(
        scene,
        kind="transfer",
        source_account_id=source,
        destination_account_id=dest,
        amount="1",
        destination_amount="60",
    )
    return source, dest, money, body


def test_concurrent_lost_response_pair_is_one_committed_revision(
    scene, repository, paired
):
    source, dest, money, body = paired
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda _: money.write(
                    user_id=scene[1],
                    request=body,
                    idempotency_key="paired-response-loss",
                    scope=PERSONAL,
                ),
                range(4),
            )
        )
    assert sum(not r["replayed"] for r in results) == 1
    assert all(r["activity"] == results[0]["activity"] for r in results)
    with repository._pool.connection() as c:
        assert (
            c.execute(
                "select count(*) from financial_activity_receipts where user_id=%s",
                (scene[1],),
            ).fetchone()[0]
            == 1
        )
        assert (
            c.execute(
                "select count(*) from financial_activity_memberships where user_id=%s",
                (scene[1],),
            ).fetchone()[0]
            == 2
        )


def test_failure_after_persisted_pair_rolls_back_before_receipt(
    scene, repository, paired, monkeypatch
):
    from argus.domain.recording import money_postgres

    source, dest, money, body = paired
    tables = (
        "financial_activity_groups",
        "financial_activity_memberships",
        "financial_activity_receipts",
        "financial_record_revisions",
    )
    with repository._pool.connection() as c:
        before = {
            t: c.execute(
                f"select count(*) from {t} where user_id=%s", (scene[1],)
            ).fetchone()[0]
            for t in tables
        }
    original = money_postgres.persist

    def interrupted(c, owner, plan):
        original(c, owner, plan)
        raise RuntimeError("Synthetic interruption before receipt")

    monkeypatch.setattr(money_postgres, "persist", interrupted)
    with pytest.raises(RuntimeError, match="Synthetic interruption"):
        money.write(
            user_id=scene[1], request=body, idempotency_key="interrupted", scope=PERSONAL
        )
    for aid in (source, dest):
        stored = scene[0].get(user_id=scene[1], account_id=aid, scope=PERSONAL)
        assert stored.account.version == 1 and not stored.expenses
    with repository._pool.connection() as c:
        for table in tables:
            assert (
                c.execute(
                    f"select count(*) from {table} where user_id=%s", (scene[1],)
                ).fetchone()[0]
                == before[table]
            )
    monkeypatch.setattr(money_postgres, "persist", original)
    assert not money.write(
        user_id=scene[1], request=body, idempotency_key="interrupted", scope=PERSONAL
    )["replayed"]


def test_unauthorized_and_stale_pair_have_no_protected_effect(
    scene, repository, users, paired
):
    source, dest, money, body = paired
    with pytest.raises(AccountNotFound):
        money.write(
            user_id=users["other"], request=body, idempotency_key="denied", scope=PERSONAL
        )
    save(scene, kind="income", account_id=source, amount="1")
    before = scene[0].get(user_id=scene[1], account_id=source, scope=PERSONAL)
    with pytest.raises(StaleVersion):
        money.write(
            user_id=scene[1], request=body, idempotency_key="stale", scope=PERSONAL
        )
    assert scene[0].get(user_id=scene[1], account_id=source, scope=PERSONAL) == before
    assert not scene[0].get(user_id=scene[1], account_id=dest, scope=PERSONAL).expenses
    with repository._pool.connection() as c:
        assert (
            c.execute(
                "select count(*) from financial_activity_receipts where user_id=%s",
                (users["other"],),
            ).fetchone()[0]
            == 0
        )
        assert (
            c.execute(
                "select count(*) from financial_activity_receipts where user_id=%s",
                (scene[1],),
            ).fetchone()[0]
            == 1
        )
