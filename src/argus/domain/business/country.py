"""The countries a Business can belong to, and what each one implies.

This registry is the one owner of which country rules apply to a Business.
Later work adds each country's fiscal schema here; no other module keeps a list.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class BusinessCountry:
    code: str
    currency: str


CountryCode = Literal["DO", "US", "CA"]

COUNTRIES: Mapping[str, BusinessCountry] = {
    country.code: country
    for country in (
        BusinessCountry("DO", "DOP"),
        BusinessCountry("US", "USD"),
        BusinessCountry("CA", "CAD"),
    )
}
DEFAULT_COUNTRY = "DO"


def business_country(code: str) -> BusinessCountry:
    return COUNTRIES[code]
