"""Transacciones: every bank movement in a period, its state, and its totals.

A movement's state is derived on read from the line, its live outcome, and
its open offers. Nothing here stores a state. The settlement a match writes is
planned here and stored by the outcomes store.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from argus.domain.business.bank.matching import derive_confidence, expected_kind
from argus.domain.business.bank.model import (
    MATCH_WINDOW_DAYS,
    BankLine,
    ScoreParts,
    TargetKind,
)
from argus.domain.business.month_close import MonthDocument, Settlement, to_minor
from argus.domain.recording.currency import format_minor_units

MovementState = Literal[
    "igualada", "sugerencia", "falta_comprobante", "no_lleva_comprobante"
]
ItemState = MovementState | Literal["sin_movimiento"]
Segment = Literal["por_igualar", "igualadas", "todas"]
Method = Literal["efectivo", "transferencia", "tarjeta", "otro"]

POR_IGUALAR: frozenset[str] = frozenset(
    {"sugerencia", "falta_comprobante", "sin_movimiento"}
)
_SEGMENT_STATES: dict[str, frozenset[str]] = {
    "por_igualar": POR_IGUALAR,
    "igualadas": frozenset({"igualada", "no_lleva_comprobante"}),
    "todas": frozenset(
        {"igualada", "sugerencia", "falta_comprobante", "no_lleva_comprobante"}
    ),
}
_GROUP_RANK = {"sugerencia": 0, "falta_comprobante": 1, "sin_movimiento": 2}
_METHOD_BY_ACCOUNT_TYPE: dict[str, Method] = {
    "checking": "transferencia",
    "savings": "transferencia",
    "credit_card": "tarjeta",
    "cash": "efectivo",
}
_ROLE_KIND: dict[str, TargetKind] = {"receipt": "receipt", "invoice": "venta"}
_SETTLED: dict[str, str] = {"receipt": "pagado", "venta": "cobrado"}
MAX_PAGE = 200
DISPOSITIONS = ("cargo_banco", "entre_cuentas", "compra_informal", "personal")


class InvalidCursor(ValueError):
    pass


def method_for(account_type: str) -> Method:
    """How money left or reached this account, from its type alone."""

    return _METHOD_BY_ACCOUNT_TYPE.get(account_type, "otro")


def movement_state(
    amount: Decimal, *, matched: bool, disposition: str | None, has_offer: bool
) -> tuple[MovementState, str | None]:
    """The one rule for a line's state and, when it needs no comprobante, why."""

    if matched:
        return "igualada", None
    if disposition is not None:
        return "no_lleva_comprobante", disposition
    if amount == 0:
        return "no_lleva_comprobante", "monto_cero"
    if has_offer:
        return "sugerencia", None
    return "falta_comprobante", None


@dataclass(frozen=True)
class Account:
    bank_account_id: str
    account_id: str
    name: str | None
    type: str
    currency: str
    covered_through: date | None

    @property
    def method(self) -> Method:
        return method_for(self.type)


@dataclass(frozen=True)
class Document:
    """A recorded receipt or venta, as the bank can match it."""

    activity_id: str
    kind: TargetKind
    currency: str
    total_minor: int
    itbis_minor: int | None
    occurred_on: date
    counterparty: str | None
    rnc: str | None
    ncf: str | None
    ecf: str | None
    status: str
    settled_on: date | None
    payment_method: str | None
    account_id: str | None
    category_id: str | None

    @property
    def amount(self) -> Decimal:
        return Decimal(format_minor_units(self.total_minor, self.currency))

    @property
    def merchant(self) -> str | None:
        return self.counterparty

    @property
    def id(self) -> str:
        return self.activity_id

    @property
    def approved(self) -> bool:
        return True


def documents_from(
    month_documents: Iterable[MonthDocument], activities: Mapping[str, Mapping]
) -> tuple[Document, ...]:
    """Recorded income and expense activities of the Business, with the account
    they were recorded on and their category."""

    found = []
    for document in month_documents:
        activity = activities.get(document.activity_id, {})
        legs = activity.get("legs") or ()
        found.append(
            Document(
                activity_id=document.activity_id,
                kind=_ROLE_KIND[document.role],
                currency=document.currency,
                total_minor=document.total_minor,
                itbis_minor=document.itbis_minor,
                occurred_on=document.occurred_on,
                counterparty=document.counterparty,
                rnc=document.rnc,
                ncf=document.ncf,
                ecf=document.ecf,
                status=document.status,
                settled_on=document.settled_on,
                payment_method=document.payment_method,
                account_id=str(legs[0]["account_id"]) if legs else None,
                category_id=activity.get("category_id"),
            )
        )
    return tuple(found)


@dataclass(frozen=True)
class Offer:
    """A pending pair the person can still confirm."""

    suggestion_id: str
    document: Document
    parts: ScoreParts

    @property
    def confidence(self) -> Decimal:
        return derive_confidence(self.parts)


@dataclass(frozen=True)
class StoredPair:
    """A stored suggestion row, reduced to what the read needs."""

    suggestion_id: str
    line_id: str
    target_kind: TargetKind
    target_id: str
    status: str
    parts: ScoreParts


@dataclass(frozen=True)
class LiveOutcome:
    """A line's one live outcome: a match to a document, or a reason it needs
    no comprobante."""

    line_id: str
    kind: Literal["match", "no_receipt"]
    target_id: str | None
    reason: str | None


def taken_documents(outcomes: Mapping[str, LiveOutcome]) -> frozenset[str]:
    """Every document a live match holds."""

    return frozenset(
        outcome.target_id
        for outcome in outcomes.values()
        if outcome.kind == "match" and outcome.target_id is not None
    )


def applied_settlement(kind: TargetKind, line: BankLine, account: Account) -> Settlement:
    """The settlement a match writes: settled on the movement's date, by the
    method of the account the movement came from."""

    return Settlement(_SETTLED[kind], line.occurred_on, account.method)


def match_refusal(line: BankLine, document: Document) -> str | None:
    """Why a person cannot match this line to this document, or None. One
    movement to one document of the same sense, currency, and exact amount."""

    if (
        expected_kind(line.amount) != document.kind
        or line.currency != document.currency
        or abs(line.amount) != document.amount
    ):
        return "document_not_matchable"
    return None


@dataclass(frozen=True)
class Movement:
    line: BankLine
    account: Account
    state: MovementState
    reason: str | None
    document: Document | None
    offers: tuple[Offer, ...]

    @property
    def amount_minor(self) -> int:
        return to_minor(str(self.line.amount), self.line.currency)

    @property
    def counterparty(self) -> str:
        if self.document is not None and self.document.counterparty:
            return self.document.counterparty
        return " ".join(self.line.description.split())


@dataclass(frozen=True)
class Unmoved:
    """A settled document from a bank account that the statement does not show."""

    document: Document
    account: Account
    state: Literal["sin_movimiento"] = "sin_movimiento"


Item = Movement | Unmoved


def build_movements(
    lines: Sequence[BankLine],
    accounts: Mapping[str, Account],
    documents: Mapping[str, Document],
    pairs: Sequence[StoredPair],
    outcomes: Mapping[str, LiveOutcome],
    taken: frozenset[str],
) -> list[Movement]:
    """Each line with its state. ``pairs`` are the stored offers of these lines,
    ``outcomes`` their live outcomes by line, and ``taken`` every document a
    live match holds in the Business. A pending pair is an offer while its line
    has no outcome and its document is free."""

    movements = []
    for line in lines:
        line_id = str(line.id)
        outcome = outcomes.get(line_id)
        matched = (
            documents.get(outcome.target_id or "")
            if outcome is not None and outcome.kind == "match"
            else None
        )
        offers = ()
        if outcome is None:
            offers = tuple(
                sorted(
                    (
                        Offer(pair.suggestion_id, documents[pair.target_id], pair.parts)
                        for pair in pairs
                        if pair.line_id == line_id
                        and pair.status == "pending"
                        and pair.target_id in documents
                        and documents[pair.target_id].kind == pair.target_kind
                        and pair.target_id not in taken
                    ),
                    key=lambda offer: (-offer.confidence, offer.suggestion_id),
                )
            )
        state, reason = movement_state(
            line.amount,
            matched=outcome is not None and outcome.kind == "match",
            disposition=outcome.reason if outcome is not None else None,
            has_offer=bool(offers),
        )
        movements.append(
            Movement(
                line=line,
                account=accounts[str(line.bank_account_id)],
                state=state,
                reason=reason,
                document=matched,
                offers=offers,
            )
        )
    return movements


def unmoved_documents(
    documents: Iterable[Document],
    accounts: Iterable[Account],
    matched: frozenset[str],
    period_start: date,
    period_end: date,
) -> list[Unmoved]:
    """Settled documents (only a settled one has a date) recorded on a bank
    account, in the period, with no matched line, whose settlement date plus
    the match window is on or before the account's coverage date. A date the bank has not reached is unknown,
    not missing."""

    by_account = {account.account_id: account for account in accounts}
    window = timedelta(days=MATCH_WINDOW_DAYS)
    found = []
    for document in documents:
        account = by_account.get(document.account_id or "")
        if (
            account is None
            or account.covered_through is None
            or document.settled_on is None
            or document.activity_id in matched
            or not period_start <= document.occurred_on <= period_end
            or document.settled_on + window > account.covered_through
        ):
            continue
        found.append(Unmoved(document, account))
    return found


def reasons(line: BankLine, offer: Offer) -> list[dict[str, object]]:
    """Why the server offers this pair, as data codes the web words."""

    found: list[dict[str, object]] = [{"code": "monto_exacto"}]
    days = (offer.document.occurred_on - line.occurred_on).days
    if days == 0:
        found.append({"code": "misma_fecha"})
    else:
        found.append({"code": "fecha_cercana", "days": days})
    if offer.parts.merchant_score > 0:
        found.append({"code": "nombre_parecido"})
    return found


COUNT_KEYS = (
    "movimientos",
    "igualadas",
    "no_lleva_comprobante",
    "sugerencias",
    "falta_comprobante",
    "sin_movimiento",
    "por_igualar",
)


@dataclass
class _CurrencyTotals:
    entradas: int = 0
    salidas: int = 0
    por_igualar: int = 0
    counts: dict[str, int] = field(default_factory=lambda: dict.fromkeys(COUNT_KEYS, 0))


_COUNT_KEY = {
    "igualada": "igualadas",
    "no_lleva_comprobante": "no_lleva_comprobante",
    "sugerencia": "sugerencias",
    "falta_comprobante": "falta_comprobante",
    "sin_movimiento": "sin_movimiento",
}


def totals(items: Iterable[Item]) -> list[dict]:
    """Entradas, Salidas, Por igualar and the counts, one block per currency.
    Currencies are never added together."""

    blocks: dict[str, _CurrencyTotals] = {}
    for item in items:
        block = blocks.setdefault(_currency_of(item), _CurrencyTotals())
        if isinstance(item, Movement):
            minor = item.amount_minor
            block.counts["movimientos"] += 1
            if minor > 0:
                block.entradas += minor
            else:
                block.salidas -= minor
            magnitude = abs(minor)
        else:
            magnitude = item.document.total_minor
        block.counts[_COUNT_KEY[item.state]] += 1
        if item.state in POR_IGUALAR:
            block.counts["por_igualar"] += 1
            block.por_igualar += magnitude
    return [
        {
            "currency": currency,
            "entradas_minor": block.entradas,
            "entradas": format_minor_units(block.entradas, currency),
            "salidas_minor": block.salidas,
            "salidas": format_minor_units(block.salidas, currency),
            "por_igualar_minor": block.por_igualar,
            "por_igualar": format_minor_units(block.por_igualar, currency),
            "counts": dict(block.counts),
        }
        for currency, block in sorted(blocks.items())
    ]


def period_counts(blocks: Iterable[dict]) -> dict[str, int]:
    """The period's counts across every currency, added from the per-currency
    blocks. Counts are not money, so adding them across currencies is sound."""

    found = dict.fromkeys(COUNT_KEYS, 0)
    for block in blocks:
        for key in COUNT_KEYS:
            found[key] += block["counts"][key]
    return found


def _sense_of(item: Item) -> str:
    if isinstance(item, Movement):
        return item.line.sense
    return "charge" if item.document.kind == "receipt" else "deposit"


def _currency_of(item: Item) -> str:
    if isinstance(item, Movement):
        return item.line.currency
    return item.document.currency


def _chosen(items: Iterable[Item], segment: Segment, sense: str | None) -> list[Item]:
    """The rows the segment and sense select, in every currency."""

    states = _SEGMENT_STATES[segment]
    return [
        item
        for item in items
        if item.state in states and (sense is None or _sense_of(item) == sense)
    ]


def other_currencies(
    items: Iterable[Item], *, segment: Segment, sense: str | None, currency: str | None
) -> list[dict]:
    """How many of the segment's rows the chosen currency leaves out, per
    other currency, sorted by code. Nothing is left out while no currency is chosen."""

    if currency is None:
        return []
    counts: dict[str, int] = {}
    for item in _chosen(items, segment, sense):
        found = _currency_of(item)
        if found != currency:
            counts[found] = counts.get(found, 0) + 1
    return [{"currency": code, "count": count} for code, count in sorted(counts.items())]


def _sort_key(item: Item, segment: Segment) -> tuple[int, int, int, str]:
    if isinstance(item, Movement):
        day, identifier = item.line.occurred_on, str(item.line.id)
        best = item.offers[0].confidence if item.offers else Decimal(0)
    else:
        day, identifier = item.document.occurred_on, item.document.activity_id
        best = Decimal(0)
    rank = _GROUP_RANK.get(item.state, 0) if segment == "por_igualar" else 0
    confidence = -int(best * 1000) if segment == "por_igualar" else 0
    return (rank, confidence, -day.toordinal(), identifier)


def encode_cursor(key: tuple[int, int, int, str]) -> str:
    raw = json.dumps(list(key), separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[int, int, int, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded.encode()))
    except (binascii.Error, ValueError, UnicodeDecodeError) as error:
        raise InvalidCursor("invalid_cursor") from error
    if (
        not isinstance(value, list)
        or len(value) != 4
        or not all(isinstance(part, int) for part in value[:3])
        or not isinstance(value[3], str)
    ):
        raise InvalidCursor("invalid_cursor")
    return (value[0], value[1], value[2], value[3])


def page(
    items: Sequence[Item],
    *,
    segment: Segment,
    sense: str | None,
    limit: int,
    cursor: str | None,
    currency: str | None = None,
) -> tuple[list[Item], str | None]:
    """One page of a segment, in the chosen currency when one is given. Por
    igualar groups Sugerencias (best offer first), Falta comprobante, then
    Comprobantes sin movimiento; each group and every other segment runs
    newest first."""

    chosen = [
        item
        for item in _chosen(items, segment, sense)
        if currency is None or _currency_of(item) == currency
    ]
    keyed = sorted(
        ((_sort_key(item, segment), item) for item in chosen), key=lambda pair: pair[0]
    )
    if cursor is not None:
        after = decode_cursor(cursor)
        keyed = [pair for pair in keyed if pair[0] > after]
    shown = keyed[:limit]
    following = encode_cursor(shown[-1][0]) if len(keyed) > limit else None
    return [item for _, item in shown], following


def _money(minor: int | None, currency: str) -> str | None:
    return None if minor is None else format_minor_units(minor, currency)


def _day(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def document_payload(document: Document) -> dict:
    return {
        "activity_id": document.activity_id,
        "kind": document.kind,
        "counterparty": document.counterparty,
        "occurred_on": document.occurred_on.isoformat(),
        "currency": document.currency,
        "total_minor": document.total_minor,
        "total": _money(document.total_minor, document.currency),
        "itbis_minor": document.itbis_minor,
        "itbis": _money(document.itbis_minor, document.currency),
        "rnc": document.rnc,
        "ncf": document.ncf,
        "ecf": document.ecf,
        "status": document.status,
        "settled_on": _day(document.settled_on),
        "payment_method": document.payment_method,
        "category_id": document.category_id,
    }


def account_payload(account: Account) -> dict:
    return {"account_id": account.account_id, "name": account.name, "type": account.type}


def coverage_payload(account: Account) -> dict:
    """The newest movement date the bank has shown for this account. A later
    date is unknown, not missing."""

    return {
        **account_payload(account),
        "bank_account_id": account.bank_account_id,
        "currency": account.currency,
        "covered_through": _day(account.covered_through),
    }


def item_payload(item: Item) -> dict:
    """One row of the table. A movement is a bank line; a document is a
    settled comprobante the statement does not show."""

    if isinstance(item, Unmoved):
        document = item.document
        signed = (
            -document.total_minor if document.kind == "receipt" else document.total_minor
        )
        return {
            "kind": "document",
            "id": document.activity_id,
            "occurred_on": document.occurred_on.isoformat(),
            "description": None,
            "counterparty": document.counterparty,
            "sense": _sense_of(item),
            "currency": document.currency,
            "amount_minor": signed,
            "amount": format_minor_units(signed, document.currency),
            "state": item.state,
            "reason": None,
            "category_id": document.category_id,
            "account": account_payload(item.account),
            "method": document.payment_method,
            "document": document_payload(document),
            "suggestions": [],
        }
    line = item.line
    return {
        "kind": "movement",
        "id": str(line.id),
        "occurred_on": line.occurred_on.isoformat(),
        "description": line.description,
        "counterparty": item.counterparty,
        "sense": line.sense,
        "currency": line.currency,
        "amount_minor": item.amount_minor,
        "amount": format_minor_units(item.amount_minor, line.currency),
        "state": item.state,
        "reason": item.reason,
        "category_id": item.document.category_id if item.document else None,
        "account": account_payload(item.account),
        "method": item.account.method,
        "document": document_payload(item.document) if item.document else None,
        "suggestions": [
            {
                "id": offer.suggestion_id,
                "confidence": str(offer.confidence),
                "reasons": reasons(line, offer),
                "document": document_payload(offer.document),
            }
            for offer in item.offers
        ],
    }
