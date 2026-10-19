from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb
from pydantic import TypeAdapter, ValidationError

from argus.domain.business.actions import plans, sources
from argus.domain.business.actions.facts import facts_of, patched_facts, validate_facts
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.actions import (
    Applied,
    Ask,
    AttachSource,
    BusinessAction,
    ExistingDraft,
    ProposeActivity,
    ProposeAllocation,
)
from argus.domain.business.contracts.authority import ActorProvenance
from argus.domain.business.contracts.checks import DgiiQr, EcfVerification
from argus.domain.business.contracts.dgii import (
    DgiiDeclaration,
    FiscalReview,
    PurchaseDeclaration,
    SalesDeclaration,
)
from argus.domain.business.contracts.facts import (
    BusinessFactPatch,
    BusinessFacts,
    BusinessResolution,
    Known,
    ReadPurchase,
)
from argus.domain.business.transactions import ActionTransaction
from argus.domain.ingestion.documents.dgii_qr import fill_from_qr
from argus.domain.ingestion.documents.models import (
    DocumentDraft,
    ExtractionBatch,
    ReceiptDetails,
)
from argus.domain.ingestion.reconcile.model import EventNotFound, ImportEvent


def event_at(tx: ActionTransaction, ref: ExistingDraft) -> ImportEvent:
    try:
        event = tx.imports.event(str(ref.draft_id))
    except EventNotFound:
        raise ActionError("not_found", "business_record_not_found") from None
    if event.version != ref.version:
        raise ActionError("stale_version", "stale_version")
    if event.state == "accepted":
        raise ActionError("invalid_input", "recorded_correction_unsupported")
    if event.state != "open":
        raise ActionError("invalid_input", "business_draft_not_open")
    return event


def new_candidate(owner_id: str, now: datetime) -> ImportEvent:
    return ImportEvent(
        str(uuid4()),
        owner_id,
        "open",
        "transaction",
        None,
        None,
        None,
        (),
        {},
        None,
        None,
        now,
        now,
        1,
    )


def save_revision(
    tx: ActionTransaction,
    event: ImportEvent,
    before: BusinessFacts | None,
    after: BusinessFacts,
    source_ids: tuple[UUID, ...],
    actor: ActorProvenance,
    turn_key: str | None,
    read_purchases: tuple[ReadPurchase, ...] | None = None,
    read_total: str | None = None,
    ecf_checks: EcfVerification | None = None,
    dgii_qr: DgiiQr | None = None,
    dgii: DgiiDeclaration | None = None,
    *,
    reuse_version: bool = False,
) -> Applied:
    validate_facts(tx, after)
    resolution = dict(event.resolution)
    previous = resolution.get("business") or {}
    if read_purchases is None:
        # A later revision keeps the evidence the read left on the draft.
        read_purchases = tuple(
            ReadPurchase.model_validate(item)
            for item in previous.get("read_purchases") or ()
        )
        read_total = previous.get("read_total")
    if ecf_checks is None:
        # A later document (a photo beside the e-CF) or a person's revision
        # brings no verification; the one the e-CF gave stays on the draft.
        kept = previous.get("ecf_checks")
        ecf_checks = EcfVerification.model_validate(kept) if kept else None
    if dgii_qr is None:
        kept_qr = previous.get("dgii_qr")
        dgii_qr = DgiiQr.model_validate(kept_qr) if kept_qr else None
    resolution["business"] = BusinessResolution(
        facts=after,
        read_purchases=read_purchases,
        read_total=read_total,
        ecf_checks=ecf_checks,
        dgii_qr=dgii_qr,
        remainder_settled=bool(previous.get("remainder_settled", False)),
        dgii=dgii if dgii is not None else previous.get("dgii"),
    ).model_dump(mode="json")
    event = replace(event, resolution=resolution, anchor_on=after.occurred_on.value)
    tx.imports.put_event(event)
    sources.attach(tx, event.id, source_ids)
    if reuse_version:
        payload = resolution["business"].get("dgii")
        tx.rows(
            "update public.business_draft_revisions set after_dgii=coalesce(after_dgii, %s)"
            " where space_id=%s and draft_id=%s and version=%s",
            (
                Jsonb(payload) if payload else None,
                tx.context.actor.space_id,
                event.id,
                event.version,
            ),
        )
        return Applied(outcome="applied", draft_id=event.id, version=event.version)
    tx.rows(
        "insert into public.business_draft_revisions"
        " (space_id,draft_id,version,actor,before_facts,after_facts,source_ids,turn_key,before_dgii,after_dgii)"
        " values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            tx.context.actor.space_id,
            event.id,
            event.version,
            Jsonb(actor.model_dump(mode="json")),
            Jsonb(before.model_dump(mode="json")) if before is not None else None,
            Jsonb(after.model_dump(mode="json")),
            list(source_ids),
            turn_key,
            Jsonb(previous.get("dgii")) if previous.get("dgii") else None,
            Jsonb(resolution["business"].get("dgii"))
            if resolution["business"].get("dgii")
            else None,
        ),
    )
    return Applied(outcome="applied", draft_id=event.id, version=event.version)


def revise(
    tx: ActionTransaction,
    ref: ExistingDraft | None,
    patch: BusinessFactPatch | None,
    source_ids: tuple[UUID, ...],
    actor: ActorProvenance,
    *,
    turn_key: str | None = None,
    answer_id: UUID | None = None,
    fiscal_review: FiscalReview | None = None,
) -> Applied:
    sources.require_sources(tx, source_ids)
    now = datetime.now(timezone.utc)
    if ref is None:
        event = new_candidate(tx.context.owner_id, now)
        before = None
    else:
        event = event_at(tx, ref)
        before = facts_of(event)
        event = replace(event, version=event.version + 1, updated_at=now)
    origin = {
        "member": "member_set",
        "owner_via_agent": "owner_stated",
        "extractor": "extracted",
    }[actor.actor_kind]
    try:
        after = (
            patched_facts(before, patch, source_ids, origin=origin)
            if patch is not None
            else before
        )
        if fiscal_review is not None:
            from argus.domain.business.actions.fiscal import reviewed_fiscal_facts

            after = reviewed_fiscal_facts(after, fiscal_review, source_ids, origin)
    except ValidationError:
        raise ActionError("invalid_input", "business_fact_provenance_invalid") from None
    if answer_id is not None:
        answer_question(tx, event.id, answer_id, patch, source_ids[-1])
    elif actor.actor_kind == "member" and patch is not None:
        for question in tx.rows(
            "select id,field from public.business_questions where space_id=%s"
            " and draft_id=%s and state in ('open','owner_does_not_know','waiting_for_window')",
            (tx.context.actor.space_id, event.id),
        ):
            value = getattr(patch, question["field"])
            if value is not None and value.state in {"known", "owner_does_not_know"}:
                answer_question(tx, event.id, question["id"], patch, source_ids[-1])
    declared = fiscal_review.declaration if fiscal_review else None
    if patch is not None and patch.purchase is not None:
        current = declared
        if current is None:
            raw = (event.resolution.get("business") or {}).get("dgii")
            current = TypeAdapter(DgiiDeclaration).validate_python(raw) if raw else None
        if not isinstance(current, SalesDeclaration):
            from argus.domain.business.purchase_review import apply_purchase

            amount = after.amount.value if isinstance(after.amount, Known) else None
            declared = apply_purchase(
                current if isinstance(current, PurchaseDeclaration) else None,
                patch.purchase,
                amount,
            )
    return save_revision(
        tx,
        event,
        before,
        after,
        source_ids,
        actor,
        turn_key,
        dgii=declared,
    )


def answer_question(
    tx: ActionTransaction,
    draft_id: str,
    question_id: UUID,
    patch: BusinessFactPatch,
    source_id: UUID,
) -> None:
    questions = tx.rows(
        "select field,state,asked_of from public.business_questions"
        " where id=%s and draft_id=%s and space_id=%s for update",
        (question_id, draft_id, tx.context.actor.space_id),
    )
    if not questions:
        raise ActionError("not_found", "business_record_not_found")
    question = questions[0]
    if question["state"] not in {"open", "owner_does_not_know", "waiting_for_window"}:
        raise ActionError("invalid_input", "business_question_closed")
    if question["asked_of"] == "accountant" and tx.context.actor.actor_kind != "member":
        raise ActionError("permission_denied", "business_question_requires_member")
    answer = getattr(patch, question["field"])
    if answer is None or answer.state == "unknown":
        raise ActionError("invalid_input", "business_question_answer_missing")
    unknown = answer.state == "owner_does_not_know"
    tx.rows(
        "update public.business_questions set state=%s,asked_of=%s,channel=%s,"
        " answer_source_id=%s where id=%s",
        (
            "owner_does_not_know" if unknown else "answered",
            "accountant" if unknown else question["asked_of"],
            "web" if unknown or question["asked_of"] == "accountant" else "whatsapp",
            source_id,
            question_id,
        ),
    )


def apply(
    tx: ActionTransaction,
    action: BusinessAction,
    actor: ActorProvenance,
    key: str,
    index: int,
) -> Applied:
    draft = getattr(action, "draft", None)
    ref = plans.reference(tx, draft, key, index) if draft is not None else None
    if isinstance(action, (ProposeActivity, ProposeAllocation)):
        patch = (
            action.facts
            if isinstance(action, ProposeActivity)
            else BusinessFactPatch(
                funding=action.funding, business_share=action.business_share
            )
        )
        return revise(
            tx,
            ref,
            patch,
            action.source_ids,
            actor,
            turn_key=key,
            answer_id=action.answers_question_id,
        )
    if isinstance(action, AttachSource):
        event = event_at(tx, ref)
        facts = facts_of(event)
        event = replace(
            event, version=event.version + 1, updated_at=datetime.now(timezone.utc)
        )
        return save_revision(tx, event, facts, facts, (action.source_id,), actor, key)
    if isinstance(action, Ask):
        event = event_at(tx, ref)
        facts_of(event)
        existing = tx.rows(
            "select id,field,asked_of,state from public.business_questions"
            " where space_id=%s and draft_id=%s and field=%s"
            " and state in ('open','owner_does_not_know','waiting_for_window')",
            (tx.context.actor.space_id, event.id, action.field),
        )
        if existing:
            question_id = existing[0]["id"]
        else:
            if action.asked_of == "owner" and tx.rows(
                "select id from public.business_questions where space_id=%s"
                " and asked_of='owner' and state in ('open','waiting_for_window') limit 1",
                (tx.context.actor.space_id,),
            ):
                raise ActionError("invalid_input", "business_owner_question_pending")
            question_id = uuid4()
            tx.rows(
                "insert into public.business_questions"
                " (id,space_id,draft_id,field,asked_of,channel,state,prompt,allowed_answers)"
                " values (%s,%s,%s,%s,%s,%s,'open',%s,ARRAY['known','owner_does_not_know'])",
                (
                    question_id,
                    tx.context.actor.space_id,
                    event.id,
                    action.field,
                    action.asked_of,
                    "whatsapp" if action.asked_of == "owner" else "web",
                    action.prompt,
                ),
            )
        return Applied(
            outcome="applied",
            draft_id=event.id,
            version=event.version,
            question_id=question_id,
        )
    draft_id = getattr(action, "draft_id", None)
    if draft_id is None:
        return Applied(outcome="applied")
    try:
        event = tx.imports.event(str(draft_id))
    except EventNotFound:
        raise ActionError("not_found", "business_record_not_found") from None
    return Applied(outcome="applied", draft_id=event.id, version=event.version)


def prepare_attachment(
    tx: ActionTransaction,
    target: ExistingDraft | None,
    batch: ExtractionBatch,
    draft: DocumentDraft,
    actor: ActorProvenance,
) -> Applied:
    from argus.domain.business.contracts.dossier import AttachmentSource
    from argus.domain.ingestion.documents.extractor import (
        fiscal_facts_from_receipt,
        ncf_bill,
        priced_amounts,
        review_amount,
    )

    candidates = [
        candidate for candidate in batch.candidates if candidate.evidence == "transaction"
    ]
    refusal = _read_refusal(batch)
    if refusal is not None:
        raise ActionError("invalid_input", refusal)
    if any(
        candidate.source.connection_id != draft.connection_id for candidate in candidates
    ):
        raise ActionError("invalid_input", "business_preparation_source_changed")
    purchases = candidates or _observed_purchases(batch)
    if not purchases and ncf_bill(batch) and batch.receipt is not None:
        purchases = [_bill_purchase(batch.receipt)]
    priced = () if purchases else priced_amounts(batch)
    chosen = review_amount(batch) if priced else None
    if chosen is not None:
        purchases = [_review_purchase(item) for item in priced]
    if not purchases and _notice_only(batch):
        raise ActionError("invalid_input", "not_a_receipt")
    # One clean purchase becomes the draft's facts. Several purchases, or an
    # ambiguous read, still become one draft: it keeps only what every read
    # purchase shares, leaves the amount for a person, and carries each read
    # purchase as evidence, so there is always something to review.
    ambiguous = len(purchases) != 1 or any(
        issue.code == "receipt_purchase_ambiguous" for issue in batch.issues
    )
    read_purchases = (
        tuple(
            ReadPurchase(
                index=index,
                amount=candidate.amount,
                currency=candidate.currency,
                occurred_on=candidate.occurred_on,
                merchant=candidate.merchant,
                kind_hint=_kind(candidate.kind_hint),
            )
            for index, candidate in enumerate(purchases, 1)
        )
        if ambiguous
        else ()
    )
    read_total = (
        batch.receipt.total if ambiguous and batch.receipt is not None else None
    )
    candidate = _consensus(purchases) if ambiguous else purchases[0]
    source_id = sources.record_source(
        tx,
        f"attachment:{draft.connection_id}",
        AttachmentSource(
            id=uuid4(),
            channel="web",
            received_at=draft.created_at,
            connection_id=draft.connection_id,
            filename=draft.filename,
            media_type=draft.media_type,
        ),
    )
    now = datetime.now(timezone.utc)
    if target is None:
        event, before = new_candidate(tx.context.owner_id, now), None
    else:
        event = event_at(tx, target)
        before = facts_of(event)
        event = replace(event, version=event.version + 1, updated_at=now)
    values = {
        "amount": candidate.amount,
        "currency": candidate.currency,
        "occurred_on": candidate.occurred_on,
        "counterparty": candidate.merchant,
        "kind": _kind(candidate.kind_hint),
    }
    uncertain = set(candidate.uncertain)
    _fill_unknown_purchase(values, uncertain, batch.receipt)
    if "merchant" in uncertain:
        uncertain.add("counterparty")
    if "direction" in uncertain:
        uncertain.add("kind")
    facts = BusinessFacts().model_dump(mode="json")
    for name, value in values.items():
        known = value is not None and name not in uncertain
        facts[name] = {
            "state": "known" if known else "unknown",
            "value": value if known else None,
            "origin": "extracted",
            "verified": False,
            "source_ids": [str(source_id)],
        }
    if chosen is not None:
        facts = _mark_unverified_review(facts, _review_purchase(chosen))
    facts["fiscal"] = fiscal_facts_from_receipt(
        batch.receipt, source_id=source_id
    ).model_dump(mode="json")
    # The typed merge after decode and read: the QR fills only what the read
    # left unknown, each filled fact naming its origin; a mismatch fills nothing.
    facts = fill_from_qr(facts, batch.dgii_qr, source_id, fill_amount=len(purchases) <= 1)
    facts = BusinessFacts.model_validate(facts).model_dump(mode="json")
    if before is not None:
        merged = before.model_dump(mode="json")
        for name in values:
            merged[name] = _retain_or_fill(
                merged[name], facts[name], currency=name == "currency"
            )
        if merged["fiscal"] is None:
            merged["fiscal"] = facts["fiscal"]
        else:
            for name, incoming in facts["fiscal"].items():
                merged["fiscal"][name] = _retain_or_fill(merged["fiscal"][name], incoming)
        facts = merged
    after = BusinessFacts.model_validate(facts)
    return save_revision(
        tx,
        event,
        before,
        after,
        (source_id,),
        actor,
        None,
        read_purchases,
        read_total,
        batch.ecf_checks,
        batch.dgii_qr,
    )


KINDS = frozenset({"expense", "income", "transfer", "refund"})


def _read_refusal(batch: ExtractionBatch) -> str | None:
    """Why this read cannot become a draft, before its purchases are considered.

    An unreadable file is terminal. A readable fiscal bill is not. Any other
    readable read with a positive amount and a currency is not: it becomes a
    review draft and a person decides. A readable read with no such amount
    and no receipt is not a receipt. An incomplete receipt that still has no
    priced amount stays on the retryable review. A complete receipt still
    reaches purchase handling.
    """

    from argus.domain.ingestion.documents.extractor import ncf_bill, review_amount

    if batch.readable is not True:
        return "unreadable_document"
    if ncf_bill(batch) or review_amount(batch) is not None:
        return None
    if batch.receipt is None:
        return "not_a_receipt"
    if batch.complete is not True:
        return "receipt_requires_review"
    return None


def _notice_only(batch: ExtractionBatch) -> bool:
    """Rows that name a balance, a period, or an amount due, and no purchase."""

    if not batch.observations:
        return False
    return not any(row.evidence == "transaction" for row in batch.observations)


def _review_purchase(priced) -> SimpleNamespace:  # noqa: ANN001
    """One expense from a priced amount. The amount stays off the draft
    until the review mark places it unverified."""

    purchase = _bill_purchase(
        ReceiptDetails(
            merchant=priced.merchant,
            occurred_on=priced.occurred_on,
            currency=priced.currency,
            total=priced.amount,
        )
    )
    purchase.uncertain = frozenset(set(purchase.uncertain) | {"amount"})
    return purchase


def _mark_unverified_review(facts: dict, purchase: SimpleNamespace) -> dict:
    """Publish the priced amount as a known value a person still has to review."""

    amount = facts["amount"]
    facts["amount"] = {
        **amount,
        "state": "known",
        "value": purchase.amount,
        "verified": False,
    }
    return facts


def _bill_purchase(receipt: ReceiptDetails) -> SimpleNamespace:
    """One expense from the fiscal bill's own total. The notice row is not it."""

    uncertain: set[str] = set()
    if receipt.currency is None:
        uncertain.add("currency")
    if receipt.occurred_on is None:
        uncertain.add("occurred_on")
    if not receipt.merchant:
        uncertain.add("merchant")
    return SimpleNamespace(
        amount=receipt.total,
        currency=receipt.currency,
        occurred_on=receipt.occurred_on,
        merchant=receipt.merchant,
        kind_hint="expense",
        uncertain=frozenset(uncertain),
    )


def _observed_purchases(batch: ExtractionBatch) -> list[SimpleNamespace]:
    """The transaction rows a read showed. The projection delivers no
    candidate for a receipt it could not settle on one purchase, so the rows
    themselves are the evidence, read the way the projection reads a row."""

    from argus.domain.ingestion.documents.extractor import plain_amount

    rows = []
    seen: set[tuple[int, int]] = set()
    for row in batch.observations:
        identity = (row.page, row.row)
        # The projection's own skips: a repeated identity or an amount that is
        # not plain decimal text is never a purchase.
        if row.evidence != "transaction" or identity in seen:
            continue
        seen.add(identity)
        if row.amount is not None and not plain_amount(row.amount):
            continue
        uncertain = set(row.uncertain)
        for name in ("amount", "currency", "occurred_on"):
            if getattr(row, name) is None:
                uncertain.add(name)
        if row.direction == "unknown":
            uncertain.add("direction")
        rows.append(
            SimpleNamespace(
                amount=row.amount,
                currency=row.currency,
                occurred_on=row.occurred_on,
                merchant=row.merchant,
                kind_hint=row.kind_hint,
                uncertain=frozenset(uncertain),
            )
        )
    return rows


def _kind(hint: str | None) -> str | None:
    """A read kind the facts accept; anything else is left unknown."""

    return hint if hint in KINDS else None


def _consensus(purchases: list) -> SimpleNamespace:  # noqa: ANN001
    """What every read purchase agrees on; the amount is never shared."""

    def shared(values: set) -> object | None:
        return values.pop() if len(values) == 1 and None not in values else None

    uncertain: set[str] = set()
    for candidate in purchases:
        uncertain |= set(candidate.uncertain)
    return SimpleNamespace(
        amount=None,
        currency=shared({c.currency for c in purchases}),
        occurred_on=shared({c.occurred_on for c in purchases}),
        merchant=shared({c.merchant for c in purchases}),
        kind_hint=shared({_kind(c.kind_hint) for c in purchases}),
        uncertain=frozenset(uncertain),
    )


def _fill_unknown_purchase(
    values: dict, uncertain: set[str], receipt: ReceiptDetails | None
) -> None:
    """A candidate that left the supplier or the currency unknown takes the receipt's.

    A later merge still runs ``_retain_or_fill``, so a member or owner value stays.
    """

    if receipt is None:
        return
    if (
        values["counterparty"] is None
        or "counterparty" in uncertain
        or "merchant" in uncertain
    ) and receipt.merchant:
        values["counterparty"] = receipt.merchant
        uncertain.discard("counterparty")
        uncertain.discard("merchant")
    if (values["currency"] is None or "currency" in uncertain) and receipt.currency:
        values["currency"] = receipt.currency
        uncertain.discard("currency")


def _retain_or_fill(prior: dict, incoming: dict, *, currency: bool = False) -> dict:
    if incoming["state"] != "known":
        return prior
    if prior["state"] == "unknown":
        return (
            prior
            if prior.get("origin") in {"owner_stated", "member_set", "matched"}
            else incoming
        )
    if (
        currency
        and prior.get("origin") == "default"
        and prior["value"] == "DOP"
        and not prior["source_ids"]
    ):
        return incoming
    if prior["state"] == "known" and prior["value"] == incoming["value"]:
        return prior
    raise ActionError("invalid_input", "receipt_requires_review")
