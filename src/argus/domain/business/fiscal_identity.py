import re

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


def printed_rnc(value: str) -> str:
    """The RNC or cédula as printed, without label or note text around it.
    A read with no 9 or 11 digit number is returned unchanged."""

    match = _PRINTED_RNC.search(value)
    return match.group(0) if match else value


def printed_ncf(value: str) -> str:
    """The NCF or e-CF number as printed, without label or note text around it.
    Digits are never padded or fixed; a read with no B or E series stays unchanged."""

    match = _PRINTED_NCF.search(value)
    return match.group(0) if match else value


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
