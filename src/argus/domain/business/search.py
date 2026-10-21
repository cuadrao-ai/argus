"""How a Business search query matches a record.

Words match as the canonical financial search matches them. An amount and a
fiscal number (RNC, NCF, e-CF) match only by value: the query read as an amount
by the canonical amount reader equals the record's amount, or the query's digits
equal the number's digits. Nothing here keeps an index; every read is current.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal, get_args

from argus.domain import financial_search
from argus.domain.ingestion.shortcuts.amounts import parse_amount

SearchKind = Literal[
    "expenses", "ventas", "receipts", "accounts", "email_deliveries", "email_senders"
]
KINDS: tuple[SearchKind, ...] = get_args(SearchKind)
# Characters a bare amount may carry besides its digits when no marker names its currency.
_BARE_AMOUNT = frozenset("0123456789.,$ ")


@dataclass(frozen=True)
class SearchQuery:
    text: str
    digits: str
    amount: Decimal | None
    currency: str | None


def digits(value: str) -> str:
    return "".join(character for character in value if character in "0123456789")


def parse(q: str) -> SearchQuery:
    """The query as words, as its digits, and as an amount when it reads as
    exactly one: "3450", "3,450.00", "$ 50" or "RD$3,450.00", never
    "ferretería 3450" or a signed amount."""

    read = parse_amount(q)
    bare = "currency" not in read.uncertain or set(q.strip()) <= _BARE_AMOUNT
    amount = (
        Decimal(read.amount)
        if read.amount is not None and "direction" not in read.uncertain and bare
        else None
    )
    return SearchQuery(financial_search.query_text(q), digits(q), amount, read.currency)


def exact(
    query: SearchQuery,
    *,
    amount: str | None = None,
    currency: str | None = None,
    numbers: Iterable[str] = (),
) -> bool:
    """The record's amount is the query's, in its currency when the query names
    one, or one of its fiscal numbers has exactly the query's digits."""

    if query.amount is not None and amount and query.currency in (None, currency):
        try:
            if Decimal(amount) == query.amount:
                return True
        except InvalidOperation:
            pass
    return bool(query.digits) and any(
        digits(number) == query.digits for number in numbers
    )


def matches(
    query: SearchQuery,
    text: str,
    *,
    amount: str | None = None,
    currency: str | None = None,
    numbers: Iterable[str] = (),
) -> bool:
    return financial_search.matches(query.text, text) or exact(
        query, amount=amount, currency=currency, numbers=numbers
    )
