from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from argus.domain.business.actions import captures, mutations, plans, related, sources
from argus.domain.business.actions import dossier as views
from argus.domain.business.authority import (
    ActionContext,
    ActionError,
    BusinessAuthority,
    authorize,
)
from argus.domain.business.contracts.actions import (
    ActionOutcome,
    Applied,
    ApproveExpense,
    ApproveIncome,
    AttachmentPreparationBinding,
    CaptureNote,
    DecideFiscalInclusion,
    DecideFiscalInclusionCommand,
    ExistingDraft,
    ExplainStatus,
    FindRelated,
    MarkPersonal,
    MarkPersonalCommand,
    PrepareAttachmentCommand,
    ReadContext,
    RebindAttachmentCommand,
    ReviewCommand,
    ReviewDraft,
    SettleRemainder,
    SettleRemainderCommand,
    TurnPlan,
    canonical_input_hash,
)
from argus.domain.business.contracts.authority import ActorProvenance, TrustedActor
from argus.domain.business.contracts.dossier import (
    BusinessDossier,
    RecordContext,
    SourceEvidence,
    WebActionSource,
)
from argus.domain.business.contracts.recovery import SenderLease
from argus.domain.business.duplicates import flag_receipt_duplicates
from argus.domain.business.transactions import (
    ActionTransaction,
    GrantImportStore,
    transaction,
)
from argus.domain.ingestion.documents.models import DocumentDraft, ExtractionBatch
from argus.domain.ingestion.reconcile.service import ReconciliationService
from argus.domain.owner_scope import OwnerScope, space_id


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

    def settle_remainder(
        self,
        context: ActionContext,
        draft_id: UUID,
        request: SettleRemainder,
        key: str,
    ) -> ActionOutcome:
        """A person with approval permission settles the read purchases a
        recorded draft does not cover: the receipt stops asking for them. One
        ledger row; the facts and the recorded money do not change."""

        from dataclasses import replace

        from argus.domain.business.contracts.facts import BusinessResolution
        from argus.domain.ingestion.reconcile.model import EventNotFound

        command = SettleRemainderCommand(draft_id=draft_id, request=request)
        try:
            with transaction(self.authority, context, "approve") as tx:
                saved = plans.receipt(tx, key, command)
                if saved is not None:
                    return plans.replay(saved)
                plans.start_receipt(tx, key, command)
                try:
                    with tx.connection.transaction():
                        tx.authorization.require("approve")
                        if context.actor.actor_kind != "member":
                            raise ActionError(
                                "permission_denied", "business_human_command_required"
                            )
                        try:
                            event = tx.imports.event(str(draft_id))
                        except EventNotFound:
                            raise ActionError(
                                "not_found", "business_record_not_found"
                            ) from None
                        if event.version != request.version:
                            raise ActionError("stale_version", "stale_version")
                        if event.state != "accepted":
                            raise ActionError(
                                "invalid_input", "business_draft_not_recorded"
                            )
                        resolution = BusinessResolution.model_validate(
                            event.resolution["business"]
                        )
                        if not resolution.unrecorded_purchases():
                            raise ActionError("invalid_input", "business_remainder_none")
                        settled = dict(event.resolution)
                        settled["business"] = resolution.model_copy(
                            update={"remainder_settled": True}
                        ).model_dump(mode="json")
                        event = replace(
                            event,
                            resolution=settled,
                            version=event.version + 1,
                            updated_at=datetime.now(timezone.utc),
                        )
                        tx.imports.put_event(event)
                        result = Applied(
                            outcome="applied", draft_id=event.id, version=event.version
                        )
                except ActionError as error:
                    result = error.result
                return plans.finish_receipt(tx, key, result)
        except ActionError as error:
            return error.result

    def mark_personal(
        self,
        context: ActionContext,
        draft_id: UUID,
        request: MarkPersonal,
        key: str,
    ) -> ActionOutcome:
        """The owner alone marks a receipt as personal (business_share none,
        stated by the owner) or takes the mark back; on an open or an approved
        draft, a new revision each way, one ledger row naming the grant."""

        from argus.domain.business.contracts.facts import Known, WholeBusinessShare

        command = MarkPersonalCommand(draft_id=draft_id, request=request)

        def change(facts, source_id):  # noqa: ANN001, ANN202
            return facts.model_copy(
                update={
                    "business_share": Known(
                        value=WholeBusinessShare(
                            kind="none" if request.personal else "all"
                        ),
                        origin="owner_stated",
                        verified=True,
                        source_ids=(source_id,),
                    )
                }
            )

        return self._mark(
            context, draft_id, request.version, key, command, change, owner=True
        )

    def decide_606(
        self,
        context: ActionContext,
        draft_id: UUID,
        request: DecideFiscalInclusion,
        key: str,
    ) -> ActionOutcome:
        """A prepare-holder other than the owner answers whether a personal
        receipt that carries a fiscal number goes into the 606. The app never
        decides; the owner reads the answer."""

        from argus.domain.business.contracts.facts import (
            FiscalFacts,
            Known,
            fiscal_value,
            is_personal,
        )

        command = DecideFiscalInclusionCommand(draft_id=draft_id, request=request)

        def change(facts, source_id):  # noqa: ANN001, ANN202
            if not is_personal(facts) or fiscal_value(facts) is None:
                raise ActionError("invalid_input", "business_606_not_applicable")
            fiscal = facts.fiscal or FiscalFacts()
            return facts.model_copy(
                update={
                    "fiscal": fiscal.model_copy(
                        update={
                            "include_606": Known(
                                value=request.include,
                                origin="member_set",
                                verified=True,
                                source_ids=(source_id,),
                            )
                        }
                    )
                }
            )

        return self._mark(
            context, draft_id, request.version, key, command, change, owner=False
        )

    def _mark(  # noqa: ANN202
        self,
        context: ActionContext,
        draft_id: UUID,
        version: int,
        key: str,
        command,  # noqa: ANN001
        change,  # noqa: ANN001
        *,
        owner: bool,
    ) -> ActionOutcome:
        """One person's fact on a draft, open or approved: a revision row that
        says who, through which grant, and a ledger row for the command."""

        from dataclasses import replace

        from argus.domain.business.actions.mutations import facts_of, save_revision
        from argus.domain.ingestion.reconcile.model import EventNotFound

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
                        acting_owner = str(context.actor.actor_id) == str(
                            context.owner_id
                        )
                        if acting_owner != owner:
                            raise ActionError(
                                "permission_denied", "business_permission_denied"
                            )
                        try:
                            event = tx.imports.event(str(draft_id))
                        except EventNotFound:
                            raise ActionError(
                                "not_found", "business_record_not_found"
                            ) from None
                        if event.version != version:
                            raise ActionError("stale_version", "stale_version")
                        if event.state not in ("open", "accepted"):
                            raise ActionError("invalid_input", "business_draft_not_open")
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
                        before = facts_of(event)
                        after = change(before, source_id)
                        event = replace(
                            event,
                            version=event.version + 1,
                            updated_at=datetime.now(timezone.utc),
                        )
                        result = save_revision(
                            tx,
                            event,
                            before,
                            after,
                            (source_id,),
                            tx.authorization.provenance,
                            None,
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

    def approve_income(
        self,
        context: ActionContext,
        draft_id: UUID,
        request: ApproveIncome,
        key: str,
    ) -> ActionOutcome:
        from argus.domain.business.actions.approval import approve

        return approve(self, context, draft_id, request, key)

    def capture_attachment_preparation(
        self,
        context: ActionContext,
        connection_id: UUID,
        *,
        target: ExistingDraft | None,
    ) -> AttachmentPreparationBinding:
        actor = context.actor.model_copy(update={"actor_kind": "extractor"})
        original = self.resolve_actor(actor, grant_id=context.grant_id)
        with transaction(self.authority, original, "prepare") as tx:
            row = self._attachment_row(tx, connection_id)
            draft = DocumentDraft.model_validate(row["draft"])
            if not draft.consent or not draft.source_available:
                raise ActionError("invalid_input", "document_extraction_consent_required")
            if row["preparation_binding"] is not None:
                binding = AttachmentPreparationBinding.model_validate(
                    row["preparation_binding"]
                )
                if (
                    not plans.same_authority(tx, binding.actor)
                    or binding.target != target
                ):
                    raise ActionError(
                        "idempotency_conflict", "business_preparation_binding_conflict"
                    )
                return binding
            if target is not None:
                mutations.event_at(tx, target)
            binding = AttachmentPreparationBinding(
                binding_id=uuid4(),
                space_id=actor.space_id,
                owner_id=context.owner_id,
                connection_id=connection_id,
                source_sha256=draft.sha256,
                actor=tx.authorization.provenance,
                target=target,
                consent=True,
                captured_at=datetime.now(timezone.utc),
            )
            tx.rows(
                "update public.financial_document_extractions set preparation_binding=%s,"
                " draft=jsonb_set(draft,'{status}','\"queued\"'::jsonb) where connection_id=%s",
                (Jsonb(binding.model_dump(mode="json")), connection_id),
            )
            return binding

    def rebind_attachment_preparation(
        self, context: ActionContext, connection_id: UUID
    ) -> AttachmentPreparationBinding:
        """Owner action: a receipt bound to a grant that is no longer live is
        bound again to the owner's current grant, with one ledger row.

        A binding whose grant is still live is left alone (``binding_live``),
        so this never silently moves authority that still works."""

        if context.actor.actor_kind != "member":
            raise ActionError("permission_denied", "business_human_command_required")
        if str(context.actor.actor_id) != context.owner_id:
            raise ActionError("permission_denied", "business_owner_required")
        with transaction(self.authority, context, "prepare") as tx:
            row = self._attachment_row(tx, connection_id)
            if row["preparation_binding"] is None:
                raise ActionError("invalid_input", "business_preparation_binding_missing")
            binding = AttachmentPreparationBinding.model_validate(
                row["preparation_binding"]
            )
            try:
                authorize(
                    tx.connection,
                    TrustedActor(
                        actor_id=binding.actor.actor_id,
                        actor_kind="extractor",
                        space_id=binding.space_id,
                    ),
                    binding.actor.grant_id,
                )
            except ActionError:
                pass
            else:
                raise ActionError("invalid_input", "business_preparation_binding_live")
            rebound = binding.model_copy(
                update={
                    "binding_id": uuid4(),
                    "actor": tx.authorization.provenance.model_copy(
                        update={"actor_kind": "extractor"}
                    ),
                    "captured_at": datetime.now(timezone.utc),
                }
            )
            command = RebindAttachmentCommand(
                previous_binding_id=binding.binding_id,
                previous_grant_id=binding.actor.grant_id,
                binding=rebound,
            )
            key = f"rebind:{rebound.binding_id}"
            plans.start_receipt(tx, key, command)
            tx.rows(
                "update public.financial_document_extractions set preparation_binding=%s"
                " where connection_id=%s",
                (Jsonb(rebound.model_dump(mode="json")), connection_id),
            )
            plans.finish_receipt(tx, key, Applied(outcome="applied"))
            return rebound

    @staticmethod
    def _attachment_row(tx: ActionTransaction, connection_id: UUID) -> dict:
        rows = tx.rows(
            "select d.*,c.lease_holder,c.lease_until,clock_timestamp() as checked_at from public.financial_source_connections c"
            " join public.financial_document_extractions d on d.connection_id=c.id and d.user_id=c.user_id"
            " where c.id=%s and c.user_id=%s and c.owner_space_id=%s"
            " and c.source='statement' and c.status<>'disconnected' for update of c,d",
            (connection_id, tx.context.owner_id, tx.context.actor.space_id),
        )
        if not rows:
            raise ActionError("not_found", "business_record_not_found")
        return rows[0]

    def _attachment_context(
        self, user_id: str, connection_id: str, scope: OwnerScope
    ) -> tuple[AttachmentPreparationBinding, ActionContext]:
        with self.authority.pool.connection() as connection:
            row = connection.execute(
                "select d.preparation_binding from public.financial_document_extractions d"
                " join public.financial_source_connections c on c.id=d.connection_id"
                " where d.connection_id=%s and d.user_id=%s and c.user_id=d.user_id"
                " and c.owner_space_id=%s and c.status<>'disconnected'",
                (connection_id, user_id, space_id(scope)),
            ).fetchone()
        if not row or row[0] is None:
            raise ActionError("invalid_input", "business_preparation_binding_missing")
        binding = AttachmentPreparationBinding.model_validate(row[0])
        context = self.resolve_actor(
            TrustedActor(
                actor_id=binding.actor.actor_id,
                actor_kind="extractor",
                space_id=binding.space_id,
            ),
            grant_id=binding.actor.grant_id,
        )
        if (
            str(binding.owner_id) != user_id
            or str(binding.connection_id) != connection_id
        ):
            raise ActionError("not_found", "business_record_not_found")
        return binding, context

    def _checked_attachment(
        self,
        tx: ActionTransaction,
        binding: AttachmentPreparationBinding,
        holder: str,
        attempt_id: str | None,
    ) -> tuple[dict, DocumentDraft]:
        row = self._attachment_row(tx, binding.connection_id)
        draft = DocumentDraft.model_validate(row["draft"])
        if row["preparation_binding"] != binding.model_dump(
            mode="json"
        ) or not plans.same_authority(tx, binding.actor):
            raise ActionError(
                "permission_denied", "business_preparation_authority_changed"
            )
        if (
            (row["source_path"] is None and row["source_bytes"] is None)
            or not draft.consent
            or not draft.source_available
            or draft.sha256 != binding.source_sha256
            or row["source_sha256"] not in (None, binding.source_sha256)
            or (
                row["source_bytes"] is not None
                and hashlib.sha256(bytes(row["source_bytes"])).hexdigest()
                != binding.source_sha256
            )
        ):
            raise ActionError("invalid_input", "business_preparation_source_changed")
        if (
            row["lease_holder"] != holder
            or row["lease_until"] is None
            or row["lease_until"] <= row["checked_at"]
        ):
            raise ActionError("permission_denied", "document_lease_lost")
        job = row["preparation_job"]
        if (job is not None and job.get("attempt_id") != attempt_id) or (
            job is None and attempt_id is not None
        ):
            raise ActionError("invalid_input", "document_attempt_superseded")
        return row, draft

    def check_attachment_preparation(
        self,
        *,
        user_id: str,
        connection_id: str,
        scope: OwnerScope,
        holder: str,
        attempt_id: str | None,
    ) -> None:
        binding, context = self._attachment_context(user_id, connection_id, scope)
        with transaction(self.authority, context, "prepare") as tx:
            self._checked_attachment(tx, binding, holder, attempt_id)

    def prepare_attachment(
        self,
        *,
        user_id: str,
        connection_id: str,
        scope: OwnerScope,
        holder: str,
        attempt_id: str | None,
        expected_batch_sha256: str,
    ) -> ActionOutcome:
        binding, context = self._attachment_context(user_id, connection_id, scope)
        with transaction(self.authority, context, "prepare") as tx:
            row, draft = self._checked_attachment(tx, binding, holder, attempt_id)
            if row["batch"] is None:
                raise ActionError("invalid_input", "draft_not_prepared")
            batch = ExtractionBatch.model_validate(row["batch"])
            if batch.metadata.get("sha256") != binding.source_sha256 or any(
                candidate.source.connection_id != str(binding.connection_id)
                or candidate.source.source != "statement"
                or not candidate.attachments
                or any(
                    attachment.sha256 != binding.source_sha256
                    for attachment in candidate.attachments
                )
                for candidate in batch.candidates
            ):
                raise ActionError("invalid_input", "business_preparation_source_changed")
            saved_digest = canonical_input_hash(batch)
            if expected_batch_sha256 != saved_digest:
                raise ActionError(
                    "idempotency_conflict", "business_preparation_batch_changed"
                )
            command = PrepareAttachmentCommand(binding=binding, batch_sha256=saved_digest)
            key = str(binding.binding_id)
            saved = plans.receipt(tx, key, command)
            if saved is not None:
                result = plans.replay(saved)
                if result.outcome not in {"applied", "replayed"}:
                    raise ActionError("invalid_input", "business_preparation_unsettled")
                return result
            if binding.target is not None:
                mutations.event_at(tx, binding.target)
            plans.start_receipt(tx, key, command)
            result = mutations.prepare_attachment(
                tx, binding.target, batch, draft, binding.actor
            )
            # The read is saved; a repeat of another receipt is marked on this
            # draft's event before the command settles.
            flag_receipt_duplicates(tx.imports, str(result.draft_id))
            live = authorize(tx.connection, context.actor, binding.actor.grant_id)
            live.require("prepare")
            final_tx = ActionTransaction(tx.connection, live, tx.imports)
            final_row, _ = self._checked_attachment(final_tx, binding, holder, attempt_id)
            if (
                final_row["batch"] is None
                or canonical_input_hash(
                    ExtractionBatch.model_validate(final_row["batch"])
                )
                != command.batch_sha256
            ):
                raise ActionError(
                    "idempotency_conflict", "business_preparation_batch_changed"
                )
            return plans.finish_receipt(tx, key, result)
