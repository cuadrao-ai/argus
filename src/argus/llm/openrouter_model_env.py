from __future__ import annotations

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
    {"openai/gpt-6-luna-pro", "openai/gpt-6-luna-pro-20260922"}
)


def model_sampling_parameters(model: str, temperature: float) -> dict[str, float]:
    return (
        {} if model in _TEMPERATURE_UNSUPPORTED_MODELS else {"temperature": temperature}
    )
