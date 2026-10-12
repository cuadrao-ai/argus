"""On real Postgres through the C0 bridge: the second receipt whose read
merchant, date, amount and currency equal a prepared one is marked as its
possible duplicate when it is prepared; the first stays untouched, also when
its own preparation is retried; the dossier blocks approval."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import uuid4

from argus.domain.ingestion.contract import Attachment
from argus.domain.ingestion.documents.extractor import batch_from_result
from argus.domain.ingestion.documents.models import DocumentDraft, ExtractionResult
from psycopg.types.json import Jsonb

from tests import test_business_attachment_preparation_postgres as shared
from tests.test_business_spaces_migration_postgres import connection

actions = shared.actions
users = shared.users
prepared = shared.prepared
pytestmark = shared.pytestmark


def _another_receipt(prepared, content: bytes, merchant: str = "Synthetic shop"):  # noqa: ANN001
    """A second document with other bytes whose read gives the same facts."""

    service, context, grant, _, _, _ = prepared
    digest = sha256(content).hexdigest()
    now = datetime.now(timezone.utc)
    holder = str(uuid4())
    with service.authority.pool.connection() as db:
        cid = connection(db, context.owner_id, context.actor.space_id)
        draft = DocumentDraft(
            connection_id=cid,
            filename="otra-foto.txt",
            media_type="text/plain",
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
                        amount="250.50",
                        currency="DOP",
                        direction="outflow",
                        kind_hint="expense",
                        merchant=merchant,
                    )
                ],
                receipt=dict(total="250.50", currency="DOP"),
            )
        )
        batch = batch_from_result(result, digest, cid, now, 1)
        attachment = Attachment(
            external_id=digest,
            sha256=digest,
            media_type=draft.media_type,
            size_bytes=len(content),
            filename=draft.filename,
        )
        batch = batch.model_copy(
            update={
                "metadata": {"sha256": digest},
                "candidates": tuple(
                    c.model_copy(update={"attachments": (attachment,)})
                    for c in batch.candidates
                ),
            }
        )
        db.execute(
            "insert into public.financial_document_extractions (connection_id,user_id,draft,source_bytes,batch) values (%s,%s,%s,%s,%s)",
            (
                cid,
                context.owner_id,
                Jsonb(draft.model_dump(mode="json")),
                content,
                Jsonb(batch.model_dump(mode="json")),
            ),
        )
        db.execute(
            "update public.financial_source_connections set lease_holder=%s, lease_until=%s where id=%s",
            (holder, now + timedelta(minutes=3), cid),
        )
    return service, context, grant, cid, holder, batch


def _event(service, event_id):  # noqa: ANN001
    with service.authority.pool.connection() as db:
        return db.execute(
            "select attention, possible_duplicates::text[], attention_detail->>'basis' from public.financial_import_events where id=%s",
            (event_id,),
        ).fetchone()


def test_the_second_receipt_with_the_same_read_is_marked_and_the_first_stays_clean(
    prepared,
) -> None:  # noqa: ANN001
    service, context, _, _, _, _ = prepared
    shared.bind(prepared)
    first = shared.finish(prepared)
    assert first.outcome == "applied", first
    second_receipt = _another_receipt(prepared, b"the same receipt, photographed again")
    shared.bind(second_receipt)
    second = shared.finish(second_receipt)
    assert second.outcome == "applied", second
    assert _event(service, second.draft_id) == (
        "possible_duplicate",
        [str(first.draft_id)],
        "read_facts",
    )
    assert _event(service, first.draft_id) == (None, [], None)
    view = service.dossier(context, second.draft_id)
    assert "possible_duplicate" in [b.code for b in view.blockers]
    assert view.approval_available is False
    assert view.facts.amount.value is not None
    assert "possible_duplicate" not in [
        b.code for b in service.dossier(context, first.draft_id).blockers
    ]
    # A retried preparation of the original replays its receipt and never marks it.
    again = shared.finish(prepared)
    assert again.outcome in ("applied", "replayed")
    assert _event(service, first.draft_id) == (None, [], None)
    # A different merchant with the same amount and date is not a repeat.
    third_receipt = _another_receipt(
        prepared, b"another shop, same amount", merchant="Otra tienda"
    )
    shared.bind(third_receipt)
    third = shared.finish(third_receipt)
    assert third.outcome == "applied", third
    assert _event(service, third.draft_id) == (None, [], None)
