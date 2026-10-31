"""Pending senders on real Postgres: nothing of the mail is stored."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import psycopg
import pytest

from tests import test_business_email_intake_postgres as shared

actions = shared.actions
users = shared.users
rig = shared.rig
pytestmark = shared.pytestmark

ALIGNED = {"spf": "pass", "dkim": "pass", "dmarc": "pass"}
FORGED = {"spf": "pass", "dkim": "fail", "dmarc": "fail"}
NOTE = "No pudimos verificar este remitente."
SENDER = "proveedor@example.test"


def _send(rig, authentication=ALIGNED, *, on=True):
    rig["runtime"].pending_senders = lambda: on
    rig["provider"].authentication = authentication
    rig["provider"].provider_from = SENDER
    delivery = rig["runtime"].enqueue_resend(str(uuid4()), (rig["route"].recipient,))
    assert asyncio.run(rig["runtime"].next())
    return rig["store"].get(delivery.id, rig["route"].space_id)


def _rule(rig):
    return next(
        r for r in rig["store"].list_senders(rig["route"].space_id) if r.value == SENDER
    )


def _stored(rig, delivery_id):
    with rig["pool"].connection() as db:
        parts = db.execute(
            "select count(*) from public.business_email_parts where delivery_id=%s",
            (delivery_id,),
        ).fetchone()[0]
        documents = db.execute(
            "select count(*) from public.business_sources where space_id=%s",
            (rig["route"].space_id,),
        ).fetchone()[0]
    return parts, documents


def test_an_unknown_sender_stores_nothing_and_is_pending(rig):
    before = _stored(rig, str(uuid4()))[1]
    saved = _send(rig, FORGED)
    assert (saved.state, saved.error_code, saved.inbox_group) == (
        "rejected",
        "email_sender_pending",
        None,
    )
    assert saved.original_document_id is None
    assert _stored(rig, saved.id) == (0, before)
    rule = _rule(rig)
    assert (rule.status, rule.last_auth_result) == ("pending", "failed")
    assert rule.last_seen_at is not None


def test_once_authorized_the_sender_lands_in_bandeja(rig):
    _send(rig)
    first = _rule(rig)
    rig["store"].upsert_sender(rig["route"].space_id, "address", SENDER, "authorized")
    saved = _send(rig)
    assert (saved.state, saved.inbox_group, saved.review_note) == (
        "captured",
        "bandeja",
        None,
    )
    rule = _rule(rig)
    assert (rule.id, rule.status, rule.last_auth_result) == (
        first.id,
        "authorized",
        "aligned",
    )
    assert rule.last_seen_at >= first.last_seen_at


def test_an_authorized_failed_sender_keeps_the_note(rig):
    rig["store"].upsert_sender(rig["route"].space_id, "address", SENDER, "authorized")
    saved = _send(rig, FORGED)
    assert (saved.state, saved.inbox_group, saved.review_note) == (
        "captured",
        "bandeja",
        NOTE,
    )
    no_result = _send(rig, None)
    assert (no_result.state, no_result.inbox_group, no_result.review_note) == (
        "captured",
        "bandeja",
        None,
    )


def test_a_blocked_sender_is_dropped_and_its_row_untouched(rig):
    rig["store"].upsert_sender(rig["route"].space_id, "address", SENDER, "blocked")
    saved = _send(rig)
    assert (saved.state, saved.error_code) == ("rejected", "email_sender_blocked")
    rule = _rule(rig)
    assert (rule.status, rule.last_auth_result, rule.last_seen_at) == (
        "blocked",
        None,
        None,
    )


def test_flag_off_keeps_new_senders_and_flag_on_leaves_those_rows(rig):
    old = _send(rig, on=False)
    assert (old.state, old.inbox_group) == ("captured", "remitentes_nuevos")
    assert rig["store"].list_senders(rig["route"].space_id) == []
    _send(rig, on=True)
    assert rig["store"].get(old.id, rig["route"].space_id) == old
    assert _rule(rig).status == "pending"


def test_the_columns_refuse_values_outside_the_verdicts(rig):
    with rig["pool"].connection() as db, pytest.raises(psycopg.errors.CheckViolation):
        db.execute(
            "insert into public.business_email_senders"
            "(space_id, kind, value, status, last_auth_result)"
            " values (%s,'address','x@y.test','pending','pass')",
            (rig["route"].space_id,),
        )
    with rig["pool"].connection() as db, pytest.raises(psycopg.errors.CheckViolation):
        db.execute(
            "insert into public.business_email_senders(space_id, kind, value, status)"
            " values (%s,'address','x@y.test','waiting')",
            (rig["route"].space_id,),
        )
