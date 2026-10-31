from dataclasses import replace
from datetime import date

from argus.domain.business.contracts.facts import Unknown
from argus.domain.business.dgii_export import fiscal_manifest, line_verdicts
from argus.domain.business.dgii_line import first_missing, reason
from argus.domain.business.reporting_projection import with_export_verdicts
from argus.domain.business.reporting_query import ReportFilters

from tests.business.test_business_reporting_query import record, run
from tests.dgii.test_606_review_and_rnc import (
    INVALID,
    VALID,
    MapRegistry,
    purchase,
    supplier,
    with_ncf,
)

CAPTURED = date(2026, 10, 18)
SEPTEMBER = {"kind": "custom", "from_date": "2026-09-01", "to_date": "2026-09-30"}


def named(subject, index):
    return replace(subject, activity_id=f"activity-{index}")


def fiscal(subject, **changes):
    return replace(
        subject,
        facts=subject.facts.model_copy(
            update={
                "fiscal": subject.facts.fiscal.model_copy(
                    update={
                        name: getattr(subject.facts.fiscal, name).model_copy(
                            update={"value": value}
                        )
                        for name, value in changes.items()
                    }
                )
            }
        ),
    )


def mix():
    base = supplier(purchase(), VALID)
    numbered = [fiscal(base, ncf=f"B01000000{index:02}") for index in range(1, 8)]
    no_type = replace(
        numbered[1],
        declaration=numbered[1].declaration.model_copy(update={"category": None}),
    )
    no_date = replace(
        numbered[5],
        facts=numbered[5].facts.model_copy(update={"occurred_on": Unknown()}),
    )
    dollars = replace(numbered[6], currency="USD")
    return tuple(
        named(subject, index)
        for index, subject in enumerate(
            (
                numbered[0],
                no_type,
                supplier(numbered[2], None),
                supplier(numbered[3], INVALID),
                with_ncf(numbered[4], "B01000008"),
                no_date,
                dollars,
            )
        )
    )


def rows(records):
    approved = [
        record(
            f"activity:{subject.activity_id}",
            report_date=subject.occurred_on,
            stage="ready_for_export",
            linked_activity_ids=(subject.activity_id,),
        )
        for subject in records
    ]
    return (
        *approved,
        record(
            "draft:unapproved", report_date=date(2026, 9, 2), stage="awaiting_approval"
        ),
    )


class TestRegistrosReadyMatchesTheExport:
    def test_ready_count_equals_the_export_line_count_for_the_month(self):
        records = mix()
        registry = MapRegistry({})
        verdicts = line_verdicts(
            records, rnc="199990013", captured_on=CAPTURED, registry=registry
        )
        manifest, lines = fiscal_manifest(
            records,
            rnc="199990013",
            business_name="Taller Ensayo",
            start=date(2026, 9, 1),
            end=date(2026, 9, 30),
            captured_on=CAPTURED,
            registry=registry,
        )
        overview = run(
            with_export_verdicts(rows(records), verdicts),
            ReportFilters(period=SEPTEMBER),
        ).overview
        assert overview.export_lines == len(lines["606"]) + len(lines["607"]) == 1
        assert overview.needs_fiscal_data == 6
        assert overview.awaiting_approval == 1
        assert overview.ready_for_export == 1

    def test_each_row_names_the_first_thing_missing(self):
        records = mix()
        judged = with_export_verdicts(
            rows(records),
            line_verdicts(
                records, rnc="199990013", captured_on=CAPTURED, registry=MapRegistry({})
            ),
        )
        assert [(row.stage, row.export_missing, row.export_line) for row in judged] == [
            ("ready_for_export", None, True),
            ("needs_fiscal_data", "expense_type_missing", False),
            ("needs_fiscal_data", "rnc_missing", False),
            ("needs_fiscal_data", "rnc_invalid", False),
            ("needs_fiscal_data", "ncf_invalid", False),
            ("needs_fiscal_data", "date_missing", False),
            ("needs_fiscal_data", "detail_missing", False),
            ("awaiting_approval", None, False),
        ]

    def test_missing_items_read_in_spanish(self):
        assert [
            reason(code)
            for code in (
                "expense_type_missing",
                "rnc_missing",
                "rnc_invalid",
                "ncf_invalid",
                "date_missing",
                "ncf_missing",
                "payment_method_missing",
                "detail_missing",
            )
        ] == [
            "Falta el tipo de gasto",
            "Falta el RNC",
            "RNC con error",
            "NCF con error",
            "Falta la fecha",
            "Falta el NCF",
            "Falta la forma de pago",
            "Falta un dato",
        ]
        assert [reason(c, "en") for c in ("ncf_missing", "detail_missing")] == [
            "NCF is missing",
            "A detail is missing",
        ]


def required(field):
    return {"code": "fiscal_fact_required", "activity_id": "a", "field": field}


class TestFirstMissingNamesNcfAndPayment:
    subject = supplier(purchase(), VALID)

    def test_only_ncf_missing(self):
        assert first_missing(self.subject, [required("ncf")]) == "ncf_missing"

    def test_only_payment_method_missing(self):
        assert (
            first_missing(self.subject, [required("payment_method")])
            == "payment_method_missing"
        )

    def test_both_missing_names_ncf_first(self):
        issues = [required("payment_method"), required("ncf")]
        assert first_missing(self.subject, issues) == "ncf_missing"

    def test_unmapped_code_reads_as_a_missing_detail(self):
        issues = [{"code": "fiscal_unheard_of", "activity_id": "a", "field": "x"}]
        assert first_missing(self.subject, issues) == "detail_missing"
        assert reason(first_missing(self.subject, issues)) == "Falta un dato"
