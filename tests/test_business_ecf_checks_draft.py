"""A draft prepared from a DGII e-CF keeps what the file proved: the batch's
verification lands on the resolution, the dossier shows it, and a later
revision keeps it the way it keeps the read purchases."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from argus.domain.business.actions import mutations
from argus.domain.business.contracts.facts import BusinessResolution
from argus.domain.ingestion.documents.ecf_checks import read_ecf
from argus.domain.ingestion.documents.extractor import batch_from_result
from argus.domain.ingestion.documents.models import DocumentDraft, ExtractionResult

from tests.ecf_signing_support import RNC, signed_ecf
from tests.test_business_attachment_preparation import checked  # noqa: F401
from tests.test_business_multi_purchase import _prepared

NOW = datetime(2026, 10, 12, 20, 0, tzinfo=timezone.utc)


def _ecf_batch(draft: DocumentDraft, content: bytes):
    result = ExtractionResult.model_validate(
        dict(
            complete=True,
            readable=True,
            pages_read=[1],
            observations=[
                dict(
                    page=1,
                    row=1,
                    evidence="transaction",
                    status="posted",
                    amount="33254.91",
                    currency="DOP",
                    occurred_on="2026-10-09",
                    direction="outflow",
                    kind_hint="expense",
                    merchant="Hotel Brisa del Este SRL",
                )
            ],
            receipt=dict(
                total="33254.91",
                currency="DOP",
                rnc=RNC,
                ecf="E320000001234",
                occurred_on="2026-10-09",
                itbis="4676.47",
            ),
        )
    )
    return batch_from_result(
        result, draft.sha256, draft.connection_id, NOW, 1, ecf=read_ecf(content)
    )


def test_the_verification_lands_on_the_draft_and_survives_a_revision(
    checked,  # noqa: ANN001, F811
    monkeypatch,  # noqa: ANN001
) -> None:
    _, tx, binding, row = checked
    draft = DocumentDraft.model_validate(row["draft"])
    batch = _ecf_batch(draft, signed_ecf())
    assert batch.ecf_checks is not None and batch.ecf_checks.checked_at == NOW
    _, resolution, _ = _prepared(checked, monkeypatch, batch)
    assert resolution.ecf_checks == batch.ecf_checks
    states = {c.name: c.state for c in resolution.ecf_checks.checks}
    assert states["signature_integrity"] == "verified"
    assert states["read_matches_xml"] == "verified"
    assert states["dgii_accepted"] == "not_checked"
    # A person's later revision keeps the verification; it is not re-read.
    saved = tx.imports.put_event.call_args.args[0]
    mutations.save_revision(
        tx, saved, resolution.facts, resolution.facts, (uuid4(),), binding.actor, None
    )
    again = BusinessResolution.model_validate(
        tx.imports.put_event.call_args.args[0].resolution["business"]
    )
    assert again.ecf_checks == batch.ecf_checks


def test_a_source_that_is_not_an_ecf_carries_no_verification(
    checked,  # noqa: ANN001, F811
    monkeypatch,  # noqa: ANN001
) -> None:
    _, _, _, row = checked
    draft = DocumentDraft.model_validate(row["draft"])
    batch = _ecf_batch(draft, b"<Factura><MontoTotal>1</MontoTotal></Factura>")
    assert batch.ecf_checks is None
    _, resolution, _ = _prepared(checked, monkeypatch, batch)
    assert resolution.ecf_checks is None
