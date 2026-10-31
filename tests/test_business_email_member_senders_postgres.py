"""Owner and team are approved by default when pending senders are on, in Postgres."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from argus.domain.ingestion.email_intake import sender_policy

from tests import test_business_email_intake_postgres as shared

actions = shared.actions
users = shared.users
rig = shared.rig
pytestmark = shared.pytestmark

ALIGNED = {"spf": "pass", "dkim": "pass", "dmarc": "pass"}
FORGED = {"spf": "pass", "dkim": "fail", "dmarc": "fail"}


def _email(rig, label):
    with rig["pool"].connection() as db:
        return db.execute(
            "select lower(email) from auth.users where id=%s", (rig["users"][label],)
        ).fetchone()[0]


def _send(rig, address, authentication):
    provider = rig["provider"]
    provider.raw = shared.message().replace(b"proveedor@example.test", address.encode())
    provider.sender = provider.provider_from = address
    provider.authentication = authentication
    rig["runtime"].pending_senders = lambda: True
    delivery = rig["runtime"].enqueue_resend(str(uuid4()), (rig["route"].recipient,))
    assert asyncio.run(rig["runtime"].next())
    return rig["store"].get(delivery.id, rig["route"].space_id)


def _status(rig, address):
    rule = next(
        r for r in rig["store"].list_senders(rig["route"].space_id) if r.value == address
    )
    return rule.status, rule.last_auth_result


def test_the_owner_and_team_are_the_live_grantees(rig):
    members = rig["store"].member_addresses(rig["route"].space_id)
    assert _email(rig, "owner") in members
    assert "proveedor@example.test" not in members


def test_an_aligned_owner_is_approved_and_lands_in_bandeja(rig):
    owner = _email(rig, "owner")
    saved = _send(rig, owner, ALIGNED)
    assert (saved.state, saved.inbox_group) == ("captured", "bandeja")
    assert _status(rig, owner) == ("authorized", "aligned")


@pytest.mark.parametrize(
    ("required", "status"), [(True, "pending"), (False, "authorized")]
)
def test_a_failed_owner_follows_the_one_switch(rig, monkeypatch, required, status):
    monkeypatch.setattr(sender_policy, "DEFAULT_APPROVAL_REQUIRES_ALIGNED", required)
    owner = _email(rig, "owner")
    saved = _send(rig, owner, FORGED)
    assert _status(rig, owner) == (status, "failed")
    assert saved.state == ("rejected" if required else "captured")


def test_the_default_never_overrides_a_blocked_owner(rig):
    owner = _email(rig, "owner")
    rig["store"].upsert_sender(rig["route"].space_id, "address", owner, "blocked")
    saved = _send(rig, owner, ALIGNED)
    assert (saved.state, saved.error_code) == ("rejected", "email_sender_blocked")
    assert _status(rig, owner) == ("blocked", None)


@pytest.mark.parametrize("required", [True, False])
def test_default_approved_follows_the_live_grant_not_the_switch(
    rig, monkeypatch, required
):
    from argus.api.routers.email_intake import _sender_item

    monkeypatch.setattr(sender_policy, "DEFAULT_APPROVAL_REQUIRES_ALIGNED", required)
    space, store = rig["route"].space_id, rig["store"]
    other = _email(rig, "other")
    store.upsert_sender(space, "address", other, "blocked")
    for value, status in (("caja@tienda.test", "authorized"), ("zz@x.test", "blocked")):
        store.upsert_sender(space, "address", value, status)
    store.record_sender(space, "nuevo@proveedor.test", "aligned")
    store.upsert_sender(space, "domain", other.split("@")[1], "authorized")

    def flags():
        members = store.member_addresses(space)
        return {
            (r.kind, r.value): _sender_item(r, members)["default_approved"]
            for r in store.list_senders(space)
        }

    found = flags()
    assert found.pop(("address", other)) is True
    assert set(found.values()) == {False}
    with rig["pool"].connection() as db:
        db.execute(
            "update public.business_client_grants set revoked_at=now()"
            " where space_id=%s and grantee_id=%s",
            (space, rig["users"]["other"]),
        )
    assert flags()[("address", other)] is False
