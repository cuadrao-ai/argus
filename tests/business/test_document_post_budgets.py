"""Uploads spend a 60-a-minute budget per person and no daily one, and three
may be in flight at once. Prepare and the reading toggle keep their own minute
budgets."""

from __future__ import annotations

import asyncio
import threading

import pytest
from argus.api.documents import _in_flight, _minute, documents_service

from tests.business.conftest import ALICE, BOB
from tests.business.test_business_api import RECEIPT, Owner, started


@pytest.fixture
def alice(biz, identities):  # noqa: ANN001
    return started(Owner(biz, ALICE, identities[ALICE]["id"]))


@pytest.fixture
def bob(biz, identities):  # noqa: ANN001
    return started(Owner(biz, BOB, identities[BOB]["id"]))


def _post_budget(owner: Owner, path: str, **headers: str):
    if path == "/receipts":
        return owner.upload(consent=False)
    if path == "/receipt-reading":
        shown = owner.get("/receipt-reading").json()
        return owner.post(
            path,
            {
                "enabled": True,
                "scope_version": shown["scope_version"],
                "disclosure_token": shown["disclosure_token"],
            },
        )
    return owner.post(path, **headers)


def test_sixty_uploads_a_minute_pass_and_the_sixty_first_waits(alice: Owner):
    _minute.reset()
    uploaded = [_post_budget(alice, "/receipts") for _ in range(60)]
    assert [item.status_code for item in uploaded] == [200] * 60, uploaded[-1].text
    refused = _post_budget(alice, "/receipts")
    assert refused.status_code == 429
    assert refused.json()["code"] == "document_rate_limited"
    assert refused.headers["Retry-After"]


def test_prepare_and_the_reading_toggle_keep_their_own_minute_budgets(alice: Owner):
    _minute.reset()
    reading = _post_budget(alice, "/receipt-reading")
    assert reading.status_code == 200, reading.text
    receipt_id = alice.upload().json()["id"]
    prepares = [
        _post_budget(
            alice,
            f"/receipts/{receipt_id}/prepare",
            **{"X-Extraction-Consent": "true"},
        )
        for _ in range(5)
    ]
    assert [item.status_code for item in prepares] == [200] * 5
    blocked = _post_budget(
        alice, f"/receipts/{receipt_id}/prepare", **{"X-Extraction-Consent": "true"}
    )
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "document_rate_limited"
    toggles = [_post_budget(alice, "/receipt-reading") for _ in range(4)]
    assert all(item.status_code != 429 for item in toggles)
    limited = _post_budget(alice, "/receipt-reading")
    assert limited.status_code == 429
    assert limited.json()["code"] == "document_rate_limited"
    assert alice.upload().status_code == 200


def test_a_fourth_upload_in_flight_waits_while_another_person_passes(
    alice: Owner, bob: Owner, monkeypatch: pytest.MonkeyPatch
):
    """Three of one person's uploads are in flight; the fourth is told to wait a
    second and nobody else is, so a burst from one phone never fills the API."""

    _minute.reset()
    _in_flight.reset()
    assert alice.upload(consent=False).status_code == 200
    documents = documents_service()
    original = documents.upload
    release = threading.Event()
    started = threading.Semaphore(0)
    holds = iter(range(3))

    async def held(**kwargs):  # noqa: ANN003, ANN202
        # Only three are held, so a gate that lets a fourth in fails the
        # assertion below instead of hanging the test.
        if kwargs["user_id"] == alice.person and next(holds, None) is not None:
            started.release()
            await asyncio.to_thread(release.wait)
        return await original(**kwargs)

    monkeypatch.setattr(documents, "upload", held)
    answers: list = []
    senders = [
        threading.Thread(target=lambda: answers.append(alice.upload(consent=False)))
        for _ in range(3)
    ]
    for sender in senders:
        sender.start()
    try:
        for _ in senders:
            assert started.acquire(timeout=10)
        fourth = alice.upload(consent=False)
        assert fourth.status_code == 429, fourth.text
        assert fourth.headers["Retry-After"] == "1"
        assert fourth.json()["code"] == "document_rate_limited"
        other = bob.upload(consent=False)
        assert other.status_code == 200, other.text
    finally:
        release.set()
        for sender in senders:
            sender.join(timeout=10)
    assert [item.status_code for item in answers] == [200] * 3
    assert alice.upload(consent=False).status_code == 200


def test_a_refused_upload_frees_its_in_flight_slot(alice: Owner):
    _minute.reset()
    _in_flight.reset()
    refused = [alice.upload(media_type="application/zip") for _ in range(4)]
    assert [item.status_code for item in refused] == [415] * 4
    assert alice.upload().status_code == 200


def test_a_slot_covers_the_upload_not_the_read_behind_it(
    alice: Owner, monkeypatch: pytest.MonkeyPatch
):
    """With jobs off a read runs as a background task after the response. Three
    receipts being read must not hold the three upload slots: the person keeps
    uploading while the API reads."""

    _minute.reset()
    _in_flight.reset()
    assert alice.reading(True).status_code == 200
    documents = documents_service()
    release = threading.Event()
    started = threading.Semaphore(0)
    blocked = iter(range(3))

    async def read_later(**kwargs):  # noqa: ANN003, ANN202
        if next(blocked, None) is None:
            return
        started.release()
        await asyncio.to_thread(release.wait)

    monkeypatch.setattr(documents, "background_prepare", read_later)
    answers: list = []
    senders = [
        threading.Thread(
            target=lambda n=n: answers.append(alice.upload(content=RECEIPT + bytes([n])))
        )
        for n in range(3)
    ]
    for sender in senders:
        sender.start()
    try:
        for _ in senders:
            assert started.acquire(timeout=10)
        while_reading = [alice.upload(content=RECEIPT + bytes([n])) for n in (10, 11)]
        assert [item.status_code for item in while_reading] == [200, 200], [
            item.text for item in while_reading
        ]
    finally:
        release.set()
        for sender in senders:
            sender.join(timeout=10)
    assert [item.status_code for item in answers] == [200] * 3
