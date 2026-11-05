"""HTTP proof for household invite codes and the default-off beta invite surface."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from argus.api import households as surface
from argus.domain.household.errors import VerifiedUserRequired
from argus.domain.household.invite_codes import (
    InviteSettings,
    format_code,
    invite_link,
    new_code,
    normalize_code,
)
from argus.domain.household.invites import verified_user

from tests.household.conftest import ALICE, BOB

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()


def test_codes_normalize_typing_and_reject_garbage():
    code = new_code()
    assert normalize_code(format_code(code).lower()) == code
    assert normalize_code(" abcd-efgh-jkmn ") == "ABCDEFGHJKMN"
    assert normalize_code("oiLu-0000-0000") == "011V00000000"
    assert normalize_code("ABC") is None and normalize_code("ABCD-EFGH-JKM!") is None
    # The 8-character codes of #788 are no longer a valid shape.
    assert normalize_code("ABCD-EFGH") is None


def test_null_or_missing_caller_is_never_an_owner_or_the_founder():
    # Priya (b): auth.uid() is null under service_role; null must own nothing.
    founder_id, other_id = str(uuid4()), str(uuid4())
    for missing in (None, "", "  ", "not-a-uuid", ALICE):
        with pytest.raises(VerifiedUserRequired):
            verified_user(missing)
    assert verified_user(founder_id.upper()) == founder_id
    for settings in (InviteSettings(), InviteSettings(founder_user_id="")):
        assert not settings.is_founder(None)
        assert not settings.is_founder("")
        assert not settings.is_founder(founder_id)
    founder = InviteSettings(founder_user_id=founder_id)
    assert founder.is_founder(founder_id) and not founder.is_founder(None)
    assert not founder.is_founder(other_id)


def test_group_link_label_is_trimmed_and_cannot_be_blank():
    from argus.domain.household.invite_schemas import CreateGroupLinkRequest
    from pydantic import ValidationError

    when = datetime.now(timezone.utc) + timedelta(days=1)
    for blank in ("   ", "\t\n"):
        with pytest.raises(ValidationError):
            CreateGroupLinkRequest(source_label=blank, cap=3, expires_at=when)
    request = CreateGroupLinkRequest(source_label="  Primos  ", cap=3, expires_at=when)
    assert request.source_label == "Primos"


def test_link_flag_off_keeps_todays_household_scheme_and_no_beta_link():
    off = InviteSettings()
    on = InviteSettings(universal_link_enabled=True)
    assert (
        invite_link("t0k", household=True, settings=off) == "argus-household://invite#t0k"
    )
    assert invite_link("t0k", household=False, settings=off) is None
    assert (
        invite_link("t0k", household=False, settings=on)
        == "https://cuadrao.ai/invite#t0k"
    )


def test_household_invite_returns_code_and_accepts_by_code(alice, bob, monkeypatch):
    hid = alice.create_household({"name": "Casa"}).json()["household_id"]
    created = alice.invite(hid)
    assert created.status_code == 201, created.text
    invitation = created.json()["invitation"]
    assert invitation["code"] and invitation["link"].startswith(
        "argus-household://invite#"
    )
    preview = bob.write("/household-invitations/preview", {"code": invitation["code"]})
    assert preview.status_code == 200 and preview.json()["available"]
    accepted = bob.write(
        "/household-invitations/accept",
        {"code": invitation["code"].lower(), "display_name": "Bob"},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["state"] == "active"
    both = bob.write(
        "/household-invitations/accept", {"code": invitation["code"], "token": "x" * 40}
    )
    assert both.status_code == 422
    neither = bob.write("/household-invitations/accept", {"display_name": "Bob"})
    assert neither.status_code == 422


def test_household_invite_uses_universal_link_when_flag_is_on(alice, monkeypatch):
    hid = alice.create_household({"name": "Casa"}).json()["household_id"]
    service = surface.households_service()
    monkeypatch.setattr(
        service, "_invite_settings", InviteSettings(universal_link_enabled=True)
    )
    invitation = alice.invite(hid).json()["invitation"]
    assert invitation["link"] == "https://cuadrao.ai/invite#" + invitation["token"]


def test_invites_surface_is_off_by_default_before_auth(client):
    response = client.get("/api/v1/invites/access")
    assert response.status_code == 404
    assert response.json()["code"] == "invites_unavailable"


def test_invites_surface_stays_off_in_memory_mode(client, monkeypatch, alice):
    monkeypatch.setenv("CUADRAO_BETA_INVITES_ENABLED", "true")
    response = client.get(
        "/api/v1/invites/access", headers={"Authorization": f"Bearer {ALICE}"}
    )
    assert response.status_code == 404


@pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL required")
def test_invite_routes_over_postgres(client, alice, bob, identities, monkeypatch):
    from argus.domain.household.invites import PostgresInviteStore
    from psycopg_pool import ConnectionPool

    monkeypatch.setenv("CUADRAO_BETA_INVITES_ENABLED", "true")
    ids = [identities[ALICE]["id"], identities[BOB]["id"]]
    pool = ConnectionPool(DSN, min_size=1, max_size=4, open=True)
    with pool.connection() as c:
        for uid in ids:
            c.execute(
                "insert into auth.users(id,email,is_anonymous) values(%s,%s,false)",
                (uid, f"api-{uid}@example.test"),
            )
    settings = InviteSettings(
        founder_user_id=ids[0], waitlist_url="https://cuadrao.ai/waitlist"
    )
    surface.configure_invites_store(PostgresInviteStore(pool, settings=settings))
    created_ids = []
    try:
        assert bob.write("/invites", {}, key=None).status_code == 201
        missing_key = client.post(
            "/api/v1/invites", json={}, headers={"Authorization": f"Bearer {BOB}"}
        )
        assert missing_key.status_code in {400, 422, 428}
        key = str(uuid4())
        first = alice.write("/invites", {}, key=key)
        assert first.status_code == 201, first.text
        body = first.json()
        created_ids.append(body["invitation"]["id"])
        assert body["quota"] == {"limit": 10, "used": 1, "remaining": 9}
        replay = alice.write("/invites", {}, key=key).json()["invitation"]
        assert replay["replayed"] and replay["token"] is None
        refused = bob.write(
            "/invites/group-links",
            {
                "source_label": "Chat",
                "cap": 1,
                "expires_at": (
                    datetime.now(timezone.utc) + timedelta(days=1)
                ).isoformat(),
            },
        )
        assert refused.status_code == 403 and refused.json()["code"] == "founder_required"
        link = alice.write(
            "/invites/group-links",
            {
                "source_label": "Chat",
                "cap": 1,
                "expires_at": (
                    datetime.now(timezone.utc) + timedelta(days=1)
                ).isoformat(),
            },
        )
        assert link.status_code == 201, link.text
        created_ids.append(link.json()["invitation"]["id"])
        preview = bob.write(
            "/invites/preview", {"code": link.json()["invitation"]["code"]}
        )
        assert preview.json() == {
            "kind": "group_link",
            "available": True,
            "expires_at": preview.json()["expires_at"],
            "household_name": None,
        }
        # Bob is not admitted yet, so the group link admits him.
        redeemed = bob.write(
            "/invites/redeem", {"token": link.json()["invitation"]["token"]}
        )
        assert redeemed.status_code == 200 and redeemed.json()["outcome"] == "admitted"
        # Without the founder role Alice is not admitted, so the full link
        # sends her to the waitlist and says so.
        surface.configure_invites_store(
            PostgresInviteStore(
                pool, settings=InviteSettings(waitlist_url="https://cuadrao.ai/waitlist")
            )
        )
        access = alice._client.get(
            "/api/v1/invites/access", headers={"Authorization": f"Bearer {ALICE}"}
        )
        assert access.json()["admitted"] is True  # gate is off: today's behavior
        full = alice.write("/invites/redeem", {"code": link.json()["invitation"]["code"]})
        assert full.status_code == 409 and full.json()["code"] == "group_link_full"
        assert full.json()["context"] == {"waitlist_url": "https://cuadrao.ai/waitlist"}
        sent = alice._client.get(
            "/api/v1/invites", headers={"Authorization": f"Bearer {ALICE}"}
        ).json()
        assert [i["state"] for i in sent["invitations"]] == ["pending"]
        numbers = alice._client.get(
            "/api/v1/invites/network", headers={"Authorization": f"Bearer {ALICE}"}
        )
        assert numbers.status_code == 403
    finally:
        surface.configure_invites_store(None)
        with pool.connection() as c, c.transaction():
            c.execute(
                "delete from public.invite_referrals where beta_invitation_id in"
                " (select id from public.beta_invitations where created_by=any(%s::uuid[]))"
                " or acceptor_user_id=any(%s::uuid[])",
                (ids, ids),
            )
            c.execute(
                "delete from public.beta_invitations where created_by=any(%s::uuid[])",
                (ids,),
            )
            c.execute("delete from auth.users where id=any(%s::uuid[])", (ids,))
        pool.close()
