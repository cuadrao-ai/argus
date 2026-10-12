"""Receive one message, bind it to one route, capture its parts once.

The route is the only thing that chooses a Business. Message headers, the
sender and the provider's recipient list prove nothing on their own: the
provider list must equal the recipients the signed event named, and the
route's grant is checked again, live, before any bytes are read."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import replace
from typing import Iterator, Protocol
from uuid import UUID

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
    """The route's principal must still hold the route's grant with prepare."""

    def check(route: RecipientRoute) -> None:
        actor = TrustedActor(
            actor_id=UUID(route.principal_id),
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

    @contextmanager
    def authorized_route(self, route: RecipientRoute) -> Iterator[None]:
        with self.store.locked_route(route.id) as live:
            if not self.enabled() or live is None or not live.active or live != route:
                raise ActionError("permission_denied", "email_route_unavailable")
            try:
                self.route_authority(live)
            except ActionError:
                raise ActionError("permission_denied", "email_route_revoked") from None
            yield

    def route_usable(self, route: RecipientRoute) -> bool:
        try:
            with self.authorized_route(route):
                return True
        except ActionError:
            return False

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
            with self.authorized_route(route):
                return self.store.enqueue(
                    "resend",
                    external_id,
                    recipients,
                    route_id=route.id,
                    space_id=route.space_id,
                    principal_id=route.principal_id,
                )
        except ActionError:
            delivery = self.store.enqueue("resend", external_id, recipients)
            return self.store.reject_unclaimed(delivery.id, "email_route_revoked")

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
        delivery = self.store.claim()
        if delivery is None:
            return False
        await self.process(delivery)
        return True

    async def process(self, delivery: EmailDelivery) -> None:
        try:
            routes = self.store.routes(delivery.recipients)
            if len(routes) != 1:
                raise EmailProviderError(
                    "email_route_ambiguous"
                    if len(routes) > 1
                    else "email_route_unavailable"
                )
            route = routes[0]
            if (delivery.route_id, delivery.space_id, delivery.principal_id) != (
                route.id,
                route.space_id,
                route.principal_id,
            ):
                raise EmailProviderError("email_route_changed")
            with self.authorized_route(route):
                if delivery.original_document_id:
                    raw = self.documents.source_bytes(
                        user_id=delivery.principal_id,
                        connection_id=delivery.original_document_id,
                        scope=BusinessSpace(delivery.space_id),
                    )
                else:
                    if self.provider is None:
                        raise EmailProviderError(
                            "email_provider_unavailable", retryable=True
                        )
                    received = await self.provider.raw_message(delivery.external_id)
                    expected = {address.lower() for address in delivery.recipients}
                    actual = {address.lower() for address in received.recipients}
                    if actual != expected:
                        raise EmailProviderError("email_recipient_mismatch")
                    raw = received.raw
                await self._capture(delivery, raw)
        except LeaseLost:
            return
        except ActionError as error:
            self.store.finish(delivery, "rejected", error.code)
        except (EmailProviderError, DocumentServiceError) as error:
            self.store.finish(
                delivery, "partial" if error.retryable else "rejected", error.code
            )
        except DocumentExtractionError as error:
            self.store.finish(delivery, "rejected", error.code)
        except Exception:
            self.store.finish(delivery, "partial", "email_capture_unavailable")

    async def _capture(self, delivery: EmailDelivery, raw: bytes) -> None:
        self.store.renew(delivery)
        scope = BusinessSpace(delivery.space_id)
        envelope = parse_envelope(raw)
        self.store.update(
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
                self.store.update(delivery, original_document_id=outcome.connection_id)
            except DocumentExtractionError:
                original_rejected = True
        existing = {part.id: part for part in self.store.parts(delivery.id)}
        transient = False
        for part in envelope.parts:
            self.store.renew(delivery)
            previous = existing.get(part.id)
            if previous and previous.state in ("captured", "rejected"):
                continue
            result = EmailDeliveryPart(
                part.id, part.filename, part.media_type, "pending", None, part.error_code
            )
            self.store.put_part(delivery, result)
            if part.error_code:
                self.store.put_part(delivery, replace(result, state="rejected"))
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
            self.store.put_part(delivery, result)
        rejected = original_rejected or any(
            part.state == "rejected" for part in self.store.parts(delivery.id)
        )
        self.store.finish(
            delivery,
            "partial" if transient else "captured",
            "email_capture_incomplete"
            if transient
            else "email_parts_rejected"
            if rejected
            else None,
        )
