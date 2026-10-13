"""On real Postgres: a draft prepared from a receipt with a DGII QR keeps the
QR on the dossier, the facts it filled name their origin in the current
facts and in the history, and a person's later revision keeps both."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import uuid4

from argus.domain.business.contracts.actions import ReviewDraft
from argus.domain.business.contracts.facts import BusinessFactPatch
from argus.domain.ingestion.contract import Attachment
from argus.domain.ingestion.documents.dgii_qr import parse_dgii_url
from argus.domain.ingestion.documents.extractor import batch_from_result
from argus.domain.ingestion.documents.models import DocumentDraft, ExtractionResult
from psycopg.types.json import Jsonb

from tests import test_business_attachment_preparation_postgres as bridge
from tests.dgii_qr_support import ENCF, RNC, TOTAL, URL
from tests.test_business_spaces_migration_postgres import connection

actions = bridge.actions
users = bridge.users
pytestmark = bridge.pytestmark
QR = parse_dgii_url(URL)


def _saved_with_qr(actions):  # noqa: ANN001
    """A JPEG read whose receipt block printed no numbers, with the QR decoded."""

    service, context, grant = actions
    content = b"\xff\xd8\xff synthetic jpeg with qr"
    digest = sha256(content).hexdigest()
    now = datetime.now(timezone.utc)
    holder = str(uuid4())
    with service.authority.pool.connection() as db:
        cid = connection(db, context.owner_id, context.actor.space_id)
        draft = DocumentDraft(
            connection_id=cid,
            filename="factura.jpg",
            media_type="image/jpeg",
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
                        status="posted",
                        amount=None,
                        currency="DOP",
                        occurred_on="2026-10-09",
                        direction="outflow",
                        kind_hint="expense",
                        merchant="Hotel Brisa del Este SRL",
                        uncertain=["amount"],
                    )
                ],
                receipt=dict(currency="DOP", merchant="Hotel Brisa del Este SRL"),
            )
        )
        batch = batch_from_result(result, digest, cid, now, 1, dgii_qr=QR)
        attachment = Attachment(
            external_id=digest,
            sha256=digest,
            media_type="image/jpeg",
            size_bytes=len(content),
            filename="factura.jpg",
        )
        batch = batch.model_copy(
            update={
                "metadata": {"sha256": digest, "pages": 1, "media_type": "image/jpeg"},
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


def test_the_qr_and_its_filled_facts_survive_a_persons_revision(actions):  # noqa: ANN001
    saved = _saved_with_qr(actions)
    service, context, _, _, _, _ = saved
    bridge.bind(saved)
    result = bridge.finish(saved)
    assert result.outcome == "applied", result
    view = service.dossier(context, result.draft_id)
    assert view.dgii_qr == QR
    assert (
        view.facts.amount.value,
        view.facts.amount.origin,
        view.facts.amount.verified,
    ) == (
        TOTAL,
        "qr_decoded",
        False,
    )
    assert (view.facts.fiscal.rnc.value, view.facts.fiscal.rnc.origin) == (
        RNC,
        "qr_decoded",
    )
    assert (view.facts.fiscal.ecf.value, view.facts.fiscal.ecf.origin) == (
        ENCF,
        "qr_decoded",
    )
    assert view.approval_available is False  # a filled amount is a draft value
    names = {c.name: c.state for c in view.ecf_checks.checks}
    assert (names["qr_present"], names["qr_matches_read"]) == ("verified", "not_checked")
    # A person fills the rest: the QR and the origins stay, in the history too.
    from tests.test_business_multi_purchase_postgres import _account

    funding = _account(service, context)
    revised = service.review(
        context,
        result.draft_id,
        ReviewDraft(
            version=view.version,
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
    assert revised.outcome == "applied", revised
    after = service.dossier(context, result.draft_id)
    assert after.dgii_qr == QR
    assert after.facts.amount.origin == "qr_decoded"
    assert after.history[-1].after.fiscal.rnc.origin == "qr_decoded"
    assert after.history[0].after.fiscal.ecf.origin == "qr_decoded"
