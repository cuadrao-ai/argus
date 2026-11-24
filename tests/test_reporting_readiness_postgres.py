"""Real-store readiness, including a blocker created after approval."""

from uuid import uuid4

import pytest
from argus.domain.business.contracts.actions import ReviewDraft
from argus.domain.business.contracts.facts import BusinessFactPatch
from argus.domain.business.fiscal_profile import set_profile
from argus.domain.business.reporting_file import (
    RecordsExport,
    build_file,
    summarize_export,
)
from argus.domain.business.reporting_query import ReportRequest
from argus.domain.business.reporting_store import read_export_source, read_report
from faker import Faker

from tests import test_business_actions_postgres as shared
from tests import test_business_dgii_postgres as dgii
from tests.business.test_records_export_filename import one_stem
from tests.test_business_declaration_after_approval_postgres import (
    FILER,
    account_funding,
    approved,
    captured,
    declared,
)

users = shared.users
shared_actions = shared.actions
actions = dgii.actions
pytestmark = [shared.pytestmark, pytest.mark.owner_acts]


@pytest.fixture
def readiness_records(actions):
    service, context, _ = actions
    fake = Faker()
    fake.seed_instance(2169)
    set_profile(service.authority, context, dgii.filer_change(FILER), str(uuid4()))
    account = dgii.business_account(service, context, nickname=fake.word())
    purchased = []
    for index in range(3):
        draft, version = captured(
            service,
            context,
            f"B01{fake.unique.random_int(1, 99999999):08}",
            account_funding(account),
        )
        if index == 2:
            edited = service.review(
                context,
                draft,
                ReviewDraft(
                    version=version,
                    facts=BusinessFactPatch(
                        currency={"state": "known", "value": "USD"},
                        funding={"state": "known", "value": {"kind": "owner_funds"}},
                    ),
                ),
                str(uuid4()),
            )
            assert edited.outcome == "applied", edited
            version = edited.version
        view = approved(service, context, draft, version)
        result = declared(
            service, context, draft, view.version, category="02", payment_method="01"
        )
        assert result.outcome == "applied", result
        purchased.append((draft, view.approval_result.activity_id))
    sale = dgii.approve(service, context, dgii.reviewed(service, context, account, 4))
    assert sale.outcome == "applied", sale
    exported, activity_id = purchased[1]
    changed = declared(
        service,
        context,
        exported,
        service.dossier(context, exported).version,
        category=None,
    )
    assert changed.outcome == "applied", changed
    with service.authority.pool.connection() as db:
        db.execute(
            "insert into public.business_dgii_export_lines(space_id,activity_id,form,period,actor_id)"
            " values(%s,%s,'606','202609',%s)",
            (context.actor.space_id, activity_id, context.actor.actor_id),
        )
        db.execute(
            "update public.financial_accounts set archived=true where id=%s", (account,)
        )
    return service, context, str(sale.draft_id), str(exported), str(purchased[2][0])


@pytest.mark.parametrize("ready", [None, True, False])
def test_store_row_filter_and_count_share_current_readiness(readiness_records, ready):
    service, context, sale, exported, dollars = readiness_records
    all_rows = read_report(service.authority, context, ReportRequest()).items
    indexed = {row.draft_id: row for row in all_rows}
    # A sale is a log: its date, B01 NCF and client RNC make it ready, and a
    # workflow hold does not.
    assert indexed[sale].workflow_blockers == ("business_record_not_found",)
    assert (indexed[sale].ready, indexed[sale].missing) == (True, ())
    assert (
        indexed[exported].ready,
        indexed[exported].missing,
        indexed[exported].stage,
    ) == (False, ("expense_type_missing",), "exported")
    assert (indexed[dollars].ready, indexed[dollars].missing) == (True, ())
    result = read_report(
        service.authority, context, ReportRequest(filters={"ready": ready})
    )
    expected = [row for row in all_rows if ready is not False or not row.ready]
    assert {row.row_id for row in result.items} == {row.row_id for row in expected}
    assert result.matching_count == len(expected)
    assert result.overview.not_ready == sum(not row.ready for row in expected)
    assert result.overview.not_ready == 1


def test_usd_readiness_does_not_change_the_export_dialog_or_file(readiness_records):
    service, context, _, _, dollars = readiness_records
    request = ReportRequest(filters={"record_families": ["purchase"], "ready": True})
    dataset = read_export_source(service.authority, context)
    before = summarize_export(dataset, request)
    assert before.dgii.pending_rate_count == 1
    assert before.dgii.record_count == 1
    assert (
        build_file(
            dataset, RecordsExport(report=request, mode="dgii", format="csv")
        ).row_count
        == 1
    )
    from uuid import UUID

    draft = UUID(dollars)
    changed = declared(
        service, context, draft, service.dossier(context, draft).version, category=None
    )
    assert changed.outcome == "applied", changed
    dataset = read_export_source(service.authority, context)
    row = next(row for row in dataset.records if row.draft_id == dollars)
    assert (row.ready, row.missing) == (False, ("expense_type_missing",))
    after = summarize_export(dataset, request)
    # The names carry the minute each read happened; the rest must not move.
    assert one_stem(after.dgii.filenames.model_dump()) == one_stem(
        before.dgii.filenames.model_dump()
    )
    assert after.dgii.model_dump(exclude={"filenames"}) == before.dgii.model_dump(
        exclude={"filenames"}
    )
