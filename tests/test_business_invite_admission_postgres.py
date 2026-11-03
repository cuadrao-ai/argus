"""Sign-in admission by Business invitation on real Postgres: the live invite
row admits exactly its email, acceptance hands admission to the grant, and a
disabled allowlist row refuses either way. The allowlist is read through the
real gateway against the disposable local stack."""

from __future__ import annotations

import os

import psycopg
import pytest
from argus.api.guest_access import permanent_account_access_allowed
from argus.domain.business.access import PostgresAccessStore
from argus.domain.business.spaces import PostgresSpaceStore
from faker import Faker
from psycopg_pool import ConnectionPool

from tests import test_financial_accounts_postgres as shared
from tests.local_supabase_support import local_supabase_gateway

users = shared.users
fake = Faker()
pytestmark = [
    pytest.mark.skipif(not shared.DSN, reason="Disposable database required"),
    pytest.mark.skipif(
        not os.getenv("ARGUS_LOCAL_SUPABASE_URL"),
        reason="disposable local Supabase gateway is not configured",
    ),
]


@pytest.fixture
def pool():
    with ConnectionPool(shared.DSN, min_size=0, max_size=4) as pool:
        yield pool


@pytest.fixture
def gateway():
    return local_supabase_gateway()


@pytest.fixture
def closed_signup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED", "false")


@pytest.fixture
def allowlist():
    emails: list[str] = []

    def add(email: str, *, disabled: bool) -> None:
        emails.append(email)
        with psycopg.connect(shared.DSN) as db:
            db.execute(
                "insert into public.private_alpha_allowlist(email, role, disabled_at)"
                " values (%s, 'user', case when %s then now() end)",
                (email, disabled),
            )

    yield add
    with psycopg.connect(shared.DSN) as db:
        db.execute(
            "delete from public.private_alpha_allowlist where email = any(%s)", (emails,)
        )


def _confirmed_email(user_id: str) -> str:
    with psycopg.connect(shared.DSN) as db:
        return db.execute(
            "update auth.users set email_confirmed_at=now() where id=%s returning lower(email)",
            (user_id,),
        ).fetchone()[0]


def _expire(invite_id: str) -> None:
    with psycopg.connect(shared.DSN) as db:
        db.execute(
            "update public.business_access_invites set created_at=now()-interval '8 days',"
            " expires_at=now()-interval '1 second' where id=%s",
            (invite_id,),
        )


def test_a_live_invite_admits_exactly_that_email_until_it_expires_or_is_revoked(
    pool, users, gateway, closed_signup
) -> None:  # noqa: ANN001
    spaces, access = PostgresSpaceStore(pool), PostgresAccessStore(pool)
    space, _ = spaces.create(users["owner"], "Colmado")
    invited = fake.email().lower()

    def admitted(email: str) -> bool:
        return permanent_account_access_allowed(gateway, email, access)

    assert not admitted(invited)
    _, listed = access.give(space.id, users["owner"], f" {invited.upper()} ")
    assert admitted(invited) and admitted(invited.upper()) and admitted(f" {invited}")
    assert not admitted("x" + invited)
    assert not admitted(invited.replace("@", "@x"))

    _expire(listed.invites[0].id)
    assert not admitted(invited)
    renewed = access.resend(space.id, users["owner"], listed.invites[0].id)
    assert renewed is not None and admitted(invited)

    assert access.revoke_invite(space.id, users["owner"], renewed.invites[0].id)
    assert not admitted(invited)

    access.give(space.id, users["owner"], invited)
    with psycopg.connect(shared.DSN) as db:
        db.execute("update public.spaces set closed_at=now() where id=%s", (space.id,))
    assert not admitted(invited)


def test_acceptance_moves_admission_to_the_grant_and_revocation_ends_it(
    pool, users, gateway, closed_signup
) -> None:  # noqa: ANN001
    spaces, access = PostgresSpaceStore(pool), PostgresAccessStore(pool)
    space, _ = spaces.create(users["owner"], "Colmado")
    email = _confirmed_email(users["other"])

    assert not permanent_account_access_allowed(gateway, email, access)
    _, listed = access.give(space.id, users["owner"], email)
    assert permanent_account_access_allowed(gateway, email, access)
    grant_id = access.accept_invite(users["other"], space.id, listed.invites[0].id)
    assert access.list(space.id, users["owner"]).invites == ()
    assert permanent_account_access_allowed(gateway, email, access)

    assert access.revoke_grant(space.id, users["owner"], grant_id) == "revoked"
    assert not permanent_account_access_allowed(gateway, email, access)


def test_a_disabled_row_refuses_and_a_hand_listed_email_outlives_its_invite(
    pool, users, gateway, closed_signup, allowlist
) -> None:  # noqa: ANN001
    spaces, access = PostgresSpaceStore(pool), PostgresAccessStore(pool)
    space, _ = spaces.create(users["owner"], "Colmado")
    disabled, by_hand = fake.email().lower(), fake.email().lower()
    allowlist(disabled, disabled=True)
    allowlist(by_hand, disabled=False)

    access.give(space.id, users["owner"], disabled)
    assert not permanent_account_access_allowed(gateway, disabled, access)

    _, listed = access.give(space.id, users["owner"], by_hand)
    assert access.revoke_invite(space.id, users["owner"], listed.invites[0].id)
    assert permanent_account_access_allowed(gateway, by_hand, access)


def test_open_signup_ignores_invitations(
    pool, users, gateway, allowlist, monkeypatch
) -> None:  # noqa: ANN001
    monkeypatch.setenv("CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED", "true")
    access = PostgresAccessStore(pool)
    disabled = fake.email().lower()
    allowlist(disabled, disabled=True)

    assert permanent_account_access_allowed(gateway, fake.email(), access)
    assert not permanent_account_access_allowed(gateway, disabled, access)


def test_a_closed_business_admits_no_grantee_and_a_hand_listed_owner_stays(
    pool, users, gateway, closed_signup, allowlist
) -> None:  # noqa: ANN001
    spaces, access = PostgresSpaceStore(pool), PostgresAccessStore(pool)
    space, _ = spaces.create(users["owner"], "Colmado")
    owner, member = _confirmed_email(users["owner"]), _confirmed_email(users["other"])
    allowlist(owner, disabled=False)
    _, listed = access.give(space.id, users["owner"], member)
    access.accept_invite(users["other"], space.id, listed.invites[0].id)
    assert permanent_account_access_allowed(gateway, member, access)

    with psycopg.connect(shared.DSN) as db:
        db.execute("update public.spaces set closed_at=now() where id=%s", (space.id,))
    assert not permanent_account_access_allowed(gateway, member, access)
    assert permanent_account_access_allowed(gateway, owner, access)

    with psycopg.connect(shared.DSN) as db:
        db.execute("update public.spaces set closed_at=null where id=%s", (space.id,))
    assert permanent_account_access_allowed(gateway, member, access)
