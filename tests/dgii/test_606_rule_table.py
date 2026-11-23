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
from zipfile import ZipFile

import pytest
from argus.domain.business import dgii_606_rules, export, ledger
from argus.domain.business.contracts.dgii import (
    PurchaseDeclaration,
    cell_date,
    date_cell,
    period_text,
    printed_date,
)
from argus.domain.business.contracts.facts import (
    BusinessFacts,
    FiscalFacts,
    Known,
    Unknown,
)
from argus.domain.business.dgii_606_rules import RULES, Context, broken, itbis_limit
from argus.domain.business.dgii_columns import PURCHASE_COLUMNS
from argus.domain.business.dgii_export import (
    fiscal_manifest,
    line_assessments,
    line_values,
    line_verdicts,
)
from argus.domain.business.dgii_validation import FiscalRecord
from argus.domain.business.missing_reasons import DETAIL_MISSING
from argus.domain.business.reporting_file import RecordsExport, build_file
from argus.domain.business.reporting_projection import with_export_verdicts
from argus.domain.business.reporting_query import ReportRecord, ReportRequestV2
from argus.domain.business.reporting_store import ExportSource

SOURCE = uuid4()
TODAY = date(2026, 11, 14)
PAID = date(2026, 10, 20)
#: An amount a receipt can hold and no 606 cell can: 30 whole digits.
BEYOND = "123456789012345678901234567890"


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


class LinuxDate(date):
    """A date as the Linux server formats it: ``%Y`` leaves a year below 1000
    unpadded. macOS pads it, so a plain date hides the difference there."""

    def strftime(self, pattern: str) -> str:
        return super().strftime(pattern.replace("%Y", str(self.year)))


def paid(subject: FiscalRecord, on: date) -> FiscalRecord:
    """The record paid ``on``, the date kept as given."""

    return replace(
        subject, declaration=subject.declaration.model_copy(update={"paid_on": on})
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
        "C4 NCF sequence 0", "ncf_sequence_zero", "invalid_ncf", record(ncf="B0100000000")
    ),
    held(
        "C4 e-NCF sequence 0",
        "ncf_sequence_zero",
        "invalid_ncf",
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
    # A year typed short is held by its date, on Linux as on macOS.
    held(
        "F2 payment year 0026",
        "payment_before_invoice",
        "payment_before_invoice",
        paid(record(), LinuxDate(26, 10, 5)),
    ),
    held(
        "B5 invoice year 0026",
        "invoice_date_before_series",
        "date_too_old",
        record(occurred=LinuxDate(26, 10, 5), itbis="160.00"),
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
    # Measured on DGII's pre-validator: the 18% is rounded to cents, half to even.
    held(
        "E1 measured: base 100.03, ITBIS 18.57",
        "itbis_over_cap",
        "itbis_over_limit",
        record(base="100.03", itbis="18.57"),
    ),
    held(
        "E1 a half cent rounds down to the even cent",
        "itbis_over_cap",
        "itbis_over_limit",
        record(base="100.25", itbis="18.60"),
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
    # Measured on DGII's pre-validator: the 10% is not rounded.
    held(
        "E9 measured: total 1234.57, propina 123.46",
        "tip_over_limit",
        "tip_over_limit",
        record(base="1234.57", itbis="0.00", legal_tip="123.46"),
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
        "B04 dated more than 30 days after its purchase",
        "fiscal_credit_tax_treatment_required",
        "credit_note_too_late",
        *credit(occurred=date(2026, 11, 5)),
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
    listo("E1 measured: base 100.03, ITBIS 18.56", record(base="100.03", itbis="18.56")),
    listo(
        "E1 a half cent rounds down to the even cent",
        record(base="100.25", itbis="18.59"),
    ),
    listo(
        "E1 a half cent rounds up to the even cent",
        record(base="100.75", itbis="18.69"),
    ),
    listo("E6 proporcionalidad equal to ITBIS", record(itbis_proportionality="180.00")),
    listo("E8 retenido equal to ITBIS", record(itbis_withheld="180.00", paid_on=PAID)),
    listo("E9 propina exactly 10%", record(legal_tip="100.00")),
    listo(
        "E9 measured: total 1234.57, propina 123.45",
        record(base="1234.57", itbis="0.00", legal_tip="123.45"),
    ),
    listo("G1 B11 with a cédula", record(ncf="B1100000123", party=PERSON, id_type="2")),
    listo("G2 B13 with the own RNC and no ITBIS", own("B1300000123")),
    listo("G7 B03 modifies a B01", record(ncf="B0300000123", modified_ncf="B0100000001")),
    listo("B04 linked to its B01", *credit()),
)

# An amount no 606 cell holds is held by the line's own checks. Neither has a
# named fix yet.
BEYOND_A_CELL = (
    held(
        "a total no 606 cell holds",
        "fiscal_invoice_total_conflict",
        DETAIL_MISSING,
        record(extra_gross=BEYOND),
    ),
    held(
        "an ITBIS no 606 cell holds",
        "fiscal_amount_precision_or_limit",
        DETAIL_MISSING,
        record(itbis=BEYOND),
    ),
)

CASES = HELD + NAMED + BEYOND_A_CELL + ACCEPTED


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
    @pytest.mark.parametrize("case", named(HELD + NAMED + BEYOND_A_CELL))
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

    def test_a_missing_value_is_not_also_called_wrong(self):
        subject = record(ncf="B1100000123", party=None, id_type=None)
        found = line_verdicts((subject,), rnc=FILER, captured_on=TODAY)
        assert found[subject.activity_id] == ("missing_rnc",)

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

    @pytest.mark.parametrize(
        ("cell", "held_by"),
        [
            ("billed_amount", []),
            ("selective_tax", []),
            ("itbis", ["itbis_over_cap", "itbis_over_total"]),
        ],
    )
    def test_a_cell_beyond_the_606_limit_is_judged_not_raised(self, cell, held_by):
        line = self.line(record()) | {cell: BEYOND}
        assert [
            rule.id for rule in broken(line, Context(today=TODAY, period="202610"))
        ] == held_by

    @pytest.mark.parametrize(
        ("base", "limit"),
        [("100.03", "18.56"), ("100.25", "18.59"), ("100.75", "18.69")],
    )
    def test_the_itbis_ceiling_rounds_the_rate_to_cents_half_to_even(self, base, limit):
        assert itbis_limit(Decimal(base)) == Decimal(limit)


class TestADateCell:
    @pytest.mark.parametrize("year", (26, 999, 1000, 2026))
    def test_the_year_has_four_digits_on_every_platform(self, year):
        day = LinuxDate(year, 10, 5)
        assert (date_cell(day), period_text(day), printed_date(day)) == (
            f"{year:04d}1005",
            f"{year:04d}10",
            f"05/10/{year:04d}",
        )

    @pytest.mark.parametrize("year", (26, 999, 1000, 2026))
    def test_the_rules_read_back_the_date_the_file_writes(self, year):
        assert cell_date(date_cell(LinuxDate(year, 10, 5))) == date(year, 10, 5)

    def test_an_empty_cell_has_no_date(self):
        assert cell_date("") is None


#: 8:30 pm in Santo Domingo on 2026-10-09; the UTC date is already the 10th.
EVENING = datetime(2026, 10, 10, 0, 30, tzinfo=timezone.utc)


class TestTodayIsTheDominicanDay:
    def test_the_business_day_of_an_instant_is_santo_domingos(self):
        assert ledger.business_day(EVENING) == date(2026, 10, 9)

    def test_the_handoff_holds_tomorrows_invoice_and_takes_todays(self):
        tomorrow, today = (
            record(ncf=f"B01000001{day:02d}", occurred=date(2026, 10, day))
            for day in (10, 9)
        )
        archive = export.build_archive(
            export.ExportSnapshot(
                period=export.ExportPeriod(date(2026, 10, 1), date(2026, 10, 31)),
                activities=(),
                sources=(),
                unresolved=(),
                captured_at=EVENING,
                fiscal_records=(tomorrow, today),
                business_rnc=FILER,
            ),
            lambda _: None,
        )
        with ZipFile(io.BytesIO(archive)) as files:
            issues = json.loads(files.read("manifest.json"))["dgii"]["issues"]
        held_rows = [
            (issue["activity_id"], issue["code"])
            for issue in issues
            if issue["activity_id"]
        ]
        assert held_rows == [(tomorrow.activity_id, "invoice_date_in_future")]


class TestRegistrosAndTheExcelAgree:
    @pytest.mark.parametrize("case", named(CASES))
    def test_the_excel_carries_a_row_only_when_registros_says_listo(self, case):
        verdicts = line_assessments(case.records, rnc=FILER, captured_on=TODAY)
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
        assert len(lines) == sum(
            item.stage == "ready_for_export" and start <= item.report_date <= end
            for item in judged
        )
