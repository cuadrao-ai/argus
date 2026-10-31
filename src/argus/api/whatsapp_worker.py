from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
from uuid import UUID

from loguru import logger

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
from argus.domain.ingestion.whatsapp.replies import inbox_url
from argus.llm.openrouter_key_policy import openrouter_traffic_class


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
    app_origin: str | None = None,
) -> BusinessWhatsAppWorker:
    async def execute(
        *, captured, turn, lease, authorization, begin_reply, history
    ) -> str:
        from argus.domain.business.context import AuthorizedBusinessContext

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
        # Hosted environments refuse a model call without a traffic class. An
        # owner is a registered account, so its calls use the registered key.
        with openrouter_traffic_class("registered"):
            result = await runner.run(
                context=context,
                turn=turn,
                message=captured.envelope.text,
                history=history,
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
        inbox_link=inbox_url(app_origin) if app_origin else None,
    )


CLAIM_SWEEP_SECONDS = 60


async def sweep_lapsed_claims(intake, interval: float = CLAIM_SWEEP_SECONDS) -> None:  # noqa: ANN001
    """Runs whatever the document jobs switch says: a lost photo is recovered
    with background jobs on or off."""

    while True:
        try:
            await intake.recover()
        except Exception as error:
            logger.warning(
                "WhatsApp claim sweep failed", failure_mode=type(error).__name__
            )
        await asyncio.sleep(interval)


def start_worker(app) -> None:
    from argus.api.whatsapp import whatsapp_runtime

    runtime = whatsapp_runtime()
    if runtime is None:
        return
    for name, worker in (
        ("business_whatsapp_worker", runtime.worker),
        ("whatsapp_failure_reply_worker", runtime.failure_replies),
    ):
        existing = getattr(app.state, name, None)
        if worker is not None and (existing is None or existing.done()):
            setattr(app.state, name, asyncio.create_task(worker.run()))
    existing = getattr(app.state, "whatsapp_claim_sweeper", None)
    if runtime.intake is not None and (existing is None or existing.done()):
        app.state.whatsapp_claim_sweeper = asyncio.create_task(
            sweep_lapsed_claims(runtime.intake)
        )


async def stop_worker(app) -> None:
    for name in (
        "business_whatsapp_worker",
        "whatsapp_failure_reply_worker",
        "whatsapp_claim_sweeper",
    ):
        task = getattr(app.state, name, None)
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            setattr(app.state, name, None)
