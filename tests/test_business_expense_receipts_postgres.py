"""On real Postgres: a saved expense approved from a bridge draft names the
receipt it was recorded from, in the expenses list and in search, so the
person can open its record. The legacy lookup reaches a receipt through
import observations, which a bridge draft never has."""

from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

import pytest
from argus.api.business_drafts import (
    expense_detail,
    expenses_with_receipts,
    search_with_drafts,
)
from argus.domain.business.authority import ActionError, TrustedActor
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
    assert (expense["id"], expense["receipt_id"], expense["draft_id"]) == (
        str(approved.activity_id),
        cid,
        str(result.draft_id),
    )
    [hit] = search_with_drafts(web, "Brisa", 5)["expenses"]
    assert (hit["id"], hit["receipt_id"]) == (str(approved.activity_id), cid)
    # One expense on its own: the same records, with when it was recorded.
    detail = expense_detail(web, str(approved.activity_id))
    assert (detail["receipt_id"], detail["draft_id"]) == (cid, str(result.draft_id))
    assert detail["recorded_at"] is not None and detail["revision"] >= 1
    # An accountant with read and prepare opens the dossier behind it read-only.
    with service.authority.pool.connection() as db:
        db.execute(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities)"
            " values (%s,%s,%s,ARRAY['read','prepare'])",
            (context.actor.space_id, users["other"], context.owner_id),
        )
    reader = service.resolve_actor(
        TrustedActor(
            actor_id=UUID(users["other"]),
            actor_kind="member",
            space_id=context.actor.space_id,
        )
    )
    seen = service.dossier(reader, result.draft_id)
    assert (seen.draft_id, seen.approval_available) == (result.draft_id, False)
    assert "approve" not in seen.capabilities
    refused = service.approve(
        reader,
        result.draft_id,
        ApproveExpense(version=seen.version, action="record_expense"),
        "reader-approve",
    )
    assert (refused.outcome, refused.code) == (
        "permission_denied",
        "business_permission_denied",
    )


def test_an_expense_of_another_business_is_not_found(actions):  # noqa: ANN001
    service, context, _ = actions
    web = _web(service, context)
    with pytest.raises(ActionError) as refused:
        expense_detail(web, str(uuid4()))
    assert refused.value.result.code == "expense_not_found"
