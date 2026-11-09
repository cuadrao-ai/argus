"""Por cobrar and Por pagar behind one server switch, off by default.

Off, the month close carries no receivables, payables or line status, the
routes that only serve settlement refuse, the workspace says so, and an open
receivable or payable never keeps a month from being ready for the 606 and
607. The fiscal requirements still do. The net result, ITBIS cobrado and the
counts by status keep their meaning: what they show while nobody can mark is
the owner's call. On, the month close is what it was."""

from __future__ import annotations

from uuid import uuid4

import pytest
from argus.api.business_month_close_schemas import MonthClose
from argus.domain.business.actions.dossier import shown_bill_mark
from argus.domain.business.actions.mutations import PAID_BILL_MARK, PAYABLE_BILL_MARK
from argus.domain.business.contracts.facts import BusinessFacts, BusinessResolution
from argus.domain.business.month_close import (
    PAYMENT_METHODS,
    month_period,
    summarize,
    with_unreviewed,
)
from argus.domain.business.month_close_store import (
    empty_month,
    foreign_currency,
    month_close,
)

from tests.business.test_business_api import BASE, Owner, alice  # noqa: F401
from tests.business.test_month_close import DAY, document

SWITCH = "CUADRAO_BUSINESS_SETTLEMENT_ENABLED"
SETTLEMENT_KEYS = {"payment_methods", "cuentas_por_cobrar", "cuentas_por_pagar"}
BLOCK_SETTLEMENT_KEYS = {
    "cuentas_por_cobrar",
    "cuentas_por_cobrar_minor",
    "cuentas_por_pagar",
    "cuentas_por_pagar_minor",
}
STANDING = {"606": "prepared_candidate", "607": "prepared_candidate"}


@pytest.fixture
def settlement_off(monkeypatch: pytest.MonkeyPatch) -> None:
    # Set, not deleted: an absent name would be refilled from a worktree .env.
    monkeypatch.setenv(SWITCH, "false")


def _open_month() -> list:
    """A filed-ready October with one sale still to collect and one purchase
    still to pay; every document carries its RNC and NCF."""

    return [
        document(
            activity_id="sale-open",
            total_minor=11800,
            itbis_minor=1800,
            status="pendiente",
            settled_on=None,
            payment_method=None,
        ),
        document(
            activity_id="purchase-open",
            role="receipt",
            total_minor=2360,
            itbis_minor=360,
            status="pendiente",
            settled_on=None,
            payment_method=None,
        ),
    ]


def _october(documents, settlement: bool, forms=STANDING) -> dict:  # noqa: ANN001
    return month_close("2026-10", DAY, documents, dict(forms), settlement=settlement)


def _lines(close: dict) -> list[dict]:
    return [
        line
        for key in ("missing_rnc", "missing_ncf", "missing_payment_form", "missing_fiscal_data")
        for line in close[key]
    ]


def _stripped(close: dict) -> dict:
    """An on month close with its settlement state taken out by hand."""

    def line(item: dict) -> dict:
        return {key: value for key, value in item.items() if key != "status"}

    shown = {key: value for key, value in close.items() if key not in SETTLEMENT_KEYS}
    for key in ("missing_rnc", "ncf_malformed", "missing_ncf", "missing_payment_form", "missing_fiscal_data"):
        shown[key] = [line(item) for item in close[key]]
    shown["currencies"] = [
        {
            key: value
            for key, value in block.items()
            if key not in BLOCK_SETTLEMENT_KEYS
        }
        for block in close["currencies"]
    ]
    return shown


def test_off_the_month_close_carries_no_settlement_state() -> None:
    held = document(activity_id="no-rnc", rnc=None, status="pendiente")
    close = _october([*_open_month(), held], settlement=False)
    assert SETTLEMENT_KEYS.isdisjoint(close)
    [block] = close["currencies"]
    assert BLOCK_SETTLEMENT_KEYS.isdisjoint(block)
    assert _lines(close) and all("status" not in line for line in _lines(close))
    # Every fiscal figure, list and reason stays what it was.
    on = _october([*_open_month(), held], settlement=True)
    assert _stripped(close) == _stripped(on)
    MonthClose.model_validate(with_unreviewed(close, 0))


def test_off_the_net_result_and_itbis_cobrado_keep_their_meaning() -> None:
    [off] = _october(_open_month(), settlement=False)["currencies"]
    [on] = _october(_open_month(), settlement=True)["currencies"]
    names = ("net_result_final", "itbis_cobrado_minor", "by_status")
    assert {name: off[name] for name in names} == {name: on[name] for name in names}
    assert off["net_result_final"] is False


def test_off_open_receivables_and_payables_never_hold_filing_ready() -> None:
    off = with_unreviewed(_october(_open_month(), settlement=False), 0)
    assert off["filing_ready"] is True
    on = with_unreviewed(_october(_open_month(), settlement=True), 0)
    assert on["filing_ready"] is False
    assert on["cuentas_por_cobrar"] and on["cuentas_por_pagar"]


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"count": 1}, "a draft still in the Bandeja"),
        ({"month_unknown": True}, "a read in flight with no date"),
        ({"forms": {**STANDING, "606": "needs_review"}}, "a form that does not stand"),
        ({"held": True}, "a document the 606 or 607 holds"),
    ],
)
def test_off_the_fiscal_requirements_still_hold_filing_ready(change, reason) -> None:  # noqa: ANN001
    forms = change.get("forms", STANDING)
    close = _october(_open_month(), settlement=False, forms=forms)
    if change.get("held"):
        close = month_close(
            "2026-10",
            DAY,
            _open_month(),
            dict(forms),
            missing={"sale-open": ("rnc_missing",)},
            settlement=False,
        )
    ready = with_unreviewed(
        close, change.get("count", 0), change.get("month_unknown", False)
    )
    assert ready["filing_ready"] is False, reason


def test_on_the_month_close_is_unchanged() -> None:
    start, end = month_period("2026-10")
    on = _october(_open_month(), settlement=True)
    assert on == month_close("2026-10", DAY, _open_month(), dict(STANDING))
    assert on == {
        "month": "2026-10",
        "today": DAY,
        "payment_methods": list(PAYMENT_METHODS),
        "dgii_forms": STANDING,
        "dgii_foreign_currency": foreign_currency({}),
        **summarize(_open_month(), start, end),
    }
    assert SETTLEMENT_KEYS <= set(on)
    [block] = on["currencies"]
    assert BLOCK_SETTLEMENT_KEYS <= set(block)
    assert [line["status"] for line in on["cuentas_por_cobrar"]] == ["pendiente"]
    assert empty_month("2026-10") == empty_month("2026-10", settlement=True)


def test_off_the_api_hides_and_refuses_settlement(alice: Owner, settlement_off) -> None:  # noqa: F811, ANN001
    assert alice.get("/workspace").json()["settlement_available"] is False
    month = alice.get("/month-close", month="2026-10")
    assert month.status_code == 200, month.text
    assert SETTLEMENT_KEYS.isdisjoint(month.json())
    assert month.json()["filing_ready"] is True
    refused = alice.get("/open-items")
    assert (refused.status_code, refused.json()["code"]) == (
        404,
        "business_settlement_unavailable",
    )
    mark = alice.client.patch(
        f"{BASE}/month-close/documents/{uuid4()}",
        json={"status": "pagado", "settled_on": "2026-10-05", "payment_method": "efectivo"},
        headers={**alice.auth, "Idempotency-Key": str(uuid4())},
    )
    assert (mark.status_code, mark.json()["code"]) == (
        404,
        "business_settlement_unavailable",
    )


def test_on_the_api_offers_settlement_as_before(alice: Owner, settlement_on) -> None:  # noqa: F811, ANN001
    assert alice.get("/workspace").json()["settlement_available"] is True
    month = alice.get("/month-close", month="2026-10").json()
    assert SETTLEMENT_KEYS <= set(month)
    assert alice.get("/open-items").status_code == 200


@pytest.mark.parametrize("mark", [PAYABLE_BILL_MARK, PAID_BILL_MARK])
def test_the_due_notice_mark_shows_only_while_settlement_is_on(
    mark: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolution = BusinessResolution(facts=BusinessFacts(), bill_mark=mark)
    monkeypatch.setenv(SWITCH, "false")
    assert shown_bill_mark(resolution) is None
    monkeypatch.setenv(SWITCH, "true")
    assert shown_bill_mark(resolution) == mark
