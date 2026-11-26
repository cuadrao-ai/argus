"""Record origin and file intake history for the Bandeja and dossier."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict

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

    @classmethod
    def stored(cls, tx: ActionTransaction) -> UploadIntake:
        from argus.domain.ingestion.email_intake.store import PostgresEmailStore
        from argus.domain.ingestion.whatsapp.store_postgres import PostgresWhatsAppStore
        from argus.domain.postgres_connection import BorrowedConnection

        pool = BorrowedConnection(tx.connection)
        owner = tx.context.owner_id
        space = str(tx.context.actor.space_id)
        captured = PostgresWhatsAppStore(pool).captured_connections(destination_owner_id=owner)
        # A record can carry a WhatsApp attachment without an inbound webhook row.
        sources = tx.rows(
            "select distinct s.connection_id::text as id from public.business_sources s"
            " join public.financial_source_connections c on c.id=s.connection_id"
            " and c.owner_space_id=s.space_id"
            " where s.space_id=%s and c.user_id=%s and s.kind='attachment' and s.channel='whatsapp'",
            (space, owner),
        )
        return cls(
            captured.union(row["id"] for row in sources),
            email_flags(PostgresEmailStore(pool).membership(space)),
        )

    def channel(self, connection_id: str, saved_at: datetime) -> Channel:
        flag = self.emails.get(connection_id)
        if flag and flag[2] is not None and flag[2] <= saved_at:
            return "email"
        return "whatsapp" if connection_id in self.captured else "web"

    def deliveries(self, connection_id: str) -> tuple[str, ...]:
        flag = self.emails.get(connection_id)
        return flag[0] if flag else ()


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
            "channel": intake.channel(doc.connection_id, doc.created_at),
            "email_delivery_ids": intake.deliveries(doc.connection_id),
        }
        for doc in sources
        if isinstance(doc, OriginUpload)
    ]
    senders = receipt_senders(tx, uploads) if tx and uploads else {}
    channels = {view["id"]: view["channel"] for view in uploads}
    result = {}
    for source in sources:
        if isinstance(source, OriginUpload):
            key, at = source.connection_id, source.created_at
            channel, sender = channels[key], senders.get(key)
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
        channel = intake.channel(str(file.connection_id), file.received_at)
        return document.model_copy(
            update={"file": file.model_copy(update={"channel": channel})}
        )

    sources = tuple(
        source.model_copy(
            update={
                "channel": intake.channel(str(source.connection_id), source.received_at),
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
