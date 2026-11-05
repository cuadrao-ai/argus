"""Relevance is the person's choice: a per-connection sender allowlist.

The person names the bank senders to import from, as full addresses
(``alertas@banco-ejemplo.test``) or domains (``banco-ejemplo.test``, which also
covers its subdomains). Nothing decides relevance from what a message says.

The Gmail search query is built from this list only and merely narrows what
Gmail returns; ``matches`` is the one rule that decides, applied to the parsed
``From`` address of every message on every path (initial scan, history,
recovery), so the paths cannot disagree. Entries are validated structurally to
a conservative character set, which also keeps them from injecting Gmail
search operators into the query.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from datetime import datetime
from email import policy
from email.utils import getaddresses
from typing import Literal, Protocol

MAX_SENDERS = 20
MAX_SENDER_CHARS = 254
_LOCAL_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789._%+-")
_LABEL_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-")

SenderKind = Literal["address", "domain"]


class InvalidSender(ValueError):
    pass


@dataclass(frozen=True)
class SenderRule:
    sender: str
    created_at: datetime
    backfilled_at: datetime | None = None

    @property
    def kind(self) -> SenderKind:
        return "address" if "@" in self.sender else "domain"


def normalize_sender(raw: str) -> str:
    value = str(raw).strip().lower()
    if value.startswith("@"):
        value = value[1:]
    if not value or len(value) > MAX_SENDER_CHARS:
        raise InvalidSender("sender is empty or too long")
    local, at, domain = value.rpartition("@")
    if at:
        if not local or len(local) > 64 or not set(local) <= _LOCAL_CHARS:
            raise InvalidSender("sender address is not a plain mailbox")
        if local.startswith(".") or local.endswith(".") or ".." in local:
            raise InvalidSender("sender address is not a plain mailbox")
    else:
        domain = value
    _check_domain(domain)
    return value


def normalize_senders(raws: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    values = sorted({normalize_sender(raw) for raw in raws})
    if len(values) > MAX_SENDERS:
        raise InvalidSender(f"at most {MAX_SENDERS} senders")
    return tuple(values)


def _check_domain(domain: str) -> None:
    labels = domain.split(".")
    if len(labels) < 2 or len(domain) > 253:
        raise InvalidSender("sender domain is not a domain name")
    for label in labels:
        if (
            not 1 <= len(label) <= 63
            or not set(label) <= _LABEL_CHARS
            or label.startswith("-")
            or label.endswith("-")
        ):
            raise InvalidSender("sender domain is not a domain name")


def from_address(header: str | None) -> str | None:
    """The single mailbox in a ``From`` header, lowercased; None if ambiguous.

    Two independent parsers must agree: ``policy.default``'s header registry
    (refused when it reports any defect) and ``email.utils.getaddresses`` on
    the raw value. Parser differentials are a known way to show one address
    to a filter and another to a reader, so any disagreement is no sender.
    """

    if not header:
        return None
    try:
        parsed = policy.default.header_factory("From", header)
        addresses = parsed.addresses
    except Exception:  # noqa: BLE001 - unparseable headers have no sender
        return None
    if parsed.defects or len(addresses) != 1:
        return None
    address = addresses[0].addr_spec.strip().lower()
    strict = [addr for _, addr in getaddresses([header]) if addr]
    if len(strict) != 1 or strict[0].strip().lower() != address:
        return None
    local, at, domain = address.rpartition("@")
    if not at or not local or not domain or "@" in local:
        return None
    return address


def domain_of(address: str) -> str:
    return address.rpartition("@")[2]


def matches(
    address: str | None, rules: list[SenderRule] | tuple[SenderRule, ...]
) -> SenderRule | None:
    if not address:
        return None
    domain = domain_of(address)
    for rule in rules:
        if rule.kind == "address":
            if address == rule.sender:
                return rule
        elif domain == rule.sender or domain.endswith("." + rule.sender):
            return rule
    return None


def sender_query(senders: list[str] | tuple[str, ...], *, newer_than_days: int) -> str:
    """``from:(a OR b) newer_than:Nd``; entries are already validated."""

    if not senders:
        raise InvalidSender("no senders")
    joined = " OR ".join(sorted(senders))
    return f"from:({joined}) newer_than:{max(1, int(newer_than_days))}d"


class SenderRepository(Protocol):
    def list(self, *, connection_id: str) -> list[SenderRule]: ...

    def replace(
        self, *, user_id: str, connection_id: str, senders: tuple[str, ...], now: datetime
    ) -> list[SenderRule]: ...

    def mark_backfilled(
        self, *, connection_id: str, senders: tuple[str, ...], now: datetime
    ) -> None: ...

    def delete(self, *, connection_id: str) -> None: ...


class InMemorySenderRepository:
    """Deterministic twin of ``PostgresSenderRepository``. Ownership and
    liveness of the connection are checked by the caller in memory mode."""

    def __init__(self) -> None:
        self._rows: dict[str, dict[str, SenderRule]] = {}
        self._lock = threading.Lock()

    def list(self, *, connection_id: str) -> list[SenderRule]:
        rows = self._rows.get(connection_id, {})
        return [rows[key] for key in sorted(rows)]

    def replace(
        self, *, user_id: str, connection_id: str, senders: tuple[str, ...], now: datetime
    ) -> list[SenderRule]:
        with self._lock:
            current = self._rows.get(connection_id, {})
            # Kept entries keep their backfill mark; new ones start unscanned.
            self._rows[connection_id] = {
                s: current.get(s) or SenderRule(sender=s, created_at=now) for s in senders
            }
        return self.list(connection_id=connection_id)

    def mark_backfilled(
        self, *, connection_id: str, senders: tuple[str, ...], now: datetime
    ) -> None:
        with self._lock:
            rows = self._rows.get(connection_id, {})
            for sender in senders:
                if sender in rows and rows[sender].backfilled_at is None:
                    rows[sender] = replace(rows[sender], backfilled_at=now)

    def delete(self, *, connection_id: str) -> None:
        with self._lock:
            self._rows.pop(connection_id, None)
