from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from argus.domain.business.spaces import PostgresSpaceStore
from faker import Faker
from psycopg_pool import ConnectionPool

from tests import test_financial_accounts_postgres as shared
from tests.ingestion.business_whatsapp_support import build_world

fake = Faker()
users = shared.users
pytestmark = pytest.mark.skipif(
    not shared.DSN, reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured"
)


@pytest.fixture
def world(users):
    with ConnectionPool(shared.DSN, min_size=0, max_size=4) as pool:
        space, _ = PostgresSpaceStore(pool).create(users["owner"], fake.company())
        yield build_world(pool, users["owner"], UUID(space.id))


@pytest.mark.asyncio
async def test_three_webhooks_capture_and_reply_once_and_deny_retroactive_consent(world):
    message = world.message()
    assert [world.captures.capture(message) for _ in range(3)] == [True] * 3
    assert len(world.captures.pending()) == 1
    assert await world.worker().run_once()
    assert world.states(message) == [("sent",)]
    assert len(world.transport.messages) == 1
    assert world.turns.load_turn(world.keys.message(message.id).hex()) is None
    assert not await world.worker(synthetic_consent=True).run_once()
    assert world.executor.interpretations == []


@pytest.mark.asyncio
async def test_scripted_turns_follow_capture_order_and_support_multiple_replies(world):
    first, second = world.message("Primero"), world.message("Segundo")
    world.executor.reply = "x" * 5000
    world.captures.capture(first)
    world.captures.capture(second)
    worker = world.worker(synthetic_consent=True)
    assert await worker.run_once()
    assert await worker.run_once()
    assert not await worker.run_once()
    assert world.executor.interpretations == ["Primero", "Segundo"]
    assert [len(item["text"]["body"]) for item in world.transport.messages] == [
        4096,
        904,
        4096,
        904,
    ]
    assert world.states(first) == [("sent",), ("sent",)]
    assert world.states(second) == [("sent",), ("sent",)]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["fail_before_plan", "fail_composition"])
async def test_interrupted_provider_outcome_is_never_retried(world, failure):
    setattr(world.executor, failure, True)
    message = world.message()
    world.captures.capture(message)
    assert await world.worker(synthetic_consent=True).run_once()
    assert not await world.worker(synthetic_consent=True).run_once()
    assert len(world.executor.interpretations) == 1
    assert world.executor.compositions == (failure == "fail_composition")
    assert world.transport.messages == []
    turn = world.turns.load_turn(world.keys.message(message.id).hex())
    assert turn.model_state == (
        "unknown" if failure == "fail_before_plan" else "completed"
    )


@pytest.mark.asyncio
async def test_a_failed_binding_is_a_retryable_model_failure_with_the_same_reply(world):
    from argus.agent_runtime.business.binding import BusinessBindingError

    world.executor.invalid_output = BusinessBindingError("business_target_not_in_context")
    message = world.message()
    world.captures.capture(message)
    assert await world.worker(synthetic_consent=True).run_once()
    assert [m["text"]["body"] for m in world.transport.messages] == [
        "No pude entender tu mensaje esta vez. Envíalo de nuevo, por favor."
    ]
    turn = world.turns.load_turn(world.keys.message(message.id).hex())
    assert (turn.model_state, turn.plan) == ("unknown", None)


@pytest.mark.asyncio
async def test_invalid_output_after_a_plan_exists_is_not_a_resend_request(world):
    from argus.domain.business.contracts.recovery import BusinessModelOutputInvalid

    world.executor.fail_composition = BusinessModelOutputInvalid()
    message = world.message()
    world.captures.capture(message)
    assert await world.worker(synthetic_consent=True).run_once()
    assert world.transport.messages == []
    turn = world.turns.load_turn(world.keys.message(message.id).hex())
    assert turn.plan is not None


@pytest.mark.asyncio
async def test_without_ai_consent_the_owner_hears_that_plainly_and_no_model_runs(world):
    message = world.message()
    world.captures.capture(message)
    assert await world.worker(synthetic_consent=False).run_once()
    assert world.executor.interpretations == []
    assert [m["text"]["body"] for m in world.transport.messages] == [
        "Todavía no has dado permiso para que Cuadrao lea tus mensajes con IA. "
        "Puedes activarlo en tu perfil, en App y luego WhatsApp."
    ]


@pytest.mark.asyncio
async def test_invalid_model_output_tells_the_owner_once_and_is_never_replayed(world):
    world.executor.invalid_output = True
    message = world.message()
    world.captures.capture(message)
    assert await world.worker(synthetic_consent=True).run_once()
    assert not await world.worker(synthetic_consent=True).run_once()
    assert len(world.executor.interpretations) == 1
    assert world.states(message) == [("sent",)]
    assert [m["text"]["body"] for m in world.transport.messages] == [
        "No pude entender tu mensaje esta vez. Envíalo de nuevo, por favor."
    ]
    turn = world.turns.load_turn(world.keys.message(message.id).hex())
    assert (turn.model_state, turn.plan) == ("unknown", None)
    follow_up = world.message()
    world.captures.capture(follow_up)
    world.executor.invalid_output = False
    assert await world.worker(synthetic_consent=True).run_once()
    assert len(world.executor.interpretations) == 2


@pytest.mark.asyncio
async def test_transport_unknown_never_resends_or_sends_later_chunks(world):
    world.transport.fail = True
    world.executor.reply = "x" * 5000
    message = world.message()
    world.captures.capture(message)
    assert await world.worker(synthetic_consent=True).run_once()
    assert world.states(message) == [("unknown",), ("suppressed",)]
    assert not await world.worker(synthetic_consent=True).run_once()
    assert len(world.transport.messages) == 1


@pytest.mark.asyncio
async def test_closed_window_persists_reply_and_waiting_questions_without_send(world):
    message = world.message(sent_at=datetime.now(timezone.utc) - timedelta(hours=25))
    world.captures.capture(message)
    assert await world.worker(synthetic_consent=True).run_once()
    assert world.states(message) == [("waiting_for_window",)]
    assert world.actions.waiting == [world.keys.message(message.id).hex()]
    assert world.transport.messages == []


@pytest.mark.asyncio
async def test_restart_after_plan_resumes_original_grant_and_stops_interrupted_composition(
    world,
):
    message = world.message()
    world.captures.capture(message)
    lease = world.turns.acquire(
        space_id=world.space,
        sender_hash=world.keys.sender(message.sender).hex(),
        holder=uuid4(),
        duration=timedelta(seconds=60),
    )
    captured = world.captures.read(world.keys.message(message.id), lease=lease)
    turn = world.turns.start_turn(
        turn_key=captured.turn_key, actor_id=world.owner, lease=lease
    )
    context = world.worker(synthetic_consent=True)._authorization(captured, turn)
    world.actions.persist_synthetic_plan(turn, context)
    assert world.outbox.begin_reply(captured, lease=lease) is None
    world.turns.release(lease)
    assert await world.worker(synthetic_consent=True).run_once()
    assert world.actions.resolved_grants[-1] == world.actions.grant_id
    assert world.executor.interpretations == [] and world.executor.compositions == 0
    assert world.transport.messages == []
    assert not await world.worker(synthetic_consent=True).run_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("parent", ["link", "space", "account"])
async def test_parent_deletion_purges_transport_but_link_deletion_keeps_canonical_evidence(
    world, parent
):
    message = world.message()
    world.captures.capture(message)
    await world.worker().run_once()
    with world.pool.connection() as connection:
        source = connection.execute(
            "insert into public.business_sources(space_id,kind,channel,source_key,text_content,received_at)"
            " values (%s,'message','whatsapp',%s,%s,clock_timestamp()) returning id",
            (world.space, fake.uuid4(), message.body),
        ).fetchone()[0]
        if parent == "link":
            connection.execute(
                "delete from public.whatsapp_sender_links where id=%s", (world.link,)
            )
        elif parent == "space":
            connection.execute("delete from public.spaces where id=%s", (world.space,))
        else:
            from tests.test_business_account_deletion_postgres import (
                erase_open_owner,
                release_custodian,
            )

            connection.commit()
            outcome = erase_open_owner(world.pool, world.owner)
            assert outcome.status == "done"
            assert (
                connection.execute(
                    "select 1 from auth.users where id=%s", (world.owner,)
                ).fetchone()
                is None
            )
            assert (
                connection.execute(
                    "select 1 from public.whatsapp_inbound_messages where provider_message_key=%s",
                    (world.keys.message(message.id),),
                ).fetchone()
                is None
            )
            assert (
                connection.execute(
                    "select 1 from public.whatsapp_outbox where provider_message_key=%s",
                    (world.keys.message(message.id),),
                ).fetchone()
                is None
            )
            assert connection.execute(
                "select text_content from public.business_sources where id=%s", (source,)
            ).fetchone() == (message.body,)
            release_custodian(world.space)
            return
        assert (
            connection.execute(
                "select 1 from public.whatsapp_inbound_messages where provider_message_key=%s",
                (world.keys.message(message.id),),
            ).fetchone()
            is None
        )
        assert (
            connection.execute(
                "select 1 from public.whatsapp_outbox where provider_message_key=%s",
                (world.keys.message(message.id),),
            ).fetchone()
            is None
        )
        original = connection.execute(
            "select text_content from public.business_sources where id=%s", (source,)
        ).fetchone()
        assert original == ((message.body,) if parent == "link" else None)


@pytest.mark.asyncio
async def test_original_envelope_and_settled_outbox_cannot_be_rewritten_or_erased(world):
    from psycopg.errors import CheckViolation

    message = world.message()
    world.captures.capture(message)
    await world.worker().run_once()
    key = world.keys.message(message.id)
    mutations = [
        (
            "update public.whatsapp_inbound_messages set sent_at=sent_at+interval '1 second' where provider_message_key=%s",
            (key,),
        ),
        (
            "update public.whatsapp_inbound_messages set composition_state='not_started' where provider_message_key=%s",
            (key,),
        ),
        (
            "update public.whatsapp_outbox set body='replacement' where provider_message_key=%s",
            (key,),
        ),
        (
            "update public.whatsapp_outbox set state='pending',sent_at=null where provider_message_key=%s",
            (key,),
        ),
        ("delete from public.whatsapp_outbox where provider_message_key=%s", (key,)),
    ]
    for sql, args in mutations:
        with (
            world.pool.connection() as connection,
            pytest.raises(CheckViolation),
            connection.transaction(),
        ):
            connection.execute(sql, args)
    assert world.states(message) == [("sent",)]


def test_transport_tables_are_server_only_and_truncate_is_denied(world):
    with world.pool.connection() as connection:
        assert connection.execute(
            "select relrowsecurity from pg_class where oid='public.whatsapp_outbox'::regclass"
        ).fetchone() == (True,)
        for role in ("anon", "authenticated"):
            for relation in ("whatsapp_outbox", "whatsapp_inbound_messages"):
                assert connection.execute(
                    "select has_table_privilege(%s,%s,%s)",
                    (role, f"public.{relation}", "SELECT,INSERT,UPDATE,DELETE,TRUNCATE"),
                ).fetchone() == (False,)
        assert connection.execute(
            "select has_table_privilege('service_role','public.whatsapp_outbox','SELECT,INSERT,UPDATE,DELETE')"
        ).fetchone() == (True,)
        for relation in ("whatsapp_outbox", "whatsapp_inbound_messages"):
            assert connection.execute(
                "select has_table_privilege(%s,%s,%s)",
                ("service_role", f"public.{relation}", "TRUNCATE"),
            ).fetchone() == (False,)


@pytest.mark.asyncio
async def test_sender_revocation_blocks_reply_from_old_capture(world):
    message = world.message()
    world.captures.capture(message)
    with world.pool.connection() as connection:
        connection.execute(
            "update public.whatsapp_sender_links set status='revoked',revoked_at=clock_timestamp() where id=%s",
            (world.link,),
        )
    await world.worker(synthetic_consent=True).run_once()
    assert world.states(message) == [("suppressed",)]
    assert not world.executor.interpretations and not world.transport.messages


@pytest.mark.asyncio
async def test_revoked_original_grant_suppresses_persisted_reply_without_recomposition(
    world,
):
    message = world.message()
    world.captures.capture(message)
    first = world.worker(synthetic_consent=True)
    first.transport = None
    assert await first.run_once()
    assert world.states(message) == [("pending",)]
    world.actions.revoked = True
    assert await world.worker(synthetic_consent=True).run_once()
    assert world.states(message) == [("suppressed",)]
    assert world.executor.compositions == 1 and not world.transport.messages
    assert not await world.worker(synthetic_consent=True).run_once()


@pytest.mark.asyncio
async def test_restart_after_send_started_marks_unknown_without_resending(world):
    message = world.message()
    world.captures.capture(message)
    first = world.worker()
    first.transport = None
    assert await first.run_once()
    lease = world.turns.acquire(
        space_id=world.space,
        sender_hash=world.keys.sender(message.sender).hex(),
        holder=uuid4(),
        duration=timedelta(seconds=60),
    )
    captured = world.captures.read(world.keys.message(message.id), lease=lease)
    assert (
        world.delivery.claim(captured, lease=lease, permitted=lambda: True).state
        == "sending"
    )
    world.turns.release(lease)
    assert await world.worker().run_once()
    assert world.states(message) == [("unknown",)] and not world.transport.messages
    assert not await world.worker().run_once()


@pytest.mark.asyncio
async def test_concurrent_workers_do_not_duplicate_turn_or_reply(world):
    import asyncio

    message = world.message()
    world.captures.capture(message)
    first, second = (
        world.worker(synthetic_consent=True),
        world.worker(synthetic_consent=True),
    )
    await asyncio.gather(first.run_once(), second.run_once())
    assert world.executor.interpretations == [message.body]
    assert world.executor.compositions == 1 and len(world.transport.messages) == 1
    assert world.states(message) == [("sent",)]


@pytest.mark.asyncio
async def test_consent_withdrawal_after_persisted_reply_prevents_send(world):
    message = world.message()
    world.captures.capture(message)
    first = world.worker(synthetic_consent=True)
    first.transport = None
    assert await first.run_once()
    assert world.states(message) == [("pending",)]
    assert await world.worker().run_once()
    assert world.states(message) == [("suppressed",)]
    assert world.executor.compositions == 1 and not world.transport.messages


@pytest.mark.asyncio
async def test_unreadable_envelope_quarantines_pending_delivery_without_send(world):
    from argus.domain.ingestion.secrets import SecretBox

    message = world.message()
    world.captures.capture(message)
    first = world.worker()
    first.transport = None
    await first.run_once()
    world.captures.codec.box = SecretBox(bytes(reversed(range(32))))
    assert await world.worker().run_once()
    assert world.states(message) == [("suppressed",)]
    assert not await world.worker().run_once()
    assert world.transport.messages == []


@pytest.mark.asyncio
async def test_live_outbound_switch_defers_send_without_recomposing(world):
    message = world.message()
    world.captures.capture(message)
    first = world.worker(synthetic_consent=True)
    first.send_enabled = lambda: False
    await first.run_once()
    assert world.states(message) == [("pending",)] and world.transport.messages == []
    assert await world.worker(synthetic_consent=True).run_once()
    assert world.states(message) == [("sent",)]
    assert world.executor.compositions == 1 and len(world.transport.messages) == 1


@pytest.mark.asyncio
async def test_history_uses_three_sent_canonical_pairs_in_order_and_excludes_acks_pending_unknown(
    world,
):
    from argus.domain.ingestion.whatsapp.business_history import sent_history

    ack = world.message("Sin permiso AI")
    world.captures.capture(ack)
    await world.worker().run_once()
    for index in range(4):
        world.captures.capture(world.message(f"Mensaje {index}"))
        await world.worker(synthetic_consent=True).run_once()
    world.executor.fail_before_plan = True
    world.captures.capture(world.message("Resultado desconocido"))
    await world.worker(synthetic_consent=True).run_once()
    world.executor.fail_before_plan = False
    world.captures.capture(
        world.message(
            "Ventana cerrada", sent_at=datetime.now(timezone.utc) - timedelta(hours=25)
        )
    )
    await world.worker(synthetic_consent=True).run_once()
    current = world.message("Seguimiento")
    world.captures.capture(current)
    lease = world.turns.acquire(
        space_id=world.space,
        sender_hash=world.keys.sender(current.sender).hex(),
        holder=uuid4(),
        duration=timedelta(seconds=60),
    )
    captured = world.captures.read(world.keys.message(current.id), lease=lease)
    history = sent_history(
        world.pool, captured, lease=lease, grant_id=world.actions.grant_id
    )
    assert [row["content"] for row in history if row["role"] == "user"] == [
        "Mensaje 1",
        "Mensaje 2",
        "Mensaje 3",
    ]
    assert [row["role"] for row in history] == ["user", "assistant"] * 3
    assert sum(len(row["content"].encode()) for row in history) <= 6000
    world.turns.release(lease)


@pytest.mark.asyncio
async def test_history_excludes_other_sender_and_changed_grant_issuer(world, users):
    from argus.domain.ingestion.whatsapp.business_history import sent_history
    from argus.domain.ingestion.whatsapp.payload import TextMessage

    world.captures.capture(world.message("Mensaje previo"))
    await world.worker(synthetic_consent=True).run_once()
    current = world.message("Seguimiento")
    world.captures.capture(current)
    lease = world.turns.acquire(
        space_id=world.space,
        sender_hash=world.keys.sender(current.sender).hex(),
        holder=uuid4(),
        duration=timedelta(seconds=60),
    )
    captured = world.captures.read(world.keys.message(current.id), lease=lease)
    assert sent_history(
        world.pool, captured, lease=lease, grant_id=world.actions.grant_id
    )
    with world.pool.connection() as connection:
        connection.execute(
            "update public.business_client_grants set issuer_id=%s where id=%s",
            (users["other"], world.actions.grant_id),
        )
    assert (
        sent_history(world.pool, captured, lease=lease, grant_id=world.actions.grant_id)
        == ()
    )
    world.turns.release(lease)
    with world.pool.connection() as connection:
        connection.execute(
            "update public.business_client_grants set issuer_id=%s where id=%s",
            (world.owner, world.actions.grant_id),
        )
        connection.execute(
            "update public.whatsapp_sender_links set status='revoked',revoked_at=clock_timestamp() where id=%s",
            (world.link,),
        )
        connection.execute(
            "insert into public.whatsapp_sender_links(destination_owner_id,wa_id_hash,last4,reply_language,status,linked_at) values (%s,%s,'4321','es-419','active',clock_timestamp())",
            (world.owner, world.keys.sender("15550104321")),
        )
    other = TextMessage(
        fake.uuid4(), "15550104321", datetime.now(timezone.utc), "Otro remitente"
    )
    world.captures.capture(other)
    lease = world.turns.acquire(
        space_id=world.space,
        sender_hash=world.keys.sender(other.sender).hex(),
        holder=uuid4(),
        duration=timedelta(seconds=60),
    )
    captured = world.captures.read(world.keys.message(other.id), lease=lease)
    assert (
        sent_history(world.pool, captured, lease=lease, grant_id=world.actions.grant_id)
        == ()
    )
    world.turns.release(lease)


@pytest.mark.asyncio
async def test_expiration_during_delivery_guard_rolls_back_claim(world):
    import time

    from argus.domain.ingestion.whatsapp.business_store import LeaseLost

    message = world.message()
    world.captures.capture(message)
    first = world.worker()
    first.transport = None
    await first.run_once()
    lease = world.turns.acquire(
        space_id=world.space,
        sender_hash=world.keys.sender(message.sender).hex(),
        holder=uuid4(),
        duration=timedelta(milliseconds=200),
    )
    captured = world.captures.read(world.keys.message(message.id), lease=lease)
    checked = []

    def permitted():
        checked.append(True)
        time.sleep(0.25)
        return True

    with pytest.raises(LeaseLost):
        world.delivery.claim(captured, lease=lease, permitted=permitted)
    assert checked == [True]
    assert world.states(message) == [("pending",)]
    assert world.transport.messages == []


@pytest.mark.asyncio
async def test_shutdown_cancellation_persists_unknown_and_releases_sender_lease(world):
    import asyncio

    message = world.message()
    world.captures.capture(message)
    started = asyncio.Event()

    async def interrupted(**kwargs):
        started.set()
        await asyncio.Future()

    worker = world.worker(synthetic_consent=True)
    worker.execute_turn = interrupted
    task = asyncio.create_task(worker.run_once())
    await asyncio.wait_for(started.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    turn = world.turns.load_turn(world.keys.message(message.id).hex())
    assert turn.model_state == "unknown"
    assert not await world.worker(synthetic_consent=True).run_once()
    replacement = world.turns.acquire(
        space_id=world.space,
        sender_hash=world.keys.sender(message.sender).hex(),
        holder=uuid4(),
        duration=timedelta(seconds=60),
    )
    assert replacement is not None and replacement.fence == turn.lease_fence + 1
    world.turns.release(replacement)


@pytest.mark.asyncio
async def test_interruption_marking_questions_waiting_recovers_without_recomposing(
    world, monkeypatch
):
    message = world.message(sent_at=datetime.now(timezone.utc) - timedelta(hours=25))
    world.captures.capture(message)
    original = world.actions.mark_turn_waiting_for_window

    def interrupted(*args, **kwargs):
        raise RuntimeError("synthetic interruption before question update")

    monkeypatch.setattr(world.actions, "mark_turn_waiting_for_window", interrupted)
    await world.worker(synthetic_consent=True).run_once()
    assert world.states(message) == [("pending",)]
    monkeypatch.setattr(world.actions, "mark_turn_waiting_for_window", original)
    await world.worker(synthetic_consent=True).run_once()
    assert world.states(message) == [("waiting_for_window",)]
    assert world.actions.waiting == [world.keys.message(message.id).hex()]
    assert world.executor.compositions == 1 and not world.transport.messages


@pytest.mark.asyncio
async def test_a_crash_between_saving_the_resend_reply_and_marking_unknown_replays_once(
    world,
):
    from argus.domain.ingestion.whatsapp.replies import compose_reply

    message = world.message()
    world.captures.capture(message)
    lease = _lease(world, message)
    captured = world.captures.read(world.keys.message(message.id), lease=lease)
    world.outbox.save_reply(
        captured,
        compose_reply("whatsapp_agent_unavailable", language=captured.language),
        lease=lease,
        fixed=True,
    )
    world.turns.release(lease)
    # The process died here: the reply is saved, the turn was never marked unknown.
    assert await world.worker(synthetic_consent=True).run_once()
    assert not await world.worker(synthetic_consent=True).run_once()
    assert world.executor.interpretations == []
    assert [m["text"]["body"] for m in world.transport.messages] == [
        "No pude entender tu mensaje esta vez. Envíalo de nuevo, por favor."
    ]
    assert world.states(message) == [("sent",)]


def _lease(world, message):
    from datetime import timedelta
    from uuid import uuid4

    lease = world.turns.acquire(
        space_id=world.space,
        sender_hash=world.keys.sender(message.sender).hex(),
        holder=uuid4(),
        duration=timedelta(seconds=60),
    )
    assert lease is not None
    return lease


def second_sender(world, users):
    """Another owner with a Business space and an active WhatsApp link."""

    from argus.domain.business.spaces import PostgresSpaceStore
    from argus.domain.ingestion.whatsapp.business_capture import BusinessCaptureStore
    from argus.domain.ingestion.whatsapp.payload import TextMessage

    PostgresSpaceStore(world.pool).create(users["guest"], fake.company())
    sender = "15550109876"
    with world.pool.connection() as connection:
        connection.execute(
            "insert into public.whatsapp_sender_links(destination_owner_id,wa_id_hash,last4,reply_language,status,linked_at)"
            " values (%s,%s,'9876','es-419','active',clock_timestamp())",
            (users["guest"], world.keys.sender(sender)),
        )
    assert isinstance(world.captures, BusinessCaptureStore)
    return TextMessage(
        fake.uuid4(), sender, datetime.now(timezone.utc), "Compré pintura por 420"
    )


@pytest.mark.asyncio
async def test_with_sending_off_a_saved_reply_does_not_hide_other_senders(world, users):
    first = world.message()
    world.captures.capture(first)
    sending = {"on": False}
    worker = world.worker(synthetic_consent=True)
    worker.send_enabled = lambda: sending["on"]
    assert await worker.run_once()
    assert world.states(first) == [("pending",)]
    other = second_sender(world, users)
    assert world.captures.capture(other)

    keys = [key for _, _, key in world.captures.pending(include_unsent=False)]
    assert keys == [world.keys.message(other.id)]
    assert await worker.run_once()
    assert len(world.executor.interpretations) == 2
    assert not await worker.run_once()

    sending["on"] = True
    assert world.captures.pending(include_unsent=True)
    assert await worker.run_once()
    assert await worker.run_once()
    assert not await worker.run_once()
    assert [m["text"]["body"] for m in world.transport.messages] == [
        "Guardé el borrador para revisión."
    ] * 2
    assert world.states(first) == [("sent",)] and world.states(other) == [("sent",)]
    assert not await worker.run_once() and len(world.transport.messages) == 2


@pytest.mark.asyncio
async def test_sending_switched_off_just_before_the_claim_keeps_the_reply_pending(world):
    message = world.message()
    world.captures.capture(message)
    sending = {"on": True}
    worker = world.worker(synthetic_consent=True)
    worker.send_enabled = lambda: sending["on"]
    original = worker.delivery.claim

    def switch_off_then_claim(*args, **kwargs):
        sending["on"] = False
        return original(*args, **kwargs)

    worker.delivery.claim = switch_off_then_claim
    assert await worker.run_once()
    assert world.states(message) == [("pending",)] and world.transport.messages == []
    worker.delivery.claim = original
    sending["on"] = True
    assert await worker.run_once()
    assert [m["text"]["body"] for m in world.transport.messages] == [
        "Guardé el borrador para revisión."
    ]
    assert world.states(message) == [("sent",)]
    assert not await worker.run_once() and len(world.transport.messages) == 1


@pytest.mark.asyncio
async def test_a_newer_reply_never_overtakes_an_older_saved_one(world):
    sending = {"on": False}
    worker = world.worker(synthetic_consent=True)
    worker.send_enabled = lambda: sending["on"]
    world.executor.reply = "Primera"
    first = world.message("Compré materiales por 850")
    world.captures.capture(first)
    assert await worker.run_once()
    world.executor.reply = "Segunda"
    second = world.message("Compré cemento por 300")
    world.captures.capture(second)
    assert await worker.run_once()
    assert world.states(first) == [("pending",)] and world.states(second) == [
        ("pending",)
    ]

    # A batch picked while sending was off names only the newer message.
    sending["on"] = True
    sender = world.keys.sender("15550101234").hex()
    real = worker.captures.pending
    worker.captures.pending = lambda **_: [
        (world.space, sender, world.keys.message(second.id))
    ]
    assert await worker.run_once()
    assert world.transport.messages == []
    worker.captures.pending = real
    assert await worker.run_once() and await worker.run_once()
    assert not await worker.run_once()
    assert [m["text"]["body"] for m in world.transport.messages] == ["Primera", "Segunda"]
    assert world.states(first) == [("sent",)] and world.states(second) == [("sent",)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("link", "ending"),
    [("https://app.test/biz", ": https://app.test/biz"), (None, ".")],
)
async def test_the_receipts_only_reply_carries_the_inbox_link_when_there_is_one(
    world, link, ending
):
    worker = world.worker(synthetic_consent=True)
    worker.execute_turn = None
    worker.inbox_link = link
    message = world.message()
    world.captures.capture(message)
    assert await worker.run_once()
    assert [m["text"]["body"] for m in world.transport.messages] == [
        "Aquí solo recibimos recibos. Para todo lo demás usa Cuadrao" + ending
    ]


def _outbox(world, message):
    with world.pool.connection() as db:
        return db.execute(
            "select state,error_code from public.whatsapp_outbox where provider_message_key=%s",
            (world.keys.message(message.id),),
        ).fetchall()


@pytest.mark.asyncio
async def test_consent_ending_after_the_claim_records_not_permitted_not_unknown(world):
    message = world.message()
    world.captures.capture(message)
    worker = world.worker(synthetic_consent=True)
    original = worker.delivery.claim

    def claim_then_revoke(*args, **kwargs):
        claim = original(*args, **kwargs)
        worker.has_consent = lambda *_: False
        return claim

    worker.delivery.claim = claim_then_revoke
    await worker.run_once()
    assert world.transport.messages == []
    assert _outbox(world, message) == [("unknown", "whatsapp_send_not_permitted")]


@pytest.mark.asyncio
async def test_a_failing_reply_gives_up_after_bounded_tries_and_frees_the_sender(
    world, monkeypatch
):
    from argus.domain.ingestion.whatsapp.business_worker import MAX_ATTEMPTS

    sending = {"on": False}
    worker = world.worker(synthetic_consent=True)
    worker.send_enabled = lambda: sending["on"]
    first = world.message("Compré materiales por 850")
    world.captures.capture(first)
    assert await worker.run_once()
    assert _outbox(world, first) == [("pending", None)]
    sending["on"] = True

    def broken(*_, **__):
        raise RuntimeError("synthetic outage")

    monkeypatch.setattr(world.actions, "resolve_actor", broken)
    for _ in range(MAX_ATTEMPTS - 1):
        assert await worker.run_once()
    assert _outbox(world, first) == [("pending", None)]
    assert await worker.run_once()
    assert _outbox(world, first) == [("suppressed", "whatsapp_reply_failed")]
    assert world.transport.messages == []
    monkeypatch.undo()

    world.executor.reply = "Siguiente"
    second = world.message("Compré cemento por 300")
    world.captures.capture(second)
    assert await worker.run_once()
    assert [m["text"]["body"] for m in world.transport.messages] == ["Siguiente"]


@pytest.mark.asyncio
@pytest.mark.parametrize("cause", ["store_error", "agent_off"])
async def test_a_failed_check_or_a_disabled_agent_is_not_recorded_as_not_permitted(
    world, cause
):
    message = world.message()
    world.captures.capture(message)
    worker = world.worker(synthetic_consent=True)
    original = worker.delivery.claim

    def claim_then_break(*args, **kwargs):
        claim = original(*args, **kwargs)
        if cause == "store_error":

            def broken(*_):
                raise RuntimeError("synthetic store outage")

            worker.has_consent = broken
        else:
            worker.enabled = lambda: False
        return claim

    worker.delivery.claim = claim_then_break
    await worker.run_once()
    assert world.transport.messages == []
    expected = (
        "whatsapp_send_check_failed"
        if cause == "store_error"
        else "whatsapp_send_disabled"
    )
    assert _outbox(world, message) == [("unknown", expected)]


@pytest.mark.asyncio
async def test_a_give_up_that_fails_is_logged_and_tried_again_on_the_next_failure(
    world, monkeypatch
):
    from argus.domain.ingestion.whatsapp.business_worker import MAX_ATTEMPTS
    from loguru import logger

    seen = []
    sink = logger.add(lambda m: seen.append(m.record), level="ERROR")
    sending = {"on": False}
    worker = world.worker(synthetic_consent=True)
    worker.send_enabled = lambda: sending["on"]
    message = world.message()
    world.captures.capture(message)
    assert await worker.run_once()
    sending["on"] = True
    monkeypatch.setattr(
        world.actions,
        "resolve_actor",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError()),
    )
    real = worker.delivery.give_up

    def failing(*args, **kwargs):
        raise RuntimeError("synthetic give-up outage")

    worker.delivery.give_up = failing
    for _ in range(MAX_ATTEMPTS):
        await worker.run_once()
    assert [r["extra"]["event"] for r in seen] == ["business_whatsapp_give_up_failed"]
    assert _outbox(world, message) == [("pending", None)]
    worker.delivery.give_up = real
    await worker.run_once()
    logger.remove(sink)
    assert [r["extra"]["event"] for r in seen] == [
        "business_whatsapp_give_up_failed",
        "business_whatsapp_given_up",
    ]
    assert _outbox(world, message) == [("suppressed", "whatsapp_reply_failed")]
