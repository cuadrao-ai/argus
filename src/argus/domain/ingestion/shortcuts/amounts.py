"""Deterministic reading of a formatted amount as Wallet hands it to Shortcuts.

The Wallet trigger gives a display string ("RD$1,250.00", "$12.50",
"1.250,00 €"), not a number and not a currency code. This reads the magnitude
only when the separators leave a single possible value, and a currency only
when the marker names exactly one. Everything else stays unresolved and marked
uncertain for the person: "$" is DOP or USD in the Dominican Republic, and
"1,250" is twelve hundred fifty or one and a quarter depending on locale.

It is a character-level number parser, not a reader of meaning: the input is
one short amount field, never free text.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

MAX_AMOUNT_TEXT = 64
# The contract refuses amounts with more digits; past it the text is not a
# purchase anyone made, so it stays unresolved instead of failing the request.
MAX_AMOUNT_DIGITS = 18

# Markers that name exactly one ISO 4217 currency. Bare "$" and "¥" name
# several, so they are deliberately absent and read as ambiguous.
_UNAMBIGUOUS = {
    "RD$": "DOP",
    "RD": "DOP",
    "US$": "USD",
    "U$S": "USD",
    "€": "EUR",
    "£": "GBP",
}
# Codes written out on the amount itself ("USD 12.50", "12,50 EUR"). A short
# list on purpose: an unlisted three-letter word is not taken as a currency.
_ISO_MARKERS = frozenset(
    {"DOP", "USD", "EUR", "GBP", "CAD", "MXN", "COP", "BRL", "CHF", "JPY", "CNY"}
)
_GROUPING_SPACES = {" ", " ", " ", " ", "'", "’"}
_MINUS = {"-", "\u2212"}
_SIGNS = _MINUS | {"+", "(", ")"}


@dataclass(frozen=True)
class ParsedAmount:
    amount: str | None
    currency: str | None
    uncertain: frozenset[str]


def parse_amount(
    text: str | None,
    *,
    currency_code: str | None = None,
    grouping: str | None = None,
) -> ParsedAmount:
    """Magnitude and currency from a formatted amount; doubt is listed.

    ``currency_code`` is an explicit ISO code the shortcut sent alongside the
    text. It settles only a bare "$" or an amount with no marker; any other
    marker it disagrees with or cannot vouch for ("R$", "€", "¥") leaves the
    currency unresolved. A sign or parentheses is doubt about direction: a
    refund, a reversal or just a display style, never decided here.

    ``grouping`` is the thousands separator the text's source groups by (","
    in a Business search box), so "3,450" there is one value. Without it,
    "1,250" and "1.250" stay unresolved.
    """

    uncertain: set[str] = set()
    raw = (text or "").strip()
    if not raw:
        return ParsedAmount(None, _iso(currency_code), frozenset())
    if len(raw) > MAX_AMOUNT_TEXT:
        return ParsedAmount(None, None, frozenset({"amount", "currency"}))
    marker, number, signed = _split(raw)
    amount = _magnitude(number, grouping) if number is not None else None
    if amount is None:
        uncertain.add("amount")
    if signed:
        uncertain.add("direction")
    currency, currency_doubt = _currency(marker, _iso(currency_code))
    if currency_doubt:
        uncertain.add("currency")
    return ParsedAmount(amount, currency, frozenset(uncertain))


def _iso(code: str | None) -> str | None:
    if code is None:
        return None
    code = code.strip().upper()
    if len(code) == 3 and code.isascii() and code.isalpha():
        return code
    return None


def _split(raw: str) -> tuple[str, str | None, bool]:
    """Marker text, the numeric core between it, and whether a sign showed."""

    start = 0
    while start < len(raw) and not raw[start].isdigit():
        start += 1
    end = len(raw)
    while end > start and not raw[end - 1].isdigit():
        end -= 1
    edges = raw[:start] + raw[end:]
    signed = any(c in _SIGNS for c in edges)
    marker = " ".join("".join(c for c in edges if c not in _SIGNS).split())
    if start >= end or any(c in ".," for c in edges):
        # No digits, or a separator outside them (".99", "12."): unreadable.
        return marker, None, signed
    core = raw[start:end]
    if any(not (c.isdigit() or c in ".," or c in _GROUPING_SPACES) for c in core):
        return marker, None, signed
    if any(c.isdigit() and not c.isascii() for c in core):
        return marker, None, signed
    if sum(c.isdigit() for c in core) > MAX_AMOUNT_DIGITS:
        return marker, None, signed
    return marker, core, signed


def _currency(marker: str, explicit: str | None) -> tuple[str | None, bool]:
    compact = "".join(marker.split()).upper()
    if not compact:
        # Nothing on the amount: an explicit code is the only statement.
        return explicit, False
    named = _UNAMBIGUOUS.get(compact)
    if named is None and compact in _ISO_MARKERS:
        named = compact
    if named is not None:
        if explicit is not None and explicit != named:
            return None, True
        return named, False
    # A bare "$" is pesos or dollars: only an explicit ISO code settles it.
    # Any other unlisted marker ("R$", "C$", "¥") stays open even then.
    if compact == "$" and explicit is not None:
        return explicit, False
    return None, True


def _magnitude(core: str, grouping: str | None = None) -> str | None:
    for space in _GROUPING_SPACES:
        if space in core:
            core = _ungroup(core, space)
            if core is None:
                return None
    has_dot, has_comma = "." in core, "," in core
    if has_dot and has_comma:
        decimal_sep = "." if core.rfind(".") > core.rfind(",") else ","
        group_sep = "," if decimal_sep == "." else "."
        if core.count(decimal_sep) != 1:
            return None
        whole, fraction = core.split(decimal_sep)
        whole = _ungroup(whole, group_sep)
        if whole is None:
            return None
        return _decimal(whole, fraction)
    sep = "." if has_dot else "," if has_comma else None
    if sep is None:
        return _decimal(core, "")
    if core.count(sep) > 1:
        whole = _ungroup(core, sep)
        return None if whole is None else _decimal(whole, "")
    whole, fraction = core.split(sep)
    if len(fraction) == 3 and whole:
        # "1,250" / "1.250": thousands in one locale, decimals in another,
        # unless the source groups by this separator.
        if sep != grouping:
            return None
        whole = _ungroup(core, sep)
        return None if whole is None else _decimal(whole, "")
    return _decimal(whole or "0", fraction)


def _ungroup(text: str, sep: str) -> str | None:
    """Remove a grouping separator only where groups are of three digits."""

    if sep not in text:
        return text
    parts = text.split(sep)
    head, rest = parts[0], parts[1:]
    if not head or len(head) > 3:
        return None
    if any(len(part) != 3 for part in rest[:-1]):
        return None
    last = rest[-1]
    # The final group may still carry a decimal part ("1 250,00").
    digits = last.split(",")[0].split(".")[0]
    if len(digits) != 3:
        return None
    return head + "".join(rest)


def _decimal(whole: str, fraction: str) -> str | None:
    if not whole.isdigit() or (fraction and not fraction.isdigit()):
        return None
    try:
        value = Decimal(f"{whole}.{fraction}" if fraction else whole)
    except InvalidOperation:
        return None
    return format(value, "f")
