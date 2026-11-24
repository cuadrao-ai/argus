"""Recover a human review's explicit fact and declaration edits from its saved command.

Audit snapshots stay untouched. Missing or older unrecognized evidence keeps
its existing history, rather than guessing what a person intended.
"""
import json
from typing import TYPE_CHECKING, Any, get_args
from uuid import UUID

from pydantic import ValidationError

from argus.domain.business.amount_inheritance import INHERITANCE, same_value
from argus.domain.business.contracts.actions import ReviewCommand, ReviewDraft
from argus.domain.business.contracts.dgii import SalePaymentForm
from argus.domain.business.contracts.facts import FiscalFacts

if TYPE_CHECKING:
    from argus.domain.business.contracts.dossier import DraftRevision, WebActionSource
    from argus.domain.business.contracts.facts import BusinessFacts


#: Marks review evidence that keeps a person's cleared answers as nulls. Older
#: evidence dropped every null, so there a cleared answer reads as omitted.
CLEARED_KEPT = "cleared_kept"
#: The review inputs where an explicit null clears a saved answer.
_CLEARABLE = ("purchase", "payment_split")


def review_evidence(command: ReviewCommand) -> dict[str, Any]:
    """The review command as its web action source records it."""
    data = command.model_dump(mode="json", exclude_none=True)
    for name in _CLEARABLE:
        answers = getattr(command.request, name)
        if answers is not None:
            data["request"][name] |= {field: None for field in answers.model_fields_set if getattr(answers, field) is None}
    return {**data, CLEARED_KEPT: True}


def legacy_evidence(data: dict[str, Any]) -> dict[str, Any]:
    """Review evidence as models have always read it: no marker, no kept nulls."""
    if not data.pop(CLEARED_KEPT, False):
        return data
    request = data.get("request") or {}
    for name in _CLEARABLE:
        if isinstance(request.get(name), dict):
            request[name] = {field: value for field, value in request[name].items() if value is not None}
    return data


def _saved_command(text: str) -> tuple[ReviewCommand, bool]:
    """The saved command, and whether its evidence kept cleared answers."""
    # Saved commands drop the nulls of a full fiscal snapshot. Restore only its
    # nullable required fields, then validate again.
    data = json.loads(text)
    kept = isinstance(data, dict) and bool(data.pop(CLEARED_KEPT, False))
    try:
        return ReviewCommand.model_validate(data), kept
    except ValidationError as error:
        for detail in error.errors():
            path = detail["loc"]
            if detail["type"] != "missing" or len(path) < 4 or path[:2] != ("request", "dgii") or path[2] not in {"fiscal", "declaration"}:
                raise
            snapshot = data["request"]["dgii"].get(path[2])
            if not isinstance(snapshot, dict):
                raise
            snapshot[path[-1]] = None
        return ReviewCommand.model_validate(data), kept


def human_review(revision: "DraftRevision", sources: dict[UUID, "WebActionSource"]) -> "DraftRevision":
    """The revision with the fields its person's saved command names. Both stay
    null without that one command."""
    commands = []
    if revision.actor.actor_kind == "member" and revision.reason is None:
        for source_id in revision.source_ids:
            source = sources.get(source_id)
            if source is None:
                continue
            try:
                command, kept = _saved_command(source.text)
            except (ValidationError, ValueError, TypeError):
                continue
            if command.draft_id == revision.draft_id and command.request.version == revision.version - 1:
                commands.append((command, kept))
    if len(commands) != 1:
        return revision
    [(command, kept)] = commands
    return revision.model_copy(update={
        "reviewed_fact_fields": _reviewed_facts(revision, command.request),
        "reviewed_declaration_fields": _reviewed_declaration(revision, command.request, kept),
    })


def _reviewed_facts(revision: "DraftRevision", request: ReviewDraft) -> tuple[str, ...]:
    """The facts the request names that changed. A fiscal review carries every
    fiscal fact, so only a changed one counts."""
    names = set(request.facts.model_fields_set) if request.facts is not None else set()
    if request.montos is not None:
        names.update(name for name in ("net_amount", "legal_tip") if getattr(request.montos, name) is not None)
    fiscal = {name for name in FiscalFacts.model_fields if name != "include_606"} if request.dgii is not None else set()

    def fact(facts: "BusinessFacts | None", name: str) -> object:
        if facts is None:
            return None
        return getattr(facts.fiscal, name, None) if name in fiscal else getattr(facts, name)

    return tuple(sorted(name for name in names | fiscal if fact(revision.before, name) != fact(revision.after, name)))


def _reviewed_declaration(revision: "DraftRevision", request: ReviewDraft, kept: bool) -> tuple[str, ...] | None:
    names = set()
    for answers in (request.purchase, request.payment_split):
        if answers is None:
            continue
        names.update(answers.model_fields_set)
        unnamed = set(type(answers).model_fields) - answers.model_fields_set
        if not kept and any(_cleared(revision, name) for name in unnamed):
            # An answer this older evidence omits may be one the person cleared.
            return None
    if request.sale_payment_form is not None:
        names.update(get_args(SalePaymentForm))
    if request.montos is not None:
        names.update(request.montos.override_inherited)
        names.update(request.montos.restore_inherited)
    if request.dgii is not None:
        sent = request.dgii.declaration
        fields = type(sent).model_fields.keys()
        names.update(fields - INHERITANCE.keys())
        # A linked value saved as sent may be the person's; one saved otherwise
        # followed its source.
        names.update(
            name for name in fields & INHERITANCE.keys()
            if same_value(name, getattr(sent, name), getattr(revision.after_dgii, name, None))
        )
    names.difference_update({"form", "category_suggested", "suggestion_sources"})
    return tuple(sorted(name for name in names if getattr(revision.before_dgii, name, None) != getattr(revision.after_dgii, name, None)))


def _cleared(revision: "DraftRevision", name: str) -> bool:
    return getattr(revision.before_dgii, name, None) is not None and getattr(revision.after_dgii, name, None) is None
