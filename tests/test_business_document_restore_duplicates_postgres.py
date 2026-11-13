from __future__ import annotations

from uuid import uuid4

import pytest
from argus.api.business_drafts import receipt_detail
from argus.domain.business.transactions import transaction

from tests import test_business_document_delete_postgres as deletion
from tests.test_business_document_delete_postgres import (
    _act,
    _captured_purchase,
    _client,
)

actions = deletion.actions
users = deletion.users
pytestmark = deletion.pytestmark


def _finish_repeat(receipt, target=None):
    from tests import test_business_attachment_preparation_postgres as preparation

    preparation.bind(receipt, target)
    result = preparation.finish(receipt)
    assert result.outcome == "applied", result
    service, _, _, cid, _, _ = receipt
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.financial_source_connections set lease_until=null,lease_holder=null where id=%s",
            (cid,),
        )
        db.execute(
            "update public.financial_document_extractions set draft=jsonb_set(draft,'{status}','\"review_ready\"') where connection_id=%s",
            (cid,),
        )
    return result.draft_id


def _assert_duplicate_approval_refused(service, context, draft_id, other_id):
    from argus.domain.business.contracts.actions import ApproveExpense

    view = service.dossier(context, draft_id)
    assert "possible_duplicate" in {blocker.code for blocker in view.blockers}
    assert not view.approval_available
    assert str(other_id) in {str(item.draft_id) for item in view.duplicate_candidates}
    refused = service.approve(
        context,
        draft_id,
        ApproveExpense(
            action="record_expense", version=view.version, approve_anyway=True
        ),
        str(uuid4()),
    )
    assert (refused.outcome, refused.code) == ("invalid_input", "possible_duplicate")


@pytest.mark.parametrize("by_draft", [False, True])
@pytest.mark.parametrize("arrived_while_deleted", [False, True])
def test_restore_rechecks_newly_arrived_receipt_duplicates_on_both_sides(
    actions, by_draft, arrived_while_deleted
):
    from tests import test_business_duplicates_postgres as duplicates
    from tests.test_business_receipt_views_postgres import _web

    service, context, _ = actions
    original = duplicates._receipt(actions, b"Synthetic original purchase")
    original_id = _finish_repeat(original)
    client = _client(service, context)
    target = original_id if by_draft else original[3]
    if arrived_while_deleted:
        assert _act(client, target, "delete").status_code == 200
    repeated = duplicates._receipt(actions, b"Synthetic second photograph")
    repeated_id = _finish_repeat(repeated)
    if arrived_while_deleted:
        assert duplicates._event(service, repeated_id) == (None, [], None)
    else:
        assert _act(client, target, "delete").status_code == 200
    key = str(uuid4())
    restored = _act(client, target, "restore", key)
    assert restored.status_code == 200, restored.text
    with transaction(service.authority, context) as tx:
        after_restore = tuple(
            tx.imports.event(str(draft)) for draft in (original_id, repeated_id)
        )
    assert _act(client, target, "restore", key).json() == restored.json()
    with transaction(service.authority, context) as tx:
        assert tuple(
            tx.imports.event(str(draft)) for draft in (original_id, repeated_id)
        ) == after_restore
    web = _web(service, context)
    for receipt, draft_id, other_id in (
        (original, original_id, repeated_id),
        (repeated, repeated_id, original_id),
    ):
        row = receipt_detail(web, web.service.receipt(web.scope, receipt[3]))
        assert (row["attention"], row["error_code"]) == (
            "duplicate",
            "possible_duplicate",
        )
        assert row["bandeja_group"]["group"] == "attention"
        _assert_duplicate_approval_refused(service, context, draft_id, other_id)


@pytest.mark.parametrize("multiple", [False, True])
def test_restore_rechecks_generic_candidates_against_new_prepared_purchase(
    actions, multiple
):
    from argus.domain.business.service import BusinessError

    from tests import test_business_duplicates_postgres as duplicates
    from tests.test_business_receipt_views_postgres import _web

    service, context, _ = actions
    original = duplicates._receipt(actions, b"Synthetic legacy purchase")
    candidates = original[5].candidates
    if multiple:
        first = candidates[0]
        candidates += (
            first.model_copy(
                update={
                    "source": first.source.model_copy(
                        update={"external_id": str(uuid4())}
                    ),
                    "amount": "750.50",
                }
            ),
        )
    service.imports.submit(
        user_id=context.owner_id,
        connection_id=original[3],
        candidates=candidates,
        scope=context.scope,
    )
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.financial_source_connections set lease_until=null,lease_holder=null where id=%s",
            (original[3],),
        )
        db.execute(
            "update public.financial_document_extractions set draft=jsonb_set(draft,'{status}','\"review_ready\"') where connection_id=%s",
            (original[3],),
        )
    with transaction(service.authority, context) as tx:
        [original_event] = [
            event
            for event in tx.imports.events(("open",))
            if any(
                observation.external_id == candidates[0].source.external_id
                for observation in tx.imports.observations(event.id)
            )
        ]
    client = _client(service, context)
    assert _act(client, original[3], "delete").status_code == 200
    repeated = duplicates._receipt(actions, b"Synthetic newly prepared purchase")
    repeated_id = _finish_repeat(repeated)
    assert duplicates._event(service, repeated_id) == (None, [], None)
    assert _act(client, original[3], "restore").status_code == 200
    web = _web(service, context)
    original_view = web.service.receipt(web.scope, original[3])
    expected_blocker = "several_purchases_found" if multiple else "possible_duplicate"
    assert original_view.review.blocker == expected_blocker
    refusal = "missing_fields" if multiple else "possible_duplicate"
    with pytest.raises(BusinessError, match=refusal):
        web.service.confirm(
            web.scope, original[3], original_view.version, str(uuid4())
        )
    view = service.dossier(context, repeated_id)
    assert "possible_duplicate" in {blocker.code for blocker in view.blockers}
    from argus.domain.business.contracts.actions import ApproveExpense

    refused = service.approve(
        context,
        repeated_id,
        ApproveExpense(
            action="record_expense", version=view.version, approve_anyway=True
        ),
        str(uuid4()),
    )
    assert (refused.outcome, refused.code) == ("invalid_input", "possible_duplicate")
    with transaction(service.authority, context) as tx:
        assert str(repeated_id) in tx.imports.event(original_event.id).possible_duplicates
        assert original_event.id in tx.imports.event(str(repeated_id)).possible_duplicates


def test_restore_rechecks_message_only_purchase_against_new_capture(actions):
    service, context, _ = actions
    original_id = _captured_purchase(service, context)
    client = _client(service, context)
    assert _act(client, original_id, "delete").status_code == 200
    repeated_id = _captured_purchase(service, context)
    assert _act(client, original_id, "restore").status_code == 200
    _assert_duplicate_approval_refused(service, context, original_id, repeated_id)
    _assert_duplicate_approval_refused(service, context, repeated_id, original_id)


@pytest.mark.parametrize("deciding_side", ["original", "repeated"])
def test_restore_keeps_a_valid_duplicate_decision_but_matching_ncf_still_collides(
    actions, deciding_side
):
    from argus.domain.business.contracts.actions import ApproveExpense, ReviewDraft
    from argus.domain.business.contracts.dgii import FiscalReview

    from tests import test_business_duplicates_postgres as duplicates
    from tests.test_business_approval_fiscal_postgres import SUPPLIER, saved_declaration
    from tests.test_business_duplicate_resolution_postgres import request_for

    service, context, _ = actions
    original = duplicates._receipt(actions, b"Synthetic first fiscal purchase")
    original_id = _finish_repeat(original)
    client = _client(service, context)
    assert _act(client, original_id, "delete").status_code == 200
    repeated = duplicates._receipt(actions, b"Synthetic second fiscal photograph")
    repeated_id = _finish_repeat(repeated)
    assert _act(client, original_id, "restore").status_code == 200
    for draft_id in (original_id, repeated_id):
        view = service.dossier(context, draft_id)
        updated = service.review(
            context,
            draft_id,
            ReviewDraft(
                version=view.version,
                dgii=FiscalReview.model_validate(
                    {
                        "fiscal": {
                            "rnc": SUPPLIER,
                            "ncf": "B0100000991",
                            "itbis": "0.00",
                        },
                        "declaration": saved_declaration(
                            services_amount="250.50", paid_on=None
                        ),
                    }
                ),
            ),
            str(uuid4()),
        )
        assert updated.outcome == "applied", updated
    _assert_duplicate_approval_refused(service, context, original_id, repeated_id)
    _assert_duplicate_approval_refused(service, context, repeated_id, original_id)
    deciding, other = (
        (original_id, repeated_id)
        if deciding_side == "original"
        else (repeated_id, original_id)
    )
    decision = service.resolve_duplicate(
        context,
        deciding,
        request_for(service, context, deciding, other),
        str(uuid4()),
    )
    assert decision.outcome == "applied", decision
    assert _act(client, original_id, "delete").status_code == 200
    assert _act(client, original_id, "restore").status_code == 200
    for draft_id in (original_id, repeated_id):
        assert "possible_duplicate" not in {
            blocker.code for blocker in service.dossier(context, draft_id).blockers
        }
    from tests.test_business_receipt_views_postgres import _web

    web = _web(service, context)
    for receipt in (original, repeated):
        row = receipt_detail(web, web.service.receipt(web.scope, receipt[3]))
        assert row["attention"] is None and row["error_code"] is None
    approved = service.approve(
        context,
        repeated_id,
        ApproveExpense(
            action="record_expense",
            version=service.dossier(context, repeated_id).version,
            approve_anyway=True,
        ),
        str(uuid4()),
    )
    assert approved.outcome == "applied", approved
    refused = service.approve(
        context,
        original_id,
        ApproveExpense(
            action="record_expense",
            version=service.dossier(context, original_id).version,
            approve_anyway=True,
        ),
        str(uuid4()),
    )
    assert (refused.outcome, refused.code) == ("invalid_input", "duplicate_comprobante")
    assert str(refused.existing_record_id) == str(repeated_id)
    with service.authority.pool.connection() as db:
        assert db.execute(
            "select count(*) from public.financial_records where owner_space_id=%s",
            (context.actor.space_id,),
        ).fetchone() == (1,)


@pytest.mark.parametrize("changed_side", ["original", "repeated"])
def test_restore_reopens_both_sides_when_duplicate_decision_evidence_changed(
    actions, changed_side
):
    from argus.domain.business.contracts.actions import ExistingDraft

    from tests import test_business_duplicates_postgres as duplicates
    from tests.test_business_duplicate_resolution_postgres import request_for

    service, context, _ = actions
    original = duplicates._receipt(actions, b"Synthetic original decided purchase")
    original_id = _finish_repeat(original)
    client = _client(service, context)
    assert _act(client, original_id, "delete").status_code == 200
    repeated = duplicates._receipt(actions, b"Synthetic repeat decided purchase")
    repeated_id = _finish_repeat(repeated)
    changed_id = original_id if changed_side == "original" else repeated_id
    assert _act(client, original_id, "restore").status_code == 200
    decided = service.resolve_duplicate(
        context,
        original_id,
        request_for(service, context, original_id, repeated_id),
        str(uuid4()),
    )
    assert decided.outcome == "applied", decided
    added = duplicates._receipt(actions, b"Synthetic revised source evidence")
    assert _finish_repeat(
        added,
        ExistingDraft(
            draft_id=changed_id,
            version=service.dossier(context, changed_id).version,
        ),
    ) == changed_id
    assert _act(client, original_id, "delete").status_code == 200
    assert _act(client, original_id, "restore").status_code == 200
    _assert_duplicate_approval_refused(service, context, original_id, repeated_id)
    _assert_duplicate_approval_refused(service, context, repeated_id, original_id)


def test_restore_flags_a_recorded_match_without_changing_the_recorded_event(actions):
    from argus.domain.business.contracts.actions import ApproveExpense

    from tests import test_business_duplicates_postgres as duplicates

    service, context, _ = actions
    original = duplicates._receipt(actions, b"Synthetic original pending purchase")
    original_id = _finish_repeat(original)
    client = _client(service, context)
    assert _act(client, original_id, "delete").status_code == 200
    repeated = duplicates._receipt(actions, b"Synthetic recorded matching purchase")
    repeated_id = _finish_repeat(repeated)
    approved = service.approve(
        context,
        repeated_id,
        ApproveExpense(
            action="record_expense",
            version=service.dossier(context, repeated_id).version,
            approve_anyway=True,
        ),
        str(uuid4()),
    )
    assert approved.outcome == "applied", approved
    with transaction(service.authority, context) as tx:
        before = tx.imports.event(str(repeated_id))
    assert _act(client, original_id, "restore").status_code == 200
    _assert_duplicate_approval_refused(service, context, original_id, repeated_id)
    with transaction(service.authority, context) as tx:
        assert tx.imports.event(str(repeated_id)) == before
