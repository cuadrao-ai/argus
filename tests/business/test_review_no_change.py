"""Human review commands that repeat saved answers write no revision (#2317)."""
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from argus.domain.business.actions import mutations, plans, sources
from argus.domain.business.actions import service as actions
from argus.domain.business.amount_inheritance import inherit_amounts
from argus.domain.business.contracts.actions import ReviewDraft
from argus.domain.business.contracts.dgii import PurchaseReview, SalesDeclaration
from argus.domain.business.contracts.facts import BusinessFacts, BusinessResolution
from argus.domain.business.purchase_review import apply_purchase
from faker import Faker

from tests.business.test_document_type_direction import _event, _tx
from tests.business.test_fiscal_links import read
from tests.business.test_venta import _actor

fake = Faker("es_MX")
fake.seed_instance(2317)


@pytest.fixture
def review_command(monkeypatch):
    """Real review -> revise -> save_revision; replace only storage and grants."""
    data = read().model_dump()
    data["counterparty"] = {**data["amount"], "value": fake.company()}
    data["currency"] = {**data["amount"], "value": "DOP"}
    data["net_amount"] = {**data["amount"], "value": "1000.00"}
    facts = BusinessFacts.model_validate(data)
    declaration = inherit_amounts(facts, apply_purchase(None, PurchaseReview(category="02", payment_method="01")), ())
    resolution = BusinessResolution(facts=facts, dgii=declaration, fiscal_overrides=(), amount_derived=True)
    event = _event("recibo", facts)
    event.resolution["business"] = resolution.model_dump(mode="json")
    tx = _tx()
    tx.rows.side_effect = lambda sql, *args: [{"business_rnc": None}] if sql.startswith("select business_rnc from public.spaces") else []
    tx.imports.event = Mock(return_value=event)
    actor = _actor().model_copy(update={"actor_kind": "member"})
    tx.context.actor.actor_id = actor.actor_id
    tx.context.actor.actor_kind = "member"
    tx.authorization = SimpleNamespace(require=Mock(), provenance=actor)
    tx.connection = SimpleNamespace(transaction=nullcontext)
    monkeypatch.setattr(actions, "transaction", lambda *args: nullcontext(tx))
    monkeypatch.setattr(plans, "receipt", lambda *args: None)
    monkeypatch.setattr(plans, "start_receipt", lambda *args: None)
    monkeypatch.setattr(plans, "finish_receipt", lambda tx, key, result: result)
    tx.evidence = []

    def record_source(tx, key, evidence):
        tx.evidence.append(evidence)
        return evidence.id

    monkeypatch.setattr(sources, "record_source", record_source)
    monkeypatch.setattr(sources, "require_sources", lambda *args: None)
    monkeypatch.setattr(sources, "attach", lambda *args: None)
    monkeypatch.setattr(mutations.dossier, "log_changed_suggestions", lambda *args: None)
    service = actions.BusinessActions(None, SimpleNamespace(money=SimpleNamespace(accounts=object())))

    def review(body):
        return service.review(tx.context, event.id, ReviewDraft.model_validate({"version": event.version, **body}), str(uuid4()))

    return review, tx, event, resolution


@pytest.mark.parametrize("field", ["counterparty", "amount", "currency", "occurred_on"])
def test_repeating_a_fact_through_the_review_command_writes_nothing(review_command, field):
    review, tx, event, resolution = review_command
    fact = getattr(resolution.facts, field)
    result = review({"facts": {field: {"state": fact.state, "value": fact.value}}})
    assert (result.outcome, result.version) == ("applied", event.version)
    tx.imports.put_event.assert_not_called()
    assert not any("insert into public.business_draft_revisions" in call.args[0] for call in tx.rows.call_args_list)


@pytest.mark.parametrize("kind", ["montos", "purchase", "fiscal"])
def test_repeating_other_saved_answers_writes_nothing(review_command, kind):
    review, tx, event, resolution = review_command
    body = {
        "montos": {"montos": {"net_amount": {"state": "known", "value": "1000.00"}}},
        "purchase": {"purchase": {"category": "02"}},
        "fiscal": {"dgii": {"fiscal": {"rnc": resolution.facts.fiscal.rnc.value, "ncf": resolution.facts.fiscal.ncf.value, "itbis": "180.00"}, "declaration": resolution.dgii.model_dump(mode="json")}},
    }[kind]
    result = review(body)
    assert (result.outcome, result.version) == ("applied", event.version)
    tx.imports.put_event.assert_not_called()


def test_typing_a_derived_amount_at_its_own_value_takes_it_from_its_source(review_command):
    review, tx, event, resolution = review_command
    side = next(name for name in ("services_amount", "goods_amount") if getattr(resolution.dgii, name) is not None)
    assert side not in resolution.fiscal_overrides
    result = review({"purchase": {side: getattr(resolution.dgii, side)}})
    assert (result.outcome, result.version) == ("applied", event.version + 1)
    saved = BusinessResolution.model_validate(tx.imports.put_event.call_args.args[0].resolution["business"])
    assert side in saved.fiscal_overrides


def test_a_real_change_keeps_the_other_facts_and_writes_one_revision(review_command):
    review, tx, event, resolution = review_command
    result = review({"facts": {"counterparty": {"state": "known", "value": fake.company()}}})
    assert (result.outcome, result.version) == ("applied", event.version + 1)
    saved = BusinessResolution.model_validate(tx.imports.put_event.call_args.args[0].resolution["business"])
    assert saved.facts.counterparty != resolution.facts.counterparty
    assert saved.facts.model_dump(exclude={"counterparty"}) == resolution.facts.model_dump(exclude={"counterparty"})
    assert sum("insert into public.business_draft_revisions" in call.args[0] for call in tx.rows.call_args_list) == 1


def test_a_stale_no_change_review_is_still_refused(review_command):
    review, tx, event, resolution = review_command
    result = review({"version": event.version - 1, "facts": {"counterparty": {"state": "known", "value": resolution.facts.counterparty.value}}})
    assert result.outcome == "stale_version"
    tx.imports.put_event.assert_not_called()


def test_no_change_still_requires_review_authority(review_command):
    from argus.domain.business.authority import ActionError

    review, tx, _, resolution = review_command
    tx.authorization.require.side_effect = ActionError("permission_denied", "business_human_command_required")
    result = review({"facts": {"counterparty": {"state": "known", "value": resolution.facts.counterparty.value}}})
    assert result.outcome == "permission_denied"
    tx.imports.put_event.assert_not_called()


@pytest.mark.parametrize("purchase", [{"category": "02"}, {"category": "02", "payment_method": "01"}])
def test_a_purchase_answer_on_a_saved_607_is_refused_not_compared(review_command, purchase):
    review, tx, event, resolution = review_command
    sale = {**dict.fromkeys(SalesDeclaration.model_fields), "form": "607", "cash": "1180.00"}
    facts = resolution.facts.model_copy(update={"kind": resolution.facts.kind.model_copy(update={"value": "income"})})
    event.resolution["business"] = {**resolution.model_dump(mode="json"), "document_type": "venta", "facts": facts.model_dump(mode="json"), "dgii": sale}
    result = review({"purchase": purchase})
    assert (result.outcome, result.code) == ("invalid_input", "fiscal_direction_unsupported")
    tx.imports.put_event.assert_not_called()
