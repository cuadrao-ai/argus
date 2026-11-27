"""The original WhatsApp sender follows only the assigned held document."""

from dataclasses import dataclass, replace
from uuid import uuid4

import psycopg
import pytest
from argus.domain.ingestion.whatsapp.store_postgres import PostgresWhatsAppStore
from argus.domain.postgres_connection import BorrowedConnection
from psycopg import Connection

from tests import test_business_spaces_migration_postgres as fixtures

users = fixtures.users
db = fixtures.db
pytestmark = fixtures.pytestmark


@dataclass(frozen=True)
class Capture:
    key: bytes
    link: str
    personal: str
    business: str
    target: str


@pytest.fixture
def capture(db: Connection, users: dict[str, str]) -> Capture:
    sender, custodian = users["other"], users["owner"]
    sender_hash = uuid4().bytes + uuid4().bytes
    key = uuid4().bytes + uuid4().bytes
    link = fixtures.sender_link(db, sender, sender_hash)
    personal = fixtures.connection(db, sender)
    business = fixtures.space(db, custodian)
    target = fixtures.connection(db, custodian, business)
    db.execute(
        "insert into public.whatsapp_inbound_messages"
        " (provider_message_key, sender_hash, destination_owner_id, status,"
        " connection_id, sender_link_id, received_at, updated_at)"
        " values (%s, %s, %s, 'captured', %s, %s, now(), now())",
        (key, sender_hash, sender, personal, link),
    )
    db.execute(
        "insert into public.whatsapp_held_files"
        " (user_id, sender_link_id, provider_message_key, connection_id, reason, held_at)"
        " values (%s, %s, %s, %s, 'no_match', now())",
        (sender, link, key, personal),
    )
    return Capture(key, link, personal, business, target)


def assign(db: Connection, capture: Capture) -> None:
    db.execute(
        "update public.whatsapp_held_files set state='assigned', settled_at=now(),"
        " assigned_space_id=%s, assigned_connection_id=%s where provider_message_key=%s",
        (capture.business, capture.target, capture.key),
    )


def move_capture(db: Connection, capture: Capture) -> None:
    db.execute(
        "update public.whatsapp_inbound_messages set connection_id=%s"
        " where provider_message_key=%s",
        (capture.target, capture.key),
    )


def disconnect(db: Connection, capture: Capture) -> None:
    db.execute(
        "update public.whatsapp_sender_links set status='revoked', revoked_at=now()"
        " where id=%s",
        (capture.link,),
    )


def test_adoption_after_disconnect_retains_sender_and_channel_or_rolls_back(
    db: Connection, users: dict[str, str], capture: Capture
) -> None:
    disconnect(db, capture)
    store = PostgresWhatsAppStore(BorrowedConnection(db))
    original = store.inbound(capture.key)
    assert (
        original.connection_id == capture.personal
        and original.sender_link_id == capture.link
    )
    with db.transaction(force_rollback=True):
        assign(db, capture)
        move_capture(db, capture)
        adopted = store.inbound(capture.key)
        assert adopted == replace(original, connection_id=capture.target)
        assert store.captured_connections(destination_owner_id=users["owner"]) == {
            capture.target
        }
    assert store.inbound(capture.key) == original
    assert db.execute(
        "select state, assigned_connection_id from public.whatsapp_held_files"
        " where provider_message_key=%s",
        (capture.key,),
    ).fetchone() == ("held", None)


@pytest.mark.parametrize(
    "tamper",
    [
        "state='held', settled_at=null, assigned_connection_id=null, assigned_space_id=null",
        "provider_message_key=sha256(gen_random_uuid()::text::bytea)",
        "sender_link_id=gen_random_uuid()",
        "connection_id=gen_random_uuid()",
        "assigned_connection_id=gen_random_uuid()",
        "assigned_space_id=gen_random_uuid()",
        "user_id=(select user_id from public.financial_source_connections where id=assigned_connection_id)",
    ],
    ids=["unassigned", "message", "link", "source", "target", "business", "sender"],
)
def test_disconnected_link_needs_exact_held_assignment(
    db: Connection, capture: Capture, tamper: str
) -> None:
    disconnect(db, capture)
    assign(db, capture)
    db.execute(
        f"update public.whatsapp_held_files set {tamper} where provider_message_key=%s",
        (capture.key,),
    )
    with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
        move_capture(db, capture)


def test_active_link_cannot_move_capture_to_another_receipt(
    db: Connection, capture: Capture, users: dict[str, str]
) -> None:
    assign(db, capture)
    another_receipt = fixtures.connection(db, users["owner"], capture.business)
    with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
        db.execute(
            "update public.whatsapp_inbound_messages set connection_id=%s"
            " where provider_message_key=%s",
            (another_receipt, capture.key),
        )


def test_assignment_can_change_only_the_captured_connection(
    db: Connection, capture: Capture
) -> None:
    disconnect(db, capture)
    assign(db, capture)
    with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
        db.execute(
            "update public.whatsapp_inbound_messages set connection_id=%s,"
            " received_at=received_at+interval '1 day' where provider_message_key=%s",
            (capture.target, capture.key),
        )
