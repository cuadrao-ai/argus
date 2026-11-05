from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from argus.api.business import BusinessPerson, require_business_person
from argus.api.business_notifications import notification_store, require_notifications
from argus.api.documents import NO_STORE
from argus.domain.business.notifications.store import Notification


class BusinessNotifications(BaseModel):
    items: list[Notification]
    unread_count: int


class BusinessNotificationRead(BaseModel):
    updated: int


router = APIRouter(
    prefix="/notifications",
    dependencies=[Depends(require_notifications)],
    responses={404: {"description": "Unavailable"}},
)
Person = Annotated[BusinessPerson, Depends(require_business_person)]


@router.get("", response_model=BusinessNotifications)
def list_notifications(business_id: UUID, person: Person) -> dict:
    items = notification_store(str(business_id), person.person_id).list(
        str(business_id), person.person_id
    )
    return {
        "items": items,
        "unread_count": sum(n.read_at is None and n.resolved_at is None for n in items),
    }


@router.post("/read-all", response_model=BusinessNotificationRead)
def mark_all_read(business_id: UUID, person: Person) -> dict[str, int]:
    return {
        "updated": notification_store(str(business_id), person.person_id).mark_read(
            str(business_id), person.person_id
        )
    }


@router.post("/{notification_id}/read", response_model=BusinessNotificationRead)
def mark_read(notification_id: UUID, business_id: UUID, person: Person) -> dict[str, int]:
    store = notification_store(str(business_id), person.person_id)
    if not any(
        n.id == str(notification_id)
        for n in store.list(str(business_id), person.person_id)
    ):
        raise HTTPException(404, "business_notification_not_found", headers=NO_STORE)
    return {
        "updated": store.mark_read(
            str(business_id), person.person_id, str(notification_id)
        )
    }
