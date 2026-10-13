"""The four groups the founder named, plus a non-receipt: what the draft
holds after the read and the QR meet in the typed merge step. Nothing is
overwritten, every filled fact names its source, a mismatch fills nothing
and is a row to review, a filled amount is a draft value a person approves,
and a non-receipt yields no checks and no invented values."""

# ruff: noqa: F811  # the shared fixture is imported by name, as its siblings do
from __future__ import annotations

from datetime import datetime, timezone

from argus.domain.business.contracts.facts import BusinessResolution
from argus.domain.ingestion.documents.dgii_qr import parse_dgii_url
from argus.domain.ingestion.documents.extractor import batch_from_result
from argus.domain.ingestion.documents.models import DocumentDraft, ExtractionResult

from tests.dgii_qr_support import ENCF, RNC, TOTAL, URL
from tests.test_business_attachment_preparation import checked  # noqa: F401
from tests.test_business_multi_purchase import _prepared

NOW = datetime(2026, 10, 12, 20, 0, tzinfo=timezone.utc)
QR = parse_dgii_url(URL)


def _read(*, rows: list[dict], receipt: dict | None) -> ExtractionResult:
    return ExtractionResult.model_validate(
        dict(
            complete=True,
            readable=True,
            pages_read=[1],
            observations=rows,
            receipt=receipt,
        )
    )


def _row(amount: str | None) -> dict:
    return dict(
        page=1,
        row=1,
        evidence="transaction",
        status="posted",
        amount=amount,
        currency="DOP",
        occurred_on="2026-10-09",
        direction="outflow",
        kind_hint="expense",
        merchant="Hotel Brisa del Este SRL",
        uncertain=[] if amount else ["amount"],
    )


def _draft(checked):  # noqa: ANN001
    _, _, _, row = checked
    return DocumentDraft.model_validate(row["draft"])


def _resolution(checked, monkeypatch, result, qr):  # noqa: ANN001
    draft = _draft(checked)
    batch = batch_from_result(
        result, draft.sha256, draft.connection_id, NOW, 1, dgii_qr=qr
    )
    _, resolution, _ = _prepared(checked, monkeypatch, batch)
    return batch, resolution


def _states(verification):  # noqa: ANN001
    return (
        {c.name: (c.state, c.code) for c in verification.checks} if verification else None
    )


def test_printed_rnc_and_ncf_without_a_qr_stand_as_read(checked, monkeypatch):  # noqa: ANN001, F811
    read = _read(
        rows=[_row(TOTAL)],
        receipt=dict(total=TOTAL, currency="DOP", rnc=RNC, ncf="B0100000099"),
    )
    batch, resolution = _resolution(checked, monkeypatch, read, None)
    assert batch.dgii_qr is None and batch.ecf_checks is None
    facts = resolution.facts
    assert (facts.fiscal.rnc.value, facts.fiscal.rnc.origin) == (RNC, "extracted")
    assert (facts.fiscal.ncf.value, facts.fiscal.ecf.state) == ("B0100000099", "unknown")
    assert (facts.amount.value, facts.amount.origin) == (TOTAL, "extracted")
    assert resolution.dgii_qr is None


def test_a_qr_without_printed_numbers_fills_the_empty_facts_from_the_qr(
    checked, monkeypatch
):  # noqa: ANN001, F811
    read = _read(
        rows=[_row(None)],
        receipt=dict(currency="DOP", merchant="Hotel Brisa del Este SRL"),
    )
    batch, resolution = _resolution(checked, monkeypatch, read, QR)
    facts = resolution.facts
    assert (facts.amount.value, facts.amount.origin, facts.amount.verified) == (
        TOTAL,
        "qr_decoded",
        False,
    )
    assert (facts.fiscal.rnc.value, facts.fiscal.rnc.origin) == (RNC, "qr_decoded")
    assert (facts.fiscal.ecf.value, facts.fiscal.ecf.origin) == (ENCF, "qr_decoded")
    assert facts.counterparty.origin == "extracted"
    assert resolution.dgii_qr == QR
    assert _states(batch.ecf_checks) == {
        "qr_present": ("verified", None),
        "qr_matches_read": ("not_checked", "no_read"),
        "dgii_accepted": ("not_checked", "network_not_in_tier_a"),
    }
    assert batch.ecf_checks.encf == ENCF and batch.ecf_checks.tipo_ecf == "32"


def test_a_qr_and_printed_numbers_that_agree_keep_the_read_and_match(
    checked, monkeypatch
):  # noqa: ANN001, F811
    read = _read(
        rows=[_row(TOTAL)], receipt=dict(total=TOTAL, currency="DOP", rnc=RNC, ecf=ENCF)
    )
    batch, resolution = _resolution(checked, monkeypatch, read, QR)
    facts = resolution.facts
    assert (facts.amount.origin, facts.fiscal.rnc.origin, facts.fiscal.ecf.origin) == (
        "extracted",
        "extracted",
        "extracted",
    )
    assert _states(batch.ecf_checks)["qr_matches_read"] == ("verified", None)


def test_a_qr_and_printed_numbers_that_disagree_fill_nothing_and_ask_for_review(
    checked, monkeypatch
):  # noqa: ANN001, F811
    read = _read(
        rows=[_row("33254.19")],
        receipt=dict(total="33254.19", currency="DOP", rnc="131111223", ecf=ENCF),
    )
    batch, resolution = _resolution(checked, monkeypatch, read, QR)
    facts = resolution.facts
    # The read's values stand; nothing from the QR overwrote them.
    assert (facts.amount.value, facts.fiscal.rnc.value, facts.amount.origin) == (
        "33254.19",
        "131111223",
        "extracted",
    )
    match = next(c for c in batch.ecf_checks.checks if c.name == "qr_matches_read")
    assert (match.state, match.code) == ("failed", "qr_differs")
    assert match.detail == {
        "rnc": f"read=131111223 qr={RNC}",
        "total": f"read=33254.19 qr={TOTAL}",
    }
    assert resolution.dgii_qr == QR


def test_a_non_receipt_yields_no_checks_and_no_invented_values(checked, monkeypatch):  # noqa: ANN001, F811
    # Bank details: a read with nothing to record and no receipt block.
    read = ExtractionResult.model_validate(
        dict(
            complete=True,
            readable=True,
            pages_read=[1],
            observations=[],
            receipt=dict(merchant="Banco Ficticio"),
        )
    )
    batch, resolution = _resolution(checked, monkeypatch, read, None)
    assert batch.ecf_checks is None and batch.dgii_qr is None
    facts = resolution.facts
    assert (facts.amount.state, facts.fiscal.rnc.state, facts.fiscal.ecf.state) == (
        "unknown",
        "unknown",
        "unknown",
    )
    assert resolution.dgii_qr is None and resolution.ecf_checks is None
    assert (
        BusinessResolution.model_validate(resolution.model_dump(mode="json"))
        == resolution
    )
