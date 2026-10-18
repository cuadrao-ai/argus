"""Score a line against one approved target. No pair is confirmed here."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from argus.domain.business.bank.model import (
    MATCH_WINDOW_DAYS,
    BankLine,
    MatchTarget,
    ScoreParts,
    TargetKind,
)

_QUANTUM = Decimal("0.001")


def normalize_description(value: str) -> str:
    return " ".join(value.casefold().split())


def expected_kind(amount: Decimal) -> TargetKind | None:
    if amount < 0:
        return "receipt"
    if amount > 0:
        return "venta"
    return None


def _tokens(value: str | None) -> set[str]:
    if not value:
        return set()
    return {token for token in normalize_description(value).split(" ") if token}


def merchant_score(description: str, merchant: str | None) -> Decimal:
    left = _tokens(description)
    right = _tokens(merchant)
    if not left or not right:
        return Decimal("0.000")
    overlap = len(left & right)
    union = len(left | right)
    return (Decimal(overlap) / Decimal(union)).quantize(_QUANTUM)


def _date_score(left: date, right: date) -> Decimal | None:
    days = abs((left - right).days)
    if days > MATCH_WINDOW_DAYS:
        return None
    return (Decimal(MATCH_WINDOW_DAYS - days) / Decimal(MATCH_WINDOW_DAYS)).quantize(
        _QUANTUM
    )


def score_parts(line: BankLine, target: MatchTarget) -> ScoreParts | None:
    """None when the pair cannot be offered.

    Amount must be exact and in the same currency. The dates must fall
    inside the window. Merchant overlap only changes the stored parts.
    """

    if not target.approved:
        return None
    kind = expected_kind(line.amount)
    if kind is None or target.kind != kind:
        return None
    if line.currency != target.currency:
        return None
    if abs(line.amount) != abs(target.amount):
        return None
    dated = _date_score(line.occurred_on, target.occurred_on)
    if dated is None:
        return None
    return ScoreParts(
        amount_score=Decimal("1.000"),
        date_score=dated,
        merchant_score=merchant_score(line.description, target.merchant),
    )


def derive_confidence(parts: ScoreParts) -> Decimal:
    """The only function that turns stored parts into a confidence."""

    total = parts.amount_score + parts.date_score + parts.merchant_score
    return (total / Decimal(3)).quantize(_QUANTUM)
