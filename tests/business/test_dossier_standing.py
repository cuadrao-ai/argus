"""The dossier's Bandeja standing with no database: for one draft it carries
the group, reason and label the receipt list gives the row, and every gap the
rule finds. The rule stays in ``bandeja_group``; nothing here restates it."""

from __future__ import annotations

from dataclasses import replace

import pytest
from argus.domain.business.actions.dossier import bandeja_standing
from argus.domain.business.bandeja_group import (
    RULE,
    DraftStanding,
    group_of,
    listo_gaps,
)
from argus.domain.business.contracts.dossier import ReviewFlag
from argus.domain.business.contracts.facts import Unknown

from tests.business.test_bandeja_group import (
    LISTO,
    OPEN_VIEW,
    known,
    with_facts,
    with_fiscal,
)

#: One draft per reason of the rule, each with that reason as its first gap.
GAPS: dict[str, DraftStanding] = {
    "not_read": replace(LISTO, read="none"),
    "check_details": replace(LISTO, read="unclear"),
    "several_purchases": replace(LISTO, read_attention="several_purchases"),
    "no_purchase_found": replace(LISTO, read_attention="no_purchase_found"),
    "duplicate": replace(LISTO, repeated=True),
    "credit_note": replace(LISTO, credit_note=True),
    "missing_merchant": with_facts(counterparty=Unknown()),
    "missing_date": with_facts(occurred_on=Unknown()),
    "missing_amount": with_facts(amount=Unknown()),
    "missing_currency": with_facts(currency=Unknown()),
    "sin_comprobante": with_facts(receipt_state=known("no_receipt"), fiscal=None),
    "missing_rnc": with_fiscal(rnc=Unknown()),
    "invalid_rnc": with_fiscal(rnc=known("12345")),
    "missing_ncf": with_fiscal(ncf=Unknown()),
    "invalid_ncf": replace(
        LISTO, flags=(ReviewFlag(code="ncf_malformed", field="ncf", confirm=True),)
    ),
    "ecf_check_failed": replace(LISTO, ecf_failed=True),
    "missing_itbis": with_fiscal(itbis=Unknown()),
    "review_flag": replace(
        LISTO, flags=(ReviewFlag(code="itbis_high", field="itbis", confirm=False),)
    ),
    "blocked": replace(LISTO, blockers=("business_questions_unresolved",)),
    "unverified_sender": replace(LISTO, sender="new"),
}


def _open(draft: DraftStanding, **view: object):  # noqa: ANN202
    return bandeja_standing(
        "open", draft, **{"deleted": False, "reading": False, "attention": None, **view}
    )


def _listed(view: dict, draft: DraftStanding | None, **more: object) -> dict:
    row = group_of(view, draft, **more)
    return {name: row[name] for name in ("group", "reason", "label")}


def test_the_table_covers_every_reason_of_the_rule() -> None:
    assert set(GAPS) == {reason for reason, _ in RULE}


@pytest.mark.parametrize("reason", GAPS)
def test_an_open_draft_carries_the_reason_the_list_gives_it(reason: str) -> None:
    draft = GAPS[reason]

    group, gaps = _open(draft)

    assert group.model_dump() == _listed(OPEN_VIEW, draft)
    assert (group.group, group.reason, group.label) == (
        "attention",
        reason,
        "needs_attention",
    )
    assert gaps == listo_gaps(draft)
    assert gaps[0] == reason


def test_a_draft_with_several_gaps_names_them_all_in_the_rules_order() -> None:
    draft = replace(
        with_facts(
            counterparty=Unknown(),
            fiscal=LISTO.facts.fiscal.model_copy(
                update={"ncf": Unknown(), "itbis": Unknown()}
            ),
        ),
        sender="new",
    )

    group, gaps = _open(draft)

    assert group.reason == "missing_merchant"
    assert gaps == (
        "missing_merchant",
        "missing_ncf",
        "missing_itbis",
        "unverified_sender",
    )
    assert gaps == listo_gaps(draft)


def test_a_draft_with_no_gap_is_ready_and_names_none() -> None:
    group, gaps = _open(LISTO)

    assert group.model_dump() == _listed(OPEN_VIEW, LISTO)
    assert (group.group, group.reason, group.label) == ("listo", None, "ready")
    assert gaps == ()


def test_an_accepted_record_is_labeled_accepted_and_names_no_gap() -> None:
    group, gaps = bandeja_standing(
        "accepted", None, deleted=False, reading=False, attention=None
    )

    assert group.model_dump() == _listed({**OPEN_VIEW, "status": "confirmed"}, None)
    assert (group.group, group.reason, group.label) == (None, None, "accepted")
    assert gaps == ()


def test_an_accepted_record_with_purchases_left_unrecorded_stays_accepted() -> None:
    group, gaps = bandeja_standing(
        "accepted", None, deleted=False, reading=False, attention="several_purchases"
    )

    assert (group.group, group.reason, group.label) == (None, None, "accepted")
    assert gaps == ()


def test_a_draft_being_approved_is_ready() -> None:
    group, gaps = bandeja_standing(
        "accepting", None, deleted=False, reading=False, attention=None
    )

    assert group.model_dump() == _listed(OPEN_VIEW, None, accepting=True)
    assert (group.group, group.label) == ("listo", "ready")
    assert gaps == ()


def test_a_deleted_or_dismissed_draft_has_no_label() -> None:
    deleted, _ = bandeja_standing(
        "dismissed", None, deleted=True, reading=False, attention=None
    )
    dismissed, _ = bandeja_standing(
        "dismissed", None, deleted=False, reading=False, attention=None
    )

    assert (deleted.group, deleted.reason, deleted.label) == ("eliminados", None, None)
    assert (dismissed.group, dismissed.reason, dismissed.label) == (None, None, None)


def test_a_draft_whose_receipt_is_being_read_waits_and_names_no_gap() -> None:
    group, gaps = _open(GAPS["missing_ncf"], reading=True)

    assert group.model_dump() == _listed(
        {**OPEN_VIEW, "read_pending": True}, GAPS["missing_ncf"]
    )
    assert (group.group, group.reason, group.label) == ("reading", "reading", "reading")
    assert gaps == ()


def test_a_repeat_shows_first_and_stays_among_the_gaps() -> None:
    draft = replace(
        with_fiscal(ncf=Unknown()), read="unclear", blockers=("possible_duplicate",)
    )

    group, gaps = _open(draft, attention="duplicate")

    assert group.model_dump() == _listed({**OPEN_VIEW, "attention": "duplicate"}, draft)
    assert group.reason == "duplicate"
    assert gaps == ("check_details", "duplicate", "missing_ncf", "blocked")
