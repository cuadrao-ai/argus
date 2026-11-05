"""Two edges of the WhatsApp read: the read binds only to the owner who
received the receipt, and a release that fails after a read that could not
start keeps the original error as the one raised."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from argus.api import whatsapp as module
from argus.domain.ingestion.reconcile.service import ReconciliationService
from argus.domain.ingestion.reconcile.store import InMemoryImportStore
from argus.domain.ingestion.whatsapp.intake import CaptureFailed


def _documents(owner_id: str, capabilities=("read", "prepare")):  # noqa: ANN001, ANN202
    documents = Mock()
    documents.hub.sink = ReconciliationService(
        InMemoryImportStore(), Mock(), lambda: datetime.now(timezone.utc)
    )
    actions = Mock()
    actions.resolve_actor = Mock(return_value=SimpleNamespace(owner_id=owner_id))
    actions.record_context = Mock(return_value=SimpleNamespace(capabilities=capabilities))
    documents.business_actions = actions
    return documents


def test_the_read_binds_only_to_the_owner_who_received_the_receipt(monkeypatch):  # noqa: ANN001
    owner, other = str(uuid4()), str(uuid4())
    scope = SimpleNamespace(space_id=uuid4())
    bound = []
    monkeypatch.setattr(
        "argus.api.business_drafts.bind_to_grant",
        lambda documents, hub, actions, context, capability: (
            bound.append(context) or (documents, None)
        ),
    )
    # A grant that resolves for another person, prepare and all: refused.
    with pytest.raises(CaptureFailed) as refused:
        module._as_owner(_documents(other), owner, scope)
    assert refused.value.code == "business_permission_denied"
    assert bound == []
    # The owner: bound.
    documents = _documents(owner)
    assert module._as_owner(documents, owner, scope) is documents
    assert [c.owner_id for c in bound] == [owner]
    # The owner without prepare: refused.
    with pytest.raises(CaptureFailed):
        module._as_owner(_documents(owner, capabilities=("read",)), owner, scope)


@pytest.mark.asyncio
async def test_a_failed_release_keeps_the_original_error_and_chains_the_release(
    monkeypatch,
):  # noqa: ANN001
    owner = str(uuid4())
    documents = Mock()
    documents.get = Mock(return_value=SimpleNamespace(status="queued"))
    documents.release_queued = Mock(side_effect=RuntimeError("release broke"))
    destination = module.DocumentsDestination(documents, Mock())
    monkeypatch.setattr(
        module,
        "resolve_business_scope",
        lambda spaces, owner_id: SimpleNamespace(owner=SimpleNamespace(space_id=uuid4())),
    )
    monkeypatch.setattr(module, "_as_owner", lambda documents, owner_id, scope: documents)

    async def failing_dispatch(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        raise ValueError("read could not start")

    monkeypatch.setattr("argus.api.documents.dispatch_preparation", failing_dispatch)
    with pytest.raises(ValueError) as raised:
        await destination.read(owner_id=owner, connection_id=str(uuid4()))
    assert str(raised.value) == "read could not start"
    assert isinstance(raised.value.__cause__, RuntimeError)
    assert str(raised.value.__cause__) == "release broke"
    documents.release_queued.assert_called_once()
