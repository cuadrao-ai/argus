"""Where an email stands in the Bandeja. The cases mirror the web's own test of
the same rule, plus the one fact only the server sees: a saved original."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest
from argus.domain.ingestion.email_intake.models import EmailDelivery, EmailDeliveryPart
from argus.domain.ingestion.email_intake.standing import email_row, email_standing

NOW = datetime(2026, 10, 13, 17, 14, tzinfo=timezone.utc)


def delivery(state: str = "captured", original: str | None = None) -> EmailDelivery:
    return EmailDelivery(
        id="email-1",
        provider="resend",
        external_id="msg-1",
        recipients=("negocio@example.test",),
        route_id="route-1",
        space_id="space-1",
        principal_id="user-1",
        state=state,
        original_document_id=original,
        received_at=NOW,
        updated_at=NOW,
        lease_token=None,
        attempts=0,
        error_code=None,
        subject="Factura",
        sender="ventas@example.test",
        sent_at=None,
        text_body=None,
    )


def part(
    part_id: str = "1.2", state: str = "captured", document: str | None = "rcpt-1"
) -> EmailDeliveryPart:
    return EmailDeliveryPart(
        id=part_id,
        filename="factura.pdf",
        media_type="application/pdf",
        state=state,
        document_id=document if state == "captured" else None,
        error_code="too_large" if state == "rejected" else None,
    )


SAVED = part()
OTHER_SAVED = part("1.3")
PENDING = part(state="pending")
REJECTED = part("1.3", state="rejected")
ONLY_REPEAT = frozenset({SAVED.id})

CASES = [
    ("a saved file is its own row", "captured", None, [SAVED], frozenset(), None),
    (
        "a saved file beside a refused one",
        "partial",
        None,
        [SAVED, REJECTED],
        frozenset(),
        None,
    ),
    ("received, nothing yet", "received", None, [], frozenset(), "reading"),
    (
        "processing with a pending part",
        "processing",
        None,
        [PENDING],
        frozenset(),
        "reading",
    ),
    (
        "partial with a pending and a refused part",
        "partial",
        None,
        [PENDING, REJECTED],
        frozenset(),
        "reading",
    ),
    ("rejected", "rejected", None, [], frozenset(), "no_receipt"),
    (
        "every part refused",
        "partial",
        None,
        [part(state="rejected")],
        frozenset(),
        "no_receipt",
    ),
    ("captured with no attachment", "captured", None, [], frozenset(), "no_receipt"),
    (
        "a refused file beside a repeat",
        "partial",
        None,
        [SAVED, REJECTED],
        ONLY_REPEAT,
        "no_receipt",
    ),
    ("a repeat of a file already saved", "captured", None, [SAVED], ONLY_REPEAT, None),
    (
        "a repeat beside a new file",
        "captured",
        None,
        [SAVED, OTHER_SAVED],
        ONLY_REPEAT,
        None,
    ),
    ("rejected with a saved original", "rejected", "orig-1", [], frozenset(), None),
    ("captured, no parts, original saved", "captured", "orig-1", [], frozenset(), None),
    ("received, original saved", "received", "orig-1", [], frozenset(), None),
    (
        "a pending part, original saved",
        "processing",
        "orig-1",
        [PENDING],
        frozenset(),
        None,
    ),
    (
        "original saved and a new file",
        "partial",
        "orig-1",
        [SAVED, REJECTED],
        frozenset(),
        None,
    ),
    (
        "original saved and only a repeat",
        "partial",
        "orig-1",
        [SAVED, REJECTED],
        ONLY_REPEAT,
        "no_receipt",
    ),
]


@pytest.mark.parametrize(
    ("state", "original", "parts", "repeats", "expected"),
    [case[1:] for case in CASES],
    ids=[case[0] for case in CASES],
)
def test_where_an_email_stands(state, original, parts, repeats, expected):
    standing = email_standing(
        delivery(state, original), parts, lambda each: each.id in repeats
    )
    assert standing == expected


def test_a_repeat_is_only_looked_up_when_it_could_change_the_answer():
    asked: list[str] = []

    def is_repeat(each: EmailDeliveryPart) -> bool:
        asked.append(each.id)
        return False

    assert email_standing(delivery("captured"), [SAVED], is_repeat) is None
    assert asked == []
    assert email_standing(delivery("rejected"), [], is_repeat) == "no_receipt"
    assert asked == []
    assert email_standing(delivery("partial"), [SAVED, REJECTED], is_repeat) is None
    assert asked == [SAVED.id]


def test_the_row_says_what_the_email_saved_and_why_it_brought_nothing():
    """The delivery views read the standing, the saved count and the reason
    from one row; the reason is a code, present only with ``no_receipt``."""

    nothing = lambda each: False  # noqa: E731
    saved = email_row(delivery("captured"), [SAVED, OTHER_SAVED], nothing)
    assert (saved.standing, saved.saved_receipt_count, saved.no_receipt_reason) == (
        None,
        2,
        None,
    )
    # The repeat still counts as a file the email saved; the refused file names the cause.
    refused = email_row(
        delivery("partial"), [SAVED, REJECTED], lambda each: each.id in ONLY_REPEAT
    )
    assert (refused.standing, refused.saved_receipt_count, refused.no_receipt_reason) == (
        "no_receipt",
        1,
        "too_large",
    )
    # The email's own cause wins when it names one; "parts rejected" names none.
    blocked = replace(delivery("rejected"), error_code="email_sender_blocked")
    assert email_row(blocked, [], nothing).no_receipt_reason == "email_sender_blocked"
    parts_rejected = replace(delivery("captured"), error_code="email_parts_rejected")
    assert (
        email_row(parts_rejected, [part(state="rejected")], nothing).no_receipt_reason
        == "too_large"
    )
    assert email_row(delivery("captured"), [], nothing).no_receipt_reason == (
        "email_no_attachment"
    )
    assert email_row(parts_rejected, [], nothing).no_receipt_reason == (
        "email_no_attachment"
    )
    # Only a repeat was saved and nothing names a cause: the email's generic code.
    only_repeat = email_row(delivery("rejected"), [SAVED], lambda each: True)
    assert only_repeat.no_receipt_reason == "email_parts_rejected"
    assert email_row(delivery("received"), [], nothing).no_receipt_reason is None


@pytest.mark.parametrize(
    ("state", "original", "parts", "repeats", "expected"),
    [case[1:] for case in CASES],
    ids=[case[0] for case in CASES],
)
def test_the_standing_is_the_rows_standing(state, original, parts, repeats, expected):
    found = email_row(delivery(state, original), parts, lambda each: each.id in repeats)
    assert found.standing == expected
    assert (found.no_receipt_reason is not None) == (expected == "no_receipt")
