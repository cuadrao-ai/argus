from __future__ import annotations

from collections.abc import Mapping

from loguru import logger


class OpenRouterZDRUnavailableError(RuntimeError):
    def __init__(self, model: str) -> None:
        self.model = model
        super().__init__("llm_zdr_unavailable")


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
    code = error.get("code", status)
    message = str(error.get("message", "")).casefold()
    if str(code) == "404" or (
        str(code) in {"400", "403"}
        and any(term in message for term in ("data policy", "privacy", "zero data retention", "zdr"))
    ):
        logger.warning("llm_zdr_unavailable", model=model)
        raise OpenRouterZDRUnavailableError(model) from None


def check_retention_response(response: object, model: str) -> None:
    status = getattr(response, "status_code", 200)
    if status == 404:
        raise_for_retention_error(model, status)
    if status in (200, 400, 403):
        try:
            body = response.json()
        except ValueError:
            body = None
        raise_for_retention_error(model, status, body)
