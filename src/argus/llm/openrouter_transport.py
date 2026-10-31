from __future__ import annotations

from collections.abc import Callable
from typing import Literal

import httpx

from argus.llm import openrouter_model_env as model_policy
from argus.llm.openrouter_request_policy import guard_openrouter_request as _guard_request
from argus.llm.openrouter_retention import check_retention_response
from argus.llm.openrouter_tasks import OpenRouterTask
from argus.llm.provider_permit import ProviderCallPermit

OpenRouterRetryAttempt = tuple[OpenRouterTask, float, str, Literal["json_schema", "chat_model"], str | None, list[str] | None]


async def _post_openrouter_json_schema(
    *,
    client: httpx.AsyncClient,
    api_key: str,
    payload: dict[str, object],
    retry_attempt: OpenRouterRetryAttempt,
    reserve_attempt: Callable[..., ProviderCallPermit | None],
) -> httpx.Response | None:
    response = await client.post(
        "https://openrouter.ai/api/v1/chat/completions", headers=_openrouter_headers(api_key), json=_guard_request(retry_attempt[0], payload)
    )
    try:
        check_retention_response(response, str(payload["model"]))
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 400 or not model_policy.can_retry_without_reasoning(payload):
            raise
        if (permit := reserve_attempt(*retry_attempt)) is None:
            return None
        fallback_payload = {key: value for key, value in payload.items() if key != "reasoning"}
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions", headers=_openrouter_headers(api_key),
            json=_guard_request(retry_attempt[0], fallback_payload),
            timeout=permit.timeout_seconds,
        )
        check_retention_response(response, str(payload["model"]))
        response.raise_for_status()
    return response


def _post_openrouter_json_schema_sync(
    *,
    client: httpx.Client,
    api_key: str,
    payload: dict[str, object],
    retry_attempt: OpenRouterRetryAttempt,
    reserve_attempt: Callable[..., ProviderCallPermit | None],
) -> httpx.Response | None:
    response = client.post(
        "https://openrouter.ai/api/v1/chat/completions", headers=_openrouter_headers(api_key), json=_guard_request(retry_attempt[0], payload)
    )
    try:
        check_retention_response(response, str(payload["model"]))
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 400 or not model_policy.can_retry_without_reasoning(payload):
            raise
        if (permit := reserve_attempt(*retry_attempt)) is None:
            return None
        fallback_payload = {key: value for key, value in payload.items() if key != "reasoning"}
        response = client.post(
            "https://openrouter.ai/api/v1/chat/completions", headers=_openrouter_headers(api_key),
            json=_guard_request(retry_attempt[0], fallback_payload),
            timeout=permit.timeout_seconds,
        )
        check_retention_response(response, str(payload["model"]))
        response.raise_for_status()
    return response

def _openrouter_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


