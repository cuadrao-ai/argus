"""A receipt that repeats another one, decided by its read facts.

Two receipts are a possible repeat when the read merchant, date, amount and
currency are all known and all equal. The mark is the import event's own
``possible_duplicate`` attention, so it is durable, every reader sees it, and
approval stays closed until a person settles it. Intake marks only the newer
event, so a retried read keeps the original clean. Restoration also marks
open counterparts because both purchases are waiting for review again.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from argus.domain.business.contracts.facts import BusinessFacts, BusinessResolution, Known
from argus.domain.ingestion.reconcile import duplicates
from argus.domain.ingestion.reconcile.model import EventNotFound, ImportEvent, Observation
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


def evidence_signature(tx: ImportTx, event: ImportEvent) -> str:
    evidence = sorted(
        (
            {
                "id": o.id,
                "connection_id": o.connection_id,
                "fingerprint": o.fingerprint,
                "candidate": o.candidate,
            }
            for o in tx.observations(event.id)
            if o.live
        ),
        key=lambda item: item["id"],
    )
    payload = {"facts": event_key(event, tx.observations), "evidence": evidence}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def different_purchase(
    tx: ImportTx,
    event: ImportEvent,
    other: ImportEvent,
    source_signature: Callable[[str], str] | None = None,
) -> bool:
    for left, right in ((event, other), (other, event)):
        decision = left.resolution.get("different_purchases", {}).get(right.id)
        if decision is None:
            continue
        if decision.get("self") != evidence_signature(tx, left) or decision.get(
            "other"
        ) != evidence_signature(tx, right):
            continue
        if source_signature is not None and (
            decision.get("source_self") == source_signature(left.id)
            and decision.get("source_other") == source_signature(right.id)
        ):
            return True
    return False


def pending_duplicates(
    tx: ImportTx,
    event: ImportEvent,
    source_signature: Callable[[str], str] | None = None,
) -> tuple[str, ...]:
    """Keep existing warnings and reopen a decided pair when its evidence changes."""
    pending = set()
    for candidate_id in event.possible_duplicates:
        try:
            candidate = tx.event(candidate_id)
        except EventNotFound:
            continue
        if candidate.state in OPEN_OR_RECORDED:
            pending.add(candidate_id)
    decisions = event.resolution.get("different_purchases", {})
    key = event_key(event, tx.observations)
    for other_id in set(decisions) | pending:
        try:
            other = tx.event(other_id)
        except EventNotFound:
            continue
        if different_purchase(tx, event, other, source_signature):
            pending.discard(other.id)
        elif (
            other.id in decisions
            and other.state in OPEN_OR_RECORDED
            and key is not None
            and event_key(other, tx.observations) == key
        ):
            pending.add(other.id)
    return tuple(sorted(pending))


def flag_receipt_duplicates(
    tx: ImportTx,
    event_id: str,
    source_signature: Callable[[str], str] | None = None,
    *,
    symmetric: bool = False,
) -> tuple[str, ...]:
    """Mark ``event_id`` as a possible repeat of the other open or recorded
    events of this scope that share its read facts. Returns what it named."""

    event = tx.event(event_id)
    key = event_key(event, tx.observations)
    if key is None:
        return ()
    found = []
    for other in tx.events(OPEN_OR_RECORDED):
        if other.id == event.id or (
            not symmetric and event.id in other.possible_duplicates
        ):
            continue
        if event_key(other, tx.observations) == key and not different_purchase(
            tx, event, other, source_signature
        ):
            found.append(other.id)
    if not found:
        return ()
    flagged = duplicates.flag(
        event, set(found) | set(event.possible_duplicates) if symmetric else found
    )
    if event.attention == "ambiguous_match":
        # The import layer's bank-match warning outranks a repeat mark; both
        # are settled by a person, and the repeat is still recorded below.
        flagged = replace(flagged, attention="ambiguous_match")
    detail = {"basis": "read_facts", "fields": list(DUPLICATE_FIELDS)}
    if not symmetric or flagged.attention == "possible_duplicate":
        flagged = replace(flagged, attention_detail=detail)
    tx.put_event(flagged)
    if symmetric:
        for other_id in found:
            other = tx.event(other_id)
            if other.state != "open":
                continue
            reciprocal = duplicates.flag(
                other, (*other.possible_duplicates, event.id),
                ambiguous=other.attention == "ambiguous_match",
            )
            if reciprocal.attention == "possible_duplicate":
                reciprocal = replace(reciprocal, attention_detail=detail)
            if reciprocal != other:
                tx.put_event(
                    replace(
                        reciprocal,
                        version=other.version + 1,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
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
