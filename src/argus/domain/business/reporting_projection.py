"""Project source-owned facts without turning a document into a cash movement."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import TypeAdapter

from argus.domain.business.amount_inheritance import document_is_paid, inheritance_state
from argus.domain.business.contracts.dgii import PurchaseDeclaration, SalesDeclaration
from argus.domain.business.contracts.dossier import AccountChoice
from argus.domain.business.contracts.facts import (
    BusinessFacts,
    Known,
    fiscal_inclusion,
    is_personal,
    is_sin_comprobante,
    personal_mark_admits,
)
from argus.domain.business.dgii_codes import EXPENSE_TYPES, PAYMENT_FORMS
from argus.domain.business.dgii_line import confirmed_declaration
from argus.domain.business.dgii_validation import (
    FiscalRecord,
    fact_value,
    is_credit,
    record_issues,
)
from argus.domain.business.document_type import SALE, direction
from argus.domain.business.fiscal_identity import normalized_ncf, normalized_taxpayer_id
from argus.domain.business.purchase_review import net_amount
from argus.domain.business.reporting_query import DgiiChoice, Purchase606, ReportRecord
from argus.domain.business.review_flags import review_flags
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


def _choice(names: dict[str, str], code: str | None) -> DgiiChoice | None:
    return DgiiChoice(code=code, label=names[code]) if code else None


def current_marks(approved: FiscalRecord, draft: BusinessFacts | None) -> BusinessFacts:
    """The Personal mark and the 606 answer change after approval; every reader
    takes them from the draft as it stands now, or the approved facts without one."""

    return draft if draft is not None else approved.facts


def purchase_606(approved: FiscalRecord, marks: BusinessFacts) -> Purchase606 | None:
    """The 606 answers the export would carry for this record, from the same
    declaration and admission rules, so Registros and the DGII summary never disagree.
    A suggested tipo de gasto nobody confirmed counts as missing, as in the export."""

    found = direction(approved.document_type)
    admitted = personal_mark_admits(
        is_personal(marks), fiscal_inclusion(marks), sale=False
    )
    if (
        found is None
        or found.family != "purchase"
        or not admitted
        or is_sin_comprobante(approved.facts)
    ):
        return None
    declaration = confirmed_declaration(approved)
    purchase = declaration if isinstance(declaration, PurchaseDeclaration) else None
    return Purchase606(
        expense_type=_choice(EXPENSE_TYPES, purchase.category if purchase else None),
        payment_form=_choice(
            PAYMENT_FORMS, purchase.payment_method if purchase else None
        ),
    )


def _credit(
    record: FiscalRecord, originals: dict[str, FiscalRecord], filer_identity: str | None
) -> tuple[str, FiscalRecord | None]:
    """A credit note's adjustment, known once the document it returns is
    linked and the line is clean, and that original."""

    declaration = confirmed_declaration(record)
    original = None
    if isinstance(declaration, PurchaseDeclaration):
        original = originals.get(str(declaration.purchase_activity_id))
    elif isinstance(declaration, SalesDeclaration):
        matches = [
            item
            for item in originals.values()
            if direction(item.document_type) is SALE
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
    linked = original is not None and not invalid_reference
    return "known" if linked and not issues else "unknown", original


def project(
    recorded: RecordedRecord,
    draft: DraftState | None,
    originals: dict[str, FiscalRecord],
    filer_identity: str | None,
    accounts: tuple[AccountChoice, ...] = (),
) -> ReportRecord:
    """One Registros row for one recorded money row, read with the approved
    facts and, when a draft backs it, that draft's current marks and blockers."""

    approved = recorded.approved
    facts = approved.facts
    marks = current_marks(approved, draft.facts if draft else None)
    activity = json.loads(recorded.activity_json)
    settled = bool(
        approved.draft_id
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
        value(facts, "occurred_on") if document_backed else recorded.row.occurred_on
    )
    currency = value(facts, "currency") if document_backed else recorded.row.currency
    gross = value(facts, "amount") if document_backed else str(activity["amount"])
    found = direction(approved.document_type)
    family = found.family if found else None
    document_kind = "credit_note" if is_credit(approved) else "unknown"
    adjustment = None
    credit_original = None
    if document_kind == "credit_note":
        adjustment, credit_original = _credit(approved, originals, filer_identity)
    technical = draft.technical_state if draft else None
    blocked = draft.blockers if draft else ()
    if settled:
        blocked = tuple(code for code in blocked if code != "business_draft_not_open")
    elif draft:
        technical = technical or "approval_provenance_unavailable"
    effect = "unknown" if technical else recorded.row.effect
    if technical:
        stage = None
    elif blocked:
        stage = "needs_review"
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
    if draft is None:
        funding_key = activity.get("funding") or (
            "account:" + str(activity["legs"][0]["account_id"])
            if activity.get("legs")
            else None
        )
    account = next(
        (account for account in accounts if funding_key == "account:" + str(account.id)),
        None,
    )
    identity = normalized_taxpayer_id(fact_value(approved, "rnc"))
    # A sale's fiscal identity is the buyer; an issuer is never a customer.
    if found is SALE and identity == normalized_taxpayer_id(filer_identity):
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
    purchase = purchase_606(approved, marks)
    declaration = confirmed_declaration(approved)
    purchase_amounts = (
        declaration
        if purchase is not None and isinstance(declaration, PurchaseDeclaration)
        else None
    )
    net = net_amount(facts, declaration, total=gross)
    mismatch = next(
        (
            flag
            for flag in review_flags(facts, declaration=declaration)
            if flag.code == "amounts_mismatch"
        ),
        None,
    )
    return ReportRecord(
        row_id=f"draft:{draft.event.id}"
        if draft
        else f"activity:{recorded.row.activity_id}",
        draft_id=draft.event.id if draft else None,
        linked_activity_ids=(recorded.row.activity_id,),
        revision=draft.event.version if draft else recorded.row.revision,
        report_date=report_date,
        date_basis="document_issue" if document_backed else "activity_effective",
        family=family,
        stage=stage,
        technical_state=technical,
        workflow_blockers=blocked,
        currency=currency,
        gross_amount=gross,
        net_amount=net.amount,
        net_amount_source=net.source,
        amounts_difference=mismatch.difference if mismatch else None,
        inheritance=inheritance_state(
            facts,
            declaration,
            approved.fiscal_overrides,
            paid=approved.paid or document_is_paid(recorded.settlement.status if recorded.settlement else None),
        ),
        itbis_amount=value(facts.fiscal, "itbis") if facts.fiscal else None,
        goods_amount=purchase_amounts.goods_amount if purchase_amounts else None,
        services_amount=purchase_amounts.services_amount if purchase_amounts else None,
        recorded_amount=str(activity["amount"]),
        recorded_currency=recorded.row.currency,
        money_kind=recorded.row.kind,
        money_effect=effect,
        adjustment_effect=adjustment,
        # With no draft, the activity's note is its merchant.
        counterparty=value(facts, "counterparty")
        or (activity.get("note") if not draft else None),
        counterparty_key=identity,
        category_key=activity.get("category_id") or "uncategorized",
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
        dgii_606=purchase,
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
        # Only a saved note: the draft's and the activity's `note` hold the merchant.
        note=draft.event.resolution.get("current_note") if draft else None,
        settlement_status=recorded.settlement.status if recorded.settlement else None,
        dependency_fingerprint=dependency,
    )


def with_export_verdicts(
    rows: tuple[ReportRecord, ...],
    verdicts: dict[str, tuple[str, ...] | None],
    exported: frozenset[str],
) -> tuple[ReportRecord, ...]:
    """Current fiscal data uses the current verdict. Export stage separately
    keeps the history of downloaded lines."""

    def judged(row: ReportRecord) -> ReportRecord:
        if row.stage != "ready_for_export":
            return row
        identifier = row.linked_activity_ids[0]
        if identifier in verdicts:
            row = row.model_copy(
                update={
                    "fiscal_data": "complete"
                    if verdicts[identifier] is None
                    else "missing"
                }
            )
        if identifier in exported:
            return row.model_copy(update={"stage": "exported", "export_line": True})
        if identifier not in verdicts:
            return row
        missing = verdicts[identifier]
        if missing is None:
            return row.model_copy(update={"export_line": True})
        return row.model_copy(
            update={
                "stage": "needs_fiscal_data",
                "export_missing": missing[0],
                "export_missing_several": len(missing) > 1,
            }
        )

    return tuple(judged(row) for row in rows)
