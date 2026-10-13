"""A failed Graph call says which step failed, the HTTP status and Graph's error
code and type, never the message, the media id, a URL or a token."""

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


@pytest.fixture
def records():
    seen = []
    sink = logger.add(lambda message: seen.append(message.record), level="WARNING")
    yield seen
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


@pytest.mark.asyncio
async def test_nothing_hostile_in_a_graph_error_reaches_a_log_record(records) -> None:
    media = _media(lambda request: httpx.Response(400, json=HOSTILE))
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
    for forbidden in (TOKEN, "evil.example", "700000000000009", "700000000000003"):
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
async def test_the_acknowledgement_failure_log_line_has_exactly_its_fields(
    records,
) -> None:
    from argus.domain.ingestion.whatsapp.replies import ReplyFailed

    from tests.ingestion import whatsapp_cases as cases
    from tests.ingestion.test_whatsapp_intake import _world
    from tests.ingestion.whatsapp_support import ALICE_PHONE, RECEIPT_PNG, Media

    class Refused:
        async def send(self, payload):  # noqa: ANN001, ANN201
            raise ReplyFailed("401:190")

    world = _world()
    await world.link(world.alice, ALICE_PHONE)
    world.intake.transport = Refused()
    world.graph.media["700000000000301"] = Media(RECEIPT_PNG, "image/png")
    del records[:]
    await world.deliver(cases.image("700000000000301", "wamid.ACK-FAIL"))
    [record] = [r for r in records if r["message"] == "WhatsApp acknowledgement not sent"]
    assert set(record["extra"]) == {"message_ref", "sender_ref", "failure_mode"}
    assert record["extra"]["failure_mode"] == "401:190"
