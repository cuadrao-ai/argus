"""The four groups the founder named, plus a non-receipt: what the draft
holds after the read and the QR meet in the typed merge step. The QR wins
over the reader, every fact it gives names its source, the saved row asks
for review only of what the record still holds against the QR, an amount
from the QR is a draft value a person approves, and a non-receipt yields no
checks and no invented values."""

# ruff: noqa: F811  # the shared fixture is imported by name, as its siblings do
from __future__ import annotations

from datetime import date, datetime, timezone

from argus.domain.business.contracts.checks import DgiiQr, EcfCheck
from argus.domain.business.contracts.facts import BusinessResolution
from argus.domain.ingestion.documents.dgii_qr import parse_dgii_url
from argus.domain.ingestion.documents.extractor import batch_from_result
from argus.domain.ingestion.documents.models import DocumentDraft, ExtractionResult

from tests.dgii_qr_support import ENCF, RNC, TOTAL, URL
from tests.test_business_attachment_preparation import checked  # noqa: F401
from tests.test_business_multi_purchase import _prepared

NOW = datetime(2026, 10, 12, 20, 0, tzinfo=timezone.utc)
QR = parse_dgii_url(URL)
DATED = DgiiQr.model_validate(
    {**QR.model_dump(mode="json"), "fecha_emision": "2026-11-05"}
)


def _read(*, rows: list[dict], receipt: dict | None) -> ExtractionResult:
    return ExtractionResult.model_validate(
        dict(
            complete=True,
            readable=True,
            pages_read=[1],
            observations=rows,
            receipt={"payment_status": "paid", **receipt} if receipt else None,
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
    assert _states(resolution.ecf_checks)["qr_matches_read"] == ("verified", None)


def _match(verification):  # noqa: ANN001
    return next(c for c in verification.checks if c.name == "qr_matches_read")


def _pairs(check: EcfCheck) -> dict:
    return {name: pair.model_dump() for name, pair in check.read_vs_qr.items()}


def test_a_qr_and_printed_numbers_that_disagree_end_with_the_qr_and_no_review(
    checked, monkeypatch
):  # noqa: ANN001, F811
    read = _read(
        rows=[_row("33254.19")],
        receipt=dict(total="33254.19", currency="DOP", rnc="131111223", ecf=ENCF),
    )
    batch, resolution = _resolution(checked, monkeypatch, read, QR)
    facts = resolution.facts
    assert (facts.amount.value, facts.amount.origin, facts.amount.verified) == (
        TOTAL,
        "qr_decoded",
        False,
    )
    assert (facts.fiscal.rnc.value, facts.fiscal.rnc.origin) == (RNC, "qr_decoded")
    assert (facts.fiscal.ecf.value, facts.fiscal.ecf.origin) == (ENCF, "extracted")
    # The read on its own did differ from the QR, with both values typed.
    match = _match(batch.ecf_checks)
    assert (match.state, match.code, match.detail) == ("failed", "qr_differs", {})
    assert _pairs(match) == {
        "rnc": {"read": "131111223", "qr": RNC},
        "total": {"read": "33254.19", "qr": TOTAL},
    }
    # The record holds the QR's values, so its row has nothing left to review.
    saved = _match(resolution.ecf_checks)
    assert (saved.state, saved.code) == ("verified", None)
    assert _pairs(saved) == {"ecf": {"read": ENCF, "qr": ENCF}}
    # The typed pairs survive the JSON round trip the draft row takes.
    again = EcfCheck.model_validate(saved.model_dump(mode="json"))
    assert again.read_vs_qr["ecf"].qr == ENCF
    assert resolution.dgii_qr == QR


def test_the_qr_issue_date_replaces_a_date_the_reader_took_from_elsewhere(
    checked, monkeypatch
):  # noqa: ANN001, F811
    # The reader took the number's "válido hasta" date for the issue date.
    read = _read(
        rows=[{**_row(TOTAL), "occurred_on": "2027-12-31"}],
        receipt=dict(
            total=TOTAL, currency="DOP", rnc=RNC, ecf=ENCF, occurred_on="2027-12-31"
        ),
    )
    batch, resolution = _resolution(checked, monkeypatch, read, DATED)
    assert _pairs(_match(batch.ecf_checks)) == {
        "occurred_on": {"read": "2027-12-31", "qr": "2026-11-05"}
    }
    occurred_on = resolution.facts.occurred_on
    assert (occurred_on.value, occurred_on.origin) == (date(2026, 11, 5), "qr_decoded")
    saved = _match(resolution.ecf_checks)
    assert saved.state == "verified" and "occurred_on" not in saved.read_vs_qr


def test_a_sale_keeps_the_client_rnc_the_read_found(checked, monkeypatch):  # noqa: ANN001, F811
    from argus.domain.business.actions import mutations

    # The QR's issuer is the Business itself, so the read chose a Venta.
    monkeypatch.setattr(mutations, "business_tax_id", lambda tx: RNC)
    read = _read(
        rows=[{**_row(TOTAL), "direction": "inflow", "kind_hint": "income"}],
        receipt=dict(total=TOTAL, currency="DOP", rnc="101000001", ecf=ENCF),
    )
    _, resolution = _resolution(checked, monkeypatch, read, QR)
    rnc = resolution.facts.fiscal.rnc
    assert resolution.document_type == "venta"
    assert (rnc.value, rnc.origin) == ("101000001", "extracted")


def test_several_purchases_keep_the_amount_and_the_total_that_differs_is_reviewed(
    checked, monkeypatch
):  # noqa: ANN001, F811
    read = _read(
        rows=[_row("33000.00"), {**_row("254.19"), "row": 2}],
        receipt=dict(total="33254.19", currency="DOP", rnc=RNC, ecf=ENCF),
    )
    _, resolution = _resolution(checked, monkeypatch, read, QR)
    assert resolution.facts.amount.state == "unknown"
    saved = _match(resolution.ecf_checks)
    assert (saved.state, saved.code) == ("failed", "qr_differs")
    assert _pairs(saved) == {"total": {"read": "33254.19", "qr": TOTAL}}


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
