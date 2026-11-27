"""Durable WhatsApp state: deliveries, sender links and one-time link codes.

A delivery moves ``received -> linked | rejected | captured | failed``. Linked,
rejected and captured are final. A failed delivery, or a received one whose
claim lapsed (the process died mid-way), is claimed again when Meta redelivers
it. A concurrent redelivery with a live claim can retry after the claim ends.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from time import monotonic
from typing import TYPE_CHECKING, Literal, Protocol
from uuid import uuid4
from zoneinfo import ZoneInfo

from argus.domain.business.access import GrantedSpace, InMemoryAccessStore
from argus.domain.ingestion.connections import (
    ConnectionNotFound,
    ConnectionRepository,
    SourceConnection,
)
from argus.domain.ingestion.whatsapp.ai_consent import (
    matches_link_disclosure,
    require_link_disclosure,
)
from argus.domain.owner_scope import BusinessSpace, scope_of

if TYPE_CHECKING:
    from psycopg import Connection

    from argus.domain.ingestion.whatsapp.reply_groups import PendingFailure

ReplyLanguage = Literal["en", "es-419"]
InboundStatus = Literal["received", "linked", "rejected", "captured", "failed"]
SettledStatus = Literal["linked", "rejected", "captured", "failed"]
RETRYABLE: frozenset[InboundStatus] = frozenset({"received", "failed"})
# Code attempts get at most one reply per sender per Dominican calendar day.
REPLY_DAY = ZoneInfo("America/Santo_Domingo")
UNLINKED_REPLY_RESERVED = "whatsapp_unlinked_reply_reserved"


def dominican_day(at: datetime) -> date:
    return at.astimezone(REPLY_DAY).date()


def unlinked_reply_key(sender_hash: bytes, day: date) -> bytes:
    """The provider_message_key of the one reservation row per sender and day.
    Its unique key is what makes two reservations for the same day collide."""

    return hashlib.sha256(
        b"argus.whatsapp.unlinked-reply\0" + sender_hash + day.isoformat().encode()
    ).digest()


# A capture whose sender link ended before it settled keeps no connection.
SENDER_LINK_REVOKED = "sender_link_revoked"


@dataclass(frozen=True)
class InboundRecord:
    provider_message_key: bytes
    sender_hash: bytes | None
    status: InboundStatus
    destination_owner_id: str | None
    connection_id: str | None
    error_code: str | None
    claim_until: datetime | None
    received_at: datetime
    updated_at: datetime
    sender_link_id: str | None = None


@dataclass(frozen=True)
class Claim:
    record: InboundRecord
    claimed: bool


@dataclass(frozen=True)
class CaptureSource:
    content: bytes = field(repr=False)
    filename: str
    media_type: str
    caption: str | None


@dataclass(frozen=True)
class Settlement:
    status: SettledStatus
    destination_owner_id: str | None = None
    connection_id: str | None = None
    error_code: str | None = None
    # Not stored; they choose the reply. ``duplicate``: the destination already
    # held these bytes. ``reading``: the receipt was queued for reading.
    # ``reply_language``: the sender link's, if any.
    duplicate: bool = False
    reading: bool = False
    reply_language: str | None = None
    # The sender link observed before the download, and the staged document location.
    sender_link_id: str | None = None
    original: CaptureSource | None = field(default=None, repr=False, compare=False)
    storage_user_id: str | None = None
    space_id: str | None = None


PrepareCapture = Callable[["Connection | None", Settlement, bytes], Settlement]


def settlement_time(now: datetime | Callable[[], datetime]) -> datetime:
    return now() if callable(now) else now


def settlement_seconds(
    claim_until: datetime, now: datetime, deadline: float | None
) -> float:
    seconds = (claim_until - now).total_seconds()
    return seconds if deadline is None else min(seconds, deadline - monotonic())


def revoked(settlement: Settlement) -> Settlement:
    return replace(
        settlement,
        status="rejected",
        connection_id=None,
        error_code=SENDER_LINK_REVOKED,
        duplicate=False,
        reading=False,
    )


@dataclass(frozen=True)
class SenderLink:
    destination_owner_id: str
    last4: str
    linked_at: datetime
    reply_language: ReplyLanguage
    id: str

    def authorizes(self, settlement: Settlement) -> bool:
        return self.id == settlement.sender_link_id and self.destination_owner_id == settlement.destination_owner_id


class WhatsAppStore(Protocol):
    def claim(
        self,
        *,
        provider_message_key: bytes,
        sender_hash: bytes,
        now: datetime,
        claim_until: datetime,
    ) -> Claim: ...

    def inbound(self, provider_message_key: bytes) -> InboundRecord | None:
        """The row for one message, or None when it was never claimed."""
        ...

    def renew(
        self,
        *,
        provider_message_key: bytes,
        held: datetime,
        now: datetime,
        claim_until: datetime,
    ) -> datetime | None:
        """Extend this worker's claim right before its work starts, only if it
        is still the one ``held``; None when it was lost to another worker."""
        ...

    def settle(
        self,
        *,
        provider_message_key: bytes,
        claim_until: datetime | None,
        settlement: Settlement,
        now: datetime | Callable[[], datetime],
        reply_failure: PendingFailure | None = None,
        prepare: PrepareCapture | None = None,
        deadline: float | None = None,
    ) -> Settlement | None:
        """Settle only while the caller holds a live claim; None when it does not.

        A capture settles only while its owner's sender link is active, checked
        in the same transaction. Otherwise the message settles ``rejected`` with
        ``SENDER_LINK_REVOKED`` and no connection. The optional prepare hook
        publishes the captured document and reports whether reading was queued.
        It shares the settlement transaction in Postgres.
        """
        ...

    def issue_code(
        self,
        *,
        destination_owner_id: str,
        code_digest: bytes,
        reply_language: ReplyLanguage,
        disclosure: str,
        now: datetime,
        expires_at: datetime,
    ) -> None: ...

    def redeem_code(
        self, *, code_digest: bytes, sender_hash: bytes, last4: str, now: datetime
    ) -> SenderLink | None:
        """Consume the code and make its sender link active, carrying its language."""
        ...

    def eligible_businesses(self, person_id: str) -> tuple[GrantedSpace, ...]: ...

    def sender_link(self, *, sender_hash: bytes) -> SenderLink | None: ...

    def destination_link(self, *, destination_owner_id: str) -> SenderLink | None: ...

    def revoke(self, *, destination_owner_id: str, now: datetime) -> bool:
        """End the active link and every unused code for this destination."""
        ...

    def captured_connections(self, *, destination_owner_id: str) -> frozenset[str]:
        """Documents this destination received through WhatsApp."""
        ...

    def reserve_unlinked_reply(
        self, *, sender_hash: bytes, provider_message_key: bytes, now: datetime
    ) -> bool:
        """Take this number's one code reply for the Dominican day this
        message arrived; ``False`` when the day's reply is already taken."""
        ...


@dataclass
class _Code:
    disclosure: str
    owner: str
    reply_language: ReplyLanguage
    expires_at: datetime


@dataclass
class _Link:
    owner: str
    sender: bytes
    last4: str
    linked_at: datetime
    reply_language: ReplyLanguage
    active: bool = True
    id: str = field(default_factory=lambda: str(uuid4()))


class InMemoryWhatsAppStore:
    def __init__(
        self, connections: ConnectionRepository, access: InMemoryAccessStore,
        eligible_businesses: Callable[[str], tuple[GrantedSpace, ...]],
    ) -> None:
        self._connections = connections
        self.eligible_businesses = eligible_businesses
        self._lock = access._lock
        self._inbound: dict[bytes, InboundRecord] = {}
        self._codes: dict[bytes, _Code] = {}
        self._links: list[_Link] = []
        self.reply_failures: list[PendingFailure] = []

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
                record = replace(
                    current,
                    claim_until=claim_until,
                    updated_at=now,
                )
                self._inbound[provider_message_key] = record
                return Claim(record, True)
            return Claim(current, False)

    def settle(
        self,
        *,
        provider_message_key: bytes,
        claim_until: datetime | None,
        settlement: Settlement,
        now: datetime | Callable[[], datetime],
        reply_failure: PendingFailure | None = None,
        prepare: PrepareCapture | None = None,
        deadline: float | None = None,
    ) -> Settlement | None:
        with self._lock:
            current = self._inbound.get(provider_message_key)
            settled_at = settlement_time(now)
            if (
                current is None
                or claim_until is None
                or settlement_seconds(claim_until, settled_at, deadline) <= 0
                or current.status not in RETRYABLE
                or current.claim_until != claim_until
            ):
                return None
            link_id = None
            if settlement.connection_id is not None:
                link = (
                    self.sender_link(sender_hash=current.sender_hash)
                    if current.sender_hash
                    else None
                )
                if link is None or not link.authorizes(settlement):
                    settlement = revoked(settlement)
                else:
                    document = self._connection(
                        settlement.storage_user_id, settlement.connection_id
                    )
                    if document is None or document.scope != scope_of(
                        settlement.space_id
                    ):
                        settlement = replace(
                            settlement,
                            status="rejected",
                            connection_id=None,
                            error_code="whatsapp_media_invalid",
                        )
                    else:
                        link_id = link.id
            if prepare is not None and settlement.status == "captured":
                settlement = prepare(None, settlement, provider_message_key)
            self._inbound[provider_message_key] = replace(
                current,
                status=settlement.status,
                destination_owner_id=settlement.destination_owner_id,
                connection_id=settlement.connection_id,
                error_code=settlement.error_code,
                claim_until=None,
                updated_at=settled_at,
                sender_link_id=link_id,
            )
            if reply_failure is not None:
                self.reply_failures.append(reply_failure)
            return settlement

    def renew(
        self,
        *,
        provider_message_key: bytes,
        held: datetime,
        now: datetime,
        claim_until: datetime,
    ) -> datetime | None:
        with self._lock:
            current = self._inbound[provider_message_key]
            if current.status not in RETRYABLE or current.claim_until != held:
                return None
            self._inbound[provider_message_key] = replace(
                current, claim_until=claim_until, updated_at=now
            )
            return claim_until

    def inbound(self, provider_message_key: bytes) -> InboundRecord | None:
        return self._inbound.get(provider_message_key)

    def reserve_unlinked_reply(
        self, *, sender_hash: bytes, provider_message_key: bytes, now: datetime
    ) -> bool:
        with self._lock:
            day = dominican_day(self._inbound[provider_message_key].received_at)
            key = unlinked_reply_key(sender_hash, day)
            if key in self._inbound:
                return False
            self._inbound[key] = InboundRecord(
                key,
                sender_hash,
                "rejected",
                None,
                None,
                UNLINKED_REPLY_RESERVED,
                None,
                now,
                now,
            )
            return True

    def _connection(
        self, user_id: str | None, connection_id: str
    ) -> SourceConnection | None:
        if user_id is None:
            return None
        try:
            return self._connections.get_any_scope(
                user_id=user_id, connection_id=connection_id
            )
        except ConnectionNotFound:
            return None

    def captured_connections(self, *, destination_owner_id: str) -> frozenset[str]:
        with self._lock:
            return frozenset(
                record.connection_id
                for record in self._inbound.values()
                if record.status == "captured"
                and record.connection_id is not None
                and (row := self._connection(destination_owner_id, record.connection_id)) is not None
                and isinstance(row.scope, BusinessSpace)
            )

    def issue_code(
        self,
        *,
        destination_owner_id: str,
        code_digest: bytes,
        reply_language: ReplyLanguage,
        disclosure: str,
        now: datetime,
        expires_at: datetime,
    ) -> None:
        require_link_disclosure(reply_language, disclosure)
        with self._lock:
            for digest in [
                d
                for d, c in self._codes.items()
                if c.owner == destination_owner_id
            ]:
                del self._codes[digest]
            self._codes[code_digest] = _Code(
                disclosure, destination_owner_id, reply_language, expires_at
            )

    def redeem_code(
        self, *, code_digest: bytes, sender_hash: bytes, last4: str, now: datetime
    ) -> SenderLink | None:
        with self._lock:
            code = self._codes.pop(code_digest, None)
            if code is None or code.expires_at <= now:
                return None
            if not matches_link_disclosure(code.reply_language, code.disclosure):
                return None
            if not self.eligible_businesses(code.owner):
                return None
            for link in self._links:
                if link.active and (
                    link.sender == sender_hash or link.owner == code.owner
                ):
                    link.active = False
            link = _Link(code.owner, sender_hash, last4, now, code.reply_language)
            self._links.append(link)
            return SenderLink(link.owner, link.last4, link.linked_at, link.reply_language, link.id)

    def _active(self, predicate) -> SenderLink | None:  # noqa: ANN001
        for link in self._links:
            if link.active and predicate(link):
                return SenderLink(
                    link.owner, link.last4, link.linked_at, link.reply_language, link.id
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
                if c.owner == destination_owner_id
            ]:
                del self._codes[digest]
            revoked = False
            for link in self._links:
                if link.active and link.owner == destination_owner_id:
                    link.active = False
                    revoked = True
            return revoked
