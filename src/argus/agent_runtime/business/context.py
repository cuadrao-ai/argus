from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from argus.domain.business.authority import ActionContext
from argus.domain.business.contracts.actions import ActionOutcome, TurnPlan
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.contracts.dossier import BusinessDossier, SourceEvidence
from argus.domain.business.contracts.recovery import SenderLease


class BusinessActionService(Protocol):
    def resolve_actor(
        self, actor: TrustedActor, *, grant_id: UUID | None = None
    ) -> ActionContext: ...
    def read_context(self, context: ActionContext) -> dict: ...
    def record_source(
        self, context: ActionContext, source_key: str, evidence: SourceEvidence
    ) -> UUID: ...
    def plan_for_turn(
        self, context: ActionContext, turn_key: str, *, lease: SenderLease
    ) -> TurnPlan | None: ...
    def persist_plan(
        self, context: ActionContext, turn_key: str, plan: TurnPlan, *, lease: SenderLease
    ) -> TurnPlan: ...
    def execute(
        self,
        context: ActionContext,
        turn_key: str,
        action_index: int,
        *,
        lease: SenderLease,
    ) -> ActionOutcome: ...
    def dossier(self, context: ActionContext, draft_id: UUID) -> BusinessDossier: ...
    def find_related(self, context: ActionContext, draft_id: UUID) -> dict: ...


@dataclass(frozen=True)
class AuthorizedBusinessContext:
    actions: BusinessActionService
    authorization: ActionContext
    turn_key: str
    lease: SenderLease
    message_id: UUID
    received_at: datetime
    channel: Literal["web", "whatsapp"]
    begin_reply: Callable[[], str | None]
    language: str = "es-419"

    def __post_init__(self) -> None:
        actor = self.authorization.actor
        if actor.actor_kind != "owner_via_agent":
            raise ValueError("Business agent turns require owner_via_agent")
        if actor.space_id != self.lease.space_id:
            raise ValueError("Business context and lease must share one space")
        if self.received_at.tzinfo is None:
            raise ValueError("Business source timestamp must have a timezone")
        if not self.turn_key or self.channel not in {"web", "whatsapp"}:
            raise ValueError("Business turn identity and channel are required")
