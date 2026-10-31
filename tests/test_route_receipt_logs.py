"""Assert what Render receives, not Loguru extras or a shared formatter."""

import json
from typing import Literal

import pytest
from argus.llm.openrouter import (
    annotate_latest_openrouter_route_receipt,
    begin_openrouter_route_receipt_capture,
    end_openrouter_route_receipt_capture,
    record_openrouter_route_receipt,
)
from loguru import logger


@pytest.mark.parametrize(
    ("outcome", "failure_mode"),
    [("succeeded", None), ("failed", "TimeoutError"), ("skipped", "missing_api_key")],
)
def test_route_receipt_is_diagnosable_in_default_rendered_log(
    monkeypatch: pytest.MonkeyPatch,
    outcome: Literal["succeeded", "failed", "skipped"],
    failure_mode: str | None,
) -> None:
    monkeypatch.setenv("CUADRAO_CHAT_FALLBACK_MODEL", "test/fallback")
    lines: list[str] = []
    sink = logger.add(lambda message: lines.append(str(message)), level="INFO")
    try:
        record_openrouter_route_receipt(
            task="clarification",
            model_name="test/fallback",
            mode="json_schema",
            schema_name="ClarificationResponse",
            latency_ms=25001,
            outcome=outcome,
            failure_mode=failure_mode,
            token_usage={"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
            usage_cost_usd=0.001,
        )
    finally:
        logger.remove(sink)

    line, = lines
    assert "INFO" in line
    payload = json.loads(line.split("OpenRouter route receipt ", 1)[1])
    assert payload.pop("created_at")
    assert payload == {
        "task": "clarification",
        "tier": "chat",
        "model": "test/fallback",
        "fallback_model": "test/fallback",
        "fallback_used": True,
        "mode": "json_schema",
        "schema_name": "ClarificationResponse",
        "latency_ms": 25001,
        "outcome": outcome,
        "failure_mode": failure_mode,
        "token_usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
        "usage_cost_usd": 0.001,
        "context_packet_ids": [],
    }


def test_route_receipt_escapes_newlines_and_does_not_dump_bound_context() -> None:
    lines: list[str] = []
    sink = logger.add(lambda message: lines.append(str(message)), level="INFO")
    try:
        with logger.contextualize(prompt="private prompt", api_key="private credential"):
            record_openrouter_route_receipt(
                task="clarification",
                model_name="test/model",
                mode="chat_model",
                schema_name=None,
                latency_ms=0,
                outcome="failed",
                failure_mode='ExampleError\n{"outcome":"succeeded"}',
            )
    finally:
        logger.remove(sink)
    line, = lines
    assert len(line.splitlines()) == 1
    assert "private prompt" not in line
    assert "private credential" not in line
    payload = json.loads(line.split("OpenRouter route receipt ", 1)[1])
    assert payload["outcome"] == "failed"
    assert payload["failure_mode"] == 'ExampleError\n{"outcome":"succeeded"}'


def test_repair_effect_annotation_emits_a_bounded_followup_log() -> None:
    repair_effect = {
        "schema_version": "argus_repair_effect/v1",
        "trigger_reason": "date_window_intent_uncertain",
        "repair_applied": False,
        "changed_fields": [],
        "before_fingerprint": "a" * 64,
        "after_fingerprint": "a" * 64,
        "no_op_reason": "no_typed_change",
    }
    lines: list[str] = []
    token = begin_openrouter_route_receipt_capture()
    sink = logger.add(lambda message: lines.append(str(message)), level="INFO")
    try:
        receipt = record_openrouter_route_receipt(
            task="interpretation_repair",
            model_name="test/model",
            mode="json_schema",
            schema_name="FocusedDateWindowExtraction",
            latency_ms=17,
            outcome="succeeded",
        )
        annotated = annotate_latest_openrouter_route_receipt(
            task="interpretation_repair",
            schema_name="FocusedDateWindowExtraction",
            repair_effect=repair_effect,
        )
        receipts = end_openrouter_route_receipt_capture(token)
    except BaseException:
        end_openrouter_route_receipt_capture(token)
        raise
    finally:
        logger.remove(sink)

    assert annotated is True
    assert receipts[0].repair_effect == repair_effect
    effect_lines = [line for line in lines if "OpenRouter repair effect " in line]
    assert len(effect_lines) == 1
    payload = json.loads(effect_lines[0].split("OpenRouter repair effect ", 1)[1])
    assert payload == {
        "task": "interpretation_repair",
        "schema_name": "FocusedDateWindowExtraction",
        "receipt_created_at": receipt.created_at,
        "repair_effect": repair_effect,
    }
