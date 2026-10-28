"""Which ledger actions the feed lists, for whom, and what each one names."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Literal, TypedDict
from uuid import UUID

from argus.domain.business.contracts.activity import (
    ActivityActor,
    ActivityItem,
    ActivityObject,
    ObjectKind,
)

Audience = Literal["member", "manager"]
Path = tuple[str, ...]


class LedgerRow(TypedDict):
    id: str
    created_at: datetime
    actor: Mapping[str, Any]
    command: Any
    outcome: Any


@dataclass(frozen=True)
class ActionSpec:
    audience: Audience = "member"
    #: The object's kind and the row paths that may hold its id; the first
    #: path holding a UUID wins.
    object: tuple[ObjectKind, tuple[Path, ...]] | None = None


_DRAFT = ("draft", (("outcome", "draft_id"), ("command", "draft_id")))
_PLANNED_DRAFT = (
    "draft",
    (("outcome", "draft_id"), ("command", "draft", "draft_id")),
)
_GRANT = ("grant", (("command", "grant_id"),))
_INVITE = ("invite", (("command", "invite_id"),))

CATALOG: Mapping[str, ActionSpec] = MappingProxyType(
    {
        "review_draft": ActionSpec(object=_DRAFT),
        "approve_expense": ActionSpec(object=_DRAFT),
        "approve_income": ActionSpec(object=_DRAFT),
        "approve_refund": ActionSpec(object=_DRAFT),
        "capture_note": ActionSpec(object=_DRAFT),
        "prepare_attachment": ActionSpec(object=_DRAFT),
        "rebind_attachment": ActionSpec(object=_DRAFT),
        "settle_remainder": ActionSpec(object=_DRAFT),
        "mark_personal": ActionSpec(object=_DRAFT),
        "decide_606": ActionSpec(object=_DRAFT),
        "resolve_duplicate": ActionSpec(object=_DRAFT),
        "edit_current_note": ActionSpec(object=_DRAFT),
        "append_supporting_file": ActionSpec(object=_DRAFT),
        "receipt_upload": ActionSpec(),
        "receipt_review": ActionSpec(),
        "receipt_confirm": ActionSpec(),
        "email_ai_consent_declined": ActionSpec(),
        "set_business_rnc": ActionSpec(),
        "business_propose_activity": ActionSpec(object=_PLANNED_DRAFT),
        "business_attach_source": ActionSpec(object=_PLANNED_DRAFT),
        "business_propose_allocation": ActionSpec(object=_PLANNED_DRAFT),
        "business_ask": ActionSpec(object=_PLANNED_DRAFT),
        "owner_grant": ActionSpec("manager", _GRANT),
        "grant_access": ActionSpec("manager", _GRANT),
        "invite_access": ActionSpec("manager", _INVITE),
        "accept_invite": ActionSpec("manager", _GRANT),
        "revoke_grant": ActionSpec("manager", _GRANT),
        "revoke_invite": ActionSpec("manager", _INVITE),
        "change_role": ActionSpec("manager", _GRANT),
    }
)

READ_MARKS: frozenset[str] = frozenset(
    {
        "access_seen",
        "business_read_context",
        "business_find_related",
        "business_explain_status",
    }
)


@dataclass(frozen=True)
class Visibility:
    """Which action names a reader's page may hold. A member's page holds only
    the names the catalog lists for members, so a new ledger action never
    reaches members before the catalog names it. A manager's page holds every
    name but the read marks, and one the catalog does not know shows as
    ``other``."""

    only: tuple[str, ...] | None
    hidden: tuple[str, ...]


def visibility(*, manager: bool) -> Visibility:
    if manager:
        return Visibility(only=None, hidden=tuple(sorted(READ_MARKS)))
    listed = (name for name, spec in CATALOG.items() if spec.audience == "member")
    return Visibility(only=tuple(sorted(listed)), hidden=())


def project(row: LedgerRow) -> ActivityItem:
    name = _at(row, ("command", "action"))
    spec = CATALOG.get(name) if isinstance(name, str) else None
    actor = row["actor"]
    return ActivityItem(
        id=row["id"],
        occurred_at=row["created_at"],
        actor=ActivityActor(display_name=actor["display_name"], kind=actor["actor_kind"]),
        action=name if spec is not None else "other",
        object=None if spec is None else _object(row, spec),
    )


def _object(row: LedgerRow, spec: ActionSpec) -> ActivityObject | None:
    if spec.object is None:
        return None
    kind, paths = spec.object
    for path in paths:
        try:
            return ActivityObject(kind=kind, id=UUID(str(_at(row, path))))
        except ValueError:
            continue
    return None


def _at(value: Any, path: Path) -> Any:
    for step in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(step)
    return value
