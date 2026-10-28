"""What the activity feed shows of a ledger row. The server projects each row
to these shapes; the raw command, the input hash and every id but the
object's stay in the ledger."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BeforeValidator

from argus.domain.business.contracts.authority import ActorKind
from argus.domain.business.contracts.facts import Contract

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
    "other",
]
ObjectKind = Literal["draft", "grant", "invite"]


def _query_integer(value: object) -> object:
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        return int(value)
    return value


PageSize = Annotated[Literal[25, 50, 100], BeforeValidator(_query_integer)]


class ActivityActor(Contract):
    display_name: str
    kind: ActorKind


class ActivityObject(Contract):
    kind: ObjectKind
    id: UUID


class ActivityItem(Contract):
    id: str
    occurred_at: datetime
    actor: ActivityActor
    action: ActivityAction
    object: ActivityObject | None = None


class ActivityPage(Contract):
    items: tuple[ActivityItem, ...]
    next_cursor: str | None = None
