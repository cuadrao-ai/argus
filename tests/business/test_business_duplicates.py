"""The same receipt twice never records money twice.

Same bytes: the upload comes back as the receipt already saved, and says so.
Different bytes, same read facts: the second draft is set aside as a possible
duplicate of the first, with what was read kept, and it cannot be confirmed
or entered by hand while that stands."""

from __future__ import annotations

from pathlib import Path

from argus.api.ingestion import ingestion_hub

from tests.business.receipt_stub import ReceiptStub
from tests.business.test_business_api import Owner, alice, prepared  # noqa: F401

SECOND = (
    Path(__file__).parents[1] / "document_extraction_fixtures/unreadable.png"
).read_bytes()
CONSENT = {"X-Extraction-Consent": "true"}


def test_the_same_bytes_come_back_as_the_saved_receipt(alice: Owner) -> None:  # noqa: F811
    first = alice.upload(consent=False)
    assert first.status_code == 200, first.text
    again = alice.upload(consent=False)
    assert again.status_code == 200, again.text
    assert again.json()["id"] == first.json()["id"]
    assert (first.json()["replayed"], again.json()["replayed"]) == (False, True)
    assert len(alice.get("/receipts", view="all").json()["items"]) == 1


def test_a_second_receipt_with_the_same_read_facts_is_a_duplicate_not_a_second_expense(
    alice: Owner,  # noqa: F811
    stub: ReceiptStub,
) -> None:
    original = prepared(alice)
    detail = alice.detail(original)
    assert detail["status"] == "review_ready"
    # A different file whose read gives the same merchant, date, amount and currency.
    second = alice.upload(content=SECOND, name="otra-foto.png")
    assert second.status_code == 200, second.text
    second_id = second.json()["id"]
    assert second_id != original
    _flag_if_legacy(alice, original, second_id)
    repeat = alice.detail(second_id)
    assert (repeat["status"], repeat["attention"], repeat["duplicate_of"]) == (
        "needs_attention",
        "duplicate",
        original,
    )
    assert (repeat["enterable"], repeat["preparable"]) == (False, False)
    # What was read stays visible for the person who settles it.
    assert (
        repeat["amount"] == detail["amount"] and repeat["merchant"] == detail["merchant"]
    )
    refused = alice.confirm(second_id, repeat["version"], "dup-confirm")
    assert refused.status_code in (409, 422), refused.text
    assert refused.json()["code"] in ("import_possible_duplicate", "possible_duplicate")
    entered = alice.review(second_id, 0, merchant="Otra", amount="1.00")
    assert entered.status_code in (409, 422), entered.text
    # The first receipt is untouched and still the one to confirm.
    assert alice.detail(original)["status"] == "review_ready"
    listed = {
        item["id"]: item for item in alice.get("/receipts", view="inbox").json()["items"]
    }
    assert listed[second_id]["attention"] == "duplicate"
    assert listed[original]["attention"] is None
    assert stub.calls.count(second_id) == 1


def _flag_if_legacy(alice: Owner, original: str, second_id: str) -> None:  # noqa: F811
    """The local app has no C0 bridge, so the import layer's own duplicate
    pass is what marks the repeat; the hosted bridge marks it in
    ``flag_duplicates``. Both land on the same event attention."""

    scope = alice.scope()
    sink = ingestion_hub().sink
    events = sink.list(user_id=scope.person_id, states=("open",), scope=scope.owner)
    by_receipt = {}
    for event in events:
        for observation in event["observations"]:
            by_receipt.setdefault(observation["connection_id"], event)
    assert original in by_receipt and second_id in by_receipt
    if by_receipt[second_id]["attention"] in ("possible_duplicate", "ambiguous_match"):
        return
    from dataclasses import replace

    from argus.domain.ingestion.reconcile import duplicates

    with sink.store.transaction(scope.person_id, scope=scope.owner) as tx:
        event = tx.event(by_receipt[second_id]["id"])
        tx.put_event(
            replace(
                duplicates.flag(event, [by_receipt[original]["id"]]),
                attention_detail={"basis": "read_facts"},
            )
        )
