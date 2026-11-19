from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from pydantic import Field, computed_field, model_validator

from argus.domain.business.bandeja_group import ApprovalGroup
from argus.domain.business.contracts.authority import PersonShown
from argus.domain.business.contracts.facts import Contract

#: How long a deleted document stays in Eliminados before it is purged. The
#: privacy text promises deletion within 10 business days.
PURGE_AFTER = timedelta(days=7)


DeletionReason = Literal["duplicate"]


class DeletingActor(Contract):
    """Who deleted the document, named live for the viewer as ``PersonName``
    reads. The stored marker keeps only the id (``people.named_deletion``)."""

    actor_id: UUID
    display_name: str | None = None
    email: str | None = None
    shown_as: PersonShown | None = None


class PreviousDocumentState(Contract):
    state: str
    group: ApprovalGroup
    events: dict[str, Literal["open", "dismissed"]] = Field(
        default_factory=dict, exclude_if=lambda value: not value
    )


class DeletedDocument(Contract):
    actor: DeletingActor
    at: datetime
    key: str
    previous_state: PreviousDocumentState
    #: Why it was deleted, when the person gave a reason by how they deleted
    #: it. Absent for a plain delete.
    reason: DeletionReason | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="before")
    @classmethod
    def _derived(cls, value: object) -> object:
        # A wire copy carries purge_at; the stored marker never does.
        if isinstance(value, dict):
            return {key: item for key, item in value.items() if key != "purge_at"}
        return value

    @computed_field
    @property
    def purge_at(self) -> datetime:
        return self.at + PURGE_AFTER

    def stored(self) -> dict:
        return self.model_dump(
            mode="json",
            exclude={"purge_at": True, "actor": {"display_name", "email", "shown_as"}},
        )


class DocumentCommand(Contract):
    action: Literal["delete_document", "restore_document", "purge_document"]
    document_id: UUID


class DocumentActionResult(Contract):
    document_id: UUID
    deleted: bool


def deletion(state: str, resolution: dict) -> DeletedDocument | None:
    marker = resolution.get("deleted")
    return (
        DeletedDocument.model_validate(marker)
        if state == "dismissed" and marker
        else None
    )
