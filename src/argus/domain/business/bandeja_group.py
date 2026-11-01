"""Which Bandeja group an open receipt sits in, and the one reason it is not
Listos. The only owner of the rule: the receipt list, the counts and the
approval of a list all read it here. A group decides what the Bandeja shows and
what the faster approval admits. It never approves anything, and any open
receipt can still be approved alone.

Listos is a business purchase the server has confirmed in full. A sale, a
credit note and a receipt marked Personal stay out: the faster approval records
business purchases only. ``RULE`` runs in order, so a receipt with several gaps
names the first.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from argus.domain.business.contracts.dossier import ReviewFlag
from argus.domain.business.contracts.facts import (
    BusinessFacts,
    FiscalFacts,
    Known,
    is_personal,
)
from argus.domain.business.fiscal_identity import identity_digits
from argus.domain.business.receipt_activity import awaiting_owner
from argus.domain.business.receipts import Attention
from argus.domain.business.review_flags import CHECK_DIGIT

BandejaGroupName = Literal["listo", "attention"]
ListoGap = Literal[
    "reading",
    "not_read",
    "duplicate",
    "sale",
    "credit_note",
    "missing_merchant",
    "missing_date",
    "missing_amount",
    "missing_currency",
    "missing_rnc",
    "invalid_rnc",
    "missing_ncf",
    "invalid_ncf",
    "ecf_check_failed",
    "missing_itbis",
    "foreign_currency",
    "personal",
    "review_flag",
    "blocked",
    "unverified_sender",
]
BandejaReason = Literal[Attention, ListoGap]
ReadState = Literal["finished", "none", "unclear"]


@dataclass(frozen=True)
class DraftStanding:
    """What the rule reads of one open draft. ``sender`` is the email standing,
    None for a receipt that did not come by email."""

    draft_id: str
    version: int
    facts: BusinessFacts
    read: ReadState
    read_attention: Attention | None
    credit_note: bool
    ecf_failed: bool
    repeated: bool
    blockers: tuple[str, ...]
    flags: tuple[ReviewFlag, ...]
    sender: str | None = None


def _fiscal(draft: DraftStanding) -> FiscalFacts:
    return draft.facts.fiscal or FiscalFacts()


def _blank(fact: object) -> bool:
    return not isinstance(fact, Known) or not str(fact.value).strip()


def _lacks(draft: DraftStanding, name: str) -> bool:
    return _blank(getattr(draft.facts, name))


def _flagged(draft: DraftStanding, code: str) -> bool:
    return any(flag.code == code for flag in draft.flags)


def _no_number(draft: DraftStanding) -> bool:
    fiscal = _fiscal(draft)
    return _blank(fiscal.ecf) and _blank(fiscal.ncf)


def _invalid_rnc(draft: DraftStanding) -> bool:
    digits = identity_digits(_fiscal(draft).rnc.value)
    return len(digits or "") not in CHECK_DIGIT or _flagged(draft, "rnc_check_digit")


def _foreign(draft: DraftStanding) -> bool:
    return draft.facts.currency.value != "DOP"


RULE: tuple[tuple[BandejaReason, Callable[[DraftStanding], bool]], ...] = (
    ("not_read", lambda draft: draft.read == "none"),
    ("check_details", lambda draft: draft.read == "unclear"),
    ("several_purchases", lambda draft: draft.read_attention == "several_purchases"),
    ("no_purchase_found", lambda draft: draft.read_attention == "no_purchase_found"),
    (
        "duplicate",
        lambda draft: draft.repeated or "possible_duplicate" in draft.blockers,
    ),
    ("sale", lambda draft: draft.facts.kind.value == "income"),
    ("credit_note", lambda draft: draft.credit_note),
    ("missing_merchant", lambda draft: _lacks(draft, "counterparty")),
    ("missing_date", lambda draft: _lacks(draft, "occurred_on")),
    ("missing_amount", lambda draft: _lacks(draft, "amount")),
    ("missing_currency", lambda draft: _lacks(draft, "currency")),
    ("missing_rnc", lambda draft: _blank(_fiscal(draft).rnc)),
    ("invalid_rnc", _invalid_rnc),
    ("missing_ncf", _no_number),
    ("invalid_ncf", lambda draft: _flagged(draft, "ncf_malformed")),
    ("ecf_check_failed", lambda draft: draft.ecf_failed),
    ("missing_itbis", lambda draft: _blank(_fiscal(draft).itbis)),
    ("foreign_currency", _foreign),
    ("personal", lambda draft: is_personal(draft.facts)),
    ("review_flag", lambda draft: bool(draft.flags)),
    ("blocked", lambda draft: bool(draft.blockers)),
    ("unverified_sender", lambda draft: draft.sender not in (None, "authorized")),
)


def listo_reason(draft: DraftStanding) -> BandejaReason | None:
    """The first gap between this draft and Listos, or None when it is Listos."""

    return next((reason for reason, gap in RULE if gap(draft)), None)


def _row_reason(
    view: Mapping[str, Any], draft: DraftStanding | None
) -> BandejaReason | None:
    if view.get("read_pending"):
        return "reading"
    if view.get("attention"):
        return view["attention"]
    if draft is None:
        return "not_read" if view["status"] in ("saved", "queued") else "check_details"
    return listo_reason(draft)


def group_of(view: Mapping[str, Any], draft: DraftStanding | None) -> dict[str, Any]:
    """The group of a receipt row. A closed receipt and the email itself have
    none. ``draft_id`` and ``version`` are what an approval of this row names."""

    if not awaiting_owner(view):
        return {"group": None, "reason": None, "draft_id": None, "version": None}
    reason = _row_reason(view, draft)
    return {
        "group": "attention" if reason else "listo",
        "reason": reason,
        "draft_id": draft.draft_id if draft else None,
        "version": draft.version if draft else None,
    }
