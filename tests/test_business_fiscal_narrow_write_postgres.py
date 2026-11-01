"""On real local Postgres: a fiscal edit writes only the fact a person changed.

The review carries the RNC, the fiscal number and the ITBIS together, because a
fiscal write always holds all three. Only the one whose value differs from the
record becomes "del revisor". The other two keep their value, origin and sources.
"""

from uuid import uuid4

import pytest
from argus.domain.business.contracts.actions import ReviewDraft
from argus.domain.business.contracts.dgii import FiscalReview

from tests.test_business_approval_fiscal_postgres import (
    EDITED_SUPPLIER,
    NCF,
    SUPPLIER,
    actions,  # noqa: F401
    colmado,
    pytestmark,  # noqa: F401
    receipt_draft,
    saved_declaration,
    shared_actions,  # noqa: F401
    users,  # noqa: F401
)

READ = {"rnc": SUPPLIER, "ncf": NCF, "itbis": "180.00"}


def fiscal_edit(service, context, draft, version, **fiscal):
    """One fiscal write of the three values, and the record it leaves."""

    result = service.review(
        context,
        draft,
        ReviewDraft(
            version=version,
            dgii=FiscalReview.model_validate(
                {
                    "fiscal": {**READ, **fiscal},
                    "declaration": saved_declaration(
                        category="09", services_amount="0.00", goods_amount="1000.00"
                    ),
                }
            ),
        ),
        str(uuid4()),
    )
    assert result.outcome == "applied", result
    return service.dossier(context, draft).facts.fiscal


def read_e_cf(service, context, number):
    return receipt_draft(service, context, colmado(ncf=None, ecf=number), "DOP")


def facts_of(fiscal, *names):
    return {name: getattr(fiscal, name).model_dump(mode="json") for name in names}


@pytest.mark.parametrize(
    ("edited", "value", "kept"),
    [
        ("itbis", "150", ("rnc", "ncf", "ecf")),
        ("rnc", EDITED_SUPPLIER, ("ncf", "ecf", "itbis")),
        ("ncf", "B0100000002", ("rnc", "itbis")),
    ],
)
def test_one_edit_marks_only_its_own_fact_as_the_reviewers(
    actions,  # noqa: F811
    edited,
    value,
    kept,
):
    service, context = actions
    draft, version = receipt_draft(service, context, colmado(), "DOP")
    read = service.dossier(context, draft).facts.fiscal
    assert {read.rnc.origin, read.ncf.origin, read.itbis.origin} == {"extracted"}

    fiscal = fiscal_edit(service, context, draft, version, **{edited: value})

    changed = getattr(fiscal, edited)
    assert (changed.value, changed.origin) == (value, "member_set")
    assert facts_of(fiscal, *kept) == facts_of(read, *kept)


def test_an_edit_to_the_e_cf_leaves_the_rnc_and_itbis(actions):  # noqa: F811
    service, context = actions
    draft, version = receipt_draft(service, context, colmado(), "DOP")
    read = service.dossier(context, draft).facts.fiscal

    fiscal = fiscal_edit(service, context, draft, version, ncf="E310000000001")

    assert (fiscal.ecf.value, fiscal.ecf.origin) == ("E310000000001", "member_set")
    assert (fiscal.ncf.state, fiscal.ncf.origin) == ("unknown", "member_set")
    assert facts_of(fiscal, "rnc", "itbis") == facts_of(read, "rnc", "itbis")


def test_an_edit_to_the_itbis_leaves_a_read_e_cf(actions):  # noqa: F811
    service, context = actions
    number = "E310000000002"
    draft, version = read_e_cf(service, context, number)
    read = service.dossier(context, draft).facts.fiscal
    assert (read.ecf.value, read.ecf.origin) == (number, "extracted")

    fiscal = fiscal_edit(service, context, draft, version, ncf=number, itbis="150")

    assert fiscal.itbis.value == "150"
    assert facts_of(fiscal, "rnc", "ncf", "ecf") == facts_of(read, "rnc", "ncf", "ecf")


def test_the_same_value_keyed_another_way_is_not_an_edit(actions):  # noqa: F811
    service, context = actions
    draft, version = receipt_draft(service, context, colmado(), "DOP")
    read = service.dossier(context, draft).facts.fiscal

    fiscal = fiscal_edit(
        service,
        context,
        draft,
        version,
        rnc=f"{SUPPLIER[:3]}-{SUPPLIER[3:8]}-{SUPPLIER[8:]}",
        ncf=NCF.lower(),
        itbis="180",
    )

    names = ("rnc", "ncf", "ecf", "itbis")
    assert facts_of(fiscal, *names) == facts_of(read, *names)


def test_clearing_one_fact_leaves_the_other_two(actions):  # noqa: F811
    service, context = actions
    draft, version = receipt_draft(service, context, colmado(), "DOP")
    read = service.dossier(context, draft).facts.fiscal

    fiscal = fiscal_edit(service, context, draft, version, itbis=None)

    assert (fiscal.itbis.state, fiscal.itbis.origin) == ("unknown", "member_set")
    assert facts_of(fiscal, "rnc", "ncf") == facts_of(read, "rnc", "ncf")


def test_clearing_an_e_cf_leaves_no_fiscal_number(actions):  # noqa: F811
    service, context = actions
    draft, version = read_e_cf(service, context, "E310000000003")
    read = service.dossier(context, draft).facts.fiscal

    fiscal = fiscal_edit(service, context, draft, version, ncf=None)

    assert (fiscal.ecf.state, fiscal.ncf.state) == ("unknown", "unknown")
    assert facts_of(fiscal, "rnc", "itbis") == facts_of(read, "rnc", "itbis")


def test_a_write_with_no_fiscal_change_keeps_all_of_them(actions):  # noqa: F811
    service, context = actions
    draft, version = receipt_draft(service, context, colmado(), "DOP")
    read = service.dossier(context, draft).facts.fiscal

    fiscal = fiscal_edit(service, context, draft, version)

    names = ("rnc", "ncf", "ecf", "itbis")
    assert facts_of(fiscal, *names) == facts_of(read, *names)
    assert service.dossier(context, draft).dgii.category == "09"
