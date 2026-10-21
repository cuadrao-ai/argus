"""The purchases a credit note may refund: the dossier's ``refund_candidates``.
One rule, on the server: the same approved records the 606 validation reads
as originals, narrowed the way that validation will accept them."""

from __future__ import annotations

from datetime import date
from typing import Callable, Iterable

from argus.domain.business.contracts.dossier import RefundCandidate
from argus.domain.business.contracts.facts import BusinessFacts, Known
from argus.domain.business.dgii_validation import FiscalRecord, credit_note
from argus.domain.business.fiscal_identity import normalized_taxpayer_id

#: A credit note refunds a purchase of the 30 days before it (the 606 rule).
WINDOW_DAYS = 30
#: The most recent candidates the dossier carries; the picker stays short.
LIMIT = 20


def fiscal_number(facts: BusinessFacts) -> str | None:
    if facts.fiscal is None:
        return None
    for fact in (facts.fiscal.ecf, facts.fiscal.ncf):
        if isinstance(fact, Known):
            return fact.value
    return None


def could_refund(facts: BusinessFacts) -> bool:
    """A draft that may name an original purchase: a refund, or a document
    whose fiscal number is a credit note, dated and in a known currency."""

    kind = facts.kind.value if isinstance(facts.kind, Known) else None
    return (
        (kind == "refund" or credit_note(fiscal_number(facts)))
        and isinstance(facts.occurred_on, Known)
        and isinstance(facts.currency, Known)
    )


def refund_candidates(
    facts: BusinessFacts, records: Callable[[], Iterable[FiscalRecord]]
) -> tuple[RefundCandidate, ...]:
    """Approved expenses in the draft's currency, within the 30 days up to its
    date, from the draft's supplier when its RNC is known, and not paid from
    the owner's own money (the money write refuses to refund those); newest
    first, at most ``LIMIT``. Empty when the draft could not refund anything,
    and then ``records`` is never read."""

    if not could_refund(facts):
        return ()
    day: date = facts.occurred_on.value
    currency = facts.currency.value
    supplier = (
        normalized_taxpayer_id(facts.fiscal.rnc.value)
        if facts.fiscal is not None and isinstance(facts.fiscal.rnc, Known)
        else None
    )
    found = [
        record
        for record in records()
        if record.kind == "expense"
        and not record.owner_funded
        and record.currency == currency
        and 0 <= (day - record.occurred_on).days <= WINDOW_DAYS
        and (supplier is None or normalized_taxpayer_id(_rnc(record.facts)) == supplier)
    ]
    found.sort(key=lambda record: (record.occurred_on, record.activity_id), reverse=True)
    return tuple(
        RefundCandidate(
            id=record.activity_id,
            merchant=record.facts.counterparty.value
            if isinstance(record.facts.counterparty, Known)
            else None,
            occurred_on=record.occurred_on,
            amount=record.amount,
            currency=record.currency,
        )
        for record in found[:LIMIT]
    )


def _rnc(facts: BusinessFacts) -> str | None:
    if facts.fiscal is not None and isinstance(facts.fiscal.rnc, Known):
        return facts.fiscal.rnc.value
    return None
