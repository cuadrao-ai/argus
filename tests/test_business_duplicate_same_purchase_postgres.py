"""The owner settles a repeated read as the same purchase: the reviewed
document goes to Eliminados with the reason, and the comparison the dossier
carries recommends by the fiscal number."""

from __future__ import annotations

from uuid import uuid4

import pytest
from argus.domain.business.activity.queries import read_activity
from argus.domain.business.contracts.actions import ResolveDuplicate
from argus.domain.business.contracts.activity import ActivityFilters
from argus.domain.business.contracts.deletion import DocumentCommand
from psycopg.types.json import Jsonb

from tests import test_business_duplicate_resolution_postgres as resolution

actions = resolution.actions
users = resolution.users
pytestmark = resolution.pytestmark


def _pair(actions):
    service, _, _ = actions
    first, second = resolution.pair(actions)
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.financial_source_connections set lease_until=null,"
            "lease_holder=null where lease_until is not null"
        )
    return first, second


def _same_purchase(service, context, draft_id, other_id):
    return ResolveDuplicate(
        version=service.dossier(context, draft_id).version,
        other_draft_id=other_id,
        other_version=service.dossier(context, other_id).version,
        decision="same_purchase",
    )


def _fiscal_number(service, draft_id, number: str | None) -> None:
    known = {
        "state": "known",
        "value": number,
        "origin": "extracted",
        "verified": False,
        "source_ids": [str(uuid4())],
    }
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.financial_import_events set resolution ="
            " jsonb_set(resolution, '{business,facts,fiscal,ncf}', %s) where id=%s",
            (Jsonb(known if number else {"state": "unknown"}), str(draft_id)),
        )


def _fiscal_identity(service, draft_id, rnc: str, number: str) -> None:
    def known(value):
        return {
            "state": "known",
            "value": value,
            "origin": "extracted",
            "verified": False,
            "source_ids": [str(uuid4())],
        }

    with service.authority.pool.connection() as db:
        db.execute(
            "update public.financial_import_events set resolution = jsonb_set("
            "jsonb_set(resolution, '{business,facts,fiscal,ncf}', %s),"
            " '{business,facts,fiscal,rnc}', %s) where id=%s",
            (Jsonb(known(number)), Jsonb(known(rnc)), str(draft_id)),
        )


def _fiscal_pair(actions):
    """Two purchases a read told apart that carry one supplier RNC and NCF."""

    service, _, _ = actions
    drafts = []
    for content, merchant in ((b"Synthetic one", "Tienda uno"), (b"Synthetic two", "Tienda dos")):
        receipt = resolution.receipts._receipt(actions, content, merchant=merchant)
        resolution.preparation.bind(receipt)
        drafts.append(resolution.preparation.finish(receipt).draft_id)
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.financial_source_connections set lease_until=null,"
            "lease_holder=null where lease_until is not null"
        )
    for draft_id in drafts:
        _fiscal_identity(service, draft_id, "131246753", "B0100000077")
    return drafts


def _stored(service, draft_id):
    with service.authority.pool.connection() as db:
        return db.execute(
            "select state, version, resolution->'deleted' from"
            " public.financial_import_events where id=%s",
            (str(draft_id),),
        ).fetchone()


@pytest.mark.owner_acts
def test_same_purchase_sends_the_newer_document_to_eliminados_and_restores(actions):
    from argus.domain.business.actions.document_deletion import change_document

    service, context, _ = actions
    first, second = _pair(actions)
    older_before = _stored(service, first)
    decided = service.resolve_duplicate(
        context, second, _same_purchase(service, context, second, first), str(uuid4())
    )
    assert decided.outcome == "applied", decided
    view = service.dossier(context, second)
    assert view.review_state == "dismissed"
    assert view.deleted is not None and view.deleted.reason == "duplicate"
    assert view.deleted.actor.actor_id == context.actor.actor_id
    assert view.restore_available is True
    assert _stored(service, first) == older_before
    feed = read_activity(service.authority, context, limit=25, filters=ActivityFilters())
    [entry] = [item for item in feed.items if item.action == "resolve_duplicate"]
    assert entry.decision == "same_purchase"
    restored = change_document(
        service,
        context,
        DocumentCommand(action="restore_document", document_id=second),
        str(uuid4()),
    )
    assert restored.outcome == "applied", restored
    again = service.dossier(context, second)
    assert again.review_state == "open" and again.deleted is None
    assert "possible_duplicate" in {b.code for b in again.blockers}
    assert {c.draft_id for c in again.duplicate_candidates} == {first}


def test_only_the_owner_may_choose_same_purchase(actions):
    service, context, _ = actions
    first, second = _pair(actions)
    before = _stored(service, second)
    view = service.dossier(context, second)
    assert view.delete_available is False
    assert [c.decisions for c in view.duplicate_candidates] == [("different_purchase",)]
    refused = service.resolve_duplicate(
        context, second, _same_purchase(service, context, second, first), str(uuid4())
    )
    assert refused.outcome == "permission_denied", refused
    assert _stored(service, second) == before


@pytest.mark.owner_acts
def test_repeating_same_purchase_changes_nothing(actions):
    service, context, _ = actions
    first, second = _pair(actions)
    request = _same_purchase(service, context, second, first)
    key = str(uuid4())
    decided = service.resolve_duplicate(context, second, request, key)
    assert decided.outcome == "applied", decided
    after = _stored(service, second)
    assert service.resolve_duplicate(context, second, request, key) == decided
    assert _stored(service, second) == after
    repeated = service.resolve_duplicate(context, second, request, str(uuid4()))
    assert repeated.outcome in ("applied", "replayed"), repeated
    assert _stored(service, second) == after


@pytest.mark.owner_acts
def test_same_purchase_refuses_a_pair_that_is_not_pending(actions):
    service, context, _ = actions
    first, second = _pair(actions)
    before = _stored(service, first)
    refused = service.resolve_duplicate(
        context, first, _same_purchase(service, context, first, second), str(uuid4())
    )
    assert refused.code == "duplicate_pair_not_available", refused
    assert _stored(service, first) == before


@pytest.mark.owner_acts
@pytest.mark.parametrize(
    ("newer", "older", "recommendation", "ncf_differs"),
    [
        ("B0100000002", "B0100000001", "different_purchase", True),
        ("B0100000001", "b0100000001 ", "same_purchase", False),
        (None, None, None, False),
        ("B0100000001", None, None, True),
    ],
)
def test_the_comparison_recommends_by_the_fiscal_number(
    actions, newer, older, recommendation, ncf_differs
):
    service, context, _ = actions
    first, second = _pair(actions)
    _fiscal_number(service, second, newer)
    _fiscal_number(service, first, older)
    [candidate] = service.dossier(context, second).duplicate_candidates
    comparison = candidate.comparison
    assert candidate.draft_id == first
    assert candidate.basis == "read_facts"
    assert candidate.decisions == ("different_purchase", "same_purchase")
    assert comparison.recommendation == recommendation
    assert comparison.document.draft_id == second
    assert comparison.other.draft_id == first
    assert comparison.document.fiscal_number == newer
    assert comparison.other.counterparty == "Synthetic shop"
    assert comparison.other.amount == "250.5"
    assert comparison.other.currency == "DOP"
    assert comparison.other.occurred_on.isoformat() == "2026-10-11"
    assert comparison.other.file is not None
    assert comparison.other.file.filename == "foto.txt"
    assert comparison.other.received_at is not None
    assert comparison.other.received_at <= comparison.document.received_at
    assert ("fiscal_number" in comparison.differences) is ncf_differs
    assert "file" in comparison.differences
    assert not {"counterparty", "occurred_on", "amount", "currency"} & set(
        comparison.differences
    )


@pytest.mark.owner_acts
def test_a_shared_rnc_and_ncf_is_a_pair_the_owner_can_delete(actions):
    service, context, _ = actions
    first, second = _fiscal_pair(actions)
    view = service.dossier(context, second)
    assert "possible_duplicate" not in {b.code for b in view.blockers}
    [candidate] = view.duplicate_candidates
    assert candidate.draft_id == first
    assert candidate.basis == "fiscal_number"
    assert candidate.decisions == ("same_purchase",)
    assert candidate.comparison.recommendation == "same_purchase"
    assert "counterparty" in candidate.comparison.differences
    assert "fiscal_number" not in candidate.comparison.differences
    kept = service.resolve_duplicate(
        context,
        second,
        _same_purchase(service, context, second, first).model_copy(
            update={"decision": "different_purchase"}
        ),
        str(uuid4()),
    )
    assert kept.code == "duplicate_pair_not_available", kept
    decided = service.resolve_duplicate(
        context, second, _same_purchase(service, context, second, first), str(uuid4())
    )
    assert decided.outcome == "applied", decided
    deleted = service.dossier(context, second)
    assert deleted.deleted is not None and deleted.deleted.reason == "duplicate"
    assert deleted.duplicate_candidates == ()
    assert service.dossier(context, first).duplicate_candidates == ()


def test_a_shared_rnc_and_ncf_offers_no_decision_without_approve(actions):
    service, context, _ = actions
    first, second = _fiscal_pair(actions)
    [candidate] = service.dossier(context, second).duplicate_candidates
    assert (candidate.basis, candidate.decisions) == ("fiscal_number", ())


@pytest.mark.owner_acts
def test_the_route_answers_the_deleted_dossier_with_its_reason(actions):
    from tests.test_business_document_delete_postgres import _client

    service, context, _ = actions
    first, second = _pair(actions)
    request = _same_purchase(service, context, second, first)
    answer = _client(service, context).post(
        f"/api/v1/business/drafts/{second}/duplicate-resolution",
        json=request.model_dump(mode="json"),
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["review_state"] == "dismissed"
    assert body["deleted"]["reason"] == "duplicate"
    assert body["restore_available"] is True
    assert body["duplicate_candidates"] == []


def _total(service, draft_id, amount: str) -> None:
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.financial_import_events set resolution ="
            " jsonb_set(resolution, '{business,facts,amount,value}', %s) where id=%s",
            (Jsonb(amount), str(draft_id)),
        )


def _repeated(service, context, *draft_ids):
    """Whether the Bandeja rule still calls each draft a repeated comprobante."""

    from argus.domain.business.actions.listos import draft_standings
    from argus.domain.business.transactions import transaction

    with transaction(service.authority, context) as tx:
        events = [tx.imports.event(str(draft_id)) for draft_id in draft_ids]
        standings = draft_standings(tx, events)
    return {draft_id: standings[str(draft_id)].repeated for draft_id in draft_ids}


@pytest.mark.owner_acts
@pytest.mark.parametrize("shared_ncf", [False, True])
def test_a_pair_settled_as_different_purchases_leaves_the_review(actions, shared_ncf):
    service, context, _ = actions
    first, second = _pair(actions)
    if shared_ncf:
        for draft_id in (first, second):
            _fiscal_identity(service, draft_id, "131246753", "B0100000077")
    [candidate] = service.dossier(context, second).duplicate_candidates
    assert candidate.decisions == ("different_purchase", "same_purchase")
    kept = service.resolve_duplicate(
        context,
        second,
        _same_purchase(service, context, second, first).model_copy(
            update={"decision": "different_purchase"}
        ),
        str(uuid4()),
    )
    assert kept.outcome == "applied", kept
    *earlier, decided = service.dossier(context, second).history
    assert [revision.duplicate for revision in earlier] == [None] * len(earlier)
    assert decided.duplicate is not None
    assert decided.duplicate.model_dump() == {
        "decision": "different_purchase",
        "other_draft_id": first,
        "other_counterparty": "Synthetic shop",
        "other_filename": "foto.txt",
    }
    assert decided.after == decided.before
    for draft_id in (second, first):
        view = service.dossier(context, draft_id)
        assert view.duplicate_candidates == ()
        assert "possible_duplicate" not in {b.code for b in view.blockers}
    assert service.dossier(context, second).approval_available is True
    assert _repeated(service, context, first, second) == {first: False, second: False}
    refused = service.resolve_duplicate(
        context, second, _same_purchase(service, context, second, first), str(uuid4())
    )
    assert refused.code == "duplicate_pair_not_available", refused
    if shared_ncf:
        _total(service, first, "300.00")
        [back] = service.dossier(context, second).duplicate_candidates
        assert (back.draft_id, back.basis, back.decisions) == (
            first,
            "fiscal_number",
            ("same_purchase",),
        )
        assert _repeated(service, context, first, second) == {first: True, second: True}
