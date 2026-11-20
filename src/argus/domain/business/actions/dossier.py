from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, get_args
from uuid import UUID

from loguru import logger
from psycopg.rows import dict_row
from pydantic import TypeAdapter

from argus.domain.business.actions.duplicate_comparison import (
    compare,
    duplicate_revisions,
)
from argus.domain.business.actions.facts import facts_of
from argus.domain.business.actions.fiscal import last_choice, repeated_comprobantes
from argus.domain.business.actions.marks import draft_marks, fiscal_inclusion_available
from argus.domain.business.actions.refunds import refund_candidates
from argus.domain.business.actions.reopen import linked_reason
from argus.domain.business.amount_inheritance import (
    APPROVED,
    LinkedSources,
    inheritance_state,
    links_of,
    original_ncf,
    written_from,
)
from argus.domain.business.annotations import annotation_available, current_note
from argus.domain.business.approved_facts import approved_revision_sql
from argus.domain.business.authority import ActionError
from argus.domain.business.bandeja_group import upload_year, year_to_check
from argus.domain.business.config import (
    business_settlement_enabled,
    ecf_checks_panel_enabled,
)
from argus.domain.business.contracts.actions import APPROVAL_ACTION, DuplicateDecision
from argus.domain.business.contracts.authority import PersonName
from argus.domain.business.contracts.deletion import deletion
from argus.domain.business.contracts.dgii import (
    DeclarationSuggestions,
    DgiiDeclaration,
    PurchaseDeclaration,
    SuggestedField,
    SuggestionSource,
)
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
from argus.domain.business.document_type import DocumentType, kind_disagrees
from argus.domain.business.duplicates import pending_duplicates
from argus.domain.business.fact_blockers import blockers
from argus.domain.business.people import actor_ids, actor_view, named_deletion, people
from argus.domain.business.purchase_review import (
    blank_answer,
    declaration_from_facts,
    net_amount,
    takes_payment_split,
    takes_purchase_declaration,
)
from argus.domain.business.review_flags import review_flags
from argus.domain.business.rnc_registry import (
    RncRegistry,
    postgres_rnc_fetch,
    registry_from_config,
)
from argus.domain.business.transactions import ActionTransaction
from argus.domain.ingestion.receipt_review import DUPLICATE_WARNINGS
from argus.domain.ingestion.reconcile.model import EventNotFound, ImportEvent

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


def rnc_registry(tx: ActionTransaction) -> RncRegistry:
    return registry_from_config(
        "dgii",
        postgres_rnc_fetch(
            lambda query, params: next(iter(tx.rows(query, params)), None)
        ),
    )


def review_questions(
    tx: ActionTransaction, draft_ids: Sequence[UUID]
) -> dict[str, tuple[ReviewQuestion, ...]]:
    """The questions of each draft by id, oldest first. A draft with none has
    no entry."""

    rows = tx.rows(
        "select id,draft_id,field,asked_of,channel,state,prompt,allowed_answers,"
        " answer_source_id,created_at from public.business_questions"
        " where space_id=%s and draft_id=any(%s) order by created_at,id",
        (tx.context.actor.space_id, list(draft_ids)),
    )
    found: dict[str, list[ReviewQuestion]] = {}
    for row in rows:
        question = ReviewQuestion.model_validate(row)
        found.setdefault(str(question.draft_id), []).append(question)
    return {draft_id: tuple(questions) for draft_id, questions in found.items()}


def _fiscal_records(tx: ActionTransaction, activities: list[dict[str, Any]]):  # noqa: ANN202
    """The approved records as the 606 validation reads its originals."""

    from argus.domain.business.dgii_snapshot import fiscal_snapshot

    with tx.connection.cursor(row_factory=dict_row) as cursor:
        records, _rnc, _name = fiscal_snapshot(cursor, tx.context, activities)
    return records


def approval_of(
    receipt: Mapping[str, Any] | None,
    activity_id: UUID | None,
    approved_revision: Callable[[int], int],
    found: Mapping[str, PersonName | None],
) -> ApprovalResult | None:
    """What the latest approval receipt says: recorded once the draft holds its
    activity, else the unsettled outcome it left, else nothing to show.
    ``approved_revision`` reads the revision approved at a reviewed version;
    ``found`` names the receipt's people."""

    if receipt is None:
        return None
    version = receipt["command"]["request"]["version"]
    outcome = receipt["outcome"] or {}
    if activity_id:
        return RecordedApproval(
            activity_id=activity_id,
            reviewed_version=version,
            approved_revision=approved_revision(version),
            approved_at=receipt["created_at"],
            actor=actor_view(receipt["actor"], found),
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


def approval_receipts(tx: ActionTransaction, event: ImportEvent) -> list[dict[str, Any]]:
    """The draft's latest approval receipt: the one it points at, else the
    newest one that names it."""

    pointer = event.resolution.get("approval_receipt")
    approval_filter = "" if pointer is None else " and actor_id=%s and idempotency_key=%s"
    approval_params = () if pointer is None else (pointer["actor_id"], pointer["key"])
    return tx.rows(
        "select actor,command,outcome,created_at from public.business_action_receipts"
        " where space_id=%s and command->>'action' in ('approve_expense','approve_income','approve_refund')"
        " and command->>'draft_id'=%s"
        + approval_filter
        + " order by created_at desc limit 1",
        (tx.context.actor.space_id, event.id, *approval_params),
    )


def duplicate_candidates(
    tx: ActionTransaction,
    event: ImportEvent,
    pending: tuple[str, ...],
    *,
    can_prepare: bool,
    can_delete: bool,
) -> tuple[DuplicateCandidate, ...]:
    """The documents this open draft may repeat, each with why and what the
    reader may decide. ``pending`` are the read-facts warnings still open; a
    read-facts pair settled as different purchases is none until its evidence
    changes. A shared RNC and fiscal number is one comprobante: it is the
    stronger reason when both hold, no answer settles it, and keeping one is
    the only decision."""

    if event.state != "open":
        return ()
    warned = event.attention in (None, "possible_duplicate") and bool(
        (event.attention_detail or {}).get("basis") == "read_facts"
        or event.resolution.get("different_purchases")
    )
    read = pending if warned else ()
    draft_id = UUID(event.id)
    fiscal = tuple(str(i) for i in repeated_comprobantes(tx, [event]).get(draft_id, ()))
    candidates = []
    for other_id in dict.fromkeys((*read, *fiscal)):
        try:
            other = tx.imports.event(other_id)
        except EventNotFound:
            continue
        if other.state not in ("open", "accepted") or "business" not in other.resolution:
            continue
        decisions: tuple[DuplicateDecision, ...] = ()
        if other_id in read and other_id not in fiscal and can_prepare:
            decisions += ("different_purchase",)
        if can_delete:
            decisions += ("same_purchase",)
        candidates.append(
            DuplicateCandidate(
                draft_id=other.id,
                version=other.version,
                basis="fiscal_number" if other_id in fiscal else "read_facts",
                decisions=decisions,
                comparison=compare(
                    tx,
                    event,
                    other,
                    approval_receipts(tx, other) if other.state == "accepted" else [],
                ),
            )
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
    if event.state == "open" and kind_disagrees(
        (event.resolution.get("business") or {}).get("document_type", "recibo"), facts
    ):
        blocked.append(Blocker(code="activity_kind_unsupported", field="kind"))
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


def _approved_facts(tx: ActionTransaction) -> Callable[[str], BusinessFacts | None]:
    def read(activity_id: str) -> BusinessFacts | None:
        rows = tx.rows(
            "select resolution->'business'->'facts' as facts"
            " from public.financial_import_events where user_id=%s and owner_space_id=%s"
            " and activity_id=%s and state='accepted'",
            (tx.context.owner_id, tx.context.actor.space_id, activity_id),
        )
        return BusinessFacts.model_validate(rows[0]["facts"]) if rows else None

    return read


def _paying_account_type(
    tx: ActionTransaction, facts: BusinessFacts, accounts: Sequence[AccountChoice] | None
) -> str | None:
    """The type of the Business account a person stated paid the record."""

    funding = facts.funding.value if isinstance(facts.funding, Known) else None
    if not isinstance(funding, BusinessAccountFunding):
        return None
    listed = record_context(tx).accounts if accounts is None else accounts
    return next((account.type for account in listed if account.id == funding.account_id), None)


def linked_original(
    tx: ActionTransaction,
    state: str,
    facts: BusinessFacts,
    declaration: DgiiDeclaration | None,
) -> LinkedSources:
    """What a stored declaration follows: the credit note's original, and
    never a suggestion or the account's Forma de pago, which a person's write
    or an approval saves. Once the draft is not open, the amounts alone."""

    if links_of(state) is APPROVED:
        return APPROVED
    return LinkedSources(original_ncf=original_ncf(facts, declaration, _approved_facts(tx)))


def review_sources(
    tx: ActionTransaction,
    draft_id: UUID | str,
    state: str,
    facts: BusinessFacts,
    stored: DgiiDeclaration | None,
    document_type: DocumentType,
    accounts: Sequence[AccountChoice] | None = None,
    shown: DeclarationSuggestions | None = None,
) -> LinkedSources:
    """What ``written_from`` reads beyond the draft to show its declaration:
    the one reader behind the dossier, a write to the declaration and the
    approval. An open expense the 606 takes starts from the declaration its
    facts state, and an answer the server suggests stays a suggestion until
    the approval. A draft that is not open keeps what was saved.

    ``shown`` is the suggestions a person approving saw, in place of the
    server's own read now. One is refused when its answer is no longer blank
    or the approval saves no 606 declaration: the record changed."""

    if links_of(state) is APPROVED:
        return APPROVED
    purchase = stored if isinstance(stored, PurchaseDeclaration) else None
    reviewing = (
        state == "open"
        and isinstance(facts.kind, Known)
        and facts.kind.value == "expense"
        and takes_purchase_declaration(document_type, facts)
    )
    built = declaration_from_facts(facts, _paying_account_type(tx, facts, accounts)) if reviewing else None
    # A suggestion shows only where the approval saves it: on a declaration
    # the person saved, or on the one built from the facts.
    offers = reviewing and (purchase is not None or built is not None)
    if shown is None:
        shown = offered_suggestions(tx, draft_id, stored) if offers else DeclarationSuggestions()
    elif any(
        getattr(shown, field) is not None and not (offers and blank_answer(purchase, field))
        for field in get_args(SuggestedField)
    ):
        raise ActionError("invalid_input", "suggestion_stale")
    return LinkedSources(shown, original_ncf(facts, stored, _approved_facts(tx)), built=built)


def shown_bill_mark(resolution: BusinessResolution) -> str | None:
    """The due-notice mark a person sees. Factura por pagar and Factura pagada
    are settlement state, so none shows while settlement is off; the draft
    keeps the mark the read gave it."""

    return resolution.bill_mark if business_settlement_enabled() else None


#: Where each suggested answer comes from, best first. A read is ``receipt``
#: when the receipt prints the answer and ``reading`` when the reader works it out.
_SUGGESTION_SOURCES: dict[SuggestedField, tuple[SuggestionSource, ...]] = {
    "payment_method": ("receipt", "last_choice"),
    "category": ("last_choice", "reading"),
}
#: The read's own name for each answer.
_READ_FIELD: dict[SuggestedField, str] = {
    "payment_method": "payment_form",
    "category": "expense_type",
}


def best_suggestion(
    field: SuggestedField, read: str | None, remembered: Callable[[], str | None]
) -> dict[str, str] | None:
    """The answer to suggest with its source. ``read`` is what the reader read
    on this draft's receipt; ``remembered`` reads the last choice for its RNC."""

    for source in _SUGGESTION_SOURCES[field]:
        value = remembered() if source == "last_choice" else read
        if value:
            return {"value": value, "source": source}
    return None


def _read_answers(tx: ActionTransaction, draft_id: UUID) -> Mapping[str, str | None]:
    """What the reader read for each answer on the draft's newest receipt."""

    rows = tx.rows(
        "select "
        + ",".join(
            f"d.batch->'receipt'->>'{name}' as {field}"
            for field, name in _READ_FIELD.items()
        )
        + " from public.business_draft_sources l join public.business_sources s"
        " on s.id=l.source_id and s.space_id=l.space_id"
        " join public.financial_document_extractions d on d.connection_id=s.connection_id"
        " join public.financial_source_connections c on c.id=s.connection_id"
        " and c.owner_space_id=s.space_id"
        " where l.space_id=%s and l.draft_id=%s and s.kind='attachment' and c.user_id=%s"
        " and jsonb_typeof(d.batch->'receipt')='object'"
        " order by s.received_at desc,s.id desc limit 1",
        (tx.context.actor.space_id, draft_id, tx.context.owner_id),
    )
    return rows[0] if rows else {}


def offered_suggestions(
    tx: ActionTransaction, draft_id: UUID, declaration: DgiiDeclaration | None
) -> DeclarationSuggestions:
    """The suggestion for each answer the draft has not got, from what the
    reader read and the last choice for this RNC: what the dossier shows and
    what a bulk approval saves."""

    purchase = declaration if isinstance(declaration, PurchaseDeclaration) else None
    blank: tuple[SuggestedField, ...] = tuple(
        field for field in get_args(SuggestedField) if blank_answer(purchase, field)
    )
    read = _read_answers(tx, draft_id) if blank else {}
    return DeclarationSuggestions.model_validate(
        {
            field: best_suggestion(
                field, read.get(field), lambda field=field: last_choice(tx, draft_id, field)
            )
            for field in blank
        }
    )


def log_changed_suggestions(
    tx: ActionTransaction,
    draft_id: UUID | str,
    stored: DgiiDeclaration | None,
    declared: DgiiDeclaration | None,
) -> None:
    """The accuracy signal: a write over ``stored`` gives an answer other
    than the one the server suggested, whether or not an approval saved it."""

    if not isinstance(declared, PurchaseDeclaration):
        return
    before = stored if isinstance(stored, PurchaseDeclaration) else None
    answered = {
        field: answer
        for field in get_args(SuggestedField)
        if (answer := getattr(declared, field)) is not None
        and answer != getattr(before, field, None)
    }
    if not answered:
        return
    offered = offered_suggestions(tx, draft_id, before)
    for field, answer in answered.items():
        shown = getattr(offered, field)
        if shown is not None:
            source = shown.source if shown.value != answer else None
        else:
            source = before.suggestion_sources.get(field) if before else None
        if source is not None:
            logger.info("business_suggestion_changed field={} source={}", field, source)


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
    questions = review_questions(tx, [draft_id]).get(str(draft_id), ())
    history = tx.rows(
        "select draft_id,version,actor,before_facts as before,after_facts as after,"
        " source_ids,turn_key,created_at,before_dgii,after_dgii,before_due_on,after_due_on,before_current_note,after_current_note,reason"
        " from public.business_draft_revisions"
        " where space_id=%s and draft_id=%s order by version",
        (tx.context.actor.space_id, draft_id),
    )
    source_rows = tx.rows(
        "select s.id,s.kind,s.channel,s.received_at,s.text_content,s.connection_id,d.draft,"
        " exists (select 1 from public.business_draft_sources l2"
        " join public.business_sources s2 on s2.id=l2.source_id and s2.space_id=l2.space_id"
        " where l2.space_id=l.space_id and s2.connection_id=s.connection_id and l2.draft_id<>l.draft_id"
        " union select 1 from public.financial_import_observations o"
        " where o.connection_id=s.connection_id and o.event_id<>l.draft_id) as shared"
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
    approvals = approval_receipts(tx, event)
    decided = duplicate_revisions(tx, evidence)
    found = people(
        tx.connection,
        tx.authorization,
        actor_ids([row["actor"] for row in (*history, *approvals)]),
    )
    revisions = tuple(
        DraftRevision.model_validate(
            {
                **row,
                "actor": actor_view(row["actor"], found),
                "duplicate": next(
                    (decided[i] for i in row["source_ids"] if i in decided), None
                ),
            }
        )
        for row in history
    )

    def approved_revision(reviewed: int) -> int:
        [row] = tx.rows(
            approved_revision_sql("%s", "%s", "%s"),
            (draft_id, tx.context.actor.space_id, reviewed),
        )
        return row["version"]

    approval = approval_of(
        approvals[0] if approvals else None,
        event.activity_id if event.accept_key else None,
        approved_revision,
        found,
    )
    resolution = BusinessResolution.model_validate(event.resolution["business"])
    linked = review_sources(
        tx, draft_id, event.state, facts, resolution.dgii, resolution.document_type, context.accounts
    )
    declaration = written_from(
        facts, resolution.dgii, resolution.fiscal_overrides, resolution.bill_mark, linked
    )
    approvable = not blocked and "approve" in tx.authorization.capabilities
    can_prepare = "prepare" in tx.authorization.capabilities
    can_annotate = annotation_available(tx.authorization, event)
    fiscal_writable = can_prepare and event.state in ("open", "accepted")
    declaration_editable = fiscal_writable and takes_purchase_declaration(
        resolution.document_type, facts
    )
    reopen_available = (
        event.state == "accepted"
        and "approve" in tx.authorization.capabilities
        and linked_reason(tx, event.activity_id) is None
    )
    from argus.domain.business.actions.document_deletion import is_reading

    marker = deletion(event.state, event.resolution)
    deleted = named_deletion(
        marker,
        people(tx.connection, tx.authorization, [marker and marker.actor.actor_id]),
    )
    delete_available = (
        event.state == "open"
        and "approve" in tx.authorization.capabilities
        and not any(row["shared"] for row in source_rows)
        and not is_reading(tx, source_rows)
    )
    uploaded = upload_year(source_rows[0]["received_at"] if source_rows else None)
    return BusinessDossier(
        deleted=deleted,
        delete_available=delete_available,
        restore_available=deleted is not None
        and "approve" in tx.authorization.capabilities,
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
        net_amount=net_amount(facts, declaration),
        inheritance=inheritance_state(facts, declaration, resolution.fiscal_overrides, linked),
        sources=tuple(evidence),
        questions=questions,
        history=revisions,
        blockers=tuple(blocked),
        review_flags=review_flags(facts, rnc_registry(tx), declaration=resolution.dgii),
        approval_available=approvable,
        duplicate_candidates=duplicate_candidates(
            tx,
            event,
            duplicate_ids,
            can_prepare=can_prepare,
            can_delete=delete_available,
        ),
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
        ecf_checks_panel_available=ecf_checks_panel_enabled(),
        bill_mark=shown_bill_mark(resolution),
        dgii=declaration.model_dump(mode="json") if declaration else None,
        document_type=resolution.document_type,
        document_type_detected=resolution.document_type_detected,
        document_type_editable=event.state == "open" and can_prepare,
        declaration_editable=declaration_editable,
        declaration_suggestions=linked.suggestions
        if declaration_editable
        else DeclarationSuggestions(),
        payment_split_editable=fiscal_writable
        and takes_payment_split(resolution.document_type),
        reopen_available=reopen_available,
        due_on=resolution.due_on,
        upload_year=uploaded,
        year_to_check=year_to_check(facts, uploaded),
        **draft_marks(tx, draft_id, facts),
    )
