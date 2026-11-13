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


@pytest.mark.owner_acts
def test_payment_date_follows_settlement_in_dossier_and_fiscal_snapshot(actions):
    from datetime import date

    from argus.domain.business.contracts.actions import ApproveExpense
    from argus.domain.business.dgii_snapshot import fiscal_snapshot
    from argus.domain.business.month_close import Settlement
    from argus.domain.business.month_close_store import settle_document
    from psycopg.rows import dict_row

    from tests.test_business_dgii_postgres import business_account

    service, context, _ = actions
    draft, version = create(service, context)
    account = business_account(service, context)
    result = service.review(context, draft, ReviewDraft(
        version=version,
        facts=BusinessFactPatch.model_validate({
            name: {"state": "known", "value": value}
            for name, value in {
                "kind": "expense", "amount": "1180", "currency": "DOP",
                "occurred_on": "2026-11-01", "counterparty": "Prueba local",
                "funding": {"kind": "business_account", "account_id": str(account)},
                "business_share": {"kind": "all"}, "receipt_state": "fiscal_receipt",
            }.items()
        }),
        dgii=FiscalReview(fiscal=FiscalInput(rnc="199990021", ncf="B0100000088", itbis="180"), declaration=apply_purchase(None, PurchaseReview(category="09", payment_method="01", id_type="1"))),
    ), str(uuid4()))
    assert result.outcome == "applied"
    pending = service.dossier(context, draft)
    assert pending.dgii.paid_on is None
    assert pending.inheritance["paid_on"].value is None
    approved = service.approve(context, draft, ApproveExpense(version=result.version, action="record_expense", approve_anyway=True), str(uuid4()))
    assert approved.outcome == "applied", approved
    activity_id = service.dossier(context, draft).approval_result.activity_id
    settle_document(service.authority, context, str(activity_id), Settlement("pagado", date(2026, 11, 3), "efectivo"))
    paid = service.dossier(context, draft)
    assert paid.dgii.paid_on == date(2026, 11, 1)
    assert paid.inheritance["paid_on"].value == "2026-11-01"
    with service.authority.pool.connection() as db:
        activities = [service.imports.money.repository.get_activity(user_id=context.owner_id, activity_id=str(activity_id), scope=context.scope)]
        with db.cursor(row_factory=dict_row) as cursor:
            records, _, _ = fiscal_snapshot(cursor, context, activities)
    record = next(record for record in records if str(record.activity_id) == str(activity_id))
    assert record.declaration.paid_on == date(2026, 11, 1)
    settle_document(service.authority, context, str(activity_id), Settlement("pendiente", None, None))
    assert service.dossier(context, draft).dgii.paid_on is None


def test_amount_preview_is_read_only_and_uses_current_version(actions):
    from argus.domain.business.authority import ActionError
    from argus.domain.business.contracts.amounts import AmountsPreviewRequest

    service, context, _ = actions
    draft, version = create(service, context)
    result = service.review(context, draft, ReviewDraft(
        version=version,
        facts=BusinessFactPatch(amount={"state": "known", "value": "1180"}),
        montos=MontosReview(net_amount={"state": "known", "value": "1000"}),
        dgii=FiscalReview(fiscal=FiscalInput(rnc="199990021", ncf="B0100000044", itbis="180"), declaration=apply_purchase(None, PurchaseReview(category="09"))),
    ), str(uuid4()))
    assert result.outcome == "applied"
    before = service.dossier(context, draft)

    def counts():
        with service.authority.pool.connection() as connection:
            return tuple(connection.execute(f"select count(*) from public.{table} where space_id=%s", (context.actor.space_id,)).fetchone()[0] for table in ("business_action_receipts", "business_sources", "business_draft_revisions"))

    old_counts = counts()
    preview = service.preview_amounts(context, draft, AmountsPreviewRequest(version=before.version, amount={"state": "known", "value": "1200"}))
    assert preview.mismatch.difference == "20.00"
    assert service.dossier(context, draft).model_dump() == before.model_dump()
    assert counts() == old_counts
    with pytest.raises(ActionError) as stale:
        service.preview_amounts(context, draft, AmountsPreviewRequest(version=before.version - 1))
    assert stale.value.result.code == "stale_version"


def test_read_context_never_gives_a_model_the_human_only_amounts(actions):
    from argus.domain.business.contracts.facts import HUMAN_AMOUNT_FIELDS

    service, context, _ = actions
    draft, version = create(service, context)
    result = service.review(context, draft, ReviewDraft(
        version=version,
        facts=BusinessFactPatch(amount={"state": "known", "value": "1180"}),
        montos=MontosReview(net_amount={"state": "known", "value": "1000"}, legal_tip={"state": "known", "value": "80"}),
    ), str(uuid4()))
    assert result.outcome == "applied"
    saved = service.dossier(context, draft).facts
    assert saved.net_amount.state == saved.legal_tip.state == "known"
    row = next(row for row in service.read_context(context)["drafts"] if row["id"] == str(draft))
    assert Decimal(row["facts"]["amount"]["value"]) == Decimal("1180")
    assert not set(HUMAN_AMOUNT_FIELDS) & set(row["facts"])


def test_amount_preview_requires_prepare(actions):
    from argus.domain.business.authority import ActionError
    from argus.domain.business.contracts.amounts import AmountsPreviewRequest

    service, context, grant = actions
    draft, version = create(service, context)
    with service.authority.pool.connection() as connection:
        connection.execute("update public.business_client_grants set business_role='viewer' where id=%s", (grant,))
    with pytest.raises(ActionError) as denied:
        service.preview_amounts(context, draft, AmountsPreviewRequest(version=version))
    assert denied.value.result.outcome == "permission_denied"
