"""Turning intake or Business off never takes away saved data or blocks deleting it.

Each case restarts the real API on the disposable local Supabase stack, the
way a flag change restarts a deployed service: data is written with the flags
on, then read, unlinked or deleted with them off. Storage objects are counted
by name prefix; their content is never read. Needs the local Supabase proof
variables and ``ARGUS_DISPOSABLE_DATABASE_URL``.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import psycopg
import pytest
from argus.api import state as api_state
from argus.api.main import app
from argus.api.routers import auth as auth_router
from argus.domain.business.spaces import PostgresSpaceStore
from argus.domain.ingestion.documents.objects import owner_prefix
from argus.domain.ingestion.whatsapp.store_postgres import PostgresWhatsAppStore
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from tests.document_sources_support import stored_paths
from tests.ingestion.whatsapp_support import ENV as WHATSAPP_TEST_ENV
from tests.local_supabase_support import local_supabase_gateway
from tests.test_conversation_surfaces_postgres import DSN
from tests.test_financial_accounts_api_postgres import ORIGIN, _login

pytestmark = pytest.mark.skipif(
    not (DSN and os.getenv("ARGUS_LOCAL_SUPABASE_URL")),
    reason="local Supabase proof variables are not configured",
)
RECEIPT = (
    Path(__file__).parent / "document_extraction_fixtures/receipt-dop.png"
).read_bytes()
DOCUMENTS = "/api/v1/financial-documents"
CONNECTIONS = "/api/v1/financial-connections"
ON = {
    "ARGUS_FINANCIAL_ACCOUNTS_ENABLED": "true",
    "ARGUS_INGESTION_ENABLED": "true",
    "ARGUS_DOCUMENT_EXTRACTION_ENABLED": "true",
    "ARGUS_DOCUMENT_JOBS_ENABLED": "false",
    "ARGUS_BUSINESS_CHAT_ENABLED": "false",
    # Intake is on with the project's local test credentials; nothing is sent.
    **WHATSAPP_TEST_ENV,
    "ARGUS_WHATSAPP_OUTBOUND_ENABLED": "false",
}


class Api:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.monkeypatch = monkeypatch
        self.gateway = local_supabase_gateway()
        self.created: list[str] = []
        self.headers: dict[str, str] = {}

    @contextmanager
    def running(self, **flags: str) -> Iterator[TestClient]:
        """A fresh process: startup reads the flags, as a deploy would."""
        for name, value in {**ON, **flags}.items():
            self.monkeypatch.setenv(name, value)
        with (
            patch.object(api_state, "supabase_gateway", self.gateway),
            patch.object(api_state, "DATABASE_URL", DSN),
            patch.object(api_state, "PERSISTENCE_MODE", "supabase"),
            TestClient(app, base_url="http://localhost:3000") as client,
        ):
            if not self.headers:
                self.headers = {
                    **_login(client, self.gateway, "whileoff", self.created),
                    **ORIGIN,
                }
            yield client

    @property
    def person(self) -> str:
        return self.created[0]


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> Iterator[Api]:
    auth_router.reset_auth_attempt_limiter_for_tests()
    for name, value in {
        "ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED": "true",
        "NEXT_PUBLIC_MOCK_AUTH": "false",
        "ARGUS_MOCK_AUTH": "false",
        "ARGUS_DEV_MEMORY_FALLBACK": "false",
    }.items():
        monkeypatch.setenv(name, value)
    api = Api(monkeypatch)
    try:
        yield api
    finally:
        for user_id in api.created:
            with suppress(Exception):
                _erase_storage(user_id)
            with suppress(Exception):
                api.gateway.delete_auth_user(user_id)


def _erase_storage(user_id: str) -> None:
    from tests.document_sources_support import source_objects

    source_objects().delete(owner_prefix(user_id))


def _objects(person: str) -> int:
    with psycopg.connect(DSN) as connection:
        return sum(
            len(stored_paths(connection, prefix))
            for prefix in (owner_prefix(person), f"sealed/{person}/", f"rebuilt/{person}/")
        )


def _extractions(person: str) -> int:
    with psycopg.connect(DSN) as connection:
        row = connection.execute(
            "select count(*) from public.financial_document_extractions "
            "where user_id = %s",
            (person,),
        ).fetchone()
    assert row is not None
    return int(row[0])


def _upload(api: Api, client: TestClient) -> str:
    saved = client.post(
        DOCUMENTS,
        content=RECEIPT,
        headers={
            **api.headers,
            "Content-Type": "image/png",
            "X-Extraction-Consent": "false",
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["status"] == "saved"
    return saved.json()["connection_id"]


@pytest.mark.parametrize(
    "off",
    [
        {"ARGUS_DOCUMENT_EXTRACTION_ENABLED": "false"},
        {
            "ARGUS_INGESTION_ENABLED": "false",
            "ARGUS_DOCUMENT_EXTRACTION_ENABLED": "false",
        },
    ],
    ids=["extraction-off", "ingestion-off"],
)
def test_a_saved_document_is_read_and_deleted_with_intake_off(
    api: Api, off: dict[str, str]
) -> None:
    with api.running() as client:
        document = _upload(api, client)
    assert (_objects(api.person), _extractions(api.person)) == (1, 1)

    with api.running(**off) as client:
        listed = client.get(DOCUMENTS, headers=api.headers)
        assert [item["connection_id"] for item in listed.json()["items"]] == [document]
        source = client.get(f"{DOCUMENTS}/{document}/source", headers=api.headers)
        assert source.status_code == 200
        assert source.headers["content-type"] == "image/jpeg"
        assert source.content.startswith(b"\xff\xd8") and source.content != RECEIPT
        assert _objects(api.person) == 2
        from argus.api.documents import documents_service

        assert documents_service().store.source(user_id=api.person, connection_id=document) == RECEIPT
        assert client.get(f"{DOCUMENTS}/{document}/source", headers=api.headers).content == source.content
        assert _objects(api.person) == 2
        refused = client.post(
            DOCUMENTS,
            content=RECEIPT,
            headers={**api.headers, "Content-Type": "image/png"},
        )
        assert (refused.status_code, refused.json()["code"]) == (
            404,
            "financial_connections_unavailable",
        )
        for _attempt in range(2):
            removed = client.post(
                f"{CONNECTIONS}/{document}/disconnect", headers=api.headers
            )
            assert removed.status_code == 200, removed.text
            assert removed.json()["connection"]["status"] == "disconnected"
        assert client.get(DOCUMENTS, headers=api.headers).json()["items"] == []

    assert (_objects(api.person), _extractions(api.person)) == (0, 0)


@pytest.mark.parametrize(
    "off",
    [
        {"ARGUS_BUSINESS_PILOT_ENABLED": "false"},
        {"ARGUS_WHATSAPP_INTAKE_ENABLED": "false"},
        {"ARGUS_INGESTION_ENABLED": "false", "ARGUS_BUSINESS_PILOT_ENABLED": "false"},
    ],
    ids=["pilot-off", "intake-off", "everything-off"],
)
def test_unlink_with_business_or_intake_off_ends_the_link_and_codes(
    api: Api, off: dict[str, str]
) -> None:
    with api.running() as client:
        document = _upload(api, client)
    now = datetime.now(timezone.utc)
    with ConnectionPool(DSN, min_size=0, max_size=2) as pool:
        PostgresSpaceStore(pool).create(api.person, "Mi negocio")
        store = PostgresWhatsAppStore(pool)
        for digest in (b"used-code", b"unused-code"):
            store.issue_code(
                destination_owner_id=api.person,
                code_digest=hashlib.sha256(digest + api.person.encode()).digest(),
                reply_language="es-419",
                now=now,
                expires_at=now + timedelta(minutes=10),
            )
            if digest == b"used-code":
                store.redeem_code(
                    code_digest=hashlib.sha256(digest + api.person.encode()).digest(),
                    sender_hash=hashlib.sha256(api.person.encode()).digest(),
                    last4="1234",
                    now=now,
                )
    with api.running() as client:
        linked = client.get("/api/v1/whatsapp/link", headers=api.headers)
        assert (linked.status_code, linked.json()["linked"]) == (200, True)

    with api.running(**off) as client:
        gated = client.get("/api/v1/whatsapp/link", headers=api.headers)
        assert (gated.status_code, gated.json()["code"]) == (404, "whatsapp_unavailable")
        assert (
            client.delete("/api/v1/whatsapp/link", headers=api.headers).status_code == 204
        )
        assert (
            client.delete("/api/v1/whatsapp/link", headers=api.headers).status_code == 204
        )

    with psycopg.connect(DSN) as connection:
        links = connection.execute(
            "select status from public.whatsapp_sender_links where destination_owner_id = %s",
            (api.person,),
        ).fetchall()
        codes = connection.execute(
            "select count(*) from public.whatsapp_link_codes "
            "where destination_owner_id = %s and consumed_at is null",
            (api.person,),
        ).fetchone()
    assert (links, codes) == ([("revoked",)], (0,))
    assert _objects(api.person) == 1, "unlinking keeps what was saved"
    with api.running() as client:
        removed = client.post(f"{CONNECTIONS}/{document}/disconnect", headers=api.headers)
        assert removed.status_code == 200
    assert _objects(api.person) == 0


def test_business_chat_off_refuses_turns_but_keeps_read_and_delete(api: Api) -> None:
    with api.running() as client:
        assert client.get("/api/v1/me", headers=api.headers).status_code == 200
    with ConnectionPool(DSN, min_size=0, max_size=2) as pool:
        space = PostgresSpaceStore(pool).create(api.person, "Mi negocio")[0].id
    with psycopg.connect(DSN) as connection:
        row = connection.execute(
            "insert into public.conversations (user_id, title, title_source, language, "
            "owner_space_id) values (%s, 'Shop ledger', 'system_default', 'en', %s) "
            "returning id",
            (api.person, space),
        ).fetchone()
        assert row is not None
        business = str(row[0])
        connection.execute(
            "insert into public.messages (conversation_id, user_id, role, content) "
            "values (%s, %s, 'user', 'How is my shop doing?')",
            (business, api.person),
        )

    with api.running() as client:
        workspace = client.get("/api/v1/business/workspace", headers=api.headers)
        assert workspace.json()["chat_available"] is False
        started = client.post(
            "/api/v1/conversations", json={"surface": "business"}, headers=api.headers
        )
        turn = client.post(
            "/api/v1/chat/stream",
            json={"conversation_id": business, "message": "hi"},
            headers=api.headers,
        )
        unavailable = (404, "business_chat_unavailable")
        assert (started.status_code, started.json()["code"]) == unavailable
        assert (turn.status_code, turn.json()["code"]) == unavailable
        messages = client.get(
            f"/api/v1/conversations/{business}/messages", headers=api.headers
        )
        assert [item["content"] for item in messages.json()["items"]] == [
            "How is my shop doing?"
        ]
        removed = client.delete(f"/api/v1/conversations/{business}", headers=api.headers)
        assert removed.status_code == 200, removed.text

    with psycopg.connect(DSN) as connection:
        stored = connection.execute(
            "select count(*), count(*) filter (where deleted_at is not null) "
            "from public.conversations where user_id = %s",
            (api.person,),
        ).fetchone()
    assert stored == (1, 1)
