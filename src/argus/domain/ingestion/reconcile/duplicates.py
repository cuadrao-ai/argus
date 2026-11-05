"""Possible-duplicate links are symmetric and never dangle.

When an event may be the same purchase as another, both carry the warning,
so neither can be recorded in a batch while the question is open. Clearing
the question (the person says they differ, an event is merged away or
deleted) clears it on both sides.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from datetime import datetime

from argus.domain.ingestion.reconcile.model import EventNotFound, ImportEvent
from argus.domain.ingestion.reconcile.store import ImportTx

DUPLICATE_ATTENTION = ("possible_duplicate", "ambiguous_match")


def flag(
    event: ImportEvent, ids: Iterable[str], *, ambiguous: bool = False
) -> ImportEvent:
    """``event`` with ``ids`` as its possible duplicates (replacing the list)."""

    found = tuple(sorted({i for i in ids if i != event.id}))
    duplicate_warning = event.attention in (None, *DUPLICATE_ATTENTION)
    if found:
        # A source-change warning outranks a duplicate warning; keep it.
        attention = (
            ("ambiguous_match" if ambiguous else "possible_duplicate")
            if duplicate_warning
            else event.attention
        )
        return replace(event, possible_duplicates=found, attention=attention)
    return replace(
        event,
        possible_duplicates=(),
        attention=None if duplicate_warning else event.attention,
    )


def mirror(
    tx: ImportTx, event: ImportEvent, previous: Iterable[str], now: datetime
) -> None:
    """Make every listed event point back at ``event``; drop the back-links
    of events it no longer lists."""

    current = set(event.possible_duplicates)
    for other_id in set(previous) | current:
        try:
            other = tx.event(other_id)
        except EventNotFound:
            continue
        others = set(other.possible_duplicates)
        wanted = others | {event.id} if other_id in current else others - {event.id}
        if wanted != others:
            ambiguous = other.attention == "ambiguous_match"
            tx.put_event(_bump(flag(other, wanted, ambiguous=ambiguous), now))


def forget(tx: ImportTx, event: ImportEvent, now: datetime) -> None:
    """``event`` is going away or no longer in question: remove it from the
    lists that name it."""

    mirror(tx, replace(event, possible_duplicates=()), event.possible_duplicates, now)


def _bump(event: ImportEvent, now: datetime) -> ImportEvent:
    return replace(event, updated_at=now, version=event.version + 1)
