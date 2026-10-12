"""On real Postgres, the receipt views the API returns: a receipt linked to a
bridge draft takes its status, facts and message from that draft in the list
and in the detail, never from legacy import events; after approval it is a
saved expense; a saved read whose hand-off failed waits as interrupted and
retryable."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from argus.api.business_drafts import (
    bridged,
    overview_with_drafts,
    receipt_detail,
    receipt_summaries,
    scoped_legacy,
)
from argus.domain.business.contracts.actions import ApproveExpense, ReviewDraft
from argus.domain.business.contracts.facts import BusinessFactPatch
from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository
from argus.domain.ingestion.documents.service import DocumentsService
from argus.domain.ingestion.documents.store_postgres import PostgresDocumentStore
from argus.domain.ingestion.hub import IngestionHub
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
    """The Business context the receipt routes build for the signed-in owner."""

    pool = service.authority.pool
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
    return scoped_legacy(request, documents, hub, context.owner_id, None)


def _views(web, cid: str):  # noqa: ANN001
    [row] = [item for item in receipt_summaries(web, "all") if item["id"] == cid]
    detail = receipt_detail(web, web.service.receipt(web.scope, cid))
    return row, detail


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
    # Linked and open: counted once as awaiting review, in the inbox.
    counts = overview_with_drafts(web, date(2026, 10, 1), date(2026, 10, 31))
    assert (counts["awaiting_review"], counts["needs_attention"]) == (1, 0)
    assert [item["id"] for item in receipt_summaries(web, "inbox")] == [cid]
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
