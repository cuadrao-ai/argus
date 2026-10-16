from __future__ import annotations

import json

import httpx
import pytest
from argus.llm import openrouter
from pydantic import BaseModel


class Result(BaseModel):
    answer: str


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-test-key")
    monkeypatch.setenv("ARGUS_STRUCTURED_MODEL", "openai/test-primary")
    monkeypatch.setenv("ARGUS_STRUCTURED_MODEL_FALLBACK", "openai/test-fallback")
    monkeypatch.setattr(openrouter, "resolve_openrouter_api_key", lambda: "synthetic-test-key")


@pytest.mark.parametrize("task", list(openrouter.OPENROUTER_PROFILES))
def test_schema_request_requires_retention_policy(task):
    payload = openrouter.openrouter_schema_payload(
        model="openai/test-primary", messages=[{"role": "user", "content": "synthetic"}],
        schema_model=Result, schema_name="Result", profile=openrouter.openrouter_profile_for_task(task),
    )
    assert payload["provider"]["zdr"] is True
    assert payload["provider"]["data_collection"] == "deny"
    assert payload["provider"]["allow_fallbacks"] is False


@pytest.mark.asyncio
async def test_chat_http_request_requires_retention_policy(configured, monkeypatch):
    requests = []
    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(openrouter.httpx, "AsyncClient", lambda **kwargs: client)
    assert await openrouter.invoke_openrouter_chat_completion(task="chat_composer", messages=[], model_name="openai/test") == "ok"
    assert requests[0]["provider"]["zdr"] is True
    assert requests[0]["provider"]["data_collection"] == "deny"


@pytest.mark.parametrize("mode", ["sync", "async", "chat"])
@pytest.mark.parametrize("status,code", [(404, 404), (200, 404), (400, 400)])
@pytest.mark.asyncio
async def test_zdr_unavailable_stops_before_model_fallback(configured, monkeypatch, mode, status, code):
    from argus.llm.openrouter_retention import OpenRouterZDRUnavailableError
    from loguru import logger

    requests, records = [], []
    private_text = "synthetic-private-receipt-and-provider-body"
    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(status, json={"error": {"code": code, "message": "No endpoints matching your data policy " + private_text}})
    transport = httpx.MockTransport(respond)
    client = httpx.Client(transport=transport) if mode == "sync" else httpx.AsyncClient(transport=transport)
    monkeypatch.setattr(openrouter.httpx, "Client" if mode == "sync" else "AsyncClient", lambda **kwargs: client)
    monkeypatch.setattr(openrouter, "openrouter_model_candidates", lambda *a, **k: ["openai/primary", "openai/fallback"])
    monkeypatch.setattr(openrouter, "openrouter_structured_model_candidates", lambda *a, **k: ["openai/primary", "openai/fallback"])
    args = dict(task="interpretation", messages=[{"role": "user", "content": private_text}])
    sink = logger.add(lambda message: records.append(message.record))
    try:
        with pytest.raises(OpenRouterZDRUnavailableError) as error:
            if mode == "chat":
                await openrouter.invoke_openrouter_chat_completion(**args)
            elif mode == "async":
                await openrouter.invoke_openrouter_json_schema(**args, schema_model=Result, schema_name="Result")
            else:
                openrouter.invoke_openrouter_json_schema_sync(**args, schema_model=Result, schema_name="Result")
    finally:
        logger.remove(sink)
    assert len(requests) == 1
    assert error.value.model == "openai/primary"
    assert private_text not in str(error.value) + str(records)
    events = [record for record in records if record["message"] == "llm_zdr_unavailable"]
    assert len(events) == 1
    assert events[0]["extra"] == {"model": "openai/primary"}


def test_request_guard_cannot_opt_out_of_retention():
    from argus.llm.openrouter_request_policy import (
        guard_openrouter_request,
        openrouter_request_guard,
    )
    payload = {"model": "openai/test"}
    def weaken(task, value):
        return {**value, "provider": {"zdr": False, "data_collection": "allow", "allow_fallbacks": True}}
    with openrouter_request_guard(weaken):
        with pytest.raises(PermissionError, match="openrouter_retention_policy_changed"):
            guard_openrouter_request("interpretation", payload)


@pytest.mark.parametrize("status", [200, 404])
def test_web_search_uses_policy_and_typed_error(status):
    from argus.domain.research.search.openrouter_web_search import (
        OpenRouterWebSearchProvider,
    )
    from argus.llm.openrouter_retention import OpenRouterZDRUnavailableError
    requests = []
    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(status, json={"choices": [{"message": {"content": "", "annotations": []}}]})
    provider = OpenRouterWebSearchProvider(api_key="synthetic-test-key", model="openai/test", transport=httpx.MockTransport(respond))
    if status == 404:
        with pytest.raises(OpenRouterZDRUnavailableError):
            provider.search("synthetic", max_results=1, timeout_seconds=2)
    else:
        assert provider.search("synthetic", max_results=1, timeout_seconds=2).results == ()
    assert len(requests) == 1
    assert requests[0]["provider"] == openrouter.openrouter_provider_policy()


@pytest.mark.parametrize("mode", ["sync", "async", "stream", "astream"])
@pytest.mark.asyncio
async def test_langchain_enforces_policy_at_invocation(monkeypatch, mode):
    from argus.llm.openrouter_langchain import BaseChatOpenRouter, ChatOpenRouter
    observed = []
    def sync(self, *a, **kwargs):
        observed.append(kwargs)
        return "ok"
    async def asynchronous(self, *a, **kwargs):
        return sync(self, *a, **kwargs)
    def stream(self, *a, **kwargs):
        yield sync(self, *a, **kwargs)
    async def astream(self, *a, **kwargs):
        yield sync(self, *a, **kwargs)
    for name, fake in [("_generate", sync), ("_agenerate", asynchronous), ("_stream", stream), ("_astream", astream)]:
        monkeypatch.setattr(BaseChatOpenRouter, name, fake)
    model = ChatOpenRouter(model_name="openai/test", openrouter_api_key="synthetic-test-key")
    args = {"provider": {"zdr": True, "data_collection": "deny"}}
    if mode == "sync":
        assert model._generate([], **args) == "ok"
    elif mode == "async":
        assert await model._agenerate([], **args) == "ok"
    elif mode == "stream":
        assert list(model._stream([], **args)) == ["ok"]
    else:
        assert [chunk async for chunk in model._astream([], **args)] == ["ok"]
    assert observed[0]["provider"] == openrouter.openrouter_provider_policy()


@pytest.mark.asyncio
async def test_langchain_maps_sdk_404_to_typed_error(monkeypatch):
    from argus.llm.openrouter_langchain import BaseChatOpenRouter, ChatOpenRouter
    from argus.llm.openrouter_retention import OpenRouterZDRUnavailableError
    class SDKError(Exception):
        status_code = 404
    async def fail(*a, **k):
        raise SDKError("synthetic-private-provider-body")
    monkeypatch.setattr(BaseChatOpenRouter, "_agenerate", fail)
    model = ChatOpenRouter(model_name="openai/test", openrouter_api_key="synthetic-test-key")
    with pytest.raises(OpenRouterZDRUnavailableError) as error:
        await model._agenerate([])
    assert str(error.value) == "llm_zdr_unavailable"
    assert error.value.__suppress_context__ is True


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.asyncio
async def test_reasoning_retry_keeps_retention_policy(configured, monkeypatch, mode):
    requests = []
    def respond(request):
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            return httpx.Response(400, json={"error": {"code": 400, "message": "Unsupported reasoning parameter"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"answer":"ok"}'}}]})
    transport = httpx.MockTransport(respond)
    client = httpx.Client(transport=transport) if mode == "sync" else httpx.AsyncClient(transport=transport)
    monkeypatch.setattr(openrouter.httpx, "Client" if mode == "sync" else "AsyncClient", lambda **kwargs: client)
    monkeypatch.setattr(openrouter.model_policy, "can_retry_without_reasoning", lambda payload: True)
    args = dict(task="interpretation", messages=[], model_name="openai/test", schema_model=Result, schema_name="Result")
    result = openrouter.invoke_openrouter_json_schema_sync(**args) if mode == "sync" else await openrouter.invoke_openrouter_json_schema(**args)
    assert result.answer == "ok"
    assert len(requests) == 2
    assert "reasoning" not in requests[1]
    assert all(body["provider"] == openrouter.openrouter_provider_policy() for body in requests)


@pytest.mark.parametrize("status", [200, 404])
@pytest.mark.asyncio
async def test_real_langchain_sdk_wire_policy_and_failure(status):
    from argus.llm.openrouter_langchain import ChatOpenRouter
    from argus.llm.openrouter_retention import OpenRouterZDRUnavailableError
    from openrouter import OpenRouter

    requests = []
    def respond(request):
        requests.append(json.loads(request.content))
        body = {"error": {"code": 404, "message": "No endpoints found matching your data policy"}}
        if status == 200:
            body = {"id": "synthetic", "model": "openai/test", "object": "chat.completion", "created": 1, "system_fingerprint": None, "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}]}
        return httpx.Response(status, json=body)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        sdk = OpenRouter(api_key="synthetic-test-key", async_client=client)
        model = ChatOpenRouter(model_name="openai/test", openrouter_api_key="synthetic-test-key", client=sdk)
        if status == 200:
            assert (await model.ainvoke("synthetic")).content == "ok"
        else:
            with pytest.raises(OpenRouterZDRUnavailableError):
                await model.ainvoke("synthetic")
    assert len(requests) == 1
    assert requests[0]["provider"] == openrouter.openrouter_provider_policy()


@pytest.mark.asyncio
async def test_real_langchain_sdk_embedded_error_is_typed():
    from argus.llm.openrouter_langchain import ChatOpenRouter
    from argus.llm.openrouter_retention import OpenRouterZDRUnavailableError
    from openrouter import OpenRouter
    def respond(request):
        return httpx.Response(200, json={"error": {"code": 404, "message": "No endpoints available"}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        model = ChatOpenRouter(model_name="openai/test", openrouter_api_key="synthetic", client=OpenRouter(api_key="synthetic", async_client=client))
        with pytest.raises(OpenRouterZDRUnavailableError):
            await model.ainvoke("synthetic")


@pytest.mark.parametrize("setting", ["zdr", "data_collection", "allow_fallbacks", "require_parameters"])
def test_langchain_rejects_policy_override_before_sdk_dispatch(monkeypatch, setting):
    from argus.llm.openrouter_langchain import BaseChatOpenRouter, ChatOpenRouter
    def unexpected(*args, **kwargs):
        pytest.fail("Policy override reached the SDK")
    monkeypatch.setattr(BaseChatOpenRouter, "_generate", unexpected)
    model = ChatOpenRouter(model_name="openai/test", openrouter_api_key="synthetic")
    value = "allow" if setting == "data_collection" else not openrouter.openrouter_provider_policy()[setting]
    with pytest.raises(PermissionError, match="openrouter_retention_policy_changed"):
        model._generate([], provider={setting: value})


@pytest.mark.parametrize("key,value", [("zdr", 1), ("require_parameters", 1), ("allow_fallbacks", 0)])
def test_retention_boolean_parameters_require_json_booleans(key, value):
    from argus.llm.openrouter_retention import enforce_openrouter_retention
    with pytest.raises(PermissionError, match="openrouter_retention_policy_changed"):
        enforce_openrouter_retention({"provider": {key: value}})


@pytest.mark.asyncio
async def test_legacy_fallback_zdr_failure_stops_before_repairs(configured, monkeypatch):
    from argus.agent_runtime import llm_interpreter
    from argus.agent_runtime.capabilities.contract import (
        build_default_capability_contract,
    )
    from argus.agent_runtime.stages.interpret import InterpretationRequest
    from argus.agent_runtime.state.models import UserState
    from argus.llm.openrouter_retention import OpenRouterZDRUnavailableError

    models = []
    class FailedModel:
        def with_structured_output(self, schema):
            if len(models) == 1:
                raise RuntimeError("synthetic primary outage")
            raise OpenRouterZDRUnavailableError("openai/fallback")
    def build(task, model_name=None):
        models.append(model_name)
        return FailedModel()
    async def repair(**kwargs):
        pytest.fail("ZDR failure reached a repair call")
    monkeypatch.setattr(llm_interpreter, "build_openrouter_model", build)
    monkeypatch.setattr(openrouter, "resolve_openrouter_model", lambda *a, fallback=False, **k: "openai/fallback" if fallback else "openai/primary")
    monkeypatch.setattr(llm_interpreter, "_plan_pending_artifact_assumption_edit", repair)
    interpreter = llm_interpreter.OpenRouterStructuredInterpreter(contract=build_default_capability_contract(), model_name="openai/primary")
    request = InterpretationRequest(current_user_message="synthetic", recent_thread_history=[], latest_task_snapshot=None, user=UserState(user_id="synthetic"))
    with pytest.raises(OpenRouterZDRUnavailableError):
        await interpreter.ainvoke(request)
    assert models == ["openai/primary", "openai/fallback"]
