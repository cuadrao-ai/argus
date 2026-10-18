from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from argus.domain.ingestion.connections import InMemoryConnectionRepository
from argus.domain.ingestion.documents.extractor import batch_from_result
from argus.domain.ingestion.documents.models import ExtractionResult
from argus.domain.ingestion.documents.service import DocumentsService
from argus.domain.ingestion.documents.store import InMemoryDocumentStore
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.owner_scope import PERSONAL
from pydantic import ValidationError


@pytest.mark.parametrize("participant", ["", "p" * 101])
@pytest.mark.parametrize("nested", [False, True])
def test_proposal_participant_references_are_bounded(participant, nested):
    from argus.domain.ingestion.documents.models import DraftProposal

    value = {"participant_ids": [participant]}
    if nested:
        value = {"item_assignments": [{"item_id": "item-1", **value}]}
    with pytest.raises(ValidationError):
        DraftProposal.model_validate(value)


def test_unknown_balance_does_not_reject_transactions():
    result = ExtractionResult.model_validate(
        {
            "complete": True,
            "readable": True,
            "pages_read": [1],
            "observations": [
                {
                    "page": 1,
                    "row": 1,
                    "evidence": "balance",
                    "amount": "100",
                    "currency": "USD",
                },
                {
                    "page": 1,
                    "row": 2,
                    "evidence": "transaction",
                    "amount": "40.25",
                    "currency": "USD",
                    "direction": "outflow",
                    "occurred_on": "2026-09-07",
                },
            ],
        }
    )
    batch = batch_from_result(
        result, "digest", "connection", datetime.now(timezone.utc), 1
    )
    assert len(batch.observations) == 2
    assert batch.observations[0].balance_scope is None
    assert len(batch.candidates) == 1
    assert batch.issues[0].code == "candidate_incompatible"


@pytest.mark.asyncio
async def test_capture_saves_without_extractor_and_reopens_same_source():
    repo = InMemoryConnectionRepository()
    store = InMemoryDocumentStore(repo)
    hub = IngestionHub(
        repo, box=None, sink=None, clock=lambda: datetime.now(timezone.utc)
    )
    extractor = Mock(extract=AsyncMock(side_effect=RuntimeError()))
    service = DocumentsService(hub, store, extractor)
    result = await service.upload(
        user_id="owner",
        content=b"%PDF-fixture",
        filename="test.pdf",
        media_type="application/pdf",
        scope=PERSONAL,
    )
    assert result.status == "saved"
    extractor.extract.assert_not_awaited()
    reopened = DocumentsService(hub, store, extractor)
    assert reopened.get(
        user_id="owner", connection_id=result.connection_id, scope=PERSONAL
    ).source_available
    assert (
        reopened.source_bytes(
            user_id="owner", connection_id=result.connection_id, scope=PERSONAL
        )
        == b"%PDF-fixture"
    )


@pytest.mark.parametrize("scope", [None, "opening", "running"])
def test_review_only_balances_preserve_scope_and_sibling_transaction(scope):
    from tests.ingestion.test_document_extraction import result

    parsed = result()
    balance = parsed.observations[1].model_copy(update={"balance_scope": scope})
    parsed = parsed.model_copy(update={"observations": (parsed.observations[0], balance)})
    batch = batch_from_result(parsed, "digest", "owner", datetime.now(timezone.utc), 1)
    assert len(batch.candidates) == 1
    assert batch.observations[1].balance_scope == scope
    assert batch.issues[0].code == "candidate_incompatible"


@pytest.mark.parametrize("ambiguous", [False, True])
def test_receipt_items_are_retained_and_ambiguous_purchases_withheld(ambiguous):
    from argus.domain.ingestion.documents.models import ReceiptDetails, ReceiptItem

    from tests.ingestion.test_document_extraction import result

    parsed = result()
    purchase = parsed.observations[0]
    observations = (
        (purchase,)
        if not ambiguous
        else (purchase, purchase.model_copy(update={"row": 3, "amount": "20"}))
    )
    receipt = ReceiptDetails(
        payment_status="paid",
        total=purchase.amount,
        currency=purchase.currency,
        items=(ReceiptItem(id="item-1", quantity="2", unit_price="10", total="20"),),
    )
    parsed = parsed.model_copy(update={"observations": observations, "receipt": receipt})
    batch = batch_from_result(parsed, "digest", "owner", datetime.now(timezone.utc), 1)
    assert batch.receipt == receipt
    assert len(batch.observations) == len(observations)
    assert len(batch.candidates) == (0 if ambiguous else 1)
    assert bool(batch.issues) == ambiguous


@pytest.mark.asyncio
async def test_failure_keeps_source_and_duplicate_does_not_retry(rig):
    from tests.ingestion.test_document_service import fake

    service, _, extractor, sink = rig
    user = fake.uuid4()
    extractor.extract.side_effect = RuntimeError("secret body must not be stored")
    upload = dict(
        user_id=user,
        content=b"%PDF-fixture",
        filename="test.pdf",
        media_type="application/pdf",
        consent=True,
    )
    first = await service.upload(**upload, scope=PERSONAL)
    await service.background_prepare(
        user_id=user, connection_id=first.connection_id, scope=PERSONAL
    )
    assert (
        service.get(
            user_id=user, connection_id=first.connection_id, scope=PERSONAL
        ).status
        == "needs_attention"
    )
    duplicate = await service.upload(**upload, scope=PERSONAL)
    await service.background_prepare(
        user_id=user, connection_id=duplicate.connection_id, scope=PERSONAL
    )
    assert duplicate.connection_id == first.connection_id
    assert extractor.extract.await_count == 1
    assert (
        service.source_bytes(
            user_id=user, connection_id=first.connection_id, scope=PERSONAL
        )
        == upload["content"]
    )
    sink.submit.assert_not_called()


@pytest.mark.asyncio
async def test_saved_without_consent_requires_explicit_preparation(rig):
    from argus.domain.ingestion.documents.service import DocumentServiceError

    service, _, extractor, _ = rig
    saved = await service.upload(
        user_id="owner",
        content=b"%PDF-fixture",
        filename="test.pdf",
        media_type="application/pdf",
        scope=PERSONAL,
    )
    await service.background_prepare(
        user_id="owner", connection_id=saved.connection_id, scope=PERSONAL
    )
    extractor.extract.assert_not_awaited()
    with pytest.raises(DocumentServiceError, match="consent_required"):
        service.queue(
            user_id="owner",
            connection_id=saved.connection_id,
            consent=False,
            scope=PERSONAL,
        )
    service.queue(
        user_id="owner", connection_id=saved.connection_id, consent=True, scope=PERSONAL
    )
    await service.background_prepare(
        user_id="owner", connection_id=saved.connection_id, scope=PERSONAL
    )
    assert (
        service.get(
            user_id="owner", connection_id=saved.connection_id, scope=PERSONAL
        ).status
        == "review_ready"
    )
    assert extractor.extract.await_count == 1


@pytest.mark.asyncio
async def test_interrupted_attempt_needs_attention_without_automatic_retry(rig):
    from datetime import timedelta

    service, hub, extractor, _ = rig
    saved = await service.upload(
        user_id="owner",
        content=b"%PDF-fixture",
        filename="test.pdf",
        media_type="application/pdf",
        consent=True,
        scope=PERSONAL,
    )
    draft = service.get(
        user_id="owner", connection_id=saved.connection_id, scope=PERSONAL
    )
    hub.connections.lease(
        connection_id=saved.connection_id, holder="lost-worker", now=hub.clock()
    )
    service._update("owner", draft, holder="lost-worker", status="preparing")
    old = hub.clock()
    hub.clock = lambda: old + timedelta(minutes=6)
    reopened = service.get(
        user_id="owner", connection_id=saved.connection_id, scope=PERSONAL
    )
    assert reopened.status == "needs_attention"
    assert reopened.error_code == "document_preparation_interrupted"
    await service.background_prepare(
        user_id="owner", connection_id=saved.connection_id, scope=PERSONAL
    )
    extractor.extract.assert_not_awaited()


@pytest.mark.asyncio
async def test_proposal_version_and_owner_checks_preserve_preparation(rig):
    from argus.domain.ingestion.connections import ConnectionNotFound
    from argus.domain.ingestion.documents.models import DraftProposal, ItemAssignment
    from argus.domain.ingestion.documents.service import DocumentServiceError

    service, _, _, _ = rig
    saved = await service.upload(
        user_id="owner",
        content=b"%PDF-fixture",
        filename="test.pdf",
        media_type="application/pdf",
        consent=True,
        scope=PERSONAL,
    )
    await service.background_prepare(
        user_id="owner", connection_id=saved.connection_id, scope=PERSONAL
    )
    before = service.store.get(user_id="owner", connection_id=saved.connection_id)
    draft = service.get(
        user_id="owner", connection_id=saved.connection_id, scope=PERSONAL
    )
    proposal = DraftProposal(
        requested_plan="Trip",
        payer_id="p1",
        participant_ids=("p1", "p2"),
        split_method="items",
        item_assignments=(
            ItemAssignment(item_id="item-1", participant_ids=("p1", "p2")),
        ),
    )
    updated = service.update_proposal(
        user_id="owner",
        connection_id=draft.connection_id,
        version=draft.version,
        proposal=proposal,
        scope=PERSONAL,
    )
    assert updated.proposal == proposal
    assert service.store.get(user_id="owner", connection_id=draft.connection_id) == before
    with pytest.raises(DocumentServiceError, match="version_conflict"):
        service.update_proposal(
            user_id="owner",
            connection_id=draft.connection_id,
            version=draft.version,
            proposal=proposal,
            scope=PERSONAL,
        )
    with pytest.raises(ConnectionNotFound):
        service.source_bytes(
            user_id="other", connection_id=draft.connection_id, scope=PERSONAL
        )


# This is the established mocked service fixture, not a durable database assertion.
from tests.ingestion import test_document_service as support  # noqa: E402

rig = support.rig


@pytest.mark.asyncio
async def test_legacy_checkpoint_reupload_retains_source_without_model(rig):
    service, hub, extractor, _ = rig
    saved = await service.upload(
        user_id="owner",
        content=b"%PDF-fixture",
        filename="test.pdf",
        media_type="application/pdf",
        consent=True,
        scope=PERSONAL,
    )
    await service.background_prepare(
        user_id="owner", connection_id=saved.connection_id, scope=PERSONAL
    )
    original = service.store.get(user_id="owner", connection_id=saved.connection_id)
    service.store._drafts.clear()
    service.store._sources.clear()
    legacy = service.get(
        user_id="owner", connection_id=saved.connection_id, scope=PERSONAL
    )
    assert not legacy.source_available
    replayed = await service.upload(
        user_id="owner",
        content=b"%PDF-fixture",
        filename="test.pdf",
        media_type="application/pdf",
        scope=PERSONAL,
    )
    assert replayed.connection_id == saved.connection_id
    assert replayed.status == "review_ready"
    assert (
        service.source_bytes(
            user_id="owner", connection_id=saved.connection_id, scope=PERSONAL
        )
        == b"%PDF-fixture"
    )
    assert (
        service.store.get(user_id="owner", connection_id=saved.connection_id) == original
    )
    assert extractor.extract.await_count == 1


def test_luna_observation_shape_retains_all_five_and_projects_exact_transactions():
    import json
    from pathlib import Path

    from scripts.documents.benchmark import DIRECTIONS, row_score

    samples = json.loads(
        (
            Path(__file__).parents[1] / "document_extraction_fixtures/manifest.json"
        ).read_text()
    )["samples"]
    sample = next(row for row in samples if row["id"] == "statement-usd")
    # The captured Luna classification had an unknown scope for the opening amount.
    # Expected amounts/dates come from the existing fixture, never into a model prompt.
    observations = [
        {"page": 1, "row": 1, "evidence": "statement_period"},
        {
            "page": 1,
            "row": 2,
            "evidence": "balance",
            "amount": sample["excluded_balances"]["opening"],
            "currency": sample["excluded_balances"]["currency"],
            "balance_scope": None,
        },
    ]
    observations.extend(
        {
            "page": row["page"],
            "row": index + 3,
            "evidence": "transaction",
            "amount": row["amount"],
            "currency": row["currency"],
            "occurred_on": row["date"],
            "direction": DIRECTIONS[row["kind"]],
        }
        for index, row in enumerate(sample["expected_rows"])
    )
    observations.append(
        {
            "page": 1,
            "row": 5,
            "evidence": "balance",
            "amount": sample["excluded_balances"]["closing"],
            "currency": sample["excluded_balances"]["currency"],
            "balance_scope": "statement_closing",
        }
    )
    parsed = ExtractionResult.model_validate(
        {
            "readable": True,
            "complete": True,
            "pages_read": [1],
            "observations": observations,
        }
    )
    batch = batch_from_result(
        parsed, sample["sha256"], "owner", datetime.now(timezone.utc), sample["pages"]
    )
    assert len(batch.observations) == 5
    assert batch.observations[1].balance_scope is None
    score = row_score(sample, batch.candidates)
    assert score["exact_matches"] == len(sample["expected_rows"])
    assert score["missing_or_mismatched"] == 0
    assert any(
        issue.row == 2 and issue.code == "candidate_incompatible"
        for issue in batch.issues
    )


@pytest.mark.parametrize(
    "field,value", [("currency", "USD"), ("occurred_on", "2026-10-01")]
)
def test_receipt_conflicting_fields_remain_reviewable_not_confirmable(field, value):
    from argus.domain.ingestion.documents.models import ReceiptDetails

    from tests.ingestion.test_document_extraction import result

    parsed = result()
    observation = parsed.observations[0].model_copy(
        update={"occurred_on": datetime(2026, 9, 10).date()}
    )
    detail = ReceiptDetails.model_validate(
        {
            "payment_status": "paid",
            "currency": observation.currency,
            "occurred_on": observation.occurred_on,
            "total": observation.amount,
            field: value,
        }
    )
    parsed = parsed.model_copy(update={"observations": (observation,), "receipt": detail})
    batch = batch_from_result(parsed, "digest", "owner", datetime.now(timezone.utc), 1)
    assert batch.candidates == ()
    assert batch.observations == (observation,)
    assert batch.receipt == detail
    assert batch.issues[0].code == "receipt_purchase_ambiguous"


def _service() -> tuple[DocumentsService, IngestionHub, InMemoryDocumentStore]:
    repo = InMemoryConnectionRepository()
    store = InMemoryDocumentStore(repo)
    hub = IngestionHub(
        repo, box=None, sink=None, clock=lambda: datetime.now(timezone.utc)
    )
    return DocumentsService(hub, store, Mock()), hub, store


@pytest.mark.parametrize(
    ("given", "stored"),
    [
        ("state\x00ment\r\n.pdf", "statement.pdf"),
        ("receipt‮gpj.pdf", "receiptgpj.pdf"),
        ("\x1b[31m\x7f", "[31m"),
        ("\x00​\t", "document"),
        ("recibo-ñandú.pdf", "recibo-ñandú.pdf"),
    ],
)
@pytest.mark.asyncio
async def test_stored_filenames_keep_no_control_or_format_characters(given, stored):
    service, _, _ = _service()
    result = await service.upload(
        user_id="owner",
        content=b"%PDF-fixture",
        filename=given,
        media_type="application/pdf",
        scope=PERSONAL,
    )
    draft = service.get(
        user_id="owner", connection_id=result.connection_id, scope=PERSONAL
    )
    assert draft.filename == stored


@pytest.mark.asyncio
async def test_memory_sources_are_one_object_until_disconnect():
    service, hub, store = _service()
    first = await service.upload(
        user_id="owner",
        content=b"%PDF-fixture",
        filename="a.pdf",
        media_type="application/pdf",
        scope=PERSONAL,
    )
    await service.upload(
        user_id="owner",
        content=b"%PDF-fixture",
        filename="a.pdf",
        media_type="application/pdf",
        scope=PERSONAL,
    )
    assert list(store.objects.objects.values()) == [b"%PDF-fixture"]
    hub.disconnect(user_id="owner", connection_id=first.connection_id, scope=PERSONAL)
    assert store.objects.objects == {}
