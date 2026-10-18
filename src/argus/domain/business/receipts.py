"""A receipt as the Business owner sees it, composed from the facts its owners hold.

``receipt_review`` decides status, fields and the recorded expense. This module
only shapes that review for the Business wire and derives updates from it. It
stores nothing.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from argus.domain.ingestion.documents.models import DocumentDraft, ExtractionBatch
from argus.domain.ingestion.documents.service import entered_by_owner
from argus.domain.ingestion.receipt_review import (
    ReceiptReview,
    ReceiptStatus,
    receipt_review,
)

# ``email`` is set at the API boundary from the email queue, never stored on the draft.
Channel = Literal["web", "whatsapp", "email"]
REVIEW_FIELDS = (
    "merchant",
    "occurred_on",
    "amount",
    "currency",
    "category_id",
    "account_id",
)
CLOSED: frozenset[ReceiptStatus] = frozenset({"confirmed", "dismissed"})
# What a receipt nobody has read needs before the owner can save it by hand.
UNREAD_NEEDS = ("account_id", "amount", "currency", "occurred_on")
# Why a receipt needs the owner, in the words the owner sees. The web keys its
# message on this; ``error_code`` stays the precise cause.
Attention = Literal[
    "unreadable",
    "ai_unavailable",
    "interrupted",
    "outcome_unknown",
    "no_purchase_found",
    "several_purchases",
    "source_unavailable",
    "check_details",
    "duplicate",
    "other",
]
# Preparation failures with nothing read, by the code the draft records.
_UNREAD_ATTENTION: Mapping[str, Attention] = {
    **dict.fromkeys(
        (
            "invalid_document",
            "empty_document",
            "encrypted_document",
            "unsupported_image_frames",
            "unsupported_media_type",
            "document_too_large",
            "document_page_limit",
            "document_text_limit",
            "document_memory_limit",
            "document_empty",
            "document_row_limit",
            "document_cell_limit",
            "document_archive_limit",
            "unsupported_spreadsheet_content",
            "spreadsheet_formula_unsupported",
            "document_email_limit",
            "unsupported_email_attachment",
        ),
        "unreadable",
    ),
    **dict.fromkeys(
        (
            "missing_vision_model",
            "missing_api_key",
            "document_tools_unavailable",
            "document_extraction_disabled",
            "document_extraction_unavailable",
            "extraction_unavailable",
            "extraction_provider_failed",
            "document_extraction_failed",
            "document_invalid_extraction",
            "document_preparation_timeout",
            "document_rate_limited",
        ),
        "ai_unavailable",
    ),
    **dict.fromkeys(
        (
            "document_preparation_interrupted",
            "document_delivery_failed",
            "document_lease_lost",
            "document_storage_unavailable",
            "document_version_conflict",
            "document_busy",
            "document_attempt_superseded",
        ),
        "interrupted",
    ),
    "document_preparation_outcome_unknown": "outcome_unknown",
    "document_source_unavailable": "source_unavailable",
}
# Another read of the same bytes fails the same way, or cannot be made.
_NO_RETRY: frozenset[Attention] = frozenset({"unreadable", "source_unavailable"})
_BUSY = ("queued", "preparing")
_UPDATE_KINDS: Mapping[str, str] = {
    "review_ready": "receipt_ready",
    "needs_attention": "receipt_needs_attention",
    "confirmed": "expense_confirmed",
}


@dataclass(frozen=True)
class Receipt:
    draft: DocumentDraft
    review: ReceiptReview
    channel: Channel
    entered_by_owner: bool = False
    # Deliveries this document arrived in; set at the API boundary from the email queue.
    email_delivery_ids: tuple[str, ...] = ()
    # The whole message of an email whose attachment is already a receipt: it
    # is context for that receipt, never a second one to prepare or approve.
    email_original: bool = False
    # The upload that produced this view found the same bytes already saved.
    replayed: bool = False
    # A read will happen (in flight, or queued and allowed now); None reads it
    # from the draft's status alone, for callers without a documents service.
    read_pending: bool | None = None

    @property
    def id(self) -> str:
        return self.draft.connection_id

    @property
    def busy(self) -> bool:
        """Something is reading, or will read, this receipt."""

        if self.read_pending is not None:
            return self.read_pending
        return self.draft.status in _BUSY

    @property
    def status(self) -> ReceiptStatus:
        if self.review.status == "saved" and self.draft.error_code is not None:
            return "needs_attention"
        # Prepared, yet with no single purchase to confirm: the owner must look.
        if self.review.status == "review_ready" and self.review.blocker is not None:
            return "needs_attention"
        # Queued, yet nothing will read it (the owner's reading is off): it is
        # saved and waits for a person, and the view says so.
        if self.review.status == "queued" and not self.busy:
            return "saved"
        return self.review.status

    @property
    def error_code(self) -> str | None:
        if self.status == "needs_attention" and self.review.error_code is None:
            return self.review.blocker
        return self.review.error_code

    @property
    def version(self) -> int:
        """The import event's version; 0 while there is no purchase to review."""

        return self.review.event_version or 0

    @property
    def enterable(self) -> bool:
        """The owner may fill it in by hand: there is no single purchase to
        review, nothing is reading it, and no read purchase is being recorded."""

        return (
            not self.email_original
            and self.review.blocker is not None
            and self.review.blocker != "possible_duplicate"
            and not self.busy
            and all(
                read.state in ("open", "dismissed") for read in self.review.read_purchases
            )
        )

    @property
    def preparable(self) -> bool:
        """The owner may ask for an AI read: nothing was read or entered, the
        source is stored, and another read could succeed."""

        return (
            not self.email_original
            and self.review.blocker == "not_prepared"
            and self.draft.source_available
            and not self.busy
            and _UNREAD_ATTENTION.get(self.draft.error_code or "") not in _NO_RETRY
        )

    @property
    def attention(self) -> Attention | None:
        """Why the owner must look; ``enterable`` and ``preparable`` say what
        they can do about it."""

        if self.status != "needs_attention":
            return None
        blocker = self.review.blocker
        if blocker is None:
            return "check_details"
        if blocker == "not_prepared":
            if not self.draft.source_available:
                return "source_unavailable"
            if self.review.evidence is not None:
                # The read is saved; only the hand-off to a record failed.
                return "interrupted"
            return _UNREAD_ATTENTION.get(self.draft.error_code or "", "other")
        if self.entered_by_owner:
            # The owner's entry stopped before it reached review.
            return "other"
        if self.draft.error_code == "unreadable_document":
            return "unreadable"
        if blocker == "no_purchase_found":
            return "no_purchase_found"
        if blocker == "possible_duplicate":
            return "duplicate"
        return "several_purchases"

    @property
    def missing_fields(self) -> list[str]:
        if self.enterable:
            return list(UNREAD_NEEDS)
        return [name for name in self.review.missing if name in REVIEW_FIELDS]

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "channel": self.channel,
            "email_delivery_ids": list(self.email_delivery_ids),
            "email_original": self.email_original,
            "filename": self.draft.filename,
            "source_text": self.draft.source_text,
            "media_type": self.draft.media_type,
            "size_bytes": self.draft.size_bytes,
            "received_at": self.draft.created_at,
            "status": self.status,
            "error_code": self.error_code,
            "attention": self.attention,
            "duplicate_of": self.review.duplicate_of,
            "replayed": self.replayed,
            "read_pending": self.busy,
            "preparable": self.preparable,
            "enterable": self.enterable,
            "expense_id": self.review.expense_id,
            **review_fields(self.review),
        }

    def detail(self) -> dict[str, Any]:
        return {
            **self.summary(),
            "version": self.version,
            "draft_id": self.review.event_id,
            "evidence": None if self.entered_by_owner else evidence(self.review),
            "missing_fields": self.missing_fields,
        }


def review_fields(review: ReceiptReview) -> dict[str, str | None]:
    """The review's proposal under the Business wire names.

    The only reader of ``ReceiptFields``, so a rename there changes one place.
    """

    fields = review.fields
    if fields is None:
        return dict.fromkeys(REVIEW_FIELDS)
    return {
        "merchant": fields.note,
        "occurred_on": fields.occurred_on,
        "amount": fields.amount,
        "currency": fields.currency,
        "category_id": fields.category_id,
        "account_id": fields.account_id,
    }


def compose(
    draft: DocumentDraft,
    batch: ExtractionBatch | None,
    events: Iterable[Mapping[str, Any]],
    channel: Channel,
    read_pending: bool | None = None,
) -> Receipt:
    return Receipt(
        draft,
        receipt_review(draft, batch, events),
        channel,
        entered_by_owner(batch),
        read_pending=read_pending,
    )


def evidence(review: ReceiptReview) -> dict[str, Any] | None:
    """What the receipt itself says. Review corrections never change it."""

    read = (review.evidence or {}).get("receipt")
    if read is None:
        return None
    return {
        "merchant": read["merchant"],
        "occurred_on": read["occurred_on"],
        "total": read["total"],
        "currency": read["currency"],
        "tax": read["tax"],
        "tip": read["tip"],
        "service": read["service"],
        "lines": [
            {"description": item["description"] or "", "amount": item["total"]}
            for item in read["items"]
        ],
    }


def updates(
    receipts: Iterable[Receipt],
    confirmed_at: Mapping[str, datetime],
    views: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Newest first. ``confirmed_at`` maps an expense id to when it was recorded.
    ``views`` are the receipts' overlaid summaries by id: when a receipt has
    one, its status, expense, cause and label come from there."""

    items = []
    for receipt in receipts:
        view = (views or {}).get(receipt.id) or receipt.summary()
        kind = _UPDATE_KINDS.get(view["status"])
        if kind is None:
            continue
        expense_id = view["expense_id"]
        items.append(
            {
                "id": f"{kind}:{receipt.id}",
                "kind": kind,
                "occurred_at": confirmed_at.get(
                    expense_id or "", receipt.draft.updated_at
                ),
                "receipt_id": receipt.id,
                "expense_id": expense_id,
                "error_code": view["error_code"],
                "attention": view["attention"],
                "label": view["merchant"] or receipt.draft.filename,
            }
        )
    return sorted(items, key=lambda item: item["occurred_at"], reverse=True)
