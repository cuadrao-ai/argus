from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
    model_validator,
)

from .authority import ActorProvenance
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


class BoundDraft(Contract):
    draft_id: UUID
    base_version: int = Field(ge=1, strict=True)


DraftReference = ExistingDraft | PlannedDraft | BoundDraft
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

    @model_validator(mode="after")
    def consistent_draft_bindings(self) -> TurnPlan:
        targets: dict[UUID, ExistingDraft | BoundDraft] = {}
        for action in self.actions:
            draft = getattr(action, "draft", None)
            if isinstance(draft, (ExistingDraft, BoundDraft)):
                prior = targets.get(draft.draft_id)
                if prior is not None and (
                    isinstance(prior, BoundDraft) or isinstance(draft, BoundDraft)
                ):
                    if prior != draft:
                        raise ValueError("a plan requires one captured draft binding")
                targets[draft.draft_id] = draft
        return self


class ReviewDraft(Contract):
    version: int = Field(ge=1)
    facts: BusinessFactPatch


class ApproveExpense(Contract):
    version: int = Field(ge=1)
    action: Literal["record_expense"]


class ApproveIncome(Contract):
    version: int = Field(ge=1, strict=True)
    action: Literal["record_income"]


class SettleRemainder(Contract):
    """A person settles the read purchases a recorded draft does not cover."""

    version: int = Field(ge=1)


class SettleRemainderCommand(Contract):
    action: Literal["settle_remainder"] = "settle_remainder"
    draft_id: UUID
    request: SettleRemainder


class MarkPersonal(Contract):
    """The owner or a prepare-holder marks a receipt as personal (no part of
    it is the Business's) or takes the mark back. Reversible, a new revision
    each way."""

    version: int = Field(ge=1)
    personal: bool


class MarkPersonalCommand(Contract):
    action: Literal["mark_personal"] = "mark_personal"
    draft_id: UUID
    request: MarkPersonal


class DecideFiscalInclusion(Contract):
    """A prepare-holder other than the owner answers whether a personal receipt
    that carries a fiscal number goes into the 606."""

    version: int = Field(ge=1)
    include: bool


class DecideFiscalInclusionCommand(Contract):
    action: Literal["decide_606"] = "decide_606"
    draft_id: UUID
    request: DecideFiscalInclusion


class ReviewCommand(Contract):
    action: Literal["review_draft"] = "review_draft"
    draft_id: UUID
    request: ReviewDraft


class ApprovalCommand(Contract):
    action: Literal["approve_expense"] = "approve_expense"
    draft_id: UUID
    request: ApproveExpense


class CaptureNote(Contract):
    text: str = Field(min_length=1, max_length=20000)
    draft: ExistingDraft | None = None

    @field_validator("draft", mode="before")
    @classmethod
    def exact_target_version(cls, value: object) -> object:
        if isinstance(value, dict):
            version = value.get("version")
            if not isinstance(version, int) or isinstance(version, bool):
                raise ValueError("capture target version must be an integer")
        return value

    @model_validator(mode="after")
    def original_text(self) -> CaptureNote:
        if not self.text.strip():
            raise ValueError("capture text must not be blank")
        if "\x00" in self.text:
            raise ValueError("capture text must not contain NUL")
        return self


class CaptureCommand(Contract):
    action: Literal["capture_note"] = "capture_note"
    request: CaptureNote


class IncomeApprovalCommand(Contract):
    action: Literal["approve_income"] = "approve_income"
    draft_id: UUID
    request: ApproveIncome


class AttachmentPreparationBinding(Contract):
    schema_version: Literal[1] = 1
    binding_id: UUID
    space_id: UUID
    owner_id: UUID
    connection_id: UUID
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    actor: ActorProvenance
    target: ExistingDraft | None
    consent: Literal[True]
    captured_at: AwareDatetime

    @model_serializer(mode="wrap")
    def explicit_target(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, object]:
        payload = handler(self)
        if self.target is None:
            payload["target"] = None
        return payload

    @field_validator("target", mode="before")
    @classmethod
    def exact_target_version(cls, value: object) -> object:
        if isinstance(value, dict):
            version = value.get("version")
            if not isinstance(version, int) or isinstance(version, bool):
                raise ValueError("attachment target version must be an integer")
        return value

    @field_validator("consent", mode="before")
    @classmethod
    def affirmative_consent(cls, value: object) -> object:
        if value is not True:
            raise ValueError("attachment preparation requires explicit consent")
        return value

    @model_validator(mode="after")
    def original_preparer(self) -> AttachmentPreparationBinding:
        if self.actor.actor_kind != "extractor":
            raise ValueError("attachment preparation requires extractor provenance")
        return self


class PrepareAttachmentCommand(Contract):
    action: Literal["prepare_attachment"] = "prepare_attachment"
    binding: AttachmentPreparationBinding
    batch_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RebindAttachmentCommand(Contract):
    """The owner moved a receipt's preparation binding from a grant that is
    no longer live to their current one. The ledger row of that move."""

    action: Literal["rebind_attachment"] = "rebind_attachment"
    previous_binding_id: UUID
    previous_grant_id: UUID
    binding: AttachmentPreparationBinding


Command = (
    BusinessAction
    | ReviewCommand
    | ApprovalCommand
    | CaptureCommand
    | IncomeApprovalCommand
    | PrepareAttachmentCommand
    | SettleRemainderCommand
    | RebindAttachmentCommand
    | MarkPersonalCommand
    | DecideFiscalInclusionCommand
)


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
