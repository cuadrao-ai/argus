"""On real Postgres: a saved expense approved from a bridge draft names the
receipt it was recorded from, in the expenses list and in search, so the
person can open its record. The legacy lookup reaches a receipt through
import observations, which a bridge draft never has."""

from __future__ import annotations

from datetime import date

from argus.api.business_drafts import expenses_with_receipts, search_with_drafts
from argus.domain.business.contracts.actions import ApproveExpense, ReviewDraft
from argus.domain.business.contracts.facts import BusinessFactPatch

from tests import test_business_attachment_preparation_postgres as bridge
from tests import test_business_single_candidate_postgres as single
from tests.test_business_multi_purchase_postgres import _account
from tests.test_business_receipt_views_postgres import _web

actions = bridge.actions
users = bridge.users
pytestmark = bridge.pytestmark


def test_an_expense_approved_from_a_draft_names_its_receipt(actions):  # noqa: ANN001
    saved = single._saved(actions, "expense")
    service, context, _, cid, _, _ = saved
    bridge.bind(saved)
    result = bridge.finish(saved)
    assert result.outcome == "applied", result
    funding = _account(service, context)
    version = service.dossier(context, result.draft_id).version
    filled = service.review(
        context,
        result.draft_id,
        ReviewDraft(
            version=version,
            facts=BusinessFactPatch.model_validate(
                {
                    "funding": {
                        "state": "known",
                        "value": {"kind": "business_account", "account_id": funding},
                    },
                    "business_share": {"state": "known", "value": {"kind": "all"}},
                }
            ),
        ),
        "fill",
    )
    assert filled.outcome == "applied", filled
    approved = service.approve(
        context,
        result.draft_id,
        ApproveExpense(version=filled.version, action="record_expense"),
        "approve",
    )
    assert approved.outcome == "applied", approved
    web = _web(service, context)
    period = (date(2026, 10, 1), date(2026, 10, 31))
    # The cause: the legacy lookup finds no receipt for a draft-recorded expense.
    [legacy] = web.service.expenses(web.scope, *period)
    assert (legacy["id"], legacy["receipt_id"]) == (str(approved.activity_id), None)
    # The list and the search both name the receipt the draft was linked to.
    [expense] = expenses_with_receipts(web, *period)
    assert (expense["id"], expense["receipt_id"]) == (str(approved.activity_id), cid)
    [hit] = search_with_drafts(web, "Brisa", 5)["expenses"]
    assert (hit["id"], hit["receipt_id"]) == (str(approved.activity_id), cid)
