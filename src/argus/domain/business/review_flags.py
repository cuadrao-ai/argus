"""What a person should look at again before approving a receipt.

A flag never changes a stored value: the RNC and NCF stay exactly as read.
Normalizing happens here, for the comparison only. ``confirm`` flags need an
explicit "approve anyway" on the approve request; the 606 export still refuses
them. An ITBIS flag only warns.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from argus.domain.business.contracts.dgii import (
    DgiiDeclaration,
)
from argus.domain.business.contracts.dossier import ReviewFlag
from argus.domain.business.contracts.facts import BusinessFacts, Known
from argus.domain.business.dgii_606_rules import itbis_limit
from argus.domain.business.fiscal_identity import (
    cedula_check_digit_ok,
    identity_digits,
    normalized_ncf,
    rnc_check_digit_ok,
)
from argus.domain.business.purchase_review import (
    amount_parts,
    exact_amount_text,
    net_amount,
)
from argus.domain.business.rnc_registry import RncRegistry, UnknownRncRegistry

CHECK_DIGIT = {9: rnc_check_digit_ok, 11: cedula_check_digit_ok}


def _known(fact: object) -> str | date | None:
    return fact.value if isinstance(fact, Known) else None


def itbis_too_high(total: Decimal, itbis: Decimal, on: date | None = None) -> bool:
    """ITBIS above the ceiling the 606 holds a row for, read on the pre-tax
    amount. A lower ITBIS (16%, exempt items) is never flagged."""

    base = net_amount(total=str(total), itbis=str(itbis))
    return itbis > itbis_limit(Decimal(base.amount), on)


def review_flags(
    facts: BusinessFacts, registry: RncRegistry | None = None,
    *, declaration: DgiiDeclaration | None = None,
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
        and itbis_too_high(Decimal(total), Decimal(itbis), _known(facts.occurred_on))
    ):
        flags.append(ReviewFlag(code="itbis_high", field="itbis", confirm=False))
    net = net_amount(facts, declaration)
    if total is not None and net.amount is not None:
        difference = Decimal(total) - Decimal(net.amount) - sum(amount_parts(facts, declaration))
        # An unknown ITBIS counts as zero and can only close a gap the Total leaves.
        if difference < Decimal("-0.01") or (itbis is not None and difference > Decimal("0.01")):
            flags.append(ReviewFlag(
                code="amounts_mismatch", field="amount", confirm=False,
                difference=exact_amount_text(difference),
            ))
    return tuple(flags)


def unconfirmed(flags: tuple[ReviewFlag, ...]) -> tuple[str, ...]:
    return tuple(flag.code for flag in flags if flag.confirm)
