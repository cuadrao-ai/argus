"""Sender gating that #1615 left untested, in Postgres: who the live-grant
member query leaves out, and what a retry from a stored original does."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from argus.api.routers.email_intake import _sender_item
from argus.domain.ingestion.documents.service import DocumentServiceError
from argus.domain.ingestion.email_intake.routing import UNVERIFIED_SENDER_NOTE

from tests import test_business_email_intake_postgres as shared
from tests import test_business_email_member_senders_postgres as members

actions = shared.actions
users = shared.users
rig = shared.rig
pytestmark = shared.pytestmark

SUPPLIER = "proveedor@example.test"

# Each statement takes the teammate (a live grantee) out of the members.
LAPSED = {
    "expired grant": "update public.business_client_grants set expires_at=now()-interval '1 minute'"
    " where space_id=%(space)s and grantee_id=%(user)s",
    "banned user": "update auth.users set banned_until=now()+interval '1 day' where id=%(user)s",
    "anonymous user": "update auth.users set is_anonymous=true where id=%(user)s",
    "account in deletion": "insert into argus_private.account_deletion_runs"
    " (user_id, subject_hash, analytics_distinct_id) values"
    " (%(user)s::uuid, md5(%(user)s::uuid::text) || md5(%(user)s::uuid::text), 'x')",
}


@pytest.fixture
def teammate(rig):
    """A third live grantee, so lapsing it leaves the route's own grant alone."""

    space, user = rig["route"].space_id, str(uuid4())
    address = f"equipo-{user[:8]}@example.test"
    with rig["pool"].connection() as db:
        db.execute("insert into auth.users (id, email) values (%s, %s)", (user, address))
        db.execute(
            "insert into public.business_client_grants (space_id, grantee_id, issuer_id,"
            " capabilities, business_role, created_at) select space_id, %s, issuer_id,"
            " capabilities, business_role, now()-interval '1 hour'"
            " from public.business_client_grants where id=%s",
            (user, rig["grant"]),
        )
    yield {"space": space, "user": user, "address": address}
    with rig["pool"].connection() as db:
        db.execute(
            "delete from argus_private.account_deletion_runs where user_id=%s", (user,)
        )
        db.execute(
            "delete from public.business_client_grants where grantee_id=%s", (user,)
        )
        db.execute("delete from auth.users where id=%s", (user,))


@pytest.mark.parametrize("statement", LAPSED.values(), ids=LAPSED.keys())
def test_a_lapsed_member_is_not_approved_by_default(rig, teammate, statement):
    space, store, address = rig["route"].space_id, rig["store"], teammate["address"]
    assert address in store.member_addresses(space)
    with rig["pool"].connection() as db:
        db.execute(statement, teammate)
    assert address not in store.member_addresses(space)
    saved = members._send(rig, address, members.ALIGNED)
    assert (saved.state, saved.error_code) == ("rejected", "email_sender_pending")
    [rule] = [r for r in store.list_senders(space) if r.value == address]
    assert rule.status == "pending"
    assert _sender_item(rule, store.member_addresses(space))["default_approved"] is False


def test_a_live_teammate_is_approved_by_default(rig, teammate):
    saved = members._send(rig, teammate["address"], members.ALIGNED)
    assert (saved.state, saved.inbox_group) == ("captured", "bandeja")


def _partial_with_stored_original(rig, monkeypatch):
    """An authorized supplier's mail whose original is stored but whose part
    hit a storage outage: the row is partial and a retry reads the original."""

    space, store = rig["route"].space_id, rig["store"]
    store.upsert_sender(space, "address", SUPPLIER, "authorized")
    documents = rig["documents"]
    upload = documents.upload
    outage = {"on": True}

    async def flaky(**kwargs):
        if outage["on"] and kwargs["media_type"] != "message/rfc822":
            raise DocumentServiceError("document_storage_unavailable", retryable=True)
        return await upload(**kwargs)

    monkeypatch.setattr(documents, "upload", flaky)
    saved = members._send(rig, SUPPLIER, members.ALIGNED)
    assert (saved.state, saved.auth_result) == ("partial", "aligned")
    assert saved.original_document_id is not None
    outage["on"] = False
    return saved


def _retry(rig, delivery_id):
    space = rig["route"].space_id
    assert rig["store"].retry(delivery_id, space)
    assert asyncio.run(rig["runtime"].next())
    return rig["store"].get(delivery_id, space)


def test_a_retry_of_a_stored_original_is_gated_by_a_later_block(rig, monkeypatch):
    saved = _partial_with_stored_original(rig, monkeypatch)
    rig["store"].upsert_sender(rig["route"].space_id, "address", SUPPLIER, "blocked")
    retried = _retry(rig, saved.id)
    assert (retried.state, retried.error_code) == ("rejected", "email_sender_blocked")
    assert {p.state for p in rig["store"].parts(saved.id)} == {"pending"}


def test_a_retry_of_a_stored_original_still_captures_an_authorized_sender(
    rig, monkeypatch
):
    saved = _partial_with_stored_original(rig, monkeypatch)
    retried = _retry(rig, saved.id)
    assert (retried.state, retried.inbox_group, retried.auth_result) == (
        "captured",
        "bandeja",
        "aligned",
    )


def test_a_retry_with_no_stored_verdict_lands_in_bandeja_with_no_note(rig, monkeypatch):
    # An authorized sender with no check result stays accepted (Lucas, Oct 31).
    saved = _partial_with_stored_original(rig, monkeypatch)
    with rig["pool"].connection() as db:
        db.execute(
            "update public.business_email_deliveries set auth_result=null where id=%s",
            (saved.id,),
        )
    retried = _retry(rig, saved.id)
    assert (
        retried.state,
        retried.inbox_group,
        retried.auth_result,
        retried.review_note,
    ) == ("captured", "bandeja", "no_result", None)
    assert retried.first_scan is False


def test_a_retry_with_a_failed_verdict_stays_pending_with_the_note(rig, monkeypatch):
    # Oct 18 lock: a failed check is Pendiente, never accepted like no result.
    saved = _partial_with_stored_original(rig, monkeypatch)
    with rig["pool"].connection() as db:
        db.execute(
            "update public.business_email_deliveries set auth_result='failed' where id=%s",
            (saved.id,),
        )
    retried = _retry(rig, saved.id)
    assert (
        retried.inbox_group,
        retried.auth_result,
        retried.review_note,
        retried.approved,
    ) == ("bandeja", "failed", UNVERIFIED_SENDER_NOTE, False)
