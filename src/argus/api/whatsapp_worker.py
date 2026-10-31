from __future__ import annotations

import asyncio
from contextlib import suppress


def start_worker(app) -> None:
    from argus.api.whatsapp import whatsapp_runtime

    runtime = whatsapp_runtime()
    if runtime is None:
        return
    for name, worker in (("whatsapp_failure_reply_worker", runtime.failure_replies),):
        existing = getattr(app.state, name, None)
        if worker is not None and (existing is None or existing.done()):
            setattr(app.state, name, asyncio.create_task(worker.run()))


async def stop_worker(app) -> None:
    for name in ("whatsapp_failure_reply_worker",):
        task = getattr(app.state, name, None)
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            setattr(app.state, name, None)
