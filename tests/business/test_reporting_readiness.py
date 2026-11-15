"""The row, Estado filter and count share one current readiness verdict."""

from dataclasses import replace
from datetime import date

import pytest
from argus.domain.business.contracts.facts import Unknown
from argus.domain.business.dgii_export import fiscal_manifest, line_assessments
from argus.domain.business.dgii_line import reason
from argus.domain.business.reporting_file import (
    RecordsExport,
    build_file,
    summarize_export,
)
from argus.domain.business.reporting_projection import with_export_verdicts
from argus.domain.business.reporting_query import ReportFilters
from faker import Faker
from loguru import logger

from tests.business.test_business_reporting_query import run
from tests.business.test_records_file import report, source
from tests.business.test_registros_export_ready import CAPTURED, SEPTEMBER, rows
from tests.dgii.test_606_review_and_rnc import VALID, purchase, supplier, with_ncf


@pytest.fixture
def approved_rows():
    fake = Faker()
    fake.seed_instance(2169)
    base = supplier(purchase(), VALID)
    return tuple(
        replace(
            with_ncf(base, f"B01{index:08}"),
            activity_id=fake.uuid4(),
            facts=with_ncf(base, f"B01{index:08}").facts.model_copy(
                update={
                    "counterparty": base.facts.amount.model_copy(
                        update={"value": fake.company()}
                    )
                }
            ),
        )
        for index in range(1, 35)
    )


def judge(records, projected=None, exported=frozenset()):
    verdicts = line_assessments(records, rnc="199990013", captured_on=CAPTURED)
    return with_export_verdicts(projected or rows(records), verdicts, exported)


@pytest.fixture
def mixed_rows(approved_rows):
    good, blocked, exported, several, *others = approved_rows
    exported = replace(
        exported, declaration=exported.declaration.model_copy(update={"category": None})
    )
    several = replace(
        supplier(several, None),
        declaration=several.declaration.model_copy(
            update={"category": None, "payment_method": None}
        ),
    )
    outside = tuple(
        replace(
            subject, declaration=subject.declaration.model_copy(update={"category": None})
        )
        for subject in others[:4]
    )
    records = (good, blocked, exported, several, *outside, *others[4:])
    projected = list(rows(records))
    projected[1] = projected[1].model_copy(
        update={
            "stage": "needs_review",
            "workflow_blockers": ("business_record_not_found",),
        }
    )
    # Rows outside the chosen search, currency, family and period cannot inflate it.
    for index, changes in enumerate(
        (
            {"counterparty": "outside"},
            {"currency": "USD"},
            {"family": "sale"},
            {"report_date": date(2026, 8, 1)},
        ),
        start=4,
    ):
        projected[index] = projected[index].model_copy(update=changes)
    projected = tuple(
        row.model_copy(update={"counterparty": row.counterparty or "selected"})
        for row in projected
    )
    return judge(records, projected, frozenset({exported.activity_id}))


@pytest.mark.parametrize("ready", [None, True, False])
def test_row_filter_and_count_agree_before_pagination(mixed_rows, ready):
    filters = ReportFilters(
        period=SEPTEMBER,
        currencies=("DOP",),
        record_families=("purchase",),
        q="selected",
        ready=ready,
    )
    answer = run(mixed_rows, filters)
    expected = [
        r
        for r in mixed_rows
        if r.counterparty == "selected"
        and r.currency == "DOP"
        and r.family == "purchase"
        and r.report_date.month == 9
        and (ready is None or r.ready == ready)
    ]
    assert answer.matching_count == len(expected)
    assert answer.overview.not_ready == sum(not row.ready for row in expected)
    assert answer.overview.not_ready == (0 if ready else 3)
    pages = [
        run(mixed_rows, filters, page=page) for page in range(1, answer.page_count + 1)
    ]
    assert {r.row_id for page in pages for r in page.items} == {
        r.row_id for r in expected
    }
    assert all(page.overview == answer.overview for page in pages)
    assert all(row.ready == (not row.missing) for row in expected)
    blocked, exported, several = mixed_rows[1:4]
    assert (blocked.ready, blocked.missing, blocked.stage) == (
        False,
        ("detail_missing",),
        "needs_review",
    )
    assert (exported.ready, exported.missing, exported.stage) == (
        False,
        ("expense_type_missing",),
        "exported",
    )
    assert several.missing == (
        "expense_type_missing",
        "rnc_missing",
        "payment_method_missing",
    )


@pytest.mark.parametrize("missing_type", [False, True])
def test_currency_only_is_ready_but_never_becomes_a_dgii_line(
    approved_rows, missing_type
):
    subject = replace(approved_rows[0], currency="USD")
    if missing_type:
        subject = replace(
            subject, declaration=subject.declaration.model_copy(update={"category": None})
        )
    projected = (rows((subject,))[0].model_copy(update={"currency": "USD"}),)
    [row] = judge((subject,), projected)
    assert row.ready is (not missing_type)
    assert row.missing == (("expense_type_missing",) if missing_type else ())
    if missing_type:
        assert reason(row.missing[0]) == "Falta el tipo de gasto"
    assert (row.stage, row.fiscal_data, row.export_line) == (
        "needs_fiscal_data",
        "missing",
        False,
    )
    manifest, lines = fiscal_manifest(
        (subject,),
        rnc="199990013",
        business_name="",
        start=date(2026, 9, 1),
        end=date(2026, 9, 30),
        captured_on=CAPTURED,
    )
    assert not lines["606"]
    assert manifest["forms"]["606"]["foreign_currency_pending_rate_count"] == 1
    dataset = source(row, approved={subject.activity_id: subject})
    preview = summarize_export(dataset, report())
    assert (
        preview.dgii.record_count,
        preview.dgii.pending_rate_count,
        preview.dgii.pending_fiscal_count,
    ) == (0, 1, 0)
    assert (
        build_file(
            dataset, RecordsExport(report=report(), mode="dgii", format="csv")
        ).row_count
        == 0
    )


@pytest.mark.parametrize("currency", ["DOP", "USD"])
def test_missing_ncf_keeps_all_readiness_reasons_and_legacy_export(
    approved_rows, currency
):
    original = approved_rows[0]
    ncf_only = replace(
        original,
        currency=currency,
        facts=original.facts.model_copy(
            update={"fiscal": original.facts.fiscal.model_copy(update={"ncf": Unknown()})}
        ),
    )
    subject = replace(
        ncf_only,
        declaration=ncf_only.declaration.model_copy(
            update={"category": None, "payment_method": None}
        ),
    )
    [row] = judge((subject,))
    assert row.ready is False
    assert row.missing == (
        "expense_type_missing",
        "ncf_missing",
        "payment_method_missing",
    )
    if currency == "DOP":
        assert (
            row.stage,
            row.fiscal_data,
            row.export_missing,
            row.export_missing_several,
        ) == ("needs_fiscal_data", "missing", "ncf_missing", False)
    assert row.export_line is False

    def export(record):
        manifest, lines = fiscal_manifest(
            (record,),
            rnc="199990013",
            business_name="",
            start=date(2026, 9, 1),
            end=date(2026, 9, 30),
            captured_on=CAPTURED,
        )
        [projected] = judge((record,))
        dataset = source(projected, approved={record.activity_id: record})
        result = build_file(
            dataset, RecordsExport(report=report(), mode="dgii", format="csv")
        )
        assert result.row_count == 0
        assert lines["606"] == []
        return manifest, result.content, summarize_export(dataset, report()).dgii

    before, before_file, before_preview = export(ncf_only)
    after, after_file, after_preview = export(subject)
    assert after_file == before_file
    assert after_preview == before_preview
    if currency == "DOP":
        assert (
            after["issues"]
            == before["issues"]
            == [
                {
                    "code": "fiscal_fact_required",
                    "field": "ncf",
                    "activity_id": subject.activity_id,
                }
            ]
        )
        assert after["reconciliation"] == before["reconciliation"]


def test_unmapped_blocker_logs_and_cannot_look_ready(approved_rows):
    subject = approved_rows[0]
    projected = rows((subject,))[0].model_copy(
        update={"stage": "needs_review", "workflow_blockers": ("future_blocker",)}
    )
    messages = []
    sink = logger.add(messages.append, level="WARNING")
    try:
        [row] = judge((subject,), (projected,))
    finally:
        logger.remove(sink)
    assert (row.ready, row.missing) == (False, ("detail_missing",))
    assert any(
        "future_blocker" in message and "detail_missing" in message
        for message in messages
    )


def test_blocker_and_fiscal_reasons_are_ordered_and_deduplicated(approved_rows):
    subject = replace(
        approved_rows[0],
        declaration=approved_rows[0].declaration.model_copy(update={"category": None}),
    )
    row = rows((subject,))[0].model_copy(
        update={
            "stage": "needs_review",
            "workflow_blockers": (
                "business_record_not_found",
                "possible_duplicate",
                "business_record_not_found",
            ),
        }
    )
    [judged] = judge((subject,), (row,))
    assert judged.missing == (
        "expense_type_missing",
        "duplicate_document",
        "detail_missing",
    )
    assert judged.ready is False


@pytest.mark.parametrize(
    "technical",
    [
        "duplicate_evidence_unavailable",
        "approval_provenance_unavailable",
        "report_effect_incomplete",
    ],
)
def test_technical_rows_cannot_look_ready(approved_rows, technical):
    [row] = judge(
        approved_rows[:1],
        (
            rows(approved_rows[:1])[0].model_copy(
                update={"stage": None, "technical_state": technical}
            ),
        ),
    )
    assert (row.ready, row.missing) == (False, ("detail_missing",))


@pytest.mark.parametrize("excluded", ["personal", "no_comprobante", "b02"])
def test_rows_left_out_by_rule_are_ready(approved_rows, excluded):
    subject = approved_rows[0]
    if excluded == "personal":
        subject = replace(subject, personal=True, include_606=False)
    elif excluded == "b02":
        subject = with_ncf(subject, "B0200000001")
    else:
        subject = replace(
            subject,
            facts=subject.facts.model_copy(
                update={
                    "receipt_state": subject.facts.amount.model_copy(
                        update={"value": "no_receipt"}
                    ),
                    "fiscal": subject.facts.fiscal.model_copy(update={"ncf": Unknown()}),
                }
            ),
        )
    [row] = judge((subject,))
    assert (row.ready, row.missing, row.export_line) == (True, (), False)
