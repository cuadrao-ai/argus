"""A failed Graph call says which step failed, the HTTP status and Graph's error
code and type, never the message, the media id, a URL or a token."""

from io import StringIO

import httpx
import pytest
from argus.domain.ingestion.whatsapp.media import GraphMedia, MediaUnavailable
from argus.domain.ingestion.whatsapp.replies import CloudApiTransport, ReplyFailed
from loguru import logger

EXPIRED = {
    "error": {
        "message": "Error validating access token: Session has expired SECRETWORDS",
        "type": "OAuthException",
        "code": 190,
        "error_subcode": 463,
    }
}
TOKEN = "synthetic-token-value"


def failed_delivery(*, number: str = "100000000000001", code: object = 131026) -> bytes:
    import json

    return json.dumps(
        {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "metadata": {"phone_number_id": number},
                                "statuses": [
                                    {
                                        "id": "wamid.PRIVATE",
                                        "recipient_id": "15550109999",
                                        "status": "failed",
                                        "errors": [
                                            {
                                                "code": code,
                                                "message": f"SECRETWORDS {TOKEN}",
                                            }
                                        ],
                                    }
                                ],
                            },
                        }
                    ]
                }
            ],
        }
    ).encode()


def test_failed_delivery_keeps_only_safe_actionable_diagnostics() -> None:
    from argus.domain.ingestion.whatsapp.payload import parse_delivery

    delivery = parse_delivery(failed_delivery(), phone_number_id="100000000000001")
    assert delivery.statuses == 1
    assert [(failure.code, failure.reason) for failure in delivery.failures] == [
        ("131026", "undeliverable")
    ]
    assert delivery.messages == ()
    for secret in ("wamid.PRIVATE", "15550109999", "SECRETWORDS", TOKEN):
        assert secret not in repr(delivery)


@pytest.mark.parametrize("code", [True, None, {}, "SECRETWORDS", "7" * 11, "١٩٠"])
def test_malformed_delivery_codes_never_become_diagnostic_text(code: object) -> None:
    from argus.domain.ingestion.whatsapp.payload import parse_delivery

    delivery = parse_delivery(
        failed_delivery(code=code), phone_number_id="100000000000001"
    )
    assert [(failure.code, failure.reason) for failure in delivery.failures] == [
        (None, "delivery_failed")
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "signed,number,http_status,events",
    [
        (True, "100000000000001", 200, 1),
        (True, "100000000000002", 200, 0),
        (False, "100000000000001", 401, 0),
    ],
)
async def test_delivery_failure_event_requires_signature_and_receiving_number(
    records, signed: bool, number: str, http_status: int, events: int
) -> None:
    from types import SimpleNamespace

    from argus.api.routers.whatsapp import webhook_router
    from argus.api.whatsapp import require_whatsapp_surface
    from fastapi import FastAPI
    from pydantic import SecretStr

    from tests.ingestion.test_whatsapp_intake import _world
    from tests.ingestion.whatsapp_support import APP_SECRET, sign

    world = _world()
    app = FastAPI()

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = "synthetic-request"
        return await call_next(request)

    app.include_router(webhook_router)
    app.dependency_overrides[require_whatsapp_surface] = lambda: SimpleNamespace(
        settings=SimpleNamespace(
            app_secret=SecretStr(APP_SECRET), phone_number_id="100000000000001"
        ),
        intake=world.intake,
    )
    body = failed_delivery(number=number)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={"X-Hub-Signature-256": sign(body) if signed else "sha256=invalid"},
        )
    assert response.status_code == http_status
    observed = [
        record
        for record in records
        if record["extra"].get("event") == "whatsapp_delivery_failed"
    ]
    assert len(observed) == events
    if observed:
        assert "code=131026 reason=undeliverable" in observed[0]["message"]
        assert observed[0]["extra"] == {
            "event": "whatsapp_delivery_failed",
            "graph_code": "131026",
            "failure_reason": "undeliverable",
        }
    for secret in ("wamid.PRIVATE", "15550109999", "SECRETWORDS", TOKEN):
        assert secret not in str(records)


@pytest.fixture
def records():
    seen = []
    sink = logger.add(lambda message: seen.append(message.record), level="WARNING")
    yield seen
    logger.remove(sink)


@pytest.fixture
def plain_sink():
    output = StringIO()
    sink = logger.add(output, level="WARNING")
    yield output
    logger.remove(sink)


def _media(handler):  # noqa: ANN001, ANN202
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return GraphMedia(
        client=client, access_token=TOKEN, graph_api_version="v23.0", max_bytes=10_000_000
    )


@pytest.mark.asyncio
async def test_an_expired_token_is_named_by_its_graph_code(records) -> None:
    media = _media(lambda request: httpx.Response(401, json=EXPIRED))
    with pytest.raises(MediaUnavailable) as failed:
        await media.fetch("700000000000001")
    assert failed.value.code == "whatsapp_media_unavailable"
    [record] = records
    extra = record["extra"]
    assert (extra["step"], extra["reason"], extra["http_status"]) == (
        "locate",
        "status",
        401,
    )
    assert (extra["graph_code"], extra["graph_error_subcode"], extra["graph_type"]) == (
        "190",
        "463",
        "OAuthException",
    )
    everything = str(record)
    assert "SECRETWORDS" not in everything
    assert TOKEN not in everything and "700000000000001" not in everything


@pytest.mark.asyncio
async def test_a_failed_download_names_its_step_and_status(records) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "graph.facebook.com":
            return httpx.Response(
                200,
                json={
                    "url": "https://lookaside.fbsbx.com/whatsapp_business/a",
                    "mime_type": "image/png",
                    "file_size": 10,
                },
            )
        return httpx.Response(403)

    with pytest.raises(MediaUnavailable):
        await _media(handler).fetch("700000000000002")
    [record] = records
    assert (record["extra"]["step"], record["extra"]["http_status"]) == ("download", 403)
    assert "lookaside" not in str(record)


@pytest.mark.asyncio
async def test_a_failed_reply_carries_status_and_graph_code() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(401, json=EXPIRED))
    )
    transport = CloudApiTransport(
        client=client,
        access_token=TOKEN,
        phone_number_id="100000000000001",
        graph_api_version="v23.0",
    )
    with pytest.raises(ReplyFailed) as failed:
        await transport.send({"to": "15550101234"})
    assert str(failed.value) == "401:190"


HOSTILE = {
    "error": {
        "message": f"token {TOKEN} for 700000000000009 at https://evil.example/x?t=abc",
        "type": f"https://evil.example/x?token={TOKEN} 700000000000009",
        "code": f"sk-{TOKEN}",
        "error_subcode": "7" * 40,
    }
}

HOSTILE_LOG_FIELDS = {
    "error": {
        "message": f"token {TOKEN} for 700000000000009 at https://evil.example/x?t=abc",
        "type": "Q" * 26,
        "code": "7000000000",
        "error_subcode": "1555012345",
    }
}


@pytest.mark.asyncio
async def test_nothing_hostile_in_a_graph_error_reaches_a_log_record(records) -> None:
    media = _media(lambda request: httpx.Response(400, json=HOSTILE_LOG_FIELDS))
    with pytest.raises(MediaUnavailable):
        await media.fetch("700000000000003")
    [record] = records
    assert [
        record["extra"][k] for k in ("graph_code", "graph_error_subcode", "graph_type")
    ] == [
        "unknown",
        "unknown",
        "unknown",
    ]
    text = str(record)
    for forbidden in (
        TOKEN,
        "evil.example",
        "700000000000009",
        "700000000000003",
        "7000000000",
        "1555012345",
        "Q" * 26,
    ):
        assert forbidden not in text


@pytest.mark.asyncio
async def test_a_hostile_graph_code_never_reaches_the_reply_failure() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(400, json=HOSTILE))
    )
    transport = CloudApiTransport(
        client=client,
        access_token=TOKEN,
        phone_number_id="100000000000001",
        graph_api_version="v23.0",
    )
    with pytest.raises(ReplyFailed) as failed:
        await transport.send({"to": "15550101234"})
    assert str(failed.value) == "400:unknown"


@pytest.mark.asyncio
async def test_plain_media_log_shows_safe_graph_failure_fields(plain_sink) -> None:
    media = _media(lambda request: httpx.Response(401, json=EXPIRED))
    with pytest.raises(MediaUnavailable):
        await media.fetch("700000000000006")

    text = plain_sink.getvalue()
    assert "step=locate" in text
    assert "reason=status" in text
    assert "http_status=401" in text
    assert "graph_code=190" in text
    assert "graph_error_subcode=463" in text
    assert "graph_type=OAuthException" in text
    for forbidden in (TOKEN, "SECRETWORDS", "700000000000006"):
        assert forbidden not in text


@pytest.mark.asyncio
async def test_plain_media_log_hides_hostile_graph_payload(plain_sink) -> None:
    media = _media(lambda request: httpx.Response(400, json=HOSTILE_LOG_FIELDS))
    with pytest.raises(MediaUnavailable):
        await media.fetch("700000000000007")

    text = plain_sink.getvalue()
    assert "step=locate" in text and "reason=status" in text
    assert "graph_code=unknown" in text
    assert "graph_error_subcode=unknown" in text
    assert "graph_type=unknown" in text
    for forbidden in (
        TOKEN,
        "evil.example",
        "700000000000009",
        "700000000000007",
        "7000000000",
        "1555012345",
        "Q" * 26,
    ):
        assert forbidden not in text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code,message,cause",
    [
        (0, "Unable to authenticate app user", "authentication_failed"),
        (3, "Capability or permissions issue", "capability_or_permissions"),
        (10, "Permission is either not granted TOKEN", "permission_required"),
        (100, "(#100) Invalid parameter SECRETWORDS", "ambiguous"),
        (104, "Access token error SECRETWORDS", "ambiguous"),
        (200, "Provide valid app ID", "access_token_missing"),
        (200, f"Provide valid app ID {TOKEN}", "unknown"),
        (131005, "Permission is either not granted TOKEN", "permission_required"),
        (131008, "Request is missing a required parameter", "required_parameter_missing"),
        (131009, "One or more parameter values are invalid", "invalid_parameter"),
        (190, "Your access token has expired", "token_invalid_or_expired"),
        (131026, "Unable to deliver message", "undeliverable"),
    ],
)
async def test_provider_error_codes_have_bounded_causes_in_both_sinks(
    records, plain_sink, code: int, message: str, cause: str
) -> None:
    response = {
        "error": {
            "message": (
                message
                if code == 200
                else f"{message} for 700000000000011 https://evil.example/x?token={TOKEN}"
            ),
            "type": "OAuthException",
            "code": code,
            "fbtrace_id": f"{TOKEN} 700000000000011 https://evil.example/x",
        }
    }
    with pytest.raises(MediaUnavailable):
        await _media(lambda request: httpx.Response(400, json=response)).fetch(
            "700000000000012"
        )

    [record] = records
    assert record["extra"]["graph_code"] == str(code)
    assert record["extra"]["graph_cause"] == cause
    assert f"graph_cause={cause}" in plain_sink.getvalue()
    for secret in ("SECRETWORDS", TOKEN, "evil.example", "700000000000011", "700000000000012"):
        assert secret not in str(record)
        assert secret not in plain_sink.getvalue()


@pytest.mark.asyncio
async def test_unknown_provider_error_code_stays_unknown_in_both_sinks(
    records, plain_sink
) -> None:
    response = {
        "error": {
            "message": f"raw {TOKEN} 700000000000013 https://evil.example/?id=abc",
            "type": "OAuthException",
            "code": 7000000000,
        }
    }
    with pytest.raises(MediaUnavailable):
        await _media(lambda request: httpx.Response(400, json=response)).fetch(
            "700000000000014"
        )

    [record] = records
    assert record["extra"]["graph_code"] == "unknown"
    assert record["extra"]["graph_cause"] == "unknown"
    assert "graph_cause=unknown" in plain_sink.getvalue()
    for secret in (TOKEN, "evil.example", "700000000000013", "700000000000014", "7000000000"):
        assert secret not in str(record)
        assert secret not in plain_sink.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "graph_type,message,cause",
    [
        (
            "GraphMethodException",
            "Invalid appsecret_proof provided in the API argument",
            "appsecret_proof_invalid",
        ),
        (
            "OAuthException",
            "Invalid appsecret_proof provided in the API argument",
            "appsecret_proof_invalid",
        ),
        (
            "GraphMethodException",
            f"Invalid appsecret_proof provided in the API argument {TOKEN}",
            "ambiguous",
        ),
        (
            "OAuthException",
            f"Invalid appsecret_proof provided in the API argument {TOKEN}",
            "ambiguous",
        ),
    ],
)
async def test_code_100_uses_only_the_exact_known_appsecret_proof_message(
    records, plain_sink, graph_type: str, message: str, cause: str
) -> None:
    response = {
        "error": {
            "message": message,
            "type": graph_type,
            "code": 100,
            "fbtrace_id": f"{TOKEN} 700000000000015 https://evil.example/x",
        }
    }
    with pytest.raises(MediaUnavailable):
        await _media(lambda request: httpx.Response(400, json=response)).fetch(
            "700000000000016"
        )

    [record] = records
    assert record["extra"]["graph_code"] == "100"
    assert record["extra"]["graph_type"] == graph_type
    assert record["extra"]["graph_cause"] == cause
    assert f"graph_cause={cause}" in plain_sink.getvalue()
    for secret in (TOKEN, "700000000000015", "700000000000016", "evil.example"):
        assert secret not in str(record)
        assert secret not in plain_sink.getvalue()


@pytest.mark.asyncio
async def test_malformed_provider_type_keeps_code_100_ambiguous(records, plain_sink) -> None:
    response = {
        "error": {
            "message": "Invalid appsecret_proof provided in the API argument",
            "type": [],
            "code": 100,
        }
    }
    with pytest.raises(MediaUnavailable):
        await _media(lambda request: httpx.Response(400, json=response)).fetch(
            "700000000000017"
        )

    [record] = records
    assert record["extra"]["graph_code"] == "100"
    assert "graph_type" not in record["extra"]
    assert record["extra"]["graph_cause"] == "ambiguous"
    assert "graph_cause=ambiguous" in plain_sink.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure,expected",
    [
        ("download_status", "step=download reason=status http_status=403"),
        ("locate_transport", "step=locate reason=transport"),
        ("locate_payload", "step=locate reason=payload"),
    ],
)
async def test_plain_media_log_names_step_and_bounded_failure(
    plain_sink, failure: str, expected: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "locate_transport":
            raise httpx.ConnectError(f"{TOKEN} SECRETWORDS", request=request)
        if request.url.host == "graph.facebook.com":
            if failure == "locate_payload":
                return httpx.Response(200, json={"token": TOKEN})
            return httpx.Response(
                200,
                json={
                    "url": "https://lookaside.fbsbx.com/whatsapp_business/synthetic",
                    "mime_type": "image/png",
                    "file_size": 10,
                },
            )
        return httpx.Response(403)

    with pytest.raises(MediaUnavailable):
        await _media(handler).fetch("700000000000008")

    text = plain_sink.getvalue()
    assert expected in text
    for forbidden in (TOKEN, "SECRETWORDS", "700000000000008"):
        assert forbidden not in text


@pytest.mark.asyncio
async def test_acknowledgement_log_formats_only_sanitized_provider_failure(
    records, plain_sink
) -> None:
    from argus.domain.ingestion.whatsapp.replies import ReplyFailed

    from tests.ingestion import whatsapp_cases as cases
    from tests.ingestion.test_whatsapp_intake import _world
    from tests.ingestion.whatsapp_support import ALICE_PHONE, RECEIPT_PNG, Media

    class Refused:
        async def send(self, payload):  # noqa: ANN001, ANN201
            raise ReplyFailed(f"401:190 {TOKEN} SECRETWORDS https://evil.example/x")

    world = _world()
    await world.link(world.alice, ALICE_PHONE)
    world.intake.transport = Refused()
    world.graph.media["700000000000301"] = Media(RECEIPT_PNG, "image/png")
    del records[:]
    await world.deliver(cases.image("700000000000301", "wamid.ACK-FAIL"))
    [record] = [
        r
        for r in records
        if r["message"].startswith("WhatsApp acknowledgement not sent:")
    ]
    assert record["extra"]["failure_mode"] == "unknown"
    assert record["extra"]["outcome"] == "known"
    text = plain_sink.getvalue()
    assert "failure_mode=unknown" in text
    assert "outcome=known" in text
    for forbidden in (TOKEN, "SECRETWORDS", "evil.example", "15550101234"):
        assert forbidden not in text


@pytest.mark.asyncio
async def test_acknowledgement_log_classifies_provider_and_transport_failures(
    plain_sink,
) -> None:
    from argus.domain.ingestion.whatsapp.replies import ReplyFailed

    from tests.ingestion import whatsapp_cases as cases
    from tests.ingestion.test_whatsapp_intake import _world
    from tests.ingestion.whatsapp_support import ALICE_PHONE, RECEIPT_PNG, Media

    class Refused:
        def __init__(self, reason: str, *, outcome_unknown: bool = False) -> None:
            self.reason = reason
            self.outcome_unknown = outcome_unknown

        async def send(self, payload):  # noqa: ANN001, ANN201
            raise ReplyFailed(self.reason, outcome_unknown=self.outcome_unknown)

    world = _world()
    await world.link(world.alice, ALICE_PHONE)
    world.graph.media["700000000000302"] = Media(RECEIPT_PNG, "image/png")
    world.intake.transport = Refused("401:190")
    await world.deliver(cases.image("700000000000302", "wamid.ACK-PROVIDER"))

    world.graph.media["700000000000303"] = Media(RECEIPT_PNG, "image/png")
    world.intake.transport = Refused("transport", outcome_unknown=True)
    await world.deliver(cases.image("700000000000303", "wamid.ACK-TRANSPORT"))

    text = plain_sink.getvalue()
    assert "failure_mode=provider_rejection" in text
    assert "http_status=401" in text and "graph_code=190" in text
    assert "failure_mode=transport" in text
    assert "outcome=unknown" in text
    for forbidden in (TOKEN, "15550101234", "wamid.ACK-"):
        assert forbidden not in text


@pytest.mark.asyncio
async def test_acknowledgement_log_hides_unrecognized_numeric_code(records, plain_sink) -> None:
    from argus.domain.ingestion.whatsapp.replies import ReplyFailed

    from tests.ingestion import whatsapp_cases as cases
    from tests.ingestion.test_whatsapp_intake import _world
    from tests.ingestion.whatsapp_support import ALICE_PHONE, RECEIPT_PNG, Media

    code = "7000000000"

    class Refused:
        async def send(self, payload):  # noqa: ANN001, ANN201
            raise ReplyFailed(f"401:{code}")

    world = _world()
    await world.link(world.alice, ALICE_PHONE)
    world.intake.transport = Refused()
    world.graph.media["700000000000309"] = Media(RECEIPT_PNG, "image/png")
    del records[:]
    await world.deliver(cases.image("700000000000309", "wamid.ACK-HOSTILE"))

    [record] = [
        row
        for row in records
        if row["message"].startswith("WhatsApp acknowledgement not sent:")
    ]
    assert record["extra"]["failure_mode"] == "provider_rejection"
    assert record["extra"]["http_status"] == 401
    assert record["extra"]["graph_code"] == "unknown"
    text = plain_sink.getvalue()
    assert "failure_mode=provider_rejection" in text
    assert "http_status=401 graph_code=unknown" in text
    assert code not in text and code not in str(record)


@pytest.mark.asyncio
async def test_successful_media_fetch_keeps_accepted_bytes_and_type() -> None:
    content = b"%PDF-1.7 synthetic receipt"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "graph.facebook.com":
            return httpx.Response(
                200,
                json={
                    "url": "https://lookaside.fbsbx.com/whatsapp_business/synthetic",
                    "mime_type": "application/pdf",
                    "file_size": len(content),
                },
            )
        return httpx.Response(200, content=content)

    fetched = await _media(handler).fetch("700000000000304")
    assert fetched.content == content
    assert fetched.mime_type == "application/pdf"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure,expected_calls",
    [
        ("transport_identity", 1),
        ("transport_media", 2),
        ("invalid_json", 1),
        ("redirect", 1),
        ("status", 1),
        ("ambiguous_identity", 1),
        ("wrong_app", 1),
        ("wrong_subject", 1),
        ("invalid", 1),
        ("unknown_type", 1),
        ("error_media", 2),
        ("bad_metadata", 2),
        ("hostile_trace", 1),
        ("success", 2),
    ],
)
async def test_private_probe_is_two_gets_max_no_retry_download_or_secret_leak(
    failure,
    expected_calls,
    records,
    caplog,
):
    import json
    import logging
    import time
    from unittest.mock import AsyncMock

    calls = []
    secret = "synthetic-private-header-token"

    def handler(request):
        calls.append(request)
        assert request.method == "GET"
        assert request.headers["Authorization"] == f"Bearer {secret}"
        assert request.url.host == "graph.facebook.com"
        if len(calls) == 1:
            assert request.url.path == "/v23.0/debug_token"
            assert request.url.params["input_token"] == secret
            if failure == "transport_identity":
                raise httpx.ReadTimeout(f"PRIVATE_RAW {request.url}")
            if failure == "invalid_json":
                return httpx.Response(200, content=b"PRIVATE_RAW")
            if failure == "redirect":
                return httpx.Response(302, headers={"location": "https://evil.example"})
            if failure == "status":
                return httpx.Response(400, json={"error": {"message": secret}})
            if failure == "hostile_trace":
                return httpx.Response(400, json={"error": {"fbtrace_id": secret}})
            data = {
                "is_valid": failure != "invalid",
                "type": "SYSTEM_USER",
                "app_id": "800000000000001",
                "user_id": "900000000000001",
                "scopes": ["whatsapp_business_messaging", "PRIVATE_RAW"],
                "expires_at": 0,
                "unexpected": secret,
            }
            if failure == "wrong_app":
                data["app_id"] = "800000000000002"
            if failure == "wrong_subject":
                data["user_id"] = "900000000000002"
            if failure == "unknown_type":
                data["type"] = secret
            if failure == "ambiguous_identity":
                return httpx.Response(200, json={"data": data, "error": {"code": 190}})
            return httpx.Response(200, json={"data": data})
        assert request.url.path == "/v23.0/700000000000001"
        assert not request.url.query
        if failure == "transport_media":
            raise httpx.ConnectError(f"PRIVATE_RAW {secret}")
        if failure == "error_media":
            return httpx.Response(
                400,
                json={
                    "error": {
                        "code": 10,
                        "error_subcode": 463,
                        "type": "OAuthException",
                        "message": f"PRIVATE_RAW {secret}",
                        "fbtrace_id": "trace_SYNTHETIC",
                    }
                },
                headers={
                    "x-fb-request-id": "request_SYNTHETIC",
                    "x-fb-trace-id": "https://evil.example",
                },
            )
        return httpx.Response(
            200,
            json={
                "id": "700000000000001",
                "mime_type": "application/pdf",
                "file_size": -1 if failure == "bad_metadata" else 20,
                "url": f"https://evil.example/PRIVATE_SIGNED_URL?t={secret}",
            },
        )

    caplog.set_level(logging.DEBUG, logger="httpx")
    caplog.set_level(logging.DEBUG, logger="httpcore")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        media = GraphMedia(
            client=client, access_token=secret, graph_api_version="v23.0", max_bytes=1000
        )
        media.fetch = AsyncMock(side_effect=AssertionError("fetch forbidden"))
        media._download = AsyncMock(side_effect=AssertionError("download forbidden"))
        result = await media.diagnose_once(
            media_id="700000000000001",
            app_id="800000000000001",
            subject_id="900000000000001",
            runtime_token=secret,
            selected_token="different-settings-token",
            expires_at=int(time.time()) + 100,
        )
        assert len(calls) == expected_calls
        assert result["get_attempts"] == expected_calls
        media.fetch.assert_not_called()
        media._download.assert_not_called()
    if failure == "error_media":
        assert result["media"]["code"] == "10"
        assert result["media"]["error_subcode"] == "463"
        assert result["media"]["type"] == "OAuthException"
        assert result["media"]["cause"] == "permission_required"
        assert result["media"]["request_id"] == "request_SYNTHETIC"
        assert result["media"]["trace_id"] == "trace_SYNTHETIC"
    if failure == "bad_metadata":
        assert result["media"]["matched"] is False
    if failure == "success":
        assert result["media"]["matched"] is True
    everything = json.dumps(result) + str(records) + caplog.text
    for value in (
        secret,
        "different-settings-token",
        "PRIVATE_RAW",
        "PRIVATE_SIGNED_URL",
        "evil.example",
        "input_token",
    ):
        assert value not in everything


@pytest.mark.asyncio
async def test_probe_cannot_make_second_get_after_expiry(monkeypatch):
    calls = []
    now = [100]

    def handler(request):
        calls.append(request)
        now[0] = 200
        return httpx.Response(
            200,
            json={
                "data": {
                    "is_valid": True,
                    "type": "SYSTEM_USER",
                    "app_id": "800000000000001",
                    "user_id": "900000000000001",
                }
            },
        )

    monkeypatch.setattr("argus.domain.ingestion.whatsapp.media.time.time", lambda: now[0])
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        media = GraphMedia(
            client=client, access_token=TOKEN, graph_api_version="v23.0", max_bytes=1000
        )
        result = await media.diagnose_once(
            media_id="700000000000001",
            app_id="800000000000001",
            subject_id="900000000000001",
            runtime_token=TOKEN,
            selected_token=TOKEN,
            expires_at=150,
        )
    assert len(calls) == 1
    assert result["outcome"] == "expired"
