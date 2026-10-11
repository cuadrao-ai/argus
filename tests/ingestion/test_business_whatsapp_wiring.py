import asyncio
from types import SimpleNamespace

import pytest
from argus.api.whatsapp_worker import start_worker, stop_worker
from argus.domain.ingestion.whatsapp.payload import Delivery, TextMessage

from tests.ingestion.test_whatsapp_intake import _world
from tests.ingestion.whatsapp_support import ALICE_PHONE


def test_factory_binds_canonical_actions_without_creating_consent(monkeypatch):
    import httpx
    from argus.api.whatsapp import build_whatsapp
    from argus.domain.ingestion.reconcile.service import ReconciliationService
    from argus.domain.ingestion.secrets import SecretBox
    from argus.domain.ingestion.whatsapp.config import load_whatsapp_settings

    from tests.ingestion.whatsapp_support import ENV

    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    route = {"gateway": "openrouter", "interpretation": [], "reply": []}
    monkeypatch.setattr(
        "argus.agent_runtime.business.runner.business_provider_route",
        lambda: route,
        raising=False,
    )
    sink = object.__new__(ReconciliationService)
    pool, runner = object(), object()
    documents = SimpleNamespace(
        hub=SimpleNamespace(
            sink=sink, box=SecretBox(bytes(range(32))), clock=lambda: None
        )
    )
    runtime = build_whatsapp(
        load_whatsapp_settings(),
        documents=documents,
        spaces=object(),
        store=object(),
        client=httpx.AsyncClient(),
        pool=pool,
        runner=runner,
    )
    assert runtime.worker.actions.imports is sink
    assert runtime.worker.actions.authority.pool is pool
    assert runtime.worker.consent is runtime.consent is runtime.worker.captures.consent
    assert not runtime.worker.has_consent(None, None)
    assert runtime.worker.execute_turn is not None


@pytest.mark.asyncio
async def test_adapter_passes_capture_bound_guard_to_runner(monkeypatch):
    from uuid import uuid4

    from argus.api.whatsapp_worker import build_worker
    from argus.domain.ingestion.secrets import SecretBox
    from argus.domain.ingestion.whatsapp.identity import WhatsAppKeys

    calls = []
    consent = SimpleNamespace(
        require_access=lambda captured, authorization, *, lease: calls.append(
            (captured, authorization, lease)
        )
    )
    actions = SimpleNamespace(plan_for_turn=lambda *args, **kwargs: None)

    class Runner:
        async def run(self, *, context, **kwargs):
            context.require_access()
            return SimpleNamespace(reply_text="Synthetic response")

    monkeypatch.setattr(
        "argus.agent_runtime.business.context.AuthorizedBusinessContext", SimpleNamespace
    )
    worker = build_worker(
        object(),
        box=SecretBox(bytes(range(32))),
        keys=WhatsAppKeys("synthetic-key"),
        transport=None,
        enabled=lambda: True,
        send_enabled=lambda: False,
        actions=actions,
        runner=Runner(),
        consent=consent,
    )
    captured = SimpleNamespace(
        id=uuid4(),
        turn_key="synthetic",
        received_at=None,
        language="es-419",
        envelope=SimpleNamespace(text="Original"),
    )
    authorization, lease = object(), object()
    reply = await worker.execute_turn(
        captured=captured,
        turn=object(),
        lease=lease,
        authorization=authorization,
        begin_reply=lambda: None,
        history=(),
    )
    assert reply == "Synthetic response"
    assert calls == [(captured, authorization, lease)]


@pytest.mark.asyncio
async def test_intake_defers_durable_text_reply_to_worker():
    world = _world()
    await world.link(world.alice, ALICE_PHONE)
    before = len(world.transport.sent)
    captured = []

    def capture(message):
        captured.append(message)
        return True

    world.intake.capture_text = capture
    message = TextMessage(
        "wamid.synthetic-durable", ALICE_PHONE, world.clock.now, "Compré materiales"
    )
    await world.intake.handle(Delivery((message,), 0, 0, 0))
    assert captured == [message]
    assert world.record(message.id) is None
    assert len(world.transport.sent) == before


@pytest.mark.asyncio
async def test_worker_lifecycle_has_one_owned_task_and_awaits_shutdown(monkeypatch):
    started, stopped = asyncio.Event(), asyncio.Event()

    class Worker:
        async def run(self):
            started.set()
            try:
                await asyncio.Future()
            finally:
                stopped.set()

    monkeypatch.setattr(
        "argus.api.whatsapp.whatsapp_runtime", lambda: SimpleNamespace(worker=Worker())
    )
    app = SimpleNamespace(state=SimpleNamespace())
    start_worker(app)
    original = app.state.business_whatsapp_worker
    start_worker(app)
    assert app.state.business_whatsapp_worker is original
    await asyncio.wait_for(started.wait(), timeout=1)
    await stop_worker(app)
    assert stopped.is_set() and original.done()
    assert app.state.business_whatsapp_worker is None
    await stop_worker(app)
