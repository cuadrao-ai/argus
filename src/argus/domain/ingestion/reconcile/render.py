"""Review-queue projection: what a person sees for one import event.

Evidence and conclusions stay apart: ``facts`` is the current best reading,
``observations`` keep each source's own words, and ``unresolved`` lists what
the person still has to supply before anything can be recorded.
"""

from __future__ import annotations

from typing import Any

from argus.domain.ingestion.reconcile.matching import (
    ACTIVITY_EVIDENCE,
    Facts,
    primary,
)
from argus.domain.ingestion.reconcile.model import ImportEvent, Observation
from argus.domain.recording.money_schemas import DESTINATION_ELIGIBILITY

# Stored on the event for recovery and matching, not person-supplied values.
_INTERNAL = frozenset({"accepted", "accepted_request", "pending_request", "reopened"})
_UNCERTAIN_TO_FACT = {
    "amount": "amount",
    "currency": "currency",
    "occurred_on": "occurred_on",
    "direction": "direction",
    "account": "account_id",
    "kind": "kind",
}


def proposed_kind(facts: Facts) -> str | None:
    if facts.kind:
        return facts.kind
    return {"outflow": "expense", "inflow": "income"}.get(facts.direction or "")


def counterpart(direction: str | None) -> str:
    """For a two-account kind, the leg the person must choose. The observed
    account is the destination when money arrived in it (a card payment seen
    on the card, a transfer seen on the receiving account), else the source."""

    return "source_account_id" if direction == "inflow" else "destination_account_id"


def unresolved(
    event: ImportEvent, observations: list[Observation], facts: Facts
) -> list[str]:
    if event.evidence not in ACTIVITY_EVIDENCE:
        return []
    missing = {
        name
        for name, value in (
            ("amount", facts.amount),
            ("currency", facts.currency),
            ("occurred_on", facts.occurred_on),
            ("account_id", facts.account_id),
            ("kind", proposed_kind(facts)),
        )
        if value is None
    }
    if event.evidence == "unclassified" and not event.resolution.get("kind"):
        missing.add("kind")
    kind = event.resolution.get("kind") or proposed_kind(facts)
    if kind in DESTINATION_ELIGIBILITY:
        other = counterpart(facts.direction)
        if not event.resolution.get(other):
            missing.add(other)
    first = primary(observations)
    if first is not None:
        for field in first.candidate.get("uncertain") or ():
            fact = _UNCERTAIN_TO_FACT.get(field, field)
            if event.resolution.get(fact) is None and fact != "merchant":
                missing.add(fact)
    return sorted(missing)


def observation_view(o: Observation) -> dict[str, Any]:
    c = o.candidate
    account = c.get("account") or {}
    source = c.get("source") or {}
    return {
        "id": o.id,
        "source": o.source,
        "connection_id": o.connection_id,
        "external_id": o.external_id,
        "evidence": c.get("evidence"),
        "status": c.get("status"),
        "live": o.live,
        "revisions": o.revisions,
        "observed_at": source.get("observed_at"),
        "occurred_on": c.get("occurred_on"),
        "posted_on": c.get("posted_on"),
        "due_on": c.get("due_on"),
        "amount": c.get("amount"),
        "currency": c.get("currency"),
        "direction": c.get("direction"),
        "merchant": c.get("merchant"),
        "description": c.get("description"),
        "excerpt": c.get("excerpt"),
        "balance_scope": c.get("balance_scope"),
        "institution": account.get("institution"),
        "account_name": account.get("name"),
        "account_mask": account.get("mask"),
        "attachments": [
            {k: a.get(k) for k in ("media_type", "size_bytes", "sha256", "filename")}
            for a in c.get("attachments") or ()
        ],
        "redacted": bool(c.get("redacted")),
    }


def event_view(
    event: ImportEvent,
    observations: list[Observation],
    facts: Facts,
    *,
    existing_activity_matches: list[str],
    recorded_duplicates: list[str],
    account_shared: bool | None,
) -> dict[str, Any]:
    return {
        "id": event.id,
        "state": event.state,
        "evidence": event.evidence,
        "version": event.version,
        "attention": event.attention,
        "attention_detail": event.attention_detail,
        "possible_duplicates": list(event.possible_duplicates),
        "existing_activity_matches": existing_activity_matches,
        "recorded_duplicates": recorded_duplicates,
        "activity_id": event.activity_id,
        "facts": {
            "amount": str(facts.amount) if facts.amount is not None else None,
            "currency": facts.currency,
            "direction": facts.direction,
            "occurred_on": facts.occurred_on.isoformat() if facts.occurred_on else None,
            "account_id": facts.account_id,
            "kind": proposed_kind(facts),
        },
        "resolution": {k: v for k, v in event.resolution.items() if k not in _INTERNAL},
        "unresolved": unresolved(event, observations, facts),
        "account_shared_with_household": account_shared,
        "observations": [observation_view(o) for o in observations],
        "created_at": event.created_at,
        "updated_at": event.updated_at,
    }
