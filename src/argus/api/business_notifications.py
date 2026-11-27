from fastapi import HTTPException, Response

from argus.api.business_spaces import business_access
from argus.api.documents import NO_STORE
from argus.domain.business.access import InMemoryAccessStore, PostgresAccessStore
from argus.domain.business.notifications.config import notifications_available
from argus.domain.business.notifications.inbox import ReadMarks
from argus.domain.business.notifications.store import PostgresNotificationStore


def require_notifications(response: Response) -> None:
    response.headers.update(NO_STORE)
    if not notifications_available():
        raise HTTPException(404, "business_notifications_unavailable", headers=NO_STORE)


def notification_access() -> InMemoryAccessStore | PostgresAccessStore:
    access = business_access()
    if isinstance(access, (InMemoryAccessStore, PostgresAccessStore)):
        return access
    raise HTTPException(404, "business_notifications_unavailable", headers=NO_STORE)


def read_marks(access: InMemoryAccessStore | PostgresAccessStore) -> ReadMarks:
    if isinstance(access, InMemoryAccessStore):
        return access.notifications
    return PostgresNotificationStore(access.pool)
