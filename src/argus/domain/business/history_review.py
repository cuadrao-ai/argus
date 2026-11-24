"""Recover a human review's explicit declaration edits from its saved command.

Audit snapshots stay untouched. Missing or older unrecognized evidence keeps
its existing history, rather than guessing what a person intended.
"""
import json
from typing import TYPE_CHECKING, Any, get_args
from uuid import UUID

from pydantic import ValidationError

from argus.domain.business.amount_inheritance import INHERITANCE
from argus.domain.business.contracts.actions import ReviewCommand
from argus.domain.business.contracts.dgii import SalePaymentForm

if TYPE_CHECKING:
    from argus.domain.business.contracts.dossier import DraftRevision, WebActionSource


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


def reviewed_declaration_fields(
    revision: "DraftRevision", sources: dict[UUID, "WebActionSource"]
) -> tuple[str, ...] | None:
    if revision.actor.actor_kind != "member" or revision.reason is not None:
        return None
    commands = []
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
        return None
    [(command, kept)] = commands
    request = command.request
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
        # Current fiscal editors name links they override or restore. An older
        # full declaration without that evidence is ambiguous.
        if request.montos is None and revision.before is not None and revision.before.fiscal == revision.after.fiscal:
            return None
        names.update(set(type(request.dgii.declaration).model_fields) - INHERITANCE.keys())
    names.difference_update({"form", "category_suggested", "suggestion_sources"})
    return tuple(sorted(name for name in names if getattr(revision.before_dgii, name, None) != getattr(revision.after_dgii, name, None)))


def _cleared(revision: "DraftRevision", name: str) -> bool:
    return getattr(revision.before_dgii, name, None) is not None and getattr(revision.after_dgii, name, None) is None
