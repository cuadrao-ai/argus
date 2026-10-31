"""Drafts still in the Bandeja keep their month from closing: one
movimientos_sin_revisar reason and a count, dated by receipt date and
otherwise by arrival."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from argus.api.business_month_close_schemas import MonthClose
from argus.api.business_receipt_activity import unreviewed_days
from argus.domain.business import ledger
from argus.domain.business.month_close import (
    draft_close_day,
    month_period,
    unreviewed_in_month,
    with_unreviewed,
)
from argus.domain.business.month_close_store import empty_month

from tests.business.receipt_stub import DETAILS, PURCHASE, ReceiptStub
from tests.business.test_business_api import Owner, alice  # noqa: F401

NO_STORE = SimpleNamespace(service=SimpleNamespace(imports=SimpleNamespace(store=None)))
ARRIVED = "2026-10-30T15:00:00Z"


def _view(status: str, occurred_on: str | None = None, **extra) -> dict:  # noqa: ANN003
    return {"status": status, "occurred_on": occurred_on, "received_at": ARRIVED, **extra}


def _october(views: list[dict]) -> int:
    start, end = month_period("2026-10")
    return unreviewed_in_month(unreviewed_days(NO_STORE, views), start, end)


def test_a_month_without_drafts_closes_as_before():
    plain = empty_month("2026-10")
    shown = with_unreviewed(plain, 0)
    assert shown == {**plain, "unreviewed_movements_count": 0}
    assert shown["closed"] is True


def test_an_unapproved_draft_in_the_month_blocks_the_close():
    count = _october([_view("review_ready", "2026-10-12")])
    shown = with_unreviewed(empty_month("2026-10"), count)
    assert shown["closed"] is False
    assert shown["unreviewed_movements_count"] == 1
    assert shown["reasons"] == [{"code": "movimientos_sin_revisar", "count": 1}]


def test_the_reason_carries_every_unreviewed_draft_and_keeps_earlier_reasons():
    earlier = {"code": "missing_rnc", "activity_id": "a1", "document_kind": "receipt"}
    month = {**empty_month("2026-09"), "closed": False, "reasons": [earlier]}
    shown = with_unreviewed(month, 5)
    assert (shown["closed"], shown["unreviewed_movements_count"]) == (False, 5)
    assert shown["reasons"] == [earlier, {"code": "movimientos_sin_revisar", "count": 5}]


def test_approved_or_rejected_drafts_do_not_block():
    assert (
        _october([_view("confirmed", "2026-10-12"), _view("dismissed", "2026-10-12")])
        == 0
    )


def test_the_email_itself_is_not_a_movement():
    assert _october([_view("review_ready", "2026-10-12", email_original=True)]) == 0


def test_a_draft_dated_in_another_month_does_not_block():
    assert (
        _october([_view("review_ready", "2026-11-02"), _view("saved", "2026-09-30")]) == 0
    )


def test_a_draft_without_a_receipt_date_counts_by_arrival():
    assert _october([_view("saved")]) == 1
    assert draft_close_day(None, "2026-11-01T02:00:00Z") == date(2026, 10, 31)
    assert draft_close_day("", datetime(2026, 10, 3, 12, tzinfo=timezone.utc)) == date(
        2026, 10, 3
    )
    assert draft_close_day("2026-09-28", ARRIVED) == date(2026, 9, 28)


def test_an_old_packet_without_the_count_reads_zero():
    old = {**empty_month("2026-10"), "starts": "2026-10-01"}
    del old["from"]
    assert MonthClose.model_validate(old).unreviewed_movements_count == 0


def test_a_saved_receipt_in_memory_mode_keeps_the_month_open(alice: Owner):  # noqa: F811
    month = PURCHASE["occurred_on"][:7]
    assert alice.upload().status_code in (200, 201, 202)
    answer = alice.get("/month-close", month=month)
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert (body["closed"], body["unreviewed_movements_count"]) == (False, 1)
    assert [(r["code"], r["count"]) for r in body["reasons"]] == [
        ("movimientos_sin_revisar", 1)
    ]


def test_a_receipt_without_a_proposal_date_counts_by_its_read_date():
    late = {"id": "r1", "status": "needs_attention", "occurred_on": None}
    late["received_at"] = "2026-11-02T15:00:00Z"
    start, end = month_period("2026-10")
    days = unreviewed_days(NO_STORE, [late], {"r1": "2026-10-31"})
    assert days == [date(2026, 10, 31)]
    assert unreviewed_in_month(days, start, end) == 1
    assert unreviewed_days(NO_STORE, [late]) == [date(2026, 11, 2)]


def test_an_ambiguous_receipt_from_last_month_keeps_that_month_open(
    alice: Owner,  # noqa: F811
    stub: ReceiptStub,
):
    """Its proposal has no fields; the date its read found still decides."""

    this_month = ledger.today().replace(day=1)
    last_day = this_month - timedelta(days=1)
    dated = {**PURCHASE, "occurred_on": last_day.isoformat()}
    stub.rows = [dated, {**dated, "row": 2, "amount": "100.00"}]
    stub.details = {**DETAILS, "occurred_on": last_day.isoformat()}
    uploaded = alice.upload()
    assert uploaded.status_code == 200, uploaded.text
    detail = alice.detail(uploaded.json()["id"])
    assert (detail["status"], detail["occurred_on"]) == ("needs_attention", None)
    assert detail["evidence"]["occurred_on"] == last_day.isoformat()

    previous = alice.get("/month-close", month=last_day.strftime("%Y-%m")).json()
    assert (previous["closed"], previous["unreviewed_movements_count"]) == (False, 1)
    current = alice.get("/month-close", month=this_month.strftime("%Y-%m")).json()
    assert current["unreviewed_movements_count"] == 0
