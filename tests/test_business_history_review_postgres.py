"""Real persistence proof for unchanged reviews and historical edit intent."""
from uuid import uuid4

from argus.domain.business.contracts.actions import ReviewDraft
from argus.domain.business.contracts.dgii import PurchaseReview
from argus.domain.business.contracts.facts import BusinessFactPatch

from tests import test_business_approval_fiscal_postgres as fiscal
from tests import test_business_fiscal_links_postgres as links

users = fiscal.users
shared_actions = fiscal.shared_actions
actions = fiscal.actions
pytestmark = fiscal.pytestmark


def test_an_unchanged_name_writes_no_revision_on_postgres(actions):
    service, context = actions
    draft, shown = links._fresh(service, context)
    request = ReviewDraft(version=shown.version, facts=BusinessFactPatch(counterparty={"state": "known", "value": shown.facts.counterparty.value}))
    key = str(uuid4())
    result = service.review(context, draft, request, key)
    assert (result.outcome, result.version) == ("applied", shown.version)
    assert service.review(context, draft, request, key) == result
    after = service.dossier(context, draft)
    assert after.version == shown.version
    assert after.history == shown.history
    assert after.facts == shown.facts


def test_a_saved_payment_date_survives_a_category_save_on_postgres(actions):
    service, context = actions
    draft, _ = links._fresh(service, context)
    links._review(service, context, draft, purchase=PurchaseReview(payment_method="01", category="02"))
    before = service.dossier(context, draft)
    stored_before = fiscal.revisions(service, draft)[-1]["dgii"]
    assert stored_before["paid_on"] is not None
    links._review(service, context, draft, purchase=PurchaseReview(category="09"))
    after = service.dossier(context, draft)
    stored_after = fiscal.revisions(service, draft)[-1]["dgii"]
    assert stored_after["paid_on"] == stored_before["paid_on"]
    assert after.dgii.paid_on == before.dgii.paid_on
    assert after.history[-1].reviewed_declaration_fields == ("category",)


def test_a_suggested_payment_date_is_not_a_persons_edit_on_postgres(actions):
    service, context = actions
    links._remembered(service, context, payment_method="01")
    draft, before = links._fresh(service, context)
    assert before.dgii.paid_on is not None
    links._review(service, context, draft, purchase=PurchaseReview(category="09"))
    after = service.dossier(context, draft)
    assert after.dgii.paid_on == before.dgii.paid_on
    assert after.history[-1].reviewed_declaration_fields == ("category",)


def test_clearing_saved_purchase_answers_is_named_in_history_on_postgres(actions):
    service, context = actions
    draft, _ = links._fresh(service, context)
    links._review(service, context, draft, purchase=PurchaseReview(payment_method="01", category="02"))
    links._review(service, context, draft, purchase=PurchaseReview(category=None, payment_method=None))
    after = service.dossier(context, draft)
    assert (after.dgii.category, after.dgii.payment_method) == (None, None)
    assert after.history[-1].reviewed_declaration_fields == ("category", "payment_method")
