"""History names the person's request, not incidental linked-field movement."""
import json
from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from argus.domain.business.actions import mutations
from argus.domain.business.amount_inheritance import written_from
from argus.domain.business.contracts.actions import ReviewCommand, ReviewDraft
from argus.domain.business.contracts.dgii import SalePaymentSplit
from argus.domain.business.contracts.dossier import BusinessDossier, web_action_text
from argus.domain.business.contracts.facts import BusinessResolution
from argus.domain.business.history_review import legacy_evidence, review_evidence
from argus.domain.business.purchase_review import declaration_from_facts

from tests.business.test_fiscal_links import DAY, suggested
from tests.business.test_review_no_change import review_command  # noqa: F401


def projected(tx, event):
    params = next(call.args[1] for call in tx.rows.call_args_list if "insert into public.business_draft_revisions" in call.args[0])
    saved = BusinessResolution.model_validate(tx.imports.put_event.call_args.args[0].resolution["business"])
    revision = dict(
        draft_id=event.id, version=params[2], actor={**params[3].obj, "shown_as": "name", "issuer_shown_as": "name"},
        before=params[4].obj, after=params[5].obj, source_ids=params[6], created_at=datetime.now(timezone.utc),
        before_dgii=params[8].obj if params[8] else None, after_dgii=params[9].obj if params[9] else None,
    )
    return BusinessDossier(
        draft_id=event.id, version=params[2], space_id=uuid4(), space_name="PRÁCTICA", accounts=(), capabilities={"read"},
        review_state="open", facts=saved.facts, sources=tuple(tx.evidence), questions=(), history=(revision,), blockers=(), approval_available=False,
    )


@pytest.mark.parametrize("payment_source", ["saved", "suggested"])
def test_category_save_preserves_the_payment_date_and_names_only_category(review_command, monkeypatch, payment_source):  # noqa: F811
    review, tx, event, resolution = review_command
    linked = suggested(payment_method="01")
    if payment_source == "suggested":
        resolution = resolution.model_copy(update={"dgii": None, "fiscal_overrides": None})
        event.resolution["business"] = resolution.model_dump(mode="json")
        original = mutations.dossier.review_sources
        monkeypatch.setattr(mutations.dossier, "review_sources", lambda *a, **kw: replace(original(*a, **kw), suggestions=linked.suggestions))
    linked = replace(linked, built=declaration_from_facts(resolution.facts, None))
    before_shown = written_from(resolution.facts, resolution.dgii, resolution.fiscal_overrides, None, linked)
    assert before_shown.paid_on == DAY
    result = review({"purchase": {"category": "09"}})
    assert result.outcome == "applied"
    saved = BusinessResolution.model_validate(tx.imports.put_event.call_args.args[0].resolution["business"])
    after_shown = written_from(saved.facts, saved.dgii, saved.fiscal_overrides, None, linked)
    assert after_shown.paid_on == before_shown.paid_on
    assert saved.dgii.paid_on == (DAY if payment_source == "saved" else None), "a saved date survives; a suggestion was never stored"
    view = projected(tx, event)
    assert view.history[0].reviewed_declaration_fields == ("category",)
    assert "reviewed_declaration_fields" not in view.model_facing()["history"][0]


@pytest.mark.parametrize("full_editor", [False, True])
def test_restoring_tax_names_only_the_requested_link(review_command, full_editor):  # noqa: F811
    review, tx, event, resolution = review_command
    held = resolution.dgii.model_copy(update={"itbis": "150.00"})
    event.resolution["business"] = resolution.model_copy(update={"dgii": held, "fiscal_overrides": ("itbis",)}).model_dump(mode="json")
    body = {"montos": {"restore_inherited": ["itbis"]}}
    if full_editor:
        body["dgii"] = {"fiscal": {"rnc": resolution.facts.fiscal.rnc.value, "ncf": resolution.facts.fiscal.ncf.value, "itbis": "180.00"}, "declaration": held.model_dump(mode="json")}
    result = review(body)
    assert result.outcome == "applied"
    view = projected(tx, event)
    assert view.history[0].after_dgii.itbis == "180.00"
    assert view.history[0].reviewed_declaration_fields == ("itbis",)


def test_missing_or_unrelated_evidence_keeps_legacy_history(review_command):  # noqa: F811
    review, tx, event, _ = review_command
    review({"purchase": {"category": "09"}})
    tx.evidence.clear()
    assert projected(tx, event).history[0].reviewed_declaration_fields is None


@pytest.mark.parametrize("saved_choices", [False, True])
def test_type_round_trips_consistently_drop_saved_declaration_answers(review_command, saved_choices):  # noqa: F811
    review, tx, event, resolution = review_command
    if not saved_choices:
        event.resolution["business"] = resolution.model_copy(update={"dgii": None, "fiscal_overrides": None}).model_dump(mode="json")
    current = event
    for document_type in ("venta", "recibo", "venta", "recibo"):
        result = review({"version": current.version, "document_type": document_type})
        assert result.outcome == "applied"
        current = tx.imports.put_event.call_args.args[0]
        tx.imports.event.return_value = current
        saved = BusinessResolution.model_validate(current.resolution["business"])
        assert saved.document_type == document_type
        assert saved.dgii is None or all(getattr(saved.dgii, name, None) is None for name in ("category", "payment_method"))


def test_subtotal_restore_through_review_keeps_the_calculated_history_value(review_command):  # noqa: F811
    review, tx, event, resolution = review_command
    data = resolution.model_dump(mode="json")
    data["facts"]["net_amount"]["value"] = "900.00"
    event.resolution["business"] = data
    result = review({"montos": {"net_amount": {"state": "unknown"}}})
    assert result.outcome == "applied"
    entry = projected(tx, event).history[0]
    assert entry.after.net_amount.state == "unknown"
    assert entry.before_net_amount.amount == "900"
    assert entry.after_net_amount.amount == "1000.00"


def test_clearing_saved_purchase_answers_names_each_cleared_field(review_command):  # noqa: F811
    review, tx, event, resolution = review_command
    assert (resolution.dgii.category, resolution.dgii.payment_method) == ("02", "01")
    assert review({"purchase": {"category": None, "payment_method": None}}).outcome == "applied"
    view = projected(tx, event)
    assert view.history[0].reviewed_declaration_fields == ("category", "payment_method")
    [source] = view.model_facing()["sources"]
    assert json.loads(source["text"])["request"]["purchase"] == {"actual_refund": False, "category_suggested": False}, "models read the evidence as before"


def _older_evidence(tx):
    """The saved command as evidence held it before cleared answers were kept: every null dropped."""
    [source] = tx.evidence
    data = json.loads(source.text)
    data.pop("cleared_kept", None)
    data["request"]["purchase"] = {name: value for name, value in data["request"]["purchase"].items() if value is not None}
    tx.evidence[0] = source.model_copy(update={"text": web_action_text(data)})


@pytest.mark.parametrize(("purchase", "named"), [
    pytest.param({"category": None}, None, id="cleared-category"),
    pytest.param({"category": "09"}, None, id="services-amount-moved-to-null"),
    pytest.param({"payment_method": "02"}, ("payment_method",), id="nothing-unnamed-cleared"),
])
def test_older_evidence_falls_back_only_when_a_cleared_answer_may_be_lost(review_command, purchase, named):  # noqa: F811
    review, tx, event, _ = review_command
    assert review({"purchase": purchase}).outcome == "applied"
    _older_evidence(tx)
    assert projected(tx, event).history[0].reviewed_declaration_fields == named


def test_review_evidence_keeps_a_cleared_payment_bucket():
    request = ReviewDraft(version=2, payment_split=SalePaymentSplit(bank=None, card="1180.00"))
    evidence = review_evidence(ReviewCommand(draft_id=uuid4(), request=request))
    assert evidence["request"]["payment_split"] == {"bank": None, "card": "1180.00"}
    assert legacy_evidence(evidence)["request"]["payment_split"] == {"card": "1180.00"}
