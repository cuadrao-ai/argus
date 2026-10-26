from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from argus.domain.business.authority import ActionError, BusinessAuthority
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.ingestion.whatsapp.ai_consent import (
    AIConsentStore,
    ConsentError,
    EnableAIConsent,
)
from psycopg import errors

from tests import test_business_whatsapp_transport_postgres as shared

users, world, pytestmark = shared.users, shared.world, shared.pytestmark


@pytest.fixture
def consent(world):
    route = {
        "gateway": "openrouter",
        "interpretation": [{"model": "scripted-fixture", "provider": None}],
        "reply": [{"model": "scripted-fixture", "provider": None}],
    }
    store = AIConsentStore(world.pool, lambda: route)
    world.captures.consent = store
    return store, route


def enable(world, store, key=None):
    request = EnableAIConsent(
        action="enable", disclosure_token=store.status(world.owner)["disclosure_token"]
    )
    key = key or str(uuid4())
    return request, key, store.enable(world.owner, request, key)


def captured(world):
    message = world.message()
    world.captures.capture(message)
    lease = world.turns.acquire(
        space_id=world.space,
        sender_hash=world.keys.sender(message.sender).hex(),
        holder=uuid4(),
        duration=timedelta(minutes=1),
    )
    capture = world.captures.read(world.keys.message(message.id), lease=lease)
    actor = TrustedActor(
        actor_id=world.owner, actor_kind="owner_via_agent", space_id=world.space
    )
    ctx = BusinessAuthority(world.pool).resolve_actor(
        actor, grant_id=world.actions.grant_id
    )
    return capture, ctx, lease


def test_enable_replay_and_revoke_do_not_reactivate(world, consent):
    store, _ = consent
    request, key, view = enable(world, store)
    assert view["enabled"] and view["consented_at"]
    assert store.enable(world.owner, request, key) == view
    store.revoke(world.owner)
    store.revoke(world.owner)
    replay = store.enable(world.owner, request, key)
    assert not replay["enabled"] and replay["revoked_at"]
    assert replay["consented_at"] == view["consented_at"]


def test_old_capture_never_adopts_new_consent(world, consent):
    store, _ = consent
    old, ctx, lease = captured(world)
    assert old.ai_consent_id is None
    enable(world, store)
    with pytest.raises(ConsentError):
        store.require_access(old, ctx, lease=lease)
    with world.pool.connection() as db:
        assert db.execute(
            "select ai_consent_id from whatsapp_inbound_messages where id=%s", (old.id,)
        ).fetchone() == (None,)


def test_revocation_regrant_route_and_lease_are_checked(world, consent):
    store, route = consent
    enable(world, store)
    capture, ctx, lease = captured(world)
    store.require_access(capture, ctx, lease=lease)
    route["reply"][0]["model"] = "different-fixture"
    with pytest.raises(ConsentError):
        store.require_access(capture, ctx, lease=lease)
    route["reply"][0]["model"] = "scripted-fixture"
    store.revoke(world.owner)
    enable(world, store)
    with pytest.raises(ConsentError):
        store.require_access(capture, ctx, lease=lease)
    world.turns.release(lease)


def test_cross_sender_or_actor_context_cannot_use_consent(world, consent):
    store, _ = consent
    enable(world, store)
    capture, ctx, lease = captured(world)
    with pytest.raises(ConsentError):
        store.require_access(replace(capture, sender_hash=b"x" * 32), ctx, lease=lease)
    with pytest.raises(ConsentError):
        store.require_access(replace(capture, owner_id=uuid4()), ctx, lease=lease)


@pytest.mark.parametrize(
    "mutation",
    [
        "update business_whatsapp_ai_consents set scope_version=2 where id=%s",
        "update business_whatsapp_ai_consents set grant_id=gen_random_uuid() where id=%s",
        "delete from business_whatsapp_ai_consents where id=%s",
    ],
)
def test_consent_original_cannot_be_rewritten_or_directly_erased(
    world, consent, mutation
):
    store, _ = consent
    enable(world, store)
    capture, _, _ = captured(world)
    with world.pool.connection() as db, pytest.raises(errors.CheckViolation):
        db.execute(mutation, (capture.ai_consent_id,))


def test_capture_consent_cannot_be_replaced_and_link_delete_purges(world, consent):
    store, _ = consent
    enable(world, store)
    capture, _, lease = captured(world)
    with world.pool.connection() as db, pytest.raises(errors.CheckViolation):
        db.execute(
            "update whatsapp_inbound_messages set ai_consent_id=null where id=%s",
            (capture.id,),
        )
    world.turns.release(lease)
    with world.pool.connection() as db:
        db.execute("delete from whatsapp_sender_links where id=%s", (world.link,))
        assert (
            db.execute(
                "select count(*) from business_whatsapp_ai_consents where sender_link_id=%s",
                (world.link,),
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "select count(*) from whatsapp_inbound_messages where id=%s",
                (capture.id,),
            ).fetchone()[0]
            == 0
        )


def test_stale_disclosure_and_key_drift_are_conflicts(world, consent):
    store, route = consent
    request = EnableAIConsent(
        action="enable", disclosure_token=store.status(world.owner)["disclosure_token"]
    )
    route["reply"][0]["model"] = "new-fixture"
    with pytest.raises(ConsentError, match="disclosure_stale"):
        store.enable(world.owner, request, str(uuid4()))
    _, key, _ = enable(world, store)
    with pytest.raises(ConsentError, match="idempotency_conflict"):
        store.enable(world.owner, request, key)


def test_concurrent_same_command_creates_one_original_receipt(world, consent):
    store, _ = consent
    request = EnableAIConsent(
        action="enable", disclosure_token=store.status(world.owner)["disclosure_token"]
    )
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(
            workers.map(lambda _: store.enable(world.owner, request, key), range(2))
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


def test_relink_requires_new_opt_in_and_cannot_revive_old_capture(world, consent):
    store, _ = consent
    enable(world, store)
    capture, ctx, lease = captured(world)
    with world.pool.connection() as db:
        db.execute(
            "update whatsapp_sender_links set status='revoked',revoked_at=clock_timestamp() where id=%s",
            (world.link,),
        )
        db.execute(
            "insert into whatsapp_sender_links(destination_owner_id,wa_id_hash,last4,reply_language,status,linked_at)"
            " values (%s,%s,'1234','es-419','active',clock_timestamp())",
            (world.owner, capture.sender_hash),
        )
    assert not store.status(world.owner)["enabled"]
    enable(world, store)
    with pytest.raises(ConsentError):
        store.require_access(capture, ctx, lease=lease)


def test_original_grant_revocation_denies_access_and_command_replay(world, consent):
    store, _ = consent
    request, key, _ = enable(world, store)
    capture, ctx, lease = captured(world)
    with world.pool.connection() as db:
        db.execute(
            "update business_client_grants set revoked_at=clock_timestamp() where id=%s",
            (world.actions.grant_id,),
        )
        db.execute(
            "insert into business_client_grants(space_id,grantee_id,issuer_id,capabilities)"
            " values (%s,%s,%s,array['read','prepare','approve'])",
            (world.space, world.owner, world.owner),
        )
    assert not store.status(world.owner)["enabled"]
    with pytest.raises((ConsentError, ActionError)) as failure:
        store.require_access(capture, ctx, lease=lease)
    assert getattr(failure.value, "code", "") in {
        "business_record_not_found",
        "whatsapp_ai_consent_authority_changed",
    }
    with pytest.raises(ConsentError, match="authority_changed"):
        store.enable(world.owner, request, key)


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
def test_business_or_account_parent_purges_consent_and_transport(world, consent, parent):
    store, _ = consent
    enable(world, store)
    capture, _, lease = captured(world)
    world.turns.release(lease)
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
            assert (
                db.execute(
                    "select count(*) from whatsapp_inbound_messages where id=%s",
                    (capture.id,),
                ).fetchone()[0]
                == 0
            )
            release_custodian(world.space)
            return
        target = world.space
        db.execute(f"delete from {parent} where id=%s", (target,))
        assert (
            db.execute(
                "select count(*) from business_whatsapp_ai_consents where owner_id=%s",
                (world.owner,),
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "select count(*) from whatsapp_inbound_messages where id=%s",
                (capture.id,),
            ).fetchone()[0]
            == 0
        )


def test_own_status_is_read_only_unlinked_and_route_unavailable(world, consent):
    store, route = consent
    outsider = uuid4()
    absent = store.status(outsider)
    assert absent["linked"] is False and absent["disclosure_token"] is None
    assert absent["reason"] == "whatsapp_link_required"
    enable(world, store)
    disabled = store.status(world.owner, "whatsapp_unavailable")
    assert disabled["linked"] and disabled["enabled"]
    assert not disabled["available"] and disabled["disclosure_token"] is None
    route.clear()
    unknown = store.status(world.owner)
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


def test_disclosure_drift_refuses_stale_post_and_old_queued_consent(
    world, consent, monkeypatch
):
    store, _ = consent
    unconfirmed = EnableAIConsent(
        action="enable", disclosure_token=store.status(world.owner)["disclosure_token"]
    )
    original_text = store.scope.disclosure
    monkeypatch.setattr(
        store, "scope", replace(store.scope, disclosure=original_text + "\n")
    )
    with pytest.raises(ConsentError, match="disclosure_stale"):
        store.enable(world.owner, unconfirmed, str(uuid4()))
    request, key, view = enable(world, store)
    capture, ctx, lease = captured(world)
    store.require_access(capture, ctx, lease=lease)
    monkeypatch.setattr(
        store,
        "scope",
        replace(store.scope, disclosure=original_text + " Updated disclosure."),
    )
    assert not store.status(world.owner)["enabled"]
    replay = store.enable(world.owner, request, key)
    assert not replay["enabled"] and replay["consented_at"] == view["consented_at"]
    with pytest.raises(ConsentError, match="consent_required"):
        store.require_access(capture, ctx, lease=lease)
    with world.pool.connection() as db:
        assert store.capture_consent(db, world.link) is None
        assert (
            db.execute(
                "select disclosure from business_whatsapp_ai_consents where id=%s",
                (capture.ai_consent_id,),
            ).fetchone()[0]
            == original_text + "\n"
        )
    store.revoke(world.owner)
    enable(world, store)
    with pytest.raises(ConsentError, match="consent_required"):
        store.require_access(capture, ctx, lease=lease)


def test_receipt_permission_replaces_the_agent_permission_on_one_row(world, consent):
    from argus.domain.ingestion.whatsapp.ai_consent import RECEIPT_SCOPE

    agent, _ = consent
    enable(world, agent)
    receipts = AIConsentStore(world.pool, agent.route, RECEIPT_SCOPE)
    assert not receipts.status(world.owner)["enabled"]
    request = EnableAIConsent(
        action="enable", disclosure_token=receipts.status(world.owner)["disclosure_token"]
    )
    receipts.enable(world.owner, request, str(uuid4()))
    assert receipts.status(world.owner)["enabled"]
    assert not agent.status(world.owner)["enabled"]
    with world.pool.connection() as db:
        [(active,)] = db.execute(
            "select count(*) from business_whatsapp_ai_consents"
            " where owner_id=%s and revoked_at is null",
            (world.owner,),
        ).fetchall()
    assert active == 1
    receipts.revoke(world.owner)
    assert not receipts.status(world.owner)["enabled"]
    assert receipts.status(world.owner, language="es-419")["disclosure"].startswith(
        "Cuadrao lee con IA"
    )


@pytest.mark.parametrize("language", ["es-419", "en"])
def test_the_text_shown_is_the_text_stored_and_either_change_asks_again(
    world, consent, language, monkeypatch
):
    from argus.domain.ingestion.whatsapp.ai_consent import RECEIPT_SCOPE

    agent, _ = consent
    receipts = AIConsentStore(world.pool, agent.route, RECEIPT_SCOPE)
    shown = receipts.status(world.owner, language=language)
    assert shown["disclosure"] == RECEIPT_SCOPE.text(language)
    receipts.enable(
        world.owner,
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
    assert stored == RECEIPT_SCOPE.text(language)
    assert receipts.status(world.owner)["enabled"]
    # Changing the words the owner saw asks again; the other language's words
    # were never shown to this owner.
    field = "disclosure_es" if language == "es-419" else "disclosure"
    other = "disclosure" if language == "es-419" else "disclosure_es"
    monkeypatch.setattr(
        receipts,
        "scope",
        replace(RECEIPT_SCOPE, **{field: getattr(RECEIPT_SCOPE, field) + " "}),
    )
    assert not receipts.status(world.owner)["enabled"]
    monkeypatch.setattr(
        receipts,
        "scope",
        replace(RECEIPT_SCOPE, **{other: getattr(RECEIPT_SCOPE, other) + " "}),
    )
    assert receipts.status(world.owner)["enabled"]
    monkeypatch.setattr(receipts, "scope", RECEIPT_SCOPE)
    receipts.revoke(world.owner)


def test_a_token_from_one_language_is_stale_for_the_other(world, consent):
    from argus.domain.ingestion.whatsapp.ai_consent import RECEIPT_SCOPE

    agent, _ = consent
    receipts = AIConsentStore(world.pool, agent.route, RECEIPT_SCOPE)
    token = receipts.status(world.owner, language="en")["disclosure_token"]
    with pytest.raises(ConsentError, match="disclosure_stale"):
        receipts.enable(
            world.owner,
            EnableAIConsent(action="enable", disclosure_token=token, language="es-419"),
            str(uuid4()),
        )


def test_the_view_reports_another_active_scope_and_turning_on_replaces_it(world, consent):
    from argus.domain.ingestion.whatsapp.ai_consent import RECEIPT_SCOPE

    agent, _ = consent
    enable(world, agent)
    receipts = AIConsentStore(world.pool, agent.route, RECEIPT_SCOPE)
    view = receipts.status(world.owner)
    assert (view["enabled"], view["active_scope_version"]) == (False, 1)
    receipts.enable(
        world.owner,
        EnableAIConsent(action="enable", disclosure_token=view["disclosure_token"]),
        str(uuid4()),
    )
    view = receipts.status(world.owner)
    assert (view["enabled"], view["active_scope_version"]) == (True, 2)
    assert agent.status(world.owner)["active_scope_version"] == 2
    receipts.revoke(world.owner)
