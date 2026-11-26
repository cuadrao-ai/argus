"""Local reader configuration, the document wire contract and the HTTP boundary."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import jsonschema
import pytest
from argus.domain.ingestion.documents.config import DocumentExtractionSettings
from argus.domain.ingestion.documents.extractor import DocumentExtractor
from argus.domain.ingestion.documents.models import ExtractionResult
from argus.llm import openrouter
from argus.llm.local_reader_fixtures import response_body
from argus.llm.openrouter_key_policy import (
    local_reader_fixtures_enabled,
    validate_hosted_openrouter_configuration,
)

SETTING = "CUADRAO_LOCAL_READER_FIXTURES"
ROOT = Path(__file__).resolve().parents[1]


def test_reader_is_opt_in_and_absent_from_hosted_profiles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(SETTING, raising=False)
    assert not local_reader_fixtures_enabled()
    assert f"{SETTING}=false" in (ROOT / ".env.example").read_text().splitlines()
    for relative in (
        "render.yaml",
        ".github/private-alpha-release-profile.json",
        "scripts/ops/staging_env_manifest.json",
    ):
        assert SETTING not in (ROOT / relative).read_text()


@pytest.mark.parametrize(
    ("environment", "render", "service_id"),
    [
        ("local", "true", ""),
        ("local", "", "srv-123"),
        ("staging", "", ""),
        ("production", "", ""),
    ],
)
def test_hosted_startup_refuses_replay(
    monkeypatch: pytest.MonkeyPatch, environment: str, render: str, service_id: str
) -> None:
    monkeypatch.setenv(SETTING, "true")
    monkeypatch.setenv("APP_ENV", environment)
    monkeypatch.setenv("RENDER", render)
    monkeypatch.setenv("RENDER_SERVICE_ID", service_id)
    with pytest.raises(RuntimeError, match=SETTING):
        validate_hosted_openrouter_configuration()


@pytest.mark.parametrize(
    ("filename", "total", "rnc"),
    [("receipt-dop.png", "250.50", None), ("unreadable.png", "3450.00", "199990021")],
)
def test_canned_answers_match_the_required_document_wire_schema(
    filename: str, total: str, rnc: str | None
) -> None:
    digest = hashlib.sha256(
        (ROOT / "tests/document_extraction_fixtures" / filename).read_bytes()
    )
    (choice,) = response_body(digest.hexdigest())["choices"]
    assert choice["finish_reason"] == "stop"
    contents = json.loads(choice["message"]["content"])
    jsonschema.validate(
        contents, openrouter._document_wire_schema(ExtractionResult.model_json_schema())
    )
    receipt = contents["receipt"]
    assert (receipt["total"], receipt["rnc"]) == (total, rnc)
    assert contents["observations"][0]["amount"] == total


@pytest.mark.asyncio
async def test_attention_file_reads_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unexpected_network(*_args: object) -> httpx.Response:
        pytest.fail("Document replay reached the network")

    monkeypatch.setenv(SETTING, "true")
    monkeypatch.setenv("CUADRAO_OPENROUTER_API_KEY_DEV", "local-placeholder")
    monkeypatch.setenv("CUADRAO_VISION_MODEL", "test/model")
    monkeypatch.setattr(
        httpx.AsyncHTTPTransport, "handle_async_request", unexpected_network
    )
    content = (ROOT / "tests/document_extraction_fixtures/receipt-dop.png").read_bytes()
    batch = await DocumentExtractor(DocumentExtractionSettings(enabled=True)).extract(
        content, "renamed.png", "image/png", "local-test", datetime.now(timezone.utc)
    )
    assert batch.receipt is not None
    assert (batch.receipt.total, batch.receipt.rnc) == ("250.50", None)
    assert batch.metadata["route_receipts"][0]["outcome"] == "succeeded"


@pytest.mark.asyncio
async def test_other_model_calls_keep_their_transport(
    monkeypatch: pytest.MonkeyPatch, respx_mock
) -> None:
    monkeypatch.setenv(SETTING, "true")
    monkeypatch.setenv("CUADRAO_OPENROUTER_API_KEY_DEV", "local-placeholder")
    route = respx_mock.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=response_body(None))
    )
    result = await openrouter.invoke_openrouter_json_schema(
        task="interpretation",
        model_name="test/model",
        messages=[],
        schema_model=ExtractionResult,
        schema_name="test_response",
    )
    assert route.call_count == 1
    assert result is not None
