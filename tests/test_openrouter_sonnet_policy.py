from __future__ import annotations

import httpx
import pytest
from argus.llm import openrouter
from argus.llm import openrouter_model_env as model_policy

SONNET = model_policy.SONNET_5_5_MODEL
PAYLOAD = {
    "model": SONNET,
    "messages": [{"role": "user", "content": "fictional"}],
    "reasoning": {"effort": "low", "exclude": True},
}
ATTEMPT = ("chat_composer", 25.0, SONNET, "json_schema", "probe", None)


@pytest.mark.asyncio
async def test_async_sonnet_http400_never_strips_reasoning() -> None:
    requests = []

    def reject(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(400, json={"error": {"message": "invalid"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(reject)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await openrouter._post_openrouter_json_schema(
                client=client,
                api_key="synthetic",
                payload=PAYLOAD,
                retry_attempt=ATTEMPT,
            )
    assert len(requests) == 1
    assert model_policy.can_retry_without_reasoning(PAYLOAD) is False


def test_sync_sonnet_http400_never_strips_reasoning() -> None:
    requests = []

    def reject(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(400, json={"error": {"message": "invalid"}})

    with httpx.Client(transport=httpx.MockTransport(reject)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            openrouter._post_openrouter_json_schema_sync(
                client=client,
                api_key="synthetic",
                payload=PAYLOAD,
                retry_attempt=ATTEMPT,
            )
    assert len(requests) == 1
    assert (
        model_policy.can_retry_without_reasoning(
            {**PAYLOAD, "model": "anthropic/claude-haiku-5.5"}
        )
        is True
    )
