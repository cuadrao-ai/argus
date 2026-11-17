from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from .facts import Contract

Capability = Literal["read", "prepare", "approve"]
ActorKind = Literal["owner_via_agent", "member", "extractor"]


class ClientGrant(Contract):
    id: UUID
    space_id: UUID
    grantee_id: UUID
    issuer_id: UUID
    capabilities: frozenset[Capability] = Field(min_length=1)
    created_at: datetime
    expires_at: datetime | None = None
    revoked_at: datetime | None = None

    @model_validator(mode="after")
    def grant_dates(self) -> ClientGrant:
        if self.expires_at is not None and self.expires_at <= self.created_at:
            raise ValueError("grant expiry must follow creation")
        if self.revoked_at is not None and self.revoked_at < self.created_at:
            raise ValueError("grant revocation cannot precede creation")
        return self


class TrustedActor(Contract):
    actor_id: UUID
    actor_kind: ActorKind
    space_id: UUID


class ActorProvenance(Contract):
    """Who acted, as a ledger row stores it. A reader names both people live
    from their ids (``people.py``); the two name slots stay empty on new rows
    and only exist because the tables' checks still require the keys."""

    actor_id: UUID
    actor_kind: ActorKind
    display_name: str = ""
    grant_id: UUID
    issuer_id: UUID
    issuer_display_name: str = ""


class PersonName(Contract):
    """A person as the members of one Business read them now: the profile
    name, else null; the email only when there is no name and they still
    hold access to this Business. Both null: they left it."""

    display_name: str | None
    email: str | None = None


class ActorView(Contract):
    """Who acted and who granted their access, each named live."""

    actor_id: UUID
    actor_kind: ActorKind
    grant_id: UUID
    issuer_id: UUID
    display_name: str | None
    email: str | None = None
    issuer_display_name: str | None
    issuer_email: str | None = None
