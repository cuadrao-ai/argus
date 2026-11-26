"""A Business receipt goes from upload to the worker, Registros and Actividad."""

from __future__ import annotations

import asyncio
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from argus.api.documents import documents_service
from argus.domain.ingestion.documents.models import ExtractionBatch
from argus.domain.ingestion.documents.service import DocumentsService
from argus.llm.local_reader_fixtures import response_body
from psycopg_pool import ConnectionPool

from tests import test_business_listos_postgres as bandeja
from tests import test_business_scope_switch_routes_postgres as scope
from tests import test_financial_accounts_postgres as database
from tests.business.test_business_api import RECEIPT
from tests.document_reads_support import read_receipt
from tests.test_business_reading_setting_postgres import _reading, _upload
from workflows.document_job import postgres_documents_service

pytestmark = scope.pytestmark
web = scope.web


@pytest.fixture(autouse=True)
def reads_finish_inside_the_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """Leave the API's queue intact so a worker with its own pool takes the read."""
    monkeypatch.setenv("CUADRAO_LOCAL_READER_FIXTURES", "true")
    monkeypatch.setenv("CUADRAO_OPENROUTER_API_KEY_DEV", "local-reader-placeholder")
    monkeypatch.setenv("CUADRAO_DOCUMENT_EXTRACTION_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_VISION_MODEL", "test/model")


def _comparable(batch: ExtractionBatch) -> dict:
    # Each actual request records when it happened and how long it took.
    return batch.model_dump(
        mode="json",
        exclude={
            "metadata": {"route_receipts": {"__all__": {"created_at", "latency_ms"}}}
        },
    )


def _upload_and_read(
    web: SimpleNamespace, worker: DocumentsService, source: bytes
) -> str:
    answer = _upload(web, source)
    assert answer.status_code == 200, answer.text
    receipt_id = answer.json()["id"]
    assert bandeja._label(web, receipt_id) == "reading"
    assert asyncio.run(read_receipt(worker, web.alice.id, receipt_id)) == "prepared"
    return receipt_id


def test_local_receipt_walk(
    web: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = (
        Path(__file__).parent / "synthetic_ingestion/samples/receipt.png"
    ).read_bytes()
    assert _reading(web, True).status_code == 200
    requests = []

    async def network(
        transport: httpx.AsyncHTTPTransport, request: httpx.Request
    ) -> httpx.Response:
        if request.url.host in {"localhost", "127.0.0.1"}:
            return await real_transport(transport, request)
        assert request.url.path.endswith("/chat/completions")
        requests.append(request.url)
        return httpx.Response(200, json=response_body(sha256(content).hexdigest()))

    real_transport = httpx.AsyncHTTPTransport.handle_async_request
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", network)
    documents = documents_service()
    with ConnectionPool(database.DSN, min_size=0, max_size=2) as pool:
        worker = postgres_documents_service(pool, documents.store.objects)
        clean_id = _upload_and_read(web, worker, content)
        assert bandeja._label(web, clean_id) == "ready"
        attention_id = _upload_and_read(web, worker, RECEIPT)
        assert bandeja._label(web, attention_id) == "needs_attention"
        assert requests == []

        saved = worker.store.get(user_id=web.alice.id, connection_id=clean_id)
        assert saved is not None
        [purchase] = saved.candidates
        assert saved.metadata["route_receipts"][0]["outcome"] == "succeeded"
        monkeypatch.setenv("CUADRAO_LOCAL_READER_FIXTURES", "false")
        normal = asyncio.run(
            worker.extractor.extract(
                content=content,
                filename="recibo.png",
                media_type="image/png",
                connection_id=clean_id,
                observed_at=purchase.source.observed_at,
            )
        )
        assert len(requests) == 1
        assert _comparable(saved) == _comparable(normal)

    item = bandeja._named(web, clean_id)
    dossier = bandeja._get(web, f"/business/drafts/{item['draft_id']}/dossier")
    assert dossier["bandeja_group"]["label"] == "ready"
    approved = bandeja._approve_alone(web, item)
    assert approved.status_code == 200, approved.text
    record = approved.json()["approval_result"]["activity_id"]
    assert bandeja._label(web, clean_id) == "accepted"
    day = purchase.occurred_on.isoformat()
    [expense] = bandeja._get(web, "/business/expenses", **{"from": day, "to": day})[
        "items"
    ]
    assert expense["id"] == record
    [approval] = [
        event
        for event in bandeja._get(web, "/business/activity")["items"]
        if event["action"] == "approve_expense"
    ]
    assert approval["object"]["id"] == item["draft_id"]
    assert (approval["area"], approval["group"]) == ("records", "approvals")
