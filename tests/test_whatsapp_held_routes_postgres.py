"""Sender-scoped recovery through HTTP on a disposable database."""

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from argus.api.main import app
from argus.api.whatsapp import WhatsAppSenderContext, require_whatsapp_sender
from argus.domain.business.contracts.deletion import PURGE_AFTER
from argus.domain.business.read_budget import ReadBudgetSettings
from argus.domain.ingestion.whatsapp.store_postgres import PostgresWhatsAppStore
from argus.domain.owner_scope import PERSONAL
from fastapi.testclient import TestClient

from tests import test_whatsapp_adopt_postgres as adopt
from tests.ingestion.whatsapp_support import RECEIPT_PNG

actions, users, pool = adopt.actions, adopt.users, adopt.pool
desk, sender = adopt.desk, adopt.sender
reads_finish_inside_the_request = adopt.reads_finish_inside_the_request
pytestmark = adopt.pytestmark
LIST = "/api/v1/whatsapp/held-files"


@pytest.fixture
def recovery(sender, monkeypatch):
    signed_in = SimpleNamespace(person=sender.owner)
    runtime = SimpleNamespace(
        intake=SimpleNamespace(store=PostgresWhatsAppStore(sender.pool))
    )
    monkeypatch.setitem(
        app.dependency_overrides,
        require_whatsapp_sender,
        lambda: WhatsAppSenderContext(runtime, signed_in.person, None),
    )
    monkeypatch.setattr(
        "argus.api.routers.whatsapp.documents_service", lambda: sender.service
    )
    with TestClient(app) as client:
        yield client, signed_in


@pytest.mark.parametrize("at_limit", [False, True], ids=["hand-over", "business-full"])
def test_preview_only_while_held_by_sender_and_never_dispatches_a_read(
    sender, recovery, at_limit
):
    client, signed_in = recovery
    row = adopt.capture(sender)
    key = dict(user_id=sender.owner, connection_id=row.connection_id)
    before = sender.service.store.draft(**key)
    response = client.get(LIST)
    assert response.status_code == 200, response.text
    [file] = response.json()["files"]
    assert set(file) == {
        "id",
        "reason",
        "reading",
        "held_at",
        "expires_at",
        "media_type",
        "preview_url",
    }
    assert file["id"] == row.id and file["reason"] == row.reason
    assert file["expires_at"] == (row.held_at + PURGE_AFTER).isoformat().replace(
        "+00:00", "Z"
    )
    preview = client.get(file["preview_url"])
    assert preview.status_code == 200
    assert preview.headers["cache-control"] == "private, no-store"
    assert preview.headers["content-type"] == "application/pdf"
    assert preview.content == sender.service.store.source(**key)
    assert sender.extractor.calls == 0 and sender.service.store.draft(**key) == before
    signed_in.person = sender.custodian
    assert client.get(LIST).json()["files"] == []
    assert client.get(file["preview_url"]).status_code == 404
    signed_in.person = sender.owner
    assert adopt.held.read(sender, row) == "prepared"
    if at_limit:
        sender.service.read_budget.settings = ReadBudgetSettings(per_day=1)
        assert sender.service.read_budget.charge(sender.space, sender.now) is None
    assign = client.post(f"{LIST}/{row.id}/assign", json={"business_id": sender.space})
    assert assign.status_code == 204, assign.text
    assert client.get(LIST).json()["files"] == []
    assert client.get(file["preview_url"]).status_code == 404
    assert sender.extractor.calls == 1 and adopt.counts(sender) == (1, int(at_limit))


def test_unread_photo_previews_without_writing_a_rebuilt_copy(sender, recovery):
    client, _ = recovery
    result = asyncio.run(
        sender.service.upload(
            user_id=sender.owner,
            scope=PERSONAL,
            content=RECEIPT_PNG,
            filename="held.png",
            media_type="image/png",
            consent=False,
            on_capture=sender.files.capture(
                user_id=sender.owner,
                sender_link_id=sender.sender_link_id,
                provider_message_key=uuid4().bytes * 2,
                reason="no_eligible_business",
                now=sender.now,
            ),
        )
    )
    key = dict(user_id=sender.owner, connection_id=result.connection_id)
    draft = sender.service.store.draft(**key)
    assert sender.service.store.rebuilt(**key) is None
    [file] = client.get(LIST).json()["files"]
    assert file["media_type"] == "image/png" and file["reading"] is False
    preview = client.get(file["preview_url"])
    assert preview.status_code == 200 and preview.headers["content-type"] == "image/jpeg"
    assert preview.content.startswith(bytes.fromhex("ffd8ff"))
    assert sender.service.store.rebuilt(**key) is None
    assert sender.service.store.draft(**key) == draft
    assert sender.extractor.calls == 0 and adopt.counts(sender) == (0, 0)


def test_refused_assignment_preserves_the_file_without_naming_revoked_business(
    sender, recovery
):
    client, _ = recovery
    row = adopt.capture(sender)
    path = f"{LIST}/{row.id}/assign"
    selection = {"business_id": sender.space}
    with sender.pool.connection() as db:
        db.execute(
            "update public.financial_source_connections set lease_until=%s, lease_holder=%s where id=%s",
            (sender.now + timedelta(minutes=1), str(uuid4()), row.connection_id),
        )
    busy = client.post(path, json=selection)
    assert (busy.status_code, busy.json()["code"]) == (409, "document_busy")
    assert client.get(LIST).json()["files"][0]["reading"] is True
    with sender.pool.connection() as db:
        name = db.execute(
            "select name from public.spaces where id=%s", (sender.space,)
        ).fetchone()[0]
        db.execute(
            "update public.business_client_grants set revoked_at=now() where id=%s",
            (sender.grant,),
        )
    denied = client.post(path, json=selection)
    assert (denied.status_code, denied.json()["code"]) == (
        403,
        "business_permission_denied",
    )
    response = client.get(LIST)
    assert response.json()["receiving_businesses"] == []
    assert response.json()["files"][0]["id"] == row.id
    for body in (denied.text, response.text):
        assert sender.space not in body and name not in body
    assert sender.extractor.calls == 0 and adopt.counts(sender) == (0, 0)
