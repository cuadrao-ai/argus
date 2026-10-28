"""What the activity feed shows of a ledger row. The server projects each row
to these shapes; the raw command, the input hash and every id but the
object's stay in the ledger."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BeforeValidator, StringConstraints, field_validator, model_validator

from argus.domain.business.contracts.authority import ActorKind
from argus.domain.business.contracts.facts import Contract
from argus.domain.business.roles import BusinessRole

ActivityAction = Literal[
    "review_draft",
    "approve_expense",
    "approve_income",
    "approve_refund",
    "capture_note",
    "prepare_attachment",
    "rebind_attachment",
    "settle_remainder",
    "mark_personal",
    "decide_606",
    "resolve_duplicate",
    "edit_current_note",
    "append_supporting_file",
    "receipt_upload",
    "receipt_review",
    "receipt_confirm",
    "set_business_rnc",
    "business_propose_activity",
    "business_attach_source",
    "business_propose_allocation",
    "business_ask",
    "owner_grant",
    "grant_access",
    "invite_access",
    "accept_invite",
    "revoke_grant",
    "revoke_invite",
    "change_role",
    "ownership_transferred",
    "receipt_reading_enabled",
    "other",
]
ObjectKind = Literal["draft", "grant", "invite"]
Area = Literal["documents", "records", "invoicing", "business"]
ActionGroup = Literal[
    "uploads",
    "reading",
    "reviews",
    "approvals",
    "edits",
    "files",
    "invoices",
    "access",
    "settings",
]
Membership = Literal["current", "former"]
#: An opaque id per person and Business; never an account id or an email.
ActorId = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]


def _query_integer(value: object) -> object:
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        return int(value)
    return value


PageSize = Annotated[Literal[25, 50, 100], BeforeValidator(_query_integer)]


class ActivityActor(Contract):
    display_name: str
    kind: ActorKind
    id: ActorId | None = None
    membership: Membership | None = None


class ActivityObject(Contract):
    kind: ObjectKind
    id: UUID
    label: str | None = None


class ActivityItem(Contract):
    id: str
    occurred_at: datetime
    #: ``None`` when the source recorded no actor: "Actor no registrado".
    actor: ActivityActor | None
    action: ActivityAction
    object: ActivityObject | None = None
    area: Area | None = None
    #: Listed only for a reader who may manage.
    restricted: bool = False
    role: BusinessRole | None = None
    personal: bool | None = None
    include: bool | None = None


class ActivityFacetActor(Contract):
    id: ActorId
    display_name: str
    kind: ActorKind
    membership: Membership | None = None


class ActivityPage(Contract):
    items: tuple[ActivityItem, ...]
    next_cursor: str | None = None
    #: Every actor with a row the reader may see; the first page only.
    actors: tuple[ActivityFacetActor, ...] | None = None


class ActivityFilters(Contract):
    """The filter set one page was read with. Dates are calendar days in the
    Business time zone, inclusive. Within one field the values are OR'ed;
    across fields they are AND'ed. A cursor is bound to the whole set."""

    since: date | None = None
    until: date | None = None
    actors: tuple[ActorId, ...] = ()
    areas: tuple[Area, ...] = ()
    groups: tuple[ActionGroup, ...] = ()

    @field_validator("actors", "areas", "groups", mode="after")
    @classmethod
    def canonical(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(set(values)))

    @model_validator(mode="after")
    def ordered_days(self) -> ActivityFilters:
        if self.since is not None and self.until is not None and self.since > self.until:
            raise ValueError("the range ends before it starts")
        return self
