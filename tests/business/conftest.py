"""Business API fixtures: the real auth dependency, documents on, a local receipt stub."""

from collections.abc import Iterator

import pytest
from argus.api.documents import documents_service
from fastapi.testclient import TestClient

from tests.business.receipt_stub import ReceiptStub
from tests.ingestion.conftest import (  # noqa: F401
    ALICE,
    BOB,
    client,
    gateway,
    identities,
    ingestion_env,
    surface_env,
)


@pytest.fixture
def business_env(ingestion_env, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001, F811
    monkeypatch.setenv("ARGUS_DOCUMENT_EXTRACTION_ENABLED", "true")


@pytest.fixture
def stub(business_env, client: TestClient, monkeypatch) -> ReceiptStub:  # noqa: ANN001, F811
    extractor = ReceiptStub()
    monkeypatch.setattr(documents_service(), "extractor", extractor)
    documents_service().business_receipt_consent.route_resolver = lambda: {
        "gateway": "synthetic",
        "interpretation": [{"model": "receipt-fixture"}],
        "reply": [],
    }
    return extractor


@pytest.fixture
def biz(stub: ReceiptStub, client: TestClient) -> Iterator[TestClient]:  # noqa: F811
    yield client


@pytest.fixture
def stored_whatsapp_dossier(monkeypatch: pytest.MonkeyPatch):
    """Give a dossier service double the real channel projection over stored captures."""
    from unittest.mock import Mock

    from argus.domain.business.record_origin import UploadIntake, with_source_channels
    from argus.domain.business.transactions import ActionTransaction
    from argus.domain.ingestion.email_intake.store import PostgresEmailStore
    from argus.domain.ingestion.whatsapp.store_postgres import PostgresWhatsAppStore

    def seed(service, owner, connection_id):
        owners = []

        def captures(store, *, destination_owner_id):
            owners.append(destination_owner_id)
            return frozenset([str(connection_id)]) if destination_owner_id == str(owner) else frozenset()

        monkeypatch.setattr(PostgresWhatsAppStore, "captured_connections", captures)
        monkeypatch.setattr(PostgresEmailStore, "membership", lambda store, space_id: {})
        read = service.dossier

        def dossier(instance, actor, draft):
            tx = Mock(spec=ActionTransaction, context=actor)
            tx.connection = Mock()
            tx.rows.return_value = []
            return with_source_channels(read(instance, actor, draft), UploadIntake.stored(tx))

        monkeypatch.setattr(service, "dossier", dossier)
        return owners

    return seed
