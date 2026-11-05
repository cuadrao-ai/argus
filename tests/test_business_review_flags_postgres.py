from __future__ import annotations

import io
import json
from datetime import date
from uuid import uuid4
from zipfile import ZipFile

import pytest
from argus.domain.business.contracts.actions import ApproveExpense
from argus.domain.business.export import ExportPeriod, export_package
from argus.domain.business.fiscal_profile import set_profile
from argus.domain.ingestion.documents.objects import InMemorySourceObjects

from tests import test_business_dgii_postgres as dgii

users = dgii.users
shared_actions = dgii.shared_actions
actions = dgii.actions
pytestmark = dgii.pytestmark

BAD_RNC = "199990022"
MALFORMED_NCF = "B01000008"


def approve_anyway(service, context, draft, key=None):
    identifier, version, _ = draft
    return service.approve(
        context,
        identifier,
        ApproveExpense(version=version, action="record_expense", approve_anyway=True),
        key or str(uuid4()),
    )


def receipts(service, context, draft):
    with service.authority.pool.connection() as db:
        return db.execute(
            "select command, outcome from public.business_action_receipts"
            " where space_id=%s and command->>'draft_id'=%s"
            " and command->>'action'='approve_expense' order by created_at",
            (context.actor.space_id, str(draft[0])),
        ).fetchall()


def export_issues(service, context):
    blob = export_package(
        service.authority,
        context,
        ExportPeriod(date(2026, 9, 1), date(2026, 9, 30)),
        InMemorySourceObjects(),
    )
    with ZipFile(io.BytesIO(blob)) as archive:
        return {
            issue["code"]
            for issue in json.loads(archive.read("manifest.json"))["dgii"]["issues"]
        }


class TestConfirmedApproval:
    @pytest.mark.parametrize(
        "override,flag",
        [
            ({"rnc": BAD_RNC}, "rnc_check_digit"),
            ({"ncf": MALFORMED_NCF}, "ncf_malformed"),
        ],
    )
    def test_a_flagged_receipt_needs_confirmation_then_approves_and_is_logged(
        self, actions, override, flag
    ):
        service, context, _ = actions
        draft = dgii.reviewed(
            service, context, dgii.cash_account(service, context), override=override
        )
        view = service.dossier(context, draft[0])
        assert [(f.code, f.confirm) for f in view.review_flags] == [(flag, True)]
        assert view.approval_available is True

        refused = dgii.approve(service, context, draft)
        assert refused.outcome == "invalid_input"
        assert refused.code == "approval_confirmation_required"
        assert refused.flags == (flag,)

        applied = approve_anyway(service, context, draft)
        assert applied.outcome == "applied", applied
        logged = receipts(service, context, draft)
        assert [row[0]["request"].get("approve_anyway") for row in logged] == [
            None,
            True,
        ]
        assert logged[-1][1]["outcome"] == "applied"

    def test_a_flagged_ncf_is_stored_exactly_as_read(self, actions):
        service, context, _ = actions
        draft = dgii.reviewed(
            service,
            context,
            dgii.cash_account(service, context),
            override={"ncf": MALFORMED_NCF},
        )
        assert approve_anyway(service, context, draft).outcome == "applied"
        assert service.dossier(context, draft[0]).facts.fiscal.ncf.value == MALFORMED_NCF

    def test_a_clean_receipt_approves_without_confirmation(self, actions):
        service, context, _ = actions
        draft = dgii.reviewed(service, context, dgii.cash_account(service, context))
        assert service.dossier(context, draft[0]).review_flags == ()
        assert dgii.approve(service, context, draft).outcome == "applied"

    def test_a_high_itbis_only_warns(self, actions):
        service, context, _ = actions
        draft = dgii.reviewed(
            service,
            context,
            dgii.cash_account(service, context),
            override={"itbis": "900.00"},
        )
        view = service.dossier(context, draft[0])
        assert [(f.code, f.confirm) for f in view.review_flags] == [("itbis_high", False)]
        assert dgii.approve(service, context, draft).outcome == "applied"

    def test_the_export_still_refuses_a_confirmed_bad_rnc(self, actions):
        service, context, _ = actions
        set_profile(service.authority, context, dgii.filer_change("199990013"), "rnc")
        draft = dgii.reviewed(
            service,
            context,
            dgii.cash_account(service, context),
            override={"rnc": BAD_RNC},
        )
        assert approve_anyway(service, context, draft).outcome == "applied"
        assert "fiscal_identity_check_digit" in export_issues(service, context)


class TestSameRncAndNcf:
    def test_a_repeat_is_refused_with_the_recorded_one(self, actions):
        service, context, _ = actions
        account = dgii.cash_account(service, context)
        first = dgii.reviewed(service, context, account)
        assert dgii.approve(service, context, first).outcome == "applied"
        repeat = dgii.reviewed(service, context, account)
        refused = dgii.approve(service, context, repeat)
        assert refused.code == "duplicate_comprobante"
        assert refused.existing_record_id == first[0]

    def test_the_same_rnc_with_another_ncf_is_not_a_repeat(self, actions):
        service, context, _ = actions
        account = dgii.cash_account(service, context)
        first = dgii.reviewed(service, context, account)
        assert dgii.approve(service, context, first).outcome == "applied"
        other = dgii.reviewed(service, context, account, override={"ncf": "B0100000002"})
        assert dgii.approve(service, context, other).outcome == "applied"
