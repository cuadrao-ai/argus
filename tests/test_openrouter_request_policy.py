from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from argus.domain.ingestion.documents.models import ExtractionResult
from argus.llm import openrouter
from argus.llm.openrouter import (
    openrouter_profile_for_task,
)
from argus.llm.openrouter_request_policy import guard_openrouter_request
from pydantic import BaseModel, ConfigDict, ValidationError


class FakeChatOpenRouter:
    calls: list[dict] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.calls.append(kwargs)


@pytest.mark.parametrize("task", openrouter.OPENROUTER_TASK_MODEL_TIERS)
@pytest.mark.parametrize(
    "model", ["openai/gpt-6-luna-pro", "openai/gpt-6-luna-pro-20260922"]
)
def test_luna_pro_sampling_capability_preserves_structured_request_policy(
    task: openrouter.OpenRouterTask, model: str
) -> None:
    class DateRangeIntent(BaseModel):
        start_date: str | None = None
        end_date: str | None = None

    arguments = {
        "messages": [{"role": "user", "content": "hello"}],
        "schema_model": DateRangeIntent,
        "schema_name": "DateRangeIntent",
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
    monkeypatch.setenv("CUADRAO_OPENROUTER_API_KEY_DEV", "test-key")
    monkeypatch.setattr(openrouter, "ChatOpenRouter", FakeChatOpenRouter)
    assert openrouter.build_openrouter_model("interpretation", model_name=model)
    assert FakeChatOpenRouter.calls == [
        {
            "model_name": model,
            "max_tokens": 3200,
            "timeout": 20,
            "max_retries": 1,
            "openrouter_api_key": "test-key",
            "openrouter_provider": openrouter.openrouter_provider_policy(),
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

    monkeypatch.setenv("CUADRAO_OPENROUTER_API_KEY_DEV", "test-key")
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
    assert payload["provider"] == openrouter.openrouter_provider_policy()
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
        (NestedWireResult, {"item": {"value": "kept"}}, True),
        (NestedWireResult, {"item": {"note": "missing value"}}, False),
        (NestedWireResult, {"item": {"value": "kept", "grant_id": "fake"}}, False),
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

    monkeypatch.setenv("CUADRAO_OPENROUTER_API_KEY_DEV", "mock-key")
    monkeypatch.setenv("CUADRAO_STRUCTURED_FALLBACK_MODEL", "")
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
    assert submitted[0]["provider"] == openrouter.openrouter_provider_policy()
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
                assert guard_openrouter_request("interpretation", payload) == {
                    **payload,
                    "outer": True,
                    "inner": True,
                    "provider": openrouter.openrouter_provider_policy(),
                }
                if failure:
                    raise RuntimeError("interrupted")
        except RuntimeError:
            assert failure
        assert guard_openrouter_request("interpretation", payload) == {
            **payload,
            "outer": True,
            "provider": openrouter.openrouter_provider_policy(),
        }
    assert events == ["outer", "inner", "outer"]
    assert guard_openrouter_request("interpretation", payload) == {**payload, "provider": openrouter.openrouter_provider_policy()}


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
        "provider": openrouter.openrouter_provider_policy(),
        "max_tokens": 700,
        **extra,
    }


_CONSUMER_SNAPSHOTS = {
    # (model, task): (max_tokens, reasoning effort, temperature or None)
    ("openai/gpt-oss-120b", "interpretation"): (3200, "medium", 0),
    ("openai/gpt-oss-120b", "chat_composer"): (1200, "none", 0.2),
    ("openai/gpt-5.6-luna", "interpretation"): (3200, "medium", 0),
    ("openai/gpt-5.6-luna", "chat_composer"): (1200, "none", 0.2),
    ("openai/gpt-6-luna", "interpretation"): (3200, "medium", 0),
    ("openai/gpt-6-luna", "chat_composer"): (1200, "none", 0.2),
}


@pytest.mark.parametrize("model,task", list(_CONSUMER_SNAPSHOTS))
def test_consumer_interpretation_and_composer_keep_their_whole_payload(model, task):
    """Snapshot taken from the integration code before the Business-only
    prompt-schema rule existed."""

    max_tokens, effort, temperature = _CONSUMER_SNAPSHOTS[(model, task)]
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
        "provider": openrouter.openrouter_provider_policy(),
        "max_tokens": max_tokens,
        "reasoning": {"effort": effort},
        "temperature": temperature,
    }


def test_document_read_allows_a_long_receipt_answer() -> None:
    profile = openrouter_profile_for_task("document_extraction")
    payload = openrouter._json_schema_payload(
        model="google/gemini-3.8-flash",
        messages=[{"role": "user", "content": "probe"}],
        schema_model=ExtractionResult,
        schema_name="document_observations",
        profile=profile,
    )
    assert payload["max_tokens"] == 16000


@pytest.mark.parametrize("async_path", [False, True])
@pytest.mark.parametrize("guard_order", ["observer_outer", "observer_inner"])
@pytest.mark.parametrize("failure", [None, "revoked", "route_drift"])
@pytest.mark.asyncio
async def test_actual_post_keeps_nested_diagnostic_then_access_guards(
    async_path, guard_order, failure
):
    import httpx
    from argus.llm import openrouter
    from argus.llm.openrouter_request_policy import (
        openrouter_payload_route,
        validate_openrouter_route,
    )

    events = []
    payload = {"model": "test/model", "provider": openrouter.openrouter_provider_policy()}
    routes = [openrouter_payload_route(payload)]

    def observer(task, actual):
        events.append("observer")
        if failure == "route_drift":
            actual = {**actual, "provider": {"allow_fallbacks": True}}
        return actual

    def access(task, actual):
        validate_openrouter_route(actual, routes)
        events.append("access")
        if failure == "revoked":
            raise PermissionError("captured_consent_revoked")
        return actual

    def post(url, **kwargs):
        events.append("post")
        assert kwargs["json"] == payload
        return httpx.Response(200, request=httpx.Request("POST", url))

    async def apost(url, **kwargs):
        return post(url, **kwargs)

    client = SimpleNamespace(post=apost if async_path else post)
    first, second = ((observer, False), (access, True))
    if guard_order == "observer_inner":
        first, second = second, first
    with openrouter.openrouter_request_guard(first[0], final=first[1]):
        with openrouter.openrouter_request_guard(second[0], final=second[1]):
            kwargs = dict(
                client=client,
                api_key="offline-placeholder",
                payload=payload,
                retry_attempt=(
                    "interpretation",
                    2.0,
                    "test/model",
                    "json_schema",
                    "Test",
                    None,
                ),
            )
            call = (
                openrouter._post_openrouter_json_schema
                if async_path
                else openrouter._post_openrouter_json_schema_sync
            )
            if failure:
                with pytest.raises(PermissionError):
                    if async_path:
                        await call(**kwargs)
                    else:
                        call(**kwargs)
            elif async_path:
                await call(**kwargs)
            else:
                call(**kwargs)
    assert events == (
        ["observer", "access", "post"]
        if not failure
        else ["observer", "access"]
        if failure == "revoked"
        else ["observer"]
    )
    assert openrouter._guard_request("interpretation", payload) is payload


@pytest.mark.parametrize("async_path", [False, True])
@pytest.mark.parametrize("revoke", [False, True])
@pytest.mark.asyncio
async def test_internal_reasoning_retry_rechecks_live_access_before_each_post(
    async_path, revoke, monkeypatch
):
    import httpx
    from argus.llm import openrouter

    payload = {"model": "test/model", "reasoning": {"effort": "medium"}}
    events = []
    live = {"value": True}

    def access(task, actual):
        events.append("access")
        if not live["value"]:
            raise PermissionError("captured_consent_revoked")
        return actual

    def post(url, **kwargs):
        events.append("post")
        if events.count("post") == 1:
            live["value"] = not revoke
            return httpx.Response(400, request=httpx.Request("POST", url))
        assert "reasoning" not in kwargs["json"]
        return httpx.Response(200, request=httpx.Request("POST", url))

    async def apost(url, **kwargs):
        return post(url, **kwargs)

    monkeypatch.setattr(
        openrouter,
        "_reserve_openrouter_attempt",
        lambda *args: SimpleNamespace(timeout_seconds=2.0),
    )
    kwargs = dict(
        client=SimpleNamespace(post=apost if async_path else post),
        api_key="offline-placeholder",
        payload=payload,
        retry_attempt=("interpretation", 2.0, "test/model", "json_schema", "Test", None),
    )
    call = (
        openrouter._post_openrouter_json_schema
        if async_path
        else openrouter._post_openrouter_json_schema_sync
    )
    with openrouter.openrouter_request_guard(access, final=True):
        if revoke:
            with pytest.raises(PermissionError, match="captured_consent_revoked"):
                if async_path:
                    await call(**kwargs)
                else:
                    call(**kwargs)
        elif async_path:
            await call(**kwargs)
        else:
            call(**kwargs)
    assert events == (
        ["access", "post", "access"] if revoke else ["access", "post", "access", "post"]
    )


@pytest.mark.parametrize("async_path", [False, True])
@pytest.mark.parametrize("denial", ["revoked", "undisclosed_fallback"])
@pytest.mark.asyncio
async def test_candidate_fallback_cannot_dispatch_after_access_or_route_denial(
    async_path, denial, monkeypatch
):
    import httpx
    from argus.llm import openrouter
    from argus.llm.openrouter_request_policy import validate_openrouter_route
    from pydantic import BaseModel

    class Result(BaseModel):
        ok: bool

    posts = []
    live = {"value": True}
    routes = [
        {"model": "test/primary", "provider": openrouter.openrouter_provider_policy()},
        {"model": "test/fallback", "provider": openrouter.openrouter_provider_policy()},
    ]

    def access(task, payload):
        validate_openrouter_route(payload, routes if denial == "revoked" else routes[:1])
        if not live["value"]:
            raise PermissionError("captured_consent_revoked")
        return payload

    def post(url, **kwargs):
        posts.append(kwargs["json"])
        live["value"] = denial != "revoked"
        return httpx.Response(503, request=httpx.Request("POST", url))

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def post(self, url, **kwargs):
            return post(url, **kwargs)

    class AsyncClient(Client):
        async def post(self, url, **kwargs):
            return post(url, **kwargs)

    monkeypatch.setattr(openrouter.httpx, "AsyncClient", AsyncClient)
    monkeypatch.setattr(openrouter.httpx, "Client", Client)
    monkeypatch.setattr(
        openrouter, "resolve_openrouter_api_key", lambda: "offline-placeholder"
    )
    monkeypatch.setattr(
        openrouter,
        "openrouter_structured_model_candidates",
        lambda *args, **kwargs: ["test/primary", "test/fallback"],
    )
    call = (
        openrouter.invoke_openrouter_json_schema
        if async_path
        else openrouter.invoke_openrouter_json_schema_sync
    )
    with openrouter.openrouter_request_guard(access, final=True):
        with pytest.raises(PermissionError):
            kwargs = dict(
                task="interpretation",
                messages=[],
                schema_model=Result,
                schema_name="Result",
            )
            if async_path:
                await call(**kwargs)
            else:
                call(**kwargs)
    assert len(posts) == 1
    assert posts[0]["model"] == "test/primary"


@pytest.mark.parametrize("extra", ["models", "route", "plugins", "provider"])
def test_disclosure_rejects_undisclosed_routing_or_recipient_overrides(extra):
    from argus.llm.openrouter_request_policy import validate_openrouter_route

    original = {"model": "test/model", "provider": None}
    changed = {**original, extra: {"override": True}}
    with pytest.raises(PermissionError, match="openrouter_consent_route_changed"):
        validate_openrouter_route(changed, [original])


@pytest.mark.asyncio
async def test_actual_post_access_guards_are_isolated_between_concurrent_tasks():
    import asyncio

    import httpx
    from argus.llm import openrouter

    posts = []

    async def run(model, admitted):
        def access(task, payload):
            assert payload["model"] == model
            if not admitted:
                raise PermissionError("captured_consent_revoked")
            return payload

        async def post(url, **kwargs):
            posts.append(kwargs["json"]["model"])
            return httpx.Response(200, request=httpx.Request("POST", url))

        with openrouter.openrouter_request_guard(access, final=True):
            await asyncio.sleep(0)
            return await openrouter._post_openrouter_json_schema(
                client=SimpleNamespace(post=post),
                api_key="offline-placeholder",
                payload={"model": model},
                retry_attempt=("interpretation", 2.0, model, "json_schema", "Test", None),
            )

    results = await asyncio.gather(
        run("test/allowed", True), run("test/denied", False), return_exceptions=True
    )
    assert isinstance(results[0], httpx.Response)
    assert isinstance(results[1], PermissionError)
    assert posts == ["test/allowed"]


@pytest.mark.parametrize("async_path", [False, True])
@pytest.mark.parametrize(
    "mutation", ["replacement", "model", "provider", "nested_provider"]
)
@pytest.mark.asyncio
async def test_nested_final_guard_cannot_change_intercepted_post_after_access(
    async_path, mutation
):
    import asyncio

    import httpx
    from argus.llm import openrouter
    from argus.llm.openrouter_request_policy import (
        openrouter_payload_route,
        validate_openrouter_route,
    )

    payload = {
        "model": "approved",
        "provider": {**openrouter.openrouter_provider_policy(), "order": ["disclosed"]},
    }
    routes = [openrouter_payload_route(payload)]
    posts = []

    def access(task, actual):
        validate_openrouter_route(actual, routes)
        return actual

    def nested_final(task, actual):
        if mutation == "replacement":
            return {**actual, "model": "undisclosed"}
        if mutation == "model":
            actual["model"] = "undisclosed"
        elif mutation == "provider":
            actual["provider"] = {"allow_fallbacks": True}
        else:
            actual["provider"]["order"].append("undisclosed")
        return actual

    def post(url, **kwargs):
        posts.append(kwargs["json"])
        return httpx.Response(200, request=httpx.Request("POST", url))

    async def apost(url, **kwargs):
        return post(url, **kwargs)

    with openrouter.openrouter_request_guard(access, final=True):
        await asyncio.sleep(0)
        with openrouter.openrouter_request_guard(nested_final, final=True):
            kwargs = dict(
                client=SimpleNamespace(post=apost if async_path else post),
                api_key="offline-placeholder",
                payload=payload,
                retry_attempt=(
                    "interpretation",
                    2.0,
                    "approved",
                    "json_schema",
                    "Test",
                    None,
                ),
            )
            with pytest.raises(PermissionError):
                if async_path:
                    await openrouter._post_openrouter_json_schema(**kwargs)
                else:
                    openrouter._post_openrouter_json_schema_sync(**kwargs)
    assert posts == []


@pytest.mark.asyncio
async def test_final_validator_captured_alias_cannot_change_intercepted_http_after_await():
    import asyncio

    import httpx
    from argus.llm import openrouter

    captured = []
    dispatched = []
    events = []
    payload = {
        "model": "approved",
        "provider": {**openrouter.openrouter_provider_policy(), "order": ["disclosed"]},
    }

    def access(task, actual):
        events.append("access")
        assert actual == payload
        return actual

    def inner_validator(task, actual):
        events.append("validator")
        captured.append(actual)
        return actual

    async def post(url, **kwargs):
        await asyncio.sleep(0)
        captured[0]["model"] = "undisclosed"
        captured[0]["provider"]["order"].append("undisclosed")
        dispatched.append(kwargs["json"])
        return httpx.Response(200, request=httpx.Request("POST", url))

    with openrouter.openrouter_request_guard(access, final=True):
        await asyncio.sleep(0)
        with openrouter.openrouter_request_guard(inner_validator, final=True):
            await openrouter._post_openrouter_json_schema(
                client=SimpleNamespace(post=post),
                api_key="offline-placeholder",
                payload=payload,
                retry_attempt=(
                    "interpretation",
                    2.0,
                    "approved",
                    "json_schema",
                    "Test",
                    None,
                ),
            )
    assert events == ["validator", "access"]
    assert dispatched == [
        {
            "model": "approved",
            "provider": {
                **openrouter.openrouter_provider_policy(),
                "order": ["disclosed"],
            },
        }
    ]
    assert dispatched[0] is not captured[0]
