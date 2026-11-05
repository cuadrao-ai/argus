from fastapi import HTTPException, Response

from argus.api.business_spaces import business_access
from argus.api.documents import NO_STORE
from argus.domain.business.access import InMemoryAccessStore, PostgresAccessStore
from argus.domain.business.notifications.config import notifications_available
from argus.domain.business.notifications.store import (
    InMemoryNotificationStore,
    PostgresNotificationStore,
)


def require_notifications(response: Response) -> None:
    response.headers.update(NO_STORE)
    if not notifications_available():
        raise HTTPException(404, "business_notifications_unavailable", headers=NO_STORE)


def notification_store(
    business_id: str, user_id: str
) -> InMemoryNotificationStore | PostgresNotificationStore:
    access = business_access()
    if isinstance(access, (InMemoryAccessStore, PostgresAccessStore)):
        access.refresh_notifications(business_id, user_id)
    if isinstance(access, InMemoryAccessStore):
        return access.notifications
    if isinstance(access, PostgresAccessStore):
        return PostgresNotificationStore(access.pool)
    raise HTTPException(404, "business_notifications_unavailable", headers=NO_STORE)
