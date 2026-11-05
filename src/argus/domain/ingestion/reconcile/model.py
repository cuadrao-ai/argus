"""Stored shapes for reconciliation: events, observations, account links."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

EventState = Literal["open", "accepting", "accepted", "dismissed"]
# source_changed: a source revised an accepted event's money facts.
# source_removed: every source withdrew an accepted event.
# possible_duplicate: this event may be the same as another; the person decides.
# ambiguous_match: several events matched equally well, so none was linked.
Attention = Literal[
    "source_changed", "source_removed", "possible_duplicate", "ambiguous_match"
]
# Fields a person may set while reviewing; anything else comes from evidence.
RESOLVABLE = frozenset(
    {
        "kind",
        "account_id",
        "source_account_id",
        "destination_account_id",
        "amount",
        "currency",
        "occurred_on",
        "direction",
        "category_id",
        "source_id",
        "purchase_activity_id",
        "note",
        "time_zone",
    }
)


class ReconcileError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class EventNotFound(LookupError):
    pass


class StaleEvent(Exception):
    pass


@dataclass(frozen=True)
class Observation:
    """One source's view of one fact; ``candidate`` is the contract JSON."""

    id: str
    user_id: str
    event_id: str
    connection_id: str
    source: str
    external_id: str
    fingerprint: str
    candidate: dict[str, Any]
    # False once the source removed it or a newer observation superseded it.
    live: bool
    revisions: int
    first_seen_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ImportEvent:
    id: str
    user_id: str
    state: EventState
    evidence: str
    # Earliest activity date among observations; indexes the match window.
    anchor_on: date | None
    attention: Attention | None
    attention_detail: dict[str, Any] | None
    possible_duplicates: tuple[str, ...]
    resolution: dict[str, Any]
    activity_id: str | None
    accept_key: str | None
    created_at: datetime
    updated_at: datetime
    version: int


@dataclass(frozen=True)
class AccountLink:
    """A person-confirmed mapping from a source's account hint to an account."""

    user_id: str
    connection_id: str
    account_key: str
    account_id: str
    created_at: datetime


@dataclass
class SubmitTally:
    recorded: int = 0
    unchanged: int = 0
    withdrawn: int = 0
    touched: set[str] = field(default_factory=set)
