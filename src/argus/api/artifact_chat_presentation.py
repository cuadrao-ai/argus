from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from argus.api.artifact_presentation import reader_payload
from argus.domain.result_readout_content import readout_metadata


def reader_chat_result(
    payload: Mapping[str, Any], metadata: Mapping[str, Any]
) -> dict[str, Any]:
    from argus.api.chat.confirmation import public_confirmation_projection

    return reader_payload(
        public_confirmation_projection(
            {**payload, "chat_action": metadata.get("chat_action")}
        )
    )


def result_breakdown_metadata(
    message: Any, run: Any, *, language: str = "en"
) -> dict[str, Any]:
    from argus.agent_runtime.research_grounded import returned_sources_research_sidecar
    from argus.domain.backtest_message_projection import result_fact_bank

    metadata = {
        "response_intent": {
            "kind": "result_breakdown",
            "facts": {
                "result_fact_bank": result_fact_bank(run) if run is not None else None
            },
        },
        "result_breakdown_source": message.source,
        "result_breakdown_fallback_used": message.fallback_used,
    }
    if message.failure_mode is not None:
        metadata["result_breakdown_failure_mode"] = message.failure_mode
    metadata.update(
        readout_metadata(
            surface="breakdown",
            text=message.text,
            language=language,
            source=message.source,
            fallback_used=message.fallback_used,
            failure_mode=message.failure_mode,
        )
    )
    if message.sources:
        metadata["research"] = returned_sources_research_sidecar(
            sources=message.sources,
            usage=message.usage,
            degraded_code=message.failure_mode if message.fallback_used else None,
        )
    return metadata
