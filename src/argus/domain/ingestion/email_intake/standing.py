"""Where an email stands in the Bandeja: being read, brought no receipt, or no row.
The one rule; the delivery views and the Bandeja counts both read it, and the
delivery views also read what it saved and why it brought nothing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Sequence

from argus.domain.ingestion.email_intake.models import EmailDelivery, EmailDeliveryPart

EmailStanding = Literal["reading", "no_receipt"]

#: The email carried no file at all.
NO_ATTACHMENT = "email_no_attachment"
#: The email's own code for "some parts were refused", which names no cause.
PARTS_REJECTED = "email_parts_rejected"


@dataclass(frozen=True)
class EmailRow:
    standing: EmailStanding | None
    #: Files this email saved as receipts, repeats of earlier ones included.
    saved_receipt_count: int
    #: Why the email brought no receipt, as a code: the delivery's own error
    #: when it names a cause, else the first refused file's, else
    #: ``email_no_attachment``, else ``email_parts_rejected``. Null unless
    #: the standing is ``no_receipt``.
    no_receipt_reason: str | None


def email_row(
    delivery: EmailDelivery,
    parts: Sequence[EmailDeliveryPart],
    is_repeat: Callable[[EmailDeliveryPart], bool],
) -> EmailRow:
    captured = [part for part in parts if part.state == "captured" and part.document_id]
    standing = _standing(delivery, parts, captured, is_repeat)
    return EmailRow(
        standing,
        len(captured),
        _no_receipt_reason(delivery, parts) if standing == "no_receipt" else None,
    )


def email_standing(
    delivery: EmailDelivery,
    parts: Sequence[EmailDeliveryPart],
    is_repeat: Callable[[EmailDeliveryPart], bool],
) -> EmailStanding | None:
    return email_row(delivery, parts, is_repeat).standing


def _standing(
    delivery: EmailDelivery,
    parts: Sequence[EmailDeliveryPart],
    captured: Sequence[EmailDeliveryPart],
    is_repeat: Callable[[EmailDeliveryPart], bool],
) -> EmailStanding | None:
    if delivery.original_document_id and not captured:
        # The saved original is this email's own Bandeja receipt row; counting
        # the email too would count it twice.
        return None
    if delivery.state == "rejected":
        outcome: EmailStanding = "no_receipt"
    elif delivery.state in ("received", "processing") or any(
        part.state == "pending" for part in parts
    ):
        outcome = "reading"
    elif not parts or any(part.state == "rejected" for part in parts):
        outcome = "no_receipt"
    else:
        return None
    # Last, so the repeat lookup runs only when the outcome could change.
    if any(not is_repeat(part) for part in captured):
        return None
    return outcome


def _no_receipt_reason(
    delivery: EmailDelivery, parts: Sequence[EmailDeliveryPart]
) -> str:
    if delivery.error_code and delivery.error_code != PARTS_REJECTED:
        return delivery.error_code
    refused = next((part for part in parts if part.state == "rejected"), None)
    if refused is not None and refused.error_code:
        return refused.error_code
    if not parts:
        return NO_ATTACHMENT
    return PARTS_REJECTED
