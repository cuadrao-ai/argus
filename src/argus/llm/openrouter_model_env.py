from __future__ import annotations

SONNET_5_5_MODEL = "anthropic/claude-sonnet-5.5"

# Model-tier environment variable names consumed by openrouter.py's candidate
# resolution. Keys are OpenRouterModelTier values; kept as plain strings here
# so this module stays import-cycle-free.
TIER_PRIMARY_ENV: dict[str, tuple[str, ...]] = {
    "vision": ("CUADRAO_VISION_MODEL", "ARGUS_VISION_MODEL"),
    "utility": ("CUADRAO_UTILITY_MODEL",),
    "chat": ("CUADRAO_CHAT_MODEL",),
    "structured": ("CUADRAO_STRUCTURED_MODEL",),
    "context": ("CUADRAO_CONTEXT_MODEL",),
    "readout": ("CUADRAO_READOUT_MODEL",),
}

TIER_FALLBACK_ENV: dict[str, tuple[str, ...]] = {
    "vision": (),
    "utility": ("CUADRAO_UTILITY_FALLBACK_MODEL",),
    "chat": ("CUADRAO_CHAT_FALLBACK_MODEL",),
    "structured": ("CUADRAO_STRUCTURED_FALLBACK_MODEL",),
    "context": ("CUADRAO_CONTEXT_FALLBACK_MODEL",),
    "readout": ("CUADRAO_READOUT_FALLBACK_MODEL",),
}


CANONICAL_TIMEOUT_TASKS = frozenset(
    {
        "asset_mention_preflight",
        "capability_conflict",
        "chat_composer",
        "clarification",
        "document_extraction",
        "field_fidelity",
        "interpretation",
        "interpretation_repair",
        "knowledge_route",
        "knowledge_voicing",
        "name_suggestion",
        "result_summary",
    }
)

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


# Only the Business routes deliver a sparse schema for OpenAI models in the
# prompt. Every other route keeps its native strict wire unchanged.
BUSINESS_SCHEMA_NAMES = frozenset(
    {"BusinessInterpretation", "BusinessReply", "BusinessE1JudgeVerdict"}
)


def uses_schema_message(
    model: str,
    schema: object,
    *,
    projected: bool = False,
    schema_name: str = "",
) -> bool:
    return model.startswith("anthropic/") or (
        model.startswith("openai/")
        and not projected
        and schema_name in BUSINESS_SCHEMA_NAMES
        and _has_optional_object_properties(schema)
    )
