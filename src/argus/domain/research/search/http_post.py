from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from argus.domain.research.search.contracts import SearchUnavailableError


def post_json(
    *,
    endpoint: str,
    transport: httpx.BaseTransport | None,
    timeout_seconds: float,
    headers: dict[str, str],
    body: dict[str, Any],
    check_response: Callable[[httpx.Response], None] | None = None,
) -> Any:
    """One bounded POST; every transport failure maps to a typed reason."""
    try:
        with httpx.Client(timeout=timeout_seconds, transport=transport) as client:
            response = client.post(endpoint, headers=headers, json=body)
            if check_response is not None:
                check_response(response)
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException as exc:
        raise SearchUnavailableError(reason="timeout", detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        reason = (
            "authentication_failed"
            if exc.response.status_code in (401, 403)
            else "http_error"
        )
        raise SearchUnavailableError(
            reason=reason, detail=f"status={exc.response.status_code}"
        ) from exc
    except httpx.HTTPError as exc:
        raise SearchUnavailableError(reason="http_error", detail=str(exc)) from exc
    except ValueError as exc:
        raise SearchUnavailableError(
            reason="malformed_response", detail="invalid_json"
        ) from exc
