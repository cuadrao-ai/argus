from datetime import datetime, timedelta, timezone

import pytest
from argus.agent_runtime.business.interpretation import BusinessInterpretation
from argus.agent_runtime.business.runner import BusinessTurnRunner
from argus.api.whatsapp_worker import build_worker
from argus.domain.business.actions import BusinessActions
from argus.domain.ingestion.reconcile.service import ReconciliationService
from argus.domain.ingestion.reconcile.store_postgres import PostgresImportStore
from argus.domain.ingestion.secrets import SecretBox
from argus.domain.recording.money_service import MoneyService
from argus.domain.recording.postgres_repository import PostgresFinancialAccountRepository
from argus.domain.recording.service import FinancialAccountService

from tests import test_business_whatsapp_transport_postgres as transport_pg
from tests.test_business_runtime_postgres import activity_plan

users = transport_pg.users
world = transport_pg.world
pytestmark = transport_pg.pytestmark


class ScriptedInterpreter:
    def __init__(self):
        self.inputs = []
        self.compositions = 0
        self.fail_interpretation = False
        self.fail_composition = False

    async def ainterpret_business(self, payload):
        self.inputs.append(payload)
        if self.fail_interpretation:
            raise RuntimeError("synthetic interpretation interruption")
        return BusinessInterpretation(plan=activity_plan(payload))

    async def acompose_business(self, payload):
        self.compositions += 1
        if self.fail_composition:
            raise RuntimeError("synthetic composition interruption")
        assert payload["saved_state"]["dossiers"][0]["version"] == 2
        return "Guardé el borrador. ¿Qué día compraste los materiales?"


@pytest.fixture
def runtime(world):
    money = MoneyService(
        FinancialAccountService(PostgresFinancialAccountRepository(world.pool))
    )
    actions = BusinessActions(
        world.pool,
        ReconciliationService(
            PostgresImportStore(world.pool), money, lambda: datetime.now(timezone.utc)
        ),
    )
    interpreter = ScriptedInterpreter()
    consent = [True]

    def worker(*, sending=True, with_consent=True):
        options = {"has_consent": lambda space, actor: consent[0]} if with_consent else {}
        return build_worker(
            world.pool,
            box=SecretBox(bytes(range(32))),
            keys=world.keys,
            transport=world.transport,
            enabled=lambda: True,
            send_enabled=lambda: sending,
            actions=actions,
            runner=BusinessTurnRunner(interpreter=interpreter),
            **options,
        )

    return worker, interpreter, consent


def recorded_counts(world):
    with world.pool.connection() as db:
        return tuple(
            db.execute(sql, (world.space,)).fetchone()[0]
            for sql in (
                "select count(*) from business_sources where space_id=%s",
                "select count(*) from financial_import_events where owner_space_id=%s",
                "select count(*) from business_action_receipts where space_id=%s",
                "select count(*) from financial_records where owner_space_id=%s",
            )
        )


@pytest.mark.asyncio
async def test_actual_graph_actions_and_outbox_replay_one_original_message(
    world, runtime
):
    worker, interpreter, _ = runtime
    message = world.message("Pagué  850 por materiales con mi dinero.")
    assert all(world.captures.capture(message) for _ in range(3))
    assert await worker(sending=False).run_once()
    assert world.states(message) == [("pending",)]
    turn = world.turns.load_turn(world.keys.message(message.id).hex())
    assert turn.plan_actor.grant_id == world.actions.grant_id
    assert len(turn.plan.actions) == 3 and turn.phase == "reply_pending"
    assert recorded_counts(world) == (1, 1, 3, 0)
    assert await worker().run_once()
    assert not await worker().run_once()
    assert world.states(message) == [("sent",)]
    resumed = world.turns.load_turn(turn.turn_key)
    assert resumed.lease_fence == turn.lease_fence + 1
    assert resumed.plan_actor == turn.plan_actor and resumed.plan == turn.plan
    assert len(interpreter.inputs) == interpreter.compositions == 1
    assert len(world.transport.messages) == 1
    assert recorded_counts(world) == (1, 1, 3, 0)
    with world.pool.connection() as db:
        assert (
            db.execute(
                "select text_content from business_sources where space_id=%s",
                (world.space,),
            ).fetchone()[0]
            == message.body
        )
        rows = db.execute(
            "select actor from business_action_receipts where space_id=%s", (world.space,)
        ).fetchall()
        assert all(row[0] == turn.plan_actor.model_dump(mode="json") for row in rows)


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["interpretation", "composition"])
async def test_actual_graph_interrupted_provider_is_not_reinvoked(world, runtime, phase):
    worker, interpreter, _ = runtime
    setattr(interpreter, f"fail_{phase}", True)
    message = world.message()
    world.captures.capture(message)
    assert await worker().run_once()
    assert not await worker().run_once()
    assert len(interpreter.inputs) == 1
    assert interpreter.compositions == (phase == "composition")
    assert world.transport.messages == []
    assert recorded_counts(world) == (
        (1, 0, 0, 0) if phase == "interpretation" else (1, 1, 3, 0)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("withdrawal", ["consent", "grant"])
async def test_actual_pending_reply_rechecks_live_authority(world, runtime, withdrawal):
    worker, interpreter, consent = runtime
    message = world.message()
    world.captures.capture(message)
    assert await worker(sending=False).run_once()
    if withdrawal == "consent":
        consent[0] = False
    else:
        with world.pool.connection() as db:
            db.execute(
                "update business_client_grants set revoked_at=clock_timestamp() where id=%s",
                (world.actions.grant_id,),
            )
    assert await worker().run_once()
    assert world.states(message) == [("suppressed",)]
    assert not await worker().run_once()
    assert world.transport.messages == []
    assert len(interpreter.inputs) == interpreter.compositions == 1
    assert recorded_counts(world) == (1, 1, 3, 0)


@pytest.mark.asyncio
async def test_actual_closed_window_questions_and_unknown_send_are_not_retried(
    world, runtime
):
    worker, interpreter, _ = runtime
    old = world.message(sent_at=datetime.now(timezone.utc) - timedelta(hours=25))
    world.captures.capture(old)
    assert await worker().run_once()
    assert world.states(old) == [("waiting_for_window",)]
    with world.pool.connection() as db:
        assert db.execute(
            "select state from business_questions where space_id=%s", (world.space,)
        ).fetchall() == [("waiting_for_window",)]
    fresh = world.message()
    world.captures.capture(fresh)
    world.transport.fail = True
    assert await worker().run_once()
    assert world.states(fresh) == [("unknown",)]
    assert not await worker().run_once()
    assert len(world.transport.messages) == 1
    assert len(interpreter.inputs) == interpreter.compositions == 2
    assert interpreter.inputs[1]["history"] == []
    assert recorded_counts(world) == (2, 2, 6, 0)


@pytest.mark.asyncio
async def test_actual_graph_receives_only_completed_conversation_history(world, runtime):
    worker, interpreter, _ = runtime
    first, second = world.message("Primero pagué 850"), world.message("Luego pagué 850")
    world.captures.capture(first)
    world.captures.capture(second)
    assert await worker().run_once()
    assert await worker().run_once()
    assert [item["message"] for item in interpreter.inputs] == [first.body, second.body]
    history = interpreter.inputs[1]["history"]
    assert [(item["role"], item["content"]) for item in history] == [
        ("user", first.body),
        ("assistant", world.transport.messages[0]["text"]["body"]),
    ]


@pytest.mark.asyncio
async def test_actual_dependencies_do_not_enable_model_without_explicit_consent(
    world, runtime
):
    worker, interpreter, _ = runtime
    message = world.message()
    world.captures.capture(message)
    assert await worker(with_consent=False).run_once()
    assert world.states(message) == [("sent",)]
    assert not await worker().run_once()
    assert interpreter.inputs == [] and interpreter.compositions == 0
    assert recorded_counts(world) == (0, 0, 0, 0)
