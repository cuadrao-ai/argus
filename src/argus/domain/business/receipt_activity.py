"""Receipt attention after canonical draft projection. Seen state is per person."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Literal, Mapping


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


def aggregate_activity(items: Iterable[ReceiptActivity]) -> dict[str, Any]:
    rows = list(items)
    reading = sum(row.state == "reading" for row in rows)
    unread = sum(row.unread for row in rows)
    return {
        "reading_count": reading,
        "unread_count": unread,
        "presentation": "working" if reading else "unread" if unread else "none",
    }
