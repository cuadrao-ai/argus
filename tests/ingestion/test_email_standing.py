"""Where an email stands in the Bandeja. The cases mirror the web's own test of
the same rule, plus the one fact only the server sees: a saved original."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from argus.domain.ingestion.email_intake.models import EmailDelivery, EmailDeliveryPart
from argus.domain.ingestion.email_intake.standing import email_standing

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
