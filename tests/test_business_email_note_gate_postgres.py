"""Unverified mail is read or approved only as Pendiente with the note, in Postgres."""

from __future__ import annotations

import pytest
from argus.api import email_intake as intake_api
from argus.domain.business.authority import ActionError

from tests import test_business_email_intake_postgres as shared
from tests.test_business_email_intake_postgres import (
    ALIGNED,
    FORGED,
    NOTE,
    approve,
    deliver,
    prepare,
)

actions = shared.actions
users = shared.users
rig = shared.rig
receipts = shared.receipts
pytestmark = shared.pytestmark


def _authorize(receipts):
    receipts["store"].upsert_sender(
        receipts["space"], "address", receipts["provider"].sender, "authorized"
    )


def _restamp(receipts, auth_result, group, note):
    with receipts["pool"].connection() as db:
        db.execute(
            "update public.business_email_deliveries"
            " set auth_result=%s, inbox_group=%s, review_note=%s where space_id=%s",
            (auth_result, group, note, receipts["space"]),
        )


def _refused(receipts, attachment):
    with pytest.raises(ActionError, match="email_sender_unauthorized"):
        prepare(receipts, attachment)
    assert receipts["documents"].extractor.calls == 0


@pytest.mark.owner_acts
def test_a_held_sender_authorized_later_stays_refused(receipts):
    attachment = deliver(receipts, FORGED)
    _authorize(receipts)
    _refused(receipts, attachment)


@pytest.mark.owner_acts
def test_a_retry_restamped_after_the_sender_was_removed_stays_refused(receipts):
    _authorize(receipts)
    attachment = deliver(receipts, FORGED)
    [rule] = receipts["store"].list_senders(receipts["space"])
    receipts["store"].remove_sender(receipts["space"], rule.id)
    # What a retry from the saved original writes for a sender no longer listed.
    _restamp(receipts, "failed", "remitentes_nuevos", None)
    _authorize(receipts)
    _refused(receipts, attachment)


@pytest.mark.owner_acts
def test_a_row_from_before_the_note_is_refused(receipts):
    _authorize(receipts)
    attachment = deliver(receipts, FORGED)
    draft_id, _ = prepare(receipts, attachment)
    _restamp(receipts, "failed", "remitentes_nuevos", None)
    response = approve(receipts, draft_id)
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == "email_sender_unauthorized"
    with pytest.raises(ActionError, match="email_sender_unauthorized"):
        prepare(receipts, attachment)


STORED = [
    (None, "bandeja", NOTE, False),
    ("unknown", "bandeja", NOTE, False),
    ("ambiguous", "bandeja", NOTE, False),
    ("no_result", "bandeja", NOTE, False),
    ("none", "bandeja", NOTE, False),
    ("failed", "bandeja", None, False),
    ("failed", "remitentes_nuevos", NOTE, False),
    ("failed", "bandeja", NOTE, True),
    ("aligned", "bandeja", None, True),
]


@pytest.mark.owner_acts
@pytest.mark.parametrize(("auth_result", "group", "note", "readable"), STORED)
def test_each_stored_verdict_reads_only_as_the_gate_allows(
    receipts, auth_result, group, note, readable
):
    _authorize(receipts)
    attachment = deliver(receipts, ALIGNED)
    _restamp(receipts, auth_result, group, note)
    if not readable:
        _refused(receipts, attachment)
        return
    draft_id, origin = prepare(receipts, attachment)
    assert origin == "email"


@pytest.mark.owner_acts
def test_with_email_receiving_off_the_dossier_still_carries_the_note(
    receipts, monkeypatch
):
    _authorize(receipts)
    attachment = deliver(receipts, FORGED)
    draft_id, _ = prepare(receipts, attachment)
    configure = intake_api.configure_email_intake
    monkeypatch.setattr(intake_api, "configure_email_intake", lambda _: configure(None))
    response = approve(receipts, draft_id)
    assert intake_api.email_intake() is None
    assert response.status_code == 200, response.text
    assert response.json()["review_note"] == NOTE
