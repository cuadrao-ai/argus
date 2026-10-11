from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from psycopg_pool import ConnectionPool

from argus.domain.business.actions import captures, mutations, plans, related, sources
from argus.domain.business.actions import dossier as views
from argus.domain.business.authority import ActionContext, ActionError, BusinessAuthority
from argus.domain.business.contracts.actions import (
    ActionOutcome,
    ApproveExpense,
    CaptureNote,
    ExistingDraft,
    ExplainStatus,
    FindRelated,
    ReadContext,
    ReviewCommand,
    ReviewDraft,
    TurnPlan,
)
from argus.domain.business.contracts.authority import ActorProvenance, TrustedActor
from argus.domain.business.contracts.dossier import (
    BusinessDossier,
    RecordContext,
    SourceEvidence,
    WebActionSource,
)
from argus.domain.business.contracts.recovery import SenderLease
from argus.domain.business.transactions import GrantImportStore, transaction
from argus.domain.ingestion.reconcile.service import ReconciliationService


class BusinessActions:
    def __init__(self, pool: ConnectionPool, imports: ReconciliationService) -> None:
        self.authority = BusinessAuthority(pool)
        self.imports = imports

    def resolve_actor(
        self, actor: TrustedActor, *, grant_id: UUID | None = None
    ) -> ActionContext:
        return self.authority.resolve_actor(actor, grant_id=grant_id)

    def context_for_draft(self, actor_id: UUID, draft_id: UUID) -> ActionContext:
        return self.authority.for_record(actor_id, draft_id, receipt=False)

    def context_for_receipt(self, actor_id: UUID, connection_id: UUID) -> ActionContext:
        return self.authority.for_record(actor_id, connection_id, receipt=True)

    def record_source(
        self, context: ActionContext, source_key: str, evidence: SourceEvidence
    ) -> UUID:
        with transaction(self.authority, context, "prepare") as tx:
            return sources.record_source(tx, source_key, evidence)

    def capture(
        self, context: ActionContext, request: CaptureNote, key: str
    ) -> ActionOutcome:
        return captures.capture(self, context, request, key)

    def captures(
        self, context: ActionContext, *, query: str = "", limit: int = 20
    ) -> list[dict]:
        return captures.entries(self, context, query=query, limit=limit)

    def persist_plan(
        self,
        context: ActionContext,
        turn_key: str,
        plan: TurnPlan,
        *,
        lease: SenderLease | None = None,
    ) -> TurnPlan:
        with transaction(self.authority, context, "prepare", lease) as tx:
            return plans.persist(tx, turn_key, plan, lease)

    def plan_for_turn(
        self, context: ActionContext, turn_key: str, *, lease: SenderLease
    ) -> TurnPlan | None:
        with transaction(self.authority, context, lease=lease) as tx:
            row = plans.turn(tx, turn_key, lease)
            if row["plan"] is None:
                if row["model_state"] == "unknown":
                    raise ActionError("invalid_input", "business_model_outcome_unknown")
                return None
            actor = ActorProvenance.model_validate(row["plan_actor"])
            if not plans.same_authority(tx, actor):
                raise ActionError("permission_denied", "business_plan_authority_changed")
            return TurnPlan.model_validate(row["plan"])

    def mark_turn_waiting_for_window(
        self, context: ActionContext, turn_key: str, *, lease: SenderLease
    ) -> None:
        with transaction(self.authority, context, "prepare", lease) as tx:
            row = plans.turn(tx, turn_key, lease)
            if row["plan"] is None:
                raise ActionError("invalid_input", "business_plan_required")
            actor = ActorProvenance.model_validate(row["plan_actor"])
            if not plans.same_authority(tx, actor):
                raise ActionError("permission_denied", "business_plan_authority_changed")
            tx.rows(
                "update public.business_questions q set state='waiting_for_window'"
                " where q.space_id=%s and q.state='open' and q.asked_of='owner'"
                " and q.channel='whatsapp' and exists("
                " select 1 from public.business_action_receipts r where r.turn_key=%s"
                " and r.space_id=q.space_id and r.actor_id=%s"
                " and r.outcome->>'question_id'=q.id::text"
                " and r.outcome->>'outcome' in ('applied','replayed'))",
                (context.actor.space_id, turn_key, context.actor.actor_id),
            )

    def execute(
        self,
        context: ActionContext,
        turn_key: str,
        action_index: int,
        *,
        lease: SenderLease | None = None,
    ) -> ActionOutcome:
        try:
            with transaction(self.authority, context, lease=lease) as tx:
                row = plans.turn(tx, turn_key, lease)
                if row["plan"] is None:
                    raise ActionError("invalid_input", "business_plan_required")
                plan = TurnPlan.model_validate(row["plan"])
                actor = ActorProvenance.model_validate(row["plan_actor"])
                if not plans.same_authority(tx, actor):
                    raise ActionError(
                        "permission_denied", "business_plan_authority_changed"
                    )
                if not 0 <= action_index < len(plan.actions):
                    raise ActionError("invalid_input", "business_action_index_invalid")
                action = plan.actions[action_index]
                key = plans.action_key(turn_key, action_index)
                saved = plans.receipt(tx, key, action)
                if saved is not None:
                    return plans.replay(saved)
                prior = tx.rows(
                    "select action_index,outcome from public.business_action_receipts"
                    " where turn_key=%s and action_index<%s order by action_index",
                    (turn_key, action_index),
                )
                if len(prior) != action_index or any(
                    row["outcome"] is None
                    or row["outcome"]["outcome"] == "outcome_unknown"
                    for row in prior
                ):
                    raise ActionError("invalid_input", "business_prior_action_unsettled")
                plans.start_receipt(
                    tx, key, action, actor=actor, turn_key=turn_key, index=action_index
                )
                try:
                    with tx.connection.transaction():
                        if not isinstance(
                            action, (ReadContext, FindRelated, ExplainStatus)
                        ):
                            tx.authorization.require("prepare")
                        result = mutations.apply(
                            tx, action, actor, turn_key, action_index
                        )
                except ActionError as error:
                    result = error.result
                return plans.finish_receipt(tx, key, result)
        except ActionError as error:
            return error.result

    def dossier(self, context: ActionContext, draft_id: UUID) -> BusinessDossier:
        with transaction(self.authority, context) as tx:
            return views.dossier(tx, draft_id)

    def record_context(self, context: ActionContext) -> RecordContext:
        with transaction(self.authority, context) as tx:
            return views.record_context(tx)

    def read_context(self, context: ActionContext) -> dict:
        with transaction(self.authority, context) as tx:
            drafts = tx.rows(
                "select id,version,resolution->'business'->'facts' as facts"
                " from public.financial_import_events where owner_space_id=%s and user_id=%s"
                " and state='open' and resolution ? 'business' order by updated_at desc,id limit 20",
                (context.actor.space_id, context.owner_id),
            )
            questions = tx.rows(
                "select id,draft_id,field,asked_of,channel,state,prompt,allowed_answers,"
                " answer_source_id,created_at from public.business_questions where space_id=%s"
                " and state in ('open','owner_does_not_know','waiting_for_window')"
                " order by created_at,id limit 20",
                (context.actor.space_id,),
            )
            return {
                **views.record_context(tx).model_dump(mode="json"),
                "drafts": [{**row, "id": str(row["id"])} for row in drafts],
                "questions": [
                    views.ReviewQuestion.model_validate(row).model_dump(mode="json")
                    for row in questions
                ],
            }

    def find_related(self, context: ActionContext, draft_id: UUID) -> dict:
        with transaction(self.authority, context) as tx:
            views.dossier(tx, draft_id)
            candidates = related.candidate_ids(tx, tx.imports.event(str(draft_id)))
        scoped = ReconciliationService(
            GrantImportStore(self.authority, context, "read"),
            self.imports.money,
            self.imports.clock,
        )
        detail = scoped.detail(
            user_id=context.owner_id, event_id=str(draft_id), scope=context.scope
        )
        return {
            "draft_ids": sorted(
                set(
                    candidates
                    + detail["possible_duplicates"]
                    + detail["recorded_duplicates"]
                )
            )[:20],
            "activity_ids": detail["existing_activity_matches"],
        }

    def review(
        self,
        context: ActionContext,
        draft_id: UUID,
        request: ReviewDraft,
        key: str,
    ) -> ActionOutcome:
        command = ReviewCommand(draft_id=draft_id, request=request)
        try:
            with transaction(self.authority, context) as tx:
                saved = plans.receipt(tx, key, command)
                if saved is not None:
                    return plans.replay(saved)
                plans.start_receipt(tx, key, command)
                try:
                    with tx.connection.transaction():
                        tx.authorization.require("prepare")
                        if context.actor.actor_kind != "member":
                            raise ActionError(
                                "permission_denied", "business_human_command_required"
                            )
                        evidence = WebActionSource(
                            id=uuid4(),
                            received_at=datetime.now(timezone.utc),
                            text=json.dumps(
                                command.model_dump(mode="json", exclude_none=True),
                                sort_keys=True,
                                separators=(",", ":"),
                                ensure_ascii=False,
                            ),
                        )
                        source_id = sources.record_source(
                            tx, f"web:{context.actor.actor_id}:{key}", evidence
                        )
                        result = mutations.revise(
                            tx,
                            ExistingDraft(draft_id=draft_id, version=request.version),
                            request.facts,
                            (source_id,),
                            tx.authorization.provenance,
                        )
                except ActionError as error:
                    result = error.result
                return plans.finish_receipt(tx, key, result)
        except ActionError as error:
            return error.result

    def approve(
        self,
        context: ActionContext,
        draft_id: UUID,
        request: ApproveExpense,
        key: str,
    ) -> ActionOutcome:
        from argus.domain.business.actions.approval import approve

        return approve(self, context, draft_id, request, key)
