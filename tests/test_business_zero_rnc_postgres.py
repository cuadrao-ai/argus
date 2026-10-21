"""On real Postgres: a receipt read whose RNC is all zeros is prepared with an
unknown RNC (the page reads "RNC desconocido"), and a draft saved before the
rule, still holding the zeros, opens with an unknown RNC instead of failing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import uuid4

from argus.domain.ingestion.contract import Attachment
from argus.domain.ingestion.documents.extractor import batch_from_result
from argus.domain.ingestion.documents.models import DocumentDraft, ExtractionResult
from psycopg.types.json import Jsonb

from tests import test_business_attachment_preparation_postgres as bridge
from tests.test_business_spaces_migration_postgres import connection

actions = bridge.actions
users = bridge.users
pytestmark = bridge.pytestmark


def _saved_with_rnc(actions, printed: str):  # noqa: ANN001, ANN202
    """A JPEG read whose receipt block printed this RNC and an NCF."""

    service, context, grant = actions
    content = f"synthetic receipt rnc {printed}".encode()
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
                        amount="850.00",
                        currency="DOP",
                        occurred_on="2026-10-09",
                        direction="outflow",
                        kind_hint="expense",
                        merchant="Ferretería Prueba",
                    )
                ],
                receipt=dict(
                    payment_status="paid",
                    currency="DOP",
                    merchant="Ferretería Prueba",
                    total="850.00",
                    rnc=printed,
                    ncf="B0100000099",
                ),
            )
        )
        batch = batch_from_result(result, digest, cid, now, 1)
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


def _prepared(actions, printed: str):  # noqa: ANN001, ANN202
    saved = _saved_with_rnc(actions, printed)
    bridge.bind(saved)
    result = bridge.finish(saved)
    assert result.outcome == "applied", result
    return saved[0], saved[1], result.draft_id


def test_a_read_rnc_of_zeros_is_prepared_unknown_and_a_real_one_is_kept(actions):  # noqa: ANN001
    service, context, draft_id = _prepared(actions, "000-00000-0")
    fiscal = service.dossier(context, draft_id).facts.fiscal
    assert (fiscal.rnc.state, fiscal.rnc.value, fiscal.rnc.origin) == (
        "unknown",
        None,
        "extracted",
    )
    assert fiscal.rnc.source_ids
    assert (fiscal.ncf.state, fiscal.ncf.value) == ("known", "B0100000099")

    service, context, draft_id = _prepared(actions, "131999888")
    fiscal = service.dossier(context, draft_id).facts.fiscal
    assert (fiscal.rnc.state, fiscal.rnc.value) == ("known", "131999888")


def test_a_draft_saved_with_zeros_before_the_rule_opens_with_an_unknown_rnc(actions):  # noqa: ANN001
    service, context, draft_id = _prepared(actions, "131999888")
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.financial_import_events set resolution=jsonb_set("
            "resolution,'{business,facts,fiscal,rnc,value}','\"000000000\"')"
            " where id=%s",
            (draft_id,),
        )
    view = service.dossier(context, draft_id)
    assert (view.facts.fiscal.rnc.state, view.facts.fiscal.rnc.value) == (
        "unknown",
        None,
    )
