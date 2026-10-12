"""One receipt's review, composed from facts other owners already hold.

The draft owns capture and preparation status, the extraction batch owns the
immutable evidence and whether the document is a receipt, and the import event
owns the editable proposal and its link to recorded activity. Nothing here
stores a copy of any of them.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from functools import cache
from typing import Any, Literal, get_args

from argus.domain.ingestion.documents.models import (
    RECEIPT_PURCHASE_AMBIGUOUS,
    DocumentDraft,
    DraftStatus,
    ExtractionBatch,
)
from argus.domain.ingestion.documents.service import entered_by_owner, owner_entry_id
from argus.domain.ingestion.documents.store import DocumentStore
from argus.domain.ingestion.reconcile.matching import ACTIVITY_EVIDENCE
from argus.domain.ingestion.reconcile.model import EventState
from argus.domain.ingestion.reconcile.recording import missing_fields, recorded_note
from argus.domain.ingestion.reconcile.store import ImportTx

ReceiptStatus = DraftStatus | Literal["confirmed", "dismissed"]
# Why a receipt has no single purchase to review yet.
Blocker = Literal[
    "not_prepared",
    "receipt_purchase_ambiguous",
    "no_purchase_found",
    "several_purchases_found",
    "possible_duplicate",
]
# The import event warnings that mean "this may be a purchase already saved".
DUPLICATE_WARNINGS = ("possible_duplicate", "ambiguous_match")
# The import event states ``receipt_review`` reads; list events with these.
RECEIPT_EVENT_STATES: tuple[EventState, ...] = get_args(EventState)
_EVENT_STATUS: dict[str, ReceiptStatus] = {
    "accepted": "confirmed",
    "dismissed": "dismissed",
}


@dataclass(frozen=True)
class ReceiptFields:
    """The proposal the person reviews.

    ``note`` is what ``accept`` records as the activity note: the person's
    note, else the merchant on the first live observation of the event. ``amount`` is the normalized
    decimal string import events carry, so compare it by value.
    """

    note: str | None
    occurred_on: str | None
    amount: str | None
    currency: str | None
    category_id: str | None
    account_id: str | None


@dataclass(frozen=True)
class ReadPurchase:
    """An import event a preparation read from the document."""

    event_id: str
    version: int
    state: str


@dataclass(frozen=True)
class ReceiptReview:
    receipt_id: str
    status: ReceiptStatus
    error_code: str | None
    fields: ReceiptFields | None
    # Fields the person must still supply. Empty means the fields are complete,
    # not that accept will succeed: preview still checks the request.
    missing: tuple[str, ...]
    blocker: Blocker | None
    evidence: dict[str, Any] | None
    event_id: str | None
    event_version: int | None
    expense_id: str | None
    # Purchases read from the document beside the owner's entry. Once the
    # owner enters the receipt by hand, none of them can become its expense.
    read_purchases: tuple[ReadPurchase, ...] = ()
    # The purchase under review is the one the owner entered by hand.
    owner_entry: bool = False
    # The receipt this one may repeat; set with the ``possible_duplicate`` blocker.
    duplicate_of: str | None = None


def _is_receipt(batch: ExtractionBatch | None) -> bool:
    return batch is not None and batch.receipt is not None


def _from_receipt(
    o: Mapping[str, Any],
    is_receipt: Callable[[str], bool],
    entry_id: Callable[[str], str | None],
) -> bool:
    """The one test for an observation that a receipt document still holds:
    read from a receipt, or the purchase its owner entered by hand."""

    connection_id = o["connection_id"]
    return bool(
        o["live"]
        and o["source"] == "statement"
        and (is_receipt(connection_id) or o["external_id"] == entry_id(connection_id))
    )


def receipt_review(
    draft: DocumentDraft,
    batch: ExtractionBatch | None,
    events: Iterable[dict[str, Any]],
) -> ReceiptReview:
    """``events`` are import event views listed with ``RECEIPT_EVENT_STATES``."""

    entry = owner_entry_id(draft.sha256)

    def this_receipt(connection_id: str) -> bool:
        return connection_id == draft.connection_id and _is_receipt(batch)

    def this_entry(connection_id: str) -> str | None:
        return entry if connection_id == draft.connection_id else None

    def held(event: dict[str, Any], external_id: str | None) -> bool:
        return any(
            o["live"]
            and o["connection_id"] == draft.connection_id
            and (external_id is None or o["external_id"] == external_id)
            for o in event["observations"]
        )

    activity = [e for e in events if e["evidence"] in ACTIVITY_EVIDENCE]
    entered = [e for e in activity if held(e, entry)]
    read = tuple(
        ReadPurchase(e["id"], e["version"], e["state"])
        for e in activity
        if held(e, None) and e not in entered
    )
    purchases = entered or [
        event
        for event in activity
        if any(_from_receipt(o, this_receipt, this_entry) for o in event["observations"])
    ]
    blocker: Blocker | None = None
    if batch is None or (not entered and not purchases and _handoff_failed(draft, batch)):
        # No read yet, or a read that was saved but never became a record
        # (the hand-off refused or failed): another preparation can finish it.
        blocker = "not_prepared"
    elif entered:
        blocker = None
    elif any(issue.code == RECEIPT_PURCHASE_AMBIGUOUS for issue in batch.issues):
        blocker = RECEIPT_PURCHASE_AMBIGUOUS
    elif not purchases:
        blocker = "no_purchase_found"
    elif len(purchases) > 1:
        blocker = "several_purchases_found"
    evidence = (
        None
        if batch is None
        else {
            "receipt": batch.receipt.model_dump(mode="json") if batch.receipt else None,
            "issues": [issue.code for issue in batch.issues],
        }
    )
    if blocker is not None:
        return ReceiptReview(
            receipt_id=draft.connection_id,
            status=draft.status,
            error_code=draft.error_code,
            fields=None,
            missing=(),
            blocker=blocker,
            evidence=evidence,
            event_id=None,
            event_version=None,
            expense_id=None,
            read_purchases=read,
        )
    [event] = purchases
    facts = event["facts"]
    # The owner's entry after a read replaces what the read could not settle;
    # the read's findings stay in the batch and in ``evidence``.
    after_read = bool(entered) and not entered_by_owner(batch)
    status = _EVENT_STATUS.get(
        event["state"], "review_ready" if after_read else draft.status
    )
    # A purchase the import layer marked as a possible repeat of another one
    # is shown with what was read, and blocked until a person settles it.
    repeated = event["state"] == "open" and event.get("attention") in DUPLICATE_WARNINGS
    return ReceiptReview(
        receipt_id=draft.connection_id,
        status=status,
        error_code=None if after_read else draft.error_code,
        fields=ReceiptFields(
            note=recorded_note(event),
            occurred_on=facts["occurred_on"],
            amount=facts["amount"],
            currency=facts["currency"],
            category_id=event["resolution"].get("category_id"),
            account_id=facts["account_id"],
        ),
        missing=tuple(missing_fields(event)),
        blocker="possible_duplicate" if repeated else None,
        evidence=evidence,
        event_id=event["id"],
        event_version=event["version"],
        expense_id=event["activity_id"],
        read_purchases=read,
        owner_entry=bool(entered),
        duplicate_of=_receipt_of(events, tuple(event.get("possible_duplicates") or ()))
        if repeated
        else None,
    )


def _handoff_failed(draft: DocumentDraft, batch: ExtractionBatch) -> bool:
    """The draft carries an error the read itself did not produce."""

    code = draft.error_code
    return code is not None and not any(issue.code == code for issue in batch.issues)


def _receipt_of(
    events: Iterable[dict[str, Any]], event_ids: tuple[str, ...]
) -> str | None:
    """The receipt (connection) behind the first listed event, when it has one."""

    for other in events:
        if other["id"] in event_ids:
            for observation in other["observations"]:
                if observation.get("connection_id"):
                    return observation["connection_id"]
    return None


def receipt_ids(
    tx: ImportTx,
    documents: DocumentStore,
    user_id: str,
    activity_ids: Iterable[str],
) -> dict[str, str]:
    """Activity id to the receipt (document connection) it was recorded from.

    An activity recorded by hand, evidenced by no receipt or by several, or
    whose receipt was disconnected, has no entry.
    """

    @cache
    def is_receipt(connection_id: str) -> bool:
        return _is_receipt(documents.get(user_id=user_id, connection_id=connection_id))

    @cache
    def entry_id(connection_id: str) -> str | None:
        draft = documents.draft(user_id=user_id, connection_id=connection_id)
        return owner_entry_id(draft.sha256) if draft is not None else None

    events = tx.activity_links()
    found = {}
    for activity_id in activity_ids:
        event_id = events.get(activity_id)
        if event_id is None:
            continue
        held = {
            o.connection_id
            for o in tx.observations(event_id)
            if _from_receipt(vars(o), is_receipt, entry_id)
        }
        if len(held) == 1:
            found[activity_id] = held.pop()
    return found
