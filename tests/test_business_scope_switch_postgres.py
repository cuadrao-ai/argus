"""Two Businesses on real Postgres: an accountant who holds a grant on one of
them is bound to that one only; approve never leaves the owner; a revoked or
expired grant answers nothing at once; a legacy write under the grant leaves
a ledger row naming it; the one-time access line is remembered per grant."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from argus.domain.business.access import PostgresAccessStore
from argus.domain.business.authority import ActionError, BusinessAuthority, authorize
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.transactions import record_legacy_action, transaction
from psycopg import Connection

from tests import test_business_actions_postgres as shared
from tests.test_business_spaces_migration_postgres import space
from tests.test_financial_accounts_postgres import DSN

users = shared.users
pytestmark = shared.pytestmark


@pytest.fixture
def world(users):  # noqa: ANN001
    """A owned by ``owner``, B owned by ``other``; ``other`` holds read and
    prepare on A."""

    from psycopg_pool import ConnectionPool

    with Connection.connect(DSN) as db:
        a = space(db, users["owner"])
        b = space(db, users["other"])
        db.execute("update public.spaces set name='Colmado A' where id=%s", (a,))
        db.execute("update public.spaces set name='Taller B' where id=%s", (b,))
        for space_id, owner in ((a, users["owner"]), (b, users["other"])):
            db.execute(
                "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities)"
                " select %s,%s,%s,ARRAY['read','prepare','approve'] where not exists"
                " (select 1 from public.business_client_grants where space_id=%s and grantee_id=%s"
                " and revoked_at is null)",
                (space_id, owner, owner, space_id, owner),
            )
        grant = db.execute(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities)"
            " values (%s,%s,%s,ARRAY['read','prepare']) returning id::text",
            (a, users["other"], users["owner"]),
        ).fetchone()[0]
        db.commit()
    with ConnectionPool(DSN, min_size=0, max_size=4) as pool:
        yield dict(pool=pool, a=a, b=b, grant=grant, access=PostgresAccessStore(pool))


def _ledger(pool, space_id: str) -> list[tuple[str, str, str]]:  # noqa: ANN001
    with pool.connection() as db:
        return [
            tuple(row)
            for row in db.execute(
                "select command->>'action', actor->>'grant_id', actor->>'issuer_id'"
                " from public.business_action_receipts where space_id=%s and turn_key is null"
                " order by created_at",
                (space_id,),
            ).fetchall()
        ]


def test_the_listing_and_the_seen_mark_are_the_servers(world, users) -> None:  # noqa: ANN001
    access = world["access"]
    listed = access.spaces_for(users["other"])
    assert [(s.role, s.name, s.capabilities) for s in listed] == [
        ("owner", "Taller B", ("read", "prepare", "approve")),
        ("accountant", "Colmado A", ("read", "prepare")),
    ]
    assert access.seen_grants(users["other"]) == frozenset()
    access.mark_seen(users["other"], world["grant"])
    access.mark_seen(users["other"], world["grant"])
    assert access.seen_grants(users["other"]) == frozenset({world["grant"]})
    assert [r for r in _ledger(world["pool"], world["a"]) if r[0] == "access_seen"] == [
        ("access_seen", world["grant"], users["owner"])
    ]
    # The owner's own grant is never marked; a foreign grant changes nothing.
    own = next(s for s in access.spaces_for(users["owner"]) if s.role == "owner")
    access.mark_seen(users["owner"], own.grant_id)
    access.mark_seen(users["owner"], world["grant"])
    assert access.seen_grants(users["owner"]) == frozenset()
    assert access.granted(users["owner"], world["grant"]) is None
    assert access.granted(users["other"], world["grant"]).space_id == world["a"]


def test_the_grant_binds_the_accountant_to_that_business_without_approve(
    world, users
) -> None:  # noqa: ANN001
    authority = BusinessAuthority(world["pool"])
    actor = TrustedActor(
        actor_id=UUID(users["other"]), actor_kind="member", space_id=UUID(world["a"])
    )
    context = authority.resolve_actor(actor, grant_id=UUID(world["grant"]))
    assert str(context.owner_id) == users["owner"]
    with world["pool"].connection() as db, db.transaction():
        live = authorize(db, actor, UUID(world["grant"]))
        assert live.capabilities == frozenset({"read", "prepare"})
        with pytest.raises(ActionError) as refused:
            live.require("approve")
        assert refused.value.code == "business_permission_denied"
    # Settling, approving and confirming open the transaction with approve: refused the same way.
    with pytest.raises(ActionError) as refused:
        with transaction(authority, context, "approve"):
            pass
    assert refused.value.code == "business_permission_denied"
    # The grant names A: it cannot be used to enter B.
    with pytest.raises(ActionError):
        authority.resolve_actor(
            TrustedActor(
                actor_id=UUID(users["other"]),
                actor_kind="member",
                space_id=UUID(world["b"]),
            ),
            grant_id=UUID(world["grant"]),
        )
    # A legacy write under the grant leaves a row naming the grant and the issuer.
    with transaction(authority, context, "prepare") as tx:
        record_legacy_action(tx.connection, tx.authorization, "receipt_review", ["ev-1"])
        record_legacy_action(tx.connection, tx.authorization, "receipt_review", ["ev-1"])
    assert [
        r for r in _ledger(world["pool"], world["a"]) if r[0] == "receipt_review"
    ] == [("receipt_review", world["grant"], users["owner"])]


def test_a_revoked_or_expired_grant_answers_nothing_at_once(world, users) -> None:  # noqa: ANN001
    access, grant = world["access"], world["grant"]
    authority = BusinessAuthority(world["pool"])
    actor = TrustedActor(
        actor_id=UUID(users["other"]), actor_kind="member", space_id=UUID(world["a"])
    )
    context = authority.resolve_actor(actor, grant_id=UUID(grant))
    with world["pool"].connection() as db:
        db.execute(
            "update public.business_client_grants set created_at=%s, expires_at=%s where id=%s",
            (
                datetime.now(timezone.utc) - timedelta(days=15),
                datetime.now(timezone.utc) - timedelta(seconds=1),
                grant,
            ),
        )
    assert access.granted(users["other"], grant) is None
    assert [s.role for s in access.spaces_for(users["other"])] == ["owner"]
    with pytest.raises(ActionError) as refused:
        with transaction(authority, context, "read"):
            pass
    assert refused.value.code == "business_record_not_found"
    with world["pool"].connection() as db:
        db.execute(
            "update public.business_client_grants set expires_at=null, revoked_at=now() where id=%s",
            (grant,),
        )
    assert access.granted(users["other"], grant) is None
    with pytest.raises(ActionError):
        authority.resolve_actor(actor, grant_id=UUID(grant))
