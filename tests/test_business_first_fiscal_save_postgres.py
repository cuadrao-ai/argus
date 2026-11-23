"""On real local Postgres: the revision of a person's first fiscal save starts
from the declaration the review showed, so its history holds only what they
changed."""

import pytest
from argus.domain.business.contracts.dgii import PurchaseReview

from tests import test_business_approval_fiscal_postgres as fiscal
from tests import test_business_fiscal_links_postgres as links

users = fiscal.users
shared_actions = fiscal.shared_actions
actions = fiscal.actions
pytestmark = fiscal.pytestmark


def _changed(revision) -> set[str]:  # noqa: ANN001
    """The declaration fields a revision's before and after disagree on."""

    before, after = (
        value.model_dump(mode="json", exclude={"suggestion_sources"}) if value else {}
        for value in (revision.before_dgii, revision.after_dgii)
    )
    return {name for name in before.keys() | after.keys() if before.get(name) != after.get(name)}


def _last_revision(service, context, draft):  # noqa: ANN001, ANN202
    return service.dossier(context, draft).history[-1]


@pytest.mark.parametrize(
    ("answer", "changed"),
    [
        ({"payment_method": "04"}, {"payment_method"}),
        # The amount moves to the side its Tipo de gasto names.
        ({"category": "02"}, {"category", "services_amount"}),
    ],
)
def test_a_first_fiscal_save_starts_from_the_declaration_the_review_showed(  # noqa: ANN001
    actions, answer, changed
):
    service, context = actions
    draft, shown = links._fresh(service, context)

    links._review(service, context, draft, purchase=PurchaseReview(**answer))

    first = _last_revision(service, context, draft)
    assert first.before_dgii == shown.dgii
    assert _changed(first) == changed


def test_a_later_fiscal_save_starts_from_the_stored_declaration(actions):  # noqa: ANN001
    service, context = actions
    draft, _ = links._fresh(service, context)
    links._review(service, context, draft, purchase=PurchaseReview(category="02"))
    stored = fiscal.revisions(service, draft)[-1]["dgii"]

    links._review(service, context, draft, purchase=PurchaseReview(payment_method="04"))

    later = _last_revision(service, context, draft)
    assert later.before_dgii.model_dump(mode="json") == stored
    assert _changed(later) == {"payment_method"}


def test_a_save_that_writes_no_declaration_records_none_before(actions):  # noqa: ANN001
    service, context = actions
    draft, version = links._receipt(service, context, 2)

    fiscal.reviewed(service, context, draft, version)

    saved = _last_revision(service, context, draft)
    assert (saved.before_dgii, saved.after_dgii) == (None, None)

