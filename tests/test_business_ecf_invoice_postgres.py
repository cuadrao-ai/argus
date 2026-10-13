"""On real Postgres through the C0 bridge: a fake Dominican hotel e-CF, saved as
XML, as an email with the XML attached, or as a PDF render, prepares into one
draft whose amount is the DOP total paid (never the USD total), with the
merchant, the issue date and the e-NCF, RNC and ITBIS on the fiscal facts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest
from argus.domain.ingestion.contract import Attachment
from argus.domain.ingestion.documents.extractor import batch_from_result
from argus.domain.ingestion.documents.models import DocumentDraft, ExtractionResult
from argus.domain.ingestion.documents.preparation import prepare_document
from psycopg.types.json import Jsonb

from tests import test_business_attachment_preparation_postgres as bridge
from tests.test_business_spaces_migration_postgres import connection

actions = bridge.actions
users = bridge.users
pytestmark = bridge.pytestmark
FIXTURES = Path(__file__).parent / "document_extraction_fixtures"
ECF = "E320000001234"


def _saved_invoice(actions, filename: str, media_type: str):  # noqa: ANN001
    """The fixture stored as a document with the read the extractor returns for it."""

    service, context, grant = actions
    content = (FIXTURES / filename).read_bytes()
    digest = sha256(content).hexdigest()
    now = datetime.now(timezone.utc)
    holder = str(uuid4())
    with service.authority.pool.connection() as db:
        cid = connection(db, context.owner_id, context.actor.space_id)
        draft = DocumentDraft(
            connection_id=cid,
            filename=filename,
            media_type=media_type,
            sha256=digest,
            size_bytes=len(content),
            consent=True,
            created_at=now,
            updated_at=now,
        )
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
                        amount="33254.91",
                        currency="DOP",
                        occurred_on="2026-10-09",
                        direction="outflow",
                        kind_hint="expense",
                        merchant="Hotel Brisa del Este SRL",
                    )
                ],
                receipt=dict(
                    merchant="Hotel Brisa del Este SRL",
                    occurred_on="2026-10-09",
                    currency="DOP",
                    subtotal="25980.40",
                    tax="4676.47",
                    tip="2598.04",
                    total="33254.91",
                    rnc="131111222",
                    ecf=ECF,
                    itbis="4676.47",
                ),
            )
        )
        # The same preparation the extractor runs: the e-CF read once, from the
        # XML itself or from the XML part of the email, for the local checks.
        # A PDF render carries no e-CF and needs the PDF tools the matrix lacks.
        ecf = (
            prepare_document(content, media_type).ecf
            if media_type != "application/pdf"
            else None
        )
        batch = batch_from_result(
            result, digest, cid, now, 1, document_currency="DOP", ecf=ecf
        )
        attachment = Attachment(
            external_id=digest,
            sha256=digest,
            media_type=media_type,
            size_bytes=len(content),
            filename=filename,
        )
        batch = batch.model_copy(
            update={
                "metadata": {"sha256": digest, "document_currency": "DOP"},
                "candidates": tuple(
                    c.model_copy(update={"attachments": (attachment,)})
                    for c in batch.candidates
                ),
            }
        )
        db.execute(
            "insert into public.financial_document_extractions"
            " (connection_id,user_id,draft,source_bytes,batch) values (%s,%s,%s,%s,%s)",
            (
                cid,
                context.owner_id,
                Jsonb(draft.model_dump(mode="json")),
                content,
                Jsonb(batch.model_dump(mode="json")),
            ),
        )
        db.execute(
            "update public.financial_source_connections set lease_holder=%s,"
            " lease_until=%s where id=%s",
            (holder, now + timedelta(minutes=3), cid),
        )
    return service, context, grant, cid, holder, batch


@pytest.mark.parametrize(
    "filename,media_type",
    [
        ("hotel-ecf.xml", "text/xml"),
        ("hotel-ecf.eml", "message/rfc822"),
        ("hotel-ecf.pdf", "application/pdf"),
    ],
)
def test_a_hotel_ecf_becomes_one_draft_at_the_dop_total(actions, filename, media_type):  # noqa: ANN001
    saved = _saved_invoice(actions, filename, media_type)
    service, context, _, cid, _, _ = saved
    bridge.bind(saved)
    result = bridge.finish(saved)
    assert result.outcome == "applied", result
    view = service.dossier(context, result.draft_id)
    assert Decimal(view.facts.amount.value) == Decimal("33254.91")
    assert view.facts.currency.value == "DOP"
    assert view.facts.counterparty.value == "Hotel Brisa del Este SRL"
    assert view.facts.occurred_on.value.isoformat() == "2026-10-09"
    assert view.facts.kind.value == "expense"
    assert view.read_purchases == ()
    fiscal = view.facts.fiscal
    assert (fiscal.ecf.value, fiscal.rnc.value) == (ECF, "131111222")
    assert Decimal(fiscal.itbis.value) == Decimal("4676.47")
    assert fiscal.ncf.state == "unknown"
    assert [s.kind for s in view.sources] == ["attachment"]
    assert view.sources[0].media_type == media_type
    # What the file proved travels to the dossier; a PDF render proves nothing.
    if media_type == "application/pdf":
        assert view.ecf_checks is None
    else:
        states = {c.name: c.state for c in view.ecf_checks.checks}
        assert (states["totals_arithmetic"], states["signature_integrity"]) == (
            "verified",
            "not_checked",
        )
    with service.authority.pool.connection() as db:
        stored = db.execute(
            "select draft->>'media_type', batch->'metadata'->>'document_currency'"
            " from public.financial_document_extractions where connection_id=%s",
            (cid,),
        ).fetchone()
    assert stored == (media_type, "DOP")
