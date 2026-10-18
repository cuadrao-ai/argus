"""Whose Business records a request reads and writes.

Every Business route and the WhatsApp intake destination get their scope from
``resolve_business_scope`` and nowhere else. A client never names a space or
an owner: it may name one of its own grants (``X-Business-Grant``), and the
server takes the Business from that grant row after proving, on every
request, that the grant is the caller's and live.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from argus.domain.business.spaces import SpaceStore
from argus.domain.owner_scope import BusinessSpace

Role = Literal["owner", "accountant"]


@dataclass(frozen=True)
class BusinessScope:
    #: Whose records: the Business owner (the storage key), as today.
    person_id: str
    owner: BusinessSpace
    #: Who is acting, when it is not the owner themselves; None for the person's own space.
    actor_id: str | None = None
    #: The grant the request runs under; None for the person's own space before binding.
    grant_id: str | None = None
    role: Role = "owner"

    @property
    def acting_person_id(self) -> str:
        return self.person_id if self.actor_id is None else self.actor_id

    @property
    def acting_as_owner(self) -> bool:
        return self.role == "owner"


def resolve_business_scope(spaces: SpaceStore, person_id: str) -> BusinessScope | None:
    """The signed-in person's open Business space, or None before they start one.

    A space belongs only to the person who created it; nothing here reads a
    membership or a client-supplied id.
    """

    space = spaces.open_space(person_id)
    if space is None:
        return None
    return BusinessScope(
        person_id=space.custodian_id, owner=BusinessSpace(space.id), actor_id=person_id
    )
