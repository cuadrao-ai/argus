"""Best-effort projection of invitation and sender state."""

from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

from loguru import logger
from psycopg import Connection

from argus.domain.business.notifications.config import notifications_available
from argus.domain.business.notifications.store import (
    InMemoryNotificationStore,
    put,
    resolve,
)


@contextmanager
def _attempt(db: Connection | None = None) -> Iterator[None]:
    try:
        if db is None:
            yield
        else:
            with db.transaction():
                yield
    except Exception as error:
        logger.warning("business_notification_write_failed type={}", type(error).__name__)


def invitation_changed(db: Connection, business_id: str, invite_id: str) -> None:
    if not notifications_available():
        return
    with _attempt(db):
        row = db.execute(
            "select recipient_id::text,least(accepted_at,revoked_at,"
            " case when expires_at<=clock_timestamp() then expires_at end) from public.business_access_invites"
            " where space_id=%s and id=%s",
            (business_id, invite_id),
        ).fetchone()
        if row and row[1]:
            resolve(db, business_id, "invitation_received", invite_id, row[1])
        elif row and row[0]:
            put(db, business_id, row[0], "invitation_received", invite_id)


def memory_invitation(
    store: InMemoryNotificationStore, invite: dict, now: datetime
) -> None:
    if not notifications_available():
        return
    with _attempt():
        resolved = min(
            (
                at
                for at in (
                    invite["accepted_at"],
                    invite["revoked_at"],
                    invite["expires_at"] if invite["expires_at"] <= now else None,
                )
                if at is not None
            ),
            default=None,
        )
        if resolved is not None:
            store.resolve(
                invite["space_id"], "invitation_received", invite["id"], resolved
            )
        elif invite["recipient_id"]:
            store.put(
                invite["space_id"],
                invite["recipient_id"],
                "invitation_received",
                invite["id"],
            )


def sender_changed(db: Connection, business_id: str, sender_id: str, status: str) -> None:
    if not notifications_available():
        return
    with _attempt(db):
        if status != "pending":
            resolve(db, business_id, "new_sender_waiting", sender_id)
            return
        owners = db.execute(
            "select grantee_id::text from public.business_client_grants"
            " where space_id=%s and business_role='owner' and revoked_at is null"
            " and (expires_at is null or expires_at>clock_timestamp())",
            (business_id,),
        ).fetchall()
        for (owner,) in owners:
            put(db, business_id, owner, "new_sender_waiting", sender_id)


def memory_sender(
    store: InMemoryNotificationStore | None,
    owners: Callable[[str], tuple[str, ...]],
    business_id: str,
    sender_id: str,
    status: str,
) -> None:
    if not notifications_available() or store is None:
        return
    with _attempt():
        if status != "pending":
            store.resolve(business_id, "new_sender_waiting", sender_id)
        else:
            for owner in owners(business_id):
                store.put(business_id, owner, "new_sender_waiting", sender_id)
