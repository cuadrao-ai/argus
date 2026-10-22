from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from email import message_from_string

import pytest
from argus.domain import resend_email
from argus.domain.business.lifecycle import BusinessLifecycleError
from argus.domain.business.transfer import PostgresBusinessTransfer
from argus.domain.business.transfer_mail import deliver_transfer_mail

from tests import test_business_lifecycle_postgres as lifecycle
from tests import test_financial_accounts_postgres as shared

world = lifecycle.world
users = lifecycle.users
pytestmark = pytest.mark.skipif(not shared.DSN, reason="Disposable database required")


@pytest.fixture
def provider(monkeypatch):
    class SMTP:
        messages = {}
        attempts = []
        lose_response = False

        def __init__(self, *args, **kwargs):
            assert args == ("smtp.resend.com", 465)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def login(self, user, password):
            assert (user, password) == ("resend", "synthetic-only")

        def mail(self, sender):
            assert sender == "no-responder@mail.cuadrao.ai"
            return 250, b"ok"

        def rcpt(self, recipient):
            return 250, b"ok"

        def data(self, raw):
            message = message_from_string(raw)
            assert message["Reply-To"] == "hola@cuadrao.ai"
            key = message["Resend-Idempotency-Key"]
            self.attempts.append(key)
            self.messages.setdefault(key, message)
            if self.lose_response:
                raise OSError("Synthetic lost provider response")
            return 250, b"synthetic receipt"

    monkeypatch.setenv(resend_email.SMTP_PASSWORD_ENV, "synthetic-only")
    monkeypatch.setenv("CUADRAO_APP_ORIGIN", "https://app.example.test")
    monkeypatch.setenv("CUADRAO_EMAIL_ASSET_ORIGIN", "https://images.example.test")
    monkeypatch.setattr(resend_email.smtplib, "SMTP_SSL", SMTP)
    return SMTP


def request(world, key="mail-request"):
    pool, space, people, _, member = world
    with pool.connection() as db:
        db.execute(
            "update auth.users set email_confirmed_at=now() where id=%s",
            (people["owner"],),
        )
    return PostgresBusinessTransfer(pool).request(
        owner_id=people["owner"],
        space_id=space.id,
        target_grant_id=member.id,
        confirmation=space.name,
        idempotency_key=key,
    )


def expire(world, transfer):
    pool, _, _, _, _ = world
    with pool.connection() as db:
        db.execute(
            "alter table public.business_ownership_transfers disable trigger business_transfer_immutable"
        )
        db.execute(
            "update public.business_ownership_transfers set created_at=statement_timestamp()-interval '8 days',expires_at=statement_timestamp()-interval '8 days'+interval '168 hours' where id=%s",
            (transfer.id,),
        )
        db.execute(
            "alter table public.business_ownership_transfers enable trigger business_transfer_immutable"
        )


@pytest.mark.parametrize(
    "action,variants",
    (
        ("accept", {"requested", "acceptedOwner", "acceptedTarget"}),
        ("decline", {"requested", "declined"}),
        ("cancel", {"requested", "withdrawn"}),
    ),
)
def test_real_command_path_sends_each_event_once_to_its_recipient(
    world, provider, action, variants
):
    pool, space, people, _, _ = world
    transfer = request(world)
    assert request(world) == transfer
    service = PostgresBusinessTransfer(pool)
    args = {
        "owner_id" if action == "cancel" else "actor_id": people[
            "owner" if action == "cancel" else "other"
        ],
        "transfer_id": transfer.id,
    }
    resolved = getattr(service, action)(**args)
    assert getattr(service, action)(**args) == resolved
    assert deliver_transfer_mail(pool, transfer.id) == 0
    with pool.connection() as db:
        rows = db.execute(
            "select variant,recipient_id::text,recipient_email,sent_at from public.business_transfer_mail_outbox where transfer_id=%s",
            (transfer.id,),
        ).fetchall()
        assert {row[0] for row in rows} == variants
        assert all(row[3] is not None for row in rows)
        for variant, recipient, email, _ in rows:
            assert (
                recipient
                == people[
                    "owner" if variant in ("declined", "acceptedOwner") else "other"
                ]
            )
            assert any(message["To"] == email for message in provider.messages.values())
        owner = db.execute(
            "select current_owner_id::text from public.spaces where id=%s", (space.id,)
        ).fetchone()[0]
        assert owner == people["other" if action == "accept" else "owner"]
    assert len(provider.attempts) == len(variants) == len(provider.messages)


def test_lost_response_retries_same_payload_key_and_committed_reservation(
    world, provider
):
    provider.lose_response = True
    transfer = request(world)
    pool, _, people, _, _ = world
    assert len(provider.messages) == 1
    with pool.connection() as db:
        first = db.execute(
            "select first_attempt_at,payload,sent_at from public.business_transfer_mail_outbox where transfer_id=%s",
            (transfer.id,),
        ).fetchone()
        assert first[0] is not None and first[1] and first[2] is None
        db.execute(
            "update public.profiles set display_name='Changed after event' where id=%s",
            (people["owner"],),
        )
    provider.lose_response = False
    with ThreadPoolExecutor(max_workers=4) as workers:
        sent = list(
            workers.map(lambda _: deliver_transfer_mail(pool, transfer.id), range(4))
        )
    assert sum(sent) == 1 and len(provider.messages) == 1 and len(provider.attempts) == 2
    with pool.connection() as db:
        assert (
            db.execute(
                "select first_attempt_at,payload from public.business_transfer_mail_outbox where transfer_id=%s",
                (transfer.id,),
            ).fetchone()
            == first[:2]
        )


def test_late_ambiguous_retry_stops_before_provider_key_expires(world, provider):
    provider.lose_response = True
    transfer = request(world)
    pool, _, _, _, _ = world
    with pool.connection() as db:
        db.execute(
            "update public.business_transfer_mail_outbox set first_attempt_at=clock_timestamp()-interval '23 hours' where transfer_id=%s",
            (transfer.id,),
        )
    provider.lose_response = False
    assert deliver_transfer_mail(pool, transfer.id) == 0
    assert len(provider.attempts) == 1
    with pool.connection() as db:
        assert db.execute(
            "select uncertain_at is not null from public.business_transfer_mail_outbox where transfer_id=%s",
            (transfer.id,),
        ).fetchone()[0]


def test_expiry_is_exactly_seven_days_sends_nothing_rejects_accept_and_allows_new_request(
    world, provider, monkeypatch
):
    monkeypatch.delenv(resend_email.SMTP_PASSWORD_ENV)
    transfer = request(world)
    pool, space, people, _, _ = world
    with pool.connection() as db:
        created, expires = db.execute(
            "select created_at,expires_at from public.business_ownership_transfers where id=%s",
            (transfer.id,),
        ).fetchone()
        assert expires == created + timedelta(days=7) == transfer.expires_at
    expire(world, transfer)
    service = PostgresBusinessTransfer(pool)
    assert service.discover(actor_id=people["owner"])[0].status == "expired"
    assert service.discover(actor_id=people["guest"]) == ()
    with pytest.raises(BusinessLifecycleError, match="business_transfer_expired"):
        service.accept(actor_id=people["other"], transfer_id=transfer.id)
    monkeypatch.setenv(resend_email.SMTP_PASSWORD_ENV, "synthetic-only")
    assert deliver_transfer_mail(pool, transfer.id) == 0 and not provider.messages
    fresh = request(world, key="after-expiry")
    assert (
        fresh.id != transfer.id
        and fresh.status == "pending"
        and len(provider.messages) == 1
    )
    with pool.connection() as db:
        assert (
            db.execute(
                "select current_owner_id::text from public.spaces where id=%s",
                (space.id,),
            ).fetchone()[0]
            == people["owner"]
        )
        assert (
            db.execute(
                "select status from public.business_ownership_transfers where id=%s",
                (transfer.id,),
            ).fetchone()[0]
            == "expired"
        )


def test_missing_provider_configuration_saves_event_without_any_smtp_call(
    world, provider, monkeypatch
):
    monkeypatch.delenv(resend_email.SMTP_PASSWORD_ENV)
    transfer = request(world)
    assert not provider.attempts
    pool, _, _, _, _ = world
    with pool.connection() as db:
        assert db.execute(
            "select first_attempt_at from public.business_transfer_mail_outbox where transfer_id=%s",
            (transfer.id,),
        ).fetchone() == (None,)


def test_transfer_mail_table_has_no_client_privileges(world):
    pool, _, _, _, _ = world
    with pool.connection() as db:
        for role in ("anon", "authenticated"):
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                assert not db.execute(
                    "select has_table_privilege(%s,'public.business_transfer_mail_outbox',%s)",
                    (role, privilege),
                ).fetchone()[0]


def test_auth_deletion_cannot_leave_an_outbox_recipient_behind(world):
    import psycopg

    pool, _, people, _, _ = world
    request(world)
    with pool.connection() as db:
        with pytest.raises(
            psycopg.errors.CheckViolation,
            match="business_custody_identity_detachment_required",
        ):
            db.execute("delete from auth.users where id=%s", (people["other"],))


def test_concurrent_duplicate_requests_send_one_recipient_message(world, provider):
    with ThreadPoolExecutor(max_workers=4) as workers:
        results = tuple(workers.map(lambda _: request(world), range(4)))
    assert len({row.id for row in results}) == 1
    assert len(provider.messages) == len(provider.attempts) == 1


def test_discovery_rechecks_live_grant_and_does_not_grant_access(world):
    pool, _, people, access, member = world
    request(world)
    service = PostgresBusinessTransfer(pool)
    found = service.discover(actor_id=people["other"])
    assert (
        len(found) == 1 and found[0].grant_id == member.id and found[0].role == "target"
    )
    access.revoke_grant(found[0].space_id, people["owner"], member.id)
    assert service.discover(actor_id=people["other"]) == ()
    assert service.discover(actor_id=people["guest"]) == ()


def test_expiry_between_reservation_and_send_still_suppresses_request(
    world, provider, monkeypatch
):
    from time import sleep

    from argus.domain.business import transfer_mail

    monkeypatch.delenv(resend_email.SMTP_PASSWORD_ENV)
    transfer = request(world)
    pool, _, _, _, _ = world
    with pool.connection() as db:
        db.execute(
            "alter table public.business_ownership_transfers disable trigger business_transfer_immutable"
        )
        db.execute(
            "update public.business_ownership_transfers set created_at=statement_timestamp()-interval '168 hours'+interval '2 seconds',expires_at=statement_timestamp()+interval '2 seconds' where id=%s",
            (transfer.id,),
        )
        db.execute(
            "alter table public.business_ownership_transfers enable trigger business_transfer_immutable"
        )
    monkeypatch.setenv(resend_email.SMTP_PASSWORD_ENV, "synthetic-only")
    render = transfer_mail.render_transfer_mail

    def expire_during_render(variant, context):
        sleep(2.1)
        return render(variant, context)

    monkeypatch.setattr(transfer_mail, "render_transfer_mail", expire_during_render)
    pool, _, _, _, _ = world
    assert deliver_transfer_mail(pool, transfer.id) == 0
    assert not provider.attempts
    with pool.connection() as db:
        assert db.execute(
            "select first_attempt_at is not null,suppressed_at is not null from public.business_transfer_mail_outbox where transfer_id=%s",
            (transfer.id,),
        ).fetchone() == (True, True)


@pytest.mark.parametrize("other_action", ("decline", "cancel"))
def test_racing_terminal_commands_mail_only_the_winning_resolution(
    world, provider, other_action
):
    transfer = request(world)
    pool, _, people, _, _ = world
    service = PostgresBusinessTransfer(pool)

    def resolve(action):
        try:
            return getattr(service, action)(
                **{
                    "owner_id" if action == "cancel" else "actor_id": people[
                        "owner" if action == "cancel" else "other"
                    ],
                    "transfer_id": transfer.id,
                }
            ).status
        except BusinessLifecycleError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = tuple(workers.map(resolve, ("accept", other_action)))
    assert results.count("business_transfer_not_pending") == 1
    expected = (
        {"requested", "acceptedOwner", "acceptedTarget"}
        if "accepted" in results
        else {"requested", "declined" if other_action == "decline" else "withdrawn"}
    )
    with pool.connection() as db:
        assert {
            r[0]
            for r in db.execute(
                "select variant from public.business_transfer_mail_outbox where transfer_id=%s",
                (transfer.id,),
            )
        } == expected
    assert len(provider.messages) == len(provider.attempts) == len(expected)
