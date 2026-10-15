"""Durable WhatsApp state: deliveries, sender links and one-time link codes.

A delivery moves ``received -> linked | rejected | captured | failed``. Linked,
rejected and captured are final. A failed delivery, or a received one whose
claim lapsed (the process died mid-way), is claimed again when Meta redelivers
it, so recovery reuses the original record. A live claim makes a concurrent
redelivery a no-op, so one message never produces two captures or two replies.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal, Protocol

ReplyLanguage = Literal["en", "es-419"]
InboundStatus = Literal["received", "linked", "rejected", "captured", "failed"]
SettledStatus = Literal["linked", "rejected", "captured", "failed"]
RETRYABLE: frozenset[InboundStatus] = frozenset({"received", "failed"})
# A capture whose sender link ended before it settled keeps no connection.
SENDER_LINK_REVOKED = "sender_link_revoked"


@dataclass(frozen=True)
class InboundRecord:
    provider_message_key: bytes
    sender_hash: bytes
    status: InboundStatus
    destination_owner_id: str | None
    connection_id: str | None
    error_code: str | None
    claim_until: datetime | None
    received_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class Claim:
    record: InboundRecord
    claimed: bool


@dataclass(frozen=True)
class Settlement:
    status: SettledStatus
    destination_owner_id: str | None = None
    connection_id: str | None = None
    error_code: str | None = None
    # Not stored; they choose the reply. ``duplicate``: the destination already
    # held these bytes. ``reply_language``: the sender link's, if any.
    duplicate: bool = False
    reply_language: str | None = None


def revoked(settlement: Settlement) -> Settlement:
    return replace(
        settlement,
        status="rejected",
        connection_id=None,
        error_code=SENDER_LINK_REVOKED,
        duplicate=False,
    )


@dataclass(frozen=True)
class SenderLink:
    destination_owner_id: str
    last4: str
    linked_at: datetime
    reply_language: ReplyLanguage


class WhatsAppStore(Protocol):
    def claim(
        self,
        *,
        provider_message_key: bytes,
        sender_hash: bytes,
        now: datetime,
        claim_until: datetime,
    ) -> Claim: ...

    def settle(
        self,
        *,
        provider_message_key: bytes,
        claim_until: datetime | None,
        settlement: Settlement,
        now: datetime,
    ) -> Settlement | None:
        """Settle only while the caller's claim is the one held; None when it is not.

        A capture settles only while its owner's sender link is active, checked
        in the same transaction. Otherwise the message settles ``rejected`` with
        ``SENDER_LINK_REVOKED`` and no connection. Returns what was stored.
        """
        ...

    def issue_code(
        self,
        *,
        destination_owner_id: str,
        code_digest: bytes,
        reply_language: ReplyLanguage,
        now: datetime,
        expires_at: datetime,
    ) -> None: ...

    def redeem_code(
        self, *, code_digest: bytes, sender_hash: bytes, last4: str, now: datetime
    ) -> SenderLink | None:
        """Consume the code and make its sender link active, carrying its language."""
        ...

    def sender_link(self, *, sender_hash: bytes) -> SenderLink | None: ...

    def destination_link(self, *, destination_owner_id: str) -> SenderLink | None: ...

    def revoke(self, *, destination_owner_id: str, now: datetime) -> bool:
        """End the active link and every unused code for this destination."""
        ...

    def captured_connections(self, *, destination_owner_id: str) -> frozenset[str]:
        """Documents this destination received through WhatsApp."""
        ...


@dataclass
class _Code:
    owner: str
    reply_language: ReplyLanguage
    expires_at: datetime
    consumed: bool = False


@dataclass
class _Link:
    owner: str
    sender: bytes
    last4: str
    linked_at: datetime
    reply_language: ReplyLanguage
    active: bool = True


class InMemoryWhatsAppStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._inbound: dict[bytes, InboundRecord] = {}
        self._codes: dict[bytes, _Code] = {}
        self._links: list[_Link] = []

    def claim(
        self,
        *,
        provider_message_key: bytes,
        sender_hash: bytes,
        now: datetime,
        claim_until: datetime,
    ) -> Claim:
        with self._lock:
            current = self._inbound.get(provider_message_key)
            if current is None:
                record = InboundRecord(
                    provider_message_key,
                    sender_hash,
                    "received",
                    None,
                    None,
                    None,
                    claim_until,
                    now,
                    now,
                )
                self._inbound[provider_message_key] = record
                return Claim(record, True)
            if current.status in RETRYABLE and (
                current.claim_until is None or current.claim_until <= now
            ):
                record = replace(current, claim_until=claim_until, updated_at=now)
                self._inbound[provider_message_key] = record
                return Claim(record, True)
            return Claim(current, False)

    def settle(
        self,
        *,
        provider_message_key: bytes,
        claim_until: datetime | None,
        settlement: Settlement,
        now: datetime,
    ) -> Settlement | None:
        with self._lock:
            current = self._inbound[provider_message_key]
            if current.status not in RETRYABLE or current.claim_until != claim_until:
                return None
            if settlement.connection_id is not None and not any(
                link.active and link.owner == settlement.destination_owner_id
                for link in self._links
            ):
                settlement = revoked(settlement)
            self._inbound[provider_message_key] = replace(
                current,
                status=settlement.status,
                destination_owner_id=settlement.destination_owner_id,
                connection_id=settlement.connection_id,
                error_code=settlement.error_code,
                claim_until=None,
                updated_at=now,
            )
            return settlement

    def inbound(self, provider_message_key: bytes) -> InboundRecord | None:
        return self._inbound.get(provider_message_key)

    def captured_connections(self, *, destination_owner_id: str) -> frozenset[str]:
        with self._lock:
            return frozenset(
                record.connection_id
                for record in self._inbound.values()
                if record.status == "captured"
                and record.connection_id is not None
                and record.destination_owner_id == destination_owner_id
            )

    def issue_code(
        self,
        *,
        destination_owner_id: str,
        code_digest: bytes,
        reply_language: ReplyLanguage,
        now: datetime,
        expires_at: datetime,
    ) -> None:
        with self._lock:
            for digest in [
                d
                for d, c in self._codes.items()
                if c.owner == destination_owner_id and not c.consumed
            ]:
                del self._codes[digest]
            self._codes[code_digest] = _Code(
                destination_owner_id, reply_language, expires_at
            )

    def redeem_code(
        self, *, code_digest: bytes, sender_hash: bytes, last4: str, now: datetime
    ) -> SenderLink | None:
        with self._lock:
            code = self._codes.get(code_digest)
            if code is None or code.consumed or code.expires_at <= now:
                return None
            code.consumed = True
            for link in self._links:
                if link.active and (
                    link.sender == sender_hash or link.owner == code.owner
                ):
                    link.active = False
            link = _Link(code.owner, sender_hash, last4, now, code.reply_language)
            self._links.append(link)
            return SenderLink(link.owner, link.last4, link.linked_at, link.reply_language)

    def _active(self, predicate) -> SenderLink | None:  # noqa: ANN001
        for link in self._links:
            if link.active and predicate(link):
                return SenderLink(
                    link.owner, link.last4, link.linked_at, link.reply_language
                )
        return None

    def sender_link(self, *, sender_hash: bytes) -> SenderLink | None:
        return self._active(lambda link: link.sender == sender_hash)

    def destination_link(self, *, destination_owner_id: str) -> SenderLink | None:
        return self._active(lambda link: link.owner == destination_owner_id)

    def revoke(self, *, destination_owner_id: str, now: datetime) -> bool:
        with self._lock:
            for digest in [
                d
                for d, c in self._codes.items()
                if c.owner == destination_owner_id and not c.consumed
            ]:
                del self._codes[digest]
            revoked = False
            for link in self._links:
                if link.active and link.owner == destination_owner_id:
                    link.active = False
                    revoked = True
            return revoked
