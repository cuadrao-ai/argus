import re
import unicodedata

FILER_TAX_ID_LENGTH = {"rnc": 9, "cedula": 11}
COUNTERPARTY_ID_LENGTH = {
    "1": FILER_TAX_ID_LENGTH["rnc"],
    "2": FILER_TAX_ID_LENGTH["cedula"],
}

_DIGIT_RUN = r"(?<![0-9])(?<![0-9][ -])[0-9](?:[ -]?[0-9]){{{}}}(?![ -]?[0-9])"
_PRINTED_RNC = re.compile(f"{_DIGIT_RUN.format(10)}|{_DIGIT_RUN.format(8)}")
_PRINTED_NCF = re.compile(
    r"(?<![A-Za-z0-9])[BE][0-9]{8,12}(?![A-Za-z0-9])", re.IGNORECASE
)


# The only characters that may sit right next to an identifier, besides one
# space. Anything else adjacent keeps the whole read.
EDGE_PUNCTUATION = frozenset(":,.;()[]/")


def _note_letter(char: str) -> bool:
    """A letter that may start a label or note after one space: any Unicode
    letter whose compatibility form holds no digit."""

    return unicodedata.category(char).startswith("L") and not any(
        part.isdigit() for part in unicodedata.normalize("NFKC", char)
    )


def _edge_clean(side: str) -> bool:
    """Whether the text next to a candidate, nearest character first, ends it.
    Clean is the string boundary, an EDGE_PUNCTUATION character, or one space
    of any kind (Unicode Zs, so a PDF's no-break space counts) followed by the string boundary, an EDGE_PUNCTUATION character or a
    letter. Every other neighbor keeps the read whole."""

    if not side or side[0] in EDGE_PUNCTUATION:
        return True
    if unicodedata.category(side[0]) != "Zs":
        return False
    return len(side) == 1 or side[1] in EDGE_PUNCTUATION or _note_letter(side[1])


def _isolated(value: str, match: re.Match[str]) -> str:
    """The matched token when both of its edges are clean and the pattern does
    not match again later in the read, otherwise the read. A second identifier
    anywhere after the first, whatever separates them, keeps the read whole.
    The token itself is returned exactly as printed."""

    if match.re.search(value, match.end()) is not None:
        return value
    before = value[: match.start()][::-1]
    after = value[match.end() :]
    if _edge_clean(before) and _edge_clean(after):
        return match.group(0)
    return value


def printed_rnc(value: str) -> str:
    """The RNC or cédula as printed, without label or note text around it.
    The token is the first 9 or 11 digit number with its printed dashes or
    spaces. Each edge must be the string boundary, one of ": , . ; ( ) [ ] /",
    or one space (any Unicode Zs, such as a no-break space) followed by the boundary, one of those characters or a
    letter. So
    "RNC 1-23-45678-9 (ficticio)" gives "1-23-45678-9", and a read whose number
    runs on ("1 131000002", "131000002 9", "131000002ñ") or has no such number
    is returned unchanged."""

    match = _PRINTED_RNC.search(value)
    return value if match is None else _isolated(value, match)


def printed_ncf(value: str) -> str:
    """The NCF or e-CF number as printed, without label or note text around it.
    Same edge rule as printed_rnc. Characters are never padded, fixed or
    recased; a read with no clean B or E series token stays unchanged."""

    match = _PRINTED_NCF.search(value)
    return value if match is None else _isolated(value, match)


def identity_digits(value: str | None) -> str | None:
    """Digits only. Length is not decided here: a 9-digit RNC and an 11-digit
    cédula are both identities, and anything else is still the number we were given."""

    if value is None or re.fullmatch(r"[0-9 -]+", value) is None:
        return None
    digits = value.replace(" ", "").replace("-", "")
    return digits or None


def normalized_taxpayer_id(value: str | None) -> str | None:
    digits = identity_digits(value)
    if (
        digits is None
        or len(digits) not in set(FILER_TAX_ID_LENGTH.values())
        or not any(char != "0" for char in digits)
    ):
        return None
    return digits


def normalized_filer_tax_id(kind: str, value: str) -> str:
    if kind not in FILER_TAX_ID_LENGTH:
        raise ValueError("tax_id_type")
    digits = identity_digits(value)
    if digits is None:
        raise ValueError("tax_id_not_digits")
    if len(digits) != FILER_TAX_ID_LENGTH[kind]:
        raise ValueError("tax_id_length")
    if not any(char != "0" for char in digits):
        raise ValueError("tax_id_all_zero")
    return digits


def rnc_check_digit_ok(digits: str) -> bool:
    """Mod-11 over the first 8 digits. Weights 7, 9, 8, 6, 5, 4, 3, 2.
    Remainder 0 checks as 2, remainder 1 checks as 1, otherwise 11 minus the remainder."""

    if re.fullmatch(r"\d{9}", digits) is None:
        return False
    weights = (7, 9, 8, 6, 5, 4, 3, 2)
    remainder = (
        sum(
            int(digit) * weight for digit, weight in zip(digits[:8], weights, strict=True)
        )
        % 11
    )
    expected = 2 if remainder == 0 else 1 if remainder == 1 else 11 - remainder
    return expected == int(digits[8])


def cedula_check_digit_ok(digits: str) -> bool:
    """Luhn over the 11 digits. The check digit is the last one."""

    if re.fullmatch(r"\d{11}", digits) is None:
        return False
    total = 0
    for index, character in enumerate(reversed(digits)):
        number = int(character)
        if index % 2 == 1:
            number *= 2
            if number > 9:
                number -= 9
        total += number
    return total % 10 == 0


def normalized_ncf(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    return normalized if re.fullmatch(r"(?:B\d{10}|E\d{12})", normalized) else None


def document_identity(direction: str, taxpayer_id: str | None, ncf: str | None):
    number = normalized_ncf(ncf)
    if number is None:
        return None
    return (
        ("sale", number)
        if direction == "income"
        else ("purchase", normalized_taxpayer_id(taxpayer_id), number)
    )
