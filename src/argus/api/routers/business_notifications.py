from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from argus.api.business import BusinessPerson, require_business_person
from argus.api.business_notifications import (
    notification_access,
    read_marks,
    require_notifications,
)
from argus.domain.business.memberships import RecipientInvitation
from argus.domain.business.notifications.inbox import (
    InvitationNotice,
    mark_read,
    notices,
)


class BusinessNotifications(BaseModel):
    items: list[InvitationNotice]
    unread_count: int


class ReadNotifications(BaseModel):
    ids: list[UUID] = Field(max_length=200)


class BusinessNotificationRead(BaseModel):
    updated: int


router = APIRouter(
    prefix="/notifications",
    dependencies=[Depends(require_notifications)],
    responses={404: {"description": "Unavailable"}},
)
Person = Annotated[BusinessPerson, Depends(require_business_person)]


def _name(person: BusinessPerson, invitation: RecipientInvitation) -> str | None:
    return invitation["name"] or getattr(
        person.spaces.get(invitation["space_id"]), "name", None
    )


@router.get("", response_model=BusinessNotifications)
def list_notifications(person: Person) -> dict:
    access = notification_access()
    invitations: list[RecipientInvitation] = [
        {**invitation, "name": _name(person, invitation)}
        for invitation in access.invitations_for(person.person_id)
    ]
    items = notices(read_marks(access), person.person_id, invitations)
    return {"items": items, "unread_count": sum(item.unread for item in items)}


@router.post("/read", response_model=BusinessNotificationRead)
def read_notifications(body: ReadNotifications, person: Person) -> dict[str, int]:
    access = notification_access()
    return {
        "updated": mark_read(
            read_marks(access),
            person.person_id,
            access.invitations_for(person.person_id),
            {str(found) for found in body.ids},
        )
    }
