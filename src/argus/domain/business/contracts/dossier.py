from __future__ import annotations

import json
from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import Field, model_validator

from argus.domain.business.document_type import DocumentType

from .actions import ApprovalAction
from .authority import ActorProvenance, Capability
from .checks import DgiiQr, EcfVerification
from .dgii import DgiiDeclaration
from .facts import BusinessFacts, Contract, FactField, ReadPurchase


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


class DraftRevision(Contract):
    draft_id: UUID
    version: int = Field(ge=1)
    actor: ActorProvenance
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


class Blocker(Contract):
    code: str
    field: FactField | None = None


class RecordedApproval(Contract):
    status: Literal["recorded"] = "recorded"
    activity_id: UUID
    reviewed_version: int = Field(ge=1)
    #: The facts revision the person approved: the latest history version at or
    #: below reviewed_version, which also counts approvals and settlements.
    approved_revision: int = Field(ge=1)
    approved_at: datetime
    actor: ActorProvenance


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
    space_name: str
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


class DuplicateCandidate(Contract):
    draft_id: UUID
    version: int = Field(ge=1)


class BusinessDossier(RecordContext):
    current_note: str | None = None
    note_edit_available: bool = False
    supporting_append_available: bool = False
    annotation_unavailable_reason: str | None = None
    dgii: DgiiDeclaration | None = None
    draft_id: UUID
    version: int = Field(ge=1)
    review_state: Literal["open", "accepting", "accepted", "dismissed"]
    facts: BusinessFacts
    sources: tuple[SourceEvidence, ...]
    questions: tuple[ReviewQuestion, ...]
    history: tuple[DraftRevision, ...]
    blockers: tuple[Blocker, ...]
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
    #: The due-notice mark on this one expense. Unpaid is "Factura por pagar".
    #: Paid, the same record becomes "Factura pagada".
    bill_mark: Literal["Factura por pagar", "Factura pagada"] | None = None
    #: The record's marks, read by the same function every list uses: Personal,
    #: who last changed that mark when it was not the owner, whether the fiscal
    #: reading is settled, the fiscal number the draft carries (ncf, ecf), and
    #: the accountant's 606 answer with who gave it, and whether the record is
    #: sin comprobante.
    personal: bool = False
    personal_marked_by: str | None = None
    fiscal_known: bool = False
    fiscal_value: Literal["ncf", "ecf"] | None = None
    include_606: bool | None = None
    include_606_by: str | None = None
    sin_comprobante: bool = False
    #: The document type: a receipt (recibo) or an invoice the business issued
    #: (venta). Detected when no person named it. Editable while the draft is
    #: open and the caller may prepare.
    document_type: DocumentType = "recibo"
    document_type_detected: bool = False
    document_type_editable: bool = False
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

    def model_facing(self) -> dict[str, Any]:
        """The dossier as every model reads it: the JSON dump without the
        facts no scorecard has measured yet."""
        view = self.model_dump(mode="json", exclude=_UNMEASURED_DOSSIER_FIELDS)
        view["sources"] = [_unmeasured_removed(source) for source in view["sources"]]
        return view


#: The due date a person sets in review, wherever the dossier carries it.
_UNMEASURED_DOSSIER_FIELDS = {
    "current_note": True,
    "note_edit_available": True,
    "supporting_append_available": True,
    "annotation_unavailable_reason": True,
    "due_on": True,
    "approval_action": True,
    "fiscal_inclusion_available": True,
    "refund_candidates": True,
    "duplicate_candidates": True,
    "history": {
        "__all__": {
            "before_due_on",
            "after_due_on",
            "before_current_note",
            "after_current_note",
        }
    },
}


def _unmeasured_removed(source: dict[str, Any]) -> dict[str, Any]:
    if source["kind"] != "web_action" or '"due_on"' not in source["text"]:
        return source
    command = json.loads(source["text"])
    command.get("request", {}).pop("due_on", None)
    return {**source, "text": web_action_text(command)}
