"""Where a decision's computation lives, and how a message declares one.

Every decision has one computation. A backtest decision derives it from the
evidence artifact it attaches to, because the run behind that artifact is the
immutable owner of the inputs. A computed-answer decision stores the
computation the assistant message declared under ``metadata.computation``, so
the decision keeps its inputs after the message is gone.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from argus.api.decision_contract import DecisionComputation, DecisionNote

BACKTEST_COMPUTATION_KIND = "backtest"

# The message metadata keys shared by every layer that stamps or reads a
# decision on a message. Cards carry the same two keys through
# ``argus.domain.evidence.attach_decision_to_result_card``.
COMPUTATION_METADATA_KEY = "computation"
DECISION_NOTE_ID_METADATA_KEY = "decision_note_id"
DECISION_STATE_METADATA_KEY = "decision_state"


def decision_computation(
    decision: DecisionNote,
    *,
    artifact: object,
) -> DecisionComputation:
    """The computation a decision re-runs: stored, or derived from its artifact."""
    if decision.computation is not None:
        return decision.computation
    source_run_id = _artifact_source_run_id(artifact)
    return DecisionComputation(
        kind=BACKTEST_COMPUTATION_KIND,
        inputs={"source_run_id": source_run_id} if source_run_id else {},
    )


def computation_from_message_metadata(
    metadata: Mapping[str, Any] | None,
) -> DecisionComputation | None:
    """The typed computation an assistant message declared, or ``None``.

    A message that carries no computation, or a malformed one, offers no
    decision; the shape is validated here so a decision never stores a blob
    the registry cannot re-run.
    """
    if not isinstance(metadata, Mapping):
        return None
    raw = metadata.get(COMPUTATION_METADATA_KEY)
    if not isinstance(raw, Mapping):
        return None
    try:
        return DecisionComputation.model_validate(dict(raw))
    except ValidationError:
        return None


def decision_message_metadata(
    metadata: Mapping[str, Any] | None,
    *,
    decision: DecisionNote,
) -> dict[str, Any]:
    """Stamp the current decision onto a message's metadata."""
    return {
        **(dict(metadata) if isinstance(metadata, Mapping) else {}),
        DECISION_NOTE_ID_METADATA_KEY: decision.id,
        DECISION_STATE_METADATA_KEY: decision.decision_state,
    }


def _artifact_source_run_id(artifact: object) -> str | None:
    if artifact is None:
        return None
    if isinstance(artifact, Mapping):
        value = artifact.get("source_run_id")
    else:
        value = getattr(artifact, "source_run_id", None)
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None
