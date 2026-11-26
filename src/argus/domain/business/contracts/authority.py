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


#: How a person reads to the viewer: by ``name``; by ``email`` when they have
#: none and the viewer manages the Business or is that person; as a
#: ``member`` to any other viewer; as a ``former`` member once they left or
#: were erased.
PersonShown = Literal["name", "email", "member", "former"]


def require_shown(
    display_name: str | None, email: str | None, shown_as: PersonShown | None
) -> None:
    """``display_name`` is set only when ``shown_as`` is ``name``, ``email``
    only when it is ``email``; the screen words the rest."""

    if (display_name is not None) != (shown_as == "name") or (email is not None) != (
        shown_as == "email"
    ):
        raise ValueError("a person shows exactly what shown_as says")


class PersonName(Contract):
    """A person as one viewer of a Business reads them now: ``shown_as`` says
    whether the name, the email, a member or a former member shows."""

    display_name: str | None
    email: str | None = None
    shown_as: PersonShown

    @model_validator(mode="after")
    def shown(self) -> PersonName:
        require_shown(self.display_name, self.email, self.shown_as)
        return self


class SentBy(Contract):
    """A person's sender id is shared across channels. An unnamed WhatsApp sender shows only the last four digits."""

    id: str
    kind: Literal["member", "email", "whatsapp"]
    #: The member, named for the viewer as ``people`` reads them.
    person: PersonName | None = None
    address: str | None = None
    phone_last4: str | None = None

    @model_validator(mode="after")
    def _one_sender(self) -> SentBy:
        shown = {
            "member": self.person,
            "email": self.address,
            "whatsapp": self.phone_last4,
        }
        if [kind for kind, value in shown.items() if value is not None] != [self.kind]:
            raise ValueError("a sender carries exactly what its kind names")
        return self


class ActorView(Contract):
    """Who acted and who granted their access, each named live for the viewer."""

    actor_id: UUID
    actor_kind: ActorKind
    grant_id: UUID
    issuer_id: UUID
    display_name: str | None
    email: str | None = None
    shown_as: PersonShown
    issuer_display_name: str | None
    issuer_email: str | None = None
    issuer_shown_as: PersonShown

    @model_validator(mode="after")
    def shown(self) -> ActorView:
        require_shown(self.display_name, self.email, self.shown_as)
        require_shown(self.issuer_display_name, self.issuer_email, self.issuer_shown_as)
        return self
