"""Task registry for OpenRouter calls: names, per-task profiles, model tiers.

Pure data. A task is callable only once it exists in all three structures
here; the runtime resolves models per tier from env at call time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

OpenRouterTask = Literal[
    "document_extraction",
    "interpretation",
    "interpretation_repair",
    "asset_mention_preflight",
    "field_fidelity",
    "capability_conflict",
    "clarification",
    "chat_composer",
    "result_summary",
    "name_suggestion",
    "discovery_extraction",
    "discovery_voicing",
    "discovery_model_knowledge",
    "knowledge_route",
    "knowledge_voicing",
    "memory_sensitivity",
]
OpenRouterModelTier = Literal["utility", "chat", "structured", "context", "readout", "vision"]
OpenRouterReasoningEffort = Literal["xhigh", "high", "medium", "low", "minimal", "none"]


@dataclass(frozen=True)
class OpenRouterProfile:
    task: OpenRouterTask
    temperature: float
    max_tokens: int
    timeout_seconds: int = 12
    max_retries: int = 1
    reasoning_effort: OpenRouterReasoningEffort = "none"


OPENROUTER_PROFILES: dict[OpenRouterTask, OpenRouterProfile] = {
    "document_extraction": OpenRouterProfile("document_extraction", temperature=0, max_tokens=12000, timeout_seconds=90, max_retries=0),
    "interpretation": OpenRouterProfile(
        "interpretation",
        temperature=0,
        max_tokens=3200,
        # 3200 tokens + structured + reasoning needs more than the 12s default (its peers
        # get 20-30s); proportionate bump so interpretation isn't the next timeout.
        timeout_seconds=20,
        reasoning_effort="medium",
    ),
    "interpretation_repair": OpenRouterProfile(
        "interpretation_repair",
        temperature=0,
        max_tokens=2200,
        timeout_seconds=20,
    ),
    "asset_mention_preflight": OpenRouterProfile(
        "asset_mention_preflight",
        temperature=0,
        max_tokens=2200,
        timeout_seconds=20,
    ),
    "field_fidelity": OpenRouterProfile(
        "field_fidelity",
        temperature=0,
        max_tokens=900,
        timeout_seconds=20,
    ),
    "capability_conflict": OpenRouterProfile(
        "capability_conflict",
        temperature=0,
        max_tokens=700,
        timeout_seconds=15,
        reasoning_effort="medium",
    ),
    "clarification": OpenRouterProfile("clarification", temperature=0, max_tokens=360),
    "chat_composer": OpenRouterProfile(
        "chat_composer", temperature=0.2, max_tokens=1200, timeout_seconds=25
    ),
    "result_summary": OpenRouterProfile(
        "result_summary", temperature=0.2, max_tokens=700, timeout_seconds=30
    ),
    "name_suggestion": OpenRouterProfile(
        "name_suggestion", temperature=0, max_tokens=400
    ),
    "discovery_extraction": OpenRouterProfile(
        "discovery_extraction", temperature=0, max_tokens=1200, timeout_seconds=20
    ),
    "discovery_voicing": OpenRouterProfile(
        "discovery_voicing", temperature=0.2, max_tokens=900, timeout_seconds=20
    ),
    "discovery_model_knowledge": OpenRouterProfile(
        "discovery_model_knowledge", temperature=0, max_tokens=1200, timeout_seconds=20
    ),
    "knowledge_route": OpenRouterProfile(
        "knowledge_route", temperature=0, max_tokens=350, timeout_seconds=12
    ),
    "knowledge_voicing": OpenRouterProfile(
        "knowledge_voicing", temperature=0.2, max_tokens=600, timeout_seconds=18
    ),
    "memory_sensitivity": OpenRouterProfile(
        "memory_sensitivity", temperature=0, max_tokens=300, timeout_seconds=15
    ),
}

OPENROUTER_TASK_MODEL_TIERS: dict[OpenRouterTask, OpenRouterModelTier] = {
    "document_extraction": "vision",
    "interpretation": "structured",
    "interpretation_repair": "structured",
    "asset_mention_preflight": "structured",
    "field_fidelity": "structured",
    "capability_conflict": "context",
    "clarification": "chat",
    "chat_composer": "chat",
    "result_summary": "readout",
    "name_suggestion": "utility",
    "discovery_extraction": "structured",
    "discovery_voicing": "chat",
    "discovery_model_knowledge": "structured",
    "knowledge_route": "structured",
    "knowledge_voicing": "chat",
    "memory_sensitivity": "utility",
}
