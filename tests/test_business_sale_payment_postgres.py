"""On real Postgres, through the review service: a person picks the one way a
sale was paid, the server puts the whole total in that bucket of the 607
split, the dossier says the pick back, and the bucket follows the total."""

from __future__ import annotations

from decimal import Decimal
from typing import get_args
from uuid import uuid4

import pytest
from argus.domain.business.contracts.actions import CaptureNote, ReviewDraft
from argus.domain.business.contracts.dgii import SalePayment, SalePaymentForm
from argus.domain.business.contracts.facts import BusinessFactPatch

from tests import test_business_actions_postgres as business
from tests import test_business_dgii_postgres as fiscal

actions = business.actions
users = business.users
pytestmark = business.pytestmark
FORMS = get_args(SalePaymentForm)


@pytest.fixture(autouse=True)
def _typed_notes(typed_notes_on: None) -> None:
    """These flows start a draft by typing a note: typed notes on."""


def _known(**values: str) -> BusinessFactPatch:
    return BusinessFactPatch.model_validate(
        {name: {"state": "known", "value": value} for name, value in values.items()}
    )


def _review(service, context, draft, version: int, **write):  # noqa: ANN001, ANN003, ANN202
    result = service.review(
        context, draft, ReviewDraft(version=version, **write), str(uuid4())
    )
    assert result.outcome == "applied", result
    return result.version


def _note(service, context, kind: str, total: str) -> tuple:  # noqa: ANN001
    note = service.capture(context, CaptureNote(text="nota"), str(uuid4()))
    facts = _known(kind=kind, amount=total, currency="DOP")
    return note.draft_id, _review(service, context, note.draft_id, note.version, facts=facts)


def _buckets(dossier) -> dict[str, str]:  # noqa: ANN001
    return {name: paid for name in FORMS if (paid := getattr(dossier.dgii, name))}


def test_one_pick_holds_the_whole_total_and_follows_it(actions) -> None:  # noqa: ANN001
    service, context, _ = actions
    draft, version = _note(service, context, "income", "1180.00")
    before = service.dossier(context, draft)
    assert before.payment_split_editable is True
    assert before.sale_payment == SalePayment(form=None, options=FORMS)

    version = _review(service, context, draft, version, sale_payment_form="bank")
    picked = service.dossier(context, draft)
    assert picked.sale_payment.form == "bank"
    assert _buckets(picked) == {"bank": "1180.00"}

    version = _review(service, context, draft, version, sale_payment_form="card")
    assert _buckets(service.dossier(context, draft)) == {"card": "1180.00"}

    _review(service, context, draft, version, facts=_known(amount="1200.50"))
    followed = service.dossier(context, draft)
    assert followed.sale_payment.form == "card"
    assert _buckets(followed) == {"card": "1200.50"}

    view = followed.model_facing()
    assert "sale_payment" not in view
    assert all("sale_payment_form" not in item.get("text", "") for item in view["sources"])


def test_a_purchase_has_no_payment_form_and_refuses_one(actions) -> None:  # noqa: ANN001
    service, context, _ = actions
    draft, version = _note(service, context, "expense", "500.00")
    assert service.dossier(context, draft).sale_payment is None

    refused = service.review(
        context, draft, ReviewDraft(version=version, sale_payment_form="cash"), str(uuid4())
    )
    assert (refused.outcome, refused.code) == ("invalid_input", "fiscal_direction_unsupported")

    typed = _review(service, context, draft, version, document_type="venta")
    assert service.dossier(context, draft).sale_payment == SalePayment(form=None, options=FORMS)
    _review(service, context, draft, typed, document_type="recibo")
    assert service.dossier(context, draft).sale_payment is None


@pytest.mark.owner_acts
def test_the_owner_picks_the_form_of_an_approved_sale(actions) -> None:  # noqa: ANN001
    service, context, _ = actions
    account = fiscal.cash_account(service, context)
    draft = fiscal.reviewed(service, context, account, 4)
    assert draft[2] == "income"
    assert fiscal.approve(service, context, draft).outcome == "applied"
    approved = service.dossier(context, draft[0])
    assert (approved.review_state, approved.payment_split_editable) == ("accepted", True)

    _review(service, context, draft[0], approved.version, sale_payment_form="gift")

    picked = service.dossier(context, draft[0])
    assert picked.sale_payment.form == "gift"
    assert _buckets(picked) == {"gift": f"{Decimal(approved.facts.amount.value):.2f}"}
    assert picked.facts == approved.facts
