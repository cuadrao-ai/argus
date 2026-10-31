import asyncio
from types import SimpleNamespace

import pytest
from argus.api.whatsapp_worker import start_worker, stop_worker


@pytest.mark.asyncio
async def test_failure_reply_worker_has_one_owned_task_and_awaits_shutdown(monkeypatch):
    started, stopped = asyncio.Event(), asyncio.Event()

    class Worker:
        async def run(self):
            started.set()
            try:
                await asyncio.Future()
            finally:
                stopped.set()

    monkeypatch.setattr(
        "argus.api.whatsapp.whatsapp_runtime",
        lambda: SimpleNamespace(failure_replies=Worker()),
    )
    app = SimpleNamespace(state=SimpleNamespace())
    start_worker(app)
    original = app.state.whatsapp_failure_reply_worker
    start_worker(app)
    assert app.state.whatsapp_failure_reply_worker is original
    await asyncio.wait_for(started.wait(), timeout=1)
    await stop_worker(app)
    assert stopped.is_set() and original.done()
    assert app.state.whatsapp_failure_reply_worker is None
    await stop_worker(app)


@pytest.mark.asyncio
async def test_without_a_runtime_no_worker_starts():
    import argus.api.whatsapp as whatsapp

    whatsapp.configure_whatsapp(None)
    app = SimpleNamespace(state=SimpleNamespace())
    start_worker(app)
    assert not hasattr(app.state, "whatsapp_failure_reply_worker")
