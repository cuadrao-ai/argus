"""On real local Postgres: Aceptar saves the Forma de pago and Fecha de pago
the app filled in without crediting the person with them, and a person's later
change reads from the filled value."""

from datetime import timedelta
from uuid import uuid4

import pytest
from argus.domain.business.contracts.actions import ApproveExpense
from argus.domain.business.contracts.dgii import PurchaseReview

from tests import test_business_approval_fiscal_postgres as fiscal
from tests import test_business_fiscal_links_postgres as links
from tests.business_accept_support import seen_gaps

users = fiscal.users
shared_actions = fiscal.shared_actions
actions = fiscal.actions
pytestmark = fiscal.pytestmark
FILLED = "01"
CHOSEN = "04"


def _shown(service, context, *, typed_first: bool):  # noqa: ANN001, ANN202
    """A receipt whose Forma de pago the app suggests and whose Fecha de pago
    follows it. ``typed_first``: the person saved their Tipo de gasto first,
    so a declaration is stored with both answers still blank."""

    links._remembered(service, context, payment_method=FILLED)
    draft, shown = links._fresh(service, context)
    if typed_first:
        links._review(service, context, draft, purchase=PurchaseReview(category="09"))
        shown = service.dossier(context, draft)
    assert shown.dgii.payment_method is None
    assert shown.declaration_suggestions.payment_method.value == FILLED
    assert shown.dgii.paid_on is not None
    return draft, shown


def _accept(service, context, draft):  # noqa: ANN001, ANN202
    shown = service.dossier(context, draft)
    outcome = service.approve(
        context,
        draft,
        ApproveExpense(
            version=shown.version,
            action="record_expense",
            suggestions=shown.declaration_suggestions,
            accept_gaps=seen_gaps(service, context, draft),
        ),
        str(uuid4()),
    )
    assert outcome.outcome == "applied", outcome
    return service.dossier(context, draft)


def _persons_changes(revision) -> dict[str, tuple]:  # noqa: ANN001
    """The declaration changes the history credits to the revision's person."""

    assert revision.actor.actor_kind == "member" and not revision.approval
    return {
        name: (getattr(revision.before_dgii, name), getattr(revision.after_dgii, name))
        for name in revision.reviewed_declaration_fields
    }


@pytest.mark.parametrize("typed_first", [False, True], ids=["nothing saved", "tipo de gasto saved"])
def test_aceptar_credits_the_person_with_no_filled_answer(actions, typed_first):  # noqa: ANN001
    service, context = actions
    draft, shown = _shown(service, context, typed_first=typed_first)

    accepted = _accept(service, context, draft)

    added = accepted.history[len(shown.history):]
    assert added and all(revision.approval for revision in added)
    assert (accepted.dgii.payment_method, accepted.dgii.paid_on) == (FILLED, shown.dgii.paid_on)
    assert accepted.dgii.suggestion_sources == {"payment_method": "last_choice"}
    if typed_first:
        assert _persons_changes(accepted.history[-2]) == {"category": (None, "09")}


@pytest.mark.parametrize("accepted_first", [False, True], ids=["before Aceptar", "after Aceptar"])
@pytest.mark.parametrize("typed_first", [False, True], ids=["nothing saved", "tipo de gasto saved"])
def test_a_persons_change_reads_from_the_filled_forma_de_pago(actions, typed_first, accepted_first):  # noqa: ANN001
    service, context = actions
    draft, _ = _shown(service, context, typed_first=typed_first)
    if accepted_first:
        _accept(service, context, draft)

    links._review(service, context, draft, purchase=PurchaseReview(payment_method=CHOSEN))

    changed = service.dossier(context, draft)
    assert _persons_changes(changed.history[-1]) == {"payment_method": (FILLED, CHOSEN)}
    assert changed.dgii.suggestion_sources == {}


@pytest.mark.parametrize("accepted_first", [False, True], ids=["before Aceptar", "after Aceptar"])
@pytest.mark.parametrize("typed_first", [False, True], ids=["nothing saved", "tipo de gasto saved"])
def test_a_persons_change_reads_from_the_filled_fecha_de_pago(actions, typed_first, accepted_first):  # noqa: ANN001
    service, context = actions
    draft, shown = _shown(service, context, typed_first=typed_first)
    if accepted_first:
        _accept(service, context, draft)
    paid = shown.dgii.paid_on - timedelta(days=1)

    links._review(service, context, draft, purchase=PurchaseReview(paid_on=paid))

    changed = service.dossier(context, draft)
    assert _persons_changes(changed.history[-1]) == {"paid_on": (shown.dgii.paid_on, paid)}
