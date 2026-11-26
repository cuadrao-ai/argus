"""Authorized recorded subset of Registros, before any public report filtering."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row
from pydantic import TypeAdapter

from argus.domain.business.annotations import annotation_available, supporting_source_key
from argus.domain.business.authority import (
    ActionContext,
    ActionError,
    Authorization,
    BusinessAuthority,
    authorize,
)
from argus.domain.business.country import DEFAULT_COUNTRY
from argus.domain.business.dgii_snapshot import fiscal_snapshot
from argus.domain.business.dgii_validation import FiscalRecord
from argus.domain.business.ledger import business_day, occurred_on
from argus.domain.business.month_close import Settlement
from argus.domain.business.reporting import ReportIdentity, ReportRow
from argus.domain.business.reporting_query import (
    Purchase606,
    ReportAnswer,
    ReportAttachment,
    ReportRecord,
    ReportRequest,
)
from argus.domain.business.rnc_registry import RncRegistrySnapshot
from argus.domain.recording.canonical_groups import VisibleAccounts, load
from argus.domain.recording.money_reads import current_activities
from argus.domain.recording.postgres_repository import PostgresFinancialAccountRepository

if TYPE_CHECKING:
    from argus.domain.business.transactions import ActionTransaction
    from argus.domain.ingestion.reconcile.model import ImportEvent


@dataclass(frozen=True)
class ReportSource:
    source_id: str
    linked: bool
    kind: str | None = None
    connection_id: str | None = None
    connection_status: str | None = None
    filename: str | None = None
    media_type: str | None = None
    sha256: str | None = None
    source_available: bool | None = None
    source_key: str | None = None

    @property
    def supporting_only(self) -> bool:
        return (
            self.kind == "attachment"
            and self.connection_id is not None
            and self.source_key == supporting_source_key(self.connection_id)
        )


@dataclass(frozen=True)
class RecordedRecord:
    row: ReportRow
    activity_json: str
    approved: FiscalRecord
    settlement: Settlement | None
    sources: tuple[ReportSource, ...]


@dataclass(frozen=True)
class RecordedSnapshot:
    context: ActionContext
    records: tuple[RecordedRecord, ...]
    observed_at: datetime

    @property
    def rows(self) -> tuple[ReportRow, ...]:
        return tuple(record.row for record in self.records)

    def identity(self, query_fingerprint: str) -> ReportIdentity:
        return ReportIdentity(
            business_id=str(self.context.actor.space_id),
            actor_id=str(self.context.actor.actor_id),
            owner_id=self.context.owner_id,
            grant_id=str(self.context.grant_id),
            query_fingerprint=query_fingerprint,
        )


_SOURCES = """
select l.draft_id::text, s.id::text as source_id, s.kind, s.source_key,
       s.connection_id::text, c.status as connection_status,
       d.draft->>'filename' as filename, d.draft->>'media_type' as media_type,
       coalesce(d.source_sha256, d.draft->>'sha256') as sha256,
       (d.draft->>'source_available')::boolean as source_available
from public.business_draft_sources l
join public.business_sources s on s.id=l.source_id and s.space_id=l.space_id
join public.financial_import_events e on e.id=l.draft_id and e.owner_space_id=l.space_id
left join public.financial_source_connections c
  on c.id=s.connection_id and c.owner_space_id=s.space_id and c.user_id=e.user_id
left join public.financial_document_extractions d
  on d.connection_id=c.id and d.user_id=e.user_id and c.status <> 'disconnected'
where l.space_id=%s and e.user_id=%s and l.draft_id=any(%s::uuid[])
order by l.draft_id,s.id
"""


def _json(value: Any) -> str:
    return json.dumps(
        TypeAdapter(Any).dump_python(value, mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _authorized(connection: Connection, context: ActionContext) -> Authorization:
    live = authorize(connection, context.actor, context.grant_id)
    live.require("read")
    if (
        live.context.owner_id != context.owner_id
        or live.context.current_owner_id != context.current_owner_id
    ):
        raise ActionError("not_found", "business_record_not_found")
    return live


# Registros lists approved records only: a draft reaches a row through the
# money row it recorded, so open drafts stay in the Bandeja.
_RECORDED_DRAFT_STATES = ("accepting", "accepted", "dismissed")
_MAX_REPORT_INPUTS = 10_000


def _business(events: Iterable[ImportEvent]) -> list[ImportEvent]:
    return [event for event in events if "business" in event.resolution]


def _business_drafts(
    connection: Connection,
    live: Authorization,
    selected: RecordedRecord | None = None,
) -> tuple[ActionTransaction, list[ImportEvent]]:
    from argus.domain.business.transactions import ActionTransaction
    from argus.domain.ingestion.reconcile.store_postgres import _PostgresTx

    context = live.context
    tx = ActionTransaction(
        connection, live, _PostgresTx(connection, context.owner_id, context.scope)
    )
    events = (
        tx.imports.events_of(
            _RECORDED_DRAFT_STATES,
            [selected.approved.draft_id] if selected.approved.draft_id else [],
            [selected.row.activity_id],
        )
        if selected is not None
        else tx.imports.events(_RECORDED_DRAFT_STATES)
    )
    return tx, _business(events)


def _speaking_drafts(
    records: Iterable[FiscalRecord], events: Iterable[ImportEvent]
) -> dict[str, ImportEvent]:
    """The draft that speaks for each approved record, by activity: the one
    that recorded it, else the one draft that names its activity."""

    by_id = {event.id: event for event in events}
    by_activity: dict[str, ImportEvent] = {}
    for event in by_id.values():
        if event.activity_id:
            if event.activity_id in by_activity:
                raise ValueError("duplicate canonical draft activity")
            by_activity[event.activity_id] = event
    return {
        record.activity_id: event
        for record in records
        if (event := by_id.get(record.draft_id) or by_activity.get(record.activity_id))
    }


def _recorded_activities(
    authority: BusinessAuthority, context: ActionContext, connection: Connection
) -> list[dict[str, Any]]:
    canonical = load(
        PostgresFinancialAccountRepository(authority.pool),
        connection,
        {context.owner_id},
        scope=context.scope,
    )
    return current_activities(
        VisibleAccounts(
            [
                stored
                for stored in canonical.records
                if stored.account.user_id == context.owner_id
            ],
            canonical,
        )
    )


def registros_count(authority: BusinessAuthority, context: ActionContext) -> int:
    """Each current money activity supplies one row in the unfiltered Registros list."""
    with authority.pool.connection() as connection, connection.transaction():
        connection.execute("set transaction isolation level repeatable read")
        live = _authorized(connection, context)
        count = len(_recorded_activities(authority, live.context, connection))
        _authorized(connection, live.context)
        return count


def _detail_activities(
    authority: BusinessAuthority,
    context: ActionContext,
    connection: Connection,
    activity_id: str,
) -> list[dict[str, Any]]:
    """A credit may refer to any original. For other activities only another
    document with the same number can change the assessment. Read candidate
    numbers from *every* revision; the fiscal snapshot selects the approved
    facts and line_assessments decides whether any are really duplicates."""
    from argus.domain.business.dgii_validation import fact_value, is_credit
    from argus.domain.business.fiscal_identity import normalized_ncf
    from argus.domain.recording.activity_lookup import load as load_activity

    repository = PostgresFinancialAccountRepository(authority.pool)

    def activity(identifier: str) -> dict[str, Any] | None:
        return load_activity(
            repository, connection, context.owner_id, identifier, context.scope
        )

    target = activity(activity_id)
    if target is None:
        return []
    with connection.cursor(row_factory=dict_row) as cursor:
        (record,), _, _ = fiscal_snapshot(cursor, context, [target], only_these=True)
    if is_credit(record):
        return _recorded_activities(authority, context, connection)
    number = fact_value(record, "ecf") or fact_value(record, "ncf")
    if not number:
        return [target]
    normalized = normalized_ncf(number)
    revisions = connection.execute(
        "select distinct e.activity_id::text, v.after_facts#>>'{fiscal,ecf,value}',"
        " v.after_facts#>>'{fiscal,ncf,value}' from public.financial_import_events e"
        " join public.business_draft_revisions v on v.space_id=e.owner_space_id and v.draft_id=e.id"
        " where e.user_id=%s and e.owner_space_id=%s and e.state='accepted'"
        " and e.activity_id<>%s and v.after_facts->'fiscal' is not null",
        (context.owner_id, context.actor.space_id, activity_id),
    )
    peers = {
        identifier
        for identifier, ecf, ncf in revisions
        if (ecf or ncf) and normalized_ncf(ecf or ncf) == normalized
    }
    activities = [target]
    for identifier in sorted(peers):
        peer = activity(identifier)
        if peer is not None:
            activities.append(peer)
    return activities


def _recorded(
    authority: BusinessAuthority,
    context: ActionContext,
    connection: Connection,
    activity_id: str | None = None,
) -> RecordedSnapshot:
    context = _authorized(connection, context).context
    observed_at = connection.execute("select transaction_timestamp()").fetchone()[0]
    activities = (
        _recorded_activities(authority, context, connection)
        if activity_id is None
        else _detail_activities(authority, context, connection, activity_id)
    )
    with connection.cursor(row_factory=dict_row) as cursor:
        if activity_id is None:
            approved, _, _ = fiscal_snapshot(cursor, context, activities)
        else:
            approved, _, _ = fiscal_snapshot(cursor, context, activities, only_these=True)
        cursor.execute(
            "select activity_id::text, status, settled_on, payment_method"
            " from public.business_document_settlements where space_id=%s and owner_id=%s"
            " and (%s::uuid is null or activity_id=%s)",
            (context.actor.space_id, context.owner_id, activity_id, activity_id),
        )
        settlements = {
            row["activity_id"]: Settlement(
                row["status"], row["settled_on"], row["payment_method"]
            )
            for row in cursor.fetchall()
        }
        cursor.execute(
            _SOURCES,
            (
                context.actor.space_id,
                context.owner_id,
                [record.draft_id for record in approved if record.draft_id],
            ),
        )
        sources = {
            (row.pop("draft_id"), row["source_id"]): ReportSource(linked=True, **row)
            for row in cursor.fetchall()
        }
    facts = {record.activity_id: record for record in approved}
    records = []
    for activity in activities:
        identifier = activity["activity_id"]
        record = facts[identifier]
        settlement = settlements.get(identifier)
        linked = tuple(
            sources.get(
                (record.draft_id, source),
                ReportSource(source_id=source, linked=False),
            )
            for source in sorted(record.source_ids)
        )
        activity_json = _json(activity)
        dependencies = _json(
            {
                "activity": activity,
                "approved": record,
                "settlement": settlement,
                "sources": linked,
            }
        )
        row = ReportRow(
            activity_id=identifier,
            revision=activity["revision"],
            occurred_on=occurred_on(activity),
            kind=activity["kind"],
            currency=activity["currency"],
            amount_minor=activity["amount_minor"],
            effect="known" if activity["amount_minor"] is not None else "unknown",
            dependency_fingerprints=(hashlib.sha256(dependencies.encode()).hexdigest(),),
        )
        records.append(RecordedRecord(row, activity_json, record, settlement, linked))
    return RecordedSnapshot(
        context=context,
        records=tuple(
            sorted(
                records,
                key=lambda record: (
                    -record.row.occurred_on.toordinal(),
                    record.row.activity_id,
                ),
            )
        ),
        observed_at=observed_at,
    )


def read_recorded(
    authority: BusinessAuthority,
    context: ActionContext,
    *,
    capability: Literal["read", "export"] = "read",
) -> RecordedSnapshot:
    with authority.pool.connection() as connection, connection.transaction():
        connection.execute("set transaction isolation level repeatable read")
        authorize(connection, context.actor, context.grant_id).require(capability)
        result = _recorded(authority, context, connection)
        authorize(connection, context.actor, context.grant_id).require(capability)
        return result


def projected_records(
    authority: BusinessAuthority,
    context: ActionContext,
    connection: Connection,
    *,
    activity_id: str | None = None,
) -> tuple[RecordedSnapshot, tuple[ReportRecord, ...], RncRegistrySnapshot]:
    """Project Registros on the caller's authorized transaction snapshot.

    Raises ``business_report_too_large`` when the projection cannot cover it.
    """

    from argus.domain.business.actions.dossier import record_context, workflow_blockers
    from argus.domain.business.contracts.dossier import ReviewQuestion
    from argus.domain.business.contracts.facts import (
        BusinessResolution,
        fiscal_inclusion,
        is_personal,
        personal_mark_admits,
    )
    from argus.domain.business.record_origin import draft_arrivals
    from argus.domain.business.reporting_projection import DraftState, project, value
    from argus.domain.business.supporting_files import supporting_files_full

    snapshot = _recorded(authority, context, connection, activity_id)
    context = snapshot.context
    live = authorize(connection, context.actor, context.grant_id)
    selected = None
    if activity_id is not None:
        selected = next((r for r in snapshot.records if r.row.activity_id == activity_id), None)
        if selected is None:
            return snapshot, (), RncRegistrySnapshot()
    tx, events = _business_drafts(connection, live, selected)
    if activity_id is None and len(events) + len(snapshot.records) > _MAX_REPORT_INPUTS:
        raise ActionError("invalid_input", "business_report_too_large")
    accounts = record_context(tx).accounts
    draft_ids = [event.id for event in events] if activity_id is not None else None
    question_rows = tx.rows(
        "select id,draft_id,field,asked_of,channel,state,prompt,allowed_answers,answer_source_id,created_at from public.business_questions where space_id=%s"
        " and (%s::uuid[] is null or draft_id=any(%s::uuid[]))",
        (context.actor.space_id, draft_ids, draft_ids),
    )
    questions: dict[str, list[ReviewQuestion]] = {}
    for row in question_rows:
        question = ReviewQuestion.model_validate(row)
        questions.setdefault(str(question.draft_id), []).append(question)
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            _SOURCES,
            (context.actor.space_id, context.owner_id, [event.id for event in events]),
        )
        linked: dict[str, list[ReportSource]] = {}
        for row in cursor.fetchall():
            draft_id = row.pop("draft_id")
            linked.setdefault(draft_id, []).append(ReportSource(linked=True, **row))
    resolutions = {
        event.id: BusinessResolution.model_validate(event.resolution["business"])
        for event in events
    }
    arrivals = draft_arrivals(
        tx,
        [UUID(key) for key, resolution in resolutions.items()
         if linked.get(key) and not resolution.facts.counterparty.value],
    )
    drafts = {}
    for event in events:
        resolution = resolutions[event.id]
        facts = resolution.facts
        technical = None
        try:
            blocked, pending = workflow_blockers(
                tx, event, facts, accounts, tuple(questions.get(event.id, ()))
            )
            codes = tuple(block.code for block in blocked)
        except ActionError as error:
            if error.result.code != "duplicate_evidence_unavailable":
                raise
            codes, pending, technical = (), (), error.result.code
        sources = tuple(linked.get(event.id, ()))
        fiscal = FiscalRecord(
            event.activity_id or event.id,
            0,
            event.id,
            0,
            value(facts, "occurred_on") or date.min,
            value(facts, "amount") or "0",
            value(facts, "currency") or "unknown",
            value(facts, "kind") or "unknown",
            resolution.document_type,
            facts,
            resolution.dgii,
            tuple(source.source_id for source in sources),
            personal=is_personal(facts),
            include_606=fiscal_inclusion(facts),
            fiscal_overrides=resolution.fiscal_overrides,
        )
        dependency = hashlib.sha256(
            _json(
                {
                    "version": event.version,
                    "state": event.state,
                    "attention": event.attention,
                    "facts": facts,
                    "declaration": resolution.dgii,
                    "blockers": codes,
                    "pending": pending,
                    "technical": technical,
                    "sources": sources,
                    "questions": [
                        (str(q.id), q.state) for q in questions.get(event.id, ())
                    ],
                }
            ).encode()
        ).hexdigest()
        arrival = arrivals.get(UUID(event.id))
        drafts[event.id] = DraftState(
            event, facts, fiscal, codes, technical, sources, dependency,
            original_filename=arrival.filename if arrival else None,
        )
    originals = {
        record.approved.activity_id: record.approved for record in snapshot.records
    }
    filer_identity = connection.execute(
        "select business_rnc from public.spaces where id=%s", (context.actor.space_id,)
    ).fetchone()[0]
    speaking = _speaking_drafts((record.approved for record in snapshot.records), events)
    projected = []
    for record in snapshot.records:
        if activity_id is not None and record.row.activity_id != activity_id:
            continue
        event = speaking.get(record.row.activity_id)
        draft = drafts[event.id] if event else None
        # A record mid-approval shows once the approval settles.
        if draft and draft.event.state == "accepting":
            continue
        projected.append(project(record, draft, originals, filer_identity, accounts))
    from argus.domain.business.record_attachments import retained_source_ids

    retained = retained_source_ids(tx, list(drafts))
    public_rows = []
    for row in projected:
        draft = drafts.get(row.draft_id)
        can_annotate = annotation_available(live, draft.event if draft else None)
        sources = draft.sources if draft else ()
        files = [source for source in sources if source.source_id in retained]
        connected = {
            source.source_id: source for source in files
            if source.connection_status not in (None, "disconnected")
        }
        public_rows.append(
            row.model_copy(
                update={
                    "can_edit_note": can_annotate,
                    "can_append_supporting": can_annotate
                    and not supporting_files_full(source.supporting_only for source in draft.sources),
                    "annotation_unavailable_reason": None
                    if can_annotate
                    else "business_annotation_unavailable"
                    if draft
                    else "business_annotation_unsupported",
                    "has_document": bool(connected),
                    "attachment_count": len(files),
                    "attachment_filenames": tuple(
                        source.filename for source in connected.values() if source.filename
                    ),
                    "attachment_sources": tuple(
                        ReportAttachment(
                            source_id=source.source_id,
                            receipt_id=source.connection_id,
                            filename=source.filename,
                            media_type=source.media_type,
                            source_available=(
                                source.source_available if source.source_id in retained else False
                            ),
                            download_available=(
                                "download" in live.permissions
                                and source.source_available is True
                                and source.source_id in connected
                            ),
                        )
                        for source in sources
                        if source.kind == "attachment"
                    ),
                }
            )
        )
    from argus.domain.business.contracts.dgii import PurchaseDeclaration
    from argus.domain.business.dgii_export import fiscal_form, line_assessments
    from argus.domain.business.dgii_line import confirmed_declaration
    from argus.domain.business.dgii_validation import fact_value
    from argus.domain.business.fiscal_identity import identity_digits
    from argus.domain.business.reporting_projection import with_export_verdicts
    from argus.domain.business.rnc_registry import (
        postgres_rnc_fetch,
        registry_from_config,
    )

    with connection.cursor(row_factory=dict_row) as cursor:

        def lookup(sql, params):
            cursor.execute(sql, params)
            return cursor.fetchone()

        registry = registry_from_config("dgii", postgres_rnc_fetch(lookup))
        identities = {
            digits
            for record in snapshot.records
            if fiscal_form(record.approved) is not None
            if personal_mark_admits(
                record.approved.personal,
                record.approved.include_606,
                sale=fiscal_form(record.approved) == "607",
            )
            if isinstance(confirmed_declaration(record.approved), PurchaseDeclaration)
            if (digits := identity_digits(fact_value(record.approved, "rnc")))
        }
        rnc_snapshot = RncRegistrySnapshot(
            {digits: registry.lookup(digits) for digits in sorted(identities)}
        )
        verdicts = line_assessments(
            tuple(record.approved for record in snapshot.records),
            rnc=filer_identity,
            captured_on=business_day(snapshot.observed_at),
            registry=rnc_snapshot,
        )
    exported = frozenset(
        row[0]
        for row in connection.execute(
            "select activity_id::text from public.business_dgii_export_lines"
            " where space_id=%s and (%s::uuid is null or activity_id=%s)",
            (context.actor.space_id, activity_id, activity_id),
        ).fetchall()
    )
    return (
        snapshot,
        with_export_verdicts(tuple(public_rows), verdicts, exported),
        rnc_snapshot,
    )


def read_record_detail(tx: ActionTransaction, activity_id: str) -> ReportRecord | None:
    """The selected row's readiness and 606 answers, on the open transaction."""
    from argus.domain.postgres_connection import BorrowedConnection

    authority = BusinessAuthority(BorrowedConnection(tx.connection))
    _, rows, _ = projected_records(
        authority, tx.context, tx.connection, activity_id=activity_id
    )
    return next(iter(rows), None)


def read_606(
    authority: BusinessAuthority,
    context: ActionContext,
    activity_ids: Sequence[str],
) -> dict[str, Purchase606 | None]:
    """The 606 answers Registros shows for these activities, by id, reading
    only their money rows, approvals and drafts in one snapshot. An activity
    outside this Business, or one whose approval is still settling, has none."""

    from argus.domain.business.contracts.facts import BusinessResolution
    from argus.domain.business.reporting_projection import current_marks, purchase_606
    from argus.domain.ingestion.reconcile.store_postgres import _PostgresTx
    from argus.domain.recording.activity_lookup import load as load_activity

    with authority.pool.connection() as connection, connection.transaction():
        connection.execute("set transaction isolation level repeatable read")
        live = _authorized(connection, context)
        repository = PostgresFinancialAccountRepository(authority.pool)
        activities = [
            activity
            for identifier in dict.fromkeys(activity_ids)
            if (
                activity := load_activity(
                    repository,
                    connection,
                    live.context.owner_id,
                    identifier,
                    live.context.scope,
                )
            )
        ]
        if not activities:
            return {}
        with connection.cursor(row_factory=dict_row) as cursor:
            approved, _, _ = fiscal_snapshot(
                cursor, live.context, activities, only_these=True
            )
        drafts = _PostgresTx(connection, live.context.owner_id, live.context.scope)
        events = drafts.events_of(
            _RECORDED_DRAFT_STATES,
            [record.draft_id for record in approved if record.draft_id],
            [record.activity_id for record in approved],
        )
        speaking = _speaking_drafts(approved, _business(events))
        answers: dict[str, Purchase606 | None] = {}
        for record in approved:
            event = speaking.get(record.activity_id)
            if event and event.state == "accepting":
                continue
            draft = (
                BusinessResolution.model_validate(event.resolution["business"]).facts
                if event
                else None
            )
            answers[record.activity_id] = purchase_606(
                record, current_marks(record, draft)
            )
        return answers


@dataclass(frozen=True)
class ExportSource:
    """Every projected row with the approved record its 606 or 607 line reads."""

    records: tuple[ReportRecord, ...]
    approved: dict[str, FiscalRecord]
    observed_at: datetime
    rnc_registry: RncRegistrySnapshot = field(default_factory=RncRegistrySnapshot)
    country: str = DEFAULT_COUNTRY


def read_export_source(
    authority: BusinessAuthority, context: ActionContext
) -> ExportSource:
    with authority.pool.connection() as connection, connection.transaction():
        connection.execute("set transaction isolation level repeatable read")
        authorize(connection, context.actor, context.grant_id).require("export")
        snapshot, records, rnc_registry = projected_records(authority, context, connection)
        authorize(connection, context.actor, context.grant_id).require("export")
    return ExportSource(
        records,
        {record.approved.activity_id: record.approved for record in snapshot.records},
        snapshot.observed_at,
        rnc_registry,
        context.country,
    )


def require_export(authority: BusinessAuthority, context: ActionContext) -> None:
    """The grant still exports when the built file is released."""

    with authority.pool.connection() as connection:
        authorize(connection, context.actor, context.grant_id).require("export")


def read_report_snapshot(
    authority: BusinessAuthority,
    context: ActionContext,
    request: ReportRequest,
    *,
    capability: Literal["read", "export"] = "read",
) -> tuple[ReportAnswer, tuple[ReportRecord, ...]]:
    from argus.domain.business.reporting_query import matching_records, run_query

    with authority.pool.connection() as connection, connection.transaction():
        connection.execute("set transaction isolation level repeatable read")
        authorize(connection, context.actor, context.grant_id).require(capability)
        snapshot, records, _ = projected_records(authority, context, connection)
        result = run_query(
            snapshot.identity(""),
            records,
            request,
            snapshot.observed_at,
            country=context.country,
        )
        authorize(connection, context.actor, context.grant_id).require(capability)
        return result, matching_records(records, request, snapshot.observed_at)


def read_report(
    authority: BusinessAuthority,
    context: ActionContext,
    request: ReportRequest,
    *,
    capability: Literal["read", "export"] = "read",
) -> ReportAnswer:
    return read_report_snapshot(authority, context, request, capability=capability)[0]
