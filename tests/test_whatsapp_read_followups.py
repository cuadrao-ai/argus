"""Receipt reads act under the sender grant and preserve a refused read as saved."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from argus.api import whatsapp as module
from argus.domain.ingestion.documents.service import DocumentsService
from argus.domain.ingestion.reconcile.service import ReconciliationService
from argus.domain.ingestion.reconcile.store import InMemoryImportStore
from argus.domain.ingestion.whatsapp.intake import CaptureFailed
from argus.domain.ingestion.whatsapp.store import Settlement


def _documents(owner_id: str):  # noqa: ANN202
    documents = Mock()
    documents.hub.sink = ReconciliationService(
        InMemoryImportStore(), Mock(), lambda: datetime.now(timezone.utc)
    )
    actions = Mock()
    actions.resolve_actor = Mock(return_value=SimpleNamespace(owner_id=owner_id))
    documents.business_actions = actions
    return documents


def test_the_read_binds_to_the_sender_when_storage_belongs_to_another_person(monkeypatch):  # noqa: ANN001
    owner, other = str(uuid4()), str(uuid4())
    scope = module.BusinessSpace(str(uuid4()))
    bound = []
    monkeypatch.setattr(
        "argus.api.business_drafts.bind_to_grant",
        lambda documents, hub, actions, context, capability: (
            bound.append(context) or (documents, None)
        ),
    )
    documents = _documents(other)
    assert DocumentsService.for_sender(documents, owner, scope) is documents
    assert len(bound) == 1
    (actor,) = documents.business_actions.resolve_actor.call_args.args
    assert str(actor.actor_id) == owner


def test_a_read_refused_before_dispatch_waits_saved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, connection = str(uuid4()), str(uuid4())
    scope = module.BusinessSpace(str(uuid4()))
    documents = Mock()
    documents.get.return_value = SimpleNamespace(
        status="saved",
        source_available=False,
        business_reading_consent_id=str(uuid4()),
        connection_id=connection,
    )
    grants = (SimpleNamespace(space_id=scope.space_id, owner_id=owner),)
    destination = module.DocumentsDestination(documents, SimpleNamespace(eligible_businesses=lambda _: grants))
    documents.get.return_value.media_type = "image/png"
    documents.get.return_value.size_bytes = 15

    def refused(owner_id, scope):  # noqa: ANN001, ANN202
        raise CaptureFailed("business_preparation_unavailable")

    monkeypatch.setattr(documents, "for_sender", refused)
    assert not destination.prepare(
        None,
        Settlement(
            "captured",
            owner,
            connection,
            storage_user_id=owner,
            space_id=scope.space_id,
            sender_link_id=str(uuid4()),
        ),
        b"message",
    ).reading
    documents.publish_capture.assert_called_once_with(
        user_id=owner,
        connection_id=connection,
        scope=scope,
        error_code="business_preparation_unavailable",
    )
    documents.release_queued.assert_called_once_with(
        user_id=owner,
        connection_id=connection,
        scope=scope,
        code="business_preparation_unavailable",
    )
