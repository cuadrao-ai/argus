import asyncio
from types import SimpleNamespace

import pytest
from argus.api.whatsapp_worker import start_worker, stop_worker
from argus.domain.ingestion.whatsapp.payload import Delivery, TextMessage

from tests.ingestion.test_whatsapp_intake import _world
from tests.ingestion.whatsapp_support import ALICE_PHONE


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
