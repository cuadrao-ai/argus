from __future__ import annotations

from datetime import timedelta

from argus.domain.business.transactions import ActionTransaction
from argus.domain.ingestion.reconcile.matching import (
    MATCH_WINDOW_DAYS,
    compare,
    event_facts,
)
from argus.domain.ingestion.reconcile.model import ImportEvent


def candidate_ids(tx: ActionTransaction, event: ImportEvent) -> list[str]:
    links = tx.imports.links()
    facts = event_facts(event, tx.imports.observations(event.id), links)
    if facts.occurred_on is None:
        return []
    window = timedelta(days=MATCH_WINDOW_DAYS)
    found = []
    for candidate in tx.imports.nearby(
        facts.occurred_on - window, facts.occurred_on + window
    ):
        if candidate.id == event.id or candidate.state == "dismissed":
            continue
        candidate_facts = event_facts(
            candidate, tx.imports.observations(candidate.id), links
        )
        if compare(facts, candidate_facts) is not None:
            found.append(candidate.id)
    return sorted(found)[:20]
