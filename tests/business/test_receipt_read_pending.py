"""A receipt says whether a read will actually happen. Queued with the owner's
reading on: a read is pending. Reading switched off: nothing will read it, the
view says it is saved and waits for a person, and the form is enabled."""

from __future__ import annotations

from argus.api.documents import documents_service

from tests.business.test_business_api import RECEIPT, Owner, alice  # noqa: F401


def test_a_queued_receipt_is_pending_only_while_a_read_will_happen(
    alice: Owner,  # noqa: F811
    monkeypatch,  # noqa: ANN001
) -> None:
    documents = documents_service()
    assert documents is not None
    # Saved by hand, then queued the way a WhatsApp capture with reading on is:
    # the in-memory stub reads a consented upload at once, so the queue is set here.
    uploaded = alice.upload(RECEIPT + b"\x01", consent=False, name="whatsapp.jpg")
    assert uploaded.status_code == 200, uploaded.text
    receipt_id = uploaded.json()["id"]
    draft = documents.get(
        user_id=alice.person, connection_id=receipt_id, scope=alice.scope().owner
    )
    documents._update(alice.person, draft, status="queued", consent=True)
    queued = alice.detail(receipt_id)
    assert (queued["status"], queued["read_pending"]) == ("queued", True)
    assert (queued["preparable"], queued["enterable"]) == (False, False)
    # The owner's reading switch is off now: no read will come.
    monkeypatch.setattr(documents, "read_gate", lambda user_id, connection_id: False)
    waiting = alice.detail(receipt_id)
    assert (waiting["status"], waiting["read_pending"]) == ("saved", False)
    assert (waiting["preparable"], waiting["enterable"]) == (True, True)
    [listed] = [
        r for r in alice.get("/receipts").json()["items"] if r["id"] == receipt_id
    ]
    assert (listed["status"], listed["read_pending"]) == ("saved", False)
    # Switched back on: the same receipt is pending again, nothing was rewritten.
    monkeypatch.setattr(documents, "read_gate", lambda user_id, connection_id: True)
    again = alice.detail(receipt_id)
    assert (again["status"], again["read_pending"]) == ("queued", True)


def test_a_receipt_saved_without_consent_never_claims_a_read(alice: Owner) -> None:  # noqa: F811
    uploaded = alice.upload(RECEIPT + b"\x02", consent=False, name="by-hand.jpg")
    assert uploaded.status_code == 200, uploaded.text
    detail = alice.detail(uploaded.json()["id"])
    assert (detail["status"], detail["read_pending"], detail["enterable"]) == (
        "saved",
        False,
        True,
    )
