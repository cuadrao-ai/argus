"""Receipt attention after canonical draft projection. Seen state is per person.

The Bandeja's counts come from here and nowhere else: ``unread`` is new
activity this person has not opened; ``pending_review`` is every row the
Bandeja lists, opened or not, emails that are a row of their own included;
``ready_to_review`` is the "por revisar" number, the rows a person can review
now. The Bandeja and the Resumen all read them. Each receipt row also carries
``bandeja``, its membership in those buckets, from the same predicates the
counts sum, so a count always equals the number of rows flagged."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Iterable, Literal, Mapping, Sequence

from argus.domain.business.receipts import CLOSED


@dataclass(frozen=True)
class ReceiptActivity:
    state: Literal[
        "saved_unread", "reading", "ready", "read_failed", "blocked", "inactive"
    ]
    unread: bool
    completion_cursor: str | None

    def wire(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "unread": self.unread,
            "completion_cursor": self.completion_cursor,
        }


def project_activity(
    view: Mapping[str, Any],
    *,
    completion: str | None,
    seen: str | None,
    baseline: datetime | None = None,
    completed_at: datetime | None = None,
) -> ReceiptActivity:
    if view.get("email_original") or view["status"] in ("confirmed", "dismissed"):
        return ReceiptActivity("inactive", False, None)
    if view.get("read_pending"):
        return ReceiptActivity("reading", False, None)
    if view["status"] in ("saved", "queued"):
        return ReceiptActivity("saved_unread", True, None)
    if view["status"] == "needs_attention" and (
        view.get("preparable")
        or view.get("attention")
        in {
            "unreadable",
            "ai_unavailable",
            "interrupted",
            "outcome_unknown",
            "source_unavailable",
            "other",
        }
    ):
        return ReceiptActivity("read_failed", False, None)
    cursor = (
        hashlib.sha256(f"{view['id']}:{completion}".encode()).hexdigest()
        if completion
        else None
    )
    prior = completed_at or view["received_at"]
    if isinstance(prior, str):
        prior = datetime.fromisoformat(prior.replace("Z", "+00:00"))
    old = baseline is not None and prior <= baseline
    return ReceiptActivity(
        "ready", cursor is not None and seen != cursor and not old, cursor
    )


def acknowledge(
    activity: ReceiptActivity, cursor: str | None, seen: str | None
) -> str | None:
    if (
        activity.state == "ready"
        and cursor is not None
        and cursor == activity.completion_cursor
    ):
        return cursor
    return seen


def awaiting_owner(view: Mapping[str, Any]) -> bool:
    """A receipt row the Bandeja lists: neither closed nor the email itself,
    which is context for its attachment and never a second receipt."""

    return not view.get("email_original") and view["status"] not in CLOSED


def ready_to_review(view: Mapping[str, Any]) -> bool:
    """A receipt row a person can review now: the web's ``porRevisar``. Not one
    still being read, and not one the reader found unreadable."""

    return (
        awaiting_owner(view)
        and view["status"] not in ("queued", "preparing")
        and not view.get("read_pending")
        and not still_reading(view)
        and view.get("attention") != "unreadable"
    )


def needs_attention(view: Mapping[str, Any]) -> bool:
    """A receipt row that needs the person to fix something: "con problema"."""

    return awaiting_owner(view) and view["status"] == "needs_attention"


def still_reading(view: Mapping[str, Any]) -> bool:
    """A receipt row being read now: "leyendo". Its projected activity says so."""

    return awaiting_owner(view) and (view.get("activity") or {}).get("state") == "reading"


#: The Bandeja's buckets by their wire name. ``bandeja`` flags a row with them
#: and the counts sum them, so each count equals the rows flagged.
BANDEJA: dict[str, Callable[[Mapping[str, Any]], bool]] = {
    "por_revisar": ready_to_review,
    "con_problema": needs_attention,
    "leyendo": still_reading,
}


def bandeja(view: Mapping[str, Any]) -> dict[str, bool]:
    """Which Bandeja buckets this receipt row sits in. A closed row and the
    email itself sit in none."""

    return {name: predicate(view) for name, predicate in BANDEJA.items()}


def closed_as(view: Mapping[str, Any], status: str) -> bool:
    """A receipt the Bandeja no longer lists because it ended as ``status``; the
    email itself never counts as a receipt."""

    return not view.get("email_original") and view["status"] == status


def inbox_counts(
    views: Iterable[Mapping[str, Any]],
    notes: int = 0,
    emails: Sequence[str] = (),
    por_igualar: int | None = None,
) -> dict[str, int | None]:
    """What waits for a person in the Bandeja: every receipt row it lists plus
    ``notes``, the saved notes awaiting review that no receipt carries, plus
    ``emails``, the standing of each email that is a row of its own. An email
    still being read waits like a receipt being read; one that brought no
    receipt also needs attention. ``ready_to_review_count`` is the receipts
    ready for review plus those notes; an email is never ready to review.
    ``por_igualar_count`` is the Transacciones movements and documents still
    to igualar, or None while bank matching is off. ``confirmed_count`` and
    ``dismissed_count`` are the receipts that left the Bandeja each way, so a
    reader of the inbox view knows what it does not list."""

    rows = list(views)
    pending = [view for view in rows if awaiting_owner(view)]
    return {
        "pending_review_count": len(pending) + notes + len(emails),
        "ready_to_review_count": sum(map(BANDEJA["por_revisar"], pending)) + notes,
        "needs_attention_count": emails.count("no_receipt")
        + sum(map(BANDEJA["con_problema"], pending)),
        "por_igualar_count": por_igualar,
        "confirmed_count": sum(closed_as(view, "confirmed") for view in rows),
        "dismissed_count": sum(closed_as(view, "dismissed") for view in rows),
    }


def aggregate_activity(
    views: Iterable[Mapping[str, Any]], reading_emails: int = 0
) -> dict[str, Any]:
    """Over projected receipt views (each carrying its ``activity``).
    ``reading_emails``: emails still being read count with receipts being read."""

    rows = list(views)
    reading = sum(map(BANDEJA["leyendo"], rows)) + reading_emails
    unread = sum(bool(row["activity"]["unread"]) for row in rows)
    return {
        "reading_count": reading,
        "unread_count": unread,
        "presentation": "working" if reading else "unread" if unread else "none",
    }
