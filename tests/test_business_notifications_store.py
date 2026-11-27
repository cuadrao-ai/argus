from uuid import uuid4

from argus.domain.business.notifications.store import InMemoryNotificationStore

KIND = "invitation_received"


def test_a_subject_is_unread_until_marked_and_the_first_reading_time_stays():
    ticks = iter(range(10))
    store = InMemoryNotificationStore(clock=lambda: next(ticks))
    business, recipient, subject = (str(uuid4()) for _ in range(3))
    assert store.read_subjects(recipient, KIND, [subject]) == set()
    store.mark_read(recipient, KIND, [(business, subject)])
    assert store.read_subjects(recipient, KIND, [subject]) == {subject}
    (row,) = store._rows.values()
    first = row.read_at
    store.mark_read(recipient, KIND, [(business, subject)])
    assert len(store._rows) == 1
    assert row.read_at == first


def test_marking_reads_the_row_the_invitation_writer_already_put():
    store = InMemoryNotificationStore()
    business, recipient, subject = (str(uuid4()) for _ in range(3))
    store.put(business, recipient, KIND, subject)
    store.mark_read(recipient, KIND, [(business, subject)])
    (row,) = store._rows.values()
    assert row.read_at is not None


def test_read_state_belongs_to_one_person_and_one_kind():
    store = InMemoryNotificationStore()
    business, recipient, other, subject = (str(uuid4()) for _ in range(4))
    store.mark_read(recipient, KIND, [(business, subject)])
    assert store.read_subjects(other, KIND, [subject]) == set()
    assert store.read_subjects(recipient, "new_sender_waiting", [subject]) == set()
    assert store.read_subjects(recipient, KIND, [str(uuid4())]) == set()
