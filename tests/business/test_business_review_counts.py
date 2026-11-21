"""The Bandeja and the Resumen count the same saved receipts from one server
projection, and counts with different meanings keep different names.

The named set, all saved for Alice's Business on the shared receipt day:

- ``ferreteria``: read, ready, never opened (unread).
- ``papeleria``: read, ready, opened once (seen, still awaiting review).
- ``fallida``: the read failed; it needs the owner's attention.
- ``colmado``: saved with reading off (unread, nothing read).
- the email ``forwarded.eml`` and its attachment ``adjunto``: the email itself
  is context for the attachment, never a second receipt to review.

The Bandeja lists five receipts. Three are unread. One needs attention.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from tests.business.receipt_stub import (
    ReceiptStub,
    receipt_date,
    receipt_details,
    receipt_purchase,
)
from tests.business.test_business_api import RECEIPT, Owner, alice  # noqa: F401
from tests.business.test_business_email_api import UNREADABLE, runtime  # noqa: F401


@pytest.fixture(autouse=True)
def _seven_uploads(monkeypatch: pytest.MonkeyPatch) -> None:
    """The named set takes seven uploads; the per-minute upload limit is not under test."""

    from argus.api import documents
    from argus.api.rate_limits import SlidingWindowLimiter

    monkeypatch.setattr(documents, "_minute", SlidingWindowLimiter())
    monkeypatch.setattr(
        documents._minute, "record_or_retry_after", lambda **_: None, raising=False
    )


def _saved(
    owner: Owner, content: bytes, *, consent: bool, name: str = "recibo.png"
) -> str:
    uploaded = owner.upload(content=content, consent=consent, name=name)
    assert uploaded.status_code == 200, uploaded.text
    return uploaded.json()["id"]


def _email(owner: Owner, intake) -> tuple[str, str]:  # noqa: ANN001
    """One delivery: the .eml itself and the attachment it carried."""

    from argus.domain.ingestion.email_intake.models import EmailDeliveryPart

    scope = owner.scope()
    store = intake.store
    route = store.create_route(
        recipient="recibos-00000113@recibos.example.test",
        space_id=scope.owner.space_id,
        principal_id=scope.person_id,
        granted_by=scope.person_id,
        grant_id=str(uuid4()),
    )
    store.enqueue(
        "resend",
        str(uuid4()),
        (route.recipient,),
        route_id=route.id,
        space_id=scope.owner.space_id,
        principal_id=route.principal_id,
    )
    claimed = store.claim()
    original = _saved(owner, RECEIPT + b"eml", consent=False, name="forwarded.eml")
    attachment = _saved(owner, UNREADABLE, consent=False, name="adjunto.png")
    store.update(claimed, original_document_id=original, subject="Factura 0113")
    store.put_part(
        claimed,
        EmailDeliveryPart(
            "1.2", "adjunto.png", "image/png", "captured", attachment, None
        ),
    )
    store.finish(claimed, "captured")
    return original, attachment


def _named_set(owner: Owner, stub: ReceiptStub, intake) -> dict[str, str]:  # noqa: ANN001
    ids = {"ferreteria": _saved(owner, RECEIPT, consent=True)}
    stub.rows = [{**receipt_purchase(), "merchant": "PAPELERIA CENTRAL", "amount": "980.50"}]
    stub.details = {**receipt_details(), "merchant": "PAPELERIA CENTRAL", "total": "980.50"}
    ids["papeleria"] = _saved(owner, RECEIPT + b"papeleria", consent=True)
    seen = owner.detail(ids["papeleria"])["activity"]["completion_cursor"]
    assert (
        owner.post(
            f"/receipts/{ids['papeleria']}/read", {"completion_cursor": seen}
        ).status_code
        == 200
    )
    stub.failure = "extraction_provider_failed"
    ids["fallida"] = _saved(owner, RECEIPT + b"fallida", consent=True)
    ids["colmado"] = _saved(owner, RECEIPT + b"colmado", consent=False)
    ids["email"], ids["adjunto"] = _email(owner, intake)
    return ids


def _bandeja(owner: Owner) -> tuple[list[str], dict]:
    page = owner.get("/receipts", view="inbox").json()
    rows = [item["id"] for item in page["items"] if not item.get("email_original")]
    return rows, page["activity"]


def test_bandeja_and_resumen_count_the_same_saved_receipts(
    alice: Owner,  # noqa: F811
    stub: ReceiptStub,
    runtime,  # noqa: ANN001, F811
) -> None:
    ids = _named_set(alice, stub, runtime)
    rows, activity = _bandeja(alice)
    assert sorted(rows) == sorted(
        ids[name] for name in ("ferreteria", "papeleria", "fallida", "colmado", "adjunto")
    )
    states = {
        item["id"]: item["activity"]["state"]
        for item in alice.get("/receipts", view="all").json()["items"]
    }
    assert states[ids["fallida"]] == "read_failed"
    assert states[ids["email"]] == "inactive"

    # Unread is new activity for this person; pending review is every row the
    # Bandeja lists. They are different counts and keep different names.
    assert activity["unread_count"] == 3
    assert activity["pending_review_count"] == len(rows) == 5
    labels = {
        item["id"]: item["bandeja_group"]["label"]
        for item in alice.get("/receipts", view="all").json()["items"]
    }
    assert labels[ids["fallida"]] == "cant_read"
    assert labels[ids["email"]] is None
    assert [label for label in labels.values() if label == "cant_read"] == ["cant_read"]
    assert alice.get("/receipt-activity").json() == activity

    # The Resumen reads the same projection: the email itself is not a receipt.
    overview = alice.get("/overview", **{"from": receipt_date(), "to": receipt_date()}).json()
    tabs = ("bandeja_listo_count", "bandeja_attention_count")
    assert [overview[name] for name in tabs] == [activity[name] for name in tabs]
    assert sum(overview[name] for name in tabs) == activity["pending_review_count"]
    assert not {"awaiting_review", "needs_attention"} & set(overview)
    assert overview["totals"] == []


def test_counts_follow_a_review_action_and_a_reload(
    alice: Owner,  # noqa: F811
    stub: ReceiptStub,
    runtime,  # noqa: ANN001, F811
) -> None:
    ids = _named_set(alice, stub, runtime)
    account = alice.account()
    detail = alice.detail(ids["ferreteria"])
    reviewed = alice.resolve_receipt(ids["ferreteria"], detail["version"], account_id=account)
    assert reviewed.status_code == 200, reviewed.text
    # Saving review details records nothing and every count stays put.
    assert _bandeja(alice)[1]["pending_review_count"] == 5
    assert alice.get("/overview", **{"from": receipt_date(), "to": receipt_date()}).json()["totals"] == []

    confirmed = alice.confirm(ids["ferreteria"], reviewed.json()["version"], str(uuid4()))
    assert confirmed.status_code == 200, confirmed.text
    for _reload in range(2):
        rows, activity = _bandeja(alice)
        overview = alice.get("/overview", **{"from": receipt_date(), "to": receipt_date()}).json()
        assert ids["ferreteria"] not in rows
        assert activity["pending_review_count"] == 4
        assert activity["unread_count"] == 2
        assert (
            overview["bandeja_listo_count"] + overview["bandeja_attention_count"] == 4
        )
        # One approved receipt is one expense, counted once.
        assert overview["totals"] == [
            {"currency": "DOP", "amount": "3450.00", "count": 1}
        ]
