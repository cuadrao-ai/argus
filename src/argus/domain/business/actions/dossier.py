from __future__ import annotations

from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Any
from uuid import UUID

from psycopg.rows import dict_row
from pydantic import TypeAdapter

from argus.domain.business.actions.facts import facts_of
from argus.domain.business.actions.marks import draft_marks, fiscal_inclusion_available
from argus.domain.business.actions.refunds import refund_candidates
from argus.domain.business.annotations import annotation_available, current_note
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.actions import APPROVAL_ACTION
from argus.domain.business.contracts.dossier import (
    AccountChoice,
    ApprovalResult,
    Blocker,
    BusinessDossier,
    DraftRevision,
    DuplicateCandidate,
    RecordContext,
    RecordedApproval,
    ReviewQuestion,
    SourceEvidence,
    UnsettledApproval,
)
from argus.domain.business.contracts.facts import (
    BusinessAccountFunding,
    BusinessFacts,
    BusinessResolution,
    Known,
)
from argus.domain.business.duplicates import pending_duplicates
from argus.domain.business.transactions import ActionTransaction
from argus.domain.ingestion.receipt_review import DUPLICATE_WARNINGS
from argus.domain.ingestion.reconcile.model import EventNotFound, ImportEvent
from argus.domain.recording.money_schemas import ELIGIBILITY

SOURCE = TypeAdapter(SourceEvidence)


def record_context(tx: ActionTransaction) -> RecordContext:
    rows = tx.rows(
        "select id,nickname,type,currency from public.financial_accounts"
        " where owner_space_id=%s and user_id=%s and not archived order by created_at,id",
        (tx.context.actor.space_id, tx.context.owner_id),
    )
    return RecordContext(
        space_id=tx.context.actor.space_id,
        space_name=tx.context.space_name,
        accounts=tuple(AccountChoice.model_validate(row) for row in rows),
        capabilities=tx.authorization.capabilities,
    )


def blockers(facts: BusinessFacts, accounts: tuple[AccountChoice, ...]) -> list[Blocker]:
    result = [
        Blocker(code="fact_required", field=name)
        for name in (
            "kind",
            "amount",
            "currency",
            "occurred_on",
            "funding",
            "business_share",
        )
        if not isinstance(getattr(facts, name), Known)
    ]
    if isinstance(facts.kind, Known) and facts.kind.value not in {
        "expense",
        "income",
        "refund",
    }:
        result.append(Blocker(code="activity_kind_unsupported", field="kind"))
    if (
        isinstance(facts.kind, Known)
        and facts.kind.value in {"income", "refund"}
        and isinstance(facts.funding, Known)
        and not isinstance(facts.funding.value, BusinessAccountFunding)
    ):
        result.append(Blocker(code="business_funding_unsupported", field="funding"))
    if (
        isinstance(facts.kind, Known)
        and facts.kind.value in {"income", "refund"}
        and isinstance(facts.funding, Known)
        and isinstance(facts.funding.value, BusinessAccountFunding)
    ):
        account = next(
            (item for item in accounts if item.id == facts.funding.value.account_id),
            None,
        )
        if account is None:
            result.append(Blocker(code="business_record_not_found", field="funding"))
        elif (
            isinstance(facts.currency, Known) and account.currency != facts.currency.value
        ):
            result.append(Blocker(code="import_currency_mismatch", field="funding"))
        elif account.type not in ELIGIBILITY[facts.kind.value]:
            result.append(Blocker(code="account_ineligible", field="funding"))
    if (
        isinstance(facts.kind, Known)
        and facts.kind.value == "income"
        and isinstance(facts.category_id, Known)
        and facts.category_id.value is not None
    ):
        result.append(Blocker(code="business_category_unsupported", field="category_id"))
    if isinstance(facts.amount, Known) and Decimal(facts.amount.value) <= 0:
        result.append(Blocker(code="amount_positive_required", field="amount"))
    if (
        isinstance(facts.business_share, Known)
        and facts.business_share.value.kind == "partial"
    ):
        # A personal receipt (none) is approved and left out of the totals;
        # a partial share has no recording rule yet.
        result.append(
            Blocker(code="business_allocation_unsupported", field="business_share")
        )
    return result


def _fiscal_records(tx: ActionTransaction, activities: list[dict[str, Any]]):  # noqa: ANN202
    """The approved records as the 606 validation reads its originals."""

    from argus.domain.business.dgii_snapshot import fiscal_snapshot

    with tx.connection.cursor(row_factory=dict_row) as cursor:
        records, _rnc, _name = fiscal_snapshot(cursor, tx.context, activities)
    return records


def approval_of(
    receipt: Mapping[str, Any] | None,
    activity_id: UUID | None,
    history: tuple[DraftRevision, ...],
) -> ApprovalResult | None:
    """What the latest approval receipt says: recorded once the draft holds its
    activity, else the unsettled outcome it left, else nothing to show."""

    if receipt is None:
        return None
    version = receipt["command"]["request"]["version"]
    outcome = receipt["outcome"] or {}
    if activity_id:
        return RecordedApproval(
            activity_id=activity_id,
            reviewed_version=version,
            approved_revision=max(
                (item.version for item in history if item.version <= version),
                default=version,
            ),
            approved_at=receipt["created_at"],
            actor=receipt["actor"],
        )
    if outcome.get("outcome") == "outcome_unknown":
        return UnsettledApproval(
            status="outcome_unknown", reviewed_version=version, code=outcome["code"]
        )
    if outcome.get("outcome") not in {None, "applied", "replayed"}:
        return UnsettledApproval(
            status="failed",
            reviewed_version=version,
            code=outcome.get("code", "approval_failed"),
        )
    return None


def duplicate_candidates(
    tx: ActionTransaction, event: ImportEvent, ids: tuple[str, ...]
) -> tuple[DuplicateCandidate, ...]:
    if event.attention not in (None, "possible_duplicate") or not (
        (event.attention_detail or {}).get("basis") == "read_facts"
        or event.resolution.get("different_purchases")
    ):
        return ()
    candidates = []
    for other_id in ids:
        try:
            other = tx.imports.event(other_id)
        except EventNotFound:
            continue
        if other.state in ("open", "accepted") and "business" in other.resolution:
            candidates.append(
                DuplicateCandidate(draft_id=other.id, version=other.version)
            )
    return tuple(candidates)


def workflow_blockers(
    tx: ActionTransaction,
    event: ImportEvent,
    facts: BusinessFacts,
    accounts: tuple[AccountChoice, ...],
    questions: tuple[ReviewQuestion, ...],
) -> tuple[list[Blocker], tuple[str, ...]]:
    """Shared fact, question and duplicate readiness, independent of reader role."""
    blocked = blockers(facts, accounts)
    if any(
        q.state in {"open", "owner_does_not_know", "waiting_for_window"}
        for q in questions
    ):
        blocked.append(Blocker(code="business_questions_unresolved"))
    if event.state != "open":
        blocked.append(Blocker(code="business_draft_not_open"))
    from argus.domain.business.actions.duplicate_resolution import attachment_signature

    duplicate_ids = pending_duplicates(
        tx.imports, event, lambda event_id: attachment_signature(tx, event_id)
    )
    unresolved_attention = event.attention in DUPLICATE_WARNINGS and (
        event.attention != "possible_duplicate"
        or not event.possible_duplicates
        or bool(duplicate_ids)
    )
    if unresolved_attention or duplicate_ids:
        # Settled only by a person: the draft stays reviewable, never approvable.
        blocked.append(Blocker(code="possible_duplicate"))
    return blocked, tuple(duplicate_ids)


def dossier(
    tx: ActionTransaction,
    draft_id: UUID,
    ledger: Callable[[], list[dict[str, Any]]] | None = None,
) -> BusinessDossier:
    """The draft as a person reviews it. ``ledger`` reads the Business's money
    activities when the draft may refund a purchase; without it the dossier
    names no refund candidates."""

    try:
        event = tx.imports.event(str(draft_id))
    except EventNotFound:
        raise ActionError("not_found", "business_record_not_found") from None
    facts = facts_of(event)
    question_rows = tx.rows(
        "select id,draft_id,field,asked_of,channel,state,prompt,allowed_answers,"
        " answer_source_id,created_at from public.business_questions"
        " where space_id=%s and draft_id=%s order by created_at,id",
        (tx.context.actor.space_id, draft_id),
    )
    questions = tuple(ReviewQuestion.model_validate(row) for row in question_rows)
    history = tx.rows(
        "select draft_id,version,actor,before_facts as before,after_facts as after,"
        " source_ids,turn_key,created_at,before_dgii,after_dgii,before_due_on,after_due_on,before_current_note,after_current_note"
        " from public.business_draft_revisions"
        " where space_id=%s and draft_id=%s order by version",
        (tx.context.actor.space_id, draft_id),
    )
    source_rows = tx.rows(
        "select s.id,s.kind,s.channel,s.received_at,s.text_content,s.connection_id,d.draft"
        " from public.business_draft_sources l join public.business_sources s"
        " on s.id=l.source_id and s.space_id=l.space_id"
        " left join public.financial_document_extractions d on d.connection_id=s.connection_id"
        " where l.space_id=%s and l.draft_id=%s order by s.received_at,s.id",
        (tx.context.actor.space_id, draft_id),
    )
    evidence = []
    for row in source_rows:
        value = {name: row[name] for name in ("id", "kind", "channel", "received_at")}
        if row["kind"] == "attachment":
            metadata = row["draft"]
            if metadata is None:
                raise ActionError("invalid_input", "document_source_unavailable")
            value.update(
                connection_id=row["connection_id"],
                filename=metadata.get("filename"),
                media_type=metadata["media_type"],
            )
        else:
            value["text"] = row["text_content"]
        evidence.append(SOURCE.validate_python(value))
    context = record_context(tx)
    blocked, duplicate_ids = workflow_blockers(
        tx, event, facts, context.accounts, questions
    )
    pointer = event.resolution.get("approval_receipt")
    approval_filter = "" if pointer is None else " and actor_id=%s and idempotency_key=%s"
    approval_params = () if pointer is None else (pointer["actor_id"], pointer["key"])
    approvals = tx.rows(
        "select actor,command,outcome,created_at from public.business_action_receipts"
        " where space_id=%s and command->>'action' in ('approve_expense','approve_income','approve_refund')"
        " and command->>'draft_id'=%s"
        + approval_filter
        + " order by created_at desc limit 1",
        (tx.context.actor.space_id, str(draft_id), *approval_params),
    )
    revisions = tuple(DraftRevision.model_validate(row) for row in history)
    approval = approval_of(
        approvals[0] if approvals else None,
        event.activity_id if event.accept_key else None,
        revisions,
    )
    resolution = BusinessResolution.model_validate(event.resolution["business"])
    approvable = not blocked and "approve" in tx.authorization.capabilities
    can_annotate = annotation_available(tx.authorization, event)
    return BusinessDossier(
        **context.model_dump(),
        current_note=current_note(event),
        note_edit_available=can_annotate,
        supporting_append_available=can_annotate,
        annotation_unavailable_reason=None
        if can_annotate
        else "business_annotation_unavailable",
        draft_id=draft_id,
        version=event.version,
        review_state=event.state,
        facts=facts,
        sources=tuple(evidence),
        questions=questions,
        history=revisions,
        blockers=tuple(blocked),
        approval_available=approvable,
        duplicate_candidates=duplicate_candidates(tx, event, duplicate_ids),
        approval_action=APPROVAL_ACTION[facts.kind.value] if approvable else None,
        approval_result=approval,
        fiscal_inclusion_available=fiscal_inclusion_available(tx, facts, event.state),
        refund_candidates=refund_candidates(
            facts, lambda: _fiscal_records(tx, ledger() if ledger else [])
        ),
        read_purchases=resolution.read_purchases,
        read_total=resolution.read_total,
        unrecorded_purchases=resolution.unrecorded_purchases(),
        ecf_checks=resolution.ecf_checks,
        dgii_qr=resolution.dgii_qr,
        bill_mark=resolution.bill_mark,
        dgii=resolution.dgii.model_dump(mode="json") if resolution.dgii else None,
        document_type=resolution.document_type,
        document_type_detected=resolution.document_type_detected,
        document_type_editable=event.state == "open"
        and "prepare" in tx.authorization.capabilities,
        due_on=resolution.due_on,
        **draft_marks(tx, draft_id, facts),
    )
