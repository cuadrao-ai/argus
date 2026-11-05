"""Approved match targets. Venta stays behind this catalog until that type lands."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID

from argus.domain.business.bank.model import MatchTarget, TargetKind


@dataclass(frozen=True)
class RecordedTarget:
    id: str
    kind: TargetKind
    amount: Decimal
    currency: str
    occurred_on: date
    merchant: str | None
    approved: bool = True


class StaticCatalog:
    def __init__(self, targets: tuple[RecordedTarget, ...] = ()) -> None:
        self.targets = targets

    def approved_targets(
        self,
        space_id: UUID,
        *,
        kind: TargetKind,
        period_start: date,
        period_end: date,
    ) -> tuple[MatchTarget, ...]:
        del space_id
        return tuple(
            target
            for target in self.targets
            if target.kind == kind
            and target.approved
            and period_start <= target.occurred_on <= period_end
        )


def receipt_target_from_event(event) -> RecordedTarget | None:  # noqa: ANN001
    """An accepted expense with known amount, currency, and date."""

    if getattr(event, "state", None) != "accepted":
        return None
    business = (getattr(event, "resolution", None) or {}).get("business")
    if not isinstance(business, dict):
        return None
    facts = business.get("facts")
    if not isinstance(facts, dict):
        return None
    if _known(facts.get("kind")) != "expense":
        return None
    amount = _known(facts.get("amount"))
    currency = _known(facts.get("currency"))
    occurred = _known(facts.get("occurred_on"))
    if not isinstance(amount, str) or not isinstance(currency, str):
        return None
    if not isinstance(occurred, str):
        return None
    try:
        parsed_amount = Decimal(amount)
        parsed_day = date.fromisoformat(occurred)
    except (InvalidOperation, ValueError):
        return None
    merchant = _known(facts.get("counterparty"))
    return RecordedTarget(
        id=str(event.id),
        kind="receipt",
        amount=parsed_amount,
        currency=currency,
        occurred_on=parsed_day,
        merchant=merchant if isinstance(merchant, str) else None,
        approved=True,
    )


def _known(fact: object) -> object:
    if isinstance(fact, dict) and fact.get("state") == "known":
        return fact.get("value")
    return None
