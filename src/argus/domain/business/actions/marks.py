"""The marks a record carries, read one way for every view: Personal, who
marked it when that was not the owner, the fiscal number and the 606 answer.
Receipt lists, expense lists and the record itself all take them from here."""

from __future__ import annotations

from typing import Any

from argus.domain.business.contracts.facts import (
    BusinessFacts,
    fiscal_inclusion,
    fiscal_value,
    is_personal,
)

# The person behind the latest revision that changed business_share: who
# marked or unmarked Personal. Joined beside an import event aliased ``e``.
MARKER_JOIN = (
    " left join lateral ("
    "   select r.actor->>'actor_id' as marker_id, r.actor->>'display_name' as marker_name"
    "   from public.business_draft_revisions r"
    "   where r.space_id=e.owner_space_id and r.draft_id=e.id"
    "   and (r.before_facts->'business_share') is distinct from (r.after_facts->'business_share')"
    "   order by r.version desc limit 1"
    " ) m on true"
)
MARKER_COLUMNS = " m.marker_id, m.marker_name"


def record_marks(facts: BusinessFacts, row: dict[str, Any], owner_id: str) -> dict:
    """The wire marks of one record from its facts and its MARKER_JOIN columns.
    ``personal_marked_by`` names whoever last changed the mark only while the
    record is Personal and that person is not the Business owner."""

    personal = is_personal(facts)
    marker = row.get("marker_id")
    return {
        "personal": personal,
        "personal_marked_by": row.get("marker_name")
        if personal and marker and marker != str(owner_id)
        else None,
        "fiscal_value": fiscal_value(facts),
        "include_606": fiscal_inclusion(facts),
    }


def draft_marks(tx, draft_id: Any, facts: BusinessFacts) -> dict:  # noqa: ANN001
    """The marks of one draft, read through the same join the lists use."""

    rows = tx.rows(
        "select"
        + MARKER_COLUMNS
        + " from public.financial_import_events e"
        + MARKER_JOIN
        + " where e.id=%s and e.owner_space_id=%s",
        (str(draft_id), tx.context.actor.space_id),
    )
    return record_marks(facts, rows[0] if rows else {}, tx.context.owner_id)
