"""The signed webhook acknowledges a photo only once its recovery envelope is
sealed. Without a codec, or when sealing fails, it answers a retryable 503 and
commits nothing, so the provider's redelivery is the recovery."""

import pytest
from argus.api.whatsapp import whatsapp_runtime
from fastapi.testclient import TestClient

from tests.ingestion.test_whatsapp_api import graph, link_alice, post, wa_client
from tests.ingestion.whatsapp_support import RECEIPT_PNG, Media, fixture

__all__ = ["graph", "wa_client"]


class Breaks:
    def seal(self, message):  # noqa: ANN001, ANN201
        raise RuntimeError("sealing failed")


@pytest.mark.parametrize("codec", [None, Breaks()], ids=["codec_absent", "seal_fails"])
def test_an_unsealed_photo_is_not_acknowledged_and_redelivery_captures_once(
    wa_client: TestClient,
    graph,  # noqa: ANN001
    codec,  # noqa: ANN001
) -> None:
    link_alice(wa_client)
    intake = whatsapp_runtime().intake
    graph.media["700000000000001"] = Media(RECEIPT_PNG, "image/png")
    sealing, intake.claim_codec = intake.claim_codec, codec
    assert sealing is not None

    first = post(wa_client, fixture("image_message.json"))
    assert (first.status_code, first.json()["code"]) == (503, "whatsapp_webhook_retry")
    [message] = fixture("image_message.json")["entry"][0]["changes"][0]["value"][
        "messages"
    ]
    key = intake.keys.message(message["id"])
    assert intake.store.inbound(key) is None
    assert graph.requests == []

    # Text still flows without a codec, and an unlinked sender still gets nothing.
    assert post(wa_client, fixture("text_message.json")).status_code == 200
    stranger = fixture("image_message.json", sender="15550109999", id="wamid.S1")
    assert post(wa_client, stranger).status_code == 503

    intake.claim_codec = sealing
    assert post(wa_client, fixture("image_message.json")).status_code == 200
    assert intake.store.inbound(key).status == "captured"
    fetched = len(graph.requests)

    # A replay of the settled photo stays deduplicated, codec or not.
    intake.claim_codec = codec
    assert post(wa_client, fixture("image_message.json")).status_code == 200
    intake.claim_codec = sealing
    assert post(wa_client, fixture("image_message.json")).status_code == 200
    assert len(graph.requests) == fetched
