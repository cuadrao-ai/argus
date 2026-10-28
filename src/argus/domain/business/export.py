from __future__ import annotations

import csv
import hashlib
import io
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile

import xlsxwriter

from argus.domain.business.contracts.dgii import PurchaseDeclaration, money_text
from argus.domain.business.contracts.facts import (
    BusinessFacts,
    Known,
    personal_mark_admits,
)
from argus.domain.business.dgii_export import build_fiscal_packet
from argus.domain.business.dgii_validation import FiscalRecord
from argus.domain.business.ledger import occurred_on
from argus.domain.business.month_close import document_settlement
from argus.domain.business.rnc_registry import (
    RncRegistry,
    postgres_rnc_fetch,
    registry_from_config,
)
from argus.domain.store import utcnow

MAX_ROWS = 1000
MAX_SOURCES = 1000
MAX_SOURCE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 50 * 1024 * 1024
COLUMNS = (
    "activity_id",
    "activity_revision",
    "kind",
    "occurred_on",
    "occurred_at",
    "time_zone",
    "recorded_at",
    "amount",
    "amount_minor",
    "currency",
    "funding",
    "account_ids",
    "note",
    "category_id",
    "draft_ids",
    "source_ids",
    # The owner's Personal mark, the fiscal number the draft carries (ncf, ecf)
    # and the accountant's 606 answer (yes, no); empty when not applicable.
    "personal",
    "fiscal_value",
    "include_606",
)
# The accountant's sheet, in this order. The internal columns go to a second
# sheet without the note.
SHEET_COLUMNS = (
    "Fecha",
    "Proveedor",
    "RNC",
    "NCF",
    "Tipo de gasto",
    "Forma de pago",
    "Subtotal",
    "ITBIS",
    "Total",
    "Moneda",
    "Estado",
    "Pago",
)
ID_COLUMNS = tuple(column for column in COLUMNS if column != "note")
UNRESOLVED_COLUMNS = ("draft_id", "version", "review_state", "occurred_on", "reason")
PERSONAL_COLUMNS = ("Registro", "Fecha", "Total", "Moneda", "Originales")


class ExportLimit(ValueError):
    pass


class OriginalUnavailable(Exception):
    pass


@dataclass(frozen=True)
class ExportPeriod:
    start: date
    end: date

    def __post_init__(self) -> None:
        if not 0 <= (self.end - self.start).days <= 365:
            raise ValueError("export_period_must_be_1_to_366_days")


@dataclass(frozen=True)
class ExportSource:
    source_id: UUID
    draft_ids: tuple[UUID, ...]
    activity_ids: tuple[UUID, ...]
    kind: str
    filename: str | None = None
    media_type: str | None = None
    text: str | None = None
    connection_id: UUID | None = None
    expected_sha256: str | None = None
    original_sha256: str | None = None


@dataclass(frozen=True)
class ExportSnapshot:
    period: ExportPeriod
    activities: tuple[Mapping[str, Any], ...]
    sources: tuple[ExportSource, ...]
    unresolved: tuple[Mapping[str, Any], ...]
    captured_at: datetime
    fiscal_records: tuple[FiscalRecord, ...] = ()
    business_rnc: str | None = None
    business_name: str = ""
    # Stored settlement rows by activity id, read on the same snapshot as the
    # activities. Month close and bank matching write them.
    settlements: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def spreadsheet_cell(value: Any) -> str:
    text = _text(value)
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(
        ("\t", "\r", "\n")
    ):
        return "'" + text
    return text


def _marks(recording: list[dict]) -> dict[str, str]:
    """The Personal mark, the fiscal number and the 606 answer of the draft that
    recorded an activity, as the export's own words; a personal expense stays
    in the export with its mark, never dropped."""

    from argus.domain.business.contracts.facts import (
        BusinessResolution,
        fiscal_inclusion,
        fiscal_value,
        is_personal,
    )

    for draft in recording:
        typed = (draft.get("resolution") or {}).get("business")
        if not typed:
            continue
        facts = BusinessResolution.model_validate(typed).facts
        answer = fiscal_inclusion(facts)
        return {
            "personal": "yes" if is_personal(facts) else "no",
            "fiscal_value": fiscal_value(facts) or "",
            "include_606": "" if answer is None else ("yes" if answer else "no"),
        }
    return {"personal": "no", "fiscal_value": "", "include_606": ""}


def record_rows(snapshot: ExportSnapshot) -> list[dict[str, str]]:
    if len(snapshot.activities) > MAX_ROWS or len(snapshot.unresolved) > MAX_ROWS:
        raise ExportLimit("export_record_limit")
    if len(snapshot.sources) > MAX_SOURCES:
        raise ExportLimit("export_source_limit")
    rows = []
    seen = set()
    for activity in snapshot.activities:
        identifier = str(UUID(str(activity["activity_id"])))
        if identifier in seen:
            raise ValueError("duplicate_canonical_activity")
        seen.add(identifier)
        day = occurred_on(activity)
        if not snapshot.period.start <= day <= snapshot.period.end:
            continue
        linked = [s for s in snapshot.sources if UUID(identifier) in s.activity_ids]
        funding = "unknown"
        if activity.get("funding") == "owner_funds":
            funding = "owner_funds"
        elif activity.get("legs"):
            funding = "business_account"
        row = {column: _text(activity.get(column)) for column in COLUMNS}
        row.update(
            activity_id=identifier,
            activity_revision=str(activity["revision"]),
            occurred_on=day.isoformat(),
            funding=funding,
            account_ids=";".join(
                sorted(str(leg["account_id"]) for leg in activity["legs"])
            ),
            draft_ids=";".join(
                sorted(
                    {str(d) for s in linked for d in s.draft_ids}
                    | set(activity.get("draft_ids", ()))
                )
            ),
            source_ids=";".join(sorted(str(s.source_id) for s in linked)),
        )
        if any(len(value) > 32767 for value in row.values()):
            raise ExportLimit("export_cell_limit")
        rows.append(row)
    return sorted(rows, key=lambda row: (row["occurred_on"], row["activity_id"]))


def _known(fact: Any) -> str:
    return fact.value if isinstance(fact, Known) and fact.value else ""


def sheet_rows(
    rows: Sequence[Mapping[str, str]],
    records: Sequence[FiscalRecord],
    reconciliation: Sequence[Mapping[str, Any]],
    settlements: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, str]]:
    """Each recorded row as the accountant reads it: supplier and fiscal facts
    from the approved revision, the 606 answer from its declaration, the
    fiscal packet's disposition and the month-close settlement. Subtotal is
    the total less a known ITBIS."""

    approved = {str(UUID(str(record.activity_id))): record for record in records}
    status = {
        str(UUID(str(item["activity_id"]))): item["disposition"]
        for item in reconciliation
    }
    sheet = []
    for row in rows:
        record = approved.get(row["activity_id"])
        facts = record.facts if record else BusinessFacts()
        declaration = record.declaration if record else None
        purchase = declaration if isinstance(declaration, PurchaseDeclaration) else None
        itbis = _known(getattr(facts.fiscal, "itbis", None))
        settlement = document_settlement(row, settlements)
        sheet.append(
            {
                "Fecha": row["occurred_on"],
                "Proveedor": _known(facts.counterparty),
                "RNC": _known(getattr(facts.fiscal, "rnc", None)),
                "NCF": _known(getattr(facts.fiscal, "ecf", None))
                or _known(getattr(facts.fiscal, "ncf", None)),
                "Tipo de gasto": purchase.category or ""
                if purchase and not purchase.category_suggested
                else "",
                "Forma de pago": purchase.payment_method or "" if purchase else "",
                "Subtotal": money_text(Decimal(row["amount"]) - Decimal(itbis))
                if itbis
                else "",
                "ITBIS": money_text(Decimal(itbis)) if itbis else "",
                "Total": row["amount"],
                "Moneda": row["currency"],
                "Estado": status.get(row["activity_id"], ""),
                "Pago": settlement.status if settlement else "",
                "Personal": "sí" if row["personal"] == "yes" else "no",
            }
        )
    return sheet


def personal_handoff(
    sheet: Sequence[Mapping[str, str]],
    rows: Sequence[Mapping[str, str]],
    originals: Mapping[str, str],
) -> tuple[list[Mapping[str, str]], list[dict[str, str]]]:
    """To hand everything over in one sheet with a Personal column instead, return
    ``(list(sheet), [])`` here and add "Personal" to SHEET_COLUMNS."""

    admitted = [
        personal_mark_admits(
            row["personal"] == "yes",
            {"yes": True, "no": False}.get(row["include_606"]),
            sale=row["kind"] == "income",
        )
        for row in rows
    ]
    business = [line for line, counts in zip(sheet, admitted, strict=True) if counts]
    personal = [
        {
            "Registro": row["activity_id"],
            "Fecha": row["occurred_on"],
            "Total": row["amount"],
            "Moneda": row["currency"],
            "Originales": ";".join(
                originals[source]
                for source in row["source_ids"].split(";")
                if source in originals
            ),
        }
        for row, counts in zip(rows, admitted, strict=True)
        if not counts
    ]
    return business, personal


def _csv(rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(columns)
    writer.writerows([spreadsheet_cell(row.get(column)) for column in columns] for row in rows)
    return output.getvalue().encode("utf-8-sig")


def _xlsx(
    sheet_values: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
    unresolved: Sequence[Mapping[str, Any]],
    personal: Sequence[Mapping[str, Any]],
) -> bytes:
    output = io.BytesIO()
    with xlsxwriter.Workbook(
        output,
        {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False},
    ) as book:
        heading = book.add_format({"bold": True, "bg_color": "#E8F1ED"})
        for name, columns, values in (
            ("Recorded money", SHEET_COLUMNS, sheet_values),
            ("Record ids", ID_COLUMNS, rows),
            ("Unresolved drafts", UNRESOLVED_COLUMNS, unresolved),
            ("Personal", PERSONAL_COLUMNS, personal),
        ):
            sheet = book.add_worksheet(name)
            for col, label in enumerate(columns):
                sheet.write_string(0, col, label, heading)
            for index, row in enumerate(values, 1):
                for col, label in enumerate(columns):
                    value = spreadsheet_cell(row.get(label))
                    if len(value) > 32767:
                        raise ExportLimit("export_cell_limit")
                    sheet.write_string(index, col, value)
            sheet.freeze_panes(1, 0)
            sheet.autofilter(0, 0, len(values), len(columns) - 1)
            sheet.set_column(0, len(columns) - 1, 22)
    return output.getvalue()


def build_archive(
    snapshot: ExportSnapshot,
    read_original: Callable[[ExportSource], bytes | None],
    registry: RncRegistry | None = None,
) -> bytes:
    rows = record_rows(snapshot)
    included = {UUID(row["activity_id"]) for row in rows}
    pending = {UUID(str(row["draft_id"])) for row in snapshot.unresolved}
    selected = [
        s
        for s in snapshot.sources
        if included.intersection(s.activity_ids) or pending.intersection(s.draft_ids)
    ]
    unlinked_drafts = sorted(
        str(draft) for draft in pending if not any(draft in s.draft_ids for s in selected)
    )
    if len({source.source_id for source in selected}) != len(selected):
        raise ValueError("duplicate_canonical_source")
    output = io.BytesIO()
    entries = []
    total = 0
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for source in selected:
            source_id = str(UUID(str(source.source_id)))
            entry = {
                "source_id": source_id,
                "draft_ids": [str(v) for v in source.draft_ids],
                "activity_ids": [str(v) for v in source.activity_ids],
                "kind": source.kind,
                "original_filename": source.filename,
                "media_type": source.media_type,
                "file": None,
                "sha256": None,
                "availability": "unavailable",
            }
            try:
                content = (
                    source.text.encode("utf-8")
                    if source.text is not None
                    else read_original(source)
                )
            except OriginalUnavailable as error:
                entry["availability"] = str(error)
                content = None
            except (OSError, TimeoutError):
                content = None
            if content is not None:
                digest = hashlib.sha256(content).hexdigest()
                if source.expected_sha256 and digest != source.expected_sha256:
                    entry["availability"] = "hash_mismatch"
                elif (
                    len(content) > MAX_SOURCE_BYTES
                    or total + len(content) > MAX_TOTAL_BYTES
                ):
                    entry["availability"] = "size_limit"
                else:
                    extension = (
                        "txt"
                        if source.text is not None
                        else {
                            "application/pdf": "pdf",
                            "image/png": "png",
                            "image/jpeg": "jpg",
                            "text/plain": "txt",
                            "text/csv": "csv",
                            "message/rfc822": "eml",
                            "application/xml": "xml",
                            "text/xml": "xml",
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
                        }.get(source.media_type, "bin")
                    )
                    path = f"originals/{source_id}.{extension}"
                    archive.writestr(path, content)
                    total += len(content)
                    entry.update(
                        file=path,
                        sha256=digest,
                        availability="included",
                        size_bytes=len(content),
                    )
            entries.append(entry)
        fiscal = build_fiscal_packet(
            snapshot.fiscal_records,
            rnc=snapshot.business_rnc,
            business_name=snapshot.business_name,
            start=snapshot.period.start,
            end=snapshot.period.end,
            captured_on=snapshot.captured_at.date(),
            registry=registry,
        )
        sheet = sheet_rows(
            rows,
            snapshot.fiscal_records,
            fiscal.manifest["reconciliation"],
            snapshot.settlements,
        )
        business, personal = personal_handoff(
            sheet,
            rows,
            {entry["source_id"]: entry["file"] for entry in entries if entry["file"]},
        )
        csv_bytes = _csv(business, SHEET_COLUMNS)
        personal_bytes = _csv(personal, PERSONAL_COLUMNS)
        xlsx_bytes = _xlsx(business, rows, snapshot.unresolved, personal)
        archive.writestr("records.csv", csv_bytes)
        archive.writestr("personal.csv", personal_bytes)
        archive.writestr("records.xlsx", xlsx_bytes)
        for name, content in fiscal.files.items():
            archive.writestr(name, content)
        archive.writestr("unresolved.csv", _csv(snapshot.unresolved, UNRESOLVED_COLUMNS))
        manifest = {
            "schema_version": 1,
            "period": {
                "start": snapshot.period.start.isoformat(),
                "end": snapshot.period.end.isoformat(),
                "date_basis": "canonical occurred_at in recorded time_zone",
                "inclusive": True,
            },
            "captured_at": snapshot.captured_at.isoformat(),
            "records": rows,
            "dgii": fiscal.manifest,
            "unresolved_drafts": list(snapshot.unresolved),
            "unresolved_scope": "Open or accepting drafts dated in the period, plus all undated drafts; never included as recorded money.",
            "unresolved_in_money_totals": False,
            "evidence_complete": all(e["availability"] == "included" for e in entries)
            and all(row["source_ids"] for row in rows)
            and not unlinked_drafts,
            "drafts_without_linked_sources": unlinked_drafts,
            "activities_without_linked_sources": [
                row["activity_id"] for row in rows if not row["source_ids"]
            ],
            "sources": entries,
            "files": {
                "records.csv": hashlib.sha256(csv_bytes).hexdigest(),
                "personal.csv": hashlib.sha256(personal_bytes).hexdigest(),
                "records.xlsx": hashlib.sha256(xlsx_bytes).hexdigest(),
                **{
                    name: hashlib.sha256(content).hexdigest()
                    for name, content in fiscal.files.items()
                },
            },
        }
        archive.writestr(
            "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
        )
    if len(output.getvalue()) > MAX_TOTAL_BYTES + 5 * 1024 * 1024:
        raise ExportLimit("export_archive_limit")
    return output.getvalue()


def export_package(authority, context, period: ExportPeriod, objects) -> bytes:
    from loguru import logger
    from psycopg.rows import dict_row

    from argus.domain.business.authority import ActionError, authorize
    from argus.domain.business.contracts.facts import BusinessResolution, Known
    from argus.domain.ingestion.documents.models import DocumentExtractionError
    from argus.domain.ingestion.documents.objects import (
        IMAGE_MEDIA_TYPES,
        SourceStorageUnavailable,
        verify_content,
    )
    from argus.domain.ingestion.documents.rebuilt import ensure_rebuilt_image
    from argus.domain.ingestion.documents.store_postgres import PostgresDocumentStore
    from argus.domain.recording.canonical_groups import VisibleAccounts, load
    from argus.domain.recording.money_reads import current_activities
    from argus.domain.recording.postgres_repository import (
        PostgresFinancialAccountRepository,
    )

    with authority.pool.connection() as connection, connection.transaction():
        connection.execute("set transaction isolation level repeatable read")
        auth = authorize(connection, context.actor, context.grant_id)
        auth.require("export")
        if auth.context.owner_id != context.owner_id:
            raise ActionError("not_found", "business_record_not_found")
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "select count(*) as count from public.financial_record_revisions v"
                " join public.financial_records r on r.id=v.record_id and r.user_id=v.user_id"
                " left join public.financial_accounts a on a.id=r.account_id and a.user_id=r.user_id"
                " where r.user_id=%s and (a.owner_space_id=%s or r.owner_space_id=%s)",
                (context.owner_id, context.actor.space_id, context.actor.space_id),
            )
            if cursor.fetchone()["count"] > MAX_ROWS * 10:
                raise ExportLimit("export_history_limit")
            canonical = load(
                PostgresFinancialAccountRepository(authority.pool),
                connection,
                {context.owner_id},
                scope=context.scope,
            )
            activities = tuple(
                current_activities(
                    VisibleAccounts(
                        [
                            stored
                            for stored in canonical.records
                            if stored.account.user_id == context.owner_id
                        ],
                        canonical,
                    )
                )
            )
            if len(activities) > MAX_ROWS:
                raise ExportLimit("export_record_limit")
            activity_ids = {
                UUID(a["activity_id"])
                for a in activities
                if period.start <= occurred_on(a) <= period.end
            }
            cursor.execute(
                "select id,version,state,activity_id,resolution from public.financial_import_events"
                " where user_id=%s and owner_space_id=%s order by created_at,id limit %s",
                (context.owner_id, context.actor.space_id, MAX_ROWS + 1),
            )
            drafts = cursor.fetchall()
            if len(drafts) > MAX_ROWS:
                raise ExportLimit("export_draft_limit")
            unresolved = []
            selected_drafts = set()
            for draft in drafts:
                if draft["activity_id"] in activity_ids:
                    selected_drafts.add(draft["id"])
                if draft["activity_id"] or draft["state"] not in {"open", "accepting"}:
                    continue
                typed = draft["resolution"].get("business")
                facts = BusinessResolution.model_validate(typed).facts if typed else None
                day = (
                    facts.occurred_on.value
                    if facts and isinstance(facts.occurred_on, Known)
                    else None
                )
                if day is not None and not period.start <= day <= period.end:
                    continue
                selected_drafts.add(draft["id"])
                unresolved.append(
                    {
                        "draft_id": str(draft["id"]),
                        "version": draft["version"],
                        "review_state": draft["state"],
                        "occurred_on": _text(day) or None,
                        "reason": "draft_not_prepared"
                        if facts is None
                        else ("date_unknown" if day is None else "not_recorded"),
                    }
                )
            cursor.execute(
                "select s.id,s.kind,s.text_content,s.connection_id,d.draft,d.source_sha256,"
                " array_agg(distinct l.draft_id) as draft_ids,"
                " array_remove(array_agg(distinct e.activity_id),null) as activity_ids"
                " from public.business_sources s join public.business_draft_sources l"
                " on l.source_id=s.id and l.space_id=s.space_id"
                " join public.financial_import_events e on e.id=l.draft_id and e.owner_space_id=l.space_id"
                " left join public.financial_document_extractions d on d.connection_id=s.connection_id and d.user_id=e.user_id"
                " where s.space_id=%s and e.user_id=%s and l.draft_id=any(%s::uuid[])"
                " group by s.id,d.draft,d.source_sha256 order by s.id limit %s",
                (
                    context.actor.space_id,
                    context.owner_id,
                    list(selected_drafts),
                    MAX_SOURCES + 1,
                ),
            )
            sources = tuple(
                ExportSource(
                    source_id=row["id"],
                    draft_ids=tuple(row["draft_ids"]),
                    activity_ids=tuple(row["activity_ids"]),
                    kind=row["kind"],
                    filename=(row["draft"] or {}).get("filename"),
                    media_type=(row["draft"] or {}).get("media_type"),
                    text=row["text_content"],
                    connection_id=row["connection_id"],
                    expected_sha256=row["source_sha256"]
                    or (row["draft"] or {}).get("sha256"),
                    original_sha256=row["source_sha256"]
                    or (row["draft"] or {}).get("sha256"),
                )
                for row in cursor.fetchall()
            )
            activities = tuple(
                dict(
                    a,
                    draft_ids=[
                        str(d["id"])
                        for d in drafts
                        if str(d["activity_id"]) == a["activity_id"]
                    ],
                    **_marks(
                        [d for d in drafts if str(d["activity_id"]) == a["activity_id"]]
                    ),
                )
                for a in activities
            )
            from argus.domain.business.dgii_snapshot import fiscal_snapshot
            from argus.domain.business.month_close_store import read_settlements

            fiscal_records, business_rnc, business_name = fiscal_snapshot(
                cursor, context, activities
            )
            snapshot = ExportSnapshot(
                period,
                activities,
                sources,
                tuple(unresolved),
                utcnow(),
                fiscal_records,
                business_rnc,
                business_name,
                settlements=read_settlements(
                    cursor, context.owner_id, str(context.actor.space_id)
                ),
            )

    store = PostgresDocumentStore(authority.pool, objects)
    downloads = []
    for source in snapshot.sources:
        if source.text is None and source.media_type in IMAGE_MEDIA_TYPES:
            # Rebuilding writes through another connection. Release snapshot
            # locks before the capped producer; recheck access before and after.
            with authority.pool.connection() as check, check.transaction():
                authorize(check, context.actor, context.grant_id).require("export")
                live = check.execute(
                    "select 1 from public.business_sources s "
                    "join public.financial_source_connections c on c.id=s.connection_id "
                    "where s.id=%s and s.space_id=%s and c.id=%s and c.user_id=%s "
                    "and c.owner_space_id=s.space_id and c.status <> 'disconnected'",
                    (
                        source.source_id,
                        context.actor.space_id,
                        source.connection_id,
                        context.owner_id,
                    ),
                ).fetchone()
            if live is not None:
                try:
                    ensure_rebuilt_image(
                        store=store,
                        user_id=context.owner_id,
                        connection_id=str(source.connection_id),
                    )
                    rebuilt = store.rebuilt(
                        user_id=context.owner_id, connection_id=str(source.connection_id)
                    )
                except (SourceStorageUnavailable, DocumentExtractionError):
                    rebuilt = None
                if rebuilt is not None:
                    source = replace(
                        source,
                        media_type=rebuilt[0],
                        expected_sha256=hashlib.sha256(rebuilt[1]).hexdigest(),
                    )
        downloads.append(source)
    snapshot = replace(snapshot, sources=tuple(downloads))

    with authority.pool.connection() as connection, connection.transaction():
        connection.execute("set transaction isolation level repeatable read")
        current = authorize(connection, context.actor, context.grant_id)
        current.require("export")
        if current.context.owner_id != context.owner_id:
            raise ActionError("not_found", "business_record_not_found")
        with connection.cursor(row_factory=dict_row) as cursor:

            def original(source: ExportSource) -> bytes | None:
                authorize(connection, context.actor, context.grant_id).require("export")
                cursor.execute(
                    "select d.draft->>'sha256' as original_sha256, "
                    "d.draft->>'media_type' as original_media_type, "
                    "d.source_path,d.rebuilt_path,d.rebuilt_media_type,d.rebuilt_sha256, "
                    "d.source_size_bytes, d.rebuilt_size_bytes, octet_length(d.source_bytes) as legacy_size, "
                    "case when octet_length(d.source_bytes)<=%s then d.source_bytes end as legacy_bytes "
                    "from public.financial_document_extractions d "
                    "join public.financial_source_connections c on c.id=d.connection_id and c.user_id=d.user_id "
                    "join public.business_sources s on s.connection_id=c.id and s.space_id=c.owner_space_id "
                    "where s.id=%s and s.space_id=%s and c.id=%s and c.user_id=%s "
                    "and c.status <> 'disconnected' and c.source='statement' for share of c,d",
                    (
                        MAX_SOURCE_BYTES,
                        source.source_id,
                        context.actor.space_id,
                        source.connection_id,
                        context.owner_id,
                    ),
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                if row["original_sha256"] != source.original_sha256:
                    raise OriginalUnavailable("source_changed")
                is_image = row["original_media_type"] in IMAGE_MEDIA_TYPES
                size = (
                    row["rebuilt_size_bytes"]
                    if is_image
                    else max(row["source_size_bytes"] or 0, row["legacy_size"] or 0)
                )
                if (size or 0) > MAX_SOURCE_BYTES:
                    raise OriginalUnavailable("size_limit")
                path = row["rebuilt_path"] if is_image else row["source_path"]
                if is_image:
                    if path is None:
                        return None
                    expected_paths = {
                        f"rebuilt/{context.owner_id}/{source.original_sha256}"
                    }
                    digest = row["rebuilt_sha256"]
                    if row["rebuilt_media_type"] != source.media_type:
                        raise OriginalUnavailable("source_changed")
                else:
                    expected_paths = {
                        f"sealed/{context.owner_id}/{source.original_sha256}",
                        f"{context.owner_id}/{source.connection_id}/{source.original_sha256}",
                    }
                    digest = source.original_sha256
                try:
                    if path is None:
                        legacy = row["legacy_bytes"]
                        logger.info("document_original_read caller=export_inline_reader")
                        return verify_content(
                            bytes(legacy) if legacy is not None else None, digest or ""
                        )
                    if path not in expected_paths:
                        raise OriginalUnavailable("path_mismatch")
                    return verify_content(objects.get(path), digest or "")
                except SourceStorageUnavailable:
                    return None

            def lookup(sql, params):
                cursor.execute(sql, params)
                return cursor.fetchone()

            result = build_archive(
                snapshot,
                original,
                registry_from_config("dgii", postgres_rnc_fetch(lookup)),
            )
            authorize(connection, context.actor, context.grant_id).require("export")
            return result
