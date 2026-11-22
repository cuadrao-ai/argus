"""Which Bandeja group a row sits in, the one reason it is not Listos, and the
one label the list shows for it. The only owner of the rule: the receipt list,
the notes, the emails, the counts and every approval read it here. A group
decides what the Bandeja shows and what an approval admits. A Listos record is
accepted as it is. A record with gaps is accepted alone, never in a list, and
only when a person may accept over each gap and the accept names every one.

Listos is a record the server has confirmed in full, a sale, a receipt marked
Personal and one in a foreign currency included. A credit note and a record
with no comprobante stay out. ``RULE`` runs in order, so a receipt with several
gaps names the first. A receipt still being read is in neither tab until its
read ends: a failed read needs attention, a read still running does not yet,
and neither does a read the Business's read limit holds.

The year check lives here too. The reader often writes the wrong year, so an
issue date it read whose year is not the upload year waits for a person. The
review calendar offers the upload year on the same answer.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, NamedTuple

from argus.domain.business.fiscal_identity import identity_digits
from argus.domain.business.ledger import business_day

# The deletion contract imports this type while receipt contracts initialize.
ApprovalGroup = Literal["listo", "attention"]

# Why a receipt needs the owner, in the words the owner sees. The web keys its
# message on this; ``error_code`` stays the precise cause.
Attention = Literal[
    "unreadable",
    "ai_unavailable",
    "interrupted",
    "outcome_unknown",
    "no_purchase_found",
    "not_a_receipt",
    "several_purchases",
    "source_unavailable",
    "check_details",
    "duplicate",
    "read_budget_day",
    "read_budget_month",
    "read_deadline_passed",
    "other",
]

# The dossier contract imports these while the contracts initialize too.
BandejaGroupName = Literal[ApprovalGroup, "reading", "eliminados"]
ListoGap = Literal[
    "reading",
    "not_read",
    "duplicate",
    "credit_note",
    "missing_merchant",
    "missing_date",
    "missing_amount",
    "missing_currency",
    "sin_comprobante",
    "missing_rnc",
    "invalid_rnc",
    "missing_ncf",
    "invalid_ncf",
    "ecf_check_failed",
    "missing_itbis",
    "review_flag",
    "blocked",
    "unverified_sender",
]
BandejaReason = Literal[Attention, ListoGap]
ReadState = Literal["finished", "none", "unclear"]
# The one word the Bandeja list shows for a row.
BandejaLabel = Literal["reading", "cant_read", "needs_attention", "ready", "accepted"]

from argus.domain.business.contracts.facts import (  # noqa: E402
    BusinessFacts,
    FiscalFacts,
    Known,
    is_sin_comprobante,
)

if TYPE_CHECKING:
    from argus.domain.business.contracts.dossier import ReviewFlag


#: A read that ended with nothing to review: the list says it could not be read.
READ_FAILURES: frozenset[Attention] = frozenset(
    {
        "unreadable",
        "ai_unavailable",
        "interrupted",
        "outcome_unknown",
        "source_unavailable",
        "read_deadline_passed",
        "not_a_receipt",
    }
)
#: A read the Business's read limit holds. It waits like a read still running.
READ_HELD: frozenset[Attention] = frozenset({"read_budget_day", "read_budget_month"})


@dataclass(frozen=True)
class DraftStanding:
    """What the rule reads of one open draft. ``sender`` is the email standing,
    None for a receipt that did not come by email. ``upload_year`` is the
    year its first source arrived."""

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
    upload_year: int | None = None


def _fiscal(draft: DraftStanding) -> FiscalFacts:
    return draft.facts.fiscal or FiscalFacts()


def _blank(fact: object) -> bool:
    return not isinstance(fact, Known) or not str(fact.value).strip()


def _lacks(draft: DraftStanding, name: str) -> bool:
    return _blank(getattr(draft.facts, name))


def _flagged(draft: DraftStanding, code: str) -> bool:
    return any(flag.code == code for flag in draft.flags)


#: The review flags and the blocker another row of the rule already names, so
#: one problem is one gap.
_FLAGS_NAMED = frozenset({"rnc_check_digit", "ncf_malformed"})
_BLOCKERS_NAMED = frozenset({"possible_duplicate"})


def _other_flag(draft: DraftStanding) -> bool:
    return any(flag.code not in _FLAGS_NAMED for flag in draft.flags)


def _other_blocker(draft: DraftStanding) -> bool:
    return any(code not in _BLOCKERS_NAMED for code in draft.blockers)


def _no_number(draft: DraftStanding) -> bool:
    fiscal = _fiscal(draft)
    return _blank(fiscal.ecf) and _blank(fiscal.ncf)


def _invalid_rnc(draft: DraftStanding) -> bool:
    """A blank RNC is missing, not invalid: only a number can be wrong."""

    from argus.domain.business.review_flags import CHECK_DIGIT

    rnc = _fiscal(draft).rnc
    if _blank(rnc):
        return False
    digits = identity_digits(rnc.value)
    return len(digits or "") not in CHECK_DIGIT or _flagged(draft, "rnc_check_digit")


def upload_year(first_received_at: datetime | None) -> int | None:
    """The Business year in which a draft's first source arrived."""

    return business_day(first_received_at).year if first_received_at else None


def year_to_check(facts: BusinessFacts, upload_year: int | None) -> bool:
    """The reader wrote this issue date and its year is not the upload year. A
    date from the QR or from a person is never checked."""

    issued = facts.occurred_on
    return (
        upload_year is not None
        and isinstance(issued, Known)
        and issued.origin == "extracted"
        and issued.value.year != upload_year
    )


class Gap(NamedTuple):
    """One row of the rule. ``confirmable``: the record can be recorded as it
    is, so a person may accept over the gap by naming it. The rest refuse
    every accept: a fact the money record needs, a blocker with its own
    refusal, or a sender nobody verified."""

    reason: BandejaReason
    confirmable: bool
    found: Callable[[DraftStanding], bool]


RULE: tuple[Gap, ...] = (
    Gap("not_read", True, lambda draft: draft.read == "none"),
    Gap("check_details", True, lambda draft: draft.read == "unclear"),
    Gap(
        "several_purchases",
        True,
        lambda draft: draft.read_attention == "several_purchases",
    ),
    Gap(
        "no_purchase_found",
        False,
        lambda draft: draft.read_attention == "no_purchase_found",
    ),
    Gap(
        "duplicate",
        True,
        lambda draft: draft.repeated or "possible_duplicate" in draft.blockers,
    ),
    Gap("credit_note", True, lambda draft: draft.credit_note),
    Gap("missing_merchant", True, lambda draft: _lacks(draft, "counterparty")),
    Gap("missing_date", False, lambda draft: _lacks(draft, "occurred_on")),
    Gap(
        "check_details",
        True,
        lambda draft: year_to_check(draft.facts, draft.upload_year),
    ),
    Gap("missing_amount", False, lambda draft: _lacks(draft, "amount")),
    Gap("missing_currency", False, lambda draft: _lacks(draft, "currency")),
    Gap("sin_comprobante", True, lambda draft: is_sin_comprobante(draft.facts)),
    Gap("missing_rnc", True, lambda draft: _blank(_fiscal(draft).rnc)),
    Gap("invalid_rnc", True, _invalid_rnc),
    Gap("missing_ncf", True, _no_number),
    Gap("invalid_ncf", True, lambda draft: _flagged(draft, "ncf_malformed")),
    Gap("ecf_check_failed", True, lambda draft: draft.ecf_failed),
    Gap("missing_itbis", True, lambda draft: _blank(_fiscal(draft).itbis)),
    Gap("review_flag", True, _other_flag),
    Gap("blocked", False, _other_blocker),
    Gap(
        "unverified_sender",
        False,
        lambda draft: draft.sender not in (None, "authorized"),
    ),
)

#: The gaps a person may accept a record over. An accept names each one.
CONFIRMABLE: frozenset[BandejaReason] = frozenset(
    gap.reason for gap in RULE if gap.confirmable
)


def refusing(
    gaps: Iterable[BandejaReason], named: Collection[BandejaReason]
) -> tuple[BandejaReason, ...]:
    """The gaps that refuse an accept naming ``named``: each one no person may
    accept over, and each one the accept did not name."""

    return tuple(gap for gap in gaps if gap not in CONFIRMABLE or gap not in named)


def listo_reason(draft: DraftStanding) -> BandejaReason | None:
    """The first gap between this draft and Listos, or None when it is Listos."""

    return next((gap.reason for gap in RULE if gap.found(draft)), None)


def listo_gaps(draft: DraftStanding) -> tuple[BandejaReason, ...]:
    """Every gap between this draft and Listos, in the rule's order."""

    return tuple(gap.reason for gap in RULE if gap.found(draft))


def _row_reason(
    view: Mapping[str, Any], draft: DraftStanding | None
) -> BandejaReason | None:
    if view.get("read_pending") or view.get("attention") in READ_HELD:
        return "reading"
    if view.get("attention"):
        return view["attention"]
    if draft is None:
        return "not_read" if view["status"] in ("saved", "queued") else "check_details"
    return listo_reason(draft)


def draft_group(reason: BandejaReason | None) -> ApprovalGroup:
    """A finished draft is Listos exactly when it has no gap."""

    return "listo" if reason is None else "attention"


def bandeja_label(
    group: BandejaGroupName | None,
    reason: BandejaReason | None = None,
    *,
    accepted: bool = False,
) -> BandejaLabel | None:
    """The label of a row in ``group``. A row the Bandeja no longer lists has
    one only when it ended ``accepted``; a deleted row has none."""

    if group == "attention":
        return "cant_read" if reason in READ_FAILURES else "needs_attention"
    if group == "reading":
        return "reading"
    if group == "listo":
        return "ready"
    return "accepted" if group is None and accepted else None


def _row(
    group: BandejaGroupName | None,
    reason: BandejaReason | None = None,
    *,
    draft_id: object = None,
    version: int | None = None,
    accepted: bool = False,
) -> dict[str, Any]:
    """The one shape every Bandeja row carries as ``bandeja_group``."""

    return {
        "group": group,
        "reason": reason,
        "label": bandeja_label(group, reason, accepted=accepted),
        "draft_id": draft_id,
        "version": version,
    }


def group_of(
    view: Mapping[str, Any], draft: DraftStanding | None, *, accepting: bool = False
) -> dict[str, Any]:
    """The group of a receipt row. A closed receipt and the email itself have
    none. ``draft_id`` and ``version`` are what an approval of this row names.
    ``accepting``: the receipt's one draft is being approved now, so the row is
    ready and names nothing a second approval could take."""

    from argus.domain.business.receipt_activity import awaiting_owner, closed_as

    if view.get("deleted"):
        return _row("eliminados")
    if not awaiting_owner(view):
        return _row(None, accepted=closed_as(view, "confirmed"))
    if accepting:
        return _row("listo")
    reason = _row_reason(view, draft)
    return _row(
        "reading" if reason == "reading" else draft_group(reason),
        reason,
        draft_id=draft.draft_id if draft else None,
        version=draft.version if draft else None,
    )


def note_group(
    state: str, *, deleted: bool, draft_id: object, version: int
) -> dict[str, Any]:
    """The group of a typed note no receipt carries, by its draft's state. An
    open note waits for a person; one being approved is ready."""

    if deleted:
        return _row("eliminados")
    if state == "open":
        return _row("attention", "not_read", draft_id=draft_id, version=version)
    if state == "accepting":
        return _row("listo")
    return _row(None, accepted=state == "accepted")


def email_group(standing: str | None) -> dict[str, Any]:
    """The group of an email by its standing: being read, or it brought no
    receipt and needs a person. An email that is no row of its own has none.
    Why it brought nothing stays with the delivery's ``no_receipt_reason``."""

    if standing == "reading":
        return _row("reading", "reading")
    return _row("attention" if standing == "no_receipt" else None)
