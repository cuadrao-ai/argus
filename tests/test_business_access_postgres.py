"""Owner grants and accountant access on real Postgres: born with the space,
healed once, read and prepare without approve, revoked at once, ledgered."""

from __future__ import annotations

from uuid import UUID, uuid4

import psycopg
import pytest
from argus.domain.business.access import PostgresAccessStore
from argus.domain.business.authority import ActionError, authorize
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.spaces import PostgresSpaceStore
from psycopg_pool import ConnectionPool

from tests import test_financial_accounts_postgres as shared

users = shared.users
pytestmark = pytest.mark.skipif(not shared.DSN, reason="Disposable database required")


@pytest.fixture
def pool():
    with ConnectionPool(shared.DSN, min_size=0, max_size=4) as pool:
        yield pool


def _confirm(db, user_id: str) -> str:  # noqa: ANN001
    return db.execute(
        "update auth.users set email_confirmed_at=now() where id=%s returning lower(email)",
        (user_id,),
    ).fetchone()[0]


def _grants(db, space_id: str):  # noqa: ANN001
    return db.execute(
        "select grantee_id::text, issuer_id::text, capabilities, revoked_at is not null"
        " from public.business_client_grants where space_id=%s order by created_at",
        (space_id,),
    ).fetchall()


def _ledger(db, space_id: str):  # noqa: ANN001
    return [
        row[0]
        for row in db.execute(
            "select command->>'action' from public.business_action_receipts"
            " where space_id=%s and turn_key is null order by created_at, idempotency_key",
            (space_id,),
        ).fetchall()
    ]


def test_a_space_is_born_with_the_owner_grant_and_healed_once(pool, users) -> None:  # noqa: ANN001
    spaces, access = PostgresSpaceStore(pool), PostgresAccessStore(pool)
    space, created = spaces.create(users["owner"], "Colmado")
    assert created
    with psycopg.connect(shared.DSN) as db:
        assert _grants(db, space.id) == [
            (users["owner"], users["owner"], ["read", "prepare", "approve"], False)
        ]
        assert _ledger(db, space.id) == ["owner_grant"]
        authorize(
            db,
            TrustedActor(
                actor_id=UUID(users["owner"]),
                actor_kind="member",
                space_id=UUID(space.id),
            ),
        ).require("approve")
        # An old space without the grant gets it once; a space that has it is left alone.
        db.execute(
            "delete from public.business_client_grants where space_id=%s", (space.id,)
        )
        db.execute(
            "delete from public.business_action_receipts where space_id=%s", (space.id,)
        )
    assert access.ensure_owner_grant(space.id, users["owner"]) is True
    assert access.ensure_owner_grant(space.id, users["owner"]) is False
    assert spaces.create(users["owner"], "Otro")[1] is False
    with psycopg.connect(shared.DSN) as db:
        assert len(_grants(db, space.id)) == 1
        assert _ledger(db, space.id) == ["owner_grant"]
    # A non-owner can never heal or list another person's space.
    assert access.ensure_owner_grant(space.id, users["other"]) is False
    with pytest.raises(LookupError):
        access.list(space.id, users["other"])


def test_an_accountant_reads_and_prepares_but_never_approves_and_loses_access_at_once(
    pool, users
) -> None:  # noqa: ANN001
    spaces, access = PostgresSpaceStore(pool), PostgresAccessStore(pool)
    space, _ = spaces.create(users["owner"], "Colmado")
    with psycopg.connect(shared.DSN) as db:
        email = _confirm(db, users["other"])
    created, listed = access.give(space.id, users["owner"], email.upper())
    assert created
    assert [(g.owner, g.capabilities) for g in listed.grants] == [
        (True, ("read", "prepare", "approve")),
        (False, ("read", "prepare")),
    ]
    assert listed.invites == ()
    accountant = TrustedActor(
        actor_id=UUID(users["other"]), actor_kind="member", space_id=UUID(space.id)
    )
    with psycopg.connect(shared.DSN) as db:
        live = authorize(db, accountant)
        live.require("read")
        live.require("prepare")
        with pytest.raises(ActionError):
            live.require("approve")
        # An agent acting for the accountant never holds more than read and prepare either.
        agent = authorize(
            db,
            TrustedActor(
                actor_id=UUID(users["other"]),
                actor_kind="owner_via_agent",
                space_id=UUID(space.id),
            ),
        )
        with pytest.raises(ActionError):
            agent.require("approve")
    assert access.give(space.id, users["owner"], email) == (False, listed)
    grant_id = listed.grants[1].id
    assert access.revoke_grant(space.id, users["owner"], grant_id) == "revoked"
    with psycopg.connect(shared.DSN) as db:
        with pytest.raises(ActionError):
            authorize(db, accountant)
        assert _ledger(db, space.id) == ["owner_grant", "grant_access", "revoke_grant"]
    assert [g.owner for g in access.list(space.id, users["owner"]).grants] == [True]
    assert access.revoke_grant(space.id, users["owner"], grant_id) == "missing"


def test_the_owner_cannot_revoke_their_own_grant(pool, users) -> None:  # noqa: ANN001
    spaces, access = PostgresSpaceStore(pool), PostgresAccessStore(pool)
    space, _ = spaces.create(users["owner"], "Colmado")
    own = access.list(space.id, users["owner"]).grants[0]
    assert own.owner
    assert access.revoke_grant(space.id, users["owner"], own.id) == "own_grant"
    with psycopg.connect(shared.DSN) as db:
        authorize(
            db,
            TrustedActor(
                actor_id=UUID(users["owner"]),
                actor_kind="member",
                space_id=UUID(space.id),
            ),
        ).require("approve")
        assert _ledger(db, space.id) == ["owner_grant"]


def test_an_invite_waits_for_a_confirmed_email_then_becomes_the_grant(
    pool, users
) -> None:  # noqa: ANN001
    spaces, access = PostgresSpaceStore(pool), PostgresAccessStore(pool)
    space, _ = spaces.create(users["owner"], "Colmado")
    with psycopg.connect(shared.DSN) as db:
        email = db.execute(
            "select lower(email) from auth.users where id=%s", (users["other"],)
        ).fetchone()[0]
        db.execute(
            "update auth.users set email_confirmed_at=null where id=%s", (users["other"],)
        )
    created, listed = access.give(space.id, users["owner"], email)
    assert created and [i.email for i in listed.invites] == [email]
    assert access.give(space.id, users["owner"], email) == (False, listed)
    # Unconfirmed: nothing happens on sign-in.
    assert access.accept_invites(users["other"]) == 0
    with psycopg.connect(shared.DSN) as db:
        _confirm(db, users["other"])
    assert access.accept_invites(users["other"]) == 1
    assert access.accept_invites(users["other"]) == 0
    after = access.list(space.id, users["owner"])
    assert after.invites == ()
    assert [(g.owner, g.capabilities) for g in after.grants] == [
        (True, ("read", "prepare", "approve")),
        (False, ("read", "prepare")),
    ]
    with psycopg.connect(shared.DSN) as db:
        assert _ledger(db, space.id) == ["owner_grant", "invite_access", "accept_invite"]
        assert db.execute(
            "select accepted_grant_id is not null, revoked_at is null from public.business_access_invites where space_id=%s",
            (space.id,),
        ).fetchall() == [(True, True)]
        # Another invite for the same email can be sent once the first is settled; a revoked one is a 404 for the owner.
    second_created, second = access.give(space.id, users["owner"], "nueva@example.test")
    assert (
        second_created
        and access.revoke_invite(space.id, users["owner"], second.invites[0].id) is True
    )
    assert access.revoke_invite(space.id, users["owner"], str(uuid4())) is False
    with psycopg.connect(shared.DSN) as db:
        assert _ledger(db, space.id)[-2:] == ["invite_access", "revoke_invite"]


def test_clients_cannot_read_invites(pool, users) -> None:  # noqa: ANN001
    with pool.connection() as db:
        db.execute("set local role authenticated")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with db.transaction():
                db.execute("select count(*) from public.business_access_invites")
