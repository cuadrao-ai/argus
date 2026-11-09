"""The facts a person approved and the documents they came from.

The approved revision is the latest draft revision at or below the version the
approval reviewed: approvals and settlements move the version without writing
a revision. Its facts are the approved facts, and each fact names the
documents it came from, so the record's evidence is read from the facts. A
revision that attaches no document (a note edit, the approval's own 606
declaration, its undo) changes no fact and so removes no evidence.
"""

from __future__ import annotations

from argus.domain.business.contracts.facts import BusinessFacts


def approved_revision_sql(draft: str, space: str, reviewed: str) -> str:
    """The query for the approved revision's ``version`` and ``after_facts``.

    Each argument is an SQL expression: a column of the outer query or a
    ``%s`` placeholder.
    """

    return (
        "select version,after_facts from public.business_draft_revisions"
        f" where draft_id={draft} and space_id={space} and version<={reviewed}"
        " order by version desc limit 1"
    )


def evidence(facts: BusinessFacts) -> tuple[str, ...]:
    """Every document the facts name, in first-named order."""

    named = [
        getattr(facts, name) for name in type(facts).model_fields if name != "fiscal"
    ]
    if facts.fiscal is not None:
        named += [getattr(facts.fiscal, name) for name in type(facts.fiscal).model_fields]
    return tuple(
        dict.fromkeys(str(source) for fact in named for source in fact.source_ids)
    )
