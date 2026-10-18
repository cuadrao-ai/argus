"""Synthetic local close commands exercise saved queue, delivery and privacy."""

from email.header import decode_header, make_header

import pytest
from argus.domain.business.close_mail import deliver_close_mail, render_close_mail
from argus.domain.business.custody_graph import retained_dependencies
from argus.domain.business.lifecycle import PostgresBusinessLifecycle

from tests import test_business_lifecycle_postgres as lifecycle
from tests import test_financial_accounts_postgres as shared
from tests.test_business_transfer_mail_postgres import provider as mail_provider

provider = mail_provider
world = lifecycle.world
users = lifecycle.users
pytestmark = pytest.mark.skipif(not shared.DSN, reason="Disposable database required")


def close(world, key="close-email"):
    pool, space, people, _, _ = world
    return PostgresBusinessLifecycle(pool).close(
        owner_id=people["owner"],
        space_id=space.id,
        confirmation=space.name,
        idempotency_key=key,
    )


def test_committed_close_queues_only_live_members_once_and_uses_shared_sender(
    world, provider
):  # noqa: F811
    pool, space, people, _, _ = world
    result = close(world)
    close(world)
    close(world, "another-key")
    assert len(provider.messages) == 1
    message = next(iter(provider.messages.values()))
    assert (
        str(make_header(decode_header(message["Subject"])))
        == f"{space.name} se cerró en Cuadrao"
    )
    assert message["From"] == "Cuadrao <no-responder@mail.cuadrao.ai>"
    assert message["To"].endswith("@example.test")
    with pool.connection() as db:
        row = db.execute(
            "select recipient_id::text,closed_at,sent_at,payload from public.business_close_mail_outbox where space_id=%s",
            (space.id,),
        ).fetchone()
        assert row[0] == people["other"] and row[1] == result.closed_at and row[2]
        assert "ya no tienes acceso" in row[3]["text"]
        assert "Cuadrao LLC, 123 Synthetic Street, Test City" in row[3]["text"]
        assert "business_close_mail_outbox" in retained_dependencies(db, people["owner"])


def test_failed_delivery_retries_same_provider_key_and_freezes_original_payload(
    world, provider, monkeypatch
):  # noqa: F811
    pool, space, _, _, _ = world
    provider.lose_response = True
    close(world)
    original = dict(provider.messages)
    monkeypatch.setenv("MARKETING_POSTAL_ADDRESS", "Different synthetic address")
    provider.lose_response = False
    assert deliver_close_mail(pool, space.id) == 1
    assert provider.messages == original
    assert len(provider.attempts) == 2 and len(set(provider.attempts)) == 1
    with pool.connection() as db:
        db.execute(
            "update public.business_close_mail_outbox set sent_at=null,first_attempt_at=clock_timestamp()-interval '24 hours' where space_id=%s",
            (space.id,),
        )
    assert deliver_close_mail(pool, space.id) == 0
    assert len(provider.attempts) == 2


def test_reopen_suppresses_unsent_close_and_new_close_has_new_notification(
    world, provider, monkeypatch
):  # noqa: F811
    from argus.domain import resend_email

    pool, space, people, _, _ = world
    monkeypatch.delenv(resend_email.SMTP_PASSWORD_ENV)
    close(world)
    PostgresBusinessLifecycle(pool).reopen(
        owner_id=people["owner"], space_id=space.id, idempotency_key="reopen"
    )
    monkeypatch.setenv(resend_email.SMTP_PASSWORD_ENV, "synthetic-only")
    assert deliver_close_mail(pool, space.id) == 0
    close(world, "close-again")
    assert len(provider.messages) == 1
    with pool.connection() as db:
        assert (
            db.execute(
                "select count(*) from public.business_close_mail_outbox where space_id=%s and suppressed_at is not null",
                (space.id,),
            ).fetchone()[0]
            == 1
        )


def test_revoked_member_gets_no_close_notification(world, provider):  # noqa: F811
    _, space, people, access, member = world
    access.revoke_grant(space.id, people["owner"], member.id)
    close(world)
    assert not provider.messages


def test_template_substitution_is_single_pass_and_postal_configuration_is_required(
    monkeypatch,
):
    context = {
        "businessName": "A & __CUADRAO_OWNER_NAME__",
        "ownerName": "Ana <Rosa>",
        "closedAt": "2026-10-18T02:00:00+00:00",
        "purgeAt": "2026-11-17T02:00:00+00:00",
    }
    monkeypatch.setenv("MARKETING_POSTAL_ADDRESS", "123 Synthetic Street")
    payload = render_close_mail(context)
    assert "A &amp; __CUADRAO_OWNER_NAME__" in payload["html"]
    assert "Ana &lt;Rosa&gt;" in payload["html"]
    assert "17 de octubre de 2026" in payload["text"]
    monkeypatch.delenv("MARKETING_POSTAL_ADDRESS")
    with pytest.raises(ValueError, match="postal"):
        render_close_mail(context)


def test_discovery_uses_current_owner_and_existing_target_authority(world):
    from argus.domain.business.transfer import PostgresBusinessTransfer

    pool, space, people, _, member = world
    service = PostgresBusinessLifecycle(pool)
    owned = service.owned_spaces(people["owner"])
    assert owned[0]["space_id"] == space.id
    assert owned[0]["members"][0]["grant_id"] == member.id
    assert not service.owned_spaces(people["other"])
    transfer = PostgresBusinessTransfer(pool).request(
        owner_id=people["owner"],
        space_id=space.id,
        target_grant_id=member.id,
        confirmation=space.name,
        idempotency_key="transfer-discovery",
    )
    PostgresBusinessTransfer(pool).accept(
        actor_id=people["other"], transfer_id=transfer.id
    )
    assert not service.owned_spaces(people["owner"])
    assert service.owned_spaces(people["other"])[0]["space_id"] == space.id


def test_concurrent_close_commands_send_one_event_per_member(world, provider):  # noqa: F811
    from concurrent.futures import ThreadPoolExecutor

    pool, space, _, _, _ = world
    with ThreadPoolExecutor(max_workers=4) as workers:
        results = list(workers.map(lambda _: close(world), range(4)))
    assert len({result.closed_at for result in results}) == 1
    assert len(provider.messages) == 1 and len(provider.attempts) == 1
    with pool.connection() as db:
        assert (
            db.execute(
                "select count(*) from public.business_close_mail_outbox where space_id=%s",
                (space.id,),
            ).fetchone()[0]
            == 1
        )


def test_failed_notification_queue_rolls_back_the_close(world, monkeypatch):
    from argus.domain.business import close_mail

    pool, space, _, _, _ = world

    def refuse(*args):
        raise RuntimeError("synthetic queue failure")

    monkeypatch.setattr(close_mail, "enqueue_close_mail", refuse)
    with pytest.raises(RuntimeError, match="synthetic queue failure"):
        close(world)
    with pool.connection() as db:
        assert (
            db.execute(
                "select closed_at from public.spaces where id=%s", (space.id,)
            ).fetchone()[0]
            is None
        )
        assert not db.execute(
            "select 1 from public.business_lifecycle_commands where space_id=%s",
            (space.id,),
        ).fetchone()


def test_close_notification_queue_is_service_only(world):
    import psycopg

    pool, space, _, _, _ = world
    close(world)
    for role in ("anon", "authenticated"):
        with pool.connection() as db, db.transaction():
            db.execute(f"set local role {role}")
            with pytest.raises(psycopg.errors.InsufficientPrivilege), db.transaction():
                db.execute("select * from public.business_close_mail_outbox")
    with pool.connection() as db, db.transaction():
        db.execute("set local role service_role")
        assert (
            db.execute(
                "select count(*) from public.business_close_mail_outbox where space_id=%s",
                (space.id,),
            ).fetchone()[0]
            == 1
        )
