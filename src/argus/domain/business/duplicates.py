"""A receipt that repeats another one, decided by its read facts.

Two receipts are a possible repeat when the read merchant, date, amount and
currency are all known and all equal. The mark is the import event's own
``possible_duplicate`` attention, so it is durable, every reader sees it, and
approval stays closed until a person settles it. Only the newer event is
marked; an event that already names this one is left alone, so a retried
read of the original never turns both into duplicates of each other.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import date
from decimal import Decimal, InvalidOperation

from argus.domain.business.contracts.facts import BusinessFacts, BusinessResolution, Known
from argus.domain.ingestion.reconcile import duplicates
from argus.domain.ingestion.reconcile.model import ImportEvent, Observation
from argus.domain.ingestion.reconcile.store import ImportTx

DUPLICATE_FIELDS = ("counterparty", "occurred_on", "amount", "currency")
OPEN_OR_RECORDED = ("open", "accepting", "accepted")


def _norm(name: str, value: object) -> object | None:
    if value is None:
        return None
    if name == "amount":
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    if name == "occurred_on":
        return value.isoformat() if isinstance(value, date) else str(value)
    if name == "currency":
        return str(value).strip().upper()
    return str(value).strip().casefold() or None


def _business_key(facts: BusinessFacts) -> tuple | None:
    values = []
    for name in DUPLICATE_FIELDS:
        fact = getattr(facts, name)
        value = _norm(name, fact.value) if isinstance(fact, Known) else None
        if value is None:
            return None
        values.append(value)
    return tuple(values)


def _observed_key(observations: list[Observation]) -> tuple | None:
    live = [o for o in observations if o.live]
    if len(live) != 1:
        return None
    candidate = live[0].candidate
    values = []
    for name, source in zip(
        DUPLICATE_FIELDS, ("merchant", "occurred_on", "amount", "currency"), strict=False
    ):
        value = _norm(name, candidate.get(source))
        if value is None:
            return None
        values.append(value)
    return tuple(values)


def event_key(
    event: ImportEvent, observations: Callable[[str], list[Observation]]
) -> tuple | None:
    """The four read facts, from the Business draft when it has one, else from
    the one live observation; None while any of them is unknown."""

    business = event.resolution.get("business")
    if business is not None:
        return _business_key(BusinessResolution.model_validate(business).facts)
    return _observed_key(observations(event.id))


def flag_receipt_duplicates(tx: ImportTx, event_id: str) -> tuple[str, ...]:
    """Mark ``event_id`` as a possible repeat of the other open or recorded
    events of this scope that share its read facts. Returns what it named."""

    event = tx.event(event_id)
    key = event_key(event, tx.observations)
    if key is None:
        return ()
    found = []
    for other in tx.events(OPEN_OR_RECORDED):
        if other.id == event.id or event.id in other.possible_duplicates:
            continue
        if event_key(other, tx.observations) == key:
            found.append(other.id)
    if not found:
        return ()
    flagged = duplicates.flag(event, found)
    if event.attention == "ambiguous_match":
        # The import layer's bank-match warning outranks a repeat mark; both
        # are settled by a person, and the repeat is still recorded below.
        flagged = replace(flagged, attention="ambiguous_match")
    flagged = replace(
        flagged,
        attention_detail={"basis": "read_facts", "fields": list(DUPLICATE_FIELDS)},
    )
    tx.put_event(flagged)
    return tuple(flagged.possible_duplicates)


def events_of_connection(tx: ImportTx, connection_id: str) -> list[ImportEvent]:
    """The open events a document's observations belong to."""

    return [
        event
        for event in tx.events(("open",))
        if any(
            o.live and o.connection_id == connection_id for o in tx.observations(event.id)
        )
    ]
