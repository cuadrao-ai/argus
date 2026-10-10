from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from .actions import ActionOutcome, Command, TurnPlan
from .authority import ActorProvenance
from .facts import Contract

TurnPhase = Literal[
    "captured",
    "turn_running",
    "turn_done",
    "reply_pending",
    "reply_sent",
    "reply_unknown",
]


class SenderLease(Contract):
    space_id: UUID
    sender_hash: str
    holder: UUID
    fence: int = Field(ge=1)
    lease_until: datetime


class DurableTurn(Contract):
    space_id: UUID
    actor_id: UUID
    sender_hash: str
    turn_key: str
    arrival_sequence: int = Field(ge=1)
    phase: TurnPhase
    model_state: Literal["not_started", "running", "completed", "unknown"]
    plan: TurnPlan | None = None
    plan_actor: ActorProvenance | None = None
    lease_fence: int | None = Field(default=None, ge=1)
    reply_text: str | None = None

    @model_validator(mode="after")
    def completed_plan(self) -> DurableTurn:
        if self.model_state == "completed" and self.plan is None:
            raise ValueError("completed interpretation requires its persisted plan")
        if self.plan is not None and self.model_state != "completed":
            raise ValueError("a persisted plan requires completed interpretation")
        if (self.plan is None) != (self.plan_actor is None):
            raise ValueError("persisted plan requires its actor provenance")
        if self.plan_actor is not None and self.plan_actor.actor_id != self.actor_id:
            raise ValueError("plan provenance must match the actual actor")
        if self.phase in {"turn_done", "reply_pending", "reply_sent", "reply_unknown"}:
            if self.plan is None:
                raise ValueError("completed turns require a plan")
        return self


class ActionReceipt(Contract):
    space_id: UUID
    actor_id: UUID
    actor: ActorProvenance
    idempotency_key: str = Field(min_length=1, max_length=80)
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    command: Command
    turn_key: str | None = None
    action_index: int | None = Field(default=None, ge=0)
    outcome: ActionOutcome | None = None
    created_at: datetime

    @model_validator(mode="after")
    def action_identity(self) -> ActionReceipt:
        if self.actor.actor_id != self.actor_id:
            raise ValueError("receipt provenance must match the actual actor")
        if (self.turn_key is None) != (self.action_index is None):
            raise ValueError("turn key and action index must be supplied together")
        if self.turn_key is None and self.command.action not in {
            "review_draft",
            "approve_expense",
        }:
            raise ValueError("agent action receipts require their persisted turn plan")
        return self
