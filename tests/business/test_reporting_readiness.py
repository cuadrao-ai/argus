"""The row, Estado filter and count share one current readiness verdict."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from argus.domain.business.contracts.facts import Unknown
from argus.domain.business.dgii_export import (
    fiscal_manifest,
    line_assessments,
    line_verdicts,
)
from argus.domain.business.missing_reasons import words
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
from tests.dgii.test_packet import practice_records


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
        and (ready is not False or not r.ready)
    ]
    assert answer.matching_count == len(expected)
    assert answer.overview.not_ready == sum(not row.ready for row in expected)
    assert answer.overview.not_ready == 3
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
        "missing_rnc",
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
        assert words(row.missing[0], "es-419") == "Falta el tipo de gasto"
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
        "missing_ncf",
        "payment_method_missing",
    )
    if currency == "DOP":
        assert (
            row.stage,
            row.fiscal_data,
            row.export_missing,
            row.export_missing_several,
        ) == ("needs_fiscal_data", "missing", "missing_ncf", False)
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


@pytest.mark.parametrize("field", ["goods_amount", "services_amount"])
def test_foreign_amount_mismatch_matches_dop_without_changing_export(
    approved_rows, field
):
    original, good = approved_rows[:2]
    mismatch = replace(
        original,
        declaration=original.declaration.model_copy(
            update={field: str(Decimal(getattr(original.declaration, field) or "0") + 1)}
        ),
    )
    usd = replace(mismatch, currency="USD")
    [dop_row] = judge((mismatch,))
    [usd_row] = judge((usd,), (rows((usd,))[0].model_copy(update={"currency": "USD"}),))
    assert dop_row.ready is False
    assert dop_row.missing == ("detail_missing",)
    assert (usd_row.ready, usd_row.missing) == (dop_row.ready, dop_row.missing)
    filtered = run((usd_row,), ReportFilters(period=SEPTEMBER, ready=False))
    assert (filtered.matching_count, filtered.overview.not_ready) == (1, 1)

    def export(subject):
        records = (subject, good)
        manifest, lines = fiscal_manifest(
            records,
            rnc="199990013",
            business_name="",
            start=date(2026, 9, 1),
            end=date(2026, 9, 30),
            captured_on=CAPTURED,
        )
        assessments = line_assessments(records, rnc="199990013", captured_on=CAPTURED)
        assert assessments[subject.activity_id].issues == (
            {
                "code": "fiscal_conversion_required",
                "activity_id": subject.activity_id,
                "field": "currency",
            },
        )
        projected = tuple(
            row.model_copy(update={"currency": record.currency})
            for row, record in zip(rows(records), records, strict=True)
        )
        judged = with_export_verdicts(projected, assessments, frozenset())
        dataset = source(
            *judged, approved={record.activity_id: record for record in records}
        )
        result = build_file(
            dataset, RecordsExport(report=report(), mode="dgii", format="csv")
        )
        assert len(lines["606"]) == result.row_count == 1
        return (
            manifest,
            lines,
            result.content,
            summarize_export(dataset, report()).dgii,
            judged[0].model_dump(exclude={"ready", "missing"}),
        )

    assert export(usd) == export(replace(original, currency="USD"))


@pytest.mark.parametrize("family", ["purchase", "sale"])
def test_foreign_duplicates_match_dop_without_changing_export(approved_rows, family):
    fake = Faker()
    fake.seed_instance(2186)
    sale = practice_records()[4]
    original = approved_rows[0] if family == "purchase" else sale
    duplicate = replace(original, activity_id=fake.uuid4(), draft_id=fake.uuid4())
    dop = (original, duplicate)
    usd = tuple(replace(record, currency="USD") for record in dop)
    dop_rows = judge(dop)
    usd_rows = judge(usd)
    assert [(row.ready, row.missing) for row in dop_rows] == [
        (False, ("duplicate_document",)),
        (False, ("duplicate_document",)),
    ]
    assert [(row.ready, row.missing) for row in usd_rows] == [
        (row.ready, row.missing) for row in dop_rows
    ]
    filtered = run(usd_rows, ReportFilters(period=SEPTEMBER, ready=False))
    assert (filtered.matching_count, filtered.overview.not_ready) == (2, 2)

    good = (
        approved_rows[2],
        replace(
            with_ncf(sale, f"B01{fake.unique.random_int(1, 99999999):08}"),
            activity_id=fake.uuid4(),
            draft_id=fake.uuid4(),
        ),
    )

    def export(pair):
        records = (*pair, *good)
        manifest, lines = fiscal_manifest(
            records,
            rnc="199990013",
            business_name="",
            start=date(2026, 9, 1),
            end=date(2026, 9, 30),
            captured_on=CAPTURED,
        )
        assert len(lines["606"]) == len(lines["607"]) == 1
        assessments = line_assessments(records, rnc="199990013", captured_on=CAPTURED)
        for subject in pair:
            assert assessments[subject.activity_id].issues == (
                {
                    "code": "fiscal_conversion_required",
                    "activity_id": subject.activity_id,
                    "field": "currency",
                },
            )
        projected = tuple(
            row.model_copy(
                update={
                    "currency": record.currency,
                    "family": "sale" if record.kind == "income" else "purchase",
                }
            )
            for row, record in zip(rows(records), records, strict=True)
        )
        dataset = source(
            *with_export_verdicts(projected, assessments, frozenset()),
            approved={record.activity_id: record for record in records},
        )
        files = tuple(
            build_file(
                dataset,
                RecordsExport(
                    report=report(record_families=[chosen]), mode="dgii", format="csv"
                ),
            ).content
            for chosen in ("purchase", "sale")
        )
        return (
            manifest,
            lines,
            files,
            line_verdicts(records, rnc="199990013", captured_on=CAPTURED),
        )

    distinct = (usd[0], with_ncf(usd[1], f"B01{fake.unique.random_int(1, 99999999):08}"))
    assert export(usd) == export(distinct)


@pytest.mark.parametrize("month", [8, 10])
def test_foreign_duplicate_count_is_limited_to_the_same_month(approved_rows, month):
    first, other = approved_rows[:2]
    records = (
        replace(first, currency="USD"),
        replace(
            first,
            currency="USD",
            activity_id=other.activity_id,
            occurred_on=date(2026, month, 1),
        ),
    )
    judged = judge(records)
    assert judged[0].ready
    assert all("duplicate_document" not in row.missing for row in judged)


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
        "duplicate",
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
