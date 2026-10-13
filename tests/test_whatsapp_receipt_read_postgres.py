"""On real Postgres, a receipt that arrived by WhatsApp is read through the
owner's own Business grant, as the web upload does, and settles in review."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

import pytest
from argus.api.whatsapp import DocumentsDestination
from argus.domain.business.actions import BusinessActions
from argus.domain.business.spaces import PostgresSpaceStore
from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository
from argus.domain.ingestion.documents.extractor import batch_from_result
from argus.domain.ingestion.documents.models import ExtractionResult
from argus.domain.ingestion.documents.service import DocumentsService
from argus.domain.ingestion.documents.store_postgres import PostgresDocumentStore
from argus.domain.ingestion.hub import IngestionHub

from tests import test_business_actions_postgres as shared
from tests.document_sources_support import source_objects
from tests.ingestion.whatsapp_support import RECEIPT_PNG

actions = shared.actions
users = shared.users
pytestmark = shared.pytestmark


class Extractor:
    def __init__(self) -> None:
        self.calls = 0

    async def extract(self, **kwargs: Any):  # noqa: ANN201
        self.calls += 1
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
                        merchant="Synthetic shop",
                    )
                ],
                receipt=dict(total="250.50", currency="DOP"),
            )
        )
        return batch_from_result(
            result,
            sha256(kwargs["content"]).hexdigest(),
            kwargs["connection_id"],
            datetime.now(timezone.utc),
            1,
        )


@pytest.mark.asyncio
async def test_a_whatsapp_receipt_is_read_through_the_owners_grant(actions):  # noqa: ANN001
    service, context, _ = actions
    pool = service.authority.pool
    with pool.connection() as db:
        db.execute(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities)"
            " select %s,%s,%s,ARRAY['read','prepare','approve'] where not exists"
            " (select 1 from public.business_client_grants where space_id=%s and grantee_id=%s"
            " and revoked_at is null)",
            (
                context.actor.space_id,
                context.owner_id,
                context.owner_id,
                context.actor.space_id,
                context.owner_id,
            ),
        )
    hub = IngestionHub(
        PostgresConnectionRepository(pool),
        box=None,
        sink=service.imports,
        clock=service.imports.clock,
    )
    extractor = Extractor()
    documents = DocumentsService(
        hub,
        PostgresDocumentStore(pool, source_objects()),
        extractor,
        business_actions=BusinessActions(pool, hub.sink),
        business_preparation_required=True,
    )
    destination = DocumentsDestination(
        documents, PostgresSpaceStore(pool), lambda _owner: True
    )
    owner = str(context.owner_id)
    captured = await destination.capture(
        owner_id=owner,
        content=RECEIPT_PNG,
        filename="whatsapp-image",
        media_type="image/png",
    )
    result = await destination.read(owner_id=owner, connection_id=captured.connection_id)
    assert result is not None
    assert result[0] in ("review_ready", "needs_attention")
    assert extractor.calls == 1
