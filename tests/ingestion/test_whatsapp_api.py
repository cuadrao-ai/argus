"""The WhatsApp HTTP surface: flag, verification, signature gate, linking, logs."""

import logging
from collections.abc import Iterator
from datetime import timedelta
from unittest.mock import patch

import httpx
import pytest
from argus.api import state as api_state
from argus.api.business_spaces import business_spaces
from argus.api.documents import documents_service
from argus.api.main import app
from argus.api.whatsapp import (
    WEBHOOK_PATH,
    build_whatsapp,
    configure_whatsapp,
    whatsapp_runtime,
)
from argus.domain.business.scope import resolve_business_scope
from argus.domain.ingestion.whatsapp.replies import CloudApiTransport
from argus.domain.ingestion.whatsapp.store import InMemoryWhatsAppStore
from argus.domain.owner_scope import PERSONAL
from fastapi.testclient import TestClient
from loguru import logger

from tests.ingestion.conftest import ALICE, BOB, GUEST, bearer
from tests.ingestion.whatsapp_support import (
    ALICE_PHONE,
    ENV,
    RECEIPT_PNG,
    VERIFY_TOKEN,
    FakeGraph,
    Media,
    encode,
    fixture,
    sign,
)

WEBHOOK = "/api/v1/webhooks/whatsapp"
LINK = "/api/v1/whatsapp/link"
CODES = "/api/v1/whatsapp/link-codes"


@pytest.fixture
def graph() -> FakeGraph:
    return FakeGraph()


@pytest.fixture
def wa_client(
    ingestion_env, gateway, identities, monkeypatch, graph
) -> Iterator[TestClient]:  # noqa: ANN001
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
        TestClient(app) as test_client,
    ):
        runtime = whatsapp_runtime()
        assert runtime is not None and runtime.intake.transport is None
        configure_whatsapp(
            build_whatsapp(
                runtime.settings,
                documents=documents_service(),
                spaces=business_spaces(),
                store=InMemoryWhatsAppStore(),
                client=graph.client(),
                app_origin="https://app.test",
            )
        )
        # Linking needs a Business space; both people have started theirs.
        for token in (ALICE, BOB):
            business_spaces().create(identities[token]["id"], "Mi negocio")
        yield test_client


def post(client: TestClient, body: dict, signature: str | None = None) -> httpx.Response:
    raw = encode(body)
    return client.post(
        WEBHOOK,
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": signature or sign(raw),
        },
    )


def link_alice(client: TestClient) -> None:
    issued = client.post(CODES, headers=bearer(ALICE))
    assert issued.status_code == 201, issued.text
    text = issued.json()["message_text"]
    assert post(client, fixture("text_link_code.json", text=text)).status_code == 200


def test_flag_off_answers_404_everywhere(client: TestClient) -> None:
    raw = encode(fixture("image_message.json"))
    responses = [
        client.get(WEBHOOK, params={"hub.mode": "subscribe"}),
        client.post(WEBHOOK, content=raw, headers={"X-Hub-Signature-256": sign(raw)}),
        client.post(CODES, headers=bearer(ALICE)),
        client.get(LINK, headers=bearer(ALICE)),
    ]
    assert [r.status_code for r in responses] == [404] * 4
    assert {r.json()["code"] for r in responses} == {"whatsapp_unavailable"}
    # Unlinking is never gated; with intake off nothing here holds a link.
    assert client.delete(LINK, headers=bearer(ALICE)).status_code == 204


@pytest.mark.parametrize(
    "flag", ["ARGUS_BUSINESS_PILOT_ENABLED", "ARGUS_WHATSAPP_INTAKE_ENABLED"]
)
def test_unlink_ends_the_link_and_unused_codes_while_off(
    wa_client: TestClient, monkeypatch, flag: str
) -> None:
    link_alice(wa_client)
    unused = wa_client.post(CODES, headers=bearer(ALICE)).json()["message_text"]
    monkeypatch.setenv(flag, "false")
    raw = encode(fixture("image_message.json"))
    gated = [
        wa_client.post(CODES, headers=bearer(ALICE)),
        wa_client.get(LINK, headers=bearer(ALICE)),
        wa_client.post(WEBHOOK, content=raw, headers={"X-Hub-Signature-256": sign(raw)}),
    ]
    assert [(r.status_code, r.json()["code"]) for r in gated] == [
        (404, "whatsapp_unavailable")
    ] * 3

    assert wa_client.delete(LINK, headers=bearer(ALICE)).status_code == 204
    assert wa_client.delete(LINK).status_code == 401

    monkeypatch.setenv(flag, "true")
    assert wa_client.get(LINK, headers=bearer(ALICE)).json()["linked"] is False
    post(wa_client, fixture("text_link_code.json", id="wamid.LATE", text=unused))
    assert wa_client.get(LINK, headers=bearer(ALICE)).json()["linked"] is False


def test_verify_challenge(wa_client: TestClient) -> None:
    ok = wa_client.get(
        WEBHOOK,
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": VERIFY_TOKEN,
            "hub.challenge": "1158201444",
        },
    )
    assert (ok.status_code, ok.text) == (200, "1158201444")
    wrong = wa_client.get(
        WEBHOOK,
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "guess",
            "hub.challenge": "1158201444",
        },
    )
    assert wrong.status_code == 403


def test_bad_signature_is_401_before_parsing(
    wa_client: TestClient, graph, identities
) -> None:  # noqa: ANN001
    link_alice(wa_client)
    graph.media["700000000000001"] = Media(RECEIPT_PNG, "image/png")
    garbage = wa_client.post(
        WEBHOOK, content=b"{not json", headers={"X-Hub-Signature-256": "sha256=00"}
    )
    unsigned = wa_client.post(WEBHOOK, content=b"{not json")
    forged = post(
        wa_client,
        fixture("image_message.json", id="wamid.FORGED"),
        signature=sign(b"another body"),
    )
    assert [r.status_code for r in (garbage, unsigned, forged)] == [401, 401, 401]
    assert {r.json()["code"] for r in (garbage, unsigned, forged)} == {
        "whatsapp_webhook_rejected"
    }
    assert graph.requests == []
    alice = identities[ALICE]["id"]
    assert documents_service().hub.connections.list(user_id=alice, scope=PERSONAL) == []


def test_signed_garbage_is_400(wa_client: TestClient) -> None:
    raw = b'{"object": "page"}'
    response = wa_client.post(
        WEBHOOK, content=raw, headers={"X-Hub-Signature-256": sign(raw)}
    )
    assert (response.status_code, response.json()["code"]) == (
        400,
        "whatsapp_webhook_invalid",
    )


def test_link_capture_status_and_revoke_over_http(
    wa_client: TestClient,
    graph,
    identities,  # noqa: ANN001
) -> None:
    issued = wa_client.post(CODES, headers=bearer(ALICE)).json()
    assert issued["message_text"] == f"CUADRAO {issued['code']}"
    assert issued["wa_me_url"] == (
        f"https://wa.me/15550009999?text=CUADRAO%20{issued['code']}"
    )
    assert wa_client.get(LINK, headers=bearer(ALICE)).json() == {
        "linked": False,
        "last4": None,
        "linked_at": None,
        "reply_language": None,
    }
    assert post(
        wa_client, fixture("text_link_code.json", text=issued["message_text"])
    ).json() == {"received": True}
    status = wa_client.get(LINK, headers=bearer(ALICE)).json()
    assert (status["linked"], status["last4"]) == (True, "1234")

    graph.media["700000000000001"] = Media(RECEIPT_PNG, "image/png")
    assert post(wa_client, fixture("image_message.json")).status_code == 200
    assert post(wa_client, fixture("image_message.json")).status_code == 200
    owner = identities[ALICE]["id"]
    business = resolve_business_scope(business_spaces(), owner).owner
    connections = documents_service().hub.connections
    assert connections.list(user_id=owner, scope=PERSONAL) == []
    [connection] = connections.list(user_id=owner, scope=business)
    document = documents_service().get(
        user_id=owner, connection_id=connection.id, scope=business
    )
    assert (document.status, document.consent) == ("saved", False)
    personal = wa_client.get(
        f"/api/v1/financial-documents/{connection.id}", headers=bearer(ALICE)
    )
    assert personal.status_code == 404

    assert wa_client.delete(LINK, headers=bearer(ALICE)).status_code == 204
    assert wa_client.get(LINK, headers=bearer(ALICE)).json()["linked"] is False


def test_guests_cannot_create_link_codes(wa_client: TestClient) -> None:
    assert wa_client.post(CODES, headers=bearer(GUEST)).status_code == 403
    assert wa_client.post(CODES).status_code == 401


def test_unfinished_delivery_answers_503_and_redelivery_resumes(
    wa_client: TestClient,
    graph,
    monkeypatch,
    identities,  # noqa: ANN001
) -> None:
    link_alice(wa_client)
    graph.media["700000000000001"] = Media(RECEIPT_PNG, "image/png")
    destination = whatsapp_runtime().intake.destination
    original = destination.capture
    calls = []

    async def crash_once(**kwargs):  # noqa: ANN003, ANN202
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("process interrupted")
        return await original(**kwargs)

    monkeypatch.setattr(destination, "capture", crash_once)
    first = post(wa_client, fixture("image_message.json"))
    assert (first.status_code, first.json()["code"]) == (503, "whatsapp_webhook_retry")
    assert post(wa_client, fixture("image_message.json")).status_code == 200
    assert post(wa_client, fixture("image_message.json")).status_code == 200
    owner = identities[ALICE]["id"]
    business = resolve_business_scope(business_spaces(), owner).owner
    assert (
        len(documents_service().hub.connections.list(user_id=owner, scope=business)) == 1
    )
    assert len(calls) == 2


def test_logs_carry_no_number_text_or_media_id(
    wa_client: TestClient,
    graph,
    caplog,  # noqa: ANN001
) -> None:
    lines: list[str] = []
    sink = logger.add(
        lambda message: lines.append(str(message)), format="{message} {extra}"
    )
    caplog.set_level("DEBUG")
    try:
        link_alice(wa_client)
        graph.media["700000000000001"] = Media(RECEIPT_PNG, "image/png")
        post(wa_client, fixture("image_message.json"))
        post(wa_client, fixture("text_message.json"))
        post(
            wa_client, fixture("image_message.json", sender="15550109999", id="wamid.X2")
        )
        post(wa_client, fixture("audio_message.json"), signature="sha256=00")
    finally:
        logger.remove(sink)
    captured = "\n".join(lines) + "\n" + caplog.text
    assert "WhatsApp message settled" in captured
    for secret in (
        ALICE_PHONE,
        "15550109999",
        "700000000000001",
        "wamid.",
        "Hola",
        "CUADRAO",
    ):
        assert secret not in captured, secret


@pytest.mark.asyncio
async def test_cloud_api_transport_posts_a_reply_to_the_configured_number() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"messages": [{"id": "wamid.REPLY"}]})

    transport = CloudApiTransport(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        access_token="test-access-token",
        phone_number_id="100000000000001",
        graph_api_version="v23.0",
    )
    await transport.send({"to": "15550101234"})
    [request] = seen
    assert str(request.url) == "https://graph.facebook.com/v23.0/100000000000001/messages"
    assert request.headers["Authorization"] == "Bearer test-access-token"


def test_redelivery_during_a_live_claim_answers_503(wa_client: TestClient, graph) -> None:  # noqa: ANN001
    link_alice(wa_client)
    graph.media["700000000000001"] = Media(RECEIPT_PNG, "image/png")
    intake = whatsapp_runtime().intake
    now = intake.clock()
    intake.store.claim(
        provider_message_key=intake.keys.message("wamid.SYNTHETIC0001"),
        sender_hash=intake.keys.sender(ALICE_PHONE),
        now=now,
        claim_until=now + timedelta(seconds=90),
    )
    response = post(wa_client, fixture("image_message.json"))
    assert (response.status_code, response.json()["code"]) == (
        503,
        "whatsapp_webhook_retry",
    )
    assert graph.requests == []


def test_access_log_redacts_only_the_webhook_query() -> None:
    assert WEBHOOK_PATH in {route.path for route in app.routes}
    access = logging.getLogger("uvicorn.access")

    def line(path: str) -> str:
        record = access.makeRecord(
            "uvicorn.access",
            logging.INFO,
            __file__,
            0,
            '%s - "%s %s HTTP/%s" %d',
            ("127.0.0.1:5000", "GET", path, "1.1", 200),
            None,
        )
        assert all(f.filter(record) for f in access.filters)
        return record.getMessage()

    secret = f"{WEBHOOK_PATH}?hub.mode=subscribe&hub.verify_token={VERIFY_TOKEN}&hub.challenge=1"
    assert line(secret) == (
        f'127.0.0.1:5000 - "GET {WEBHOOK_PATH}?<redacted> HTTP/1.1" 200'
    )
    other = "/api/v1/financial-documents?limit=5"
    assert line(other) == f'127.0.0.1:5000 - "GET {other} HTTP/1.1" 200'


def test_link_code_carries_the_web_language_to_the_link(wa_client: TestClient) -> None:
    refused = wa_client.post(CODES, json={"language": "fr"}, headers=bearer(ALICE))
    assert refused.status_code == 422
    issued = wa_client.post(CODES, json={"language": "en"}, headers=bearer(ALICE))
    assert issued.status_code == 201
    post(wa_client, fixture("text_link_code.json", text=issued.json()["message_text"]))
    assert wa_client.get(LINK, headers=bearer(ALICE)).json()["reply_language"] == "en"

    relink = wa_client.post(CODES, headers=bearer(ALICE)).json()["message_text"]
    post(wa_client, fixture("text_link_code.json", id="wamid.STILL-LINKED", text=relink))
    assert wa_client.get(LINK, headers=bearer(ALICE)).json()["reply_language"] == "en"
    assert wa_client.delete(LINK, headers=bearer(ALICE)).status_code == 204
    relink = wa_client.post(CODES, headers=bearer(ALICE)).json()["message_text"]
    post(wa_client, fixture("text_link_code.json", id="wamid.RELINK", text=relink))
    assert wa_client.get(LINK, headers=bearer(ALICE)).json()["reply_language"] == "es-419"


def test_unlink_answers_503_when_the_link_store_cannot_be_reached(
    wa_client: TestClient, monkeypatch
) -> None:
    import psycopg
    from argus.api.routers import whatsapp as routes

    class Unreachable:
        def revoke(self, **_: object) -> bool:
            raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(routes, "link_store", lambda: Unreachable())
    refused = wa_client.delete(LINK, headers=bearer(ALICE))
    assert (refused.status_code, refused.json()["code"]) == (
        503,
        "whatsapp_link_unavailable",
    )
