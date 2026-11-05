"""The marks a record carries, read one way for every view: Personal, who
marked it when that was not the owner, the fiscal number, the 606 answer and
sin comprobante.
Receipt lists, expense lists and the record itself all take them from here."""

from __future__ import annotations

from typing import Any

from argus.domain.business.contracts.facts import (
    BusinessFacts,
    fiscal_inclusion,
    fiscal_question_applies,
    fiscal_value,
    is_personal,
    is_sin_comprobante,
)

# The people behind the latest revision that changed business_share (who
# marked or unmarked Personal) and the latest that changed fiscal.include_606
# (who answered the 606). Joined beside an import event aliased ``e``.
MARKER_JOIN = (
    " left join lateral ("
    "   select r.actor->>'actor_id' as marker_id, r.actor->>'display_name' as marker_name"
    "   from public.business_draft_revisions r"
    "   where r.space_id=e.owner_space_id and r.draft_id=e.id"
    "   and (r.before_facts->'business_share') is distinct from (r.after_facts->'business_share')"
    "   order by r.version desc limit 1"
    " ) m on true"
    " left join lateral ("
    "   select r.actor->>'display_name' as answer_name"
    "   from public.business_draft_revisions r"
    "   where r.space_id=e.owner_space_id and r.draft_id=e.id"
    "   and (r.before_facts->'fiscal'->'include_606')"
    "   is distinct from (r.after_facts->'fiscal'->'include_606')"
    "   order by r.version desc limit 1"
    " ) a on true"
)
MARKER_COLUMNS = " m.marker_id, m.marker_name, a.answer_name"


def record_marks(facts: BusinessFacts, row: dict[str, Any], owner_id: str) -> dict:
    """The wire marks of one record from its facts and its MARKER_JOIN columns.
    ``personal_marked_by`` names whoever last changed the mark only while the
    record is Personal and that person is not the Business owner;
    ``include_606_by`` names whoever gave the 606 answer while it applies.
    ``fiscal_known`` says the record's facts exist, so an empty
    ``fiscal_value`` means no fiscal number rather than nothing read yet."""

    personal = is_personal(facts)
    marker = row.get("marker_id")
    answer = fiscal_inclusion(facts)
    return {
        "fiscal_known": True,
        "personal": personal,
        "personal_marked_by": row.get("marker_name")
        if personal and marker and marker != str(owner_id)
        else None,
        "fiscal_value": fiscal_value(facts),
        "include_606": answer,
        "include_606_by": row.get("answer_name") if answer is not None else None,
        "sin_comprobante": is_sin_comprobante(facts),
    }


def fiscal_inclusion_available(tx, facts: BusinessFacts, state: str) -> bool:  # noqa: ANN001
    """Whether the caller may answer the 606 question on this draft now: the
    gate ``decide_606`` enforces, read without acting. A member holding
    prepare who is not the owner, on an open or accepted draft, when the
    question applies to its facts."""

    actor = tx.context.actor
    return (
        "prepare" in tx.authorization.capabilities
        and actor.actor_kind == "member"
        and str(actor.actor_id) != str(tx.context.owner_id)
        and state in ("open", "accepted")
        and fiscal_question_applies(facts)
    )


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
