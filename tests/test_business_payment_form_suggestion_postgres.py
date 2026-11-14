"""On real local Postgres: the Forma de pago a person last chose for an RNC
comes back as a suggestion with its source."""

from uuid import uuid4

import pytest
from argus.domain.business.contracts.actions import ReopenDraft, ReviewDraft
from argus.domain.business.contracts.dgii import PurchaseReview

from tests import test_business_approval_fiscal_postgres as fiscal

users = fiscal.users
shared_actions = fiscal.shared_actions
actions = fiscal.actions
pytestmark = fiscal.pytestmark
LAST_CHOICE = "last_choice"


def _receipt(service, context, number: int, **read) -> tuple:  # noqa: ANN001, ANN003
    """An unreviewed receipt of the same supplier, under its own comprobante."""

    return fiscal.receipt_draft(
        service, context, fiscal.colmado(ncf=f"B01000002{number:02d}", **read), "DOP"
    )


def _choose(service, context, draft, **purchase) -> int:  # noqa: ANN001, ANN003
    """A person writes these 606 answers on the draft."""

    version = service.dossier(context, draft).version
    result = service.review(
        context,
        draft,
        ReviewDraft(version=version, purchase=PurchaseReview(**purchase)),
        str(uuid4()),
    )
    assert result.outcome == "applied", result
    return result.version


def _approved(service, context, draft, version, account=None) -> None:  # noqa: ANN001
    funding = (
        {"kind": "business_account", "account_id": str(account)} if account else None
    )
    reviewed = fiscal.reviewed(service, context, draft, version, funding=funding)
    outcome = fiscal.approve(service, context, draft, reviewed)
    assert outcome.outcome == "applied", outcome


def _suggested(service, context, number: int, **read) -> dict | None:  # noqa: ANN001, ANN003
    """The Forma de pago a fresh receipt is offered."""

    draft, _ = _receipt(service, context, number, **read)
    offered = service.dossier(context, draft).declaration_suggestions.payment_method
    return offered.model_dump() if offered else None


def test_the_form_a_person_chose_for_an_rnc_comes_back_with_its_source(actions):
    service, context = actions
    assert _suggested(service, context, 1) is None
    draft, version = _receipt(service, context, 2)
    _choose(service, context, draft, payment_method="03")

    assert _suggested(service, context, 3) == {"value": "03", "source": LAST_CHOICE}
    assert _suggested(service, context, 4, rnc=fiscal.EDITED_SUPPLIER) is None


def test_a_draft_with_its_own_form_is_offered_none(actions):
    service, context = actions
    earlier, _ = _receipt(service, context, 1)
    _choose(service, context, earlier, payment_method="03")
    draft, _ = _receipt(service, context, 2)
    _choose(service, context, draft, payment_method="01")

    dossier = service.dossier(context, draft)

    assert dossier.dgii.payment_method == "01"
    assert dossier.declaration_suggestions.payment_method is None


def test_the_last_form_chosen_wins(actions):
    service, context = actions
    first, _ = _receipt(service, context, 1)
    second, _ = _receipt(service, context, 2)
    _choose(service, context, first, payment_method="03")
    _choose(service, context, second, payment_method="04")
    assert _suggested(service, context, 3)["value"] == "04"

    _choose(service, context, first, paid_on="2026-09-10")
    assert _suggested(service, context, 4)["value"] == "04"
    _choose(service, context, first, payment_method="05")
    assert _suggested(service, context, 5)["value"] == "05"


def test_a_form_chosen_before_the_approval_is_a_choice(actions):
    service, context = actions
    checking = fiscal.dop_account(service, context, "checking")
    draft, _ = _receipt(service, context, 1)
    version = _choose(service, context, draft, payment_method="03")

    _approved(service, context, draft, version, checking)

    assert service.dossier(context, draft).dgii.payment_method == "03"
    assert _suggested(service, context, 2) == {"value": "03", "source": LAST_CHOICE}


def test_a_form_changed_after_the_approval_is_a_choice(actions):
    service, context = actions
    checking = fiscal.dop_account(service, context, "checking")
    draft, version = _receipt(service, context, 1)
    _approved(service, context, draft, version, checking)

    _choose(service, context, draft, payment_method="04")

    assert _suggested(service, context, 2) == {"value": "04", "source": LAST_CHOICE}


def test_a_form_chosen_on_a_reopened_record_is_remembered(actions):
    service, context = actions
    draft, version = _receipt(service, context, 1)
    _approved(service, context, draft, version)
    current = service.dossier(context, draft).version
    reopened = service.reopen(
        context, draft, ReopenDraft(version=current), str(uuid4())
    )
    assert reopened.outcome == "applied", reopened
    assert _suggested(service, context, 2) is None

    _approved(
        service, context, draft, _choose(service, context, draft, payment_method="01")
    )

    assert _suggested(service, context, 3) == {"value": "01", "source": LAST_CHOICE}


@pytest.mark.parametrize("field", ["category", "payment_method"])
def test_both_fields_come_in_one_shape(actions, field):
    service, context = actions
    draft, _ = _receipt(service, context, 1)
    _choose(service, context, draft, category="02", payment_method="03")
    fresh, _ = _receipt(service, context, 2)

    offered = service.dossier(context, fresh).model_dump(mode="json")

    assert offered["declaration_suggestions"][field] == {
        "value": {"category": "02", "payment_method": "03"}[field],
        "source": LAST_CHOICE,
    }
