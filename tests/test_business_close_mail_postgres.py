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
            "select recipient_id::text,closed_at,sent_at,payload from public.business_close_mail_outbox where space_id=%s and kind='member_closed'",
            (space.id,),
        ).fetchone()
        assert row[0] == people["other"] and row[1] == result.closed_at and row[2]
        assert "ya no tienes acceso" in row[3]["text"]
        assert row[3]["text"].endswith("\n\nCuadrao LLC")
        assert "business_close_mail_outbox" in retained_dependencies(db, people["owner"])


def test_failed_delivery_retries_same_provider_key_and_freezes_original_payload(
    world, provider, monkeypatch
):  # noqa: F811
    pool, space, _, _, _ = world
    provider.lose_response = True
    close(world)
    original = dict(provider.messages)
    monkeypatch.setenv("CUADRAO_EMAIL_ASSET_ORIGIN", "https://other-images.example.test")
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
    assert deliver_close_mail(pool, space.id) == 1
    close(world, "close-again")
    assert len(provider.messages) == 2
    with pool.connection() as db:
        assert (
            db.execute(
                "select count(*) from public.business_close_mail_outbox where space_id=%s and kind='member_closed' and suppressed_at is not null",
                (space.id,),
            ).fetchone()[0]
            == 1
        )


def test_revoked_member_gets_no_close_notification(world, provider):  # noqa: F811
    _, space, people, access, member = world
    access.revoke_grant(space.id, people["owner"], member.id)
    close(world)
    assert not provider.messages


def test_template_substitution_is_single_pass_and_reads_no_postal_address(
    monkeypatch,
):
    context = {
        "businessName": "A & __CUADRAO_OWNER_NAME__",
        "ownerName": "Ana <Rosa>",
        "closedAt": "2026-10-18T02:00:00+00:00",
        "purgeAt": "2026-11-17T02:00:00+00:00",
    }
    monkeypatch.delenv("MARKETING_POSTAL_ADDRESS", raising=False)
    payload = render_close_mail(context)
    assert "A &amp; __CUADRAO_OWNER_NAME__" in payload["html"]
    assert "Ana &lt;Rosa&gt;" in payload["html"]
    assert "17 de octubre de 2026" in payload["text"]
    assert payload["text"].endswith("\n\nCuadrao LLC")
    monkeypatch.setenv("MARKETING_POSTAL_ADDRESS", "123 Synthetic Street")
    assert render_close_mail(context) == payload


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
                "select count(*) from public.business_close_mail_outbox where space_id=%s and kind='member_closed'",
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
                "select count(*) from public.business_close_mail_outbox where space_id=%s and kind='member_closed'",
                (space.id,),
            ).fetchone()[0]
            == 1
        )


def _confirm(pool, person):  # noqa: ANN001
    with pool.connection() as db:
        db.execute(
            "update auth.users set email_confirmed_at=now() where id=%s", (person,)
        )


def _kinds(pool, space_id):  # noqa: ANN001
    with pool.connection() as db:
        return db.execute(
            "select kind,recipient_id::text,payload is null,sent_at is null,suppressed_at is not null,context->>'reopenPath'"
            " from public.business_close_mail_outbox where space_id=%s order by kind,recipient_id",
            (space_id,),
        ).fetchall()


def test_close_sends_the_owner_confirmation_and_member_notice_once(world, provider):  # noqa: F811
    from argus.domain.business.close_mail import reopen_path

    pool, space, people, _, _ = world
    _confirm(pool, people["owner"])
    close(world)
    close(world)
    assert len(provider.messages) == 2
    assert _kinds(pool, space.id) == [
        ("member_closed", people["other"], False, False, False, reopen_path(space.id)),
        ("owner_closed", people["owner"], False, False, False, reopen_path(space.id)),
    ]
    assert reopen_path(space.id) == f"/biz?lifecycle=manage&business={space.id}"


def test_reopen_queues_member_notices_and_retires_the_close_notices(
    world, provider, monkeypatch
):  # noqa: F811
    from argus.domain import resend_email

    pool, space, people, _, _ = world
    _confirm(pool, people["owner"])
    monkeypatch.delenv(resend_email.SMTP_PASSWORD_ENV)
    close(world)
    monkeypatch.setenv(resend_email.SMTP_PASSWORD_ENV, "synthetic-only")
    PostgresBusinessLifecycle(pool).reopen(
        owner_id=people["owner"], space_id=space.id, idempotency_key="reopen-notice"
    )
    PostgresBusinessLifecycle(pool).reopen(
        owner_id=people["owner"], space_id=space.id, idempotency_key="reopen-notice"
    )
    assert len(provider.messages) == 1 and len(provider.attempts) == 1
    path = f"/biz?lifecycle=manage&business={space.id}"
    assert _kinds(pool, space.id) == [
        ("member_closed", people["other"], True, True, True, path),
        ("member_reopened", people["other"], False, False, False, path),
        ("owner_closed", people["owner"], True, True, True, path),
    ]


def _age(pool, space_id, days):  # noqa: ANN001
    from datetime import timedelta

    with pool.connection() as db:
        db.execute(
            "update public.spaces set closed_at=clock_timestamp()-%s where id=%s",
            (timedelta(days=days), space_id),
        )


def test_day_23_reminds_the_current_owner_once_with_the_reopen_path(world, provider):  # noqa: F811
    from argus.domain.business.close_mail import enqueue_purge_reminders

    pool, space, people, _, _ = world
    _confirm(pool, people["owner"])
    close(world)
    _age(pool, space.id, 22)
    assert space.id not in enqueue_purge_reminders(pool)
    _age(pool, space.id, 23)
    assert space.id in enqueue_purge_reminders(pool)
    assert space.id in enqueue_purge_reminders(pool)
    with pool.connection() as db:
        rows = db.execute(
            "select recipient_id::text,payload is null,sent_at is null,context->>'reopenPath',context ? 'purgeAt'"
            " from public.business_close_mail_outbox where space_id=%s and kind='purge_reminder'",
            (space.id,),
        ).fetchall()
    assert rows == [
        (people["owner"], True, True, f"/biz?lifecycle=manage&business={space.id}", True)
    ]
    _age(pool, space.id, 30)
    assert space.id not in enqueue_purge_reminders(pool)


def test_a_business_without_an_owner_gets_no_reminder(world):  # noqa: F811
    from argus.domain.business.close_mail import enqueue_purge_reminders

    pool, space, people, _, _ = world
    close(world)
    with pool.connection() as db:
        db.execute(
            "update public.spaces set current_owner_id=null where id=%s", (space.id,)
        )
    _age(pool, space.id, 24)
    assert space.id not in enqueue_purge_reminders(pool)


NEW_KINDS = ("owner_closed", "purge_reminder", "member_reopened")
ALL_KINDS = ("member_closed", *NEW_KINDS)


def _prepare_event(world, provider, monkeypatch, kind):  # noqa: ANN001
    from argus.domain.business.close_mail import enqueue_purge_reminders

    pool, space, people, _, _ = world
    _confirm(pool, people["owner"])
    with monkeypatch.context() as preparation:
        preparation.delenv("ARGUS_APPROVAL_EMAIL_SMTP_PASSWORD")
        close(world)
        if kind == "purge_reminder":
            _age(pool, space.id, 23)
            assert space.id in enqueue_purge_reminders(pool)
        elif kind == "member_reopened":
            PostgresBusinessLifecycle(pool).reopen(
                owner_id=people["owner"], space_id=space.id, idempotency_key="mail-reopen"
            )
    with pool.connection() as db:
        db.execute(
            "update public.business_close_mail_outbox set suppressed_at=clock_timestamp()"
            " where space_id=%s and kind<>%s and sent_at is null",
            (space.id, kind),
        )
        row = db.execute(
            "select id::text,context from public.business_close_mail_outbox where space_id=%s and kind=%s",
            (space.id, kind),
        ).fetchone()
    provider.messages.clear()
    provider.attempts.clear()
    return row


@pytest.mark.parametrize("kind", NEW_KINDS)
def test_reduced_policy_never_reserves_renders_or_transports_a_held_kind(
    world, provider, monkeypatch, kind
):  # noqa: F811
    from argus.domain.business import close_mail

    pool, space, _, _, _ = world
    mail_id, _ = _prepare_event(world, provider, monkeypatch, kind)
    monkeypatch.setattr(close_mail, "_APPROVED_KINDS", frozenset({"member_closed"}))

    def forbidden_render(*args, **kwargs):
        pytest.fail("Held mail reached rendering")

    monkeypatch.setattr(close_mail, "render_close_mail", forbidden_render)
    assert deliver_close_mail(pool, space.id) == 0
    assert deliver_close_mail(pool, space.id) == 0
    assert not provider.messages and not provider.attempts
    with pool.connection() as db:
        assert db.execute(
            "select first_attempt_at,payload,sent_at,provider_receipt from public.business_close_mail_outbox where id=%s",
            (mail_id,),
        ).fetchone() == (None, None, None, None)


@pytest.mark.parametrize("kind", NEW_KINDS)
def test_reduced_policy_blocks_a_previously_frozen_kind(
    world, provider, monkeypatch, kind
):  # noqa: F811
    from argus.domain.business import close_mail
    from psycopg.types.json import Jsonb

    monkeypatch.setattr(close_mail, "_APPROVED_KINDS", frozenset({"member_closed"}))
    pool, space, _, _, _ = world
    mail_id, context = _prepare_event(world, provider, monkeypatch, kind)
    payload = render_close_mail(context, kind=kind)
    with pool.connection() as db:
        db.execute(
            "update public.business_close_mail_outbox set first_attempt_at=clock_timestamp(),payload=%s where id=%s",
            (Jsonb(payload), mail_id),
        )
    assert deliver_close_mail(pool, space.id) == 0
    assert not provider.messages and not provider.attempts
    with pool.connection() as db:
        assert db.execute(
            "select payload,sent_at,provider_receipt from public.business_close_mail_outbox where id=%s",
            (mail_id,),
        ).fetchone() == (payload, None, None)


@pytest.mark.parametrize("kind", ALL_KINDS)
@pytest.mark.parametrize("locale", ["es-419", "en"])
def test_approved_policy_dispatches_the_matching_fake_payload_once(
    world, provider, monkeypatch, kind, locale
):  # noqa: F811
    from argus.domain.business import close_mail

    pool, space, _, _, _ = world
    mail_id, context = _prepare_event(world, provider, monkeypatch, kind)

    def localized(context, *, kind):
        return render_close_mail(context, kind=kind, locale=locale)

    if locale == "en":
        monkeypatch.setattr(close_mail, "render_close_mail", localized)
    assert deliver_close_mail(pool, space.id) == 1
    assert deliver_close_mail(pool, space.id) == 0
    assert len(provider.messages) == 1 and len(provider.attempts) == 1
    payload = render_close_mail(context, kind=kind, locale=locale)
    message = next(iter(provider.messages.values()))
    assert str(make_header(decode_header(message["Subject"]))) == payload["subject"]
    text = next(
        part for part in message.walk() if part.get_content_type() == "text/plain"
    )
    assert text.get_payload(decode=True).decode("utf-8").rstrip() == payload["text"]
    with pool.connection() as db:
        row = db.execute(
            "select first_attempt_at,payload,sent_at,provider_receipt from public.business_close_mail_outbox where id=%s",
            (mail_id,),
        ).fetchone()
    assert row[0] and row[1] == payload and row[2] and row[3]


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_approved_kind_retries_keep_the_original_payload_and_provider_key(
    world, provider, monkeypatch, kind
):  # noqa: F811
    from argus.domain.business import close_mail

    pool, space, _, _, _ = world
    mail_id, _ = _prepare_event(world, provider, monkeypatch, kind)
    outgoing = []
    original_send = close_mail.resend_email.send_resend_email

    def observe(**kwargs):
        outgoing.append(kwargs)
        return original_send(**kwargs)

    monkeypatch.setattr(close_mail.resend_email, "send_resend_email", observe)
    provider.lose_response = True
    assert deliver_close_mail(pool, space.id) == 0
    monkeypatch.setenv("CUADRAO_APP_ORIGIN", "https://changed.example.test")
    with pool.connection() as db:
        db.execute(
            "update public.business_close_mail_outbox set context=jsonb_set(context,'{businessName}','\"Changed\"') where id=%s",
            (mail_id,),
        )
    provider.lose_response = False
    assert deliver_close_mail(pool, space.id) == 1
    assert len(outgoing) == 2 and outgoing[0] == outgoing[1]
    assert len(provider.messages) == 1
    assert len(provider.attempts) == 2 and len(set(provider.attempts)) == 1


@pytest.mark.parametrize("kind", ALL_KINDS)
@pytest.mark.parametrize("stale", ["business", "recipient"])
def test_stale_approved_kind_is_suppressed_before_fake_transport(
    world, provider, monkeypatch, kind, stale
):  # noqa: F811
    pool, space, _, _, _ = world
    mail_id, _ = _prepare_event(world, provider, monkeypatch, kind)
    with pool.connection() as db:
        if stale == "recipient":
            db.execute(
                "update public.business_close_mail_outbox set recipient_email='changed@example.test' where id=%s",
                (mail_id,),
            )
        elif kind == "member_reopened":
            db.execute(
                "update public.spaces set closed_at=clock_timestamp() where id=%s",
                (space.id,),
            )
        else:
            db.execute("update public.spaces set closed_at=null where id=%s", (space.id,))
    assert deliver_close_mail(pool, space.id) == 0
    assert not provider.messages and not provider.attempts
    with pool.connection() as db:
        assert db.execute(
            "select first_attempt_at,payload,sent_at,suppressed_at is not null from public.business_close_mail_outbox where id=%s",
            (mail_id,),
        ).fetchone() == (None, None, None, True)


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_approved_kind_stops_ambiguous_retries_after_23_hours(
    world, provider, monkeypatch, kind
):  # noqa: F811
    pool, space, _, _, _ = world
    mail_id, _ = _prepare_event(world, provider, monkeypatch, kind)
    provider.lose_response = True
    assert deliver_close_mail(pool, space.id) == 0
    assert len(provider.attempts) == 1
    with pool.connection() as db:
        db.execute(
            "update public.business_close_mail_outbox set first_attempt_at=clock_timestamp()-interval '23 hours' where id=%s",
            (mail_id,),
        )
    provider.lose_response = False
    assert deliver_close_mail(pool, space.id) == 0
    assert len(provider.attempts) == 1
    with pool.connection() as db:
        assert db.execute(
            "select uncertain_at is not null,sent_at from public.business_close_mail_outbox where id=%s",
            (mail_id,),
        ).fetchone() == (True, None)


@pytest.mark.parametrize("kind", ["owner_closed", "purge_reminder"])
def test_owner_notice_is_suppressed_if_the_current_owner_changes(
    world, provider, monkeypatch, kind
):  # noqa: F811
    pool, space, people, _, _ = world
    mail_id, _ = _prepare_event(world, provider, monkeypatch, kind)
    with pool.connection() as db:
        db.execute(
            "update public.spaces set current_owner_id=%s where id=%s",
            (people["other"], space.id),
        )
    assert deliver_close_mail(pool, space.id) == 0
    assert not provider.messages and not provider.attempts
    with pool.connection() as db:
        assert db.execute(
            "select first_attempt_at,payload,suppressed_at is not null from public.business_close_mail_outbox where id=%s",
            (mail_id,),
        ).fetchone() == (None, None, True)


@pytest.mark.parametrize("kind", ALL_KINDS)
@pytest.mark.parametrize("unreachable", ["unconfirmed", "anonymous", "banned"])
def test_unreachable_recipient_is_suppressed_before_fake_transport(
    world, provider, monkeypatch, kind, unreachable
):  # noqa: F811
    pool, space, _, _, _ = world
    mail_id, _ = _prepare_event(world, provider, monkeypatch, kind)
    updates = {
        "unconfirmed": "email_confirmed_at=null",
        "anonymous": "is_anonymous=true",
        "banned": "banned_until=clock_timestamp()+interval '1 day'",
    }
    with pool.connection() as db:
        db.execute(
            "update auth.users set "
            + updates[unreachable]
            + " where id=(select recipient_id from public.business_close_mail_outbox where id=%s)",
            (mail_id,),
        )
    assert deliver_close_mail(pool, space.id) == 0
    assert not provider.messages and not provider.attempts
    with pool.connection() as db:
        assert db.execute(
            "select first_attempt_at,payload,suppressed_at is not null from public.business_close_mail_outbox where id=%s",
            (mail_id,),
        ).fetchone() == (None, None, True)
