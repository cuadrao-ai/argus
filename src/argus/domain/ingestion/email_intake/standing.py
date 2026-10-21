"""Where an email stands in the Bandeja: being read, brought no receipt, or no row.
The one rule; the delivery views and the Bandeja counts both read it."""

from __future__ import annotations

from typing import Callable, Literal, Sequence

from argus.domain.ingestion.email_intake.models import EmailDelivery, EmailDeliveryPart

EmailStanding = Literal["reading", "no_receipt"]


def email_standing(
    delivery: EmailDelivery,
    parts: Sequence[EmailDeliveryPart],
    is_repeat: Callable[[EmailDeliveryPart], bool],
) -> EmailStanding | None:
    captured = [part for part in parts if part.state == "captured" and part.document_id]
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
