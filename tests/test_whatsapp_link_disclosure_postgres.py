"""A new link and the notice accepted for that number are recorded together."""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from argus.domain.business.spaces import PostgresSpaceStore
from argus.domain.ingestion.whatsapp.ai_consent import AIConsentStore
from argus.domain.ingestion.whatsapp.store_postgres import PostgresWhatsAppStore
from faker import Faker
from psycopg_pool import ConnectionPool

from tests import test_whatsapp_intake_postgres as shared
from tests.business_reading_support import ROUTE, reading_setting, turn_reading
from tests.ingestion.whatsapp_cases import Clock
from tests.ingestion.whatsapp_link_support import (
    ENGLISH_NOTICE,
    NOTICE,
    prepare_phone_business,
)

pool, users, pytestmark = shared.pool, shared.users, shared.pytestmark


@pytest.mark.parametrize(("reading_at_redemption", "route_available"), [(True, True), (False, True), (True, False)])
def test_redeem_checks_setup_and_records_only_the_notice_accepted_for_this_link(
    pool: ConnectionPool,
    users: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    reading_at_redemption: bool,
    route_available: bool,
) -> None:
    def route() -> dict:
        if not route_available:
            raise ValueError("unconfigured")
        return ROUTE

    monkeypatch.setattr(
        "argus.domain.ingestion.whatsapp.receipt_consent.receipt_provider_route", route,
    )
    owner = users["owner"]
    space, _ = PostgresSpaceStore(pool).create(owner, Faker().company())
    prepare_phone_business(pool, space.id, owner)
    setting = reading_setting(pool)
    store = PostgresWhatsAppStore(pool)
    now = Clock()()
    code, sender = uuid4().bytes * 2, uuid4().bytes * 2
    store.issue_code(
        destination_owner_id=owner,
        code_digest=code,
        reply_language="es-419",
        disclosure=NOTICE,
        now=now,
        expires_at=now + timedelta(minutes=10),
    )
    if not reading_at_redemption:
        turn_reading(setting, space.id, owner, enabled=False)
    link = store.redeem_code(code_digest=code, sender_hash=sender, last4="1234", now=now)
    assert (link is not None) == reading_at_redemption
    if link:
        assert AIConsentStore(pool, route).status(UUID(owner))["enabled"] == route_available
        assert AIConsentStore(pool, lambda: ROUTE).status(UUID(owner))["enabled"]
        assert not AIConsentStore(pool, lambda: {"gateway": "different-fixture"}).status(UUID(owner))["enabled"]
    assert (
        store.redeem_code(code_digest=code, sender_hash=sender, last4="1234", now=now)
        is None
    )
    with pool.connection() as db:
        rows = db.execute(
            "select c.disclosure,c.owner_id::text,l.wa_id_hash=c.sender_hash"
            " from public.business_whatsapp_ai_consents c"
            " join public.whatsapp_sender_links l on l.id=c.sender_link_id"
            " where c.owner_id=%s and l.status='active' and c.revoked_at is null",
            (owner,),
        ).fetchall()
    assert rows == ([(NOTICE, owner, True)] if reading_at_redemption else [])


@pytest.mark.parametrize(("language", "notice"), [("es-419", NOTICE), ("en", ENGLISH_NOTICE)])
def test_stored_consent_belongs_to_the_new_link_and_uses_its_current_grant(
    pool: ConnectionPool, users: dict[str, str], monkeypatch: pytest.MonkeyPatch,
    language: str, notice: str,
) -> None:
    from argus.domain.business.access import PostgresAccessStore
    from argus.domain.ingestion.whatsapp.ai_consent import record_link_consent

    monkeypatch.setattr(
        "argus.domain.ingestion.whatsapp.receipt_consent.receipt_provider_route",
        lambda: ROUTE,
    )
    person = users["owner"]
    space, _ = PostgresSpaceStore(pool).create(person, Faker().company())
    grant = PostgresAccessStore(pool).spaces_for(person)[0]
    sender = uuid4().bytes * 2
    with pool.connection() as db, db.transaction():
        link = db.execute(
            "insert into public.whatsapp_sender_links"
            "(destination_owner_id,wa_id_hash,last4,reply_language,status,linked_at)"
            " values (%s,%s,'1234',%s,'active',now()) returning id",
            (person, sender, language),
        ).fetchone()[0]
        record_link_consent(
            db,
            grant=grant,
            link_id=link,
            sender_hash=sender,
            language=language,
            disclosure=notice,
        )
    with pool.connection() as db:
        assert db.execute(
            "select disclosure,grant_id::text,space_id::text,sender_hash,consenting_actor_id::text"
            " from public.business_whatsapp_ai_consents where sender_link_id=%s",
            (link,),
        ).fetchall() == [(notice, grant.grant_id, space.id, sender, person)]


@pytest.mark.parametrize("disclosure", [None, NOTICE + " "], ids=["legacy", "stale"])
def test_unverified_notice_cannot_replace_an_active_link(
    pool: ConnectionPool, users: dict[str, str], disclosure: str | None,
) -> None:
    person, sender = users["owner"], uuid4().bytes * 2
    space, _ = PostgresSpaceStore(pool).create(person, Faker().company())
    prepare_phone_business(pool, space.id, person)
    now, code = Clock()(), uuid4().bytes * 2
    with pool.connection() as db:
        db.execute(
            "insert into public.whatsapp_sender_links"
            "(destination_owner_id,wa_id_hash,last4,reply_language,status,linked_at)"
            " values (%s,%s,'1928','en','active',%s)", (person, sender, now),
        )
        db.execute(
            "insert into public.whatsapp_link_codes"
            "(destination_owner_id,code_digest,reply_language,created_at,expires_at,disclosure)"
            " values (%s,%s,'es-419',%s,%s,%s)",
            (person, code, now, now + timedelta(minutes=10), disclosure),
        )
    store = PostgresWhatsAppStore(pool)
    assert store.redeem_code(code_digest=code, sender_hash=uuid4().bytes * 2, last4="3456", now=now) is None
    assert store.destination_link(destination_owner_id=person).last4 == "1928"
    with pool.connection() as db:
        assert db.execute(
            "select consumed_at is not null,disclosure from public.whatsapp_link_codes where code_digest=%s",
            (code,),
        ).fetchone() == (True, None)
        assert db.execute(
            "select count(*) from public.business_whatsapp_ai_consents where owner_id=%s", (person,),
        ).fetchone() == (0,)


def test_link_consent_survives_loss_of_the_recorded_grant_until_the_last_eligible_business(
    pool: ConnectionPool, users: dict[str, str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.domain.business.access import PostgresAccessStore
    from argus.domain.ingestion.whatsapp.receipt_consent import receipt_reading_enabled

    owner, editor = users["owner"], users["other"]
    monkeypatch.setattr(
        "argus.domain.ingestion.whatsapp.receipt_consent.receipt_provider_route", lambda: ROUTE
    )
    spaces = PostgresSpaceStore(pool)
    first, _ = spaces.create(owner, Faker().company())
    second, _ = spaces.create_additional(owner, Faker().company(), "DO", str(uuid4()))
    access = PostgresAccessStore(pool)
    with pool.connection() as db:
        email = db.execute(
            "update auth.users set email_confirmed_at=now() where id=%s returning email", (editor,)
        ).fetchone()[0]
    for space in (first, second):
        prepare_phone_business(pool, space.id, owner)
        _, listing = access.give(space.id, owner, email)
        access.accept_invite(editor, space.id, listing.invites[0].id)
    store = PostgresWhatsAppStore(pool)
    now, code, sender = Clock()(), uuid4().bytes * 2, uuid4().bytes * 2
    store.issue_code(
        destination_owner_id=editor, code_digest=code, reply_language="es-419",
        disclosure=NOTICE, now=now, expires_at=now + timedelta(minutes=10),
    )
    assert store.redeem_code(code_digest=code, sender_hash=sender, last4="4321", now=now)
    permission = AIConsentStore(pool, lambda: ROUTE)
    assert receipt_reading_enabled(permission, editor)
    with pool.connection() as db:
        original_space, original_grant = db.execute(
            "select space_id::text,grant_id::text from public.business_whatsapp_ai_consents"
            " where owner_id=%s", (editor,),
        ).fetchone()
    access.revoke_grant(original_space, owner, original_grant)
    assert receipt_reading_enabled(permission, editor)
    [remaining] = access.spaces_for(editor)
    access.revoke_grant(remaining.space_id, owner, remaining.grant_id)
    assert not receipt_reading_enabled(permission, editor)
    with pool.connection() as db:
        assert db.execute(
            "select space_id::text,grant_id::text,revoked_at from public.business_whatsapp_ai_consents"
            " where owner_id=%s", (editor,),
        ).fetchall() == [(original_space, original_grant, None)]
