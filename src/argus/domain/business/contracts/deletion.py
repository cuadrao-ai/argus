from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from argus.domain.business.contracts.facts import Contract


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


class DocumentCommand(Contract):
    action: Literal["delete_document", "restore_document"]
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
