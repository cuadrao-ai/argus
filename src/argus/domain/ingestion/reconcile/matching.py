"""Deciding which observations describe the same real-world event.

Pure functions over stored shapes, so the rules are testable without storage.
The rules (lane spec, "Deduplication rules"):

- One event holds at most one live observation per source kind. Two different
  observations from the same source are two different purchases unless the
  source itself linked them (``replaces_external_id``).
- Cross-source joining needs equal amount, known dates within the window, and
  no contradiction in currency, direction, account or card mask. Only a
  *strong* match (known equal currency on the same person-confirmed account)
  links automatically, and only when it is the single candidate.
- Equal amount and date alone never merge anything: weaker or multiple matches
  are surfaced for the person as possible duplicates.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from argus.domain.business.contracts.facts import BusinessResolution, legacy_projection
from argus.domain.ingestion.reconcile.model import ImportEvent, Observation

MATCH_WINDOW_DAYS = 5
_STATUS_RANK = {"posted": 0, "pending": 1, "unknown": 2}
_SOURCE_RANK = {"statement": 0, "plaid": 1, "gmail": 2, "shortcuts": 3}
ACTIVITY_EVIDENCE = frozenset({"transaction", "payment_notice", "unclassified"})
_KIND_FROM_HINT = {
    "expense": "expense",
    "fee": "expense",
    "income": "income",
    "refund": "refund",
    "card_payment": "card_payment",
    "transfer": "transfer",
}

Strength = Literal["strong", "weak"]


@dataclass(frozen=True)
class Facts:
    amount: Decimal | None
    currency: str | None
    direction: str | None
    occurred_on: date | None
    account_id: str | None
    mask: str | None
    kind: str | None


def account_key(candidate: Mapping[str, Any]) -> str | None:
    """Stable per-connection key for an account hint, most specific first."""

    account = candidate.get("account") or {}
    if account.get("external_account_id"):
        return "id:" + account["external_account_id"]
    if account.get("mask"):
        return "mask:" + account["mask"]
    if account.get("name"):
        return "name:" + " ".join(account["name"].casefold().split())
    return None


def observation_facts(
    observation: Observation, links: Mapping[tuple[str, str], str]
) -> Facts:
    c = observation.candidate
    key = account_key(c)
    amount = c.get("amount")
    occurred = c.get("occurred_on")
    if occurred is None and c.get("occurred_at"):
        occurred = str(c["occurred_at"])[:10]
    direction = c.get("direction")
    return Facts(
        amount=Decimal(amount) if amount is not None else None,
        currency=c.get("currency"),
        direction=None if direction in (None, "unknown") else direction,
        occurred_on=date.fromisoformat(occurred) if occurred else None,
        account_id=links.get((observation.connection_id, key)) if key else None,
        mask=(c.get("account") or {}).get("mask"),
        kind=_KIND_FROM_HINT.get(c.get("kind_hint") or ""),
    )


def primary(observations: Iterable[Observation]) -> Observation | None:
    """The most authoritative live observation: posted before pending, then
    statement, Plaid, Gmail, Shortcuts, then the most recent."""

    live = [o for o in observations if o.live]
    if not live:
        return None
    return min(
        live,
        key=lambda o: (
            _STATUS_RANK.get(o.candidate.get("status"), 3),
            _SOURCE_RANK.get(o.source, 9),
            -o.updated_at.timestamp(),
        ),
    )


def event_facts(
    event: ImportEvent,
    observations: list[Observation],
    links: Mapping[tuple[str, str], str],
) -> Facts:
    """What was recorded first (an accepted event's facts outlive its
    evidence, e.g. after a disconnect), then the person's resolution, then
    the most authoritative observation, then any live observation that knows
    a field the primary does not."""

    ordered = []
    first = primary(observations)
    if first is not None:
        ordered.append(observation_facts(first, links))
        ordered.extend(
            observation_facts(o, links) for o in observations if o.live and o is not first
        )
    r = {**event.resolution, **recorded_facts(event.resolution.get("accepted"))}
    business = event.resolution.get("business")
    projected = (
        legacy_projection(BusinessResolution.model_validate(business).facts)
        if business is not None
        else {}
    )

    def pick(name: str) -> Any:
        if name in projected:
            return projected[name]
        if r.get(name) is not None:
            return r[name]
        return next(
            (getattr(f, name) for f in ordered if getattr(f, name) is not None), None
        )

    amount = pick("amount")
    occurred = pick("occurred_on")
    return Facts(
        amount=Decimal(amount) if amount is not None else None,
        currency=pick("currency"),
        direction=pick("direction"),
        occurred_on=(
            date.fromisoformat(occurred) if isinstance(occurred, str) else occurred
        ),
        account_id=pick("account_id"),
        mask=pick("mask"),
        kind=pick("kind"),
    )


def recorded_facts(recorded: Mapping[str, Any] | None) -> dict[str, Any]:
    """Facts of the activity an event was accepted as (stored at acceptance)."""

    if not recorded:
        return {}
    return {
        k: v
        for k, v in {
            "amount": recorded.get("amount"),
            "currency": recorded.get("currency"),
            "occurred_on": recorded.get("occurred_on"),
            "account_id": recorded.get("account_id"),
            "kind": recorded.get("kind"),
        }.items()
        if v is not None
    }


def match_key(facts: Facts) -> tuple[Any, ...]:
    """The facts duplicate matching depends on."""

    return (
        facts.amount,
        facts.currency,
        facts.occurred_on,
        facts.account_id,
        facts.direction,
        facts.mask,
    )


def compare(new: Facts, existing: Facts) -> Strength | None:
    """How well ``new`` could be the same event as ``existing``; None if not.

    Strong needs amount, date window and currency known and equal, and both
    sides on the same person-confirmed account. Direction may be unknown on
    one side (a Wallet tap) but never contradictory. Anything less is weak.
    """

    if new.amount is None or existing.amount is None or new.amount != existing.amount:
        return None
    if new.occurred_on is None or existing.occurred_on is None:
        return None
    if abs((new.occurred_on - existing.occurred_on).days) > MATCH_WINDOW_DAYS:
        return None
    if new.direction and existing.direction and new.direction != existing.direction:
        return None
    if new.currency and existing.currency and new.currency != existing.currency:
        return None
    if new.account_id and existing.account_id and new.account_id != existing.account_id:
        return None
    if new.mask and existing.mask and new.mask != existing.mask:
        return None
    strong = (
        new.currency is not None
        and existing.currency is not None
        and new.account_id is not None
        and new.account_id == existing.account_id
    )
    return "strong" if strong else "weak"


@dataclass(frozen=True)
class Placement:
    event_id: str | None
    duplicates: tuple[str, ...]
    ambiguous: bool


def place(
    new: Facts,
    source: str,
    candidates: Iterable[tuple[ImportEvent, list[Observation], Facts]],
) -> Placement:
    """Where a new activity observation belongs among nearby events."""

    strong: list[str] = []
    weak: list[str] = []
    for event, observations, facts in candidates:
        if event.state == "dismissed":
            continue
        if any(o.live and o.source == source for o in observations):
            continue
        strength = compare(new, facts)
        if strength == "strong":
            strong.append(event.id)
        elif strength == "weak":
            weak.append(event.id)
    if len(strong) == 1 and not weak:
        return Placement(strong[0], (), False)
    return Placement(None, tuple(sorted(strong + weak)), len(strong) > 1)


def activity_matches(facts: Facts, activities: Iterable[Mapping[str, Any]]) -> list[str]:
    """Already-recorded activity (manual, voice, an earlier import) on the same
    account that could be this event: same amount, currency, window."""

    if facts.account_id is None or facts.amount is None or facts.occurred_on is None:
        return []
    found = []
    for activity in activities:
        if facts.currency and activity["currency"] != facts.currency:
            continue
        if not any(leg["account_id"] == facts.account_id for leg in activity["legs"]):
            continue
        if Decimal(activity["amount"]).copy_abs() != facts.amount:
            continue
        when = activity["occurred_at"]
        day = (
            when.date()
            if isinstance(when, datetime)
            else date.fromisoformat(str(when)[:10])
        )
        if abs((day - facts.occurred_on).days) <= MATCH_WINDOW_DAYS:
            found.append(activity["activity_id"])
    return found
