from decimal import Decimal
from uuid import uuid4

import pytest
from argus.domain.business.contracts.actions import ReviewDraft
from argus.domain.business.contracts.dgii import FiscalInput, FiscalReview, PurchaseReview
from argus.domain.business.contracts.facts import BusinessFactPatch, MontosReview
from argus.domain.business.purchase_review import apply_purchase

from tests import test_business_actions_postgres as shared
from tests.test_financial_accounts_postgres import DSN

actions = shared.actions
users = shared.users
create = shared.create

pytestmark = pytest.mark.skipif(not DSN, reason="Disposable database required")


def test_amount_edits_and_split_restore_survive_reloading(actions):
    service, context, _ = actions
    draft, version = create(service, context)

    def review(**changes):
        current = service.dossier(context, draft)
        result = service.review(context, draft, ReviewDraft(version=current.version, **changes), str(uuid4()))
        assert result.outcome == "applied", result
        return service.dossier(context, draft)

    initial = review(
        facts=BusinessFactPatch(amount={"state": "known", "value": "184.90"}, kind={"state": "known", "value": "expense"}),
        dgii=FiscalReview(
            fiscal=FiscalInput(rnc="199990021", ncf="B0100000001", itbis="14.48"),
            declaration=apply_purchase(None, PurchaseReview(category="09")),
        ),
    )
    assert initial.net_amount.amount == "170.42"
    assert initial.net_amount.source == "calculated"
    assert initial.dgii.goods_amount == "170.42"
    assert initial.inheritance["goods_amount"].inherited
    split = review(purchase=PurchaseReview(goods_amount="100", services_amount="70.42"))
    assert not split.inheritance["goods_amount"].inherited
    assert not split.inheritance["services_amount"].inherited
    changed = review(montos=MontosReview(net_amount={"state": "known", "value": "160"}))
    assert changed.net_amount.source == "edited"
    assert changed.dgii.goods_amount == "100"
    assert next(flag for flag in changed.review_flags if flag.code == "amounts_mismatch").difference == "10.42"
    restored = review(montos=MontosReview(restore_inherited=("goods_amount",)))
    assert restored.dgii.goods_amount == "160.00"
    assert restored.dgii.services_amount is None
    assert restored.inheritance["goods_amount"].inherited
    assert Decimal(restored.facts.amount.value) == Decimal("184.90")
    model = restored.model_facing()
    assert "net_amount" not in model and "inheritance" not in model
    assert "net_amount" not in model["facts"] and "legal_tip" not in model["facts"]
    assert "itbis" not in model["dgii"]
    assert all("itbis" not in (row["after_dgii"] or {}) for row in model["history"])


def test_service_charge_read_is_saved_with_subtotal_without_changing_gross(actions, monkeypatch):
    from tests import test_business_attachment_preparation_postgres as bridge
    from tests import test_business_single_candidate_postgres as reader

    monkeypatch.setitem(reader.RECEIPT, "subtotal", "1289.46")
    monkeypatch.setitem(reader.RECEIPT, "service", "100.00")
    monkeypatch.setitem(reader.RECEIPT, "tip", "25.00")
    saved = reader._saved(actions, "expense")
    bridge.bind(saved)
    result = bridge.finish(saved)
    service, context, *_ = saved
    view = service.dossier(context, result.draft_id)
    assert view.net_amount.source == "read"
    assert view.net_amount.amount == "1289.46"
    assert Decimal(view.facts.legal_tip.value) == Decimal("100")
    assert Decimal(view.facts.amount.value) == Decimal("33254.91")
