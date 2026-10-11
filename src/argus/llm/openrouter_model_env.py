from __future__ import annotations

SONNET_5_5_MODEL = "anthropic/claude-sonnet-5.5"

# Model-tier environment variable names consumed by openrouter.py's candidate
# resolution. Keys are OpenRouterModelTier values; kept as plain strings here
# so this module stays import-cycle-free.
TIER_PRIMARY_ENV: dict[str, tuple[str, ...]] = {
    "vision": ("ARGUS_VISION_MODEL",),
    "utility": ("ARGUS_UTILITY_MODEL",),
    "chat": ("ARGUS_CHAT_MODEL",),
    "structured": ("ARGUS_STRUCTURED_MODEL",),
    "context": ("ARGUS_CONTEXT_MODEL",),
    "readout": ("ARGUS_READOUT_MODEL",),
}

TIER_FALLBACK_ENV: dict[str, tuple[str, ...]] = {
    "vision": (),
    "utility": ("ARGUS_UTILITY_FALLBACK_MODEL",),
    "chat": ("ARGUS_CHAT_FALLBACK_MODEL",),
    "structured": ("ARGUS_STRUCTURED_FALLBACK_MODEL",),
    "context": ("ARGUS_CONTEXT_FALLBACK_MODEL",),
    "readout": ("ARGUS_READOUT_FALLBACK_MODEL",),
}


_TEMPERATURE_UNSUPPORTED_MODELS = frozenset(
    {
        "openai/gpt-6-luna-pro",
        "openai/gpt-6-luna-pro-20260922",
        SONNET_5_5_MODEL,
    }
)


def model_reasoning_parameters(model: str, effort: str) -> dict[str, str | bool]:
    if model != SONNET_5_5_MODEL:
        return {"effort": effort}
    return {
        "effort": "low" if effort in {"none", "minimal"} else effort,
        "exclude": True,
    }


def can_retry_without_reasoning(payload: dict[str, object]) -> bool:
    return "reasoning" in payload and payload.get("model") != SONNET_5_5_MODEL


def model_sampling_parameters(model: str, temperature: float) -> dict[str, float]:
    return (
        {} if model in _TEMPERATURE_UNSUPPORTED_MODELS else {"temperature": temperature}
    )


def _has_optional_object_properties(node: object) -> bool:
    if isinstance(node, list):
        return any(_has_optional_object_properties(item) for item in node)
    if not isinstance(node, dict):
        return False
    properties = node.get("properties")
    if (
        node.get("type") == "object"
        and isinstance(properties, dict)
        and set(properties).difference(node.get("required", []))
    ):
        return True
    return any(_has_optional_object_properties(item) for item in node.values())


def uses_schema_message(model: str, schema: object, *, projected: bool = False) -> bool:
    return model.startswith("anthropic/") or (
        model.startswith("openai/")
        and not projected
        and _has_optional_object_properties(schema)
    )
