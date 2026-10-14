"""The modal's real request producer crosses the actual Business HTTP boundary.

No duplicated header/body builder: Bun invokes uploadBusinessReceipt and captures
its Request. TestClient sends those exact bytes and headers to the real route.
The existing receipt stub replaces the AI provider only.
"""

from __future__ import annotations

import base64
import io
import json
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from argus.api.app_setup import validation_exception_handler
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from loguru import logger
from PIL import Image

from tests.business.conftest import ALICE
from tests.business.test_business_api import Owner

ROOT = Path(__file__).resolve().parents[2]


def web_request(content: bytes, media_type: str, consent: bool) -> dict:
    bun = shutil.which("bun")
    assert bun is not None, "Business transport proof requires Bun, as configured in CI"
    result = subprocess.run(
        [bun, "run", "__tests__/fixtures/receipt-web-request.ts"],
        cwd=ROOT / "web",
        input=json.dumps(
            {
                "content": base64.b64encode(content).decode(),
                "media_type": media_type,
                "filename": "recibo café.jpg",
                "consent": consent,
                "token": ALICE,
                "key": str(uuid4()),
            }
        ),
        text=True,
        capture_output=True,
        timeout=30,
        check=True,
    )
    return json.loads(result.stdout)


def send(client: TestClient, request: dict):
    return client.request(
        request["method"],
        request["path"],
        headers=request["headers"],
        content=base64.b64decode(request["content"]),
    )


@pytest.mark.parametrize("consent", [False, True])
def test_modal_request_saves_a_4_mib_jpeg_and_replays_without_duplication(
    biz: TestClient,
    consent: bool,
) -> None:
    owner = Owner(biz, ALICE)
    assert owner.start().status_code == 201
    if consent:
        assert owner.reading(True).status_code == 200
    image = io.BytesIO()
    Image.new("RGB", (16, 16), "white").save(image, format="JPEG")
    # Valid JPEG with trailing padding: match the reported file size without
    # creating a huge image or committing any real receipt content.
    content = image.getvalue().ljust(round(4.1 * 1024 * 1024), b"\0")
    request = web_request(content, "image/jpeg", consent)
    response = send(biz, request)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["filename"] == "recibo café.jpg"
    assert saved["size_bytes"] == len(content)
    assert saved["media_type"] == "image/jpeg"
    assert saved["status"] == ("queued" if consent else "saved")
    source = owner.get(f"/receipts/{saved['id']}/source")
    assert source.content == content
    again = send(biz, request)
    assert again.status_code == 200
    assert again.json()["id"] == saved["id"]
    assert again.json()["replayed"] is True
    assert len(owner.get("/receipts").json()["items"]) == 1


@pytest.mark.parametrize(
    "media_type,status,code",
    [
        ("image/jpeg", 422, "invalid_document"),
        ("application/octet-stream", 415, "document_media_type_unsupported"),
    ],
)
def test_modal_request_exposes_precise_safe_failure_without_saving(
    biz: TestClient,
    media_type: str,
    status: int,
    code: str,
) -> None:
    owner = Owner(biz, ALICE)
    assert owner.start().status_code == 201
    request = web_request(b"not an image", media_type, True)
    messages: list[str] = []
    sink = logger.add(lambda message: messages.append(str(message)))
    try:
        response = send(biz, request)
    finally:
        logger.remove(sink)
    assert (response.status_code, response.json()["code"]) == (status, code)
    if status == 422:
        logged = "\n".join(messages)
        assert "receipt_upload_failed status=422 code=invalid_document" in logged
        assert "not an image" not in logged
        assert "recibo café" not in logged
    assert owner.get("/receipts").json()["items"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/v1/business/receipts", "/api/v1/business/other"])
async def test_receipt_validation_logs_only_declared_fields_and_error_types(
    path: str,
) -> None:
    canary = "PRIVATE_REQUEST_CANARY"
    request = Request({"type": "http", "method": "POST", "path": path, "headers": []})
    error = RequestValidationError(
        [
            {
                "loc": ("header", "Idempotency-Key"),
                "type": "missing",
                "input": canary,
                "msg": canary,
            },
            {
                "loc": ("query", canary),
                "type": canary,
                "input": canary,
                "msg": canary,
                "ctx": {"private": canary},
            },
        ]
    )
    messages: list[str] = []
    sink = logger.add(lambda message: messages.append(str(message)))
    try:
        response = await validation_exception_handler(request, error)
    finally:
        logger.remove(sink)
    assert response.status_code == 422
    logged = "\n".join(messages)
    assert canary not in logged
    if path.endswith("/receipts"):
        assert "field=header.idempotency-key type=missing" in logged
        assert "field=query.unknown type=unknown" in logged
    else:
        assert "receipt_upload_validation_failed" not in logged
