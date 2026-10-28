"""Which events the feed lists, for whom, where each one belongs, and what each
one names. The catalog is the one owner of an action's area, group, audience,
object and typed detail, so filters, counts and rows agree."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Literal, TypedDict
from uuid import UUID

from argus.domain.business.contracts.activity import (
    ActionGroup,
    ActivityActor,
    ActivityFilters,
    ActivityItem,
    ActivityObject,
    Area,
    Membership,
    ObjectKind,
)
from argus.domain.business.contracts.authority import ActorKind
from argus.domain.business.roles import BusinessRole

Audience = Literal["member", "manager"]
Path = tuple[str, ...]
Detail = Literal["role", "personal", "include"]


class EventRow(TypedDict):
    """One row of the feed query, from the ledger or a derived source."""

    id: str
    created_at: datetime
    actor_key: str | None
    actor_kind: ActorKind | None
    #: ``None`` when the source stored no name for a recorded actor.
    display_name: str | None
    membership: Membership | None
    action: Any
    command: Any
    outcome: Any


@dataclass(frozen=True)
class ActionSpec:
    area: Area
    group: ActionGroup
    audience: Audience = "member"
    #: The object's kind and the row paths that may hold its id; the first
    #: path holding a UUID wins.
    object: tuple[ObjectKind, tuple[Path, ...]] | None = None
    #: The one typed field of the stored command the item carries.
    detail: Detail | None = None


_DRAFT = ("draft", (("outcome", "draft_id"), ("command", "draft_id")))
_PLANNED_DRAFT = (
    "draft",
    (("outcome", "draft_id"), ("command", "draft", "draft_id")),
)
_GRANT = ("grant", (("command", "grant_id"),))
_INVITE = ("invite", (("command", "invite_id"),))

#: Ledger actions: ``command->>'action'`` of an applied business_action_receipts row.
CATALOG: Mapping[str, ActionSpec] = MappingProxyType(
    {
        "review_draft": ActionSpec("records", "reviews", object=_DRAFT),
        "approve_expense": ActionSpec("records", "approvals", object=_DRAFT),
        "approve_income": ActionSpec("records", "approvals", object=_DRAFT),
        "approve_refund": ActionSpec("records", "approvals", object=_DRAFT),
        "capture_note": ActionSpec("records", "edits", object=_DRAFT),
        "prepare_attachment": ActionSpec("documents", "reading", object=_DRAFT),
        "rebind_attachment": ActionSpec("documents", "files", object=_DRAFT),
        "settle_remainder": ActionSpec("records", "edits", object=_DRAFT),
        "mark_personal": ActionSpec("records", "edits", object=_DRAFT, detail="personal"),
        "decide_606": ActionSpec("records", "approvals", object=_DRAFT, detail="include"),
        "resolve_duplicate": ActionSpec("documents", "reviews", object=_DRAFT),
        "edit_current_note": ActionSpec("records", "edits", object=_DRAFT),
        "append_supporting_file": ActionSpec("documents", "files", object=_DRAFT),
        "receipt_upload": ActionSpec("documents", "uploads"),
        "receipt_review": ActionSpec("records", "reviews"),
        "receipt_confirm": ActionSpec("records", "approvals"),
        "set_business_rnc": ActionSpec("business", "settings"),
        "business_propose_activity": ActionSpec(
            "records", "edits", object=_PLANNED_DRAFT
        ),
        "business_attach_source": ActionSpec("documents", "files", object=_PLANNED_DRAFT),
        "business_propose_allocation": ActionSpec(
            "records", "edits", object=_PLANNED_DRAFT
        ),
        "business_ask": ActionSpec("records", "reviews", object=_PLANNED_DRAFT),
        "owner_grant": ActionSpec("business", "access", "manager", _GRANT),
        "grant_access": ActionSpec(
            "business", "access", "manager", _GRANT, detail="role"
        ),
        "invite_access": ActionSpec(
            "business", "access", "manager", _INVITE, detail="role"
        ),
        "accept_invite": ActionSpec("business", "access", "manager", _GRANT),
        "revoke_grant": ActionSpec("business", "access", "manager", _GRANT),
        "revoke_invite": ActionSpec("business", "access", "manager", _INVITE),
        "change_role": ActionSpec("business", "access", "manager", _GRANT, detail="role"),
    }
)
#: Events read from a table other than the ledger; the query names them.
DERIVED: Mapping[str, ActionSpec] = MappingProxyType(
    {
        "ownership_transferred": ActionSpec("business", "access", "manager"),
        "receipt_reading_enabled": ActionSpec("business", "settings", "manager"),
    }
)
ACTIONS: Mapping[str, ActionSpec] = MappingProxyType({**CATALOG, **DERIVED})

#: A read or a look-up: not a change, so no page lists it.
READ_MARKS: frozenset[str] = frozenset(
    {
        "access_seen",
        "business_read_context",
        "business_find_related",
        "business_explain_status",
    }
)
#: A person's own state, not a change to the Business, so no page lists it.
PERSONAL_STATE: frozenset[str] = frozenset({"email_ai_consent_declined"})
UNLISTED: frozenset[str] = READ_MARKS | PERSONAL_STATE

_DETAILS: Mapping[Detail, Path] = MappingProxyType(
    {
        "role": ("command", "business_role"),
        "personal": ("command", "request", "personal"),
        "include": ("command", "request", "include"),
    }
)


@dataclass(frozen=True)
class Visibility:
    """Which action names a reader's page may hold. A member's page holds only
    the names the catalog lists for members, so a new ledger action never
    reaches members before the catalog names it. A manager's page holds every
    name but the unlisted ones, and one the catalog does not know shows as
    ``other``; once an area or group filter applies, only the names the
    catalog places there, so an unknown action never matches a filter."""

    only: tuple[str, ...] | None
    hidden: tuple[str, ...]


def selected(filters: ActivityFilters) -> frozenset[str]:
    """The catalog names inside the filter's areas and groups; every name
    when the filter names neither."""

    return frozenset(
        name
        for name, spec in ACTIONS.items()
        if (not filters.areas or spec.area in filters.areas)
        and (not filters.groups or spec.group in filters.groups)
    )


def visibility(*, manager: bool, filters: ActivityFilters) -> Visibility:
    chosen = selected(filters)
    if manager and not (filters.areas or filters.groups):
        return Visibility(only=None, hidden=tuple(sorted(UNLISTED)))
    if not manager:
        chosen = {name for name in chosen if ACTIONS[name].audience == "member"}
    return Visibility(only=tuple(sorted(chosen)), hidden=())


def project(row: EventRow) -> ActivityItem:
    name = row["action"]
    spec = ACTIONS.get(name) if isinstance(name, str) else None
    return ActivityItem(
        id=row["id"],
        occurred_at=row["created_at"],
        actor=_actor(row),
        action=name if spec is not None else "other",
        object=None if spec is None else _object(row, spec),
        area=None if spec is None else spec.area,
        restricted=spec is None or spec.audience == "manager",
        **({} if spec is None or spec.detail is None else _detail(row, spec.detail)),
    )


def with_labels(
    item: ActivityItem, labels: Mapping[tuple[ObjectKind, UUID], str]
) -> ActivityItem:
    if item.object is None:
        return item
    label = labels.get((item.object.kind, item.object.id))
    if label is None:
        return item
    return item.model_copy(
        update={"object": item.object.model_copy(update={"label": label})}
    )


def _actor(row: EventRow) -> ActivityActor | None:
    if row["display_name"] is None or row["actor_kind"] is None:
        return None
    return ActivityActor(
        display_name=row["display_name"],
        kind=row["actor_kind"],
        id=row["actor_key"],
        membership=row["membership"],
    )


def _object(row: EventRow, spec: ActionSpec) -> ActivityObject | None:
    if spec.object is None:
        return None
    kind, paths = spec.object
    for path in paths:
        try:
            return ActivityObject(kind=kind, id=UUID(str(_at(row, path))))
        except ValueError:
            continue
    return None


def _detail(row: EventRow, detail: Detail) -> dict[str, Any]:
    value = _at(row, _DETAILS[detail])
    if detail == "role":
        try:
            return {"role": BusinessRole(value)}
        except ValueError:
            return {}
    return {detail: value} if isinstance(value, bool) else {}


def _at(value: Any, path: Path) -> Any:
    for step in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(step)
    return value
