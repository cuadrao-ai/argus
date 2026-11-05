"""Local request admission must finish before a Business read is charged."""

from unittest.mock import AsyncMock

import httpx
import pytest
from argus.llm import openrouter, openrouter_transport, provider_permit
from pydantic import BaseModel


class Result(BaseModel):
    value: int


@pytest.fixture
def rig(monkeypatch):
    monkeypatch.setattr(openrouter, "resolve_openrouter_api_key", lambda: "fixture-key")
    monkeypatch.setattr(openrouter, "openrouter_structured_model_candidates", lambda *a, **k: ["fixture/model", "fixture/fallback"])
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": '{"value": 1}'}}]})

    client_type = httpx.AsyncClient
    monkeypatch.setattr(openrouter.httpx, "AsyncClient", lambda **kwargs: client_type(transport=httpx.MockTransport(respond), **kwargs))
    return calls, AsyncMock()


async def invoke(charge):
    return await openrouter.invoke_openrouter_json_schema(
        task="document_extraction", messages=[], schema_model=Result,
        schema_name="fixture", model_name="fixture/model", before_request=charge,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("refusal", ["key", "model", "permit", "payload", "guard", "serialization"])
async def test_local_transport_refusal_never_charges(rig, monkeypatch, refusal):
    calls, charge = rig
    if refusal == "key":
        monkeypatch.setattr(openrouter, "resolve_openrouter_api_key", lambda: "")
    elif refusal == "model":
        monkeypatch.setattr(openrouter, "openrouter_structured_model_candidates", lambda *a, **k: [])
    elif refusal == "permit":
        monkeypatch.setattr(provider_permit, "reserve_provider_call", lambda *a: None)
    elif refusal == "serialization":
        monkeypatch.setattr(openrouter, "_json_schema_payload", lambda **k: {"model": "fixture/model", "invalid": object()})
    else:
        def refuse(*args, **kwargs):
            raise ValueError("local refusal")
        target, name = (openrouter_transport, "_guard_request") if refusal == "guard" else (openrouter, "_json_schema_payload")
        monkeypatch.setattr(target, name, refuse)
    try:
        await invoke(charge)
    except (ValueError, TypeError) as error:
        assert "before_request" not in str(error)
    assert calls == []
    charge.assert_not_awaited()


@pytest.mark.asyncio
async def test_admission_refusal_never_sends_or_falls_back(rig):
    calls, charge = rig
    refusal = RuntimeError("read refused")
    charge.side_effect = refusal
    with pytest.raises(provider_permit.ProviderAdmissionError) as raised:
        await invoke(charge)
    assert raised.value.reason is refusal
    charge.assert_awaited_once()
    assert calls == []


@pytest.mark.asyncio
async def test_charge_precedes_first_send_and_is_not_repeated_for_fallback(rig, monkeypatch):
    calls, charge = rig
    def retention(response, model):
        charge.assert_awaited_once()
        if len(calls) == 1:
            raise ValueError("retry response")
    monkeypatch.setattr(openrouter_transport, "check_retention_response", retention)
    assert await invoke(charge) == Result(value=1)
    assert len(calls) == 2
    charge.assert_awaited_once()


@pytest.mark.asyncio
async def test_admission_time_is_not_charged_to_network_timeout(rig, monkeypatch):
    import asyncio
    from dataclasses import replace

    calls, charge = rig
    profile = openrouter.openrouter_profile_for_task("document_extraction")
    monkeypatch.setattr(openrouter, "openrouter_profile_for_task", lambda task: replace(profile, timeout_seconds=0.01))
    charge.side_effect = lambda: None

    async def slow_admission():
        await asyncio.sleep(0.025)
        await charge()

    assert await invoke(slow_admission) == Result(value=1)
    assert len(calls) == 1
    charge.assert_awaited_once()


@pytest.mark.asyncio
async def test_reasoning_retry_keeps_one_charge(rig, monkeypatch):
    calls, charge = rig

    def retention(response, model):
        if len(calls) == 1:
            refused = httpx.Response(400, request=response.request)
            raise httpx.HTTPStatusError("retry response", request=response.request, response=refused)

    monkeypatch.setattr(openrouter_transport, "check_retention_response", retention)
    monkeypatch.setattr(openrouter_transport.model_policy, "can_retry_without_reasoning", lambda payload: True)
    assert await invoke(charge) == Result(value=1)
    assert len(calls) == 2
    charge.assert_awaited_once()
