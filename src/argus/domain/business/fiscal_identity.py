import re


def normalized_taxpayer_id(value: str | None) -> str | None:
    if value is None or re.fullmatch(r"[0-9 -]+", value) is None:
        return None
    digits = value.replace(" ", "").replace("-", "")
    return (
        digits if len(digits) in {9, 11} and any(char != "0" for char in digits) else None
    )


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
