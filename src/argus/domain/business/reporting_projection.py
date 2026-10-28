"""Project source-owned facts without turning a document into a cash movement."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import TypeAdapter

from argus.domain.business.contracts.dgii import PurchaseDeclaration, SalesDeclaration
from argus.domain.business.contracts.dossier import AccountChoice
from argus.domain.business.contracts.facts import (
    BusinessFacts,
    Known,
    fiscal_inclusion,
    is_personal,
)
from argus.domain.business.dgii_validation import (
    FiscalRecord,
    fact_value,
    is_credit,
    record_issues,
)
from argus.domain.business.fiscal_identity import normalized_ncf, normalized_taxpayer_id
from argus.domain.business.reporting_query import ReportRecord
from argus.domain.ingestion.reconcile.model import ImportEvent

if TYPE_CHECKING:
    from argus.domain.business.reporting_store import RecordedRecord, ReportSource


@dataclass(frozen=True)
class DraftState:
    event: ImportEvent
    facts: BusinessFacts
    fiscal: FiscalRecord
    blockers: tuple[str, ...]
    technical_state: str | None
    sources: tuple[ReportSource, ...]
    dependency_fingerprint: str


def value(facts: BusinessFacts, name: str) -> Any:
    fact = getattr(facts, name)
    return fact.value if isinstance(fact, Known) else None


def _credit(
    record: FiscalRecord, originals: dict[str, FiscalRecord], filer_identity: str | None
) -> tuple[str | None, str, FiscalRecord | None]:
    declaration = record.declaration
    original = None
    if isinstance(declaration, PurchaseDeclaration):
        original = originals.get(str(declaration.purchase_activity_id))
    elif isinstance(declaration, SalesDeclaration):
        matches = [
            item
            for item in originals.values()
            if item.kind == "income"
            and not is_credit(item)
            and normalized_ncf(fact_value(item, "ncf"))
            == normalized_ncf(declaration.modified_ncf)
        ]
        if len(matches) == 1:
            original = matches[0]
    issues = record_issues(record, originals, filer_identity=filer_identity)
    invalid_reference = any(
        issue["code"]
        in (
            "fiscal_credit_reference_conflict",
            "fiscal_credit_settlement_required",
            "fiscal_declaration_missing",
        )
        for issue in issues
    )
    family = (
        {"expense": "purchase", "income": "sale"}.get(original.kind)
        if original and not invalid_reference
        else None
    )
    return family, "known" if family and not issues else "unknown", original


def project(
    recorded: RecordedRecord | None,
    draft: DraftState | None,
    originals: dict[str, FiscalRecord],
    filer_identity: str | None,
    accounts: tuple[AccountChoice, ...] = (),
) -> ReportRecord:
    if recorded is None and draft is None:
        raise ValueError("report source required")
    approved = recorded.approved if recorded else draft.fiscal
    facts = approved.facts
    # The Personal mark and the 606 answer change after approval; every reader
    # takes them from the draft as it stands now.
    marks = draft.facts if draft else facts
    activity = json.loads(recorded.activity_json) if recorded else None
    has_draft = draft is not None
    settled = bool(
        recorded
        and approved.draft_id
        and draft
        and draft.event.state == "accepted"
        and draft.event.accept_key
        and draft.event.activity_id == recorded.row.activity_id
    )
    sources = draft.sources if draft else recorded.sources
    fiscal_number = normalized_ncf(
        fact_value(approved, "ecf") or fact_value(approved, "ncf")
    )
    document_backed = (
        any(
            source.kind == "attachment" and not source.supporting_only
            for source in sources
        )
        or fiscal_number is not None
        or value(facts, "receipt_state") in ("fiscal_receipt", "informal_receipt")
    )
    report_date = (
        value(facts, "occurred_on")
        if document_backed or not recorded
        else recorded.row.occurred_on
    )
    currency = (
        value(facts, "currency")
        if document_backed or not recorded
        else recorded.row.currency
    )
    gross = (
        value(facts, "amount")
        if document_backed or not recorded
        else str(activity["amount"])
    )
    family = "purchase" if value(facts, "kind") == "expense" else None
    explicit_sale = (
        isinstance(approved.declaration, SalesDeclaration)
        or draft
        and draft.event.resolution["business"].get("document_type") == "venta"
    )
    if value(facts, "kind") == "income" and explicit_sale:
        family = "sale"
    if (
        not has_draft
        and activity["kind"] == "expense"
        and activity.get("source_id") is None
    ):
        family = "purchase"
    if activity and activity["kind"] == "refund":
        original = originals.get(activity.get("purchase_activity_id"))
        if original and original.kind == "expense":
            family = "purchase"
    document_kind = "credit_note" if is_credit(approved) else "unknown"
    adjustment = None
    credit_original = None
    if document_kind == "credit_note":
        family, adjustment, credit_original = _credit(approved, originals, filer_identity)
    technical = draft.technical_state if draft else None
    blocked = draft.blockers if draft else ()
    if settled:
        blocked = tuple(code for code in blocked if code != "business_draft_not_open")
    elif recorded and has_draft:
        technical = technical or "approval_provenance_unavailable"
    if draft and draft.event.state == "accepting":
        technical = "approval_outcome_unknown"
    effect = "unknown" if technical else recorded.row.effect if recorded else "known"
    if technical:
        stage = None
    elif blocked:
        stage = "needs_review"
    elif not recorded:
        stage = "awaiting_approval"
    elif (
        currency is not None
        and gross is not None
        and report_date is not None
        and effect == "known"
        and adjustment in (None, "known")
    ):
        stage = "ready_for_export"
    else:
        stage = None
        technical = "report_effect_incomplete"
    funding = value(facts, "funding")
    funding_key = (
        "owner_funds"
        if funding and funding.kind == "owner_funds"
        else "account:" + str(funding.account_id)
        if funding
        else None
    )
    if not has_draft and activity:
        funding_key = (
            "owner_funds"
            if approved.owner_funded
            else "account:" + str(activity["legs"][0]["account_id"])
            if activity.get("legs")
            else None
        )
    account = next(
        (account for account in accounts if funding_key == "account:" + str(account.id)),
        None,
    )
    identity = normalized_taxpayer_id(fact_value(approved, "rnc"))
    # A sale's fiscal identity is the buyer; an issuer is never a customer.
    if value(facts, "kind") == "income" and identity == normalized_taxpayer_id(
        filer_identity
    ):
        identity = None
    payload = {
        "recorded": recorded,
        "draft": draft.dependency_fingerprint if draft else None,
        "credit_original": credit_original,
    }
    dependency = hashlib.sha256(
        json.dumps(
            TypeAdapter(object).dump_python(payload, mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return ReportRecord(
        row_id=f"draft:{draft.event.id}"
        if draft
        else f"activity:{recorded.row.activity_id}",
        draft_id=draft.event.id if draft else None,
        linked_activity_ids=(recorded.row.activity_id,) if recorded else (),
        revision=draft.event.version if draft else recorded.row.revision,
        report_date=report_date,
        date_basis="document_issue" if document_backed else "activity_effective",
        family=family,
        stage=stage,
        technical_state=technical,
        workflow_blockers=blocked,
        currency=currency,
        gross_amount=gross,
        recorded_amount=str(activity["amount"]) if activity else None,
        recorded_currency=recorded.row.currency if recorded else None,
        proposed_amount=gross if not recorded else None,
        money_kind=recorded.row.kind if recorded else value(facts, "kind") or "unknown",
        money_effect=effect,
        adjustment_effect=adjustment,
        counterparty=value(facts, "counterparty"),
        counterparty_key=identity,
        category_key=(
            activity.get("category_id") if activity else value(facts, "category_id")
        )
        or "uncategorized",
        funding_key=funding_key,
        funding_label=account.nickname if account else None,
        funding_kind=account.type
        if account
        else "owner_funds"
        if funding_key == "owner_funds"
        else None,
        has_document=any(
            source.linked
            and source.kind == "attachment"
            and source.connection_status not in (None, "disconnected")
            for source in sources
        ),
        personal=is_personal(marks),
        include_606=fiscal_inclusion(marks),
        document_kind=document_kind,
        fiscal_classification=fiscal_number[:3]
        if fiscal_number
        else "no_comprobante"
        if value(facts, "receipt_state") == "no_receipt"
        else "unknown",
        fiscal_number=fiscal_number,
        document_identifiers=(fiscal_number,) if fiscal_number else (),
        attachment_filenames=tuple(
            source.filename
            for source in sources
            if source.linked
            and source.filename
            and source.connection_status not in (None, "disconnected")
        ),
        note=draft.event.resolution["current_note"]
        if draft and "current_note" in draft.event.resolution
        else activity.get("note")
        if activity
        else draft.event.resolution.get("note"),
        settlement_status=recorded.settlement.status
        if recorded and recorded.settlement
        else None,
        dependency_fingerprint=dependency,
    )
