from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
from uuid import UUID

from argus.domain.ingestion.secrets import SecretBox
from argus.domain.ingestion.whatsapp.business_capture import BusinessCaptureStore
from argus.domain.ingestion.whatsapp.business_delivery import BusinessDeliveryStore
from argus.domain.ingestion.whatsapp.business_envelope import EnvelopeCodec
from argus.domain.ingestion.whatsapp.business_outbox import BusinessOutbox
from argus.domain.ingestion.whatsapp.business_store import BusinessTurnStore
from argus.domain.ingestion.whatsapp.business_worker import (
    BusinessWhatsAppWorker,
    no_ai_consent,
)
from argus.domain.ingestion.whatsapp.identity import WhatsAppKeys


def build_worker(
    pool,
    *,
    box: SecretBox,
    keys: WhatsAppKeys,
    transport,
    enabled: Callable[[], bool],
    send_enabled: Callable[[], bool],
    actions=None,
    runner=None,
    has_consent: Callable[[UUID, UUID], bool] = no_ai_consent,
    consent=None,
) -> BusinessWhatsAppWorker:
    async def execute(
        *, captured, turn, lease, authorization, begin_reply, history
    ) -> str:
        from argus.agent_runtime.business.context import AuthorizedBusinessContext

        def require_access():
            if consent is None or not enabled():
                raise PermissionError("whatsapp_ai_consent_required")
            consent.require_access(captured, authorization, lease=lease)
            actions.plan_for_turn(authorization, captured.turn_key, lease=lease)

        context = AuthorizedBusinessContext(
            actions=actions,
            authorization=authorization,
            turn_key=captured.turn_key,
            lease=lease,
            message_id=captured.id,
            received_at=captured.received_at,
            channel="whatsapp",
            begin_reply=begin_reply,
            language=captured.language,
            require_access=require_access,
        )
        result = await runner.run(
            context=context, turn=turn, message=captured.envelope.text, history=history
        )
        return result.reply_text

    return BusinessWhatsAppWorker(
        captures=BusinessCaptureStore(pool, EnvelopeCodec(box, keys), consent),
        turns=BusinessTurnStore(pool),
        outbox=BusinessOutbox(pool),
        delivery=BusinessDeliveryStore(pool),
        transport=transport,
        actions=actions,
        execute_turn=execute if runner is not None and actions is not None else None,
        has_consent=has_consent,
        consent=consent,
        enabled=enabled,
        send_enabled=send_enabled,
    )


def start_worker(app) -> None:
    from argus.api.whatsapp import whatsapp_runtime

    existing = getattr(app.state, "business_whatsapp_worker", None)
    if existing is not None and not existing.done():
        return
    runtime = whatsapp_runtime()
    if runtime is not None and runtime.worker is not None:
        app.state.business_whatsapp_worker = asyncio.create_task(runtime.worker.run())


async def stop_worker(app) -> None:
    task = getattr(app.state, "business_whatsapp_worker", None)
    if task is not None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        app.state.business_whatsapp_worker = None
