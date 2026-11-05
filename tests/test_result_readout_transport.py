"""Only newly composed, language-tagged readouts cross the artifact boundary."""

from copy import deepcopy

import pytest
from argus.api.artifact_presentation import reader_payload
from argus.domain.result_readout_content import (
    ResultReadoutContent,
    normalize_readout_language,
    readout_metadata,
    readout_metadata_from_stage,
)


@pytest.mark.parametrize(
    "requested,expected",
    [
        ("en", "en"),
        ("EN_us", "en"),
        (" es-419 ", "es-419"),
        ("es-MX", "es-419"),
        ("fr", None),
        ("", None),
        (None, None),
        (False, None),
    ],
)
def test_readout_language_owner_normalizes_supported_requests(requested, expected):
    assert normalize_readout_language(requested) == expected


@pytest.mark.parametrize(
    "language,stored", [("en", "en"), ("es", "es-419"), ("es-419", "es-419")]
)
@pytest.mark.parametrize("fallback", [False, True])
def test_creation_stamps_language_and_never_publishes_fallback_prose(
    language, stored, fallback
):
    metadata = readout_metadata_from_stage(
        {
            "assistant_response": "A complete model draft.",
            "assistant_response_source": "deterministic_fallback"
            if fallback
            else "llm_explain_stage",
            "assistant_response_fallback_used": fallback,
            "assistant_response_failure_mode": "false_figure" if fallback else None,
        },
        language=language,
    )
    envelope = ResultReadoutContent.model_validate(metadata["result_readout_content"])
    assert envelope.language == stored
    assert envelope.surface == "quick_take"
    assert envelope.text == (None if fallback else "A complete model draft.")
    assert metadata["result_readout_fallback_used"] is fallback


@pytest.mark.parametrize("surface", ["quick_take", "breakdown"])
def test_reader_keeps_only_new_readout_and_never_changes_saved_record(surface):
    metadata = readout_metadata(
        surface=surface,
        text="Accepted complete text.",
        language="es-419",
        source="llm_explain_stage",
        fallback_used=False,
    )
    payload = {
        **metadata,
        "content": "PRIVATE original English",
        "result_readout": "PRIVATE job English",
        "response_intent": {
            "kind": "result" if surface == "quick_take" else "result_breakdown"
        },
        "result_fact_bank": {},
    }
    before = deepcopy(payload)
    public = reader_payload(payload)
    assert public["result_readout_content"] == metadata["result_readout_content"]
    assert "PRIVATE" not in repr(public)
    assert before == payload


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": "result_readout/v0"},
        {"language": "fr"},
        {"surface": "research"},
        {"text": ""},
        {"text": {"private": "PRIVATE"}},
        {"audit_context": "PRIVATE"},
        {"unexpected": "PRIVATE"},
    ],
)
def test_reader_drops_malformed_or_extended_readout_whole(change):
    content = {
        "schema_version": "result_readout/v1",
        "surface": "quick_take",
        "language": "en",
        "text": "Accepted complete text.",
        **change,
    }
    public = reader_payload({"result_card": {}, "result_readout_content": content})
    assert public.get("result_readout_content") is None


def test_old_result_never_gets_a_creation_stamp():
    public = reader_payload(
        {"result_card": {"quick_take": "PRIVATE"}, "content": "PRIVATE"}
    )
    assert public.get("result_readout_content") is None
    assert "PRIVATE" not in repr(public)


@pytest.mark.asyncio
async def test_graph_keeps_creation_metadata_through_end_stage(monkeypatch):
    from argus.agent_runtime.graph import workflow
    from argus.agent_runtime.runtime import _public_result
    from argus.agent_runtime.stages.interpret import StageResult
    from argus.agent_runtime.state.models import RunState, UserState

    async def explain(**kwargs):
        return StageResult(
            outcome="ready_to_respond",
            stage_patch={
                "assistant_response": "Complete accepted readout.",
                "assistant_response_source": "llm_explain_stage",
                "assistant_response_fallback_used": False,
            },
        )

    monkeypatch.setattr(workflow, "explain_stage_async", explain)
    state = {
        "run_state": RunState.new(current_user_message="", recent_thread_history=[]),
        "user": UserState(user_id="reader", language_preference="es"),
    }
    explained = await workflow._explain_node_async(state)
    ended = workflow._apply_stage_result(explained, StageResult(outcome="end_run"))
    public = _public_result(ended)
    assert public["result_readout_content"]["language"] == "es-419"
    assert public["result_readout_content"]["text"] == "Complete accepted readout."
    assert public["result_readout_fallback_used"] is False


def test_completed_job_reload_and_job_response_share_run_stamp():
    from argus.api.schemas import BacktestJob, BacktestJobResponse
    from argus.domain.backtest_message_projection import (
        hydrate_completed_backtest_job_messages,
    )

    from tests.test_backtest_message_projection import _completed_run, _queued_message

    run = _completed_run()
    metadata = readout_metadata(
        surface="quick_take",
        text="Complete accepted text.",
        language="es",
        source="llm_explain_stage",
        fallback_used=False,
    )
    run.conversation_result_card.update(metadata)
    job = {
        "id": "job-1",
        "conversation_id": run.conversation_id,
        "status": "succeeded",
        "result_run_id": run.id,
    }
    [message] = hydrate_completed_backtest_job_messages(
        [_queued_message()], jobs_by_id={job["id"]: job}, runs_by_id={run.id: run}
    )
    assert (
        message.metadata["result_readout_content"] == metadata["result_readout_content"]
    )
    response = BacktestJobResponse(
        job=BacktestJob.model_validate(job), run=run, **metadata
    ).model_dump()
    assert response["result_readout_content"] == metadata["result_readout_content"]
    assert (
        response["run"]["conversation_result_card"]["result_readout_content"]
        == metadata["result_readout_content"]
    )
