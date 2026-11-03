"""The recorded subset uses live authority and one real local database snapshot."""

from dataclasses import replace
from uuid import uuid4

import pytest
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.actions import ApproveExpense, MarkPersonal
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.reporting import summarize
from argus.domain.business.reporting_store import read_recorded

from tests import test_business_actions_postgres as shared
from tests import test_business_export_postgres as export_tests
from tests.test_business_dgii_postgres import approve, cash_account, reviewed
from tests.test_business_spaces_migration_postgres import owned_space

users = shared.users
actions = shared.actions
attachment = export_tests.attachment
pytestmark = [shared.pytestmark, pytest.mark.owner_acts]


def report(snapshot):
    return summarize(
        snapshot.identity("recorded-subset-test"),
        snapshot.rows,
        page_number=1,
        page_size=25,
        observed_at=snapshot.observed_at,
    )


def record_expense(service, context, *, owner_funds=False):
    draft = shared.ready(service, context, owner_funds=owner_funds)
    outcome = service.approve(
        context, draft, ApproveExpense(version=1, action="record_expense"), str(uuid4())
    )
    assert outcome.outcome == "applied", outcome
    return draft, str(outcome.activity_id)


def viewer_context(service, context, person):
    with service.authority.pool.connection() as db:
        grant = db.execute(
            "insert into public.business_client_grants"
            " (space_id,grantee_id,issuer_id,business_role,capabilities)"
            " values (%s,%s,%s,'viewer',array['read']) returning id",
            (context.actor.space_id, person, context.owner_id),
        ).fetchone()[0]
    return service.resolve_actor(
        TrustedActor(
            actor_id=person, actor_kind="member", space_id=context.actor.space_id
        ),
        grant_id=grant,
    )


def test_selected_business_and_exact_grant_bound_the_recorded_subset(actions, users):
    service, context, _ = actions
    _, here = record_expense(service, context)
    with service.authority.pool.connection() as db:
        other_space = owned_space(db, users["other"])
    other = service.resolve_actor(
        TrustedActor(actor_id=users["other"], actor_kind="member", space_id=other_space)
    )
    _, there = record_expense(service, other)
    viewer = viewer_context(service, context, users["other"])
    first = read_recorded(service.authority, viewer)
    second = read_recorded(service.authority, other)
    assert [row.activity_id for row in first.rows] == [here]
    assert [row.activity_id for row in second.rows] == [there]
    assert first.identity("query").grant_id == str(viewer.grant_id)
    with pytest.raises(ActionError, match="business_record_not_found"):
        read_recorded(service.authority, replace(viewer, grant_id=other.grant_id))
    with pytest.raises(ActionError, match="business_permission_denied"):
        read_recorded(service.authority, viewer, capability="export")
    assert read_recorded(service.authority, context, capability="export").rows


@pytest.mark.parametrize("state", ["revoked", "expired", "closed", "wrong-owner"])
def test_previously_resolved_context_does_not_keep_access(actions, users, state):
    service, context, _ = actions
    record_expense(service, context)
    selected = viewer_context(service, context, users["other"])
    grant = selected.grant_id
    with service.authority.pool.connection() as db:
        if state == "revoked":
            db.execute(
                "update public.business_client_grants set revoked_at=clock_timestamp() where id=%s",
                (grant,),
            )
        elif state == "expired":
            db.execute(
                "update public.business_client_grants set created_at=clock_timestamp()-interval '2 days', expires_at=clock_timestamp()-interval '1 day' where id=%s",
                (grant,),
            )
        elif state == "closed":
            db.execute(
                "update public.spaces set closed_at=clock_timestamp() where id=%s",
                (context.actor.space_id,),
            )
    stale = (
        replace(selected, owner_id=str(uuid4())) if state == "wrong-owner" else selected
    )
    with pytest.raises(ActionError):
        read_recorded(service.authority, stale)


def test_approved_revision_survives_later_marks_that_move_the_record(actions):
    service, context, _ = actions
    draft, activity_id = record_expense(service, context)
    before = read_recorded(service.authority, context)
    dossier = service.dossier(context, draft)
    changed = service.mark_personal(
        context, draft, MarkPersonal(version=dossier.version, personal=True), str(uuid4())
    )
    assert changed.outcome == "applied", changed
    after = read_recorded(service.authority, context)
    [record] = after.records
    assert record.row.activity_id == activity_id
    assert record.approved.approved_revision == 1
    assert record.approved.facts.business_share.value.kind == "all"
    assert service.dossier(context, draft).facts.business_share.value.kind == "none"
    assert record.sources
    assert all(source.linked for source in record.sources)
    # The approved facts stay as approved; the mark beside them is the draft's
    # current one, so the recorded subset changes and a stale export is refused.
    assert record.approved.personal is True
    assert report(before).fingerprint != report(after).fingerprint


def test_actual_refund_and_owner_funded_record_are_not_dropped_or_duplicated(actions):
    service, context, _ = actions
    account = cash_account(service, context)
    purchase = approve(service, context, reviewed(service, context, account, 0))
    assert purchase.outcome == "applied", purchase
    refund = approve(
        service, context, reviewed(service, context, account, 3, purchase.activity_id)
    )
    assert refund.outcome == "applied", refund
    _, funded = record_expense(service, context, owner_funds=True)
    snapshot = read_recorded(service.authority, context)
    by_id = {record.row.activity_id: record for record in snapshot.records}
    assert set(by_id) == {str(purchase.activity_id), str(refund.activity_id), funded}
    assert by_id[str(refund.activity_id)].row.kind == "refund"
    assert (
        by_id[str(refund.activity_id)].approved.declaration.purchase_activity_id
        == purchase.activity_id
    )
    assert by_id[funded].approved.no_account is True
    assert report(snapshot).matching_count == 3
    assert read_recorded(service.authority, context).rows == snapshot.rows


def test_a_record_with_no_draft_names_only_its_stated_funding(actions):
    from argus.domain.business.reporting_query import ReportRequest
    from argus.domain.business.reporting_store import read_report

    from tests.financial_accounts.test_owner_funds import entered, reviewed, unstated

    service, context, _ = actions
    money, owner, scope = service.imports.money, context.owner_id, context.scope
    written = {
        key: money.write(
            user_id=owner,
            scope=scope,
            request=reviewed(money, owner, scope, request),
            idempotency_key=str(uuid4()),
        )["activity"]["activity_id"]
        for key, request in (("owner_funds", entered(scope)), (None, unstated(scope)))
    }
    result = read_report(service.authority, context, ReportRequest())
    keys = {row.linked_activity_ids[0]: row.funding_key for row in result.items}
    assert keys == {activity: key for key, activity in written.items()}


def test_settlement_annotation_changes_fingerprint_without_new_money(actions):
    service, context, _ = actions
    _, activity = record_expense(service, context)
    before = read_recorded(service.authority, context)
    with service.authority.pool.connection() as db:
        db.execute(
            "insert into public.business_document_settlements"
            " (space_id,owner_id,activity_id,document_kind,status,settled_on,payment_method)"
            " values (%s,%s,%s,'receipt','pagado','2026-10-01','efectivo')",
            (context.actor.space_id, context.owner_id, activity),
        )
    after = read_recorded(service.authority, context)
    assert before.records[0].settlement is None
    assert after.records[0].settlement.status == "pagado"
    assert report(before).matching_count == report(after).matching_count == 1
    assert report(before).totals == report(after).totals
    assert report(before).fingerprint != report(after).fingerprint


def test_concurrent_settlement_is_visible_only_in_next_snapshot(actions, monkeypatch):
    from argus.domain.business import reporting_store

    service, context, _ = actions
    _, activity = record_expense(service, context)
    original = reporting_store.fiscal_snapshot

    def change_after_snapshot(cursor, live, activities):
        result = original(cursor, live, activities)
        with service.authority.pool.connection() as db:
            db.execute(
                "insert into public.business_document_settlements"
                " (space_id,owner_id,activity_id,document_kind,status,settled_on,payment_method)"
                " values (%s,%s,%s,'receipt','pagado','2026-10-01','efectivo')",
                (context.actor.space_id, context.owner_id, activity),
            )
        return result

    monkeypatch.setattr(reporting_store, "fiscal_snapshot", change_after_snapshot)
    first = read_recorded(service.authority, context)
    monkeypatch.setattr(reporting_store, "fiscal_snapshot", original)
    second = read_recorded(service.authority, context)
    assert first.records[0].settlement is None
    assert second.records[0].settlement.status == "pagado"
    assert report(first).fingerprint != report(second).fingerprint


def test_disconnected_source_changes_dependencies_without_dropping_money(
    actions, attachment, monkeypatch
):
    service, context, _ = actions
    _objects, source_id, _content = attachment
    monkeypatch.setattr(shared, "source", lambda *_args: source_id)
    _, activity = record_expense(service, context)
    from argus.domain.business.reporting_query import ReportRequest
    from argus.domain.business.reporting_store import read_report

    before_report = read_report(service.authority, context, ReportRequest())
    assert before_report.items[0].date_basis == "document_issue"
    first = read_recorded(service.authority, context)
    source = next(
        item for item in first.records[0].sources if item.source_id == str(source_id)
    )
    assert source.sha256
    assert source.filename
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.financial_source_connections set status='disconnected', disconnected_at=clock_timestamp() where id=%s",
            (source.connection_id,),
        )
    second = read_recorded(service.authority, context)
    current = next(
        item for item in second.records[0].sources if item.source_id == str(source_id)
    )
    after_report = read_report(service.authority, context, ReportRequest())
    assert after_report.items[0].date_basis == "document_issue"
    assert after_report.items[0].report_date == before_report.items[0].report_date
    assert after_report.items[0].has_document is False
    assert current.connection_status == "disconnected"
    assert current.filename is current.sha256 is None
    assert [row.activity_id for row in second.rows] == [activity]
    assert report(first).totals == report(second).totals
    assert report(first).fingerprint != report(second).fingerprint


def test_grant_expiring_during_read_cannot_release_records(actions, users, monkeypatch):
    from argus.domain.business import reporting_store

    service, context, _ = actions
    record_expense(service, context)
    viewer = viewer_context(service, context, users["other"])
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.business_client_grants set expires_at=clock_timestamp()+interval '1 second' where id=%s",
            (viewer.grant_id,),
        )
    original = reporting_store.fiscal_snapshot

    def expires_before_release(cursor, live, activities):
        result = original(cursor, live, activities)
        cursor.execute("select pg_sleep(1.1)")
        return result

    monkeypatch.setattr(reporting_store, "fiscal_snapshot", expires_before_release)
    with pytest.raises(ActionError, match="business_record_not_found"):
        read_recorded(service.authority, viewer)


def test_a_recorded_draft_is_one_row_for_owner_and_viewer_and_an_open_one_is_none(
    actions, users
):
    from argus.domain.business.reporting_query import ReportRequest
    from argus.domain.business.reporting_store import read_report

    service, context, _ = actions
    draft, activity = record_expense(service, context)
    shared.ready(service, context)
    viewer = viewer_context(service, context, users["other"])
    owner_result = read_report(service.authority, context, ReportRequest())
    viewer_result = read_report(service.authority, viewer, ReportRequest())
    assert owner_result.matching_count == 1
    [row] = owner_result.items
    assert (row.row_id, row.draft_id, row.linked_activity_ids) == (
        f"draft:{draft}",
        str(draft),
        (activity,),
    )
    assert [(r.row_id, r.stage) for r in owner_result.items] == [
        (r.row_id, r.stage) for r in viewer_result.items
    ]


def test_open_and_accepting_drafts_are_not_rows_and_count_in_no_card(actions):
    from argus.domain.business.reporting_query import ReportOverview, ReportRequest
    from argus.domain.business.reporting_store import read_report

    service, context, _ = actions
    shared.ready(service, context)
    accepting = shared.ready(service, context)
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.financial_import_events set state='accepting' where id=%s",
            (accepting,),
        )
    answer = read_report(service.authority, context, ReportRequest())
    assert answer.items == ()
    assert answer.matching_count == 0
    assert answer.overview == ReportOverview()
    assert answer.totals == ()


def test_recorded_correction_uses_current_blockers_but_approved_amount(actions):
    from argus.domain.business.reporting_query import ReportRequest
    from argus.domain.business.reporting_store import read_report

    service, context, _ = actions
    draft, _ = record_expense(service, context)
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.financial_import_events set resolution=jsonb_set(resolution,'{business,facts,amount}',%s::jsonb) where id=%s",
            ('{"state":"unknown"}', draft),
        )
    [row] = read_report(service.authority, context, ReportRequest()).items
    assert row.stage == "needs_review"
    assert row.recorded_amount is not None
    assert row.gross_amount is not None


def test_unknown_credit_keeps_positive_money_and_incomplete_document_effect(actions):
    from argus.domain.business.reporting_query import ReportRequest
    from argus.domain.business.reporting_store import read_report

    service, context, _ = actions
    # A credit note recorded with no purchase it returns.
    unlinked = approve(
        service, context, reviewed(service, context, cash_account(service, context), 3)
    )
    assert unlinked.outcome == "applied", unlinked
    [row] = read_report(service.authority, context, ReportRequest()).items
    assert row.document_kind == "credit_note"
    assert row.family is None
    assert row.adjustment_effect == "unknown"
    assert row.gross_amount is not None
    assert row.stage != "ready_for_export"


def test_validated_purchase_credit_and_refund_are_one_row_and_separate_components(
    actions,
):
    from argus.domain.business.reporting_query import ReportRequest
    from argus.domain.business.reporting_store import read_report

    service, context, _ = actions
    account = cash_account(service, context)
    purchase = approve(service, context, reviewed(service, context, account, 0))
    refund = approve(
        service, context, reviewed(service, context, account, 3, purchase.activity_id)
    )
    assert refund.outcome == "applied"
    result = read_report(service.authority, context, ReportRequest())
    assert result.matching_count == 2
    credit = next(row for row in result.items if row.document_kind == "credit_note")
    assert credit.family == "purchase"
    assert credit.adjustment_effect == "known"
    assert credit.linked_activity_ids == (str(refund.activity_id),)
    totals = {(total.basis, total.kind): total for total in result.totals}
    assert totals["recorded_activity_amount", "refund"].amount_minor > 0
    assert totals["document_credit_adjustment", "expense"].amount_minor < 0


def test_signature_failure_is_retained_as_unknown_not_ready(actions, monkeypatch):
    from argus.domain.business.actions import dossier
    from argus.domain.business.reporting_query import ReportRequest
    from argus.domain.business.reporting_store import read_report

    service, context, _ = actions
    record_expense(service, context)

    def unavailable(*args, **kwargs):
        raise ActionError("invalid_input", "duplicate_evidence_unavailable")

    monkeypatch.setattr(dossier, "workflow_blockers", unavailable)
    result = read_report(service.authority, context, ReportRequest())
    [row] = result.items
    assert row.technical_state == "duplicate_evidence_unavailable"
    assert row.stage is None
    assert row.money_effect == "unknown"
    assert (
        next(
            total for total in result.totals if total.basis == "recorded_activity_amount"
        ).amount_minor
        is None
    )


def test_sale_issuer_identity_is_never_a_customer_key(actions):
    from argus.domain.business.reporting_query import ReportRequest
    from argus.domain.business.reporting_store import read_report

    from tests.test_business_dgii_postgres import INPUTS

    service, context, _ = actions
    account = cash_account(service, context)
    sale = approve(service, context, reviewed(service, context, account, 4))
    assert sale.outcome == "applied", sale
    issuer = INPUTS[4]["input"]["fiscal"]["rnc"]
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.spaces set business_rnc=%s where id=%s",
            (issuer, context.actor.space_id),
        )
    answer = read_report(service.authority, context, ReportRequest())
    [row] = answer.items
    assert row.family == "sale"
    assert row.counterparty_key is None
    assert answer.counterparties == ()
    assert (
        read_report(
            service.authority,
            context,
            ReportRequest(filters={"counterparties": [issuer]}),
        ).matching_count
        == 0
    )


def test_standalone_manual_expense_uses_activity_date_and_purchase_family(actions):
    from datetime import datetime, timezone

    from argus.domain.business.reporting_query import ReportRequest
    from argus.domain.business.reporting_store import read_report
    from argus.domain.recording.money_schemas import MoneyRequest

    service, context, _ = actions
    account = cash_account(service, context)
    service.imports.money.write_entered(
        user_id=context.owner_id,
        request=MoneyRequest(
            kind="expense",
            account_id=account,
            amount="25.00",
            occurred_at=datetime(2026, 10, 7, 12, tzinfo=timezone.utc),
        ),
        idempotency_key=str(uuid4()),
        scope=context.scope,
    )
    [row] = read_report(
        service.authority,
        context,
        ReportRequest(filters={"record_families": ["purchase"]}),
    ).items
    assert row.row_id.startswith("activity:")
    assert row.draft_id is None
    assert row.report_date.isoformat() == "2026-10-07"
    assert row.date_basis == "activity_effective"


def test_document_issue_and_gross_survive_different_current_money_date_and_amount(
    actions, attachment, monkeypatch
):
    from datetime import datetime, timezone

    from argus.domain.business.reporting_query import ReportRequest
    from argus.domain.business.reporting_store import read_report
    from argus.domain.recording.money_schemas import MoneyRequest

    service, context, _ = actions
    _, source_id, _ = attachment
    monkeypatch.setattr(shared, "source", lambda *_args, **_kwargs: source_id)
    _, activity_id = record_expense(service, context)
    original = read_recorded(service.authority, context).records[0]
    import json

    activity = json.loads(original.activity_json)
    command = MoneyRequest(
        kind="expense",
        account_id=activity["legs"][0]["account_id"],
        amount="25.00",
        occurred_at=datetime(2026, 10, 15, 12, tzinfo=timezone.utc),
        expected_revision=activity["revision"],
        reason="Synthetic reporting regression",
    )
    preview = service.imports.money.preview(
        user_id=context.owner_id,
        request=command,
        scope=context.scope,
        activity_id=activity_id,
    )
    command = command.model_copy(
        update={
            "expected_versions": preview["expected_versions"],
            "preview_token": preview["preview_token"],
        }
    )
    service.imports.money.write(
        user_id=context.owner_id,
        request=command,
        idempotency_key=str(uuid4()),
        scope=context.scope,
        activity_id=activity_id,
    )
    answer = read_report(
        service.authority,
        context,
        ReportRequest(
            filters={
                "currencies": ["DOP"],
                "amount_min": "850.00",
                "amount_max": "850.00",
            }
        ),
    )
    [row] = answer.items
    assert row.report_date.isoformat() == "2026-10-01"
    assert row.date_basis == "document_issue"
    assert row.gross_amount == "850"
    assert row.recorded_amount == "25.00"
    assert (
        next(
            total for total in answer.totals if total.basis == "recorded_activity_amount"
        ).amount
        == "25.00"
    )


def record_personal_expense(service, context):
    draft = shared.ready(service, context)
    version = service.dossier(context, draft).version
    marked = service.mark_personal(
        context, draft, MarkPersonal(version=version, personal=True), str(uuid4())
    )
    assert marked.outcome == "applied", marked
    outcome = service.approve(
        context,
        draft,
        ApproveExpense(version=version + 1, action="record_expense"),
        str(uuid4()),
    )
    assert outcome.outcome == "applied", outcome
    return draft, str(outcome.activity_id)


def test_a_recorded_expense_without_an_ncf_needs_fiscal_data(actions):
    from argus.domain.business.reporting_query import ReportRequest
    from argus.domain.business.reporting_store import read_report

    service, context, _ = actions
    record_expense(service, context)
    result = read_report(service.authority, context, ReportRequest())
    [row] = result.items
    assert (row.stage, row.export_missing, row.export_line) == (
        "needs_fiscal_data",
        "ncf_missing",
        False,
    )
    assert (result.overview.ready_for_export, result.overview.export_lines) == (0, 0)
    assert (result.overview.needs_fiscal_data, result.overview.exported) == (1, 0)


def test_each_card_counts_its_stage_and_its_filter_matches_it(actions):
    from argus.domain.business.export import export_package
    from argus.domain.business.fiscal_profile import set_profile
    from argus.domain.business.reporting_query import ReportRequest
    from argus.domain.business.reporting_store import read_report
    from argus.domain.business.spaces import PostgresSpaceStore
    from argus.domain.ingestion.documents.objects import InMemorySourceObjects

    from tests.test_business_declaration_after_approval_postgres import (
        FILER,
        PERIOD,
        account_funding,
        approved,
        captured,
        declared,
    )
    from tests.test_business_dgii_postgres import PRACTICE_NAME, filer_change

    service, context, _ = actions
    PostgresSpaceStore(service.authority.pool).rename(context.owner_id, PRACTICE_NAME)
    set_profile(service.authority, context, filer_change(FILER), "rnc")
    complete, version = captured(
        service, context, "B0100000031", account_funding(cash_account(service, context))
    )
    view = approved(service, context, complete, version)
    assert declared(service, context, complete, view.version, category="02").outcome == (
        "applied"
    )
    missing_ncf, _ = record_expense(service, context, owner_funds=True)
    shared.ready(service, context)

    def cards():
        overview = read_report(service.authority, context, ReportRequest()).overview
        return (
            overview.needs_fiscal_data,
            overview.ready_for_export,
            overview.exported,
        )

    def matching(stage):
        answer = read_report(
            service.authority,
            context,
            ReportRequest(filters={"review_stages": [stage]}),
        )
        assert all(row.stage == stage for row in answer.items), stage
        return [row.draft_id for row in answer.items]

    assert cards() == (1, 1, 0)
    assert matching("needs_fiscal_data") == [str(missing_ncf)]
    assert matching("ready_for_export") == [str(complete)]
    assert matching("exported") == []

    export_package(service.authority, context, PERIOD, InMemorySourceObjects())
    assert cards() == (1, 0, 1)
    assert matching("ready_for_export") == []
    [exported] = read_report(
        service.authority,
        context,
        ReportRequest(filters={"review_stages": ["exported"]}),
    ).items
    assert (exported.draft_id, exported.stage, exported.export_line) == (
        str(complete),
        "exported",
        True,
    )


def test_purchase_rows_carry_their_606_answers_and_a_sale_carries_none(actions, users):
    from argus.domain.business.contracts.actions import ReviewDraft
    from argus.domain.business.contracts.dgii import PurchaseReview
    from argus.domain.business.reporting_query import (
        DgiiChoice,
        Purchase606,
        ReportRequest,
    )
    from argus.domain.business.reporting_store import read_report

    from tests.test_business_declaration_after_approval_postgres import (
        account_funding,
        approved,
        captured,
    )

    service, context, _ = actions
    account = cash_account(service, context)
    # A fiscal receipt paid from the cash account: approval fills the forma
    # de pago from the account; nobody chose a tipo de gasto.
    cash_paid, version = captured(
        service, context, "B0100000021", account_funding(account)
    )
    approved(service, context, cash_paid, version)
    owner_paid, _ = record_expense(service, context, owner_funds=True)
    personal, _ = record_personal_expense(service, context)
    sale = approve(service, context, reviewed(service, context, account, 4))
    assert sale.outcome == "applied", sale

    rows = {
        row.draft_id: row
        for row in read_report(service.authority, context, ReportRequest()).items
    }
    cash = DgiiChoice(code="01", label="Efectivo")
    assert rows[str(cash_paid)].dgii_606 == Purchase606(
        expense_type=None, payment_form=cash
    )
    assert rows[str(owner_paid)].dgii_606 == Purchase606(
        expense_type=None, payment_form=None
    )
    assert rows[str(personal)].dgii_606 is None
    assert rows[str(sale.draft_id)].dgii_606 is None

    # A tipo de gasto chosen on the recorded record shows in the next read.
    later = service.review(
        context,
        cash_paid,
        ReviewDraft(
            version=service.dossier(context, cash_paid).version,
            purchase=PurchaseReview(category="02"),
        ),
        str(uuid4()),
    )
    assert later.outcome == "applied", later
    answer = read_report(
        service.authority, context, ReportRequest(filters={"expense_types": ["02"]})
    )
    [edited] = answer.items
    assert edited.draft_id == str(cash_paid)
    assert edited.dgii_606 == Purchase606(
        expense_type=DgiiChoice(
            code="02", label="Gastos por trabajos, suministros y servicios"
        ),
        payment_form=cash,
    )
    assert answer.expense_types == (
        DgiiChoice(code="02", label="Gastos por trabajos, suministros y servicios"),
    )
    missing = read_report(
        service.authority,
        context,
        ReportRequest(filters={"expense_types": ["missing"]}),
    )
    assert {row.draft_id for row in missing.items} == {str(owner_paid)}


def test_each_offered_document_kind_filter_matches_a_record_of_that_kind(actions):
    from argus.domain.business.reporting_query import ReportRequest
    from argus.domain.business.reporting_store import read_report

    service, context, _ = actions
    plain, _ = record_expense(service, context)
    account = cash_account(service, context)
    purchase = approve(service, context, reviewed(service, context, account, 0))
    refund = approve(
        service, context, reviewed(service, context, account, 3, purchase.activity_id)
    )
    assert refund.outcome == "applied", refund
    credit = refund.draft_id
    rows = read_report(service.authority, context, ReportRequest()).items
    # The projection names only these two kinds; Registros offers exactly them.
    assert {row.document_kind for row in rows} == {"credit_note", "unknown"}
    for kind, drafts in (
        ("credit_note", {str(credit)}),
        ("unknown", {str(plain), str(purchase.draft_id)}),
    ):
        answer = read_report(
            service.authority,
            context,
            ReportRequest(filters={"document_kinds": [kind]}),
        )
        assert {row.draft_id for row in answer.items} == drafts, kind
