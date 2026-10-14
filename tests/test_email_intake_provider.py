import base64
import hashlib
import hmac
from uuid import uuid4

import httpx
import pytest
from argus.domain.ingestion.email_intake.provider import (
    EmailProviderError,
    ResendReceivingClient,
)
from argus.domain.ingestion.email_intake.signatures import (
    WebhookSignatureError,
    verify_webhook,
)

EMAIL_ID = str(uuid4())
HOST = "cdn.resend.app"
RAW = b"To: forged@example.test\r\n\r\nOriginal bytes\x00\xff"


def metadata(url=f"https://{HOST}/raw?Signature=test"):
    return {"id": EMAIL_ID, "to": ["recibos@example.test"], "raw": {"download_url": url}}


@pytest.mark.asyncio
async def test_exact_bytes_and_credentials_only_sent_to_api():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.host == "api.resend.com":
            return httpx.Response(200, json=metadata())
        return httpx.Response(200, content=RAW)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers={"Authorization": "client-secret", "Cookie": "private=secret"},
        auth=("user", "pass"),
        follow_redirects=True,
    ) as client:
        result = await ResendReceivingClient(client, "test-key", (HOST,)).raw_message(
            EMAIL_ID
        )
    assert result.raw == RAW
    assert result.recipients == ("recibos@example.test",)
    assert requests[0].headers["authorization"] == "Bearer test-key"
    assert "authorization" not in requests[1].headers
    assert "cookie" not in requests[1].headers
    assert requests[0].url.params["html_format"] == "cid"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        f"http://{HOST}/raw",
        "https://127.0.0.1/raw",
        "https://[::1]/raw",
        "https://localhost/raw",
        f"https://{HOST}.evil.test/raw",
        f"https://user:pass@{HOST}/raw",
        f"https://{HOST}:444/raw",
        f"https://{HOST}/raw#fragment",
    ],
)
async def test_unsafe_download_url_never_requested(url):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=metadata(url))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(EmailProviderError, match="unsafe_download_url"):
            await ResendReceivingClient(
                client, "key", (HOST, "127.0.0.1", "::1", "localhost")
            ).raw_message(EMAIL_ID)
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,retryable",
    [(301, False), (403, False), (404, False), (408, True), (429, True), (503, True)],
)
async def test_status_and_redirects_fail_closed(status, retryable):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, headers={"location": "http://127.0.0.1/secrets"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=True
    ) as client:
        with pytest.raises(EmailProviderError) as failure:
            await ResendReceivingClient(client, "key", (HOST,)).raw_message(EMAIL_ID)
    assert failure.value.retryable is retryable
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("length_header", [True, False])
async def test_oversize_bounded_with_or_without_length(monkeypatch, length_header):
    monkeypatch.setattr(
        "argus.domain.ingestion.email_intake.provider.SOURCE_MAX_BYTES", 256
    )

    class Chunks(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"x" * 128
            yield b"x" * 129
            raise AssertionError("must stop reading after size limit")

    def handler(request):
        return httpx.Response(
            200,
            stream=Chunks(),
            headers={"content-length": "257"} if length_header else {},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(EmailProviderError, match="provider_response_too_large"):
            await ResendReceivingClient(client, "key", (HOST,)).raw_message(EMAIL_ID)


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["../secret", "not-uuid", EMAIL_ID.replace("-", "")])
async def test_invalid_identifier_without_request(value):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: pytest.fail("no request"))
    ) as client:
        with pytest.raises(EmailProviderError, match="invalid_email_id"):
            await ResendReceivingClient(client, "key", (HOST,)).raw_message(value)


@pytest.mark.asyncio
async def test_metadata_must_name_the_same_message_and_real_recipients():
    bad = [
        {**metadata(), "id": str(uuid4())},
        {**metadata(), "to": []},
        {**metadata(), "to": ["x" * 321]},
        {"id": EMAIL_ID, "to": ["a@b.test"], "raw": {}},
    ]
    for body in bad:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _, body=body: httpx.Response(200, json=body)
            )
        ) as client:
            with pytest.raises(EmailProviderError, match="invalid_provider_metadata"):
                await ResendReceivingClient(client, "key", (HOST,)).raw_message(EMAIL_ID)


def signed_headers(body, now=1700000000):
    key = b"synthetic-secret"
    signature = base64.b64encode(
        hmac.digest(key, f"msg_test.{now}.".encode() + body, hashlib.sha256)
    ).decode()
    return "whsec_" + base64.b64encode(key).decode(), {
        "svix-id": "msg_test",
        "svix-timestamp": str(now),
        "svix-signature": "v1," + signature,
    }


def test_signature_matches_only_unchanged_bytes_within_the_window():
    body = b'{"type":"email.received"}'
    secret, headers = signed_headers(body)
    verify_webhook(body, headers, secret, 1700000000 + 100)
    verify_webhook(body, {k.upper(): v for k, v in headers.items()}, secret, 1700000000)
    with pytest.raises(WebhookSignatureError):
        verify_webhook(body + b" ", headers, secret, 1700000000)
    with pytest.raises(WebhookSignatureError):
        verify_webhook(body, headers, secret, 1700000000 + 301)
    with pytest.raises(WebhookSignatureError):
        verify_webhook(body, {**headers, "svix-signature": "v1,AAAA"}, secret, 1700000000)
    with pytest.raises(WebhookSignatureError):
        verify_webhook(
            body, {k: v for k, v in headers.items() if k != "svix-id"}, secret, 1700000000
        )
    with pytest.raises(WebhookSignatureError):
        verify_webhook(
            body, headers, "whsec_" + base64.b64encode(b"other").decode(), 1700000000
        )


def test_signature_accepts_one_valid_among_several_and_ignores_unknown_versions():
    body = b"{}"
    secret, headers = signed_headers(body)
    headers["svix-signature"] = "v0,AAAA " + headers["svix-signature"] + " v1,BBBB"
    verify_webhook(body, headers, secret, 1700000000)
