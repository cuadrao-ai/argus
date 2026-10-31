import unicodedata
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
    "rnc": "SYNTHETIC-RNC-1",
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
            "receipt": {
                "payment_status": "paid",
                "total": "118",
                "tax": "18.00",
                **fiscal,
            },
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
    receipt = ReceiptDetails(rnc="SYNTHETIC-RNC-1", itbis=raw)
    source_id = uuid4()
    projected = extractor.fiscal_facts_from_receipt(receipt, source_id=source_id)
    assert projected.itbis.state == "unknown" and projected.itbis.value is None
    assert projected.itbis.origin == "extracted"
    assert projected.itbis.source_ids == (source_id,)
    assert projected.rnc.state == "known" and projected.rnc.value == "SYNTHETIC-RNC-1"
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


class TestPrintedIdentifierSplit:
    @pytest.mark.parametrize(
        ("name", "read", "identifier"),
        [
            pytest.param(
                "rnc", "RNC 1-23-45678-9 (ficticio)", "1-23-45678-9", id="rnc-tail"
            ),
            pytest.param("rnc", "RNC: 101987654", "101987654", id="rnc-label"),
            pytest.param("rnc", "001-1234567-8 cedula", "001-1234567-8", id="cedula"),
            pytest.param("rnc", "1-23-45678-9", "1-23-45678-9", id="rnc-clean"),
            pytest.param("rnc", "SYNTHETIC-RNC-1", "SYNTHETIC-RNC-1", id="rnc-none"),
            pytest.param(
                "ncf", "NCF B0100000987 (ficticio)", "B0100000987", id="ncf-tail"
            ),
            pytest.param("ncf", "NCF: B0100000987", "B0100000987", id="ncf-label"),
            pytest.param("ncf", "B0100000987", "B0100000987", id="ncf-clean"),
            pytest.param("ncf", "B01000008", "B01000008", id="ncf-malformed"),
            pytest.param(
                "ncf", "NCF B01000008 (ficticio)", "B01000008", id="ncf-malformed-tail"
            ),
            pytest.param("ncf", "sin comprobante", "sin comprobante", id="ncf-none"),
        ],
    )
    def test_fact_holds_identifier_and_receipt_keeps_full_read(
        self, name: str, read: str, identifier: str
    ) -> None:
        receipt = ReceiptDetails(**{name: read})
        projected = extractor.fiscal_facts_from_receipt(receipt, source_id=uuid4())
        assert getattr(projected, name).value == identifier
        assert getattr(receipt, name) == read

    def test_ncf_characters_are_never_added_removed_or_changed(self) -> None:
        for read in ("B01000008", "b0100000987", "E3100000000012345", "B01-0000098"):
            receipt = ReceiptDetails(ncf=f"NCF: {read} (ficticio)")
            value = extractor.fiscal_facts_from_receipt(
                receipt, source_id=uuid4()
            ).ncf.value
            assert value == f"NCF: {read} (ficticio)" or value == read

    def test_split_is_idempotent(self) -> None:
        source_id = uuid4()
        first = extractor.fiscal_facts_from_receipt(
            ReceiptDetails(
                rnc="RNC 1-23-45678-9 (ficticio)", ncf="NCF B01000008 (ficticio)"
            ),
            source_id=source_id,
        )
        second = extractor.fiscal_facts_from_receipt(
            ReceiptDetails(rnc=first.rnc.value, ncf=first.ncf.value), source_id=source_id
        )
        assert second == first

    def test_cleanup_on_use_reads_the_split_fact(self) -> None:
        from argus.domain.business.fiscal_identity import identity_digits, normalized_ncf

        projected = extractor.fiscal_facts_from_receipt(
            ReceiptDetails(
                rnc="RNC 1-23-45678-9 (ficticio)", ncf="NCF B0100000987 (ficticio)"
            ),
            source_id=uuid4(),
        )
        assert identity_digits(projected.rnc.value) == "123456789"
        assert normalized_ncf(projected.ncf.value) == "B0100000987"

    @pytest.mark.parametrize(
        ("name", "read", "expected"),
        [
            pytest.param(
                "rnc", "RNC 1--131000002", None, id="rnc-prefix-repeated-hyphens"
            ),
            pytest.param(
                "rnc", "RNC 131000002--1", None, id="rnc-suffix-repeated-hyphens"
            ),
            pytest.param(
                "rnc", "RNC 1 - 131000002", None, id="rnc-prefix-mixed-separators"
            ),
            pytest.param(
                "rnc", "RNC 1 131000002", None, id="rnc-prefix-digit-after-space"
            ),
            pytest.param(
                "rnc", "RNC 131000002 9", None, id="rnc-suffix-digit-after-space"
            ),
            pytest.param(
                "rnc", "RNC 131000002\uff19", None, id="rnc-suffix-fullwidth-digit"
            ),
            pytest.param(
                "rnc", "RNC \uff19131000002", None, id="rnc-prefix-fullwidth-digit"
            ),
            pytest.param(
                "rnc", "RNC 131000002-\u0669", None, id="rnc-suffix-arabic-indic-digit"
            ),
            pytest.param(
                "rnc", "RNC \u0669--131000002", None, id="rnc-prefix-arabic-indic-digit"
            ),
            pytest.param("rnc", "RNC 1\u00a0131000002", None, id="rnc-prefix-nbsp"),
            pytest.param("rnc", "RNC 131000002\u00a09", None, id="rnc-suffix-nbsp"),
            pytest.param("rnc", "RNC 1\u2011131000002", None, id="rnc-prefix-nb-hyphen"),
            pytest.param("rnc", "RNC 131000002\u20119", None, id="rnc-suffix-nb-hyphen"),
            pytest.param("rnc", "RNC 131000002\u00f1", None, id="rnc-suffix-letter"),
            pytest.param(
                "rnc", "RNC 131000002\u0301", None, id="rnc-suffix-combining-mark"
            ),
            pytest.param(
                "ncf", "NCF B0100000987\uff19", None, id="ncf-suffix-fullwidth-digit"
            ),
            pytest.param(
                "ncf", "NCF \uff21B0100000987", None, id="ncf-prefix-fullwidth-letter"
            ),
            pytest.param(
                "ncf", "NCF \uff19B0100000987", None, id="ncf-prefix-fullwidth-digit"
            ),
            pytest.param(
                "ncf", "NCF B0100000987\u00e9", None, id="ncf-suffix-accented-letter"
            ),
            pytest.param(
                "ncf", "NCF \u00f1B0100000987", None, id="ncf-prefix-accented-letter"
            ),
            pytest.param(
                "ncf", "NCF n\u0303B0100000987", None, id="ncf-prefix-decomposed-letter"
            ),
            pytest.param(
                "ncf",
                "NCF B0100000987\u0301\uff19",
                None,
                id="ncf-suffix-mark-then-digit",
            ),
            pytest.param(
                "ncf", "NCF B0100000987\u00a09", None, id="ncf-suffix-nbsp-digit"
            ),
            pytest.param(
                "ncf", "NCF 9\u2011B0100000987", None, id="ncf-prefix-nb-hyphen"
            ),
            pytest.param("rnc", "RNC 1\u200b131000002", None, id="rnc-prefix-zwsp"),
            pytest.param("rnc", "RNC 1\t131000002", None, id="rnc-prefix-tab"),
            pytest.param(
                "ncf", "NCF B0100000987\u00ad9", None, id="ncf-suffix-soft-hyphen"
            ),
            pytest.param("ncf", "NCF B0100000987\u200d9", None, id="ncf-suffix-zwj"),
            pytest.param(
                "ncf", "NCF B0100000987 \u200b9", None, id="ncf-suffix-space-zwsp"
            ),
            pytest.param("rnc", "RNC 1\u2212131000002", None, id="rnc-prefix-minus"),
            pytest.param(
                "ncf",
                "NCF B0100000987\u200d\uff19",
                None,
                id="ncf-suffix-zwj-fullwidth-digit",
            ),
            pytest.param(
                "rnc",
                "RNC 1-23-45678-9 (ficticio)",
                "1-23-45678-9",
                id="rnc-formatted-note",
            ),
            pytest.param("rnc", "RNC 131000002", "131000002", id="rnc-plain"),
            pytest.param("rnc", "RNC: 1-23-45678-9", "1-23-45678-9", id="rnc-colon"),
            pytest.param("rnc", "RNC\u00a0131000002", "131000002", id="rnc-nbsp-label"),
            pytest.param(
                "rnc", "131000002\u00a0nota", "131000002", id="rnc-nbsp-note"
            ),
            pytest.param(
                "ncf", "NCF\u2009B0100000987\u3000(ficticio)", "B0100000987",
                id="ncf-thin-and-ideographic-space",
            ),
            pytest.param("rnc", "RNC 131000002\u00a0", "131000002", id="rnc-nbsp-end"),
            pytest.param(
                "rnc", "RNC 131000002\u00a0\u00a0x", None, id="rnc-two-nbsp"
            ),
            pytest.param(
                "rnc", "RNC 131000002\u00a0-x", None, id="rnc-nbsp-then-dash"
            ),
            pytest.param("rnc", "RNC 131000002\u2028x", None, id="rnc-line-separator"),
            pytest.param(
                "rnc", "RNC 131000002\u2029x", None, id="rnc-paragraph-separator"
            ),
            pytest.param("ncf", "NCF B0100000987", "B0100000987", id="ncf-plain"),
            pytest.param(
                "ncf", "ncf b0100000987 (ficticio)", "b0100000987", id="ncf-lowercase"
            ),
            pytest.param("ncf", "e-CF E310000000001", "E310000000001", id="ecf"),
        ],
    )
    def test_a_read_that_runs_on_past_the_identifier_stays_whole(
        self, name: str, read: str, expected: str | None
    ) -> None:
        receipt = ReceiptDetails(**{name: read})
        projected = extractor.fiscal_facts_from_receipt(receipt, source_id=uuid4())
        assert getattr(projected, name).value == (expected or read)
        assert getattr(receipt, name) == read

    def test_boundary_reads_kept_whole_stay_rejected_by_strict_cleanup(self) -> None:
        from argus.domain.business.fiscal_identity import identity_digits, normalized_ncf

        assert identity_digits("RNC 1--131000002") is None
        assert identity_digits("RNC 131000002\uff19") is None
        assert normalized_ncf("NCF B0100000987\uff19") is None

    def test_first_cleanly_bounded_candidate_still_wins(self) -> None:
        projected = extractor.fiscal_facts_from_receipt(
            ReceiptDetails(
                rnc="RNC 101987654 / 131000002", ncf="NCF B0100000987 o B0100000988"
            ),
            source_id=uuid4(),
        )
        assert projected.rnc.value == "101987654"
        assert projected.ncf.value == "B0100000987"


_INVISIBLE = [
    chr(code)
    for code in range(0x10000)
    if unicodedata.category(chr(code)) in ("Cf", "Cc")
]


@pytest.mark.parametrize(
    ("name", "token"), [("rnc", "131000002"), ("ncf", "B0100000987")]
)
def test_any_format_or_control_character_at_an_edge_keeps_the_read_whole(
    name: str, token: str
) -> None:
    source_id = uuid4()
    for char in _INVISIBLE:
        for read in (
            f"{char}{token}",
            f"{token}{char}",
            f"{char}{token} x",
            f"{token} {char}",
            f"x {char}{token}",
        ):
            receipt = ReceiptDetails(**{name: read})
            projected = extractor.fiscal_facts_from_receipt(receipt, source_id=source_id)
            assert getattr(projected, name).value == read, repr(read)
            assert getattr(receipt, name) == read


_SPACES = frozenset(
    chr(code)
    for code in range(0x110000)
    if unicodedata.category(chr(code)) == "Zs"
)


@pytest.mark.parametrize(
    ("name", "token"), [("rnc", "131000002"), ("ncf", "B0100000987")]
)
def test_only_edge_punctuation_or_one_space_may_touch_an_identifier(
    name: str, token: str
) -> None:
    """Every code point beside the token: the read splits only for the ASCII
    edge punctuation or a Unicode Zs space; everything else keeps it whole."""

    from argus.domain.business.fiscal_identity import (
        EDGE_PUNCTUATION,
        printed_ncf,
        printed_rnc,
    )

    printed = printed_rnc if name == "rnc" else printed_ncf
    permitted = EDGE_PUNCTUATION | _SPACES
    for code in range(0x110000):
        char = chr(code)
        if char.isascii() and char.isalnum():
            continue
        clean = char in permitted
        for read in (f"{char}{token}", f"{token}{char}"):
            assert printed(read) == (token if clean else read), repr(read)
        if char in _SPACES:
            assert printed(f"x{char}{token}{char}nota") == token, repr(char)
            assert printed(f"{token}{char}9") == f"{token}{char}9", repr(char)
            assert printed(f"1{char}{token}") == f"1{char}{token}", repr(char)
