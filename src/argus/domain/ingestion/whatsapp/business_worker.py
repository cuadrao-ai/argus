from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import timedelta
from typing import Any, Protocol
from uuid import UUID, uuid4

from loguru import logger
from pydantic import ValidationError

from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.contracts.recovery import (
    BusinessModelOutputInvalid,
    DurableTurn,
    SenderLease,
)
from argus.domain.ingestion.secrets import SecretUnreadable
from argus.domain.ingestion.whatsapp.business_capture import (
    BusinessCaptureStore,
    CapturedText,
)
from argus.domain.ingestion.whatsapp.business_delivery import BusinessDeliveryStore
from argus.domain.ingestion.whatsapp.business_history import sent_history
from argus.domain.ingestion.whatsapp.business_outbox import BusinessOutbox
from argus.domain.ingestion.whatsapp.business_store import BusinessTurnStore, LeaseLost
from argus.domain.ingestion.whatsapp.replies import (
    ReplyTransport,
    compose_reply,
    reply_payload,
)


class TurnExecutor(Protocol):
    async def __call__(
        self,
        *,
        captured: CapturedText,
        turn: DurableTurn,
        lease: SenderLease,
        authorization: Any,
        begin_reply: Callable[[], str | None],
        history: tuple[dict[str, str], ...],
    ) -> str: ...


class WorkerActions(Protocol):
    def resolve_actor(
        self, actor: TrustedActor, *, grant_id: UUID | None = None
    ) -> Any: ...
    def plan_for_turn(self, context: Any, key: str, *, lease: SenderLease) -> Any: ...
    def mark_turn_waiting_for_window(
        self, context: Any, key: str, *, lease: SenderLease
    ) -> None: ...


def no_ai_consent(space_id: UUID, actor_id: UUID) -> bool:
    return False


class BusinessWhatsAppWorker:
    def __init__(
        self,
        *,
        captures: BusinessCaptureStore,
        turns: BusinessTurnStore,
        outbox: BusinessOutbox,
        delivery: BusinessDeliveryStore,
        transport: ReplyTransport | None,
        actions: WorkerActions | None = None,
        execute_turn: TurnExecutor | None = None,
        has_consent: Callable[[UUID, UUID], bool] = no_ai_consent,
        consent=None,
        enabled: Callable[[], bool] = lambda: True,
        send_enabled: Callable[[], bool] = lambda: True,
    ) -> None:
        self.captures, self.turns, self.outbox, self.delivery = (
            captures,
            turns,
            outbox,
            delivery,
        )
        self.transport, self.actions, self.execute_turn = transport, actions, execute_turn
        self.has_consent, self.enabled = has_consent, enabled
        self.consent = consent
        self.send_enabled = send_enabled
        self.holder = uuid4()

    async def run_once(self) -> bool:
        if not self.enabled():
            return False
        candidates = await asyncio.to_thread(self.captures.pending)
        for space_id, sender_hash, key in candidates:
            lease = await asyncio.to_thread(
                self.turns.acquire,
                space_id=space_id,
                sender_hash=sender_hash,
                holder=self.holder,
                duration=timedelta(seconds=120),
            )
            if lease is None:
                continue
            try:
                await asyncio.wait_for(self._process(key, lease), timeout=90)
            except Exception as error:
                logger.warning(
                    "Business WhatsApp worker interrupted",
                    failure_mode=type(error).__name__,
                )
            finally:
                await asyncio.to_thread(self.turns.release, lease)
            return True
        return False

    async def run(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception as error:
                logger.warning(
                    "Business WhatsApp worker unavailable",
                    failure_mode=type(error).__name__,
                )
            await asyncio.sleep(1)

    async def _process(self, key: bytes, lease: SenderLease) -> None:
        try:
            captured = await asyncio.to_thread(self.captures.read, key, lease=lease)
        except (SecretUnreadable, ValidationError):
            await asyncio.to_thread(self.captures.quarantine, key, lease=lease)
            await asyncio.to_thread(
                self.turns.mark_model_unknown, turn_key=key.hex(), lease=lease
            )
            return
        turn = await asyncio.to_thread(self.turns.load_turn, captured.turn_key)
        context = None
        try:
            if captured.composition_state != "completed":
                permitted = await asyncio.to_thread(self._may_interpret, captured, lease)
                if not permitted:
                    if turn is not None:
                        await asyncio.to_thread(
                            self.outbox.mark_unknown, captured, lease=lease
                        )
                        return
                    missing = await asyncio.to_thread(
                        self._consent_missing, captured, lease
                    )
                    await asyncio.to_thread(
                        self.outbox.save_reply,
                        captured,
                        compose_reply(
                            "whatsapp_ai_consent_missing"
                            if missing
                            else "whatsapp_receipt_missing",
                            language=captured.language,
                        ),
                        lease=lease,
                        fixed=True,
                    )
                else:
                    context = await asyncio.to_thread(self._authorization, captured, turn)
                    turn = await asyncio.to_thread(
                        self.turns.start_turn,
                        turn_key=captured.turn_key,
                        actor_id=captured.owner_id,
                        lease=lease,
                    )
                    await asyncio.to_thread(
                        self.actions.plan_for_turn,
                        context,
                        captured.turn_key,
                        lease=lease,
                    )

                    def begin_reply() -> str | None:
                        if not self._may_interpret(captured, lease):
                            raise PermissionError("whatsapp_ai_consent_required")
                        self.actions.plan_for_turn(
                            context, captured.turn_key, lease=lease
                        )
                        return self.outbox.begin_reply(captured, lease=lease)

                    history = await asyncio.to_thread(
                        sent_history,
                        self.captures.pool,
                        captured,
                        lease=lease,
                        grant_id=context.grant_id,
                    )
                    try:
                        reply = await self.execute_turn(
                            captured=captured,
                            turn=turn,
                            lease=lease,
                            authorization=context,
                            begin_reply=begin_reply,
                            history=history,
                        )
                    except BusinessModelOutputInvalid:
                        await self._model_output_invalid(captured, lease)
                        await self._send(captured, None, None, lease)
                        return
                    await asyncio.to_thread(
                        self.outbox.save_reply, captured, reply, lease=lease
                    )
            elif self.actions is not None and turn is not None:
                context = await asyncio.to_thread(self._authorization, captured, turn)
                turn = await asyncio.to_thread(
                    self.turns.start_turn,
                    turn_key=captured.turn_key,
                    actor_id=captured.owner_id,
                    lease=lease,
                )
            await self._send(captured, turn, context, lease)
        except BaseException as error:
            denied = isinstance(error, PermissionError) or getattr(
                error, "code", None
            ) in {
                "business_permission_denied",
                "business_record_not_found",
                "business_plan_authority_changed",
            }
            try:
                if denied:
                    await asyncio.to_thread(self.delivery.suppress, captured, lease=lease)
                await asyncio.to_thread(self.outbox.mark_unknown, captured, lease=lease)
            except LeaseLost:
                pass
            if not denied:
                raise

    async def _model_output_invalid(
        self, captured: CapturedText, lease: SenderLease
    ) -> None:
        """The model answered with an invalid interpretation before any plan.
        The turn stays unknown, so it is never replayed. The owner gets one
        typed, fixed reply asking to send the message again."""

        logger.warning(
            "Business model output invalid",
            event="business_model_output_invalid",
            turn_ref=captured.turn_key[:12],
        )
        await asyncio.to_thread(
            self.turns.mark_model_unknown, turn_key=captured.turn_key, lease=lease
        )
        await asyncio.to_thread(
            self.outbox.save_reply,
            captured,
            compose_reply("whatsapp_agent_unavailable", language=captured.language),
            lease=lease,
            fixed=True,
        )

    def _consent_missing(self, captured: CapturedText, lease: SenderLease) -> bool:
        """The agent is otherwise able to answer, but the owner has not given
        permission for AI reading yet."""

        available = bool(
            self.enabled()
            and self.actions is not None
            and self.execute_turn is not None
            and self.captures.live_binding(captured, lease=lease)
        )
        if not available:
            return False
        if self.consent is None:
            return not self.has_consent(captured.space_id, captured.owner_id)
        return captured.ai_consent_id is None

    def _may_interpret(self, captured: CapturedText, lease: SenderLease) -> bool:
        available = bool(
            self.enabled()
            and self.actions is not None
            and self.execute_turn is not None
            and self.captures.live_binding(captured, lease=lease)
        )
        if not available:
            return False
        if self.consent is None:
            return self.has_consent(captured.space_id, captured.owner_id)
        if captured.ai_consent_id is None:
            return False
        context = self._authorization(captured, self.turns.load_turn(captured.turn_key))
        self.consent.require_access(captured, context, lease=lease)
        return True

    def _authorization(self, captured: CapturedText, turn: DurableTurn | None) -> Any:
        if turn is not None and turn.plan_actor is not None:
            grant_id = turn.plan_actor.grant_id
        elif self.consent is not None:
            grant_id = self.consent.original_grant(captured)
            if grant_id is None:
                raise PermissionError("whatsapp_ai_consent_required")
        else:
            grant_id = None
        return self.actions.resolve_actor(
            TrustedActor(
                actor_id=captured.owner_id,
                actor_kind="owner_via_agent",
                space_id=captured.space_id,
            ),
            grant_id=grant_id,
        )

    async def _send(
        self,
        captured: CapturedText,
        turn: DurableTurn | None,
        context: Any,
        lease: SenderLease,
    ) -> None:
        if self.transport is None or not self.send_enabled():
            return

        def authorized() -> bool:
            if turn is None:
                return True
            if self.actions is None:
                return False
            if self.consent is not None:
                self.consent.require_access(captured, context, lease=lease)
            elif not self.has_consent(captured.space_id, captured.owner_id):
                return False
            self.actions.plan_for_turn(context, captured.turn_key, lease=lease)
            return True

        while True:
            allowed = await asyncio.to_thread(authorized)
            claim = await asyncio.to_thread(
                self.delivery.claim,
                captured,
                lease=lease,
                permitted=lambda allowed=allowed: self.enabled()
                and self.send_enabled()
                and allowed
                and (
                    turn is None
                    or self.consent is not None
                    or self.has_consent(captured.space_id, captured.owner_id)
                ),
            )
            if claim.state == "waiting_for_window":
                if context is not None:
                    await asyncio.to_thread(
                        self.actions.mark_turn_waiting_for_window,
                        context,
                        captured.turn_key,
                        lease=lease,
                    )
                await asyncio.to_thread(
                    self.delivery.wait_for_window, captured, lease=lease
                )
            if claim.state != "sending":
                return
            try:
                if (
                    not self.enabled()
                    or not self.send_enabled()
                    or not await asyncio.to_thread(authorized)
                ):
                    raise PermissionError("whatsapp_ai_consent_required")
                await self.transport.send(
                    reply_payload(
                        to=captured.envelope.sender,
                        in_reply_to=captured.envelope.message_id,
                        body=claim.reply.body,
                    )
                )
            except BaseException:
                await asyncio.to_thread(
                    self.delivery.settle, captured, claim.reply, lease=lease, sent=False
                )
                raise
            await asyncio.to_thread(
                self.delivery.settle, captured, claim.reply, lease=lease, sent=True
            )
