"""A slow store call must leave the same app free to serve another request."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Event, get_ident
from time import sleep
from types import SimpleNamespace
from uuid import uuid4

import pytest
from argus.api.routers import business, business_bank, business_logo
from argus.domain.business.bank.service import bank_matching_service
from argus.domain.business.service import BusinessService

from tests.business.test_bank_api import STATEMENT
from tests.business.test_business_api import BASE, Owner, alice  # noqa: F401
from tests.profile_images.pictures import png


@pytest.fixture(autouse=True)
def bank_enabled(ingestion_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARGUS_BUSINESS_BANK_MATCHING_ENABLED", "true")


@pytest.mark.parametrize(
    ("operation", "read"),
    [
        ("upload", "receipt"),
        ("prepare", "receipt"),
        ("prepare", "_refuse_email_original"),
        ("prepare", "require_legacy_receipt_write"),
        ("prepare", "queue"),
        ("prepare", "_email_flagged"),
        ("bank", "_scope"),
        ("bank", "_capabilities"),
        ("bank", "import_statement"),
        ("logo", "_require_manager"),
        ("logo", "_payload"),
    ],
)
def test_slow_store_read_leaves_another_request_free(
    alice: Owner, monkeypatch: pytest.MonkeyPatch, operation: str, read: str  # noqa: F811
) -> None:
    receipt = alice.upload(consent=False)
    assert receipt.status_code == 200, receipt.text
    receipt_id = receipt.json()["id"]
    assert alice.reading(True).status_code == 200
    account_id = alice.account()
    if read in {"receipt", "queue"}:
        target = BusinessService
    elif operation == "bank":
        target = bank_matching_service() if read == "import_statement" else business_bank
    else:
        target = business_logo if operation == "logo" else business
    original = getattr(target, read)
    started, finished = Event(), Event()

    def slow_read(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        started.set()
        try:
            sleep(1)
            return original(*args, **kwargs)
        finally:
            finished.set()

    monkeypatch.setattr(target, read, slow_read)

    def send():  # noqa: ANN202
        if operation == "upload":
            return alice.upload()
        if operation == "prepare":
            return alice.post(
                f"/receipts/{receipt_id}/prepare", **{"X-Extraction-Consent": "true"}
            )
        if operation == "bank":
            return alice.client.post(
                BASE + "/bank/imports",
                files={"statement": ("statement.csv", STATEMENT, "text/csv")},
                data={"account_id": account_id},
                headers={**alice.auth, "Idempotency-Key": str(uuid4())},
            )
        return alice.client.put(
            BASE + "/logo",
            content=png(),
            headers={**alice.auth, "Content-Type": "image/png"},
        )

    # The fixture's TestClient lifespan shares one app event loop across callers.
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(send)
        assert started.wait(timeout=10), "request never reached the store read"
        concurrent = alice.get("/space")
        blocked = finished.is_set()
        response = pending.result(timeout=10)
    assert response.status_code == (201 if operation == "bank" else 200), response.text
    assert concurrent.status_code == 200, concurrent.text
    assert not blocked, "another request waited for the slow store read to finish"
    if operation == "upload":
        assert response.json()["id"] == receipt_id
        assert response.json()["replayed"] is True


@pytest.mark.asyncio
async def test_start_entry_checks_accounts_off_the_event_loop(
    alice: Owner, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    from argus.api.documents import documents_service
    from argus.api.ingestion import ingestion_hub

    service = BusinessService(documents_service(), ingestion_hub().sink, frozenset)
    current = SimpleNamespace(enterable=True, version=1)
    monkeypatch.setattr(service, "receipt", lambda *_: current)
    monkeypatch.setattr(service, "_set_aside", lambda *_: None)
    reads = []

    def accounts(_scope):  # noqa: ANN001, ANN202
        reads.append(get_ident())
        return {"account"}

    async def enter(**_kwargs) -> None:  # noqa: ANN003
        await asyncio.sleep(0)

    monkeypatch.setattr(service, "_account_ids", accounts)
    monkeypatch.setattr(service.documents, "enter", enter)
    assert await service.start_entry(alice.scope(), "receipt", 1, "account") == 1
    assert reads and get_ident() not in reads
