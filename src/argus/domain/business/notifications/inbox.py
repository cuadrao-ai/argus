"""A person's notices: one per live invitation addressed to them.

The access store says which invitations are alive (its one liveness rule).
This module adds only what the bell owns: whether the person has read each.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Sequence
from typing import Literal, Protocol

from pydantic import BaseModel

from argus.domain.business.memberships import RecipientInvitation
from argus.domain.business.notifications.store import Kind
from argus.domain.business.roles import BusinessRole

INVITATION: Kind = "invitation_received"


class ReadMarks(Protocol):
    def read_subjects(
        self, recipient_user_id: str, kind: Kind, subject_ids: Collection[str]
    ) -> set[str]: ...

    def mark_read(
        self, recipient_user_id: str, kind: Kind, subjects: Iterable[tuple[str, str]]
    ) -> None: ...


class InvitationNotice(BaseModel):
    """``id`` is the invitation's id: the same one the email link carries."""

    id: str
    kind: Literal["invitation_received"] = "invitation_received"
    business_id: str
    business_name: str | None
    requested_role: BusinessRole
    unread: bool


def notices(
    marks: ReadMarks, person_id: str, invitations: Sequence[RecipientInvitation]
) -> list[InvitationNotice]:
    """Newest invitation first. Invitations share one lifetime, so the later
    expiry is the newer invitation."""

    read = marks.read_subjects(person_id, INVITATION, [i["id"] for i in invitations])
    return [
        InvitationNotice(
            id=i["id"],
            business_id=i["space_id"],
            business_name=i["name"] or None,
            requested_role=i["requested_role"],
            unread=i["id"] not in read,
        )
        for i in sorted(
            invitations, key=lambda i: (i["expires_at"], i["id"]), reverse=True
        )
    ]


def mark_read(
    marks: ReadMarks,
    person_id: str,
    invitations: Sequence[RecipientInvitation],
    ids: Collection[str],
) -> int:
    """Marks the named live invitations read and says how many were unread."""

    named = [i for i in invitations if i["id"] in ids]
    read = marks.read_subjects(person_id, INVITATION, [i["id"] for i in named])
    unread = [(i["space_id"], i["id"]) for i in named if i["id"] not in read]
    marks.mark_read(person_id, INVITATION, unread)
    return len(unread)
