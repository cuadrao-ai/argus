from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from .actions import ActionOutcome, Applied, Refused
from .facts import Contract

#: How many receipts one request approves. Each one is its own approval, run in
#: turn, so a longer list is sent as several requests.
MAX_LISTOS_PER_APPROVAL = 50


class ListoItem(Contract):
    draft_id: UUID
    version: int = Field(ge=1, strict=True)


class ApproveListos(Contract):
    """The Listos receipts a person chose, each at the version they saw."""

    items: tuple[ListoItem, ...] = Field(min_length=1, max_length=MAX_LISTOS_PER_APPROVAL)

    @model_validator(mode="after")
    def each_draft_once(self) -> ApproveListos:
        if len({item.draft_id for item in self.items}) != len(self.items):
            raise ValueError("a draft is named once")
        return self


class ListoApproval(Contract):
    """What happened to one named receipt. ``outcome_unknown`` means a replay
    with the same key settles it; ``code`` says why it was refused or unsettled."""

    draft_id: UUID
    outcome: Literal["applied", "refused", "outcome_unknown"]
    code: str | None = None
    activity_id: UUID | None = None
    #: The approved record a ``duplicate_comprobante`` refusal points at.
    existing_record_id: UUID | None = None

    @classmethod
    def of(cls, draft_id: UUID, outcome: ActionOutcome) -> ListoApproval:
        if isinstance(outcome, Applied):
            return cls(
                draft_id=draft_id, outcome="applied", activity_id=outcome.activity_id
            )
        if isinstance(outcome, Refused):
            return cls(
                draft_id=draft_id,
                outcome="refused",
                code=outcome.code,
                existing_record_id=outcome.existing_record_id,
            )
        return cls(draft_id=draft_id, outcome="outcome_unknown", code=outcome.code)


class ListosApproved(Contract):
    """One result per named receipt, in the order named."""

    results: tuple[ListoApproval, ...]
