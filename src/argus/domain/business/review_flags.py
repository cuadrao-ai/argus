"""What a person should look at again before approving a receipt.

A flag never changes a stored value: the RNC and NCF stay exactly as read.
Normalizing happens here, for the comparison only. ``confirm`` flags need an
explicit "approve anyway" on the approve request; the 606 export still refuses
them. An ITBIS flag and a date flag only warn.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from loguru import logger

from argus.domain.business import ledger
from argus.domain.business.contracts.dossier import ReviewFlag
from argus.domain.business.contracts.facts import BusinessFacts, Known
from argus.domain.business.fiscal_identity import (
    cedula_check_digit_ok,
    identity_digits,
    normalized_ncf,
    rnc_check_digit_ok,
)
from argus.domain.business.rnc_registry import RncRegistry, UnknownRncRegistry
from argus.domain.recording.records import DEFAULT_TIME_ZONE

ITBIS_RATE = Decimal("0.18")
ITBIS_TOLERANCE = Decimal("1.00")
CHECK_DIGIT = {9: rnc_check_digit_ok, 11: cedula_check_digit_ok}
# A purchase receipt reaches the accountant within about 30 days of its issue.
ISSUE_DATE_WINDOW = timedelta(days=30)
READ_ORIGINS = frozenset({"extracted", "qr_decoded"})


def _known(fact: object) -> str | None:
    return fact.value if isinstance(fact, Known) else None


def itbis_too_high(total: Decimal, itbis: Decimal) -> bool:
    """ITBIS above 18% of the pre-tax amount, plus 1.00 in the receipt's own
    currency. A lower ITBIS (16%, exempt items) is never flagged."""

    return itbis > (total - itbis) * ITBIS_RATE + ITBIS_TOLERANCE


def _date_flag(
    facts: BusinessFacts, received: Mapping[UUID, datetime], today: date
) -> ReviewFlag | None:
    """A read date after today or after the day its file arrived, or more than
    30 days before that day: a date the read may have taken from another line,
    such as the NCF's "válido hasta". A date a person gave is never flagged."""

    fact = facts.occurred_on
    if not isinstance(fact, Known) or fact.origin not in READ_ORIGINS:
        return None
    arrivals = [received[source] for source in fact.source_ids if source in received]
    arrived = (
        min(arrivals).astimezone(ZoneInfo(DEFAULT_TIME_ZONE)).date() if arrivals else None
    )
    if fact.value > min(today, arrived or today):
        code = "issue_date_future"
    elif arrived is not None and fact.value < arrived - ISSUE_DATE_WINDOW:
        code = "issue_date_old"
    else:
        return None
    logger.info(
        "business_review_flag code={} origin={} days_from_arrival={}",
        code,
        fact.origin,
        None if arrived is None else (fact.value - arrived).days,
    )
    return ReviewFlag(code=code, field="occurred_on", confirm=False)


def review_flags(
    facts: BusinessFacts,
    registry: RncRegistry | None = None,
    *,
    received: Mapping[UUID, datetime] | None = None,
    today: date | None = None,
) -> tuple[ReviewFlag, ...]:
    """A number the DGII register lists is never a check-digit flag, the same
    rule the 606 export applies. ``received`` maps the draft's attachment
    sources to when each arrived."""

    dated = _date_flag(facts, received or {}, today or ledger.today())
    flags = [] if dated is None else [dated]
    fiscal = facts.fiscal
    if fiscal is None:
        return tuple(flags)
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
