"""Real persistence proof for unchanged reviews and historical edit intent."""
from uuid import uuid4

from argus.domain.business.contracts.actions import ReviewDraft
from argus.domain.business.contracts.dgii import PurchaseReview
from argus.domain.business.contracts.facts import BusinessFactPatch
from psycopg.types.json import Jsonb

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


def test_confirming_a_read_personal_share_keeps_the_receipt_out_of_the_606_on_postgres(actions):
    service, context = actions
    draft, shown = links._fresh(service, context, 3)
    read = {"state": "known", "value": {"kind": "none"}, "origin": "extracted", "verified": False, "source_ids": [str(shown.facts.amount.source_ids[0])]}
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.financial_import_events set resolution=jsonb_set(resolution,'{business,facts,business_share}',%s) where id=%s",
            (Jsonb(read), draft),
        )
    held = service.dossier(context, draft)
    assert held.facts.business_share.origin == "extracted" and not held.personal
    request = ReviewDraft(version=held.version, facts=BusinessFactPatch(business_share={"state": "known", "value": {"kind": "none"}}))
    result = service.review(context, draft, request, str(uuid4()))
    assert (result.outcome, result.version) == ("applied", held.version + 1)
    assert service.dossier(context, draft).personal
    assert fiscal.approve(service, context, draft, result.version).outcome == "applied"
    lines, _ = fiscal.lines_606(service, context)
    assert not any(shown.facts.fiscal.ncf.value in line for line in lines)
