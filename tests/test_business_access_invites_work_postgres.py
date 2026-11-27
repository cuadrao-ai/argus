"""Invites on real Postgres: one rule says whether an invite is alive, and the
send log limits Reenviar."""

from __future__ import annotations

import psycopg
import pytest
from argus.domain.business.access import PostgresAccessStore
from argus.domain.business.memberships import InviteSendRefused, MembershipError
from argus.domain.business.roles import BusinessRole
from argus.domain.business.spaces import PostgresSpaceStore
from psycopg_pool import ConnectionPool

from tests import test_financial_accounts_postgres as shared

pytestmark = pytest.mark.skipif(not shared.DSN, reason="Disposable database required")


@pytest.fixture
def pool():
    with ConnectionPool(shared.DSN, min_size=0, max_size=4) as pool:
        yield pool


@pytest.fixture
def users():
    with psycopg.connect(shared.DSN) as connection:
        ids = shared._create_users(
            connection, ("owner", False), ("admin", False), ("invitee", False)
        )
        connection.execute(
            "update auth.users set email_confirmed_at=now() where id=any(%s::uuid[])",
            (list(ids.values()),),
        )
        connection.commit()
        try:
            yield ids
        finally:
            shared._delete_users(connection, ids)


def _email(user_id: str) -> str:
    with psycopg.connect(shared.DSN) as db:
        return db.execute(
            "select lower(email) from auth.users where id=%s", (user_id,)
        ).fetchone()[0]


@pytest.fixture
def business(pool, users):  # noqa: ANN001
    """The owner's Business with an Admin who joined by invitation."""

    spaces, access = PostgresSpaceStore(pool), PostgresAccessStore(pool)
    space, _ = spaces.create(users["owner"], "Colmado")
    _, listed = access.give(
        space.id, users["owner"], _email(users["admin"]), BusinessRole.ADMIN
    )
    admin_grant = access.accept_invite(users["admin"], space.id, listed.invites[0].id)
    return access, space.id, admin_grant


def test_an_invite_dies_when_its_inviter_loses_the_role(business, users) -> None:  # noqa: ANN001
    access, space_id, admin_grant = business
    invitee = _email(users["invitee"])
    _, listed = access.give(space_id, users["admin"], invitee, BusinessRole.VIEWER)
    [invite] = listed.invites
    assert invite.state == "pending"
    assert [i["id"] for i in access.invitations_for(users["invitee"])] == [invite.id]
    assert access.admits_email(invitee)

    access.change_role(space_id, users["owner"], admin_grant, BusinessRole.VIEWER)

    assert access.invitations_for(users["invitee"]) == ()
    assert not access.admits_email(invitee)
    assert [i.state for i in access.list(space_id, users["owner"]).invites] == ["expired"]
    with pytest.raises(MembershipError, match="business_invite_not_available"):
        access.accept_invite(users["invitee"], space_id, invite.id)
    with pytest.raises(MembershipError, match="business_invite_not_available"):
        access.deliver_invitation(
            space_id, users["owner"], invite.id, lambda db, number: "accepted"
        )

    created, relisted = access.give(
        space_id, users["owner"], invitee, BusinessRole.VIEWER
    )

    assert created
    [fresh] = relisted.invites
    assert fresh.id != invite.id and fresh.state == "pending"
    assert [i["id"] for i in access.invitations_for(users["invitee"])] == [fresh.id]
    assert access.admits_email(invitee)
    access.accept_invite(users["invitee"], space_id, fresh.id)


def test_an_invite_for_owner_dies_when_its_inviter_stops_being_owner(pool, users) -> None:  # noqa: ANN001
    spaces, access = PostgresSpaceStore(pool), PostgresAccessStore(pool)
    space, _ = spaces.create(users["owner"], "Colmado")
    _, listed = access.give(
        space.id, users["owner"], _email(users["admin"]), BusinessRole.OWNER
    )
    second_owner = access.accept_invite(users["admin"], space.id, listed.invites[0].id)
    invitee = _email(users["invitee"])
    access.give(space.id, users["admin"], invitee, BusinessRole.OWNER)
    assert access.admits_email(invitee)

    access.change_role(space.id, users["owner"], second_owner, BusinessRole.ADMIN)

    assert not access.admits_email(invitee)
    assert access.invitations_for(users["invitee"]) == ()


def _sends(space_id: str) -> list[tuple[bool]]:
    with psycopg.connect(shared.DSN) as db:
        return db.execute(
            "select resend from argus_private.business_invite_sends where space_id=%s"
            " order by sent_at",
            (space_id,),
        ).fetchall()


def _age_sends(space_id: str, interval: str) -> None:
    with psycopg.connect(shared.DSN) as db:
        db.execute(
            "update argus_private.business_invite_sends set sent_at=sent_at-%s::interval"
            " where space_id=%s",
            (interval, space_id),
        )


def test_reenviar_is_limited_by_cooldown_invite_cap_and_daily_cap(
    business, users, monkeypatch
) -> None:  # noqa: ANN001
    monkeypatch.setenv("CUADRAO_BUSINESS_INVITE_SENDS_PER_INVITE", "3")
    monkeypatch.setenv("CUADRAO_BUSINESS_INVITE_RESENDS_PER_DAY", "3")
    access, space_id, _ = business
    numbers: list[int] = []

    def send(db, number: int) -> str:  # noqa: ANN001
        numbers.append(number)
        return "accepted"

    def deliver(invite_id: str, *, resend: bool) -> str:
        return access.deliver_invitation(
            space_id, users["owner"], invite_id, send, resend
        )

    _, listed = access.give(
        space_id, users["owner"], "uno@example.test", BusinessRole.VIEWER
    )
    [invite] = listed.invites
    assert deliver(invite.id, resend=False) == "accepted"
    assert deliver(invite.id, resend=False) == "accepted"
    assert numbers == [1]

    with pytest.raises(
        InviteSendRefused, match="business_invite_resend_cooldown"
    ) as cooling:
        deliver(invite.id, resend=True)
    assert 0 < cooling.value.retry_after_seconds <= 60
    [waiting] = access.list(space_id, users["owner"]).invites
    assert 0 < waiting.resend_wait_seconds <= 60
    assert waiting.expires_at == invite.expires_at

    for _ in range(2):
        _age_sends(space_id, "2 minutes")
        assert deliver(invite.id, resend=True) == "accepted"
    assert numbers == [1, 2, 3]
    _age_sends(space_id, "2 minutes")
    with pytest.raises(InviteSendRefused, match="business_invite_send_cap_reached"):
        deliver(invite.id, resend=True)
    [same] = access.list(space_id, users["owner"]).invites
    assert (same.id, same.expires_at) == (invite.id, invite.expires_at)

    _, listed = access.give(
        space_id, users["owner"], "dos@example.test", BusinessRole.VIEWER
    )
    second = next(i for i in listed.invites if i.id != invite.id)
    assert deliver(second.id, resend=False) == "accepted"
    _age_sends(space_id, "2 minutes")
    assert deliver(second.id, resend=True) == "accepted"
    _age_sends(space_id, "2 minutes")
    with pytest.raises(InviteSendRefused, match="business_invite_daily_cap_reached"):
        deliver(second.id, resend=True)
    assert _sends(space_id) == [(False,), (True,), (True,), (False,), (True,)]

    _age_sends(space_id, "1 day")
    assert deliver(second.id, resend=True) == "accepted"


def test_the_send_log_is_closed_to_signed_in_people(business, users) -> None:  # noqa: ANN001
    access, space_id, _ = business
    _, listed = access.give(
        space_id, users["owner"], "uno@example.test", BusinessRole.VIEWER
    )
    access.deliver_invitation(
        space_id, users["owner"], listed.invites[0].id, lambda db, number: "accepted"
    )
    assert _sends(space_id) == [(False,)]

    with psycopg.connect(shared.DSN) as db, db.cursor() as cursor:
        shared._set_authenticated_claims(
            cursor, user_id=users["owner"], is_anonymous=False
        )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute("select 1 from argus_private.business_invite_sends")
