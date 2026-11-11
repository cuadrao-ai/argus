"""Persisted English is private, including compatibility and nested fallbacks."""

from copy import deepcopy
from datetime import timezone

import pytest
from argus.api.artifact_message_reads import repair_result_message_facts
from argus.api.artifact_presentation import reader_payload
from argus.api.schemas import (
    BacktestJob,
    BacktestJobResponse,
    BacktestRun,
    BacktestRunResponse,
    Message,
)


@pytest.fixture
def run(faker) -> BacktestRun:
    return BacktestRun(
        id=faker.uuid4(),
        conversation_id=faker.uuid4(),
        status="completed",
        asset_class="equity",
        symbols=["AAPL"],
        allocation_method="equal_weight",
        benchmark_symbol="SPY",
        created_at=faker.date_time(tzinfo=timezone.utc),
        metrics={"aggregate": {"performance": {"total_return_pct": 12}}},
        config_snapshot={"template": "buy_and_hold"},
        conversation_result_card={
            "quick_take": "PRIVATE ORIGINAL",
            "breakdown": {"text": "PRIVATE ORIGINAL"},
        },
    )


@pytest.mark.parametrize("kind", ["result", "breakdown", "assumptions"])
def test_reader_never_exposes_private_prose_or_changes_storage(kind: str) -> None:
    fact_bank = {
        "symbols": ["AAPL"],
        "metrics": {"aggregate": {"performance": {"total_return_pct": 12}}},
        "result_card": {
            "quick_take": "PRIVATE nested result",
            "breakdown": "PRIVATE nested explanation",
        },
    }
    payload = {
        "content": "PRIVATE saved English",
        "assistant_response": "PRIVATE generated English",
        "assistant_prompt": "PRIVATE prompt compatibility English",
        "prompt": "PRIVATE historical prompt",
        "result_readout": "PRIVATE compatibility text",
        "result_fact_bank": fact_bank,
        "response_intent": {
            "kind": {
                "result": "result",
                "breakdown": "result_breakdown",
                "assumptions": "artifact_assumptions",
            }[kind],
            "facts": {"result_fact_bank": fact_bank},
        },
    }
    original = deepcopy(payload)
    public = reader_payload(payload)
    assert "PRIVATE" not in repr(public)
    assert public["result_fact_bank"]["metrics"] == fact_bank["metrics"]
    assert public["content"] == ""
    assert public["assistant_response"] == ""
    assert public["artifact_presentation_kind"] == kind
    assert payload == original


@pytest.mark.parametrize(
    "intent_kind", ["knowledge", "beginner_guidance", "unsupported_recovery"]
)
def test_ordinary_text_does_not_become_an_artifact(intent_kind, faker) -> None:
    payload = {
        "content": faker.sentence(),
        "response_intent": {"kind": intent_kind},
        "result_fact_bank": {"symbols": ["AAPL"]},
    }
    assert reader_payload(payload) == {**payload, "artifact_presentation_kind": None}


def test_bare_legacy_fact_bank_still_hides_saved_result_prose(faker) -> None:
    payload = {
        "content": faker.sentence(),
        "result_fact_bank": {"symbols": ["AAPL"]},
    }
    public = reader_payload(payload)
    assert public["content"] == ""
    assert public["artifact_presentation_kind"] == "result"
    assert public["result_fact_bank"] == payload["result_fact_bank"]


def test_reader_recomputes_stale_presentation_metadata_without_mutating_storage(faker):
    payload = {
        "content": faker.sentence(),
        "artifact_presentation_kind": "result",
        "response_intent": {"kind": "beginner_guidance"},
        "result_fact_bank": {"symbols": ["AAPL"]},
    }
    original = deepcopy(payload)
    public = reader_payload(payload)
    assert public["artifact_presentation_kind"] is None
    assert public["content"] == payload["content"]
    assert reader_payload(public) == public
    assert payload == original


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["en", "es-419"])
@pytest.mark.parametrize("fact_key", ["peak_date", "peak_value", "fee_bps"])
async def test_factual_followup_survives_live_and_persisted_readers(
    language: str, fact_key: str, faker
) -> None:
    from argus.agent_runtime.result_followups import result_followup_fact_bank
    from argus.agent_runtime.stages.interpret_internal.latest_result_answer import (
        latest_result_answer_stage_result_if_applicable,
    )
    from argus.api.artifact_chat_presentation import reader_chat_result
    from argus.api.routers.conversations import _public_message_projection
    from argus.domain.conversation_previews import project_conversation_preview

    from tests.agent_runtime.test_latest_result_fact_answers import (
        _costed_snapshot,
        _decision,
        _RecordingComposer,
    )

    snapshot = _costed_snapshot()
    reference = snapshot.latest_backtest_result_reference
    assert reference is not None
    fact = result_followup_fact_bank(dict(reference.metadata))[fact_key]
    answer = f"{faker.sentence()} {fact}"
    composer = _RecordingComposer(response=answer)
    decision = _decision("result_card_fact").model_copy(
        update={"result_followup_fact_key": fact_key}
    )
    result = await latest_result_answer_stage_result_if_applicable(
        decision=decision,
        snapshot=snapshot,
        current_user_message=faker.sentence(),
        language=language,
        compose_response_func=composer,
    )
    assert result is not None
    assert composer.calls[0]["language"] == language
    assert result.patch["response_intent"]["kind"] == "beginner_guidance"
    assert result.patch["response_intent"]["facts"][fact_key] == fact

    live = reader_chat_result(result.patch, result.patch)
    assert live["assistant_response"] == answer
    assert live["artifact_presentation_kind"] is None

    message = Message(
        id=faker.uuid4(),
        conversation_id=faker.uuid4(),
        role="assistant",
        content=answer,
        created_at=faker.date_time(tzinfo=timezone.utc),
        metadata={
            key: value
            for key, value in result.patch.items()
            if key != "assistant_response"
        },
    )
    original = message.model_dump()
    hydrated = _public_message_projection([message])[0]
    assert hydrated.content == answer
    assert hydrated.metadata["artifact_presentation_kind"] is None
    preview = project_conversation_preview(hydrated.model_dump())
    assert preview.kind == "text"
    assert preview.text == answer
    assert message.model_dump() == original


def test_legacy_breakdown_gets_typed_intent_without_reading_saved_text() -> None:
    payload = {
        "content": "PRIVATE",
        "chat_action": {"type": "show_breakdown"},
        "result_fact_bank": {"symbols": ["SPY"]},
    }
    public = reader_payload(payload)
    assert public["content"] == ""
    assert public["response_intent"] == {
        "kind": "result_breakdown",
        "facts": {"result_fact_bank": {"symbols": ["SPY"]}},
    }


def test_typed_breakdown_keeps_its_own_fact_bank_without_legacy_sidecar() -> None:
    intent = {
        "kind": "result_breakdown",
        "facts": {"result_fact_bank": {"symbols": ["AAPL"]}},
    }
    public = reader_payload({"content": "PRIVATE", "response_intent": intent})
    assert public["response_intent"] == intent


def test_public_run_and_job_responses_cannot_expose_private_prose(
    run: BacktestRun, faker
) -> None:
    original = run.model_dump()
    job = BacktestJob(id=faker.uuid4(), status="succeeded", result_run_id=run.id)
    for response in (
        BacktestRunResponse(run=run),
        BacktestJobResponse(job=job, run=run, result_readout="PRIVATE JOB ORIGINAL"),
    ):
        assert "PRIVATE" not in response.model_dump_json()
    assert (
        BacktestJobResponse(job=job, result_readout="PRIVATE").model_dump()[
            "result_readout"
        ]
        is None
    )
    assert run.model_dump() == original


def test_public_serializers_preserve_the_typed_run_schema() -> None:
    for model in (BacktestRunResponse, BacktestJobResponse):
        schema = model.model_json_schema(mode="serialization")
        assert "BacktestRun" in schema["$defs"]
        assert "BacktestRun" in repr(schema["properties"]["run"])


def test_failed_legacy_repair_still_emits_a_terminal_unavailable_result(
    run, faker
) -> None:
    from argus.api.routers.conversations import _public_message_projection

    message = Message(
        id=faker.uuid4(),
        conversation_id=run.conversation_id,
        role="assistant",
        content="PRIVATE LOST RESULT",
        created_at=run.created_at,
        metadata={"conversation_mode": "result_review", "result_run_id": run.id},
    )
    missing = repair_result_message_facts(
        [message], conversation_id=run.conversation_id, load_runs=lambda _ids: {}
    )
    public = _public_message_projection(missing)[0]
    assert public.content == ""
    assert public.metadata["result_fact_bank"] == {}


@pytest.mark.parametrize(
    "legacy_metadata", [{}, {"result_fact_bank": {"symbols": ["AAPL"]}}]
)
def test_old_result_facts_are_repaired_once_from_canonical_run_without_mutation(
    run: BacktestRun, faker, legacy_metadata
) -> None:
    message = Message(
        id=faker.uuid4(),
        conversation_id=run.conversation_id,
        role="assistant",
        content="PRIVATE ENGLISH",
        created_at=run.created_at,
        metadata={
            "conversation_mode": "result_review",
            "result_run_id": run.id,
            **legacy_metadata,
        },
    )
    original = message.model_dump()
    calls = []

    def load(ids):
        calls.append(ids)
        return {run.id: run}

    repaired = repair_result_message_facts(
        [message, message], conversation_id=run.conversation_id, load_runs=load
    )
    assert calls == [[run.id]]
    assert repaired[0].metadata["result_fact_bank"]["metrics"] == run.metrics
    assert message.model_dump() == original
    assert (
        repair_result_message_facts(
            repaired,
            conversation_id=run.conversation_id,
            load_runs=lambda _ids: pytest.fail("complete facts must not query"),
        )
        == repaired
    )


def test_reader_repair_rejects_conflicting_and_cross_conversation_identity(
    run: BacktestRun, faker
) -> None:
    message = Message(
        id=faker.uuid4(),
        conversation_id=faker.uuid4(),
        role="assistant",
        content="PRIVATE",
        created_at=run.created_at,
        metadata={"conversation_mode": "result_review", "result_run_id": run.id},
    )
    assert repair_result_message_facts(
        [message],
        conversation_id=message.conversation_id,
        load_runs=lambda _ids: {run.id: run},
    ) == [message]
    conflicting = message.model_copy(
        update={
            "metadata": {**message.metadata, "result_card": {"run_id": faker.uuid4()}}
        }
    )
    assert repair_result_message_facts(
        [conflicting],
        conversation_id=message.conversation_id,
        load_runs=lambda _ids: pytest.fail("ambiguous identity must not load"),
    ) == [conflicting]
