"""Over the actions service on Postgres: an expense approved with no saved 606
line shows and exports the one its facts state, the reads write nothing, and a
first fiscal edit keeps every built value."""

from __future__ import annotations

from datetime import date

import pytest
from argus.domain.business.fiscal_profile import set_profile
from argus.domain.recording.schemas import EditFinancialAccountRequest

from tests import test_business_actions_postgres as shared
from tests import test_business_declaration_after_approval_postgres as after_approval
from tests.test_business_dgii_postgres import cash_account, filer_change

users = shared.users
shared_actions = shared.actions
actions = after_approval.actions
pytestmark = [shared.pytestmark, pytest.mark.owner_acts]
DAY = date(2026, 9, 3)
STORED = (
    "select coalesce(jsonb_agg(to_jsonb(t) order by t.sort)::text,'') from ("
    "select 0 as sort,to_jsonb(e) as stored from public.financial_import_events e where e.id=%(draft)s"
    " union all select r.version,to_jsonb(r) from public.business_draft_revisions r"
    " where r.draft_id=%(draft)s) t"
)


def stored(service, draft_id) -> str:  # noqa: ANN001
    """The draft's row and every revision of it, as stored."""

    with service.authority.pool.connection() as db:
        return db.execute(STORED, {"draft": draft_id}).fetchone()[0]


def archived(service, context, account) -> None:  # noqa: ANN001
    """Archive a Business account the way its owner does."""

    accounts = service.imports.money.accounts
    current = accounts.get(user_id=context.owner_id, account_id=str(account), scope=context.scope)
    accounts.edit(
        user_id=context.owner_id,
        account_id=str(account),
        request=EditFinancialAccountRequest(expected_version=current.account.version, archived=True),
        scope=context.scope,
    )


def approved_with_no_line(service, context, ncf, overrides, account=None):  # noqa: ANN001, ANN201
    """An accepted purchase as the approvals before the 606 line left it: no
    declaration on the draft and none on any revision."""

    cash = after_approval.account_funding(account or cash_account(service, context))
    draft_id, version = after_approval.captured(service, context, ncf, cash)
    after_approval.approved(service, context, draft_id, version)
    with service.authority.pool.connection() as db, db.transaction():
        db.execute("set local session_replication_role=replica")
        [held] = db.execute(
            "update public.financial_import_events set resolution=jsonb_set(resolution,'{business}',"
            " ((resolution->'business') - 'dgii' - 'fiscal_overrides' - 'amount_derived') || %s::jsonb)"
            " where id=%s and owner_space_id=%s returning resolution->'business'->'dgii'",
            (overrides, draft_id, context.actor.space_id),
        ).fetchone()
        assert held is None
        seeded = db.execute(
            "update public.business_draft_revisions set before_dgii=null,after_dgii=null"
            " where draft_id=%s and space_id=%s",
            (draft_id, context.actor.space_id),
        )
        assert seeded.rowcount > 0
    return draft_id


@pytest.mark.parametrize(
    "overrides", ["{}", '{"fiscal_overrides": []}'], ids=["before overrides", "overrides recorded"]
)
def test_an_expense_approved_with_no_saved_line_reads_the_one_its_facts_state(actions, overrides):  # noqa: ANN001
    service, context, _ = actions
    set_profile(service.authority, context, filer_change(after_approval.FILER), "rnc")
    draft_id = approved_with_no_line(service, context, "B0100000051", overrides)
    before = stored(service, draft_id)
    assert '"after_dgii": null' in before

    view = service.dossier(context, draft_id)
    manifest, row = after_approval.row_606(service, context)

    assert stored(service, draft_id) == before
    assert view.review_state == "accepted"
    assert (view.dgii.id_type, view.dgii.itbis) == ("1", "180.00")
    assert (view.dgii.payment_method, view.dgii.paid_on) == ("01", DAY)
    assert (view.dgii.category, view.dgii.goods_amount, view.dgii.services_amount) == (None, None, None)
    linked = {name for name, link in view.inheritance.items() if link.inherited}
    assert {"id_type", "itbis", "paid_on", "goods_amount", "services_amount"} <= linked
    assert view.declaration_editable is True
    # The 606 holds the record for the answer nobody gave, not for a missing line.
    assert row is None
    assert {(item["code"], item["field"]) for item in manifest["issues"]} == {
        ("fiscal_fact_required", "category")
    }

    edited = after_approval.declared(service, context, draft_id, view.version, category="02")
    assert edited.outcome == "applied", edited
    saved = service.dossier(context, draft_id)
    kept = {"category", "services_amount"}
    assert saved.dgii.model_dump(exclude=kept) == view.dgii.model_dump(exclude=kept)
    assert (saved.dgii.category, saved.dgii.services_amount) == ("02", "1000.00")
    assert saved.history[-1].after_dgii.id_type == "1"
    manifest, row = after_approval.row_606(service, context)
    assert manifest["forms"]["606"]["status"] == "prepared_candidate", manifest["issues"]
    assert (row["id_type"], row["category"], row["payment_method"], row["itbis"]) == (
        "1", "02", "01", "180.00",
    )
    assert (row["services_amount"], row["paid_on"]) == ("1000.00", "20260903")


def test_archiving_the_paying_account_keeps_the_forma_de_pago_its_facts_state(actions):  # noqa: ANN001
    service, context, _ = actions
    set_profile(service.authority, context, filer_change(after_approval.FILER), "rnc")
    cash = cash_account(service, context)
    draft_id = approved_with_no_line(service, context, "B0100000052", "{}", cash)
    archived(service, context, cash)
    before = stored(service, draft_id)

    view = service.dossier(context, draft_id)
    manifest, row = after_approval.row_606(service, context)

    assert stored(service, draft_id) == before
    assert str(cash) not in {str(account.id) for account in service.record_context(context).accounts}
    assert (view.dgii.payment_method, view.dgii.paid_on) == ("01", DAY)
    assert view.inheritance["paid_on"].inherited
    assert {(item["code"], item["field"]) for item in manifest["issues"]} == {
        ("fiscal_fact_required", "category")
    }

    edited = after_approval.declared(service, context, draft_id, view.version, category="02")
    assert edited.outcome == "applied", edited
    assert service.dossier(context, draft_id).history[-1].after_dgii.payment_method == "01"
    manifest, row = after_approval.row_606(service, context)
    assert (row["payment_method"], row["paid_on"]) == ("01", "20260903"), manifest["issues"]


def test_an_open_expense_whose_paying_account_was_archived_shows_its_forma_de_pago(actions):  # noqa: ANN001
    service, context, _ = actions
    cash = cash_account(service, context)
    draft_id, _ = after_approval.captured(
        service, context, "B0100000053", after_approval.account_funding(cash)
    )
    archived(service, context, cash)

    view = service.dossier(context, draft_id)

    assert view.review_state == "open"
    assert view.dgii.payment_method == "01"
