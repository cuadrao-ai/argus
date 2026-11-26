from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from uuid import UUID, uuid4

import pytest
from argus.domain.business.authority import ActionError
from argus.domain.business.spaces import PostgresSpaceStore
from argus.domain.ingestion.whatsapp.ai_consent import (
    AIConsentStore,
    ConsentError,
    EnableAIConsent,
)
from faker import Faker
from psycopg import errors
from psycopg_pool import ConnectionPool

from tests import test_whatsapp_intake_postgres as shared
from tests.business_cleanup import delete_spaces
from tests.ingestion.test_whatsapp_ai_consent import HISTORICAL_SCOPE

users, pool, pytestmark = shared.users, shared.pool, shared.pytestmark


@dataclass
class LinkedOwner:
    pool: ConnectionPool
    owner: UUID
    space: UUID
    link: UUID


@pytest.fixture
def world(pool, users):
    owner = UUID(users["owner"])
    space, _ = PostgresSpaceStore(pool).create(str(owner), Faker().company())
    with pool.connection() as db:
        link = db.execute(
            "insert into whatsapp_sender_links(destination_owner_id,wa_id_hash,last4,reply_language,status,linked_at)"
            " values (%s,%s,'1234','es-419','active',clock_timestamp()) returning id",
            (owner, uuid4().bytes + uuid4().bytes),
        ).fetchone()[0]
    return LinkedOwner(pool, owner, UUID(space.id), link)


@pytest.fixture
def consent(world):
    route = {
        "gateway": "openrouter",
        "interpretation": [{"model": "scripted-fixture", "provider": None}],
        "reply": [],
    }
    store = AIConsentStore(world.pool, lambda: route, HISTORICAL_SCOPE)
    return store, route


def enable(world, store, key=None):
    request = EnableAIConsent(
        action="enable",
        disclosure_token=store.status(world.owner, world.space)["disclosure_token"],
    )
    key = key or str(uuid4())
    return request, key, store.enable(world.owner, world.space, request, key)


def test_enable_replay_and_revoke_do_not_reactivate(world, consent):
    store, _ = consent
    request, key, view = enable(world, store)
    assert view["enabled"] and view["consented_at"]
    assert store.enable(world.owner, world.space, request, key) == view
    store.revoke(world.owner)
    store.revoke(world.owner)
    replay = store.enable(world.owner, world.space, request, key)
    assert not replay["enabled"] and replay["revoked_at"]
    assert replay["consented_at"] == view["consented_at"]


@pytest.mark.parametrize(
    "mutation",
    [
        "update business_whatsapp_ai_consents set scope_version=1 where owner_id=%s",
        "update business_whatsapp_ai_consents set grant_id=gen_random_uuid() where owner_id=%s",
        "delete from business_whatsapp_ai_consents where owner_id=%s",
    ],
)
def test_consent_original_cannot_be_rewritten_or_directly_erased(
    world, consent, mutation
):
    store, _ = consent
    enable(world, store)
    with world.pool.connection() as db, pytest.raises(errors.CheckViolation):
        db.execute(mutation, (world.owner,))


def test_link_deletion_purges_consent(world, consent):
    store, _ = consent
    enable(world, store)
    with world.pool.connection() as db:
        db.execute("delete from whatsapp_sender_links where id=%s", (world.link,))
        assert (
            db.execute(
                "select count(*) from business_whatsapp_ai_consents where sender_link_id=%s",
                (world.link,),
            ).fetchone()[0]
            == 0
        )


def test_stale_disclosure_and_key_drift_are_conflicts(world, consent):
    store, route = consent
    request = EnableAIConsent(
        action="enable",
        disclosure_token=store.status(world.owner, world.space)["disclosure_token"],
    )
    route["interpretation"][0]["model"] = "new-fixture"
    with pytest.raises(ConsentError, match="disclosure_stale"):
        store.enable(world.owner, world.space, request, str(uuid4()))
    _, key, _ = enable(world, store)
    with pytest.raises(ConsentError, match="idempotency_conflict"):
        store.enable(world.owner, world.space, request, key)


def test_concurrent_same_command_creates_one_original_receipt(world, consent):
    store, _ = consent
    request = EnableAIConsent(
        action="enable",
        disclosure_token=store.status(world.owner, world.space)["disclosure_token"],
    )
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(
            workers.map(
                lambda _: store.enable(world.owner, world.space, request, key), range(2)
            )
        )
    assert results[0] == results[1]
    with world.pool.connection() as db:
        assert (
            db.execute(
                "select count(*) from business_whatsapp_ai_consents where owner_id=%s",
                (world.owner,),
            ).fetchone()[0]
            == 1
        )


def test_relink_requires_new_opt_in(world, consent):
    store, _ = consent
    enable(world, store)
    with world.pool.connection() as db:
        db.execute(
            "update whatsapp_sender_links set status='revoked',revoked_at=clock_timestamp() where id=%s",
            (world.link,),
        )
        db.execute(
            "insert into whatsapp_sender_links(destination_owner_id,wa_id_hash,last4,reply_language,status,linked_at)"
            " select destination_owner_id,wa_id_hash,last4,reply_language,'active',clock_timestamp()"
            " from whatsapp_sender_links where id=%s",
            (world.link,),
        )
    assert not store.status(world.owner, world.space)["enabled"]
    enable(world, store)
    assert store.status(world.owner, world.space)["enabled"]


def test_transferred_business_grants_the_creator_whatsapp_rights_only_through_their_new_role(
    world, users, consent
):
    from argus.domain.business.access import PostgresAccessStore
    from argus.domain.business.spaces import PostgresSpaceStore
    from argus.domain.business.transfer import PostgresBusinessTransfer

    store, _ = consent
    access = PostgresAccessStore(world.pool)
    transfer = PostgresBusinessTransfer(world.pool)
    owner, other, space = str(world.owner), users["other"], str(world.space)
    with world.pool.connection() as db:
        email = db.execute(
            "update auth.users set email_confirmed_at=now() where id=%s returning email",
            (other,),
        ).fetchone()[0]
    _, listing = access.give(space, owner, email)
    access.accept_invite(other, space, listing.invites[0].id)
    member = next(row for row in access.list(space, owner).grants if not row.owner)
    offer = transfer.request(
        owner_id=owner,
        space_id=space,
        target_grant_id=member.id,
        confirmation=PostgresSpaceStore(world.pool).get(space).name,
        idempotency_key=str(uuid4()),
    )
    transfer.accept(actor_id=other, transfer_id=offer.id)
    assert PostgresSpaceStore(world.pool).open_space(owner) is None
    request, _, enabled = enable(world, store)
    assert enabled["enabled"]
    grant = next(row for row in access.spaces_for(owner) if row.space_id == space)
    access.change_role(space, other, grant.grant_id, "viewer")
    status = store.status(world.owner, world.space)
    assert (status["available"], status["enabled"]) == (False, False)
    with pytest.raises(ActionError, match="business_permission_denied"):
        store.enable(world.owner, world.space, request, str(uuid4()))
    store.revoke(world.owner)


def test_original_grant_revocation_denies_access_and_command_replay(world, consent):
    store, _ = consent
    request, key, _ = enable(world, store)
    with world.pool.connection() as db:
        db.execute(
            "update business_client_grants set revoked_at=clock_timestamp()"
            " where id=(select grant_id from business_whatsapp_ai_consents where owner_id=%s and revoked_at is null)",
            (world.owner,),
        )
        db.execute(
            "insert into business_client_grants(space_id,grantee_id,issuer_id,capabilities)"
            " values (%s,%s,%s,array['read','prepare','approve'])",
            (world.space, world.owner, world.owner),
        )
    assert not store.status(world.owner, world.space)["enabled"]
    with pytest.raises(ConsentError, match="authority_changed"):
        store.enable(world.owner, world.space, request, key)


def test_fresh_consent_replaces_the_grant_of_a_closed_business(world, consent, users):
    from argus.domain.business.access import PostgresAccessStore
    from argus.domain.business.lifecycle import PostgresBusinessLifecycle

    store, _ = consent
    old_request, old_key, _ = enable(world, store)
    spaces = PostgresSpaceStore(world.pool)
    original = spaces.get(str(world.space))
    second, _ = spaces.create(users["other"], Faker().company())
    access = PostgresAccessStore(world.pool)
    with world.pool.connection() as db:
        email = db.execute(
            "update auth.users set email_confirmed_at=now() where id=%s returning email",
            (world.owner,),
        ).fetchone()[0]
    _, listing = access.give(second.id, users["other"], email)
    access.accept_invite(str(world.owner), second.id, listing.invites[0].id)
    PostgresBusinessLifecycle(world.pool).close(
        owner_id=str(world.owner), space_id=original.id, confirmation=original.name,
        idempotency_key=str(uuid4()),
    )
    selected = UUID(second.id)
    shown = store.status(world.owner, selected)
    assert shown["available"] and not shown["enabled"]
    with pytest.raises(ConsentError, match="authority_changed"):
        store.enable(world.owner, selected, old_request, old_key)
    fresh = EnableAIConsent(action="enable", disclosure_token=shown["disclosure_token"])
    assert store.enable(world.owner, selected, fresh, str(uuid4()))["enabled"]
    with world.pool.connection() as db:
        assert db.execute(
            "select space_id, revoked_at is null from business_whatsapp_ai_consents"
            " where sender_link_id=%s order by consented_at", (world.link,)
        ).fetchall() == [(world.space, False), (selected, True)]


def test_client_cannot_read_permission_and_service_cannot_truncate(world, consent):
    store, _ = consent
    enable(world, store)
    for role, statement in [
        ("authenticated", "select * from business_whatsapp_ai_consents"),
        ("service_role", "truncate business_whatsapp_ai_consents"),
    ]:
        with world.pool.connection() as db, pytest.raises(errors.InsufficientPrivilege):
            db.execute(f"set local role {role}")
            db.execute(statement)


@pytest.mark.parametrize("parent", ["spaces", "auth.users"])
def test_consent_survives_business_removal_and_account_deletion_purges_it(
    world, consent, parent
):
    store, _ = consent
    enable(world, store)
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
    assert not store.status(world.owner)["enabled"]
    store.revoke(world.owner)


def test_own_status_is_read_only_unlinked_and_route_unavailable(world, consent):
    store, route = consent
    outsider = uuid4()
    absent = store.status(outsider)
    assert absent["linked"] is False and absent["disclosure_token"] is None
    assert absent["reason"] == "whatsapp_link_required"
    enable(world, store)
    disabled = store.status(world.owner, world.space, "whatsapp_unavailable")
    assert disabled["linked"] and disabled["enabled"]
    assert not disabled["available"] and disabled["disclosure_token"] is None
    route.clear()
    unknown = store.status(world.owner, world.space)
    assert unknown["reason"] == "whatsapp_ai_route_unavailable"
    assert unknown["route"] is None and unknown["disclosure_token"] is None
    with world.pool.connection() as db:
        assert (
            db.execute(
                "select count(*) from business_whatsapp_ai_consents where owner_id=%s",
                (outsider,),
            ).fetchone()[0]
            == 0
        )


def test_disclosure_drift_refuses_stale_post_and_invalidates_prior_consent(
    world, consent, monkeypatch
):
    store, _ = consent
    unconfirmed = EnableAIConsent(
        action="enable",
        disclosure_token=store.status(world.owner, world.space)["disclosure_token"],
    )
    original_text = store.scope.disclosure
    monkeypatch.setattr(
        store, "scope", replace(store.scope, disclosure=original_text + "\n")
    )
    with pytest.raises(ConsentError, match="disclosure_stale"):
        store.enable(world.owner, world.space, unconfirmed, str(uuid4()))
    request, key, view = enable(world, store)
    monkeypatch.setattr(
        store,
        "scope",
        replace(store.scope, disclosure=original_text + " Updated disclosure."),
    )
    assert not store.status(world.owner, world.space)["enabled"]
    replay = store.enable(world.owner, world.space, request, key)
    assert not replay["enabled"] and replay["consented_at"] == view["consented_at"]
    with world.pool.connection() as db:
        assert (
            db.execute(
                "select disclosure from business_whatsapp_ai_consents where owner_id=%s and revoked_at is null",
                (world.owner,),
            ).fetchone()[0]
            == original_text + "\n"
        )


def test_new_consent_is_only_for_receipt_reading(world, consent):
    receipts, _ = consent
    historical = AIConsentStore(
        world.pool,
        receipts.route,
        replace(HISTORICAL_SCOPE, version=1, purpose="business_whatsapp_draft_assistance"),
    )
    with pytest.raises(errors.CheckViolation, match="whatsapp_consent_scope_retired"):
        enable(world, historical)
    _, _, current = enable(world, receipts)
    assert (current["enabled"], current["active_scope_version"]) == (True, 2)


@pytest.mark.parametrize("language", ["es-419", "en"])
def test_the_text_shown_is_the_text_stored_and_either_change_asks_again(
    world, consent, language, monkeypatch
):
    receipts, _ = consent
    shown = receipts.status(world.owner, world.space, language=language)
    assert shown["disclosure"] == HISTORICAL_SCOPE.text(language)
    receipts.enable(
        world.owner,
        world.space,
        EnableAIConsent(
            action="enable", disclosure_token=shown["disclosure_token"], language=language
        ),
        str(uuid4()),
    )
    with world.pool.connection() as db:
        [(stored,)] = db.execute(
            "select disclosure from business_whatsapp_ai_consents"
            " where owner_id=%s and revoked_at is null",
            (world.owner,),
        ).fetchall()
    assert stored == HISTORICAL_SCOPE.text(language)
    assert receipts.status(world.owner, world.space)["enabled"]
    # Changing the words the owner saw asks again; the other language's words
    # were never shown to this owner.
    field = "disclosure_es" if language == "es-419" else "disclosure"
    other = "disclosure" if language == "es-419" else "disclosure_es"
    monkeypatch.setattr(
        receipts,
        "scope",
        replace(HISTORICAL_SCOPE, **{field: getattr(HISTORICAL_SCOPE, field) + " "}),
    )
    assert not receipts.status(world.owner, world.space)["enabled"]
    monkeypatch.setattr(
        receipts,
        "scope",
        replace(HISTORICAL_SCOPE, **{other: getattr(HISTORICAL_SCOPE, other) + " "}),
    )
    assert receipts.status(world.owner, world.space)["enabled"]
    monkeypatch.setattr(receipts, "scope", HISTORICAL_SCOPE)
    receipts.revoke(world.owner)


def test_a_token_from_one_language_is_stale_for_the_other(world, consent):
    receipts, _ = consent
    token = receipts.status(world.owner, world.space, language="en")["disclosure_token"]
    with pytest.raises(ConsentError, match="disclosure_stale"):
        receipts.enable(
            world.owner,
            world.space,
            EnableAIConsent(action="enable", disclosure_token=token, language="es-419"),
            str(uuid4()),
        )
