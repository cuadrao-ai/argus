import json
from decimal import Decimal

import httpx
import pytest
from argus.llm.openrouter import _post_openrouter_json_schema, openrouter_profile_for_task

from scripts.documents.budget import BenchmarkBudget, price_envelope


@pytest.fixture
def endpoint():
    return dict(
        tag="fixture-provider",
        context_length=100_000,
        max_completion_tokens=20_000,
        supported_parameters=["structured_outputs", "max_tokens"],
        pricing=dict(
            prompt="0.000001", completion="0.000002", input_cache_read="0.0000001"
        ),
    )


@pytest.fixture
def payload():
    return dict(
        model="fixture-model",
        max_tokens=openrouter_profile_for_task("document_extraction").max_tokens,
        messages=[],
        response_format={"type": "json_schema"},
        provider=dict(
            require_parameters=True,
            data_collection="deny",
            zdr=True,
            allow_fallbacks=False,
        ),
    )


async def post(client, payload):
    return await _post_openrouter_json_schema(
        client=client,
        api_key="unit-test-key",
        payload=payload,
        retry_attempt=(
            "document_extraction",
            90,
            payload["model"],
            "json_schema",
            "test",
            None,
        ),
    )


@pytest.mark.asyncio
async def test_reserves_before_http_and_blocks_second_attempt(endpoint, payload):
    budget = BenchmarkBudget(price_envelope("fixture-model", [endpoint]), Decimal("2"), 6)
    saved, requests = [], []

    def transport(request):
        assert saved[-1]["attempts"] == 1
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        with budget.attempt("one", lambda: saved.append(budget.evidence())):
            await post(client, payload)
            with pytest.raises(ValueError, match="already_attempted"):
                await post(client, payload)
        await post(client, payload)
    assert requests[0]["provider"] == payload["provider"] | dict(
        only=[endpoint["tag"]],
        max_price=dict(prompt=1.0, completion=2.0, request=0, image=0),
    )
    assert requests[1] == payload
    assert budget.evidence()["reserved_usd"] == str(budget.envelope.maximum_cost)


@pytest.mark.parametrize(
    "changes",
    [
        {"pricing": {"prompt": "NaN", "completion": "1"}},
        {"pricing": {"prompt": "1", "completion": "1", "new_fee": "0.1"}},
        {"context_length": None},
        {"supported_parameters": []},
    ],
)
def test_unbounded_endpoint_never_admitted(endpoint, changes):
    with pytest.raises(ValueError, match="no_bounded_endpoint"):
        price_envelope("fixture-model", [endpoint | changes])


def test_entire_run_must_fit_before_first_attempt(endpoint):
    envelope = price_envelope("fixture-model", [endpoint])
    with pytest.raises(ValueError, match="run_exceeds_cap"):
        BenchmarkBudget(envelope, envelope.maximum_cost * 6 - Decimal("0.01"), 6)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"model": "different"},
        {"max_tokens": 999999},
        {"plugins": []},
        {"preset": "search-enabled"},
        {"presets": ["search-enabled"]},
        {"models": []},
        {"tools": []},
        {"provider": {"zdr": False}},
    ],
)
async def test_payload_changes_fail_before_http(endpoint, payload, changes):
    budget = BenchmarkBudget(price_envelope("fixture-model", [endpoint]), Decimal("2"), 6)

    def transport(request):
        pytest.fail("invalid request dispatched")

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        with budget.attempt("one", lambda: None):
            with pytest.raises(ValueError, match="unexpected_benchmark_request"):
                await post(client, payload | changes)


@pytest.mark.asyncio
async def test_timeout_keeps_reservation_and_persistence_failure_never_sends(
    endpoint, payload
):
    budget = BenchmarkBudget(price_envelope("fixture-model", [endpoint]), Decimal("2"), 6)
    calls = []

    def transport(request):
        calls.append(request)
        raise httpx.ReadTimeout("timeout")

    def fail_save():
        raise OSError("disk full")

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        with budget.attempt("one", lambda: None):
            with pytest.raises(httpx.ReadTimeout):
                await post(client, payload)
        with budget.attempt("two", fail_save):
            with pytest.raises(OSError):
                await post(client, payload)
    assert len(calls) == 1
    assert budget.evidence()["attempts"] == 2
    assert Decimal(budget.evidence()["reserved_usd"]) == budget.envelope.maximum_cost * 2


@pytest.mark.asyncio
async def test_six_attempts_cannot_become_seven(endpoint, payload):
    budget = BenchmarkBudget(price_envelope("fixture-model", [endpoint]), Decimal("2"), 6)
    requests = []

    def transport(request):
        requests.append(request)
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        for index in range(budget.max_attempts):
            with budget.attempt(str(index), lambda: None):
                await post(client, payload)
        with budget.attempt("extra", lambda: None):
            with pytest.raises(ValueError, match="spend_cap_reached"):
                await post(client, payload)
    assert len(requests) == budget.max_attempts


@pytest.mark.parametrize("field", ["prompt", "input_cache_read", "input_cache_write"])
def test_price_envelope_reserves_highest_input_and_output_tiers(endpoint, field):
    prices = endpoint["pricing"] | {
        "input_cache_write": "0.00000125",
        "overrides": [
            {"min_prompt_tokens": 10000, field: "0.000003", "completion": "0.000005"},
            {"min_prompt_tokens": 20000, "prompt": "0.000002", "completion": "0.000004"},
        ],
    }
    envelope = price_envelope("fixture-model", [endpoint | {"pricing": prices}])
    assert envelope.prompt == Decimal("0.000003" if field == "prompt" else "0.000002")
    assert envelope.completion == Decimal("0.000005")
    assert envelope.maximum_cost == endpoint["context_length"] * Decimal(
        "0.000003"
    ) + envelope.output_tokens * Decimal("0.000005")


def test_cache_write_is_full_input_price_not_added_to_prompt(endpoint):
    prices = endpoint["pricing"] | {"input_cache_write": "0.00000125"}
    envelope = price_envelope("fixture-model", [endpoint | {"pricing": prices}])
    assert envelope.prompt == Decimal("0.000001")
    assert envelope.cache_write == Decimal("0.00000125")
    assert (
        envelope.maximum_cost
        == endpoint["context_length"] * envelope.cache_write
        + envelope.output_tokens * envelope.completion
    )


@pytest.mark.parametrize(
    "overrides",
    [
        None,
        {},
        [None],
        [{}],
        [{"min_prompt_tokens": -1}],
        [{"min_prompt_tokens": True}],
        [{"min_prompt_tokens": "10"}],
        [{"min_prompt_tokens": 1.5}],
        [{"min_prompt_tokens": 10, "new_fee": "0.01"}],
        [{"min_prompt_tokens": 10, "input_cache_write": "NaN"}],
        [{"min_prompt_tokens": 10, "overrides": []}],
    ],
)
def test_malformed_or_unbounded_price_tiers_are_rejected(endpoint, overrides):
    prices = endpoint["pricing"] | {"overrides": overrides}
    with pytest.raises(ValueError, match="no_bounded_endpoint"):
        price_envelope("fixture-model", [endpoint | {"pricing": prices}])


@pytest.mark.asyncio
async def test_two_tiered_calls_fit_remaining_cap_without_extra_attempt(
    endpoint, payload
):
    prior = Decimal("1.4030075136")
    remaining = Decimal("6") - prior
    prices = dict(
        prompt="0.00000032",
        completion="0.00000128",
        input_cache_read="0.000000064",
        input_cache_write="0.0000004",
        overrides=[
            dict(
                min_prompt_tokens=256000,
                prompt="0.00000096",
                completion="0.00000384",
                input_cache_read="0.000000192",
                input_cache_write="0.0000012",
            )
        ],
    )
    envelope = price_envelope(
        "fixture-model", [endpoint | dict(context_length=1_000_000, pricing=prices)]
    )
    budget = BenchmarkBudget(envelope, remaining, 2)
    assert prior + envelope.maximum_cost * 2 == Decimal("3.8951675136")
    calls = []

    def transport(request):
        calls.append(request)
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        for sample in ("statement-usd", "receipt-dop"):
            with budget.attempt(sample, lambda: None):
                await post(client, payload)
        with budget.attempt("extra", lambda: None):
            with pytest.raises(ValueError, match="spend_cap_reached"):
                await post(client, payload)
    assert len(calls) == 2
    assert json.loads(calls[0].content)["provider"]["max_price"]["prompt"] == 0.96
    assert envelope.evidence()["reserved_input_usd_per_token"] == "0.0000012"
    with pytest.raises(ValueError, match="run_exceeds_cap"):
        BenchmarkBudget(envelope, Decimal("2") - prior, 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("output_parameter", ["max_tokens", "max_completion_tokens"])
async def test_output_parameter_and_conditional_search_price(
    endpoint, payload, output_parameter
):
    prices = dict(prompt="0.00000025", completion="0.00000075", web_search="0.01")
    envelope = price_envelope(
        "fixture-model",
        [
            endpoint
            | dict(
                context_length=1_050_000,
                pricing=prices,
                supported_parameters=["structured_outputs", output_parameter],
            )
        ],
    )
    assert envelope.output_parameter == output_parameter
    assert envelope.evidence()["output_parameter"] == output_parameter
    assert envelope.maximum_cost == Decimal("0.2715")
    prior = Decimal("2.6490875136")
    budget = BenchmarkBudget(envelope, Decimal("6") - prior, 2)
    assert prior + envelope.maximum_cost * 2 == Decimal("3.1920875136")
    payload.pop("max_tokens")
    payload[output_parameter] = envelope.output_tokens
    requests = []

    def transport(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        with budget.attempt("allowed", lambda: None):
            await post(client, payload)
        alternate = (
            "max_completion_tokens" if output_parameter == "max_tokens" else "max_tokens"
        )
        invalid = [
            payload | {alternate: envelope.output_tokens},
            {k: v for k, v in payload.items() if k != output_parameter},
            payload | {output_parameter: 1},
        ]
        invalid.extend(
            payload | {key: {}}
            for key in ("tools", "plugins", "models", "route", "web_search_options")
        )
        invalid.append(payload | {"model": "fixture-model:online"})
        for index, request in enumerate(invalid):
            with budget.attempt(str(index), lambda: None):
                with pytest.raises(ValueError, match="unexpected_benchmark_request"):
                    await post(client, request)
    assert len(requests) == 1
    assert requests[0][output_parameter] == envelope.output_tokens
    assert alternate not in requests[0]


@pytest.mark.parametrize("fee", ["NaN", "-0.01", "Infinity"])
@pytest.mark.parametrize("tier", [False, True])
def test_invalid_conditional_search_price_still_rejected(endpoint, fee, tier):
    prices = endpoint["pricing"] | (
        {"overrides": [{"min_prompt_tokens": 0, "web_search": fee}]}
        if tier
        else {"web_search": fee}
    )
    with pytest.raises(ValueError, match="no_bounded_endpoint"):
        price_envelope("fixture-model", [endpoint | {"pricing": prices}])


def test_prefers_existing_output_parameter_when_both_supported(endpoint):
    endpoint["supported_parameters"].append("max_completion_tokens")
    assert price_envelope("fixture-model", [endpoint]).output_parameter == "max_tokens"


def test_online_model_cannot_bypass_tool_fee_exclusion(endpoint):
    with pytest.raises(ValueError, match="no_bounded_endpoint"):
        price_envelope("fixture-model:online", [endpoint])
