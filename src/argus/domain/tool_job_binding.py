"""One versioned binding for a declared call that outlives its chat process."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from argus.domain.tool_contracts import (
    LocalizedText,
    ToolCall,
    ToolCardPresentation,
    ToolFailure,
    ToolOutcome,
    ToolResultCard,
)


class ToolJobBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    call: ToolCall
    artifact_id: str = Field(min_length=1)
    card_type: str = Field(min_length=1)
    card_version: int = Field(ge=1)
    input_revision: int = Field(default=0, ge=0)


def bind_tool_job_call(*, call: ToolCall, artifact_id: str) -> dict[str, Any]:
    """Freeze a validated admitted call before its provider job is dispatched."""
    from argus.domain.personal_tool_catalog import personal_tool_catalog

    declaration = personal_tool_catalog().get(call.tool_name)
    if declaration is None:
        raise ValueError("Unknown tool job declaration")
    arguments = declaration.validate_arguments(call.arguments).model_dump(mode="json")
    binding = ToolJobBinding(
        call=call.model_copy(update={"arguments": arguments}),
        artifact_id=artifact_id,
        card_type=declaration.card.card_type,
        card_version=declaration.card.version,
    )
    return binding.model_dump(mode="json")


def tool_card_for_job_completion(
    binding: dict[str, Any],
    outcome: ToolOutcome,
) -> ToolResultCard:
    """Resolve a persisted binding even when new admissions have been disabled."""
    from argus.domain.personal_tool_catalog import personal_tool_catalog

    source = ToolJobBinding.model_validate(binding)
    declaration = personal_tool_catalog(include_unavailable=True).get(source.call.tool_name)
    if declaration is not None and (
        declaration.card.card_type,
        declaration.card.version,
    ) == (source.card_type, source.card_version):
        return declaration.result_card(
            call=source.call,
            outcome=outcome,
            artifact_id=source.artifact_id,
            input_revision=source.input_revision,
        )
    return ToolResultCard(
        tool_name=source.call.tool_name,
        call_id=source.call.call_id,
        artifact_id=source.artifact_id,
        card_type=source.card_type,
        card_version=source.card_version,
        input_revision=source.input_revision,
        arguments=source.call.arguments,
        outcome=ToolOutcome(
            status="unavailable", failure=ToolFailure(code="tool_contract_changed")
        ),
        presentation=ToolCardPresentation(
            title=LocalizedText(locale_key="chat.tools.failed")
        ),
    )
