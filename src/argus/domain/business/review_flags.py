"""What a person should look at again before approving a receipt.

A flag never changes a stored value: the RNC and NCF stay exactly as read.
Normalizing happens here, for the comparison only. ``confirm`` flags need an
explicit "approve anyway" on the approve request; the 606 export still refuses
them. An ITBIS flag only warns.
"""

from __future__ import annotations

from decimal import Decimal

from argus.domain.business.contracts.dossier import ReviewFlag
from argus.domain.business.contracts.facts import BusinessFacts, Known
from argus.domain.business.fiscal_identity import (
    cedula_check_digit_ok,
    identity_digits,
    normalized_ncf,
    rnc_check_digit_ok,
)
from argus.domain.business.rnc_registry import RncRegistry, UnknownRncRegistry

ITBIS_RATE = Decimal("0.18")
ITBIS_TOLERANCE = Decimal("1.00")
CHECK_DIGIT = {9: rnc_check_digit_ok, 11: cedula_check_digit_ok}


def _known(fact: object) -> str | None:
    return fact.value if isinstance(fact, Known) else None


def itbis_too_high(total: Decimal, itbis: Decimal) -> bool:
    """ITBIS above 18% of the pre-tax amount, plus 1.00 in the receipt's own
    currency. A lower ITBIS (16%, exempt items) is never flagged."""

    return itbis > (total - itbis) * ITBIS_RATE + ITBIS_TOLERANCE


def review_flags(
    facts: BusinessFacts, registry: RncRegistry | None = None
) -> tuple[ReviewFlag, ...]:
    """A number the DGII register lists is never a check-digit flag, the same
    rule the 606 export applies."""

    fiscal = facts.fiscal
    if fiscal is None:
        return ()
    flags = []
    digits = identity_digits(_known(fiscal.rnc))
    check = CHECK_DIGIT.get(len(digits or ""))
    if (
        check is not None
        and not check(digits)
        and (registry or UnknownRncRegistry()).lookup(digits) is None
    ):
        flags.append(ReviewFlag(code="rnc_check_digit", field="rnc", confirm=True))
    number = _known(fiscal.ecf) or _known(fiscal.ncf)
    if number and normalized_ncf(number) is None:
        flags.append(ReviewFlag(code="ncf_malformed", field="ncf", confirm=True))
    total, itbis = _known(facts.amount), _known(fiscal.itbis)
    if (
        total is not None
        and itbis is not None
        and itbis_too_high(Decimal(total), Decimal(itbis))
    ):
        flags.append(ReviewFlag(code="itbis_high", field="itbis", confirm=False))
    return tuple(flags)


def unconfirmed(flags: tuple[ReviewFlag, ...]) -> tuple[str, ...]:
    return tuple(flag.code for flag in flags if flag.confirm)
