"""Recover a human review's explicit declaration edits from its saved command.

Audit snapshots stay untouched. Missing or older unrecognized evidence keeps
its existing history, rather than guessing what a person intended.
"""
import json
from typing import TYPE_CHECKING, get_args
from uuid import UUID

from pydantic import ValidationError

from argus.domain.business.amount_inheritance import INHERITANCE
from argus.domain.business.contracts.actions import ReviewCommand
from argus.domain.business.contracts.dgii import SalePaymentForm

if TYPE_CHECKING:
    from argus.domain.business.contracts.dossier import DraftRevision, WebActionSource


def _saved_command(text: str) -> ReviewCommand:
    # WebActionSource stores commands with exclude_none=True. Restore only
    # nullable required fields in the full fiscal snapshot, then validate again.
    data = json.loads(text)
    try:
        return ReviewCommand.model_validate(data)
    except ValidationError as error:
        for detail in error.errors():
            path = detail["loc"]
            if detail["type"] != "missing" or len(path) < 4 or path[:2] != ("request", "dgii") or path[2] not in {"fiscal", "declaration"}:
                raise
            snapshot = data["request"]["dgii"].get(path[2])
            if not isinstance(snapshot, dict):
                raise
            snapshot[path[-1]] = None
        return ReviewCommand.model_validate(data)


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
            command = _saved_command(source.text)
        except (ValidationError, ValueError, TypeError):
            continue
        if command.draft_id == revision.draft_id and command.request.version == revision.version - 1:
            commands.append(command)
    if len(commands) != 1:
        return None
    request = commands[0].request
    names = set()
    if request.purchase is not None:
        names.update(request.purchase.model_fields_set)
    if request.payment_split is not None:
        names.update(request.payment_split.model_fields_set)
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
