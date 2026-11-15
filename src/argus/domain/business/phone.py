"""The phone rule: Dominican Republic and United States numbers only."""

import re
from typing import Literal

from argus.domain.business.phone_area_codes import PHONE_AREA_CODES

PhoneRefusal = Literal["empty", "length", "format", "region"]


class PhoneRefused(ValueError):
    def __init__(self, reason: PhoneRefusal) -> None:
        super().__init__(reason)
        self.reason = reason


def national_phone(raw: str) -> str:
    """The ten national digits of a number typed in national or +1 form."""
    plus = raw.lstrip().startswith("+")
    digits = re.sub(r"[^0-9]", "", raw)
    if not digits:
        raise PhoneRefused("empty")
    if plus and digits[0] != "1":
        raise PhoneRefused("region")
    if len(digits) == 10 and not plus:
        national = digits
    elif len(digits) == 11 and digits[0] == "1":
        national = digits[1:]
    else:
        raise PhoneRefused("length")
    if not re.fullmatch(r"[2-9][0-9]{2}[2-9][0-9]{6}", national):
        raise PhoneRefused("format")
    if national[:3] not in PHONE_AREA_CODES:
        raise PhoneRefused("region")
    return national
