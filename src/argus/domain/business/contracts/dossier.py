from __future__ import annotations

import json
from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import Field, model_validator

from argus.domain.business.bandeja_group import (
    BandejaGroupName,
    BandejaLabel,
    BandejaReason,
)
from argus.domain.business.contracts.deletion import DeletedDocument
from argus.domain.business.document_type import DocumentType
from argus.domain.business.space_name import GivenName
from argus.domain.business.supplier_fast_path import RncRegistryStatus

from .actions import ApprovalAction, DuplicateDecision
from .authority import ActorView, Capability, PersonName
from .checks import DgiiQr, EcfVerification
from .dgii import DeclarationSuggestions, DgiiDeclaration
from .facts import (
    HUMAN_AMOUNT_FIELDS,
    BusinessFacts,
    Contract,
    FactField,
    InheritedValue,
    NetAmount,
    ReadPurchase,
)


class MessageSource(Contract):
    id: UUID
    kind: Literal["message", "agent_proposal"]
    channel: Literal["web", "whatsapp"]
    received_at: datetime
    text: str = Field(min_length=1, max_length=20000)


class WebActionSource(Contract):
    id: UUID
    kind: Literal["web_action"] = "web_action"
    channel: Literal["web"] = "web"
    received_at: datetime
    text: str = Field(min_length=1, max_length=20000)


def web_action_text(command: dict[str, Any]) -> str:
    """The canonical text a web action source records for its command."""
    return json.dumps(command, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class AttachmentSource(Contract):
    id: UUID
    kind: Literal["attachment"] = "attachment"
    #: The stored row says ``web`` for every attachment. ``whatsapp`` comes from
    #: the intake store and ``email`` (with its deliveries) from the email queue,
    #: both set at the API boundary.
    channel: Literal["web", "whatsapp", "email"]
    received_at: datetime
    connection_id: UUID
    filename: str | None
    media_type: str
    email_delivery_ids: tuple[str, ...] = ()


SourceEvidence = Annotated[
    MessageSource | WebActionSource | AttachmentSource, Field(discriminator="kind")
]
QuestionState = Literal[
    "open", "answered", "owner_does_not_know", "waiting_for_window", "withdrawn"
]


class ReviewQuestion(Contract):
    id: UUID
    draft_id: UUID
    field: FactField
    asked_of: Literal["owner", "accountant"]
    channel: Literal["whatsapp", "web"]
    state: QuestionState
    prompt: str = Field(min_length=1, max_length=500)
    allowed_answers: tuple[Literal["known", "owner_does_not_know"], ...] = Field(
        min_length=1
    )
    answer_source_id: UUID | None = None
    created_at: datetime

    @model_validator(mode="after")
    def answer_provenance(self) -> ReviewQuestion:
        if (
            self.state in {"answered", "owner_does_not_know"}
            and self.answer_source_id is None
        ):
            raise ValueError("answered questions require their answer source")
        if self.state == "owner_does_not_know" and self.asked_of != "accountant":
            raise ValueError("owner uncertainty moves the question to the accountant")
        return self


# Why a revision no person and no read made exists, as
# business_draft_revisions.reason stores it.
RevisionReason = Literal["business_rnc_set"]


class DuplicateRevision(Contract):
    """The revision a person's duplicate decision wrote, read from the command
    its web action source recorded; the other document as it reads now."""

    decision: Literal["different_purchase"]
    other_draft_id: UUID
    other_counterparty: str | None = None
    other_filename: str | None = None


class DraftRevision(Contract):
    draft_id: UUID
    version: int = Field(ge=1)
    actor: ActorView
    before: BusinessFacts | None
    after: BusinessFacts
    source_ids: tuple[UUID, ...]
    turn_key: str | None = None
    created_at: datetime
    before_dgii: DgiiDeclaration | None = None
    after_dgii: DgiiDeclaration | None = None
    before_current_note: str | None = None
    after_current_note: str | None = None
    before_due_on: date | None = None
    after_due_on: date | None = None
    reason: RevisionReason | None = None
    duplicate: DuplicateRevision | None = None


class Blocker(Contract):
    code: str
    field: FactField | None = None
    min_date: str | None = Field(default=None, exclude_if=lambda value: value is None)
    today: str | None = Field(default=None, exclude_if=lambda value: value is None)


class ReviewFlag(Contract):
    """A read value to check again. ``confirm`` flags need ``approve_anyway``
    on the approve request; the rest only warn."""

    code: Literal["rnc_check_digit", "ncf_malformed", "itbis_high", "amounts_mismatch"]
    field: Literal["rnc", "ncf", "itbis", "amount"]
    confirm: bool
    difference: str | None = Field(default=None, exclude_if=lambda value: value is None)


class RecordedApproval(Contract):
    status: Literal["recorded"] = "recorded"
    activity_id: UUID
    reviewed_version: int = Field(ge=1)
    #: The facts revision the person approved: the latest history version at or
    #: below reviewed_version, which also counts approvals and settlements.
    approved_revision: int = Field(ge=1)
    approved_at: datetime
    actor: ActorView


class UnsettledApproval(Contract):
    status: Literal["outcome_unknown", "failed"]
    code: str
    reviewed_version: int = Field(ge=1)


ApprovalResult = Annotated[
    RecordedApproval | UnsettledApproval, Field(discriminator="status")
]


class AccountChoice(Contract):
    id: UUID
    nickname: str | None
    type: str
    currency: str


class RecordContext(Contract):
    space_id: UUID
    space_name: GivenName
    accounts: tuple[AccountChoice, ...]
    capabilities: frozenset[Capability]


class RefundCandidate(Contract):
    """An approved purchase a credit note may refund; ``id`` is the activity
    the declaration's ``purchase_activity_id`` names."""

    id: str
    merchant: str | None
    occurred_on: date
    amount: str
    currency: str


class ComparedFile(Contract):
    connection_id: UUID
    filename: str | None
    media_type: str
    #: Where and when the file arrived, as ``AttachmentSource`` says it: the
    #: stored row says ``web``; the API boundary sets ``whatsapp`` and ``email``.
    channel: Literal["web", "whatsapp", "email"]
    received_at: datetime


class ComparedDocument(Contract):
    """The main data of one document of a possible repeat, as its draft
    holds it now. An unknown value is null."""

    draft_id: UUID
    counterparty: str | None = None
    occurred_on: date | None = None
    amount: str | None = None
    currency: str | None = None
    #: The NCF, else the e-CF number.
    fiscal_number: str | None = None
    file: ComparedFile | None = None
    received_at: datetime | None = None
    approved_at: datetime | None = None
    #: ``accepted`` once approved. The reviewed document is always ``open``.
    state: Literal["open", "accepted"]


ComparedField = Literal[
    "counterparty", "occurred_on", "amount", "currency", "fiscal_number", "file"
]


class DuplicateComparison(Contract):
    """The reviewed document beside the one it may repeat. The server owns
    which values differ and what it recommends; a client renders both."""

    document: ComparedDocument
    other: ComparedDocument
    differences: tuple[ComparedField, ...] = ()
    #: By the fiscal number alone: ``same_purchase`` when both carry the same
    #: one, ``different_purchase`` when they differ, null when either has none.
    recommendation: DuplicateDecision | None = None


#: Why two documents look like one: the read gave both the same merchant,
#: date, amount and currency, or both carry one supplier RNC and fiscal number.
DuplicateBasis = Literal["read_facts", "fiscal_number"]


class DuplicateCandidate(Contract):
    draft_id: UUID
    version: int = Field(ge=1)
    basis: DuplicateBasis
    #: What this reader may decide for the pair now. ``same_purchase`` deletes
    #: the reviewed document and is the owner's alone; ``different_purchase``
    #: settles only a ``read_facts`` warning.
    decisions: tuple[DuplicateDecision, ...] = ()
    comparison: DuplicateComparison


class BandejaStanding(Contract):
    """Where a record stands in the Bandeja: the group, reason and label
    ``bandeja_group.group_of`` gives its row in the receipt list."""

    group: BandejaGroupName | None
    reason: BandejaReason | None
    label: BandejaLabel | None


class BusinessDossier(RecordContext):
    deleted: DeletedDocument | None = None
    delete_available: bool = False
    restore_available: bool = False
    current_note: str | None = None
    #: "No pudimos verificar este remitente." when the draft came from email
    #: whose sender is authorized but did not verify; null otherwise. The same
    #: string the email inbox row carries, shown beside Aprobar.
    review_note: str | None = None
    note_edit_available: bool = False
    supporting_append_available: bool = False
    annotation_unavailable_reason: str | None = None
    dgii: DgiiDeclaration | None = None
    draft_id: UUID
    version: int = Field(ge=1)
    review_state: Literal["open", "accepting", "accepted", "dismissed"]
    facts: BusinessFacts
    net_amount: NetAmount = NetAmount(amount=None, source=None)
    inheritance: dict[str, InheritedValue] = Field(default_factory=dict)
    sources: tuple[SourceEvidence, ...]
    questions: tuple[ReviewQuestion, ...]
    history: tuple[DraftRevision, ...]
    blockers: tuple[Blocker, ...]
    review_flags: tuple[ReviewFlag, ...] = ()
    approval_available: bool
    duplicate_candidates: tuple[DuplicateCandidate, ...] = ()
    #: The approve action this draft takes once ``approval_available``, by its
    #: kind; null while approval is not available.
    approval_action: ApprovalAction | None = None
    approval_result: ApprovalResult | None = None
    #: The purchases a document read showed when it could not settle on one,
    #: the receipt total it showed, and how many of them this draft leaves
    #: unrecorded (0 once a person settled the rest).
    read_purchases: tuple[ReadPurchase, ...] = ()
    read_total: str | None = None
    unrecorded_purchases: int = Field(default=0, ge=0)
    #: The local checks on the e-CF the draft came from; None for any other source.
    ecf_checks: EcfVerification | None = None
    #: The DGII QR the receipt carried: the link a person opens on DGII's page.
    dgii_qr: DgiiQr | None = None
    #: Review shows the e-CF checks card: the server switch
    #: ``CUADRAO_ECF_CHECKS_PANEL_ENABLED``. ``ecf_checks`` and ``dgii_qr``
    #: come either way.
    ecf_checks_panel_available: bool = False
    #: The due-notice mark on this one expense. Unpaid is "Factura por pagar".
    #: Paid, the same record becomes "Factura pagada".
    bill_mark: Literal["Factura por pagar", "Factura pagada"] | None = None
    #: The record's marks, read by the same function every list uses: Personal,
    #: who last changed that mark when it was not the owner, whether the fiscal
    #: reading is settled, the fiscal number the draft carries (ncf, ecf), and
    #: the accountant's 606 answer with who gave it, and whether the record is
    #: sin comprobante.
    personal: bool = False
    personal_marked_by: PersonName | None = None
    fiscal_known: bool = False
    fiscal_value: Literal["ncf", "ecf"] | None = None
    fiscal_question_applies: bool = False
    include_606: bool | None = None
    include_606_by: PersonName | None = None
    sin_comprobante: bool = False
    #: The document type: a receipt (recibo) or an invoice the business issued
    #: (venta). Detected when no person named it. Editable while the draft is
    #: open and the caller may prepare.
    document_type: DocumentType = "recibo"
    document_type_detected: bool = False
    document_type_editable: bool = False
    #: The caller may write the 606 declaration now: open or approved, and the
    #: caller holds prepare. A download changes nothing here.
    declaration_editable: bool = False
    #: What the server offers for each 606 answer this open expense lacks, with
    #: where it came from. The approval saves it, so only an approval takes one.
    declaration_suggestions: DeclarationSuggestions = DeclarationSuggestions()
    #: The caller may write the 607 payment split now, on the same terms as
    #: declaration_editable, on a sale.
    payment_split_editable: bool = False
    #: The caller may return this approved record to the Bandeja now: it holds
    #: approve, and no bank match, credit note or refund is linked to the
    #: record. The reopen route refuses on the same rule.
    reopen_available: bool = False
    #: The due date a person set in review; null while unknown. Never read
    #: from the document or defaulted. Locked with the other facts once approved.
    due_on: date | None = None
    #: The caller may answer "¿Incluir en 606?" now: the same gate the
    #: fiscal-inclusion action enforces (a prepare-holder other than the
    #: owner, an open or accepted draft, a personal receipt with a fiscal number).
    fiscal_inclusion_available: bool = False
    #: The purchases this draft may refund, chosen on the server (see
    #: ``actions/refunds.py``); empty unless the draft is a refund or a credit note.
    refund_candidates: tuple[RefundCandidate, ...] = ()
    #: The Business year in which the first source arrived, and whether the
    #: issue date is a read whose year is not that year (see
    #: ``bandeja_group.year_to_check``). The review calendar offers the upload
    #: year exactly when ``year_to_check`` holds.
    upload_year: int | None = None
    year_to_check: bool = False
    #: Where the record stands in the Bandeja, by the one rule the receipt
    #: list reads. ``label`` is ``accepted`` once the record is recorded.
    bandeja_group: BandejaStanding = Field(
        default_factory=lambda: BandejaStanding(group=None, reason=None, label=None)
    )
    #: Every reason a record that needs attention is not Listos, in the rule's
    #: order; empty for any other record. ``bandeja_group.reason`` is one of them.
    listo_gaps: tuple[BandejaReason, ...] = ()
    #: What the DGII register says of the supplier RNC: its mapped status, or
    #: ``not_found`` when the register does not list it. Null when the record
    #: has no RNC or no register is loaded.
    rnc_registry_status: RncRegistryStatus | None = None

    def model_facing(self) -> dict[str, Any]:
        """The dossier as every model reads it: the JSON dump without the
        facts no scorecard has measured yet."""
        view = self.model_dump(mode="json", exclude=_UNMEASURED_DOSSIER_FIELDS)
        view["sources"] = [_unmeasured_removed(source) for source in view["sources"]]
        return view


#: The due date a person sets in review, wherever the dossier carries it.
_UNMEASURED_DOSSIER_FIELDS = {
    "net_amount": True,
    "inheritance": True,
    "facts": set(HUMAN_AMOUNT_FIELDS),
    "dgii": {"itbis", "suggestion_sources"},
    "deleted": True,
    "delete_available": True,
    "restore_available": True,
    "current_note": True,
    "note_edit_available": True,
    "supporting_append_available": True,
    "annotation_unavailable_reason": True,
    "due_on": True,
    "declaration_editable": True,
    "reopen_available": True,
    "declaration_suggestions": True,
    "payment_split_editable": True,
    "approval_action": True,
    "fiscal_inclusion_available": True,
    "refund_candidates": True,
    "duplicate_candidates": True,
    "review_flags": True,
    "upload_year": True,
    "year_to_check": True,
    "bandeja_group": True,
    "listo_gaps": True,
    "rnc_registry_status": True,
    "history": {
        "__all__": {
            "before_due_on": True,
            "after_due_on": True,
            "before_current_note": True,
            "after_current_note": True,
            "before": set(HUMAN_AMOUNT_FIELDS),
            "after": set(HUMAN_AMOUNT_FIELDS),
            "before_dgii": {"itbis", "suggestion_sources"},
            "after_dgii": {"itbis", "suggestion_sources"},
        }
    },
}


_UNMEASURED_REVIEW_INPUT = ("due_on", "payment_split", "montos")


def _unmeasured_removed(source: dict[str, Any]) -> dict[str, Any]:
    if source["kind"] != "web_action" or not any(
        f'"{name}"' in source["text"] for name in (*_UNMEASURED_REVIEW_INPUT, "itbis")
    ):
        return source
    command = json.loads(source["text"])
    for name in _UNMEASURED_REVIEW_INPUT:
        command.get("request", {}).pop(name, None)
    request = command.get("request", {})
    for declaration in ((request.get("dgii") or {}).get("declaration"), request.get("purchase")):
        if isinstance(declaration, dict):
            declaration.pop("itbis", None)
    return {**source, "text": web_action_text(command)}
