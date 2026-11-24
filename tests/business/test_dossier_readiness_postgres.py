from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from argus.api.business_drafts import expense_detail
from argus.api.business_schemas import ExpenseDetail
from argus.domain.business import reporting_store
from argus.domain.business.authority import ActionError
from argus.domain.business.missing_reasons import REASONS
from argus.domain.business.reporting_query import ReportRequest
from argus.domain.business.reporting_store import read_report
from argus.domain.recording.money_schemas import MoneyRequest
from faker import Faker

from tests import test_business_actions_postgres as shared
from tests.test_business_declaration_after_approval_postgres import (
    account_funding,
    approved,
    blank_declaration,
    captured,
    declared,
)
from tests.test_business_dgii_postgres import approve, cash_account
from tests.test_business_receipt_views_postgres import _web

users = shared.users
actions = shared.actions
pytestmark = [shared.pytestmark, pytest.mark.owner_acts]
fake = Faker()


def reason_fields(codes: list[str]) -> dict:
    return {code: {"field": REASONS[code].field, "words": REASONS[code].words} for code in codes}


def test_the_dossier_reports_the_same_missing_data_as_registros(actions) -> None:
    service, context, _ = actions
    funding = account_funding(cash_account(service, context))
    drafts = []
    for _ in range(2):
        number = fake.unique.numerify("B01########")
        draft, version = captured(service, context, number, funding)
        opened = service.dossier(context, draft).model_dump(mode="json")
        assert opened["missing"] == []
        assert opened["listo_gaps"]
        assert opened["reasons"] == reason_fields(opened["listo_gaps"])
        view = approved(service, context, draft, version)
        drafts.append(draft)
    assert declared(service, context, draft, view.version, category="02").outcome == "applied"
    rows = read_report(service.authority, context, ReportRequest()).items
    by_draft = {row.draft_id: list(row.missing) for row in rows}
    assert "expense_type_missing" in by_draft[str(drafts[0])]
    assert by_draft[str(drafts[1])] == []
    for draft in drafts:
        dossier = service.dossier(context, draft).model_dump(mode="json")
        assert dossier["missing"] == by_draft[str(draft)]
        assert dossier["reasons"] == reason_fields(dossier["missing"])


def test_both_accepted_dossiers_report_a_repeated_number(actions) -> None:
    service, context, _ = actions
    funding = account_funding(cash_account(service, context))
    numbers = [fake.unique.numerify("B01########") for _ in range(2)]
    draft_ids = []
    for number in numbers:
        draft, version = captured(service, context, number, funding)
        approved(service, context, draft, version)
        draft_ids.append(draft)
    # Approval now prevents new repeats. Represent two older approvals on this fixture.
    with service.authority.pool.connection() as connection:
        connection.execute("set local session_replication_role=replica")
        connection.execute(
            "update public.business_draft_revisions set after_facts="
            "jsonb_set(after_facts, '{fiscal,ncf,value}', to_jsonb(%s::text))"
            " where space_id=%s and draft_id=%s and after_facts#>>'{fiscal,ncf,value}'=%s",
            (numbers[0].lower(), context.actor.space_id, draft_ids[1], numbers[1]),
        )
    rows = read_report(service.authority, context, ReportRequest()).items
    assert len(rows) == 2
    for row in rows:
        assert "duplicate_document" in row.missing
        draft = next(d for d in draft_ids if str(d) == row.draft_id)
        assert service.dossier(context, draft).missing == row.missing


def test_a_manual_expense_without_a_draft_or_receipt_reports_its_own_gaps(actions) -> None:
    service, context, _ = actions
    account = cash_account(service, context)
    result = service.imports.money.write_entered(
        user_id=context.owner_id,
        request=MoneyRequest(
            kind="expense",
            account_id=account,
            amount="25.00",
            occurred_at=datetime.now(timezone.utc),
            note=fake.company(),
        ),
        idempotency_key=str(uuid4()),
        scope=context.scope,
    )
    identifier = result["activity"]["activity_id"]
    [row] = read_report(service.authority, context, ReportRequest()).items
    assert row.draft_id is None and row.missing
    detail = ExpenseDetail.model_validate(expense_detail(_web(service, context), identifier))
    assert detail.receipt_id is None and detail.draft_id is None
    assert detail.missing == row.missing
    assert detail.model_dump(mode="json")["reasons"] == reason_fields(list(row.missing))


def test_credit_note_keeps_its_prior_month_original_above_the_report_limit(
    actions, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, context, _ = actions
    funding = account_funding(cash_account(service, context))
    number = fake.numerify("B01########")
    original, version = captured(service, context, number, funding, occurred_on="2026-09-03")
    original_view = approved(service, context, original, version)
    credit, version = captured(
        service, context, fake.numerify("B04########"), funding,
        blank_declaration(
            id_type="1", category="09", goods_amount="100.00", payment_method="06",
            modified_ncf=number, actual_refund=True,
            purchase_activity_id=original_view.approval_result.activity_id,
        ),
        amount="118.00", itbis="18.00", kind="refund", occurred_on="2026-10-10",
    )
    result = approve(service, context, (credit, version, "refund"))
    assert result.outcome == "applied", result
    report = read_report(service.authority, context, ReportRequest())
    row = next(row for row in report.items if row.draft_id == str(credit))
    assert "credit_note_too_late" in row.missing
    monkeypatch.setattr(reporting_store, "_MAX_REPORT_INPUTS", 2)
    with pytest.raises(ActionError, match="business_report_too_large"):
        read_report(service.authority, context, ReportRequest())
    assert service.dossier(context, credit).missing == row.missing
