from datetime import datetime, timezone
from hashlib import sha256
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from argus.domain.ingestion.connections import InMemoryConnectionRepository
from argus.domain.ingestion.documents import extractor
from argus.domain.ingestion.documents.config import DocumentExtractionSettings
from argus.domain.ingestion.documents.models import (
    DocumentDraft,
    ExtractionResult,
    ReceiptDetails,
)
from argus.domain.ingestion.documents.preparation import PreparedDocument
from argus.domain.ingestion.documents.store import InMemoryDocumentStore
from argus.domain.owner_scope import PERSONAL
from pydantic import ValidationError

FISCAL_FIELDS = ("rnc", "ncf", "ecf", "itbis")
SYNTHETIC_FISCAL = {
    "rnc": "SYNTHETIC-RNC-A",
    "ncf": "SYNTHETIC-NCF-A",
    "ecf": "SYNTHETIC-ECF-A",
    "itbis": "18.00",
}


def receipt_result(**fiscal: str | None) -> ExtractionResult:
    return ExtractionResult.model_validate(
        {
            "complete": True,
            "readable": True,
            "pages_read": [1],
            "observations": [
                {
                    "page": 1,
                    "row": 1,
                    "evidence": "transaction",
                    "amount": "118",
                    "currency": "DOP",
                    "direction": "outflow",
                    "occurred_on": "2026-10-10",
                }
            ],
            "receipt": {"total": "118", "tax": "18.00", **fiscal},
        }
    )


def test_fiscal_schema_is_nullable_bounded_unverified_evidence() -> None:
    schema = ExtractionResult.model_json_schema()["$defs"]["ReceiptDetails"]
    for name in FISCAL_FIELDS:
        field = schema["properties"][name]
        assert name not in schema.get("required", [])
        assert {branch["type"] for branch in field["anyOf"]} == {"string", "null"}
        assert "unverified" in field["description"].lower()
        assert "source" in field["description"].lower()
        assert any(branch.get("maxLength") for branch in field["anyOf"])
    with pytest.raises(ValidationError):
        ReceiptDetails(rnc="x" * 81)


@pytest.mark.parametrize(
    "claims",
    [
        {"verified": True},
        {"source_ids": [str(uuid4())]},
        {"rnc": {"value": "RNC", "verified": True}},
    ],
)
def test_extractor_cannot_supply_fiscal_authority_or_verification(claims: dict) -> None:
    with pytest.raises(ValidationError):
        ReceiptDetails.model_validate(claims)


@pytest.mark.parametrize("explicit", [False, True])
def test_absent_fiscal_values_never_inherit_tax_or_other_defaults(explicit: bool) -> None:
    receipt = receipt_result(
        **dict.fromkeys(FISCAL_FIELDS, None) if explicit else {}
    ).receipt
    source_id = uuid4()
    projected = extractor.fiscal_facts_from_receipt(receipt, source_id=source_id)
    for name in FISCAL_FIELDS:
        fact = getattr(projected, name)
        assert fact.state == "unknown" and fact.value is None
        assert fact.origin == "extracted" and fact.verified is False
        assert fact.source_ids == (source_id,)
    assert receipt.tax == "18.00" and receipt.itbis is None


def test_fiscal_projection_uses_only_original_extracted_evidence_and_supplied_source() -> (
    None
):
    receipt = receipt_result(**SYNTHETIC_FISCAL).receipt
    original = receipt.model_dump_json()
    source_id = uuid4()
    projected = extractor.fiscal_facts_from_receipt(receipt, source_id=source_id)
    for name in FISCAL_FIELDS:
        fact = getattr(projected, name)
        assert fact.value == ("18" if name == "itbis" else SYNTHETIC_FISCAL[name])
        assert fact.origin == "extracted" and fact.verified is False
        assert fact.source_ids == (source_id,)
    assert receipt.model_dump_json() == original
    assert receipt.itbis == "18.00"
    assert extractor.fiscal_facts_from_receipt(receipt, source_id=source_id) == projected


@pytest.mark.parametrize("raw,expected", [("0", "0"), ("0.00", "0"), ("18.00", "18")])
def test_itbis_projection_uses_existing_c0_amount_semantics(
    raw: str, expected: str
) -> None:
    receipt = ReceiptDetails(itbis=raw)
    projected = extractor.fiscal_facts_from_receipt(receipt, source_id=uuid4())
    assert projected.itbis.value == expected
    assert receipt.itbis == raw


@pytest.mark.parametrize("raw", ["18%", "1,800.00", "18 or 20", "-18", ""])
def test_incompatible_itbis_becomes_unknown_and_stays_raw_in_the_receipt(
    raw: str,
) -> None:
    receipt = ReceiptDetails(rnc="SYNTHETIC-RNC-A", itbis=raw)
    source_id = uuid4()
    projected = extractor.fiscal_facts_from_receipt(receipt, source_id=source_id)
    assert projected.itbis.state == "unknown" and projected.itbis.value is None
    assert projected.itbis.origin == "extracted"
    assert projected.itbis.source_ids == (source_id,)
    assert projected.rnc.state == "known" and projected.rnc.value == "SYNTHETIC-RNC-A"
    assert receipt.itbis == raw


def test_projection_rejects_missing_or_malformed_server_source() -> None:
    for source_id in (None, "not-an-attachment-source"):
        with pytest.raises(ValidationError):
            extractor.fiscal_facts_from_receipt(ReceiptDetails(), source_id=source_id)


@pytest.mark.asyncio
async def test_scripted_extraction_preserves_fiscal_evidence_and_personal_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed = receipt_result(**SYNTHETIC_FISCAL)
    invoke = AsyncMock(return_value=parsed)
    content = b"Synthetic fiscal receipt: RNC-A, NCF-A, e-CF-A, ITBIS amount 18.00"
    monkeypatch.setattr(extractor, "resolve_openrouter_model", lambda **_: "test/vision")
    monkeypatch.setattr(extractor, "resolve_openrouter_api_key", lambda _: "offline")
    monkeypatch.setattr(extractor, "invoke_openrouter_json_schema", invoke)
    monkeypatch.setattr(
        extractor,
        "prepare_document",
        lambda *_: PreparedDocument(
            pages=1, images=(b"synthetic",), text=content.decode()
        ),
    )
    now = datetime.now(timezone.utc)
    batch = await extractor.DocumentExtractor(
        DocumentExtractionSettings(enabled=True)
    ).extract(content, "synthetic.png", "image/png", "connection", now)
    assert batch.receipt == parsed.receipt
    assert batch.metadata["sha256"] == sha256(content).hexdigest()
    candidate = batch.candidates[0]
    plain = extractor.batch_from_result(
        receipt_result(), sha256(content).hexdigest(), "connection", now, 1
    ).candidates[0]
    assert candidate.model_dump(exclude={"attachments"}) == plain.model_dump(
        exclude={"attachments"}
    )
    assert candidate.attachments[0].sha256 == sha256(content).hexdigest()
    assert not batch.issues
    assert invoke.await_args.kwargs["schema_model"] is ExtractionResult
    prompt = invoke.await_args.kwargs["messages"][0]["content"]
    for label in ("RNC", "NCF", "e-CF", "ITBIS"):
        assert label in prompt


@pytest.mark.parametrize("conflicting", [False, True])
def test_original_receipt_and_fiscal_evidence_survive_replay_unchanged(
    conflicting: bool,
) -> None:
    now = datetime.now(timezone.utc)
    content = (
        b"Synthetic receipt with conflicting RNC-A and RNC-B"
        if conflicting
        else b"Synthetic fiscal receipt"
    )
    fiscal = dict.fromkeys(FISCAL_FIELDS, None) if conflicting else SYNTHETIC_FISCAL
    batch = extractor.batch_from_result(
        receipt_result(**fiscal), sha256(content).hexdigest(), "connection", now, 1
    )
    repo = InMemoryConnectionRepository()
    repo.create(
        user_id="owner",
        source="statement",
        external_ref=sha256(content).hexdigest(),
        label=None,
        now=now,
        connection_id="connection",
        scope=PERSONAL,
    )
    store = InMemoryDocumentStore(repo)
    draft = DocumentDraft(
        connection_id="connection",
        filename="synthetic.png",
        media_type="image/png",
        sha256=sha256(content).hexdigest(),
        size_bytes=len(content),
        created_at=now,
        updated_at=now,
    )
    assert store.capture(user_id="owner", draft=draft, content=content)
    assert repo.lease(connection_id="connection", holder="holder", now=now)
    assert store.save(
        user_id="owner", connection_id="connection", holder="holder", now=now, batch=batch
    )
    altered = batch.model_copy(update={"receipt": ReceiptDetails(rnc="DIFFERENT")})
    assert store.save(
        user_id="owner",
        connection_id="connection",
        holder="holder",
        now=now,
        batch=altered,
    )
    assert store.source(user_id="owner", connection_id="connection") == content
    assert store.get(user_id="owner", connection_id="connection") == batch
