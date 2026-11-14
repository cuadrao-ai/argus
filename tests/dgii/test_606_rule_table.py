"""Listo in Registros means DGII's tools accept the 606 row.

Each case is one clean synthetic purchase with one thing changed. A held case
names the rule that held it and the word Registros shows. An accepted edge
stays Listo. Every identifier is synthetic with a valid check digit.
"""

from __future__ import annotations

import calendar
import csv
import io
import json
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from argus.domain.business import dgii_606_rules
from argus.domain.business.contracts.dgii import PurchaseDeclaration
from argus.domain.business.contracts.facts import (
    BusinessFacts,
    FiscalFacts,
    Known,
    Unknown,
)
from argus.domain.business.dgii_606_rules import RULES, Context, broken, itbis_limit
from argus.domain.business.dgii_columns import PURCHASE_COLUMNS
from argus.domain.business.dgii_export import fiscal_manifest, line_values, line_verdicts
from argus.domain.business.dgii_line import MISSING_ORDER
from argus.domain.business.dgii_validation import FiscalRecord
from argus.domain.business.reporting_file import RecordsExport, build_file
from argus.domain.business.reporting_projection import with_export_verdicts
from argus.domain.business.reporting_query import ReportRecord, ReportRequestV2
from argus.domain.business.reporting_store import ExportSource

from scripts import generate_records_file_words

SOURCE = uuid4()
TODAY = date(2026, 11, 14)
PAID = date(2026, 10, 20)


def rnc(base: str) -> str:
    remainder = sum(int(a) * int(b) for a, b in zip(base, "79865432", strict=True)) % 11
    return base + str(2 if remainder == 0 else 1 if remainder == 1 else 11 - remainder)


def cedula(base: str) -> str:
    products = [int(a) * int(b) for a, b in zip(base, "1212121212", strict=True)]
    return base + str(-sum(n // 10 + n % 10 for n in products) % 10)


FILER = rnc("13100001")
SUPPLIER = rnc("10100002")
PERSON = cedula("0010000003")


def known(value):
    return Known(value=value, origin="member_set", source_ids=(SOURCE,))


def record(
    *,
    ncf="B0100000123",
    party=SUPPLIER,
    id_type="1",
    category="02",
    base="1000.00",
    itbis="180.00",
    occurred=date(2026, 10, 5),
    kind="expense",
    extra_gross="0",
    **declared,
) -> FiscalRecord:
    side = "services_amount" if category in {"02", "03", "07", "11"} else "goods_amount"
    fields = dict.fromkeys(
        name
        for name, field in PurchaseDeclaration.model_fields.items()
        if field.is_required()
    )
    fields |= {"form": "606", "id_type": id_type, "category": category, side: base}
    fields |= {"payment_method": "01"} | declared
    declaration = PurchaseDeclaration(**fields)
    gross = (
        Decimal(base)
        + Decimal(itbis)
        + sum(
            Decimal(fields[name] or "0")
            for name in ("selective_tax", "other_taxes", "legal_tip")
        )
        + Decimal(extra_gross)
    )
    facts = BusinessFacts(
        kind=known(kind),
        amount=known(f"{gross:.2f}"),
        currency=known("DOP"),
        occurred_on=known(occurred),
        fiscal=FiscalFacts(
            rnc=known(party) if party else Unknown(),
            ncf=known(ncf),
            itbis=known(itbis),
        ),
    )
    return FiscalRecord(
        str(uuid4()),
        1,
        str(uuid4()),
        1,
        occurred,
        f"{gross:.2f}",
        "DOP",
        kind,
        "recibo",
        facts,
        declaration,
        (str(SOURCE),),
    )


def credit(original_ncf="B0100000777", **changes) -> tuple[FiscalRecord, ...]:
    original = record(ncf=original_ncf)
    fields = dict(
        ncf="B0400000123",
        kind="refund",
        occurred=date(2026, 10, 9),
        base="100.00",
        itbis="18.00",
        modified_ncf=original_ncf,
        payment_method="06",
        actual_refund=True,
        purchase_activity_id=original.activity_id,
    )
    return record(**(fields | changes)), original


@dataclass(frozen=True)
class Case:
    name: str
    records: tuple[FiscalRecord, ...]
    #: The rule or legacy code that holds the first record, and its word.
    code: str | None = None
    word: str | None = None

    @property
    def subject(self) -> FiscalRecord:
        return self.records[0]


def held(name: str, code: str, word: str, *records: FiscalRecord) -> Case:
    return Case(name, records, code, word)


def listo(name: str, *records: FiscalRecord) -> Case:
    return Case(name, records)


def own(ncf: str, **changes) -> FiscalRecord:
    """A document the Business issues to itself: a gasto menor or a pago al exterior."""

    return record(ncf=ncf, party=FILER, **({"itbis": "0.00"} | changes))


HELD = (
    # C4 and G7: DGII's sequence starts at 1.
    held(
        "C4 NCF sequence 0", "ncf_sequence_zero", "ncf_invalid", record(ncf="B0100000000")
    ),
    held(
        "C4 e-NCF sequence 0",
        "ncf_sequence_zero",
        "ncf_invalid",
        record(ncf="E310000000000"),
    ),
    held(
        "G7 modified NCF sequence 0",
        "modified_ncf_sequence_zero",
        "modified_ncf_invalid",
        record(ncf="B0300000123", modified_ncf="B0100000000"),
    ),
    # B5, F1, F8: the date window.
    held(
        "B5 invoice dated tomorrow",
        "invoice_date_in_future",
        "date_in_future",
        record(occurred=date(2026, 11, 15)),
    ),
    held(
        "B5 invoice dated 2003",
        "invoice_date_before_series",
        "date_too_old",
        record(occurred=date(2003, 5, 5), itbis="160.00"),
    ),
    held(
        "F8 B-series before 2018-05",
        "invoice_date_before_series",
        "date_too_old",
        record(occurred=date(2018, 4, 30)),
    ),
    held(
        "F8 E-series before 2019-01",
        "invoice_date_before_series",
        "date_too_old",
        record(ncf="E310000000123", occurred=date(2018, 12, 31)),
    ),
    held(
        "F8 B17 before 2019-04",
        "invoice_date_before_series",
        "date_too_old",
        own("B1700000123", occurred=date(2019, 3, 31)),
    ),
    held(
        "F1 paid tomorrow",
        "payment_date_in_future",
        "payment_date_in_future",
        record(occurred=date(2026, 11, 10), paid_on=date(2026, 11, 15)),
    ),
    held(
        "F2 paid before the invoice",
        "payment_before_invoice",
        "payment_before_invoice",
        record(paid_on=date(2026, 10, 4)),
    ),
    # E1, E2: DGII's ITBIS ceiling.
    held(
        "E1 ITBIS 30% of base",
        "itbis_over_cap",
        "itbis_over_limit",
        record(itbis="300.00"),
    ),
    held(
        "E1 ITBIS 18% + 0.56",
        "itbis_over_cap",
        "itbis_over_limit",
        record(itbis="180.56"),
    ),
    held(
        "E1 ISC raises the base, one cent over",
        "itbis_over_cap",
        "itbis_over_limit",
        record(itbis="198.56", selective_tax="100.00"),
    ),
    held(
        "E2 ITBIS above the total",
        "itbis_over_total",
        "itbis_over_limit",
        record(base="100.00", itbis="150.00"),
    ),
    # E6 to E9.
    held(
        "E6 proporcionalidad above ITBIS",
        "itbis_proportionality_over_itbis",
        "itbis_proportionality_over_itbis",
        record(itbis_proportionality="180.01"),
    ),
    held(
        "E7 retenido with no ITBIS",
        "itbis_withheld_without_itbis",
        "itbis_withheld_over_itbis",
        record(itbis="0.00", itbis_withheld="50.00", paid_on=PAID),
    ),
    held(
        "E8 retenido above ITBIS",
        "itbis_withheld_over_itbis",
        "itbis_withheld_over_itbis",
        record(itbis_withheld="180.01", paid_on=PAID),
    ),
    held(
        "E9 propina above 10% of the total",
        "tip_over_limit",
        "tip_over_limit",
        record(legal_tip="100.01"),
    ),
    # G1, G2.
    held(
        "G1 B11 with a 9-digit RNC",
        "purchase_receipt_needs_cedula",
        "purchase_receipt_needs_cedula",
        record(ncf="B1100000123"),
    ),
    held(
        "G2 B13 with ITBIS",
        "minor_expense_has_itbis",
        "minor_expense_has_itbis",
        own("B1300000123", itbis="180.00"),
    ),
    held(
        "G2 E43 with ITBIS",
        "minor_expense_has_itbis",
        "minor_expense_has_itbis",
        own("E430000000123", itbis="0.01"),
    ),
)

#: Held before this change as "Falta un dato"; now each says what is wrong.
NAMED = (
    held(
        "B12 same RNC and NCF twice",
        "fiscal_duplicate_document",
        "duplicate_document",
        record(),
        record(),
    ),
    held(
        "G2 B13 with another RNC",
        "fiscal_supplier_must_match_filer",
        "own_rnc_required",
        record(ncf="B1300000123", itbis="0.00"),
    ),
    held(
        "G3 B17 with another RNC",
        "fiscal_supplier_must_match_filer",
        "own_rnc_required",
        record(ncf="B1700000123", itbis="0.00"),
    ),
    held(
        "E5 ITBIS al costo above ITBIS",
        "fiscal_itbis_cost_exceeds_tax",
        "itbis_cost_over_itbis",
        record(itbis_cost="500.00"),
    ),
    held(
        "F9 retenido with no payment date",
        "fiscal_payment_date_required",
        "payment_date_missing",
        record(itbis_withheld="50.00"),
    ),
    held(
        "F7 paid and withheld the next month",
        "fiscal_payment_date_after_period",
        "payment_after_month",
        record(
            ncf="B1100000123",
            party=PERSON,
            id_type="2",
            itbis_withheld="180.00",
            paid_on=date(2026, 11, 3),
        ),
    ),
    held(
        "D3 Servicios and Bienes are 0",
        "fiscal_billed_amount_must_be_positive",
        "billed_amount_zero",
        record(base="0.00", itbis="0.00", extra_gross="5"),
    ),
    held(
        "D3 ITBIS and a tip with no Servicios or Bienes yet",
        "fiscal_billed_amount_must_be_positive",
        "billed_amount_zero",
        record(base="0.00", legal_tip="5.00"),
    ),
    held(
        "G5 B03 with no NCF modificado",
        "fiscal_credit_reference_conflict",
        "credit_note_reference",
        record(ncf="B0300000123"),
    ),
    held(
        "G5 B04 not linked to its purchase",
        "fiscal_credit_settlement_required",
        "credit_note_reference",
        record(
            ncf="B0400000123",
            kind="refund",
            modified_ncf="B0100000777",
            payment_method="06",
        ),
    ),
    held(
        "G6 B01 with an NCF modificado",
        "fiscal_credit_reference_not_applicable",
        "modified_ncf_not_allowed",
        record(modified_ncf="B0100000001"),
    ),
    held(
        "G7 B03 modifies a B02",
        "fiscal_ncf_unsupported",
        "modified_ncf_invalid",
        record(ncf="B0300000123", modified_ncf="B0200000001"),
    ),
    held(
        "B04 not paid as a nota de crédito",
        "fiscal_credit_payment_code_required",
        "credit_note_payment_form",
        *credit(payment_method="01"),
    ),
)

ACCEPTED = (
    listo("clean B01", record()),
    listo("C4 sequence 1", record(ncf="B0100000001")),
    listo("B5 invoice dated today", record(occurred=TODAY)),
    listo("F8 B-series on 2018-05-01", record(occurred=date(2018, 5, 1))),
    listo(
        "F8 E-series on 2019-01-01",
        record(ncf="E310000000123", occurred=date(2019, 1, 1)),
    ),
    listo("F8 B17 on 2019-04-01", own("B1700000123", occurred=date(2019, 4, 1))),
    listo("F1 paid today", record(occurred=date(2026, 11, 10), paid_on=TODAY)),
    listo("F2 paid the same day", record(paid_on=date(2026, 10, 5))),
    listo("E1 ITBIS exactly 18% + 0.55", record(itbis="180.55")),
    listo("E1 16% ITBIS", record(itbis="160.00")),
    listo("E1 exempt", record(itbis="0.00")),
    listo(
        "E1 ISC raises the base",
        record(itbis="198.55", selective_tax="100.00"),
    ),
    listo("E6 proporcionalidad equal to ITBIS", record(itbis_proportionality="180.00")),
    listo("E8 retenido equal to ITBIS", record(itbis_withheld="180.00", paid_on=PAID)),
    listo("E9 propina exactly 10%", record(legal_tip="100.00")),
    listo("G1 B11 with a cédula", record(ncf="B1100000123", party=PERSON, id_type="2")),
    listo("G2 B13 with the own RNC and no ITBIS", own("B1300000123")),
    listo("G7 B03 modifies a B01", record(ncf="B0300000123", modified_ncf="B0100000001")),
    listo("B04 linked to its B01", *credit()),
)

CASES = HELD + NAMED + ACCEPTED


def verdict(case: Case):
    return line_verdicts(case.records, rnc=FILER, captured_on=TODAY)[
        case.subject.activity_id
    ]


def month_of(subject: FiscalRecord) -> tuple[date, date]:
    start = subject.occurred_on.replace(day=1)
    last = calendar.monthrange(start.year, start.month)[1]
    return start, start.replace(day=last)


def issue_codes(case: Case) -> set[str]:
    start, end = month_of(case.subject)
    manifest, _ = fiscal_manifest(
        case.records,
        rnc=FILER,
        business_name="",
        start=start,
        end=end,
        captured_on=TODAY,
    )
    return {
        issue["code"]
        for issue in manifest["issues"]
        if issue["activity_id"] == case.subject.activity_id
    }


def named(cases):
    return [pytest.param(case, id=case.name) for case in cases]


class TestEveryRule:
    @pytest.mark.parametrize("case", named(HELD + NAMED))
    def test_a_row_dgii_rejects_is_held_with_its_reason(self, case):
        assert case.code in issue_codes(case)
        assert verdict(case) == (case.word,)

    @pytest.mark.parametrize("case", named(ACCEPTED))
    def test_an_edge_dgii_accepts_stays_listo(self, case):
        assert issue_codes(case) == set()
        assert verdict(case) is None

    def test_every_rule_in_the_table_has_a_held_case(self):
        assert {rule.id for rule in RULES} == {case.code for case in HELD}

    def test_every_phase_one_rule_blocks(self):
        assert {rule.severity for rule in RULES} == {"block"}

    def test_every_rule_names_a_word_registros_can_order(self):
        assert {rule.message_key for rule in RULES} <= set(MISSING_ORDER)
        assert {case.word for case in NAMED} <= set(MISSING_ORDER)

    @pytest.mark.parametrize("locale", ("es-419", "en"))
    def test_the_locale_has_every_word_the_server_can_send(self, locale):
        words = json.loads(generate_records_file_words.build())[locale]
        assert set(MISSING_ORDER) <= set(
            words["business.transactions.layout.workflow.missing"]
        )

    def test_a_missing_value_is_not_also_called_wrong(self):
        subject = record(ncf="B1100000123", party=None, id_type=None)
        found = line_verdicts((subject,), rnc=FILER, captured_on=TODAY)
        assert found[subject.activity_id] == ("rnc_missing",)

    def test_missing_values_are_named_before_wrong_values(self):
        subject = record(itbis="300.00", payment_method=None)
        found = line_verdicts((subject,), rnc=FILER, captured_on=TODAY)
        assert found[subject.activity_id] == (
            "payment_method_missing",
            "itbis_over_limit",
        )


class TestTheTable:
    def line(self, subject: FiscalRecord) -> dict[str, str]:
        names = [name for name, _ in PURCHASE_COLUMNS]
        return dict(zip(names, line_values(subject), strict=True))

    def test_the_rules_read_the_values_the_file_writes(self):
        line = self.line(record(itbis="300.00"))
        assert len(line) == 23
        assert [
            rule.id for rule in broken(line, Context(today=TODAY, period="202610"))
        ] == ["itbis_over_cap"]

    def test_a_rule_outside_its_periods_is_not_in_force(self, monkeypatch):
        cap = next(rule for rule in RULES if rule.id == "itbis_over_cap")
        monkeypatch.setattr(
            dgii_606_rules,
            "RULES",
            (replace(cap, from_period="202611", to_period="202612"),),
        )
        line = self.line(record(itbis="300.00"))
        found = {
            period: [
                rule.id for rule in broken(line, Context(today=TODAY, period=period))
            ]
            for period in ("202610", "202611", "202612", "202701")
        }
        assert found == {
            "202610": [],
            "202611": ["itbis_over_cap"],
            "202612": ["itbis_over_cap"],
            "202701": [],
        }

    def test_the_itbis_ceiling_is_16_percent_before_2013(self):
        assert itbis_limit(Decimal("1000"), date(2012, 12, 31)) == Decimal("160.55")
        assert itbis_limit(Decimal("1000"), date(2013, 1, 1)) == Decimal("180.55")
        assert itbis_limit(Decimal("1000")) == Decimal("180.55")


class TestRegistrosAndTheExcelAgree:
    @pytest.mark.parametrize("case", named(CASES))
    def test_the_excel_carries_a_row_only_when_registros_says_listo(self, case):
        verdicts = line_verdicts(case.records, rnc=FILER, captured_on=TODAY)
        rows = tuple(
            ReportRecord(
                row_id=f"activity:{subject.activity_id}",
                linked_activity_ids=(subject.activity_id,),
                revision=1,
                report_date=subject.occurred_on,
                date_basis="document_issue",
                family="purchase",
                stage="ready_for_export",
                currency="DOP",
                gross_amount=subject.amount,
                money_kind=subject.kind,
                counterparty=f"Proveedor {index}",
            )
            for index, subject in enumerate(case.records)
        )
        judged = with_export_verdicts(rows, verdicts, frozenset())
        start, end = month_of(case.subject)
        built = build_file(
            ExportSource(
                judged,
                {subject.activity_id: subject for subject in case.records},
                datetime(TODAY.year, TODAY.month, TODAY.day, 15, tzinfo=timezone.utc),
            ),
            RecordsExport(
                report=ReportRequestV2(
                    filters={
                        "period": {
                            "kind": "custom",
                            "from_date": start.isoformat(),
                            "to_date": end.isoformat(),
                        },
                        "record_families": ["purchase"],
                    }
                ),
                mode="dgii",
                format="csv",
            ),
        )
        _header, *lines = csv.reader(io.StringIO(built.content.decode("utf-8-sig")))
        written = {line[3] for line in lines}
        row = judged[0]
        number = case.subject.facts.fiscal.ncf.value
        if case.word is None:
            assert (row.stage, row.fiscal_data, row.export_missing) == (
                "ready_for_export",
                "complete",
                None,
            )
            assert number in written
        else:
            assert (row.stage, row.fiscal_data, row.export_missing) == (
                "needs_fiscal_data",
                "missing",
                case.word,
            )
            assert number not in written
        assert len(lines) == sum(item.stage == "ready_for_export" for item in judged)
