"""Persistence, access and lifetime of consent recorded when a phone links."""

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from argus.domain.business.access import PostgresAccessStore
from argus.domain.business.spaces import PostgresSpaceStore
from argus.domain.business.transfer import PostgresBusinessTransfer
from argus.domain.ingestion.whatsapp.ai_consent import LINK_DISCLOSURES, AIConsentStore
from argus.domain.ingestion.whatsapp.store_postgres import PostgresWhatsAppStore
from faker import Faker
from psycopg import errors
from psycopg_pool import ConnectionPool

from tests import test_whatsapp_intake_postgres as shared
from tests.business_cleanup import delete_spaces
from tests.business_reading_support import ROUTE, reading_setting
from tests.ingestion.whatsapp_cases import Clock
from tests.ingestion.whatsapp_link_support import NOTICE, prepare_phone_business

users, pool, pytestmark = shared.users, shared.pool, shared.pytestmark


@dataclass
class LinkedOwner:
    pool: ConnectionPool
    owner: UUID
    space: UUID
    link: UUID
    consent: AIConsentStore


@pytest.fixture
def world(pool, users, monkeypatch):
    owner = users["owner"]
    space, _ = PostgresSpaceStore(pool).create(owner, Faker().company())
    prepare_phone_business(pool, space.id, owner)
    monkeypatch.setattr(
        "argus.domain.ingestion.whatsapp.receipt_consent.receipt_provider_route",
        lambda: ROUTE,
    )
    now, code = Clock()(), uuid4().bytes * 2
    store = PostgresWhatsAppStore(pool)
    store.issue_code(
        destination_owner_id=owner, code_digest=code, reply_language="es-419",
        disclosure=NOTICE, now=now, expires_at=now + timedelta(minutes=10),
    )
    assert store.redeem_code(code_digest=code, sender_hash=uuid4().bytes * 2, last4="1234", now=now)
    with pool.connection() as db:
        link = db.execute(
            "select id from whatsapp_sender_links where destination_owner_id=%s and status='active'",
            (owner,),
        ).fetchone()[0]
    consent = AIConsentStore(pool, lambda: ROUTE)
    assert consent.status(UUID(owner))["enabled"]
    return LinkedOwner(pool, UUID(owner), UUID(space.id), link, consent)


@pytest.mark.parametrize(
    "mutation",
    [
        "update business_whatsapp_ai_consents set scope_version=1 where owner_id=%s",
        "update business_whatsapp_ai_consents set grant_id=gen_random_uuid() where owner_id=%s",
        "delete from business_whatsapp_ai_consents where owner_id=%s",
    ],
)
def test_consent_original_cannot_be_rewritten_or_directly_erased(
    world, mutation
):
    with world.pool.connection() as db, pytest.raises(errors.CheckViolation):
        db.execute(mutation, (world.owner,))


def test_link_deletion_purges_consent(world):
    with world.pool.connection() as db:
        db.execute("delete from whatsapp_sender_links where id=%s", (world.link,))
        assert (
            db.execute(
                "select count(*) from business_whatsapp_ai_consents where sender_link_id=%s",
                (world.link,),
            ).fetchone()[0]
            == 0
        )


def test_client_cannot_read_permission_and_service_cannot_truncate(world):
    for role, statement in [
        ("authenticated", "select * from business_whatsapp_ai_consents"),
        ("service_role", "truncate business_whatsapp_ai_consents"),
    ]:
        with world.pool.connection() as db, pytest.raises(errors.InsufficientPrivilege):
            db.execute(f"set local role {role}")
            db.execute(statement)


@pytest.mark.parametrize("parent", ["spaces", "auth.users"])
def test_consent_survives_business_removal_and_account_deletion_purges_it(
    world, parent
):
    with world.pool.connection() as db:
        if parent == "auth.users":
            from tests.test_business_account_deletion_postgres import (
                erase_open_owner,
                release_custodian,
            )

            db.commit()
            outcome = erase_open_owner(world.pool, world.owner)
            assert outcome.status == "done"
            assert (
                db.execute(
                    "select count(*) from auth.users where id=%s", (world.owner,)
                ).fetchone()[0]
                == 0
            )
            assert (
                db.execute(
                    "select count(*) from business_whatsapp_ai_consents where owner_id=%s",
                    (world.owner,),
                ).fetchone()[0]
                == 0
            )
            release_custodian(world.space)
            return
        delete_spaces(db, "id=%s", (world.space,))
        assert db.execute(
            "select sender_link_id from business_whatsapp_ai_consents where owner_id=%s",
            (world.owner,),
        ).fetchall() == [(world.link,)]
    assert not world.consent.status(world.owner)["enabled"]
    world.consent.revoke(world.owner)


def test_repeated_revoke_keeps_the_first_revocation_and_original_consent(world):
    original = world.consent.status(world.owner)
    world.consent.revoke(world.owner)
    revoked = world.consent.status(world.owner)
    assert not revoked["enabled"] and revoked["revoked_at"]
    assert revoked["consented_at"] == original["consented_at"]
    world.consent.revoke(world.owner)
    assert world.consent.status(world.owner) == revoked


def test_only_the_active_link_can_supply_the_persons_consent(world):
    store = PostgresWhatsAppStore(world.pool)
    assert store.revoke(destination_owner_id=str(world.owner), now=Clock()())
    status = world.consent.status(world.owner)
    assert not status["linked"] and not status["enabled"]
    with world.pool.connection() as db:
        db.execute(
            "insert into whatsapp_sender_links(destination_owner_id,wa_id_hash,last4,reply_language,status,linked_at)"
            " select destination_owner_id,wa_id_hash,last4,reply_language,'active',clock_timestamp()"
            " from whatsapp_sender_links where id=%s", (world.link,),
        )
    status = world.consent.status(world.owner)
    assert status["linked"] and not status["enabled"] and status["disclosure"] is None


def test_only_the_stored_language_and_route_govern_the_original_notice(world, monkeypatch):
    monkeypatch.setitem(LINK_DISCLOSURES, "en", "changed")
    assert world.consent.status(world.owner)["enabled"]
    monkeypatch.setitem(LINK_DISCLOSURES, "es-419", NOTICE + " ")
    status = world.consent.status(world.owner)
    assert not status["enabled"] and status["disclosure"] == NOTICE
    assert status["revoked_at"] is None


def test_transfer_keeps_the_phone_receipt_with_its_person_and_checks_todays_setup(world, users):
    access = PostgresAccessStore(world.pool)
    transfer = PostgresBusinessTransfer(world.pool)
    owner, other, space = str(world.owner), users["other"], str(world.space)
    with world.pool.connection() as db:
        email = db.execute(
            "update auth.users set email_confirmed_at=now() where id=%s returning email", (other,),
        ).fetchone()[0]
    _, listing = access.give(space, owner, email)
    access.accept_invite(other, space, listing.invites[0].id)
    member = next(row for row in access.list(space, owner).grants if not row.owner)
    offer = transfer.request(
        owner_id=owner, space_id=space, target_grant_id=member.id,
        confirmation=PostgresSpaceStore(world.pool).get(space).name, idempotency_key=str(uuid4()),
    )
    transfer.accept(actor_id=other, transfer_id=offer.id)
    assert not world.consent.status(UUID(other))["linked"]
    reading = reading_setting(world.pool)
    shown = reading.status(space, owner)
    if not shown["enabled"]:
        reading.set(
            space, owner, actor_id=other, enabled=True, version=shown["scope_version"],
            disclosure_token=shown["disclosure_token"],
        )
    assert world.consent.status(world.owner)["enabled"]
    grant = next(row for row in access.spaces_for(owner) if row.space_id == space)
    access.change_role(space, other, grant.grant_id, "viewer")
    assert not world.consent.status(world.owner)["enabled"]


def test_database_refuses_a_new_receipt_with_the_retired_scope(world):
    world.consent.revoke(world.owner)
    with world.pool.connection() as db, pytest.raises(errors.CheckViolation, match="whatsapp_consent_scope_retired"):
        db.execute(
            "insert into business_whatsapp_ai_consents"
            " (sender_link_id,space_id,owner_id,sender_hash,consenting_actor_id,grant_id,issuer_id,"
            " scope_version,purpose,disclosure,route,route_hash,idempotency_key,input_hash)"
            " select sender_link_id,space_id,owner_id,sender_hash,consenting_actor_id,grant_id,issuer_id,"
            " 1,'business_whatsapp_draft_assistance',disclosure,route,route_hash,%s,input_hash"
            " from business_whatsapp_ai_consents where sender_link_id=%s",
            (str(uuid4()), world.link),
        )
