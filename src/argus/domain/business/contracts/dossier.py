from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from .authority import ActorProvenance, Capability
from .facts import BusinessFacts, Contract, FactField


class MessageSource(Contract):
    id: UUID
    kind: Literal["message", "agent_proposal"]
    channel: Literal["web", "whatsapp"]
    received_at: datetime
    text: str = Field(min_length=1, max_length=20000)


class WebActionSource(Contract):
    id: UUID
    kind: Literal["web_action"] = "web_action"
    channel: Literal["web"] = "web"
    received_at: datetime
    text: str = Field(min_length=1, max_length=20000)


class AttachmentSource(Contract):
    id: UUID
    kind: Literal["attachment"] = "attachment"
    channel: Literal["web", "whatsapp"]
    received_at: datetime
    connection_id: UUID
    filename: str | None
    media_type: str


SourceEvidence = Annotated[
    MessageSource | WebActionSource | AttachmentSource, Field(discriminator="kind")
]
QuestionState = Literal[
    "open", "answered", "owner_does_not_know", "waiting_for_window", "withdrawn"
]


class ReviewQuestion(Contract):
    id: UUID
    draft_id: UUID
    field: FactField
    asked_of: Literal["owner", "accountant"]
    channel: Literal["whatsapp", "web"]
    state: QuestionState
    prompt: str = Field(min_length=1, max_length=500)
    allowed_answers: tuple[Literal["known", "owner_does_not_know"], ...] = Field(
        min_length=1
    )
    answer_source_id: UUID | None = None
    created_at: datetime

    @model_validator(mode="after")
    def answer_provenance(self) -> ReviewQuestion:
        if (
            self.state in {"answered", "owner_does_not_know"}
            and self.answer_source_id is None
        ):
            raise ValueError("answered questions require their answer source")
        if self.state == "owner_does_not_know" and self.asked_of != "accountant":
            raise ValueError("owner uncertainty moves the question to the accountant")
        return self


class DraftRevision(Contract):
    draft_id: UUID
    version: int = Field(ge=1)
    actor: ActorProvenance
    before: BusinessFacts | None
    after: BusinessFacts
    source_ids: tuple[UUID, ...]
    turn_key: str | None = None
    created_at: datetime


class Blocker(Contract):
    code: str
    field: FactField | None = None


class RecordedApproval(Contract):
    status: Literal["recorded"] = "recorded"
    activity_id: UUID
    reviewed_version: int = Field(ge=1)
    actor: ActorProvenance


class UnsettledApproval(Contract):
    status: Literal["outcome_unknown", "failed"]
    code: str
    reviewed_version: int = Field(ge=1)


ApprovalResult = Annotated[
    RecordedApproval | UnsettledApproval, Field(discriminator="status")
]


class AccountChoice(Contract):
    id: UUID
    nickname: str | None
    type: str
    currency: str


class RecordContext(Contract):
    space_id: UUID
    space_name: str
    accounts: tuple[AccountChoice, ...]
    capabilities: frozenset[Capability]


class BusinessDossier(RecordContext):
    draft_id: UUID
    version: int = Field(ge=1)
    review_state: Literal["open", "accepting", "accepted", "dismissed"]
    facts: BusinessFacts
    sources: tuple[SourceEvidence, ...]
    questions: tuple[ReviewQuestion, ...]
    history: tuple[DraftRevision, ...]
    blockers: tuple[Blocker, ...]
    approval_available: bool
    approval_result: ApprovalResult | None = None
