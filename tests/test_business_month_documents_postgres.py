"""Over HTTP on the real app, Auth and Postgres: each currency block of the
month close counts the month's documents from the same list as its figures:
how many the figures count, how many there are in all, and how many the
Bandeja still holds. A receipt waiting in the Bandeja adds to the month's
documents and changes no figure.
"""

from __future__ import annotations

from argus.domain.business import ledger

from tests import test_business_approve_unpaid_postgres as unpaid
from tests.test_business_document_type_postgres import (  # noqa: F401
    API,
    SUPPLIER_RNC,
    _own_rnc,
    _upload,
    web,
)
from tests.test_business_document_type_postgres import pytestmark as _local_supabase

pytestmark = _local_supabase

MONTH = "2026-09"
FIGURES = ("net_result", "income_before_itbis", "expense_before_itbis", "itbis_charged")
COUNTS = ("documents_counted", "documents_total", "documents_in_bandeja")


def _month(world, month: str = MONTH) -> dict:  # noqa: ANN001
    answer = world.client.get(
        f"{API}/business/month-close",
        params={"month": month},
        headers=world.alice.headers,
    )
    assert answer.status_code == 200, answer.text
    return answer.json()


def _counts(block: dict) -> tuple[int, int, int]:
    return tuple(block[name] for name in COUNTS)


def test_a_receipt_in_the_bandeja_is_one_of_the_months_documents_and_no_figure(
    web,  # noqa: ANN001, F811
) -> None:
    _own_rnc(web)
    draft, _ = unpaid._recorded(web, "expense", "B0100000061")
    unpaid._declare(web, draft, category="02", payment_method="01")
    unpaid._recorded(
        web,
        "income",
        "B0100000062",
        id_type="1",
        income_type="1",
        billed_amount="1000.00",
        credit="1180.00",
    )

    [pesos] = _month(web)["currencies"]
    assert pesos["currency"] == "DOP"
    assert _counts(pesos) == (2, 2, 0)
    approved = {name: pesos[name] for name in FIGURES}
    assert approved == {
        "net_result": "0.00",
        "income_before_itbis": "1000.00",
        "expense_before_itbis": "1000.00",
        "itbis_charged": "180.00",
    }

    _upload(web, SUPPLIER_RNC, occurred_on=f"{MONTH}-10", total="5900.00")
    waiting = _month(web)
    [still] = waiting["currencies"]
    assert _counts(still) == (2, 3, 1)
    assert waiting["unreviewed_movements_count"] == 1
    assert {name: still[name] for name in FIGURES} == approved
    assert _month(web, "2026-10")["unreviewed_movements_count"] == 0


def test_a_note_reviewed_in_dollars_waits_in_the_dollar_block(
    web,  # noqa: ANN001, F811
) -> None:
    unpaid._reviewed(web, "expense", "B0100000081", facts=unpaid._known({"currency": "USD", "amount": "118.00"}))
    unpaid._note(web, web.alice, "Taxi al aeropuerto")

    # A note counts by the day it arrived: today.
    month = _month(web, ledger.today().strftime("%Y-%m"))
    by_currency = {block["currency"]: _counts(block) for block in month["currencies"]}
    assert by_currency["USD"] == (0, 1, 1)
    assert month["unreviewed_movements_count"] == sum(c[2] for c in by_currency.values())
