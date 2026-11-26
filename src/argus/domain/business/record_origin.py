"""Record origin and file intake history for the Bandeja and dossier."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Literal, TypedDict
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from argus.domain.business.annotations import OWN_SOURCE_SQL
from argus.domain.business.contracts.authority import SentBy
from argus.domain.business.contracts.dossier import (
    AttachmentSource,
    BusinessDossier,
    ComparedDocument,
    MessageSource,
    RecordOrigin,
    WebActionSource,
)
from argus.domain.business.sent_by import receipt_senders

if TYPE_CHECKING:
    from argus.domain.business.transactions import ActionTransaction
    from argus.domain.ingestion.email_intake.store import EmailRelation

Channel = Literal["web", "whatsapp", "email"]
EmailFlag = tuple[tuple[str, ...], bool, datetime | None]


class FileArrival(TypedDict):
    channel: Channel
    received_at: datetime


class OriginUpload(BaseModel):
    """The original upload metadata retained by the document store."""

    model_config = ConfigDict(from_attributes=True)
    connection_id: str
    filename: str | None
    size_bytes: int | None
    created_at: datetime


def email_flags(relations: Mapping[str, EmailRelation]) -> dict[str, EmailFlag]:
    return {
        key: (tuple(row["delivery_ids"]), row["grouped"], row["first_received_at"])
        for key, row in relations.items()
    }


@dataclass(frozen=True)
class UploadIntake:
    captured: frozenset[str]
    emails: Mapping[str, EmailFlag]
    whatsapp_arrivals: Mapping[str, datetime] = field(default_factory=dict)

    @classmethod
    def stored(cls, tx: ActionTransaction) -> UploadIntake:
        from argus.domain.ingestion.email_intake.store import PostgresEmailStore
        from argus.domain.postgres_connection import BorrowedConnection

        pool = BorrowedConnection(tx.connection)
        owner = tx.context.owner_id
        space = str(tx.context.actor.space_id)
        arrivals = tx.rows(
            "select m.connection_id::text as id,min(m.received_at) as received_at"
            " from public.whatsapp_inbound_messages m join public.financial_source_connections c"
            " on c.id=m.connection_id where c.owner_space_id=%s and c.user_id=%s"
            " and m.status='captured' group by m.connection_id", (space, owner),
        )
        # A record can carry a WhatsApp attachment without an inbound webhook row.
        sources = tx.rows(
            "select distinct s.connection_id::text as id from public.business_sources s"
            " join public.financial_source_connections c on c.id=s.connection_id"
            " and c.owner_space_id=s.space_id"
            " where s.space_id=%s and c.user_id=%s and s.kind='attachment' and s.channel='whatsapp'",
            (space, owner),
        )
        return cls(
            frozenset(row["id"] for row in sources),
            email_flags(PostgresEmailStore(pool).membership(space)),
            {row["id"]: row["received_at"] for row in arrivals},
        )

    def arrival(self, connection_id: str, saved_at: datetime) -> FileArrival:
        """The earliest file or inbound message, even when processing ran later."""
        at = saved_at
        channel: Channel = "whatsapp" if connection_id in self.captured else "web"
        whatsapp = self.whatsapp_arrivals.get(connection_id)
        if whatsapp is not None and whatsapp <= at:
            channel, at = "whatsapp", whatsapp
        email = self.emails.get(connection_id)
        if email and email[2] is not None and email[2] <= at:
            channel, at = "email", email[2]
        return {"channel": channel, "received_at": at}

    def deliveries(self, connection_id: str) -> tuple[str, ...]:
        flag = self.emails.get(connection_id)
        return flag[0] if flag else ()


@dataclass(frozen=True)
class DraftArrival:
    received_at: datetime
    first_source_id: UUID
    file_source_id: UUID | None
    filename: str | None


def draft_arrivals(
    tx: ActionTransaction, draft_ids: Sequence[UUID], intake: UploadIntake | None = None
) -> dict[UUID, DraftArrival]:
    """Each record's first own source and first own file in actual arrival order."""
    if not draft_ids:
        return {}
    rows = tx.rows(
        "select l.draft_id,s.id,s.received_at,s.connection_id,"
        " (d.draft->>'created_at')::timestamptz as saved_at,d.draft->>'filename' as filename"
        " from public.business_draft_sources l join public.business_sources s"
        " on s.id=l.source_id and s.space_id=l.space_id"
        " left join public.financial_document_extractions d on d.connection_id=s.connection_id"
        f" where l.space_id=%s and l.draft_id=any(%s::uuid[]) and {OWN_SOURCE_SQL}",
        (tx.context.actor.space_id, list(draft_ids)),
    )
    grouped: dict[UUID, list[dict]] = {}
    for row in rows:
        if row["saved_at"] is not None:
            if intake is None:
                intake = UploadIntake.stored(tx)
            row["received_at"] = intake.arrival(str(row["connection_id"]), row["saved_at"])["received_at"]
        grouped.setdefault(row["draft_id"], []).append(row)
    found = {}
    for draft_id, sources in grouped.items():
        sources.sort(key=lambda row: (row["received_at"], row["id"]))
        first = sources[0]
        file = next((row for row in sources if row["connection_id"]), None)
        found[draft_id] = DraftArrival(
            first["received_at"], first["id"], file["id"] if file else None,
            file["filename"] if file else None,
        )
    return found


def record_origins(
    tx: ActionTransaction | None,
    sources: Sequence[OriginUpload | MessageSource | WebActionSource],
    intake: UploadIntake,
    message_senders: Mapping[str, SentBy] | None = None,
) -> dict[str, RecordOrigin]:
    """Resolve intake and viewer-scoped senders together for one record or a page."""
    uploads = [
        {
            "id": doc.connection_id,
            **intake.arrival(doc.connection_id, doc.created_at),
            "email_delivery_ids": intake.deliveries(doc.connection_id),
        }
        for doc in sources
        if isinstance(doc, OriginUpload)
    ]
    senders = receipt_senders(tx, uploads) if tx and uploads else {}
    by_id = {view["id"]: view for view in uploads}
    result = {}
    for source in sources:
        if isinstance(source, OriginUpload):
            key = source.connection_id
            channel, at = by_id[key]["channel"], by_id[key]["received_at"]
            sender = senders.get(key)
            filename, size = source.filename or None, source.size_bytes
        else:
            key, at = str(source.id), source.received_at
            channel = "note" if source.channel == "web" else source.channel
            sender = (message_senders or {}).get(key)
            filename = size = None
        result[key] = RecordOrigin(
            channel=channel,
            sent_by=sender,
            received_at=at,
            filename=filename,
            size_bytes=size,
        )
    return result


def with_source_channels(
    dossier: BusinessDossier, intake: UploadIntake
) -> BusinessDossier:
    """Each evidence or compared file carries its own upload channel."""

    def compared(document: ComparedDocument) -> ComparedDocument:
        file = document.file
        if file is None:
            return document
        arrival = intake.arrival(str(file.connection_id), file.received_at)
        return document.model_copy(
            update={"file": file.model_copy(update=arrival)}
        )

    sources = tuple(
        source.model_copy(
            update={
                **intake.arrival(str(source.connection_id), source.received_at),
                "email_delivery_ids": intake.deliveries(str(source.connection_id)),
            }
        )
        if isinstance(source, AttachmentSource)
        else source
        for source in dossier.sources
    )
    candidates = []
    for candidate in dossier.duplicate_candidates:
        pair = candidate.comparison
        comparison = pair.model_copy(
            update={"document": compared(pair.document), "other": compared(pair.other)}
        )
        candidates.append(candidate.model_copy(update={"comparison": comparison}))
    return dossier.model_copy(
        update={"sources": sources, "duplicate_candidates": tuple(candidates)}
    )
