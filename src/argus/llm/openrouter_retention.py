from __future__ import annotations

from collections.abc import Mapping

from loguru import logger


class OpenRouterRoutingError(RuntimeError):
    event: str

    def __init__(self, model: str) -> None:
        self.model = model
        super().__init__(self.event)


class OpenRouterZDRUnavailableError(OpenRouterRoutingError):
    event = "llm_zdr_unavailable"


class OpenRouterNotFoundError(OpenRouterRoutingError):
    event = "llm_route_not_found"


def openrouter_provider_policy() -> dict[str, object]:
    return {
        "require_parameters": True,
        "data_collection": "deny",
        "zdr": True,
        "allow_fallbacks": False,
    }


def enforce_openrouter_retention(payload: dict[str, object]) -> dict[str, object]:
    provider = payload.get("provider")
    policy = openrouter_provider_policy()
    if isinstance(provider, dict):
        if any(key in provider and (provider[key] != value or type(provider[key]) is not type(value)) for key, value in policy.items()):
            raise PermissionError("openrouter_retention_policy_changed")
        if all(provider.get(key) == value for key, value in policy.items()):
            return payload
    return {**payload, "provider": {**(provider if isinstance(provider, dict) else {}), **policy}}


def raise_for_retention_error(model: str, status: object, body: object = None) -> None:
    error = body.get("error") if isinstance(body, Mapping) else None
    error = error if isinstance(error, Mapping) else {}
    code = str(error.get("code", status))
    metadata = error.get("metadata")
    error_type = metadata.get("error_type") if isinstance(metadata, Mapping) else None
    message = str(error.get("message", "")).casefold()
    failure: type[OpenRouterRoutingError] | None = None
    if error_type == "not_found":
        failure = OpenRouterNotFoundError
    elif code in {"400", "403", "404"} and any(
        term in message for term in ("data policy", "privacy", "zero data retention", "zdr")
    ):
        failure = OpenRouterZDRUnavailableError
    elif code == "404":
        failure = OpenRouterNotFoundError
    if failure is not None:
        logger.warning(failure.event, model=model)
        raise failure(model) from None


def check_retention_response(response: object, model: str) -> None:
    status = getattr(response, "status_code", 200)
    if status in (200, 400, 403, 404):
        try:
            body = response.json()
        except ValueError:
            body = None
        raise_for_retention_error(model, status, body)
