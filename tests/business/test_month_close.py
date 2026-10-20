"""Month close math, the closed rule, a repeated settlement, and space scope."""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from argus.api.business_month_close_schemas import MonthClose
from argus.domain.business.authority import ActionContext, ActionError
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.contracts.dgii import SalesDeclaration
from argus.domain.business.contracts.facts import (
    BusinessFacts,
    BusinessResolution,
    FiscalFacts,
    Known,
    OwnerFunding,
    WholeBusinessShare,
)
from argus.domain.business.dgii_columns import SALES_COLUMNS
from argus.domain.business.dgii_export import build_fiscal_packet
from argus.domain.business.dgii_validation import FiscalRecord, credit_note
from argus.domain.business.month_close import (
    IMPLICIT,
    MonthDocument,
    Settlement,
    before_itbis,
    formato_totals,
    itbis_owed,
    month_period,
    net_result,
    open_items,
    project_documents,
    read_fiscal,
    set_document_status,
    summarize,
    to_minor,
)
from argus.domain.business.month_close_store import settle_document
from psycopg.errors import UniqueViolation

DAY = date(2026, 10, 5)


class Allow:
    def __init__(self, capabilities=("prepare",)):
        self.capabilities = frozenset(capabilities)

    def require(self, capability):
        if capability not in self.capabilities:
            raise ActionError("permission_denied", "business_permission_denied")


def document(**overrides) -> MonthDocument:
    values = dict(
        activity_id="doc",
        space_id="space-a",
        role="invoice",
        currency="DOP",
        total_minor=0,
        itbis_minor=0,
        occurred_on=DAY,
        rnc="131000001",
        ncf="B0100000001",
        ecf=None,
        personal=False,
        include_606=None,
        status="cobrado",
        settled_on=DAY,
        payment_method="efectivo",
    )
    values.update(overrides)
    return MonthDocument(**values)


def october():
    collected = document(
        activity_id="sale-collected",
        total_minor=11800,
        itbis_minor=1800,
        status="cobrado",
    )
    open_sale = document(
        activity_id="sale-open",
        total_minor=5900,
        itbis_minor=900,
        status="pendiente",
        settled_on=None,
        payment_method=None,
    )
    paid = document(
        activity_id="purchase-paid",
        role="receipt",
        total_minor=2360,
        itbis_minor=360,
        status="pagado",
    )
    incomplete = document(
        activity_id="purchase-open",
        role="receipt",
        total_minor=1000,
        itbis_minor=None,
        rnc=None,
        ncf=None,
        status="pendiente",
        settled_on=None,
        payment_method=None,
    )
    included = document(
        activity_id="personal-included",
        role="receipt",
        total_minor=1180,
        itbis_minor=180,
        personal=True,
        include_606=True,
        status="pagado",
    )
    excluded = document(
        activity_id="personal-excluded",
        role="receipt",
        total_minor=99999,
        itbis_minor=1,
        personal=True,
        include_606=False,
        status="pagado",
    )
    dollars = document(
        activity_id="sale-usd",
        currency="USD",
        total_minor=20000,
        itbis_minor=0,
        status="cobrado",
    )
    return [collected, open_sale, paid, incomplete, included, excluded, dollars]


def test_rounding_half_up_and_negative_net():
    assert to_minor("1.005", "DOP") == 101
    assert to_minor("1.004", "DOP") == 100
    assert to_minor("-1.005", "DOP") == -101
    assert before_itbis(11800, 1800) == 10000
    assert net_result(100, 250) == -150
    assert itbis_owed(100, 180) == -80


def test_february_period_follows_the_calendar():
    assert month_period("2024-02") == (date(2024, 2, 1), date(2024, 2, 29))
    assert month_period("2026-02") == (date(2026, 2, 1), date(2026, 2, 28))
    with pytest.raises(ValueError, match="month_invalid"):
        month_period("2026-13")


def test_summary_matches_formato_totals_for_the_fixture_month():
    documents = october()
    start, end = month_period("2026-10")
    totals = formato_totals(documents, start, end)
    summary = summarize(documents, start, end)
    dop = next(block for block in summary["currencies"] if block["currency"] == "DOP")

    assert totals["DOP"].income_before_itbis == 15000
    assert totals["DOP"].expense_before_itbis == 3000
    assert totals["DOP"].itbis_charged == 2700
    assert totals["DOP"].itbis_paid == 540
    assert dop["income_before_itbis_minor"] == 15000
    assert dop["expense_before_itbis_minor"] == 3000
    assert dop["net_result_minor"] == 12000
    assert dop["net_result"] == "120.00"
    assert dop["itbis_owed_minor"] == 2160
    assert dop["cuentas_por_cobrar_minor"] == 5900
    assert dop["cuentas_por_pagar_minor"] == 1000
    assert dop["by_status"]["invoices"]["pendiente"] == {
        "count": 1,
        "before_itbis_minor": 5000,
    }
    assert dop["by_status"]["receipts"]["pagado"]["count"] == 2
    assert "personal-excluded" not in {
        item["activity_id"]
        for item in summary["cuentas_por_pagar"] + summary["missing_ncf"]
    }
    usd = next(block for block in summary["currencies"] if block["currency"] == "USD")
    assert usd["net_result_minor"] == totals["USD"].income_before_itbis == 20000
    MonthClose.model_validate({"month": "2026-10", **summary})


def test_a_receipt_with_an_unusable_fiscal_number_stays_out_of_expense():
    start, end = month_period("2026-10")
    good = document(
        activity_id="receipt-good",
        role="receipt",
        total_minor=11800,
        itbis_minor=1800,
        ncf="B0100000001",
        status="pagado",
    )
    bad = document(
        activity_id="receipt-mistyped",
        role="receipt",
        ncf="B01-0001",
        total_minor=5900,
        itbis_minor=900,
        status="pagado",
    )
    totals = formato_totals([good, bad], start, end)
    summary = summarize([good, bad], start, end)
    dop = next(block for block in summary["currencies"] if block["currency"] == "DOP")

    assert totals["DOP"].expense_before_itbis == 10000
    assert dop["expense_before_itbis_minor"] == 10000
    assert summary["closed"] is False
    assert {
        "code": "missing_ncf",
        "activity_id": "receipt-mistyped",
        "document_kind": "receipt",
    } in summary["reasons"]


def test_a_sale_with_an_unusable_fiscal_number_keeps_the_month_open():
    start, end = month_period("2026-10")
    good = document(
        activity_id="sale-good",
        total_minor=11800,
        itbis_minor=1800,
        status="cobrado",
    )
    bad = document(
        activity_id="sale-mistyped",
        ncf="B01-0001",
        total_minor=5900,
        itbis_minor=900,
        status="cobrado",
    )
    summary = summarize([good, bad], start, end)
    dop = next(block for block in summary["currencies"] if block["currency"] == "DOP")

    assert summary["closed"] is False
    assert summary["reasons"] == [
        {
            "code": "missing_ncf",
            "activity_id": "sale-mistyped",
            "document_kind": "invoice",
        }
    ]
    assert [item["activity_id"] for item in summary["missing_ncf"]] == ["sale-mistyped"]
    assert dop["income_before_itbis_minor"] == 10000


def test_credit_notes_subtract_the_declared_amount_and_the_itbis():
    start, end = month_period("2026-10")
    sale = document(
        activity_id="sale",
        total_minor=256000,
        itbis_minor=18000,
        declared_base_minor=200000,
        ncf="B0100000001",
        status="cobrado",
    )
    credit = document(
        activity_id="credit",
        total_minor=11800,
        itbis_minor=1800,
        declared_base_minor=10000,
        ncf="B0400000001",
        status="cobrado",
    )
    totals = formato_totals([sale, credit], start, end)
    summary = summarize([sale, credit], start, end)
    dop = next(block for block in summary["currencies"] if block["currency"] == "DOP")

    assert totals["DOP"].income_before_itbis == 190000
    assert totals["DOP"].itbis_charged == 16200
    assert dop["by_status"]["invoices"]["cobrado"] == {
        "count": 2,
        "before_itbis_minor": 190000,
    }
    assert dop["income_before_itbis_minor"] == 190000
    assert dop["itbis_charged_minor"] == 16200


def test_a_personal_sale_is_not_607_income():
    start, end = month_period("2026-10")
    business = document(
        activity_id="business-sale",
        total_minor=11800,
        itbis_minor=1800,
        status="cobrado",
    )
    personal = document(
        activity_id="personal-sale",
        personal=True,
        total_minor=59000,
        itbis_minor=9000,
        status="cobrado",
    )
    totals = formato_totals([business, personal], start, end)
    summary = summarize([business, personal], start, end)

    assert totals["DOP"].income_before_itbis == 10000
    assert totals["DOP"].itbis_charged == 1800
    assert summary["closed"] is True
    assert "personal-sale" not in {
        item["activity_id"] for item in summary["missing_ncf"] + summary["reasons"]
    }


def test_sin_comprobante_counts_in_the_totals_and_never_blocks_the_close():
    start, end = month_period("2026-10")
    bought = document(
        activity_id="cash-purchase",
        role="receipt",
        total_minor=50000,
        itbis_minor=7627,
        rnc=None,
        ncf=None,
        sin_comprobante=True,
        status="pendiente",
        settled_on=None,
        payment_method=None,
    )
    sold = document(
        activity_id="cash-sale",
        total_minor=30000,
        itbis_minor=4576,
        rnc=None,
        ncf=None,
        sin_comprobante=True,
    )
    personal = document(
        activity_id="personal-cash",
        role="receipt",
        total_minor=7000,
        itbis_minor=None,
        rnc=None,
        ncf=None,
        personal=True,
        sin_comprobante=True,
    )
    fiscal = october()[2]
    documents = [bought, sold, personal, fiscal]
    totals = formato_totals(documents, start, end)["DOP"]
    summary = summarize(documents, start, end)
    [dop] = summary["currencies"]

    # The purchase's 76.27 ITBIS cannot be credited: its whole 500.00 is cost and
    # none of it is ITBIS paid. The sale's stated 45.76 ITBIS is charged.
    assert (totals.income_before_itbis, totals.expense_before_itbis) == (25424, 52000)
    assert (totals.itbis_charged, totals.itbis_paid) == (4576, 360)
    assert (dop["income_before_itbis_minor"], dop["expense_before_itbis_minor"]) == (
        25424,
        52000,
    )
    assert dop["net_result_minor"] == -26576
    assert dop["itbis_owed_minor"] == 4216
    assert dop["by_status"]["receipts"]["pendiente"] == {
        "count": 1,
        "before_itbis_minor": 50000,
    }
    assert summary["closed"] is True
    assert summary["reasons"] == []
    assert summary["missing_rnc"] == summary["missing_ncf"] == []
    [line] = summary["cuentas_por_pagar"]
    assert (line["activity_id"], line["sin_comprobante"]) == ("cash-purchase", True)


def test_a_purchase_with_a_comprobante_and_no_number_still_blocks_the_close():
    start, end = month_period("2026-10")
    missing = document(
        activity_id="missing-number",
        role="receipt",
        total_minor=1000,
        itbis_minor=None,
        rnc=None,
        ncf=None,
        status="pagado",
    )
    stated = document(
        activity_id="stated",
        role="receipt",
        total_minor=2000,
        itbis_minor=None,
        rnc=None,
        ncf=None,
        sin_comprobante=True,
        status="pagado",
    )
    summary = summarize([missing, stated], start, end)
    [dop] = summary["currencies"]

    assert summary["closed"] is False
    assert summary["reasons"] == [
        {"code": "missing_rnc", "activity_id": "missing-number", "document_kind": "receipt"},
        {"code": "missing_ncf", "activity_id": "missing-number", "document_kind": "receipt"},
    ]
    assert [line["activity_id"] for line in summary["missing_ncf"]] == ["missing-number"]
    assert dop["expense_before_itbis_minor"] == 2000


def _stated(receipt_state, **fiscal):
    source = uuid4()

    def known(value):
        return Known(value=value, origin="member_set", source_ids=(source,))

    facts = BusinessFacts(
        kind=known("expense"),
        receipt_state=known(receipt_state) if receipt_state else BusinessFacts().receipt_state,
        fiscal=FiscalFacts(**{name: known(value) for name, value in fiscal.items()})
        if fiscal
        else None,
    )
    resolution = {"business": BusinessResolution(facts=facts).model_dump(mode="json")}
    return read_fiscal(resolution, "DOP").sin_comprobante


def test_sin_comprobante_is_the_stated_receipt_state_without_a_fiscal_number():
    assert _stated("no_receipt") is True
    assert _stated("informal_receipt") is True
    assert _stated("fiscal_receipt") is False
    assert _stated(None) is False
    assert _stated("no_receipt", ncf="B0100000001") is False
    assert _stated("no_receipt", ecf="E310000000001") is False
    assert _stated("no_receipt", rnc="131000001") is True


def test_pending_rolls_into_open_balances_and_missing_fiscal_data_keeps_the_month_open():
    start, end = month_period("2026-10")
    open_month = summarize(october(), start, end)
    assert open_month["closed"] is False
    assert {reason["code"] for reason in open_month["reasons"]} == {
        "missing_rnc",
        "missing_ncf",
    }
    assert [item["activity_id"] for item in open_month["cuentas_por_cobrar"]] == [
        "sale-open"
    ]

    complete = [
        document for document in october() if document.activity_id != "purchase-open"
    ]
    closed = summarize(complete, start, end)
    assert closed["closed"] is True
    assert closed["reasons"] == []
    assert [item["activity_id"] for item in closed["cuentas_por_cobrar"]] == ["sale-open"]
    assert closed["cuentas_por_pagar"] == []


def pending(activity_id, role, day, **overrides):
    return document(
        activity_id=activity_id,
        role=role,
        occurred_on=day,
        status="pendiente",
        settled_on=None,
        payment_method=None,
        **overrides,
    )


def test_open_items_are_every_month_close_list_from_every_month_oldest_first():
    documents = [
        pending("oct-sale", "invoice", date(2026, 10, 2), total_minor=500),
        pending("aug-sale", "invoice", date(2026, 8, 30), total_minor=700),
        pending("sep-sale-b", "invoice", date(2026, 9, 16), total_minor=300),
        pending("sep-sale-a", "invoice", date(2026, 9, 16), total_minor=200),
        document(activity_id="sep-collected", occurred_on=date(2026, 9, 1)),
        pending("sep-personal-sale", "invoice", date(2026, 9, 2), personal=True),
        pending("oct-bill", "receipt", date(2026, 10, 5), total_minor=900),
        pending("sep-bill", "receipt", date(2026, 9, 3), total_minor=100),
        pending(
            "sep-personal-kept",
            "receipt",
            date(2026, 9, 4),
            personal=True,
            include_606=True,
            total_minor=50,
        ),
        pending(
            "sep-personal-left",
            "receipt",
            date(2026, 9, 4),
            personal=True,
            include_606=False,
        ),
        document(
            activity_id="sep-paid",
            role="receipt",
            status="pagado",
            occurred_on=date(2026, 9, 9),
        ),
    ]
    opened = open_items(documents)
    cobrar, pagar = opened["cuentas_por_cobrar"], opened["cuentas_por_pagar"]
    assert [item["activity_id"] for item in cobrar["items"]] == [
        "aug-sale",
        "sep-sale-a",
        "sep-sale-b",
        "oct-sale",
    ]
    assert [item["activity_id"] for item in pagar["items"]] == [
        "sep-bill",
        "sep-personal-kept",
        "oct-bill",
    ]
    assert {item["status"] for item in cobrar["items"] + pagar["items"]} == {"pendiente"}
    assert (cobrar["count"], pagar["count"]) == (4, 3)

    def by_id(items):
        return sorted(items, key=lambda item: item["activity_id"])

    for key in ("cuentas_por_cobrar", "cuentas_por_pagar"):
        by_month = []
        for month in ("2026-08", "2026-09", "2026-10"):
            by_month += summarize(documents, *month_period(month))[key]
        assert by_id(opened[key]["items"]) == by_id(by_month)


def test_the_cap_keeps_the_count_and_each_currency_total_of_every_pending_item():
    documents = [
        pending("sale-1", "invoice", date(2026, 9, 1), total_minor=1000),
        pending("sale-2", "invoice", date(2026, 9, 2), total_minor=2000),
        pending("sale-3", "invoice", date(2026, 9, 3), total_minor=4000),
        pending("sale-usd", "invoice", date(2026, 9, 4), currency="USD", total_minor=150),
    ]
    cobrar = open_items(documents, cap=2)["cuentas_por_cobrar"]
    assert [item["activity_id"] for item in cobrar["items"]] == ["sale-1", "sale-2"]
    assert cobrar["count"] == 4
    assert cobrar["totals"] == [
        {"currency": "DOP", "total_minor": 7000, "total": "70.00"},
        {"currency": "USD", "total_minor": 150, "total": "1.50"},
    ]
    assert open_items([])["cuentas_por_pagar"] == {"count": 0, "totals": [], "items": []}


def test_the_documented_cap_shows_the_oldest_hundred():
    days = [date(2026, 1, 1) + timedelta(days=index) for index in range(101)]
    documents = [
        pending(f"sale-{index:03}", "invoice", day, total_minor=1)
        for index, day in enumerate(reversed(days))
    ]
    cobrar = open_items(documents)["cuentas_por_cobrar"]
    assert len(cobrar["items"]) == 100
    assert cobrar["count"] == 101
    assert cobrar["totals"][0]["total_minor"] == 101
    assert [item["occurred_on"] for item in cobrar["items"]] == [
        day.isoformat() for day in days[:100]
    ]


def test_an_open_line_keeps_its_currency_parts_and_unknown_itbis_stays_null():
    line = open_items(
        [
            pending(
                "sale",
                "invoice",
                DAY,
                currency="USD",
                total_minor=11800,
                itbis_minor=None,
                counterparty="Cliente",
                ncf=None,
                ecf="E310000000001",
            )
        ]
    )["cuentas_por_cobrar"]["items"][0]
    assert line == {
        "activity_id": "sale",
        "document_kind": "invoice",
        "currency": "USD",
        "occurred_on": "2026-10-05",
        "total_minor": 11800,
        "total": "118.00",
        "before_itbis_minor": 11800,
        "before_itbis": "118.00",
        "itbis_minor": None,
        "itbis": None,
        "counterparty": "Cliente",
        "rnc": "131000001",
        "ncf": None,
        "ecf": "E310000000001",
        "status": "pendiente",
        "sin_comprobante": False,
    }


def test_an_empty_month_is_closed():
    start, end = month_period("2026-11")
    summary = summarize(october(), start, end)
    assert summary["closed"] is True
    assert summary["currencies"] == []


def test_the_same_settlement_twice_writes_once():
    command = Settlement("cobrado", DAY, "transferencia")
    documents = [
        document(
            activity_id="sale-open",
            status="pendiente",
            settled_on=None,
            payment_method=None,
        )
    ]
    writes = []

    def write(previous, planned):
        writes.append((previous, planned))

    role, settlement, changed = set_document_status(
        Allow(), documents, "space-a", "sale-open", command, IMPLICIT, write
    )
    again = set_document_status(
        Allow(), documents, "space-a", "sale-open", command, settlement, write
    )

    assert (role, changed, len(writes), again[2]) == ("invoice", True, 1, False)
    assert again[1] == settlement == command
    assert writes == [(IMPLICIT, command)]


def test_another_space_and_a_read_only_grant_cannot_settle():
    documents = [document(activity_id="sale-open", space_id="space-a")]
    command = Settlement("cobrado", DAY, "tarjeta")
    with pytest.raises(ActionError) as missing:
        set_document_status(
            Allow(), documents, "space-b", "sale-open", command, IMPLICIT, lambda *_: None
        )
    assert missing.value.code == "business_record_not_found"
    with pytest.raises(ActionError) as denied:
        set_document_status(
            Allow(()),
            documents,
            "space-a",
            "sale-open",
            command,
            IMPLICIT,
            lambda *_: None,
        )
    assert denied.value.code == "business_permission_denied"


def test_a_receipt_cannot_be_marked_collected():
    documents = [
        document(
            activity_id="purchase-paid",
            role="receipt",
            status="pendiente",
            settled_on=None,
            payment_method=None,
        )
    ]
    with pytest.raises(ActionError) as refused:
        set_document_status(
            Allow(),
            documents,
            "space-a",
            "purchase-paid",
            Settlement("cobrado", DAY, "efectivo"),
            IMPLICIT,
            lambda *_: None,
        )
    assert refused.value.code == "business_status_invalid"


def test_a_draft_projects_onto_the_activity_and_a_transfer_stays_out():
    source = uuid4()

    def known(value, origin="owner_stated"):
        return Known(value=value, origin=origin, verified=True, source_ids=(source,))

    facts = BusinessFacts(
        kind=known("income"),
        amount=known("118.00"),
        currency=known("DOP"),
        occurred_on=known(DAY),
        counterparty=known("Ferretería"),
        funding=known(OwnerFunding()),
        business_share=known(WholeBusinessShare(kind="all")),
        fiscal=FiscalFacts(
            rnc=known("131000001"),
            ncf=known("B0100000001"),
            itbis=known("18.00"),
        ),
    )
    resolution = {"business": BusinessResolution(facts=facts).model_dump(mode="json")}
    parts = read_fiscal(resolution, "DOP")
    assert (
        parts.rnc,
        parts.ncf,
        parts.itbis_minor,
        parts.personal,
        parts.counterparty,
    ) == ("131000001", "B0100000001", 1800, False, "Ferretería")
    sale = {
        "activity_id": "sale",
        "kind": "income",
        "amount_minor": 11800,
        "currency": "DOP",
        "occurred_at": "2026-10-05T12:00:00-04:00",
        "time_zone": "America/Santo_Domingo",
    }
    transfer = {**sale, "activity_id": "move", "kind": "transfer", "amount_minor": 1}
    documents = project_documents(
        [sale, transfer],
        [{"activity_id": "sale", "resolution": resolution}],
        {},
        "space-a",
    )
    assert [item.activity_id for item in documents] == ["sale"]
    assert documents[0].status == "pendiente"
    assert documents[0].total_minor == 11800
    assert documents[0].itbis_minor == 1800
    assert documents[0].counterparty == "Ferretería"
    assert read_fiscal({"business": {"schema_version": 1}}, "DOP").rnc is None


def _known(value, source: UUID):
    return Known(value=value, origin="member_set", source_ids=(source,))


def _sale_record(
    index: int,
    *,
    ncf: str,
    billed: str,
    itbis: str,
    gross: str,
    legal_tip: str = "0.00",
    modified_ncf: str | None = None,
    bank: str | None = None,
) -> FiscalRecord:
    source = UUID(int=index)
    day = date(2026, 9, 10 + index)
    declaration = SalesDeclaration(
        form="607",
        id_type="1",
        modified_ncf=modified_ncf,
        selective_tax="0.00",
        other_taxes="0.00",
        legal_tip=legal_tip,
        income_type="1",
        withheld_on=None,
        billed_amount=billed,
        itbis_withheld_by_third_parties="0.00",
        itbis_perceived="0.00",
        income_withheld_by_third_parties="0.00",
        income_perceived="0.00",
        cash="0.00",
        bank=bank if bank is not None else gross,
        card="0.00",
        credit="0.00",
        gift="0.00",
        barter="0.00",
        other_payment="0.00",
    )
    facts = BusinessFacts(
        kind=_known("income", source),
        amount=_known(gross, source),
        currency=_known("DOP", source),
        occurred_on=_known(day, source),
        fiscal=FiscalFacts(
            rnc=_known("199990099", source),
            ncf=_known(ncf, source),
            itbis=_known(itbis, source),
        ),
    )
    return FiscalRecord(
        str(UUID(int=index + 50)),
        1,
        str(UUID(int=index + 80)),
        2,
        day,
        gross,
        "DOP",
        "income",
        facts,
        declaration,
        (str(source),),
    )


def _project(records: tuple[FiscalRecord, ...]) -> list[MonthDocument]:
    activities = []
    resolutions = []
    for record in records:
        activities.append(
            {
                "activity_id": record.activity_id,
                "kind": record.kind,
                "amount_minor": to_minor(record.amount, record.currency),
                "currency": record.currency,
                "occurred_at": f"{record.occurred_on.isoformat()}T12:00:00-04:00",
                "time_zone": "America/Santo_Domingo",
            }
        )
        resolutions.append(
            {
                "activity_id": record.activity_id,
                "resolution": {
                    "business": BusinessResolution(
                        facts=record.facts, dgii=record.declaration
                    ).model_dump(mode="json")
                },
            }
        )
    return project_documents(activities, resolutions, {}, "space-a")


def _export_607_income(result) -> Decimal:
    billed_at = next(
        index for index, (name, _label) in enumerate(SALES_COLUMNS) if name == "billed_amount"
    )
    ncf_at = next(index for index, (name, _label) in enumerate(SALES_COLUMNS) if name == "ncf")
    income = Decimal(result.manifest["consumption_summary"]["base"])
    lines = (
        result.files["dgii/DGII_F_607_199990013_202609.TXT"].decode("ascii").splitlines()[1:]
    )
    for line in lines:
        fields = line.split("|")
        sign = -1 if credit_note(fields[ncf_at]) else 1
        income += sign * Decimal(fields[billed_at])
    return income


def test_607_income_matches_the_export_when_billed_amount_is_not_total_minus_itbis():
    from tests.dgii.test_packet import packet, practice_records

    original = _sale_record(
        1, ncf="B0100000099", billed="2000.00", itbis="360.00", gross="2560.00", legal_tip="200.00"
    )
    credit = _sale_record(
        2,
        ncf="B0400000099",
        billed="100.00",
        itbis="18.00",
        gross="118.00",
        modified_ncf="B0100000099",
        bank="0.00",
    )
    records = (*practice_records(), original, credit)
    result = packet(records)
    assert result.manifest["issues"] == []
    documents = _project(record for record in records if record.kind == "income")
    start, end = month_period("2026-09")
    income = formato_totals(documents, start, end)["DOP"].income_before_itbis
    assert income == to_minor(format(_export_607_income(result), "f"), "DOP")


def test_an_ecf_sale_is_outside_607_income():
    paper = _sale_record(3, ncf="B0100000098", billed="1000.00", itbis="180.00", gross="1180.00")
    electronic = _sale_record(
        4, ncf="E310000000001", billed="5000.00", itbis="900.00", gross="5900.00"
    )
    result = build_fiscal_packet(
        (paper, electronic),
        rnc="199990013",
        business_name="Taller Ensayo",
        start=date(2026, 9, 1),
        end=date(2026, 9, 30),
        captured_on=date(2026, 10, 18),
    )
    assert any(issue["code"] == "fiscal_607_ecf_excluded" for issue in result.manifest["issues"])
    documents = _project((paper, electronic))
    start, end = month_period("2026-09")
    income = formato_totals(documents, start, end)["DOP"].income_before_itbis
    assert income == to_minor("1000.00", "DOP")


class _Lock:
    def __init__(self, row):
        self.row = row

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _query, _params):
        return None

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self, row, *, insert_conflicts: bool):
        self.row = row
        self.insert_conflicts = insert_conflicts

    def cursor(self, row_factory=None):
        return _Lock(self.row)

    def execute(self, query, _params=None):
        if self.insert_conflicts and query.lstrip().startswith(
            "insert into public.business_document_settlements"
        ):
            raise UniqueViolation("business_document_settlements_pkey")

    def transaction(self):
        return nullcontext()


def _race_world():
    space_id = uuid4()
    actor_id = uuid4()
    owner_id = uuid4()
    activity_id = uuid4()
    context = ActionContext(
        actor=TrustedActor(
            actor_id=actor_id, actor_kind="member", space_id=space_id
        ),
        grant_id=uuid4(),
        owner_id=str(owner_id),
        space_name="Race",
    )
    pending = document(
        activity_id=str(activity_id),
        space_id=str(space_id),
        status="pendiente",
        settled_on=None,
        payment_method=None,
    )
    return context, activity_id, pending


def _patch_store(monkeypatch, connections, pending):
    from argus.domain.business import month_close_store as store

    class Auth:
        def __init__(self, context):
            self.context = context

        def require(self, _capability):
            return None

    calls = {"n": 0}

    @contextmanager
    def session(_authority, context, _capability):
        connection = connections[calls["n"]]
        calls["n"] += 1
        yield connection, Auth(context)

    def collect(_authority, _connection, auth_context):
        activity = {
            "activity_id": pending.activity_id,
            "kind": "income",
        }
        return [pending], {pending.activity_id: activity}

    monkeypatch.setattr(store, "_session", session)
    monkeypatch.setattr(store, "_collect", collect)


def test_a_concurrent_first_settle_returns_the_winner_row(monkeypatch):
    context, activity_id, pending = _race_world()
    command = Settlement("cobrado", DAY, "transferencia")
    winner = {
        "status": command.status,
        "settled_on": command.settled_on,
        "payment_method": command.payment_method,
    }
    _patch_store(
        monkeypatch,
        [
            _Connection(None, insert_conflicts=True),
            _Connection(winner, insert_conflicts=False),
        ],
        pending,
    )
    result = settle_document(None, context, str(activity_id), command)
    assert result["changed"] is False
    assert result["status"] == "cobrado"
    assert result["settled_on"] == DAY
    assert result["payment_method"] == "transferencia"


def test_a_settlement_conflict_that_survives_the_retry_is_409(monkeypatch):
    context, activity_id, pending = _race_world()
    command = Settlement("cobrado", DAY, "transferencia")
    _patch_store(
        monkeypatch,
        [
            _Connection(None, insert_conflicts=True),
            _Connection(None, insert_conflicts=True),
        ],
        pending,
    )
    with pytest.raises(ActionError) as refused:
        settle_document(None, context, str(activity_id), command)
    assert refused.value.result.outcome == "idempotency_conflict"
    assert refused.value.code == "business_document_settlement_conflict"
