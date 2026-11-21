"""On real local Postgres: the preview of a Más datos fiscales draft shows the
links the dossier shows once that same draft is saved."""

from datetime import date

import pytest
from argus.domain.business.contracts.amounts import AmountsPreviewRequest
from argus.domain.business.contracts.dgii import FiscalInput, FiscalReview
from argus.domain.business.contracts.facts import MontosReview

from tests import test_business_fiscal_links_postgres as links
from tests.business.receipt_stub import receipt_date

users = links.users
shared_actions = links.shared_actions
actions = links.actions
pytestmark = links.pytestmark
PAID_LATER = date(2026, 9, 20)

#: Each draft is what a person typed over the shown declaration, the links
#: they held apart and the links they put back. A case saves each in turn.
DRAFTS = {
    "one side of the split typed": [({"goods_amount": "400.00"}, ("goods_amount",), ())],
    "fecha pago typed": [({"paid_on": PAID_LATER}, ("paid_on",), ())],
    "forma de pago on credit": [({"payment_method": "04"}, (), ())],
    "forma de pago paid at the purchase": [({"payment_method": "02"}, (), ())],
    "a saved split restored from one side": [
        ({"goods_amount": "400.00", "services_amount": "600.00"}, ("goods_amount", "services_amount"), ()),
        ({}, (), ("goods_amount",)),
    ],
    "both sides of a saved split restored": [
        ({"goods_amount": "400.00", "services_amount": "600.00"}, ("goods_amount", "services_amount"), ()),
        ({}, (), ("goods_amount", "services_amount")),
    ],
    "a saved split typed again after its restore": [
        ({"goods_amount": "400.00", "services_amount": "600.00"}, ("goods_amount", "services_amount"), ()),
        ({"goods_amount": "1000.00", "services_amount": "250.00"}, ("goods_amount", "services_amount"), ()),
    ],
    "a link put back that nobody held apart": [({}, (), ("paid_on",))],
    "one side restored beside the other typed": [
        ({"services_amount": "600.00"}, ("services_amount",), ("goods_amount",)),
    ],
    "a saved fecha pago restored beside a typed amount": [
        ({"paid_on": PAID_LATER}, ("paid_on",), ()),
        ({"itbis": "150.00"}, ("itbis",), ("paid_on",)),
    ],
}


def _draft(shown, typed: dict):  # noqa: ANN001, ANN202
    """What the form sends: the declaration the dossier showed with the typed values."""

    return type(shown.dgii).model_validate({**shown.dgii.model_dump(), **typed})


@pytest.mark.parametrize("drafts", DRAFTS.values(), ids=DRAFTS.keys())
def test_the_preview_shows_the_links_the_saved_draft_shows(actions, drafts):  # noqa: ANN001
    service, context = actions
    links._remembered(service, context, category="09", payment_method="01")
    draft, shown = links._fresh(service, context)
    assert shown.inheritance["goods_amount"].value is not None

    for typed, held, put_back in drafts:
        declaration = _draft(shown, typed)
        previewed = service.preview_amounts(
            context,
            draft,
            AmountsPreviewRequest(
                version=shown.version,
                declaration=declaration,
                override_inherited=held,
                restore_inherited=put_back,
            ),
        ).inheritance
        assert service.dossier(context, draft).version == shown.version

        fiscal = shown.facts.fiscal
        links._review(
            service,
            context,
            draft,
            dgii=FiscalReview(
                fiscal=FiscalInput(
                    rnc=fiscal.rnc.value, ncf=fiscal.ncf.value, itbis=fiscal.itbis.value
                ),
                declaration=declaration,
            ),
            **(
                {"montos": MontosReview(override_inherited=held, restore_inherited=put_back)}
                if held or put_back
                else {}
            ),
        )
        shown = service.dossier(context, draft)
        assert previewed == shown.inheritance


def test_the_previewed_links_are_the_owners_own(actions):  # noqa: ANN001
    service, context = actions
    links._remembered(service, context, category="09", payment_method="01")
    draft, shown = links._fresh(service, context)

    def preview(typed: dict, held: tuple = (), put_back: tuple = ()):  # noqa: ANN202
        return service.preview_amounts(
            context,
            draft,
            AmountsPreviewRequest(
                version=shown.version,
                declaration=_draft(shown, typed),
                override_inherited=held,
                restore_inherited=put_back,
            ),
        ).inheritance

    split = preview({"goods_amount": "400.00"}, ("goods_amount",))
    assert (split["goods_amount"].inherited, split["services_amount"].inherited) == (False, False)
    assert split["goods_amount"].value == shown.inheritance["goods_amount"].value

    back = preview({"services_amount": "600.00"}, ("services_amount",), ("goods_amount",))
    assert (back["goods_amount"].inherited, back["services_amount"].inherited) == (True, True)

    credit = preview({"payment_method": "04"})["paid_on"]
    assert (credit.value, credit.inherited) == (None, True)
    cash = preview({"payment_method": "02"})["paid_on"]
    assert (cash.value, cash.inherited) == (receipt_date(), True)
    held = preview({"payment_method": "04", "paid_on": PAID_LATER}, ("paid_on",))["paid_on"]
    assert (held.value, held.inherited) == (None, False)
