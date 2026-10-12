from __future__ import annotations

import asyncio
import json

import pytest
from argus.agent_runtime.business.interpretation import BusinessInterpretation
from argus.llm import openrouter
from argus.llm.openrouter import (
    openrouter_profile_for_task,
)
from pydantic import BaseModel, ConfigDict, ValidationError

from tests.test_openrouter_policy import FakeChatOpenRouter


@pytest.mark.parametrize("task", openrouter.OPENROUTER_TASK_MODEL_TIERS)
@pytest.mark.parametrize(
    "model", ["openai/gpt-6-luna-pro", "openai/gpt-6-luna-pro-20260922"]
)
def test_luna_pro_sampling_capability_preserves_structured_request_policy(
    task: openrouter.OpenRouterTask, model: str
) -> None:
    from argus.agent_runtime.llm_interpreter_types import LLMDateRangeIntent

    arguments = {
        "messages": [{"role": "user", "content": "hello"}],
        "schema_model": LLMDateRangeIntent,
        "schema_name": "LLMDateRangeIntent",
        "profile": openrouter_profile_for_task(task),
    }
    baseline = openrouter._json_schema_payload(model="openai/gpt-5.6-luna", **arguments)
    payload = openrouter._json_schema_payload(model=model, **arguments)
    baseline.pop("model")
    baseline.pop("temperature", None)
    assert payload.pop("model") == model
    assert "temperature" not in payload
    assert payload == baseline
    assert payload["provider"]["require_parameters"] is True


@pytest.mark.parametrize(
    "model", ["openai/gpt-6-luna-pro", "openai/gpt-6-luna-pro-20260922"]
)
def test_luna_pro_factory_omits_unsupported_sampling_only(monkeypatch, model) -> None:
    FakeChatOpenRouter.calls.clear()
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(openrouter, "ChatOpenRouter", FakeChatOpenRouter)
    assert openrouter.build_openrouter_model("interpretation", model_name=model)
    assert FakeChatOpenRouter.calls == [
        {
            "model_name": model,
            "max_tokens": 3200,
            "timeout": 20,
            "max_retries": 1,
            "openrouter_api_key": "test-key",
        }
    ]


@pytest.mark.parametrize(
    "model", ["openai/gpt-6-luna-pro", "openai/gpt-6-luna-pro-20260922"]
)
def test_luna_pro_direct_chat_omits_unsupported_sampling_only(monkeypatch, model):
    observed = []

    async def fake_post(**arguments):
        observed.append(arguments["payload"])
        return openrouter.httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Saved draft."}}]},
            request=openrouter.httpx.Request("POST", "https://example.invalid"),
        )

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(openrouter, "_post_openrouter_json_schema", fake_post)
    result = asyncio.run(
        openrouter.invoke_openrouter_chat_completion(
            task="chat_composer",
            model_name=model,
            messages=[{"role": "user", "content": "summarize"}],
        )
    )
    assert result == "Saved draft."
    assert observed == [
        {
            "model": model,
            "messages": [{"role": "user", "content": "summarize"}],
            "max_tokens": openrouter_profile_for_task("chat_composer").max_tokens,
        }
    ]


class CompleteWireResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str


class SparseWireResult(CompleteWireResult):
    note: str | None = None


class NestedWireResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item: SparseWireResult


@pytest.mark.parametrize("schema_model", [SparseWireResult, NestedWireResult])
@pytest.mark.parametrize(
    "model", ["openai/gpt-6-luna-pro", "openai/gpt-6-luna-pro-20260922"]
)
def test_openai_optional_object_schema_is_delivered_exactly_in_prompt(
    schema_model, model
):
    profile = openrouter_profile_for_task("interpretation")
    payload = openrouter._json_schema_payload(
        model=model,
        messages=[{"role": "user", "content": "probe"}],
        schema_model=schema_model,
        schema_name="BusinessInterpretation",
        profile=profile,
    )
    assert "response_format" not in payload
    assert payload["provider"] == {"require_parameters": True}
    assert "temperature" not in payload
    assert payload["max_tokens"] == profile.max_tokens
    assert payload["reasoning"] == {"effort": profile.reasoning_effort}
    instruction = payload["messages"][0]["content"][0]["text"]
    assert (
        json.loads(instruction.split("JSON Schema:\n", 1)[1])
        == schema_model.model_json_schema()
    )
    assert payload["messages"][-1] == {"role": "user", "content": "probe"}


@pytest.mark.parametrize("model", ["openai/gpt-6-luna-pro", "x-ai/grok-4.3"])
def test_all_required_object_keeps_exact_native_schema(model):
    payload = openrouter._json_schema_payload(
        model=model,
        messages=[{"role": "user", "content": "probe"}],
        schema_model=CompleteWireResult,
        schema_name="probe",
        profile=openrouter_profile_for_task("interpretation"),
    )
    assert payload["response_format"]["json_schema"] == {
        "name": "probe",
        "strict": True,
        "schema": CompleteWireResult.model_json_schema(),
    }
    assert payload["messages"] == [{"role": "user", "content": "probe"}]


@pytest.mark.parametrize(
    ("model", "temperature", "reasoning"),
    [
        ("anthropic/claude-sonnet-5.5", False, {"effort": "low", "exclude": True}),
        ("anthropic/claude-haiku-5.5", True, {"effort": "none"}),
        ("openai/gpt-6-luna-pro", False, {"effort": "none"}),
        ("x-ai/grok-4.3", True, {"effort": "none"}),
    ],
)
def test_judge_request_model_parameters(model, temperature, reasoning):
    profile = openrouter_profile_for_task("chat_composer")
    payload = openrouter._json_schema_payload(
        model=model,
        messages=[],
        schema_model=CompleteWireResult,
        schema_name="probe",
        profile=profile,
    )
    assert ("temperature" in payload) is temperature
    assert payload["reasoning"] == reasoning


@pytest.mark.parametrize("sync", [False, True])
@pytest.mark.parametrize(
    "model", ["openai/gpt-6-luna-pro", "openai/gpt-6-luna-pro-20260922"]
)
@pytest.mark.parametrize(
    "schema_model,response_value,valid",
    [
        (
            BusinessInterpretation,
            {"records": [{"facts": {"amount": {"state": "known", "value": "37"}}}]},
            True,
        ),
        (
            BusinessInterpretation,
            {"records": [{"facts": {"funding": {"state": "unknown"}}}]},
            True,
        ),
        (
            BusinessInterpretation,
            {"records": [{"facts": {"funding": {"state": "owner_does_not_know"}}}]},
            True,
        ),
        (BusinessInterpretation, {"records": [{"facts": {"amount": None}}]}, False),
        (
            BusinessInterpretation,
            {"records": [{"facts": {"amount": {"state": "known"}}}]},
            False,
        ),
        (
            BusinessInterpretation,
            {
                "records": [
                    {
                        "facts": {
                            "amount": {"state": "known", "value": "37"},
                            "grant_id": "fake",
                        }
                    }
                ]
            },
            False,
        ),
        (NestedWireResult, {"item": {"value": "kept"}}, True),
        (NestedWireResult, {"item": {"note": "missing value"}}, False),
        (CompleteWireResult, {"value": "native"}, True),
        (CompleteWireResult, {"value": None}, False),
    ],
)
def test_openai_structured_wire_retains_exact_local_validation(
    monkeypatch, sync, model, schema_model, response_value, valid
):
    submitted = []

    def respond(payload):
        submitted.append(payload)
        if schema_model is CompleteWireResult:
            assert (
                payload["response_format"]["json_schema"]["schema"]
                == schema_model.model_json_schema()
            )
        else:
            assert "response_format" not in payload
            instruction = payload["messages"][0]["content"][0]["text"]
            assert (
                json.loads(instruction.split("JSON Schema:\n", 1)[1])
                == schema_model.model_json_schema()
            )
        return openrouter.httpx.Response(
            200,
            request=openrouter.httpx.Request("POST", "https://example.invalid"),
            json={"choices": [{"message": {"content": json.dumps(response_value)}}]},
        )

    class Client:
        def __init__(self, **kwargs):
            assert (
                kwargs["timeout"]
                == openrouter_profile_for_task("interpretation").timeout_seconds
            )

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def post(self, *args, **kwargs):
            return respond(kwargs["json"])

    class AsyncClient(Client):
        async def post(self, *args, **kwargs):
            return respond(kwargs["json"])

    monkeypatch.setenv("OPENROUTER_API_KEY", "mock-key")
    monkeypatch.setenv("ARGUS_STRUCTURED_FALLBACK_MODEL", "")
    monkeypatch.setattr(openrouter.httpx, "Client", Client)
    monkeypatch.setattr(openrouter.httpx, "AsyncClient", AsyncClient)
    openrouter.clear_openrouter_route_receipts()
    kwargs = dict(
        task="interpretation",
        model_name=model,
        messages=[{"role": "user", "content": "probe"}],
        schema_model=schema_model,
        schema_name="BusinessInterpretation",
    )

    def invoke():
        if sync:
            return openrouter.invoke_openrouter_json_schema_sync(**kwargs)
        return asyncio.run(openrouter.invoke_openrouter_json_schema(**kwargs))

    if valid:
        assert invoke().model_dump(mode="json", exclude_unset=True) == response_value
    else:
        with pytest.raises(ValidationError):
            invoke()
    assert len(submitted) == 1
    assert submitted[0]["provider"] == {"require_parameters": True}
    assert "temperature" not in submitted[0]
    receipts = openrouter.get_openrouter_route_receipts()
    assert len(receipts) == 1
    assert receipts[0].model == model
    assert receipts[0].outcome == ("succeeded" if valid else "failed")


@pytest.mark.parametrize("failure", [False, True])
def test_nested_request_observers_preserve_order_and_restore_on_exception(failure):
    events = []
    payload = {"model": "consumer/configured"}

    def observer(label):
        def observe(task, actual):
            events.append(label)
            return {**actual, label: True}

        return observe

    with openrouter.openrouter_request_guard(observer("outer")):
        try:
            with openrouter.openrouter_request_guard(observer("inner")):
                assert openrouter._guard_request("interpretation", payload) == {
                    **payload,
                    "outer": True,
                    "inner": True,
                }
                if failure:
                    raise RuntimeError("interrupted")
        except RuntimeError:
            assert failure
        assert openrouter._guard_request("interpretation", payload) == {
            **payload,
            "outer": True,
        }
    assert events == ["outer", "inner", "outer"]
    assert openrouter._guard_request("interpretation", payload) is payload


class _Inner(BaseModel):
    value: str


class _Sparse(BaseModel):
    name: str
    inner: _Inner | None = None


_SPARSE_SCHEMA = {
    "$defs": {
        "_Inner": {
            "properties": {"value": {"title": "Value", "type": "string"}},
            "required": ["value"],
            "title": "_Inner",
            "type": "object",
        }
    },
    "properties": {
        "inner": {
            "anyOf": [{"$ref": "#/$defs/_Inner"}, {"type": "null"}],
            "default": None,
        },
        "name": {"title": "Name", "type": "string"},
    },
    "required": ["name"],
    "title": "_Sparse",
    "type": "object",
}


@pytest.mark.parametrize(
    "model,task,extra",
    [
        ("openai/gpt-5.6-luna", "result_summary", {"reasoning": {"effort": "none"}}),
        (
            "openai/gpt-oss-120b",
            "capability_conflict",
            {"reasoning": {"effort": "medium"}, "temperature": 0},
        ),
    ],
)
def test_consumer_routes_keep_their_whole_payload_for_sparse_schemas(model, task, extra):
    """Whole-payload snapshot taken from the integration code before the Business
    prompt-schema rule existed."""

    payload = openrouter._json_schema_payload(
        model=model,
        messages=[{"role": "user", "content": "probe"}],
        schema_model=_Sparse,
        schema_name=task,
        profile=openrouter_profile_for_task(task),
    )
    assert payload == {
        "model": model,
        "messages": [{"role": "user", "content": "probe"}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": task, "strict": True, "schema": _SPARSE_SCHEMA},
        },
        "provider": {"require_parameters": True},
        "max_tokens": 700,
        **extra,
    }
