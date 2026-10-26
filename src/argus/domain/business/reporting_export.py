"""Full filtered records and scope manifest, with a fresh authorization before release."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import datetime, timezone

import xlsxwriter

from argus.domain.business.authority import ActionContext, ActionError, BusinessAuthority
from argus.domain.business.export import spreadsheet_cell
from argus.domain.business.reporting_query import (
    ReportAnswer,
    ReportRecord,
    ReportRequest,
)
from argus.domain.business.reporting_store import read_report_snapshot

_COLUMN_FIELDS = {
    "date": "report_date",
    "category": "category_key",
    "funding": "funding_key",
}
_REQUIRED = (
    "row_id",
    "draft_id",
    "linked_activity_ids",
    "stage",
    "technical_state",
    "workflow_blockers",
    "money_kind",
    "money_effect",
    "adjustment_effect",
    "recorded_currency",
)


def build_archive(
    context: ActionContext,
    request: ReportRequest,
    answer: ReportAnswer,
    rows: tuple[ReportRecord, ...],
) -> bytes:
    columns = tuple(
        dict.fromkeys(
            (
                *_REQUIRED,
                *(_COLUMN_FIELDS.get(column, column) for column in request.columns),
            )
        )
    )
    values = []
    for record in rows:
        raw = record.model_dump(mode="json")
        values.append(
            [
                spreadsheet_cell(
                    json.dumps(raw[column], ensure_ascii=False)
                    if isinstance(raw[column], list)
                    else raw[column]
                )
                for column in columns
            ]
        )
    if any(len(value) > 32767 for row in values for value in row):
        raise ActionError("invalid_input", "business_report_cell_too_large")
    csv_buffer = io.StringIO(newline="")
    writer = csv.writer(csv_buffer)
    writer.writerow(columns)
    writer.writerows(values)
    manifest = {
        "schema_version": 1,
        "scope": "filtered_records_only",
        "business_id": str(context.actor.space_id),
        "actor_id": str(context.actor.actor_id),
        "grant_id": str(context.grant_id),
        "query": request.model_dump(mode="json", exclude={"page", "page_size"}),
        "resolved_period": answer.resolved_period.model_dump(mode="json"),
        "captured_at": answer.captured_at.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "matching_count": answer.matching_count,
        "fingerprint": answer.fingerprint,
        "totals": [total.model_dump(mode="json") for total in answer.totals],
        "excluded_unknown_dates": answer.excluded_unknown_dates,
        "coverage_notes": answer.coverage_notes,
        "evidence_included": False,
    }
    excel_buffer = io.BytesIO()
    with xlsxwriter.Workbook(
        excel_buffer,
        {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False},
    ) as book:
        sheet = book.add_worksheet("Records")
        for index, row in enumerate((columns, *values)):
            for col, value in enumerate(row):
                sheet.write_string(index, col, value)
        sheet.freeze_panes(1, 0)
        sheet.autofilter(0, 0, len(values), len(columns) - 1)
        totals_sheet = book.add_worksheet("Totals")
        total_columns = (
            tuple(type(answer.totals[0]).model_fields)
            if answer.totals
            else ("currency", "kind", "basis", "complete", "amount")
        )
        for index, row in enumerate(
            (
                total_columns,
                *(
                    [spreadsheet_cell(total.model_dump()[key]) for key in total_columns]
                    for total in answer.totals
                ),
            )
        ):
            for col, value in enumerate(row):
                totals_sheet.write_string(index, col, value)
        scope_sheet = book.add_worksheet("Scope")
        scope_sheet.write_string(0, 0, "field")
        scope_sheet.write_string(0, 1, "value")
        for index, (key, value) in enumerate(
            ((key, value) for key, value in manifest.items() if key != "totals"), 1
        ):
            scope_sheet.write_string(index, 0, key)
            text = (
                json.dumps(value, ensure_ascii=False)
                if isinstance(value, (dict, list, tuple))
                else value
            )
            cell = spreadsheet_cell(text)
            if len(cell) > 32767:
                raise ActionError("invalid_input", "business_report_cell_too_large")
            scope_sheet.write_string(index, 1, cell)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("records.csv", csv_buffer.getvalue().encode("utf-8-sig"))
        archive.writestr("records.xlsx", excel_buffer.getvalue())
        archive.writestr(
            "manifest.json",
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2),
        )
    return output.getvalue()


def export_report(
    authority: BusinessAuthority,
    context: ActionContext,
    request: ReportRequest,
    expected_fingerprint: str,
) -> bytes:
    answer, rows = read_report_snapshot(authority, context, request, capability="export")
    if answer.fingerprint != expected_fingerprint:
        raise ActionError("stale_version", "business_report_changed")
    archive = build_archive(context, request, answer, rows)
    current, _ = read_report_snapshot(authority, context, request, capability="export")
    if current.fingerprint != expected_fingerprint:
        raise ActionError("stale_version", "business_report_changed")
    return archive
