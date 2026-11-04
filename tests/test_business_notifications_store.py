from datetime import datetime, timedelta, timezone
from uuid import uuid4

from argus.domain.business.notifications.store import InMemoryNotificationStore


def test_duplicate_unresolved_event_keeps_id_and_read_state():
    store = InMemoryNotificationStore()
    business, recipient, subject = (str(uuid4()) for _ in range(3))
    store.put(business, recipient, "invitation_received", subject)
    first = store.list(business, recipient)[0]
    assert store.mark_read(business, recipient, first.id) == 1
    store.put(business, recipient, "invitation_received", subject)
    assert len(store.list(business, recipient)) == 1
    assert store.list(business, recipient)[0].id == first.id
    assert store.list(business, recipient)[0].read_at is not None
    assert store.mark_read(business, recipient, first.id) == 0
    store.resolve(business, "invitation_received", subject)
    store.resolve(business, "invitation_received", subject)
    store.put(business, recipient, "invitation_received", subject)
    rows = store.list(business, recipient)
    assert len(rows) == 2
    assert sum(row.resolved_at is None for row in rows) == 1


def test_recipient_and_business_scopes_are_isolated():
    store = InMemoryNotificationStore()
    business, other_business, recipient, other, subject = (str(uuid4()) for _ in range(5))
    store.put(business, recipient, "new_sender_waiting", subject)
    row = store.list(business, recipient)[0]
    assert store.list(business, other) == []
    assert store.list(other_business, recipient) == []
    assert store.mark_read(business, other, row.id) == 0
    assert store.mark_read(other_business, recipient, row.id) == 0
    assert store.list(business, recipient)[0].read_at is None


def test_newest_first_and_recent_resolutions_only():
    now = datetime(2026, 11, 4, tzinfo=timezone.utc)
    store = InMemoryNotificationStore(clock=lambda: now)
    business, recipient = str(uuid4()), str(uuid4())
    unresolved, old, recent = (str(uuid4()) for _ in range(3))
    store.put(business, recipient, "invitation_received", unresolved)
    store.put(business, recipient, "invitation_received", old)
    store.resolve(business, "invitation_received", old)
    now += timedelta(days=31)
    store.put(business, recipient, "new_sender_waiting", recent)
    store.resolve(business, "new_sender_waiting", recent)
    assert [row.subject_id for row in store.list(business, recipient)] == [
        recent,
        unresolved,
    ]
    assert store.mark_read(business, recipient) == 3
    assert all(row.read_at is not None for row in store.list(business, recipient))
