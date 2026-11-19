"""The Listos rule as a table, with no database: each gap has one reason, the
first gap names a receipt with several, and every row sits in one count."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from argus.domain.business.bandeja_group import (
    RULE,
    DraftStanding,
    group_of,
    listo_gaps,
    listo_reason,
    upload_year,
    year_to_check,
)
from argus.domain.business.contracts.dossier import ReviewFlag
from argus.domain.business.contracts.facts import (
    BusinessFacts,
    FiscalFacts,
    Known,
    Unknown,
    WholeBusinessShare,
)
from argus.domain.business.receipt_activity import inbox_counts

SOURCES = (uuid4(),)


def known(value: object) -> Known:
    return Known(value=value, origin="extracted", source_ids=SOURCES)


FACTS = BusinessFacts(
    kind=known("expense"),
    amount=known("1180"),
    currency=known("DOP"),
    occurred_on=known(date(2026, 10, 6)),
    counterparty=known("FERRETERIA PRUEBA"),
    fiscal=FiscalFacts(
        rnc=known("199990021"), ncf=known("B0100000011"), itbis=known("180")
    ),
)
LISTO = DraftStanding(
    draft_id=str(uuid4()),
    version=2,
    facts=FACTS,
    read="finished",
    read_attention=None,
    credit_note=False,
    ecf_failed=False,
    repeated=False,
    blockers=(),
    flags=(),
)
OPEN_VIEW = {"status": "review_ready", "attention": None, "read_pending": False}


def with_facts(**changes: object) -> DraftStanding:
    return replace(LISTO, facts=FACTS.model_copy(update=changes))


def with_fiscal(**changes: object) -> DraftStanding:
    return with_facts(fiscal=FACTS.fiscal.model_copy(update=changes))


def test_a_draft_with_nothing_missing_is_listo() -> None:
    assert listo_reason(LISTO) is None
    assert group_of(OPEN_VIEW, LISTO) == {
        "group": "listo",
        "reason": None,
        "draft_id": LISTO.draft_id,
        "version": 2,
    }


@pytest.mark.parametrize(
    ("draft", "reason"),
    [
        (replace(LISTO, read="none"), "not_read"),
        (replace(LISTO, read="unclear"), "check_details"),
        (replace(LISTO, read_attention="several_purchases"), "several_purchases"),
        (replace(LISTO, read_attention="no_purchase_found"), "no_purchase_found"),
        (replace(LISTO, repeated=True), "duplicate"),
        (replace(LISTO, blockers=("possible_duplicate",)), "duplicate"),
        (with_facts(kind=known("income")), "sale"),
        (replace(LISTO, credit_note=True), "credit_note"),
        (with_facts(counterparty=Unknown()), "missing_merchant"),
        (with_facts(occurred_on=Unknown()), "missing_date"),
        (with_facts(amount=Unknown()), "missing_amount"),
        (with_facts(currency=Unknown()), "missing_currency"),
        (with_facts(fiscal=None), "missing_rnc"),
        (with_fiscal(rnc=Unknown()), "missing_rnc"),
        (
            with_facts(receipt_state=known("no_receipt"), fiscal=None),
            "sin_comprobante",
        ),
        (
            with_facts(
                receipt_state=known("informal_receipt"),
                fiscal=FACTS.fiscal.model_copy(update={"ncf": Unknown()}),
            ),
            "sin_comprobante",
        ),
        (with_fiscal(rnc=known("12345")), "invalid_rnc"),
        (
            replace(
                LISTO,
                flags=(ReviewFlag(code="rnc_check_digit", field="rnc", confirm=True),),
            ),
            "invalid_rnc",
        ),
        (with_fiscal(ncf=Unknown()), "missing_ncf"),
        (
            replace(
                LISTO,
                flags=(ReviewFlag(code="ncf_malformed", field="ncf", confirm=True),),
            ),
            "invalid_ncf",
        ),
        (replace(LISTO, ecf_failed=True), "ecf_check_failed"),
        (with_fiscal(itbis=Unknown()), "missing_itbis"),
        (with_facts(currency=known("USD")), "foreign_currency"),
        (
            replace(
                LISTO,
                flags=(ReviewFlag(code="itbis_high", field="itbis", confirm=False),),
            ),
            "review_flag",
        ),
        (
            with_facts(
                business_share=Known(
                    value=WholeBusinessShare(kind="none"),
                    origin="owner_stated",
                    source_ids=SOURCES,
                )
            ),
            "personal",
        ),
        (replace(LISTO, blockers=("business_questions_unresolved",)), "blocked"),
        (replace(LISTO, sender="new"), "unverified_sender"),
    ],
)
def test_each_gap_has_its_reason(draft: DraftStanding, reason: str) -> None:
    assert listo_reason(draft) == reason
    found = group_of(OPEN_VIEW, draft)
    assert (found["group"], found["reason"]) == ("attention", reason)


@pytest.mark.parametrize(
    "draft",
    [with_facts(fiscal=None), with_fiscal(rnc=Unknown()), with_fiscal(rnc=known("  "))],
)
def test_a_blank_rnc_is_missing_and_never_also_invalid(draft: DraftStanding) -> None:
    gaps = listo_gaps(draft)
    assert "missing_rnc" in gaps and "invalid_rnc" not in gaps


def test_a_stated_no_comprobante_on_a_record_with_a_number_is_no_gap() -> None:
    assert listo_reason(with_facts(receipt_state=known("no_receipt"))) is None


def test_an_authorized_sender_is_no_gap() -> None:
    assert listo_reason(replace(LISTO, sender="authorized")) is None


def test_a_receipt_with_several_gaps_names_the_first_in_rule_order() -> None:
    draft = with_fiscal(ncf=Unknown(), itbis=Unknown())
    assert listo_reason(replace(draft, read="unclear")) == "check_details"
    assert listo_reason(draft) == "missing_ncf"
    order = [reason for reason, _ in RULE]
    assert order.index("missing_ncf") < order.index("missing_itbis")
    assert order[-1] == "unverified_sender"


@pytest.mark.parametrize(
    ("view", "reason"),
    [
        (
            {**OPEN_VIEW, "status": "needs_attention", "attention": "unreadable"},
            "unreadable",
        ),
        ({**OPEN_VIEW, "status": "saved"}, "not_read"),
        ({**OPEN_VIEW, "status": "queued"}, "not_read"),
        (OPEN_VIEW, "check_details"),
    ],
)
def test_a_row_with_no_open_draft_says_why(view: dict, reason: str) -> None:
    assert group_of(view, None) == {
        "group": "attention",
        "reason": reason,
        "draft_id": None,
        "version": None,
    }


def test_a_receipt_still_being_read_waits_in_its_own_group() -> None:
    view = {**OPEN_VIEW, "read_pending": True}
    assert group_of(view, None)["group"] == "reading"
    assert group_of(view, LISTO)["group"] == "reading"
    assert group_of(view, None)["reason"] == "reading"


@pytest.mark.parametrize(
    "view",
    [
        {**OPEN_VIEW, "status": "confirmed"},
        {**OPEN_VIEW, "status": "dismissed"},
        {**OPEN_VIEW, "email_original": True},
    ],
)
def test_a_closed_receipt_and_the_email_itself_have_no_group(view: dict) -> None:
    assert group_of(view, LISTO)["group"] is None


def test_every_row_the_bandeja_lists_is_in_one_count() -> None:
    reading = {**OPEN_VIEW, "read_pending": True}
    views = [
        {**OPEN_VIEW, "bandeja_group": group_of(OPEN_VIEW, LISTO)},
        {
            **OPEN_VIEW,
            "bandeja_group": group_of(OPEN_VIEW, with_fiscal(ncf=Unknown())),
        },
        {**reading, "bandeja_group": group_of(reading, None)},
        {**OPEN_VIEW, "status": "confirmed"},
    ]
    counts = inbox_counts(views, notes=2, emails=["reading", "no_receipt"])
    assert counts["bandeja_listo_count"] == 1
    assert counts["bandeja_attention_count"] == 4
    assert counts["pending_review_count"] == 7


UPLOADED = datetime(2026, 11, 5, 15, 0, tzinfo=timezone.utc)


def dated(day: date, origin: str = "extracted", at: datetime = UPLOADED) -> DraftStanding:
    """LISTO with this issue date, on a document that arrived at ``at``."""

    issued = Known(value=day, origin=origin, source_ids=SOURCES)
    return replace(with_facts(occurred_on=issued), upload_year=upload_year(at))


def test_a_read_year_that_is_not_the_upload_year_needs_a_person() -> None:
    draft = dated(date(2024, 11, 4))

    assert year_to_check(draft.facts, draft.upload_year)
    found = group_of(OPEN_VIEW, draft)
    assert (found["group"], found["reason"]) == ("attention", "check_details")


@pytest.mark.parametrize(
    "draft",
    [
        pytest.param(dated(date(2024, 11, 4), "qr_decoded"), id="the QR gave the date"),
        pytest.param(dated(date(2024, 11, 4), "member_set"), id="a member set the date"),
        pytest.param(dated(date(2024, 11, 4), "owner_stated"), id="the owner stated the date"),
        pytest.param(dated(date(2024, 11, 4), "matched"), id="a match gave the date"),
        pytest.param(dated(date(2026, 11, 4)), id="the read year is the upload year"),
        pytest.param(
            dated(date(2025, 12, 31), at=datetime(2026, 1, 1, 3, 30, tzinfo=timezone.utc)),
            id="23:30 on 31 dic in Santo Domingo is still the old year",
        ),
        pytest.param(replace(dated(date(2024, 11, 4)), upload_year=None), id="no source time"),
    ],
)
def test_a_date_is_not_year_checked(draft: DraftStanding) -> None:
    assert not year_to_check(draft.facts, draft.upload_year)
    assert listo_reason(draft) is None


def test_the_upload_year_turns_at_midnight_in_santo_domingo() -> None:
    assert upload_year(datetime(2027, 1, 1, 3, 59, tzinfo=timezone.utc)) == 2026
    assert upload_year(datetime(2027, 1, 1, 4, 30, tzinfo=timezone.utc)) == 2027
    assert upload_year(None) is None


def test_a_year_to_check_comes_after_a_missing_fact() -> None:
    draft = dated(date(2024, 11, 4))
    lacking = replace(draft, facts=draft.facts.model_copy(update={"counterparty": Unknown()}))

    assert listo_reason(lacking) == "missing_merchant"
    assert listo_gaps(lacking) == ("missing_merchant", "check_details")
