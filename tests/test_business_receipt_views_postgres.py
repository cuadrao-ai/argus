"""On real Postgres, the receipt views the API returns: a receipt linked to a
bridge draft takes its status, facts and message from that draft in the list
and in the detail, never from legacy import events; after approval it is a
saved expense; a saved read whose hand-off failed waits as interrupted and
retryable."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from argus.api.business_drafts import (
    bridged,
    overview_with_drafts,
    receipt_detail,
    receipt_summaries,
    scoped_legacy,
    search_with_drafts,
    updates_with_drafts,
)
from argus.domain.business.contracts.actions import (
    ApproveExpense,
    ReviewDraft,
    SettleRemainder,
)
from argus.domain.business.contracts.facts import BusinessFactPatch
from argus.domain.business.scope import BusinessScope
from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository
from argus.domain.ingestion.documents.service import DocumentsService
from argus.domain.ingestion.documents.store_postgres import PostgresDocumentStore
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.owner_scope import BusinessSpace
from fastapi import FastAPI
from psycopg.types.json import Jsonb
from starlette.requests import Request

from tests import test_business_attachment_preparation_postgres as bridge
from tests import test_business_single_candidate_postgres as single
from tests.document_sources_support import source_objects
from tests.ingestion.whatsapp_support import RefusingExtractor

actions = bridge.actions
users = bridge.users
pytestmark = bridge.pytestmark


def _web(service, context):  # noqa: ANN001
    """The Business context the receipt routes build for the signed-in owner.

    The list routes resolve the signed-in person's own open space, so the
    caller is the owner; the shared fixture makes the space by SQL, so the
    owner's grant (born with a space started through the app, #988) is seeded."""

    pool = service.authority.pool
    with pool.connection() as db:
        db.execute(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities)"
            " select %s,%s,%s,ARRAY['read','prepare','approve'] where not exists"
            " (select 1 from public.business_client_grants where space_id=%s and grantee_id=%s"
            " and revoked_at is null)",
            (
                context.actor.space_id,
                context.owner_id,
                context.owner_id,
                context.actor.space_id,
                context.owner_id,
            ),
        )
    hub = IngestionHub(
        PostgresConnectionRepository(pool),
        box=None,
        sink=service.imports,
        clock=service.imports.clock,
    )
    documents = DocumentsService(
        hub, PostgresDocumentStore(pool, source_objects()), RefusingExtractor()
    )
    app = FastAPI()
    app.state.financial_accounts_pool = pool
    request = Request(
        {
            "type": "http",
            "app": app,
            "method": "GET",
            "path": "/business/receipts",
            "path_params": {},
            "headers": [],
            "state": {"request_id": "synthetic-views"},
        }
    )
    scope = BusinessScope(
        person_id=context.owner_id, owner=BusinessSpace(str(context.actor.space_id))
    )
    return scoped_legacy(request, documents, hub, context.owner_id, scope)


def _views(web, cid: str):  # noqa: ANN001
    [row] = [item for item in receipt_summaries(web, "all") if item["id"] == cid]
    detail = receipt_detail(web, web.service.receipt(web.scope, cid))
    return row, detail


@pytest.mark.owner_acts
def test_a_linked_draft_owns_the_receipt_in_the_list_and_the_detail(actions):  # noqa: ANN001
    saved = single._saved(actions, "expense")
    service, context, _, cid, _, _ = saved
    web = _web(service, context)
    # Saved and read, before the hand-off: no draft, the receipt waits for it.
    bridge.bind(saved)
    row, detail = _views(web, cid)
    assert detail["draft_id"] is None
    assert row["status"] not in ("confirmed", "dismissed")
    result = bridge.finish(saved)
    assert result.outcome == "applied", result
    # Linked: the list and the detail say what the draft says.
    row, detail = _views(web, cid)
    for view in (row, detail):
        assert (view["status"], view["attention"], view["error_code"]) == (
            "review_ready",
            None,
            None,
        )
        assert (view["preparable"], view["enterable"]) == (False, False)
        assert Decimal(view["amount"]) == Decimal("33254.91")
        assert (view["currency"], view["merchant"], view["occurred_on"]) == (
            "DOP",
            "Hotel Brisa del Este SRL",
            "2026-10-09",
        )
    assert detail["draft_id"] == str(result.draft_id)
    assert detail["version"] == service.dossier(context, result.draft_id).version
    assert detail["record_context"]["capabilities"]
    # Linked and open: counted once as awaiting review, in the inbox, in search and in updates.
    counts = overview_with_drafts(web, date(2026, 10, 1), date(2026, 10, 31))
    assert (counts["awaiting_review"], counts["needs_attention"]) == (1, 0)
    assert [item["id"] for item in receipt_summaries(web, "inbox")] == [cid]
    [hit] = search_with_drafts(web, "Brisa", 5)["receipts"]
    assert (hit["id"], hit["status"], hit["merchant"]) == (
        cid,
        "review_ready",
        "Hotel Brisa del Este SRL",
    )
    [update] = [u for u in updates_with_drafts(web) if u["receipt_id"] == cid]
    assert (update["kind"], update["attention"], update["label"]) == (
        "receipt_ready",
        None,
        "Hotel Brisa del Este SRL",
    )
    # Approved: a saved expense in both views, counted as such.
    from tests.test_business_multi_purchase_postgres import _account

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
    row, detail = _views(web, cid)
    for view in (row, detail):
        assert (view["status"], view["attention"]) == ("confirmed", None)
        assert view["expense_id"] == str(approved.activity_id)
        assert view["account_id"] == str(funding)
    counts = overview_with_drafts(web, date(2026, 10, 1), date(2026, 10, 31))
    assert (counts["awaiting_review"], counts["needs_attention"]) == (0, 0)
    assert receipt_summaries(web, "inbox") == []
    [update] = [u for u in updates_with_drafts(web) if u["receipt_id"] == cid]
    assert (update["kind"], update["expense_id"]) == (
        "expense_confirmed",
        str(approved.activity_id),
    )
    # The expense is the search hit now; the receipt is not listed twice.
    found = search_with_drafts(web, "Brisa", 5)
    assert [e["id"] for e in found["expenses"]] == [str(approved.activity_id)]
    assert found["receipts"] == []


def test_a_saved_read_whose_handoff_failed_waits_as_interrupted_on_postgres(actions):  # noqa: ANN001
    saved = single._saved(actions, "expense")
    service, context, _, cid, _, _ = saved
    bridge.bind(saved)
    # What the documents service writes when the hand-off refuses after the read.
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.financial_document_extractions set draft = draft ||"
            " %s::jsonb where connection_id=%s",
            (
                Jsonb(
                    {
                        "status": "needs_attention",
                        "error_code": "business_preparation_binding_live",
                    }
                ),
                cid,
            ),
        )
    web = _web(service, context)
    row, detail = _views(web, cid)
    for view in (row, detail):
        assert (view["status"], view["attention"], view["error_code"]) == (
            "needs_attention",
            "interrupted",
            "business_preparation_binding_live",
        )
        assert view["preparable"] is True
    assert detail["draft_id"] is None
    assert detail["evidence"]["total"] == "33254.91"
    # The hand-off then succeeds: the draft owns the receipt.
    result = bridge.finish(saved)
    assert result.outcome == "applied", result
    row, detail = _views(web, cid)
    assert (row["status"], detail["draft_id"]) == ("review_ready", str(result.draft_id))


def test_the_overlay_leaves_a_receipt_without_a_draft_alone(actions):  # noqa: ANN001
    service, context, _ = actions
    web = _web(service, context)
    summary = {"id": str(UUID(int=7)), "status": "saved", "attention": None}
    assert bridged(web, [summary]) == [summary]


def test_a_repeat_receipt_shows_as_a_duplicate_of_its_original_in_every_view(actions):  # noqa: ANN001
    first = single._saved(actions, "expense")
    service, context, _, cid1, _, _ = first
    bridge.bind(first)
    assert bridge.finish(first).outcome == "applied"
    second = single._saved(actions, "expense")
    _, _, _, cid2, _, _ = second
    bridge.bind(second)
    assert bridge.finish(second).outcome == "applied"
    web = _web(service, context)
    row, detail = _views(web, cid2)
    for view in (row, detail):
        assert (view["status"], view["attention"], view["error_code"]) == (
            "needs_attention",
            "duplicate",
            "possible_duplicate",
        )
        assert view["duplicate_of"] == cid1
        assert Decimal(view["amount"]) == Decimal("33254.91")
    original, _ = _views(web, cid1)
    assert (original["status"], original["attention"]) == ("review_ready", None)
    counts = overview_with_drafts(web, date(2026, 10, 1), date(2026, 10, 31))
    assert (counts["awaiting_review"], counts["needs_attention"]) == (1, 1)
    [update] = [u for u in updates_with_drafts(web) if u["receipt_id"] == cid2]
    assert (update["kind"], update["attention"]) == (
        "receipt_needs_attention",
        "duplicate",
    )


def test_a_receipt_with_several_purchases_waits_with_the_read_kept_in_every_view(actions):  # noqa: ANN001
    from tests.test_business_multi_purchase_postgres import saved_two_purchases

    saved = saved_two_purchases(actions)
    service, context, _, cid, _, _ = saved
    bridge.bind(saved)
    assert bridge.finish(saved).outcome == "applied"
    web = _web(service, context)
    row, detail = _views(web, cid)
    for view in (row, detail):
        assert (view["status"], view["attention"], view["error_code"]) == (
            "needs_attention",
            "several_purchases",
            "several_purchases_found",
        )
        assert view["amount"] is None
        assert view["merchant"] == "Colmado La Esquina"
    assert detail["draft_id"] is not None


def test_a_receipt_whose_grant_went_away_asks_the_owner_to_rebind(actions):  # noqa: ANN001
    saved = single._saved(actions, "expense")
    service, context, _, cid, _, _ = saved
    bridge.bind(saved)
    # What the documents service writes when the bound grant no longer resolves.
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.financial_document_extractions set draft = draft ||"
            " %s::jsonb where connection_id=%s",
            (
                Jsonb(
                    {
                        "status": "needs_attention",
                        "error_code": "business_record_not_found",
                    }
                ),
                cid,
            ),
        )
    web = _web(service, context)
    row, detail = _views(web, cid)
    for view in (row, detail):
        assert (view["status"], view["attention"], view["error_code"]) == (
            "needs_attention",
            "interrupted",
            "business_record_not_found",
        )
        assert view["preparable"] is True
    # The web shows the rebind control from this code and the approve permission.
    assert "approve" in detail["record_context"]["capabilities"]


def _linked(actions):  # noqa: ANN001
    """One receipt read, bound and handed off: its draft owns it."""
    saved = single._saved(actions, "expense")
    bridge.bind(saved)
    result = bridge.finish(saved)
    assert result.outcome == "applied", result
    return saved, result


def test_a_dismissed_draft_closes_its_receipt_in_every_view(actions):  # noqa: ANN001
    saved, result = _linked(actions)
    service, context, _, cid, _, _ = saved
    web = _web(service, context)
    # No Business action dismisses a draft yet (the legacy dismiss refuses a
    # bridge draft with business_action_required); this is the state one will
    # write, and the views must already close the receipt on it.
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.financial_import_events set state='dismissed',"
            " version=version+1 where id=%s",
            (result.draft_id,),
        )
    row, detail = _views(web, cid)
    for view in (row, detail):
        assert (view["status"], view["attention"], view["error_code"]) == (
            "dismissed",
            None,
            None,
        )
        assert (view["preparable"], view["enterable"]) == (False, False)
    assert detail["draft_id"] == str(result.draft_id)
    # Closed: out of the inbox, out of the counts, and no update is announced for it.
    assert receipt_summaries(web, "inbox") == []
    counts = overview_with_drafts(web, date(2026, 10, 1), date(2026, 10, 31))
    assert (counts["awaiting_review"], counts["needs_attention"]) == (0, 0)
    assert [u for u in updates_with_drafts(web) if u["receipt_id"] == cid] == []


def test_a_receipt_linked_to_two_drafts_asks_a_person_to_check(actions):  # noqa: ANN001
    first, result1 = _linked(actions)
    service, context, _, cid1, _, _ = first
    second, result2 = _linked(actions)
    _, _, _, cid2, _, _ = second
    # The first receipt's source is linked to the second draft as well.
    with service.authority.pool.connection() as db:
        db.execute(
            "insert into public.business_draft_sources(space_id,draft_id,source_id)"
            " select s.space_id,%s,s.id from public.business_sources s"
            " where s.space_id=%s and s.connection_id=%s",
            (result2.draft_id, context.actor.space_id, UUID(cid1)),
        )
    web = _web(service, context)
    row, detail = _views(web, cid1)
    for view in (row, detail):
        assert (view["status"], view["attention"], view["error_code"]) == (
            "needs_attention",
            "check_details",
            "receipt_candidate_ambiguous",
        )
        assert (view["preparable"], view["enterable"]) == (False, False)
    # No draft is named: a person decides which one, through the drafts.
    assert detail["draft_id"] is None
    # The second receipt keeps its own single draft (a repeat of the first).
    other, _ = _views(web, cid2)
    assert (other["status"], other["attention"]) == ("needs_attention", "duplicate")
    counts = overview_with_drafts(web, date(2026, 10, 1), date(2026, 10, 31))
    assert (counts["awaiting_review"], counts["needs_attention"]) == (0, 2)
    [update] = [u for u in updates_with_drafts(web) if u["receipt_id"] == cid1]
    assert (update["kind"], update["attention"]) == (
        "receipt_needs_attention",
        "check_details",
    )
    assert result1.draft_id != result2.draft_id


@pytest.mark.owner_acts
def test_an_approved_draft_still_asking_for_purchases_says_so_in_every_view(actions):  # noqa: ANN001
    from tests.test_business_multi_purchase_postgres import _account, saved_two_purchases

    saved = saved_two_purchases(actions)
    service, context, _, cid, _, _ = saved
    bridge.bind(saved)
    first = bridge.finish(saved)
    assert first.outcome == "applied", first
    account = _account(service, context)
    version = service.dossier(context, first.draft_id).version
    filled = service.review(
        context,
        first.draft_id,
        ReviewDraft(
            version=version,
            facts=BusinessFactPatch.model_validate(
                {
                    "funding": {
                        "state": "known",
                        "value": {"kind": "business_account", "account_id": account},
                    },
                    "business_share": {"state": "known", "value": {"kind": "all"}},
                }
            ),
        ),
        "fill",
    )
    assert filled.outcome == "applied", filled
    chosen = service.review(
        context,
        first.draft_id,
        ReviewDraft(
            version=filled.version,
            facts=BusinessFactPatch.model_validate(
                {"amount": {"state": "known", "value": "245.00"}}
            ),
        ),
        "choose",
    )
    assert chosen.outcome == "applied", chosen
    recorded = service.approve(
        context,
        first.draft_id,
        ApproveExpense(version=chosen.version, action="record_expense"),
        "approve",
    )
    assert recorded.outcome == "applied", recorded
    web = _web(service, context)
    row, detail = _views(web, cid)
    # Saved, and still asking: one purchase is recorded, one is not.
    for view in (row, detail):
        assert (view["status"], view["attention"], view["error_code"]) == (
            "confirmed",
            "several_purchases",
            "purchases_unrecorded",
        )
        assert view["expense_id"] == str(recorded.activity_id)
        assert Decimal(view["amount"]) == Decimal("245.00")
    assert receipt_summaries(web, "inbox") == []
    counts = overview_with_drafts(web, date(2026, 10, 1), date(2026, 10, 31))
    assert (counts["awaiting_review"], counts["needs_attention"]) == (0, 0)
    [update] = [u for u in updates_with_drafts(web) if u["receipt_id"] == cid]
    assert (update["kind"], update["attention"]) == (
        "expense_confirmed",
        "several_purchases",
    )
    # A person settles the rest: the receipt stops asking in every view.
    after = service.dossier(context, first.draft_id)
    settled = service.settle_remainder(
        context, first.draft_id, SettleRemainder(version=after.version), "settle"
    )
    assert settled.outcome == "applied", settled
    row, detail = _views(web, cid)
    for view in (row, detail):
        assert (view["status"], view["attention"], view["error_code"]) == (
            "confirmed",
            None,
            None,
        )
