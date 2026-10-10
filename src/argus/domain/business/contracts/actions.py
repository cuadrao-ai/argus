from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from .facts import (
    BusinessFactPatch,
    BusinessShare,
    Contract,
    FactField,
    FactInput,
    Funding,
)


class ExistingDraft(Contract):
    draft_id: UUID
    version: int = Field(ge=1)


class PlannedDraft(Contract):
    from_action: int = Field(ge=0)


DraftReference = ExistingDraft | PlannedDraft
MAX_TURN_ACTIONS = 8


class ReadContext(Contract):
    action: Literal["business_read_context"] = "business_read_context"


class ProposeActivity(Contract):
    action: Literal["business_propose_activity"] = "business_propose_activity"
    draft: DraftReference | None = None
    facts: BusinessFactPatch
    source_ids: tuple[UUID, ...] = Field(min_length=1)
    answers_question_id: UUID | None = None


class AttachSource(Contract):
    action: Literal["business_attach_source"] = "business_attach_source"
    draft: DraftReference
    source_id: UUID


class ProposeAllocation(Contract):
    action: Literal["business_propose_allocation"] = "business_propose_allocation"
    draft: DraftReference
    funding: FactInput[Funding]
    business_share: FactInput[BusinessShare]
    source_ids: tuple[UUID, ...] = Field(min_length=1)
    answers_question_id: UUID | None = None


class FindRelated(Contract):
    action: Literal["business_find_related"] = "business_find_related"
    draft_id: UUID


class Ask(Contract):
    action: Literal["business_ask"] = "business_ask"
    draft: DraftReference
    field: FactField
    asked_of: Literal["owner", "accountant"]
    prompt: str = Field(min_length=1, max_length=500)


class ExplainStatus(Contract):
    action: Literal["business_explain_status"] = "business_explain_status"
    draft_id: UUID


BusinessAction = Annotated[
    ReadContext
    | ProposeActivity
    | AttachSource
    | ProposeAllocation
    | FindRelated
    | Ask
    | ExplainStatus,
    Field(discriminator="action"),
]


class TurnPlan(Contract):
    schema_version: Literal[1] = 1
    actions: tuple[BusinessAction, ...] = Field(max_length=MAX_TURN_ACTIONS)

    @model_validator(mode="after")
    def earlier_draft_references(self) -> TurnPlan:
        for index, action in enumerate(self.actions):
            draft = getattr(action, "draft", None)
            if isinstance(draft, PlannedDraft):
                if draft.from_action >= index:
                    raise ValueError("draft references must name an earlier action")
                producer = self.actions[draft.from_action]
                if (
                    not isinstance(producer, ProposeActivity)
                    or producer.draft is not None
                ):
                    raise ValueError("draft references must name a draft creation")
        return self


class ReviewDraft(Contract):
    version: int = Field(ge=1)
    facts: BusinessFactPatch


class ApproveExpense(Contract):
    version: int = Field(ge=1)
    action: Literal["record_expense"]


class ReviewCommand(Contract):
    action: Literal["review_draft"] = "review_draft"
    draft_id: UUID
    request: ReviewDraft


class ApprovalCommand(Contract):
    action: Literal["approve_expense"] = "approve_expense"
    draft_id: UUID
    request: ApproveExpense


Command = BusinessAction | ReviewCommand | ApprovalCommand


class Applied(Contract):
    outcome: Literal["applied", "replayed"]
    draft_id: UUID | None = None
    version: int | None = Field(default=None, ge=1)
    question_id: UUID | None = None
    activity_id: UUID | None = None


class Refused(Contract):
    outcome: Literal[
        "stale_version",
        "not_found",
        "permission_denied",
        "invalid_input",
        "idempotency_conflict",
    ]
    code: str


class OutcomeUnknown(Contract):
    outcome: Literal["outcome_unknown"] = "outcome_unknown"
    code: str


ActionOutcome = Annotated[
    Applied | Refused | OutcomeUnknown, Field(discriminator="outcome")
]


def canonical_input_hash(command: Contract) -> str:
    encoded = json.dumps(
        command.model_dump(mode="json", exclude_none=True),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
