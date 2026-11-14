from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from pydantic import Field, computed_field, model_validator

from argus.domain.business.contracts.facts import Contract

#: How long a deleted document stays in Eliminados before it is purged. The
#: privacy text promises deletion within 10 business days.
PURGE_AFTER = timedelta(days=7)


class DeletingActor(Contract):
    actor_id: UUID
    display_name: str


class PreviousDocumentState(Contract):
    state: str
    group: Literal["attention", "listo"]
    events: dict[str, Literal["open", "dismissed"]] = Field(
        default_factory=dict, exclude_if=lambda value: not value
    )


class DeletedDocument(Contract):
    actor: DeletingActor
    at: datetime
    key: str
    previous_state: PreviousDocumentState

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
        return self.model_dump(mode="json", exclude={"purge_at"})


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
