"""The readings every view shares: what is personal, what carries a fiscal
number, what the accountant answered; approval admits a personal receipt and
still refuses a partial share; the export's words for the marks."""

from __future__ import annotations

from uuid import uuid4

from argus.domain.business.actions.dossier import blockers
from argus.domain.business.contracts.facts import (
    BusinessFacts,
    FiscalFacts,
    Known,
    OwnerFunding,
    Unknown,
    WholeBusinessShare,
    fiscal_inclusion,
    fiscal_value,
    is_personal,
)
from argus.domain.business.export import _marks

SOURCE = uuid4()


def known(value, origin="owner_stated", verified=True):  # noqa: ANN001, ANN201
    return Known(value=value, origin=origin, verified=verified, source_ids=(SOURCE,))


def facts(**over) -> BusinessFacts:  # noqa: ANN003
    base = dict(
        kind=known("expense"),
        amount=known("850.00"),
        currency=known("DOP"),
        occurred_on=known("2026-10-09"),
        funding=known(OwnerFunding()),
        business_share=known(WholeBusinessShare(kind="all")),
    )
    base.update(over)
    return BusinessFacts.model_validate(
        {
            key: (value.model_dump() if hasattr(value, "model_dump") else value)
            for key, value in base.items()
        }
    )


def test_personal_is_the_owners_none_and_nothing_else():
    assert (
        is_personal(facts(business_share=known(WholeBusinessShare(kind="none")))) is True
    )
    # A none the model read, a default, or a member's edit is not the owner's mark.
    assert (
        is_personal(
            facts(
                business_share=known(
                    WholeBusinessShare(kind="none"), origin="extracted", verified=False
                )
            )
        )
        is False
    )
    assert (
        is_personal(
            facts(
                business_share=known(WholeBusinessShare(kind="none"), origin="member_set")
            )
        )
        is False
    )
    assert (
        is_personal(facts(business_share=known(WholeBusinessShare(kind="all")))) is False
    )
    assert is_personal(facts(business_share=Unknown())) is False


def test_fiscal_value_is_an_ncf_or_an_ecf_the_draft_knows_of_any_origin():
    assert fiscal_value(facts()) is None
    assert fiscal_value(facts(fiscal=FiscalFacts())) is None
    assert (
        fiscal_value(
            facts(
                fiscal=FiscalFacts(
                    ncf=known("B0100000001", origin="extracted", verified=False)
                )
            )
        )
        == "ncf"
    )
    assert (
        fiscal_value(
            facts(
                fiscal=FiscalFacts(
                    ecf=known("E310000000001", origin="qr_decoded", verified=False)
                )
            )
        )
        == "ecf"
    )
    assert (
        fiscal_value(facts(fiscal=FiscalFacts(ncf=known("B01"), ecf=known("E31"))))
        == "ecf"
    )


def test_the_606_answer_applies_only_to_a_personal_receipt_with_a_fiscal_number():
    answered = FiscalFacts(
        ncf=known("B0100000001"), include_606=known(True, origin="member_set")
    )
    assert (
        fiscal_inclusion(
            facts(business_share=known(WholeBusinessShare(kind="none")), fiscal=answered)
        )
        is True
    )
    assert (
        fiscal_inclusion(
            facts(
                business_share=known(WholeBusinessShare(kind="none")),
                fiscal=FiscalFacts(ncf=known("B01")),
            )
        )
        is None
    )
    # Not personal, or no fiscal number: the answer, if any, does not apply.
    assert fiscal_inclusion(facts(fiscal=answered)) is None
    assert (
        fiscal_inclusion(
            facts(
                business_share=known(WholeBusinessShare(kind="none")),
                fiscal=FiscalFacts(include_606=known(False, origin="member_set")),
            )
        )
        is None
    )


def test_approval_admits_a_personal_receipt_and_still_refuses_a_partial_share():
    assert [
        b.code
        for b in blockers(
            facts(business_share=known(WholeBusinessShare(kind="none"))), ()
        )
    ] == []
    assert [b.code for b in blockers(facts(), ())] == []
    partial = BusinessFacts.model_validate(
        {
            **facts().model_dump(),
            "business_share": {
                "state": "known",
                "value": {"kind": "partial", "amount": "100.00"},
                "origin": "owner_stated",
                "verified": True,
                "source_ids": [str(SOURCE)],
            },
        }
    )
    assert [b.code for b in blockers(partial, ())] == ["business_allocation_unsupported"]


def test_the_export_says_the_marks_in_its_own_words_and_never_drops_a_personal_row():
    def draft(f: BusinessFacts) -> dict:
        return {"resolution": {"business": {"facts": f.model_dump(mode="json")}}}

    assert _marks([]) == {"personal": "no", "fiscal_value": "", "include_606": ""}
    assert _marks([draft(facts())]) == {
        "personal": "no",
        "fiscal_value": "",
        "include_606": "",
    }
    personal = facts(
        business_share=known(WholeBusinessShare(kind="none")),
        fiscal=FiscalFacts(
            ncf=known("B01"), include_606=known(False, origin="member_set")
        ),
    )
    assert _marks([draft(personal)]) == {
        "personal": "yes",
        "fiscal_value": "ncf",
        "include_606": "no",
    }
    undecided = facts(
        business_share=known(WholeBusinessShare(kind="none")),
        fiscal=FiscalFacts(ecf=known("E31")),
    )
    assert _marks([draft(undecided)]) == {
        "personal": "yes",
        "fiscal_value": "ecf",
        "include_606": "",
    }
