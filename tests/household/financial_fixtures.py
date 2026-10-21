"""Shared UUID-owned Household fixtures for disposable PostgreSQL tests."""

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from argus.domain.household.financial import HouseholdFinancialService
from argus.domain.household.postgres import PostgresHouseholdRepository
from argus.domain.household.repository import FinancialAccountLookup
from argus.domain.household.schemas import CreateHouseholdRequest, Recipient
from argus.domain.household.service import HouseholdService
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.money_schemas import MoneyRequest
from argus.domain.recording.postgres_repository import PostgresFinancialAccountRepository
from argus.domain.recording.records import OpeningWrite
from argus.domain.recording.repository import NewAccount
from psycopg_pool import ConnectionPool

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL required")
NOW = datetime.now(timezone.utc)


def key():
    return str(uuid4())


@pytest.fixture
def lane():
    users = [key() for _ in range(3)]
    pool = ConnectionPool(DSN, min_size=1, max_size=5)
    records = PostgresFinancialAccountRepository(pool)
    service = HouseholdService(
        PostgresHouseholdRepository(
            pool, FinancialAccountLookup(records), clock=lambda: NOW
        )
    )
    with pool.connection() as c:
        for uid in users:
            c.execute(
                "insert into auth.users(id,email,is_anonymous) values(%s,%s,false)",
                (uid, f"household-{uid}@example.test"),
            )
    try:
        yield service, records, users
    finally:
        with pool.connection() as c, c.transaction():
            hids = [
                r[0]
                for r in c.execute(
                    "select id from households where created_by=any(%s::uuid[])", (users,)
                ).fetchall()
            ]
            from tests.household.shared_cleanup import cleanup

            cleanup(c, users, hids)
            c.execute(
                "delete from household_command_receipts where actor_id=any(%s::uuid[])",
                (users,),
            )
            c.execute(
                "delete from household_account_grants where household_id=any(%s::uuid[])",
                (hids,),
            )
            c.execute(
                "delete from household_invitations where household_id=any(%s::uuid[])",
                (hids,),
            )
            c.execute(
                "delete from household_members where household_id=any(%s::uuid[])",
                (hids,),
            )
            c.execute("delete from households where id=any(%s::uuid[])", (hids,))
            c.execute("delete from auth.users where id=any(%s::uuid[])", (users,))
        pool.close()


def command(s, actor, operation, action, hid=None, body=None, k=None):
    if body is None:
        body = (
            {"expected_version": s.get(user_id=actor, household_id=hid).version}
            if hid
            else {}
        )
    return s.execute(
        actor=actor,
        operation=operation,
        key=k or key(),
        body=body,
        household_id=hid,
        action=action,
    )


def setup(lane):
    s, records, (a, b, other) = lane
    h = command(
        s,
        a,
        "create",
        lambda: s.create(
            user_id=a,
            request=CreateHouseholdRequest(name="Fixture", display_name="Alice"),
        ),
    )
    hid = h.household_id
    invitation = command(
        s, a, "invite", lambda: s.invite(user_id=a, household_id=hid), hid
    ).invitation
    accepted = command(
        s,
        b,
        "accept",
        lambda: s.accept(user_id=b, token=invitation.token, display_name="Bob"),
    )
    return hid, accepted.membership_id, invitation.token


def account(records, owner, amount=1000, currency="DOP", share=10000, kind="checking"):
    return records.create(
        user_id=owner,
        idempotency_key=key(),
        identity_hash=key(),
        account=NewAccount(
            type=kind, currency=currency, nickname=key(), ownership_share_bps=share
        ),
        opening=OpeningWrite(
            amount_minor=amount * 100,
            as_of=NOW - timedelta(days=3),
            time_zone="UTC",
            reason=None,
        )
        if amount is not None
        else None,
        scope=PERSONAL,
    ).stored.account.id


def share(s, actor, hid, aid, mid, permission="view"):
    return command(
        s,
        actor,
        "share:" + aid,
        lambda: s.replace_grants(
            user_id=actor,
            household_id=hid,
            account_id=aid,
            recipients=[Recipient(membership_id=mid, permission=permission)],
        ),
        hid,
    )


def money(s, actor, hid, body, *, aid=None, k=None, member=None, version=None):
    h = s.get(user_id=actor, household_id=hid)
    return HouseholdFinancialService(s).money(
        actor,
        hid,
        body,
        aid,
        k,
        membership_id=member or h.membership_id,
        expected_household_version=version or h.version,
    )


def reviewed(s, actor, hid, body, aid=None):
    preview = money(s, actor, hid, body, aid=aid)
    assert preview["ready"]
    return MoneyRequest.model_validate(
        preview["reviewed_request"] | {"preview_token": preview["preview_token"]}
    )


def expense(aid, amount="25", revision=None):
    return MoneyRequest(
        kind="expense",
        account_id=aid,
        amount=amount,
        occurred_at=NOW - timedelta(days=1),
        time_zone="UTC",
        expected_revision=revision,
        reason="Receipt correction" if revision else None,
    )
