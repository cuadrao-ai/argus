import re

FILER_TAX_ID_LENGTH = {"rnc": 9, "cedula": 11}
COUNTERPARTY_ID_LENGTH = {
    "1": FILER_TAX_ID_LENGTH["rnc"],
    "2": FILER_TAX_ID_LENGTH["cedula"],
}


def taxpayer_digits(value: str | None) -> str | None:
    if value is None or re.fullmatch(r"[0-9 -]+", value) is None:
        return None
    return value.replace(" ", "").replace("-", "") or None


def normalized_taxpayer_id(value: str | None) -> str | None:
    digits = taxpayer_digits(value)
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
    digits = taxpayer_digits(value)
    if digits is None:
        raise ValueError("tax_id_not_digits")
    if len(digits) != FILER_TAX_ID_LENGTH[kind]:
        raise ValueError("tax_id_length")
    if not any(char != "0" for char in digits):
        raise ValueError("tax_id_all_zero")
    return digits


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
