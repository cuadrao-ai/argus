"""One table of "is this invite alive" cases, run against both stores.

``LIVE_INVITE`` is the rule in SQL and ``InMemoryAccessStore._invite_alive``
says it again in Python. This table is what keeps the two from drifting: a
case added for one store runs against the other.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest
from argus.domain.business.access import (
    INVITE_LIFETIME,
    AccessStore,
    InMemoryAccessStore,
    PostgresAccessStore,
)
from argus.domain.business.roles import BusinessRole
from argus.domain.business.spaces import PostgresSpaceStore
from psycopg_pool import ConnectionPool

from tests import test_financial_accounts_postgres as shared

INVITEE = "invitada@example.test"


@dataclass
class World:
    """One Business, its owner, the person who invites and the person invited."""

    store: AccessStore
    space_id: str
    owner: str
    issuer: str
    invitee: str
    invitee_email: str
    issuer_grant: str
    expire: Callable[[str], None]
    close: Callable[[], None]
    sql: Callable[[str, tuple], None] | None = None


def _join(world_store: AccessStore, space_id: str, owner: str, person: str, email: str, role: BusinessRole) -> str:
    _, listed = world_store.give(space_id, owner, email, role)
    return world_store.accept_invite(person, space_id, listed.invites[0].id)


@contextmanager
def _memory_world(issuer_role: BusinessRole) -> Iterator[World]:
    store = InMemoryAccessStore()
    space_id, owner, issuer, invitee = (str(uuid4()) for _ in range(4))
    store.ensure_owner_grant(space_id, owner)
    store.confirm(issuer, "emisora@example.test")
    store.confirm(invitee, INVITEE)
    grant = _join(store, space_id, owner, issuer, "emisora@example.test", issuer_role)

    def expire(invite_id: str) -> None:
        late = datetime.now(timezone.utc) + INVITE_LIFETIME + timedelta(seconds=1)
        store._now = lambda: late  # noqa: SLF001

    yield World(
        store, space_id, owner, issuer, invitee, INVITEE, grant, expire, lambda: store.close(space_id)
    )


@contextmanager
def _postgres_world(issuer_role: BusinessRole) -> Iterator[World]:
    def sql(statement: str, values: tuple) -> None:
        with psycopg.connect(shared.DSN) as db:
            db.execute(statement, values)

    with ConnectionPool(shared.DSN, min_size=0, max_size=2) as pool, psycopg.connect(shared.DSN) as db:
        ids = shared._create_users(db, ("owner", False), ("issuer", False), ("invitee", False))
        db.execute(
            "update auth.users set email_confirmed_at=now() where id=any(%s::uuid[])",
            (list(ids.values()),),
        )
        emails = dict(
            db.execute(
                "select id::text,lower(email) from auth.users where id=any(%s::uuid[])",
                (list(ids.values()),),
            ).fetchall()
        )
        db.commit()
        try:
            store = PostgresAccessStore(pool)
            space, _ = PostgresSpaceStore(pool).create(ids["owner"], "Colmado")
            grant = _join(store, space.id, ids["owner"], ids["issuer"], emails[ids["issuer"]], issuer_role)
            yield World(
                store,
                space.id,
                ids["owner"],
                ids["issuer"],
                ids["invitee"],
                emails[ids["invitee"]],
                grant,
                lambda invite_id: sql(
                    "update public.business_access_invites set created_at=clock_timestamp()-interval"
                    " '2 seconds',expires_at=clock_timestamp()-interval '1 second' where id=%s",
                    (invite_id,),
                ),
                lambda: sql("update public.spaces set closed_at=clock_timestamp() where id=%s", (space.id,)),
                sql,
            )
        finally:
            db.execute(
                "delete from argus_private.account_deletion_runs where user_id=any(%s::uuid[])",
                (list(ids.values()),),
            )
            shared._delete_users(db, ids)


WORLDS = {"memory": _memory_world, "postgres": _postgres_world}
BOTH = ("memory", "postgres")
# The memory store keeps no account state, so these three exist only in Postgres.
POSTGRES = ("postgres",)


@dataclass(frozen=True)
class Case:
    name: str
    alive: bool
    then: Callable[[World, str], object] = lambda world, invite_id: None
    invited: BusinessRole = BusinessRole.VIEWER
    issuer: BusinessRole = BusinessRole.ADMIN
    stores: tuple[str, ...] = BOTH


def _issuer_becomes(role: BusinessRole) -> Callable[[World, str], object]:
    return lambda w, _: w.store.change_role(w.space_id, w.owner, w.issuer_grant, role)


def _issuer_account(statement: str) -> Callable[[World, str], object]:
    return lambda w, _: w.sql(statement, (w.issuer,))


CASES = (
    Case("sent and untouched", True),
    Case("accepted", False, lambda w, i: w.store.accept_invite(w.invitee, w.space_id, i)),
    Case("revoked", False, lambda w, i: w.store.revoke_invite(w.space_id, w.owner, i)),
    Case("past its expiry", False, lambda w, i: w.expire(i)),
    Case("its Business closed", False, lambda w, _: w.close()),
    Case(
        "its inviter left the Business",
        False,
        lambda w, _: w.store.revoke_grant(w.space_id, w.owner, w.issuer_grant),
    ),
    Case("its inviter became Editor", False, _issuer_becomes(BusinessRole.EDITOR)),
    Case("its inviter became Lector", False, _issuer_becomes(BusinessRole.VIEWER)),
    Case(
        "its inviter went from Dueño to Admin and it asks for Lector",
        True,
        _issuer_becomes(BusinessRole.ADMIN),
        issuer=BusinessRole.OWNER,
    ),
    Case(
        "it asks for Dueño and its inviter is still Dueño",
        True,
        invited=BusinessRole.OWNER,
        issuer=BusinessRole.OWNER,
    ),
    Case(
        "it asks for Dueño and its inviter went from Dueño to Admin",
        False,
        _issuer_becomes(BusinessRole.ADMIN),
        invited=BusinessRole.OWNER,
        issuer=BusinessRole.OWNER,
    ),
    Case(
        "its inviter is banned",
        False,
        _issuer_account("update auth.users set banned_until=clock_timestamp()+interval '1 day' where id=%s"),
        stores=POSTGRES,
    ),
    Case(
        "its inviter turned anonymous",
        False,
        _issuer_account("update auth.users set is_anonymous=true where id=%s"),
        stores=POSTGRES,
    ),
    Case(
        "its inviter asked to delete the account",
        False,
        _issuer_account(
            "insert into argus_private.account_deletion_runs(user_id,subject_hash,analytics_distinct_id)"
            " values(%s,repeat('a',64),'liveness-parity')"
        ),
        stores=POSTGRES,
    ),
)


@pytest.mark.parametrize(
    ("store", "case"),
    [
        pytest.param(
            store,
            case,
            id=f"{store}: {case.name}",
            marks=pytest.mark.skipif(
                store == "postgres" and not shared.DSN, reason="Disposable database required"
            ),
        )
        for case in CASES
        for store in case.stores
    ],
)
def test_an_invite_is_alive_by_the_same_rule_in_both_stores(store: str, case: Case) -> None:
    with WORLDS[store](case.issuer) as world:
        _, listed = world.store.give(world.space_id, world.issuer, world.invitee_email, case.invited)
        [invite] = [i for i in listed.invites if i.email == world.invitee_email]
        assert [i["id"] for i in world.store.invitations_for(world.invitee)] == [invite.id]

        case.then(world, invite.id)

        shown = [i["id"] for i in world.store.invitations_for(world.invitee)]
        assert shown == ([invite.id] if case.alive else [])
