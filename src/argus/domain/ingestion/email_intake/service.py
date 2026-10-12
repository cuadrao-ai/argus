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
from argus.domain.ingestion.email_intake.envelope import parse_envelope
from argus.domain.ingestion.email_intake.models import (
    EmailDelivery,
    EmailDeliveryPart,
    RecipientRoute,
)
from argus.domain.ingestion.email_intake.provider import EmailProviderError
from argus.domain.ingestion.email_intake.store import EmailStore, LeaseLost
from argus.domain.owner_scope import BusinessSpace

ORIGINAL_FILENAME = "forwarded.eml"


class ReceivingProvider(Protocol):
    async def raw_message(self, email_id: str): ...  # noqa: ANN201


RouteAuthority = Callable[[RecipientRoute], None]


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
    ) -> None:
        self.store, self.documents, self.provider, self.enabled = (
            store,
            documents,
            provider,
            enabled,
        )
        self.route_authority = route_authority
        self.receiving_enabled = receiving_enabled or (lambda: self.provider is not None)

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
        if len(routes) != 1:
            delivery = self.store.enqueue("resend", external_id, recipients)
            return self.store.reject_unclaimed(
                delivery.id,
                "email_route_ambiguous" if routes else "email_route_unavailable",
            )
        route = routes[0]
        try:
            self.check_route(route)
        except ActionError:
            delivery = self.store.enqueue("resend", external_id, recipients)
            return self.store.reject_unclaimed(delivery.id, "email_route_revoked")
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
            else:
                if self.provider is None:
                    raise EmailProviderError("email_provider_unavailable", retryable=True)
                received = await self.provider.raw_message(delivery.external_id)
                expected = {address.lower() for address in delivery.recipients}
                actual = {address.lower() for address in received.recipients}
                if actual != expected:
                    raise EmailProviderError("email_recipient_mismatch")
                raw = received.raw
            # The fetch took time; the grant is read once more before any write.
            await asyncio.to_thread(self.check_route, route)
            await self._capture(delivery, raw)
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

    async def _capture(self, delivery: EmailDelivery, raw: bytes) -> None:
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
            # The whole message is the first document. One unsupported sibling
            # refuses it as a document; its good parts still capture below.
            try:
                outcome = await self.documents.upload(
                    user_id=delivery.principal_id,
                    scope=scope,
                    content=raw,
                    filename=ORIGINAL_FILENAME,
                    media_type="message/rfc822",
                    consent=False,
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
            try:
                outcome = await self.documents.upload(
                    user_id=delivery.principal_id,
                    scope=scope,
                    content=part.content,
                    filename=part.filename,
                    media_type=part.media_type,
                    consent=False,
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
