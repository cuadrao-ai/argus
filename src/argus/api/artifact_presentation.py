"""Reader boundary for immutable artifact prose retained as private context.

Persistence and model inputs keep their original records. Only transport copies
pass here. No language, translation, model call, or historical rewrite belongs
in this boundary.
"""

import json
from collections.abc import Mapping
from importlib.resources import files
from typing import Any

from pydantic import BaseModel, field_serializer

from argus.domain.artifact_presentation_kind import artifact_presentation_kind
from argus.domain.result_figures import result_display_figures
from argus.domain.result_readout_content import validated_readout
from argus.domain.result_readout_facts import (
    result_readout_config,
    with_result_readout_facts,
)

# These storage fields are private across their historical nesting locations.
# The AST guard forbids a presentation consumer from reading them again.
PRIVATE_ARTIFACT_PROSE_FIELDS = frozenset(
    json.loads(files("argus.domain").joinpath("artifact_prose_fields.json").read_text())
)
ARTIFACT_ROOT_PROSE_FIELDS = frozenset(
    json.loads(
        files("argus.domain").joinpath("artifact_root_prose_fields.json").read_text()
    )
)
# Legacy rows keep the retired card summary in every copy of the card, nested
# references included, so the scrub follows the card key rather than a path.
CONFIRMATION_CARD_KEYS = frozenset({"confirmation_card", "confirmation"})
RETIRED_CONFIRMATION_CARD_FIELDS = frozenset({"summary"})


def without_private_prose(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: validated_readout(item)
            if key == "result_readout_content"
            else without_private_prose(_without_retired_card_prose(key, item))
            for key, item in value.items()
            if key not in PRIVATE_ARTIFACT_PROSE_FIELDS
        }
    if isinstance(value, list):
        return [without_private_prose(item) for item in value]
    return value


def _without_retired_card_prose(key: str, value: Any) -> Any:
    if key not in CONFIRMATION_CARD_KEYS or not isinstance(value, Mapping):
        return value
    return {
        field: item
        for field, item in value.items()
        if field not in RETIRED_CONFIRMATION_CARD_FIELDS
    }


def reader_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Strip source prose and materialize old typed artifact intent on read."""
    kind = artifact_presentation_kind(payload)
    public: dict[str, Any] = without_private_prose(payload)
    # The transport owns this decision, including for legacy persisted rows.
    # Readers consume it instead of independently classifying attached facts.
    public["artifact_presentation_kind"] = kind
    if kind not in {"result", "breakdown", "assumptions", "confirmation"}:
        return public
    if kind == "result" and not isinstance(public.get("result_fact_bank"), dict):
        # An unavailable lookup is still a terminal result, not an empty turn.
        public["result_fact_bank"] = {}
    for field in ARTIFACT_ROOT_PROSE_FIELDS:
        if field in public:
            public[field] = ""
    intent = public.get("response_intent")
    if kind == "breakdown" and not (
        isinstance(intent, dict) and intent.get("kind") == "result_breakdown"
    ):
        public["response_intent"] = {
            "kind": "result_breakdown",
            "facts": {"result_fact_bank": public.get("result_fact_bank")},
        }
    # Project stored plan facts and display figures on the transport copy; a
    # typed breakdown carries its bank inside the intent, older shapes at root.
    if "result_fact_bank" in public:
        public["result_fact_bank"] = with_result_readout_facts(public["result_fact_bank"])
    facts = (public.get("response_intent") or {}).get("facts")
    if isinstance(facts, dict) and "result_fact_bank" in facts:
        facts["result_fact_bank"] = with_result_readout_facts(facts["result_fact_bank"])
    return public


def reader_run(value: Any) -> Any:
    """Serialize a public run without changing its private persisted model."""
    if value is None:
        return None
    public = without_private_prose(value.model_dump())
    public["figures"] = result_display_figures(public.get("metrics"))
    public["config_snapshot"] = result_readout_config(public.get("config_snapshot"))
    return value.model_copy(update=public)


class ReaderJobResponse(BaseModel):
    @field_serializer("result_readout", check_fields=False)
    def omit_private_readout(self, _value: str | None) -> None:
        # Older clients retain the slot, but can never receive its stored prose.
        return None

