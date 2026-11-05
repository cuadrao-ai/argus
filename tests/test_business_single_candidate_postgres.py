"""On real Postgres through the C0 bridge: a clean read with exactly one
transaction candidate always becomes one draft at the read total, whatever
kind the observation carried and however complete the receipt block is. The
receipt is then linked to that draft, so the inbox never says "no purchase
found" for it."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from uuid import UUID, uuid4

import pytest
from argus.domain.business.actions.receipts import draft_for_receipt
from argus.domain.business.transactions import transaction
from argus.domain.ingestion.contract import Attachment
from argus.domain.ingestion.documents.extractor import batch_from_result
from argus.domain.ingestion.documents.models import DocumentDraft, ExtractionResult
from psycopg.types.json import Jsonb

from tests import test_business_attachment_preparation_postgres as bridge
from tests.test_business_spaces_migration_postgres import connection

actions = bridge.actions
users = bridge.users
pytestmark = bridge.pytestmark

RECEIPT = dict(
    payment_status="paid",
    suggested_category="lodging",
    merchant="Hotel Brisa del Este SRL",
    occurred_on="2026-10-09",
    currency="DOP",
    items=[
        {"id": "1", "description": "Room Charge", "total": "24620.40"},
        {"id": "2", "description": "Minibar", "total": "1360.00"},
    ],
    subtotal="25980.40",
    tax="4676.47",
    service=None,
    tip="2598.04",
    total="33254.91",
    rnc="131111222",
    ncf=None,
    ecf="E320000001234",
    itbis="4676.47",
)


def _saved(actions, kind_hint: str, direction: str = "outflow"):  # noqa: ANN001
    """A PNG screenshot read as one dated transaction row with a full receipt block."""

    service, context, grant = actions
    content = b"\x89PNG synthetic screenshot " + kind_hint.encode()
    digest = sha256(content).hexdigest()
    now = datetime.now(timezone.utc)
    holder = str(uuid4())
    with service.authority.pool.connection() as db:
        cid = connection(db, context.owner_id, context.actor.space_id)
        draft = DocumentDraft(
            connection_id=cid,
            filename="image.png",
            media_type="image/png",
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
                        amount="33254.91",
                        currency="DOP",
                        occurred_on="2026-10-09",
                        direction=direction,
                        kind_hint=kind_hint,
                        merchant="Hotel Brisa del Este SRL",
                    )
                ],
                receipt=RECEIPT,
            )
        )
        batch = batch_from_result(result, digest, cid, now, 1)
        assert len(batch.candidates) == 1 and batch.issues == ()
        attachment = Attachment(
            external_id=digest,
            sha256=digest,
            media_type="image/png",
            size_bytes=len(content),
            filename="image.png",
        )
        batch = batch.model_copy(
            update={
                "metadata": {"sha256": digest, "pages": 1, "media_type": "image/png"},
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
    "kind_hint,direction",
    [("expense", "outflow"), ("unknown", "outflow"), ("unknown", "unknown")],
)
def test_one_clean_candidate_always_becomes_one_draft_at_the_total(
    actions, kind_hint, direction
):  # noqa: ANN001
    saved = _saved(actions, kind_hint, direction)
    service, context, _, cid, _, _ = saved
    bridge.bind(saved)
    result = bridge.finish(saved)
    assert result.outcome == "applied", result
    view = service.dossier(context, result.draft_id)
    assert Decimal(view.facts.amount.value) == Decimal("33254.91")
    assert view.facts.currency.value == "DOP"
    assert view.facts.counterparty.value == "Hotel Brisa del Este SRL"
    assert view.facts.occurred_on.value.isoformat() == "2026-10-09"
    assert view.read_purchases == ()
    assert view.facts.fiscal.ecf.value == "E320000001234"
    if kind_hint == "expense":
        assert view.facts.kind.value == "expense"
    else:
        # An unknown kind is left for a person; the purchase itself is never lost.
        assert view.facts.kind.state == "unknown"
        assert ("fact_required", "kind") in [(b.code, b.field) for b in view.blockers]
    # The receipt finds its draft, so the inbox shows the draft, not "no purchase found".
    with transaction(service.authority, context) as tx:
        assert draft_for_receipt(tx, UUID(cid), None) == (result.draft_id, False)
    # Preparing again replays; still one draft.
    assert bridge.finish(saved).draft_id == result.draft_id
