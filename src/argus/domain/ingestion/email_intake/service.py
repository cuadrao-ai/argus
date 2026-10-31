"""Receive one message, bind it to one route, capture its parts once.

The route is the only thing that chooses a Business. Message headers, the
sender and the provider's recipient list prove nothing on their own: the
provider list must equal the recipients the signed event named, and the
route's grant is checked again, live, before any bytes are read and once more
before anything is written. Database work runs in worker threads; the event
loop only waits on the provider."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import replace
from typing import Protocol
from uuid import UUID

from loguru import logger
from psycopg_pool import ConnectionPool

from argus.domain.business.authority import ActionError, authorize
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.ingestion.documents.models import DocumentExtractionError
from argus.domain.ingestion.documents.service import (
    DocumentServiceError,
    DocumentsService,
)
from argus.domain.ingestion.email_intake.alignment import from_address, provider_verdict
from argus.domain.ingestion.email_intake.budget import (
    EmailBudgetWait,
    FetchBudget,
    FetchReservation,
)
from argus.domain.ingestion.email_intake.config import EmailIntakeSettings
from argus.domain.ingestion.email_intake.envelope import parse_envelope
from argus.domain.ingestion.email_intake.models import (
    EmailDelivery,
    EmailDeliveryPart,
    RecipientRoute,
)
from argus.domain.ingestion.email_intake.provider import EmailProviderError, ReceivedEmail
from argus.domain.ingestion.email_intake.routing import NO_RESULT, bounce_copy, decide
from argus.domain.ingestion.email_intake.sender_policy import PENDING_CODE, admitted
from argus.domain.ingestion.email_intake.store import BUDGET_CODES, EmailStore, LeaseLost
from argus.domain.owner_scope import BusinessSpace

ORIGINAL_FILENAME = "forwarded.eml"
RECEIPT_MEDIA = frozenset({"image/png", "image/jpeg", "application/pdf"})


def reader_bytes(content: bytes, media_type: str, body: str) -> bytes | None:
    """Bytes the receipt reader may see. Message text is not among them.

    ``body`` is the message text. It is never copied into the result. An image
    or PDF attachment is the only reader input.
    """

    if media_type not in RECEIPT_MEDIA or not isinstance(body, str):
        return None
    return content


class ReceivingProvider(Protocol):
    async def raw_message(
        self, email_id: str, *, budget: FetchBudget | None = None
    ) -> ReceivedEmail: ...


class DeliveryFetchBudget:
    def __init__(self, store: EmailStore, delivery: EmailDelivery) -> None:
        self.store, self.delivery = store, delivery

    async def reserve(self) -> FetchReservation:
        return await asyncio.to_thread(self.store.reserve_fetch, self.delivery)

    async def settle(self, reservation: FetchReservation, actual_bytes: int) -> None:
        await asyncio.to_thread(
            self.store.settle_fetch, self.delivery, reservation, actual_bytes
        )


RouteAuthority = Callable[[RecipientRoute], None]


def _from_receipt_domain(sender: str | None) -> bool:
    domain = EmailIntakeSettings().receiving_domain.strip().lower()
    if not domain or not isinstance(sender, str) or "@" not in sender:
        return False
    return sender.strip().lower().rsplit("@", 1)[1] == domain


def grant_route_authority(pool: ConnectionPool) -> RouteAuthority:
    """The member who bound the route must still hold its grant with prepare."""

    def check(route: RecipientRoute) -> None:
        actor = TrustedActor(
            actor_id=UUID(route.granted_by),
            actor_kind="member",
            space_id=UUID(route.space_id),
        )
        with pool.connection() as connection, connection.transaction():
            authorize(connection, actor, UUID(route.grant_id)).require("prepare")

    return check


class EmailCapture:
    def __init__(
        self,
        store: EmailStore,
        documents: DocumentsService,
        route_authority: RouteAuthority,
        provider: ReceivingProvider | None,
        enabled: Callable[[], bool],
        receiving_enabled: Callable[[], bool] | None = None,
        read_receipt=None,
        pending_senders: Callable[[], bool] | None = None,
    ) -> None:
        self.store, self.documents, self.provider, self.enabled = (
            store,
            documents,
            provider,
            enabled,
        )
        self.route_authority = route_authority
        self.read_receipt = read_receipt
        self.receiving_enabled = receiving_enabled or (lambda: self.provider is not None)
        self.pending_senders = pending_senders or (
            lambda: EmailIntakeSettings().pending_senders_enabled
        )

    def check_route(self, route: RecipientRoute) -> None:
        """Raise unless the route is live and its grant still allows prepare.

        Two short transactions, never nested: the row lock is released before
        the grant is read, so one pool connection is enough."""

        with self.store.locked_route(route.id) as live:
            if not self.enabled() or live is None or not live.active or live != route:
                raise ActionError("permission_denied", "email_route_unavailable")
        try:
            self.route_authority(route)
        except ActionError:
            raise ActionError("permission_denied", "email_route_revoked") from None

    def route_usable(self, route: RecipientRoute) -> bool:
        try:
            self.check_route(route)
        except ActionError:
            return False
        return True

    def enqueue_resend(
        self, external_id: str, recipients: tuple[str, ...]
    ) -> EmailDelivery:
        """Record the signed event durably. An unroutable message is rejected, never fetched."""

        routes = self.store.routes(recipients)
        retired = self.store.matching_retired(recipients)
        if len(retired) == 1 and not routes:
            old = retired[0]
            return self.store.enqueue(
                "resend",
                external_id,
                recipients,
                route_id=old.route_id,
                space_id=old.space_id,
                principal_id=old.principal_id,
                reject_code="email_alias_retired",
                bounce_text=bounce_copy(),
            )
        if len(routes) != 1 or retired:
            return self.store.enqueue(
                "resend",
                external_id,
                recipients,
                reject_code="email_route_ambiguous"
                if routes or len(retired) > 1
                else "email_route_unavailable",
            )
        route = routes[0]
        try:
            self.check_route(route)
        except ActionError:
            return self.store.enqueue(
                "resend", external_id, recipients, reject_code="email_route_revoked"
            )
        # The binding is checked again by the worker before any fetch.
        return self.store.enqueue(
            "resend",
            external_id,
            recipients,
            route_id=route.id,
            space_id=route.space_id,
            principal_id=route.principal_id,
        )

    def retryable(self, delivery: EmailDelivery) -> bool:
        return bool(
            self.enabled()
            and delivery.state == "partial"
            and delivery.lease_token is None
            and self.receiving_enabled()
            and self.provider is not None
        )

    async def next(self) -> bool:
        if not self.enabled() or not self.receiving_enabled():
            return False
        delivery = await asyncio.to_thread(self.store.claim)
        if delivery is None:
            return False
        await self.process(delivery)
        return True

    def _bound_route(self, delivery: EmailDelivery) -> RecipientRoute:
        routes = self.store.routes(delivery.recipients)
        if len(routes) != 1:
            raise EmailProviderError(
                "email_route_ambiguous" if len(routes) > 1 else "email_route_unavailable"
            )
        route = routes[0]
        if (delivery.route_id, delivery.space_id, delivery.principal_id) != (
            route.id,
            route.space_id,
            route.principal_id,
        ):
            raise EmailProviderError("email_route_changed")
        self.check_route(route)
        return route

    async def _preview_sender(self, delivery: EmailDelivery) -> str | None:
        preview = getattr(self.provider, "preview_from", None)
        if preview is None:
            return None
        try:
            return await preview(delivery.external_id)
        except Exception:
            logger.warning(
                "email_sender_preview_failed",
                delivery_id=delivery.id,
            )
            return None

    async def _drop_receipt_domain(self, delivery: EmailDelivery) -> bool:
        if not EmailIntakeSettings().receiving_domain.strip():
            return False
        if not _from_receipt_domain(await self._preview_sender(delivery)):
            return False
        await asyncio.to_thread(
            self.store.finish, delivery, "rejected", "email_sender_domain_refused"
        )
        return True

    async def _admit(self, delivery: EmailDelivery, route: RecipientRoute) -> bool:
        standing = "new"
        if self.store.has_sender_rules(route.space_id):
            hint = await self._preview_sender(delivery)
            standing = await asyncio.to_thread(
                self.store.sender_standing, route.space_id, hint
            )
        if standing == "blocked":
            await asyncio.to_thread(
                self.store.finish, delivery, "rejected", "email_sender_blocked"
            )
            return False
        gated = await asyncio.to_thread(self.store.gate_unauthorized, delivery)
        return gated.error_code not in BUDGET_CODES

    async def _keep_after_alignment(
        self, delivery: EmailDelivery, route: RecipientRoute, raw: bytes, auth: str
    ) -> bool:
        sender = from_address(raw)
        standing = await asyncio.to_thread(
            self.store.sender_standing, route.space_id, sender
        )
        if standing == "authorized" and auth == "aligned":
            await asyncio.to_thread(self.store.refund_aligned_fetch, delivery, len(raw))
            return True
        if standing == "authorized":
            await asyncio.to_thread(
                self.store.retain_unaligned_ceiling, delivery, len(raw)
            )
        await asyncio.to_thread(self.store.mark_cap_exempt, delivery, exempt=False)
        gated = await asyncio.to_thread(self.store.gate_unauthorized, delivery)
        return gated.error_code not in BUDGET_CODES

    def _apply_route(
        self, delivery: EmailDelivery, route: RecipientRoute, raw: bytes, auth: str
    ) -> bool:
        sender = from_address(raw)
        standing = self.store.sender_standing(route.space_id, sender)
        if standing == "blocked":
            self.store.finish(delivery, "rejected", "email_sender_blocked")
            return False
        if self.pending_senders() and not delivery.original_document_id:
            if not admitted(self.store, route.space_id, sender, auth):
                # Fetched and judged in memory only; nothing of the mail is kept.
                self.store.finish(delivery, "rejected", PENDING_CODE)
                return False
            standing = "authorized"
        first = (
            standing == "authorized"
            and auth == "aligned"
            and self.store.claim_first_scan(route.space_id, sender)
        )
        decision = decide(standing, auth, first_authorized=first)
        self.store.stamp_route(
            delivery,
            inbox_group=decision.group,
            auth_result=decision.auth,
            review_note=decision.note,
            first_scan=decision.first_scan,
        )
        return True

    async def process(self, delivery: EmailDelivery) -> None:
        try:
            route = await asyncio.to_thread(self._bound_route, delivery)
            if delivery.original_document_id:
                raw = await asyncio.to_thread(
                    self.documents.source_bytes,
                    user_id=delivery.principal_id,
                    connection_id=delivery.original_document_id,
                    scope=BusinessSpace(delivery.space_id),
                )
                auth = delivery.auth_result or NO_RESULT
            else:
                if self.provider is None:
                    raise EmailProviderError("email_provider_unavailable", retryable=True)
                if await self._drop_receipt_domain(delivery):
                    return
                if not await self._admit(delivery, route):
                    return
                received = await self.provider.raw_message(
                    delivery.external_id, budget=DeliveryFetchBudget(self.store, delivery)
                )
                expected = {address.lower() for address in delivery.recipients}
                actual = {address.lower() for address in received.recipients}
                if actual != expected:
                    raise EmailProviderError("email_recipient_mismatch")
                raw = received.raw
                auth = provider_verdict(
                    received.authentication,
                    raw=raw,
                    provider_from=received.provider_from,
                )
                if auth == "no_result":
                    # Before the pilot: if this fires for every intake, the
                    # provider stopped sending results and nothing is read.
                    logger.warning(
                        "email_auth_no_result",
                        delivery_id=delivery.id,
                        route_id=route.id,
                    )
                if not await self._keep_after_alignment(delivery, route, raw, auth):
                    return
            await asyncio.to_thread(self.check_route, route)
            if not await asyncio.to_thread(self._apply_route, delivery, route, raw, auth):
                return
            await self._capture(delivery, raw, route)
        except EmailBudgetWait as error:
            try:
                await asyncio.to_thread(self.store.defer_budget, delivery, error.code)
            except LeaseLost:
                return
        except LeaseLost:
            return
        except ActionError as error:
            await self._finish(delivery, "rejected", error.code)
        except (EmailProviderError, DocumentServiceError) as error:
            await self._finish(
                delivery, "partial" if error.retryable else "rejected", error.code
            )
        except DocumentExtractionError as error:
            await self._finish(delivery, "rejected", error.code)
        except Exception as error:  # noqa: BLE001 - the row stays retryable; only the class is logged
            logger.warning(
                "email_capture_failed",
                delivery_id=delivery.id,
                error=type(error).__name__,
            )
            await self._finish(delivery, "partial", "email_capture_unavailable")

    async def _finish(
        self, delivery: EmailDelivery, state: str, error_code: str | None = None
    ) -> None:
        await asyncio.to_thread(self.store.finish, delivery, state, error_code)

    async def _capture(
        self, delivery: EmailDelivery, raw: bytes, route: RecipientRoute
    ) -> None:
        run = asyncio.to_thread
        await run(self.store.renew, delivery)
        scope = BusinessSpace(delivery.space_id)
        envelope = await run(parse_envelope, raw)
        await run(
            self.store.update,
            delivery,
            subject=envelope.subject,
            sender=envelope.sender,
            sent_at=envelope.sent_at,
            text_body=envelope.text_body,
        )
        original_rejected = False
        if delivery.original_document_id is None:
            # The whole message is the first document. It is refused only when
            # nothing in it is readable; each part still captures on its own below.
            try:
                outcome = await self.documents.upload(
                    user_id=delivery.principal_id,
                    scope=scope,
                    content=raw,
                    filename=ORIGINAL_FILENAME,
                    media_type="message/rfc822",
                    consent=False,
                    context_only=True,
                )
                await run(
                    self.store.update,
                    delivery,
                    original_document_id=outcome.connection_id,
                )
            except DocumentExtractionError:
                original_rejected = True
        existing = {part.id: part for part in await run(self.store.parts, delivery.id)}
        transient = False
        for part in envelope.parts:
            await run(self.store.renew, delivery)
            previous = existing.get(part.id)
            if previous and previous.state in ("captured", "rejected"):
                continue
            result = EmailDeliveryPart(
                part.id, part.filename, part.media_type, "pending", None, part.error_code
            )
            await run(self.store.put_part, delivery, result)
            if part.error_code:
                await run(
                    self.store.put_part, delivery, replace(result, state="rejected")
                )
                continue
            readable = reader_bytes(part.content, part.media_type, envelope.text_body)
            try:
                outcome = await self.documents.upload(
                    user_id=delivery.principal_id,
                    scope=scope,
                    content=readable if readable is not None else part.content,
                    filename=part.filename,
                    media_type=part.media_type,
                    consent=False,
                    on_capture=self.store.part_capture_hook(delivery, result),
                )
                result = replace(
                    result, state="captured", document_id=outcome.connection_id
                )
            except DocumentExtractionError as error:
                result = replace(result, state="rejected", error_code=error.code)
            except DocumentServiceError as error:
                transient |= error.retryable
                result = replace(
                    result,
                    state="pending" if error.retryable else "rejected",
                    error_code=error.code,
                )
            await run(self.store.put_part, delivery, result)
        rejected = original_rejected or any(
            part.state == "rejected" for part in await run(self.store.parts, delivery.id)
        )
        await self._finish(
            delivery,
            "partial" if transient else "captured",
            "email_capture_incomplete"
            if transient
            else "email_parts_rejected"
            if rejected
            else None,
        )
        if self.read_receipt is not None:
            captured = await run(self.store.parts, delivery.id)
            connection_ids = {
                part.document_id
                for part in captured
                if part.state == "captured"
                and part.document_id
                and reader_bytes(b"", part.media_type, "") is not None
            }
            for connection_id in connection_ids:
                try:
                    await run(self.check_route, route)
                    await self.read_receipt(route, connection_id)
                except Exception as error:
                    logger.warning(
                        "email_receipt_dispatch_failed",
                        delivery_id=delivery.id,
                        connection_id=connection_id,
                        failure_mode=type(error).__name__,
                    )
