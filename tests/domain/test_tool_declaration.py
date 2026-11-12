"""Tool contracts are tested with a typed echo, never a production calculator."""

from __future__ import annotations

import importlib.util
import json
from dataclasses import replace

import pytest
from faker import Faker
from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model


def test_tool_declaration_has_a_neutral_owner() -> None:
    assert importlib.util.find_spec("argus.domain.tool_declaration") is not None


class EchoArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    first: float | None = None
    second: float | None = None
    third: float | None = None
    fourth: float | None = None
    fifth: float | None = None


class EchoResult(BaseModel):
    unknown: str
    values: dict[str, float | None]


def echo(arguments: EchoArguments) -> EchoResult:
    values = arguments.model_dump()
    return EchoResult(
        unknown=next(name for name, value in values.items() if value is None),
        values=values,
    )


def echo_card(arguments: EchoArguments, outcome):
    from argus.domain.tool_contracts import (
        LocalizedText,
        ToolCardPresentation,
        ToolFact,
        ToolInputFact,
    )

    return ToolCardPresentation(
        title=LocalizedText(locale_key="tools.echo.title"),
        answer=(
            ToolFact(
                name="unknown",
                label=LocalizedText(locale_key="tools.echo.unknown"),
                value=outcome.result["unknown"],
            )
            if outcome.status == "succeeded"
            else None
        ),
        inputs=[
            ToolInputFact(
                name=name,
                label=LocalizedText(locale_key=f"tools.echo.{name}"),
                value=value,
                editable=value is not None,
                unknown=value is None,
                visibility="public",
            )
            for name, value in arguments.model_dump().items()
        ],
    )


@pytest.fixture
def declaration():
    from argus.domain.tool_declaration import (
        ExactlyOneUnknown,
        ToolCardBinding,
        ToolDeclaration,
        ToolPolicy,
        ToolProgressTemplate,
    )

    return ToolDeclaration(
        name="echo",
        description="Return the original typed inputs and identify the blank.",
        handler=echo,
        policy=ToolPolicy(editable_fields=tuple(EchoArguments.model_fields)),
        progress=ToolProgressTemplate(
            locale_key="tools.echo.progress", argument_fields=("first",)
        ),
        card=ToolCardBinding(card_type="facts", version=1, presenter=echo_card),
        rules=(ExactlyOneUnknown(fields=tuple(EchoArguments.model_fields)),),
        domain=("Values are preserved without a numerical calculation.",),
    )


def known_values(blank: str) -> dict[str, float | None]:
    return {name: None if name == blank else 0.0 for name in EchoArguments.model_fields}


@pytest.mark.parametrize("blank", tuple(EchoArguments.model_fields))
def test_exactly_one_blank_keeps_all_other_zero_values(declaration, blank):
    arguments = declaration.validate_arguments(known_values(blank))
    assert arguments.model_dump() == known_values(blank)
    schema = declaration.tool_schema()["parameters"]
    assert len(schema["allOf"][0]["oneOf"]) == len(EchoArguments.model_fields)


@pytest.mark.parametrize("values", [{}, dict.fromkeys(EchoArguments.model_fields, 0)])
def test_cross_argument_rule_rejects_zero_or_multiple_blanks(declaration, values):
    with pytest.raises(ValueError, match="exactly_one_unknown"):
        declaration.validate_arguments(values)


def test_signature_is_the_single_argument_and_return_type_owner(declaration):
    assert declaration.arguments_type is EchoArguments
    assert declaration.result_type is EchoResult
    assert set(declaration.tool_schema()["parameters"]["properties"]) == set(
        EchoArguments.model_fields
    )
    assert declaration.tool_schema()["returns"] == EchoResult.model_json_schema()


def test_invalid_declaration_fails_at_registration(declaration):
    def untyped(arguments):
        return arguments

    with pytest.raises(TypeError, match="typed"):
        replace(declaration, handler=untyped)
    with pytest.raises(ValueError, match="field"):
        replace(
            declaration,
            progress=replace(declaration.progress, argument_fields=("missing",)),
        )


@pytest.mark.asyncio
async def test_invocation_checks_input_and_return_and_projects_card(declaration):
    from argus.domain.tool_contracts import ToolCall, ToolResultCard

    call = ToolCall(
        tool_name=declaration.name, call_id="call_a", arguments=known_values("fifth")
    )
    outcome = await declaration.invoke(call.arguments)
    assert outcome.status == "succeeded"
    assert outcome.result == echo(EchoArguments(**call.arguments)).model_dump()
    card = declaration.result_card(call=call, outcome=outcome, artifact_id="artifact_a")
    assert ToolResultCard.model_validate_json(card.model_dump_json()) == card
    assert card.presentation.inputs[0].value == 0.0
    assert card.presentation.inputs[-1].unknown


def test_numeric_inputs_default_to_private_visibility():
    from argus.domain.tool_contracts import LocalizedText, ToolInputFact

    fact = ToolInputFact(
        name="amount", label=LocalizedText(locale_key="tools.echo.amount"), value=0
    )
    assert fact.model_dump().get("visibility") == "private"


@pytest.mark.asyncio
async def test_card_projection_preserves_explicit_public_input_visibility(declaration):
    from argus.domain.tool_contracts import ToolCall, ToolInputFact

    def present(arguments, outcome):
        presentation = echo_card(arguments, outcome)
        public_input = ToolInputFact(
            **presentation.inputs[0].model_dump(exclude={"visibility"}),
            visibility="public",
        )
        return presentation.model_copy(update={"inputs": [public_input]})

    bound = replace(declaration, card=replace(declaration.card, presenter=present))
    call = ToolCall(tool_name="echo", call_id="public", arguments=known_values("fifth"))
    card = bound.result_card(
        call=call, outcome=await bound.invoke(call.arguments), artifact_id="public"
    )
    assert card.presentation.inputs[0].visibility == "public"


@pytest.mark.asyncio
async def test_invalid_inputs_never_call_handler(declaration):
    called = []

    def handler(arguments: EchoArguments) -> EchoResult:
        called.append(arguments)
        return echo(arguments)

    outcome = await replace(declaration, handler=handler).invoke({})
    assert outcome.status == "invalid"
    assert outcome.result is None
    assert called == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["invalid", "ambiguous", "bounded", "unavailable"])
async def test_declared_failures_have_no_answer(declaration, status):
    from argus.domain.tool_declaration import ToolInvocationError

    def handler(arguments: EchoArguments) -> EchoResult:
        raise ToolInvocationError(status, code="echo_unavailable")

    outcome = await replace(declaration, handler=handler).invoke(known_values("fifth"))
    assert outcome.status == status
    assert outcome.result is None
    assert outcome.failure.code == "echo_unavailable"


@pytest.mark.asyncio
async def test_wrong_return_is_withheld(declaration):
    def handler(arguments: EchoArguments) -> EchoResult:
        return {"unexpected": "not a typed result"}

    outcome = await replace(declaration, handler=handler).invoke(known_values("first"))
    assert outcome.status == "unavailable"
    assert outcome.result is None


def test_progress_interpolates_typed_zero_without_model_call(declaration):
    arguments = declaration.validate_arguments(known_values("fifth"))
    progress = declaration.progress_facts(arguments, call_id="call_a")
    assert progress.interpolation_args == {"first": 0.0}
    assert progress.locale_key == declaration.progress.locale_key
    assert progress.call_id == "call_a"


def test_paid_tools_cannot_declare_free_answer_first_policy():
    from argus.domain.tool_declaration import ToolPolicy

    with pytest.raises(ValueError):
        ToolPolicy(execution="local", external_calls=1, confirmation="never")


def test_catalog_keeps_actual_declarations_and_derived_capabilities(declaration):
    from argus.domain.tool_declaration import ToolCatalog

    catalog = ToolCatalog((declaration,))
    assert catalog.get("echo") is declaration
    assert "echo" in catalog.capability_text()
    assert "exactly_one_unknown" in catalog.capability_text()
    assert "Values are preserved" in catalog.capability_text()
    assert json.loads(catalog.capability_text())[0] == declaration.tool_schema()
    with pytest.raises(ValueError, match="duplicate"):
        ToolCatalog((declaration, declaration))


def test_failure_cannot_be_serialized_as_successful_answer():
    from argus.domain.tool_contracts import ToolFailure, ToolOutcome

    with pytest.raises(ValidationError):
        ToolOutcome(
            status="bounded", result={"value": 3}, failure=ToolFailure(code="bounded")
        )
    with pytest.raises(ValidationError):
        ToolOutcome(status="succeeded", result=None)


def test_recompute_retains_unknown_and_rejects_uneditable_fields(declaration):
    original = declaration.validate_arguments(known_values("fifth"))
    changed = declaration.recompute_arguments(original, {"first": 12})
    assert changed.first == 12
    assert changed.fifth is None
    with pytest.raises(ValueError, match="unknown"):
        declaration.recompute_arguments(original, {"fifth": 12, "first": None})
    limited = replace(
        declaration, policy=replace(declaration.policy, editable_fields=("first",))
    )
    with pytest.raises(ValueError, match="editable"):
        limited.recompute_arguments(original, {"second": 4})


class NestedArguments(BaseModel):
    values: EchoArguments
    names: list[str]


def nested_echo(arguments: NestedArguments) -> EchoResult:
    return echo(arguments.values)


def test_progress_reads_nested_typed_facts_without_copied_arguments(declaration):
    nested = replace(
        declaration,
        handler=nested_echo,
        policy=replace(declaration.policy, editable_fields=()),
        rules=(),
        progress=replace(declaration.progress, argument_fields=("values.first", "names")),
    )
    arguments = nested.validate_arguments(
        {"values": known_values("fifth"), "names": ["A", "B"]}
    )
    assert nested.progress_facts(arguments, call_id="call_a").interpolation_args == {
        "first": 0.0,
        "names": "A, B",
    }


@pytest.mark.asyncio
async def test_trusted_context_is_not_an_argument_the_model_can_supply(declaration):
    trusted = object()

    def handler(arguments: EchoArguments, *, context: object) -> EchoResult:
        assert context is trusted
        return echo(arguments)

    bound = replace(declaration, handler=handler)
    assert "context" not in bound.tool_schema()["parameters"]["properties"]
    result = await bound.invoke(known_values("fifth"), context=trusted)
    assert result.status == "succeeded"
    rejected = await bound.invoke(
        {**known_values("fifth"), "context": "injected"}, context=trusted
    )
    assert rejected.status == "invalid"


def test_workflow_confirmation_is_declared_independently_of_execution():
    from argus.domain.tool_declaration import ToolPolicy

    policy = ToolPolicy(execution="workflow", external_calls=1, confirmation="never")
    assert policy.confirmation == "never"


def test_public_receipts_require_explicit_declaration(declaration):
    assert declaration.policy.public_receipt == "disabled"
    assert declaration.tool_schema()["policy"]["public_receipt"] == "disabled"


@pytest.mark.parametrize("public_receipt", ["disabled", "typed_facts", "cited_facts"])
def test_public_receipt_policy_is_derived_in_the_catalog(declaration, public_receipt):
    from argus.domain.tool_declaration import ToolCatalog

    bound = replace(
        declaration, policy=replace(declaration.policy, public_receipt=public_receipt)
    )
    catalog = ToolCatalog((bound,))
    schema = json.loads(catalog.capability_text())[0]
    assert (
        schema["policy"]["public_receipt"]
        == catalog.get(bound.name).policy.public_receipt
    )


@pytest.mark.parametrize("public_receipt", [None, True, 1, "enabled"])
def test_public_receipt_policy_rejects_undeclared_modes(public_receipt):
    from argus.domain.tool_declaration import ToolPolicy

    with pytest.raises(ValueError, match="public receipt"):
        ToolPolicy(public_receipt=public_receipt)




class AmountArguments(BaseModel):
    amount: float


class AmountResult(BaseModel):
    amount: float


def echo_amount(arguments: AmountArguments) -> AmountResult:
    return AmountResult(amount=arguments.amount)


@pytest.mark.parametrize("as_answer", [True, False])
@pytest.mark.asyncio
async def test_result_units_derive_into_answer_and_rows(declaration, as_answer):
    from argus.domain.tool_contracts import (
        LocalizedText,
        ToolCall,
        ToolCardPresentation,
        ToolFact,
    )
    from argus.domain.tool_declaration import ToolPolicy, ToolUnit

    unit = LocalizedText(locale_key="chat.tools.units.currency")

    def present(arguments, outcome):
        fact = ToolFact(
            name="amount",
            label=LocalizedText(locale_key="tools.echo.amount"),
            value=outcome.result["amount"],
        )
        return ToolCardPresentation(
            title=LocalizedText(locale_key="tools.echo.title"),
            answer=fact if as_answer else None,
            rows=[] if as_answer else [fact],
        )

    bound = replace(
        declaration,
        handler=echo_amount,
        policy=ToolPolicy(),
        progress=replace(declaration.progress, argument_fields=("amount",)),
        card=replace(declaration.card, presenter=present),
        rules=(),
        units=(ToolUnit(source="result", field="amount", unit=unit),),
    )
    call = ToolCall(tool_name=bound.name, call_id="amount", arguments={"amount": 0})
    card = bound.result_card(
        call=call,
        outcome=await bound.invoke(call.arguments),
        artifact_id="amount",
    )
    fact = card.presentation.answer if as_answer else card.presentation.rows[0]
    assert fact.value == 0
    assert fact.unit == unit


@pytest.mark.parametrize(
    "alias_kind", ["alias", "validation_alias", "serialization_alias"]
)
def test_unsupported_argument_aliases_fail_registration(declaration, alias_kind):
    argument_type = create_model(
        "AliasedEchoArguments",
        __base__=EchoArguments,
        first=(float | None, Field(default=None, **{alias_kind: "target_amount"})),
    )

    def handler(arguments: EchoArguments) -> EchoResult:
        return echo(arguments)

    handler.__annotations__["arguments"] = argument_type
    with pytest.raises(ValueError, match="alias"):
        replace(declaration, handler=handler)


@pytest.mark.parametrize(
    ("annotation", "default"),
    [
        (float | None, 0),
        (float, None),
        (float | None, ...),
        (float | None, Field(default_factory=lambda: None)),
    ],
    ids=["known-default", "not-nullable", "required", "factory"],
)
def test_unknown_rule_rejects_defaults_that_disagree_with_blank_schema(
    declaration, annotation, default
):
    argument_type = create_model(
        "DefaultedEchoArguments",
        __base__=EchoArguments,
        first=(annotation, default),
    )

    def handler(arguments: EchoArguments) -> EchoResult:
        return echo(arguments)

    handler.__annotations__["arguments"] = argument_type
    with pytest.raises(ValueError, match="nullable.*default None"):
        replace(declaration, handler=handler)


@pytest.mark.parametrize("annotation", [dict[str, float], list[int], EchoArguments])
def test_progress_rejects_nonscalar_leaves_at_registration(declaration, annotation):
    argument_type = create_model(
        "InvalidProgressArguments", __base__=EchoArguments, first=(annotation, ...)
    )

    def handler(arguments: EchoArguments) -> EchoResult:
        return echo(arguments)

    handler.__annotations__["arguments"] = argument_type
    with pytest.raises(ValueError, match="Progress.*scalar"):
        replace(declaration, handler=handler, rules=())


def test_result_card_validates_completed_result_before_calling_presenter(declaration):
    from argus.domain.tool_contracts import (
        LocalizedText,
        ToolCall,
        ToolCardPresentation,
        ToolOutcome,
    )

    presented = []

    def present(arguments, outcome):
        presented.append(outcome)
        return ToolCardPresentation(title=LocalizedText(locale_key="tools.echo.title"))

    bound = replace(declaration, card=replace(declaration.card, presenter=present))
    with pytest.raises(ValidationError):
        bound.result_card(
            call=ToolCall(
                tool_name=bound.name,
                call_id="completion",
                arguments=known_values("first"),
            ),
            outcome=ToolOutcome(status="succeeded", result={"unexpected": "wrong model"}),
            artifact_id="completion",
        )
    assert presented == []


class EchoConfirmation(BaseModel):
    unknown: str
    approved: bool


def test_required_confirmation_needs_a_real_binding(declaration):
    from argus.domain.tool_declaration import ToolPolicy

    with pytest.raises(ValueError, match="confirmation handler"):
        replace(
            declaration,
            policy=ToolPolicy(execution="workflow", confirmation="required"),
        )


def test_confirmation_binding_uses_same_argument_model_and_trusted_context(declaration):
    def wrong_arguments(arguments: EchoResult, *, context: object) -> EchoConfirmation:
        return EchoConfirmation(unknown=arguments.unknown, approved=False)

    def no_context(arguments: EchoArguments) -> EchoConfirmation:
        return EchoConfirmation(unknown=echo(arguments).unknown, approved=False)

    def untyped_return(arguments: EchoArguments, *, context: object):
        return False

    for handler, message in (
        (wrong_arguments, "same argument model"),
        (no_context, "trusted context"),
        (untyped_return, "typed Pydantic models"),
    ):
        with pytest.raises(TypeError, match=message):
            replace(declaration, confirmation_handler=handler)


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.asyncio
async def test_confirmation_preparation_validates_args_and_returns_typed_result(
    declaration, asynchronous
):
    from argus.domain.tool_declaration import ToolPolicy

    trusted = object()
    prepared = []

    def prepare(arguments: EchoArguments, *, context: object) -> EchoConfirmation:
        assert context is trusted
        prepared.append(arguments)
        return EchoConfirmation(unknown=echo(arguments).unknown, approved=False)

    async def async_prepare(
        arguments: EchoArguments, *, context: object
    ) -> EchoConfirmation:
        return prepare(arguments, context=context)

    bound = replace(
        declaration,
        policy=ToolPolicy(execution="workflow", confirmation="required"),
        confirmation_handler=async_prepare if asynchronous else prepare,
    )
    result = await bound.prepare_confirmation(known_values("first"), context=trusted)
    assert isinstance(result, EchoConfirmation)
    assert result.unknown == "first"
    assert result.approved is False
    assert len(prepared) == 1
    assert prepared[0].second == 0
    assert "context" not in bound.tool_schema()["parameters"]["properties"]


@pytest.mark.asyncio
async def test_confirmation_never_invokes_binding_for_invalid_arguments(declaration):
    from argus.domain.tool_declaration import ToolInvocationError

    prepared = []

    def prepare(arguments: EchoArguments, *, context: object) -> EchoConfirmation:
        prepared.append(arguments)
        return EchoConfirmation(unknown=echo(arguments).unknown, approved=False)

    bound = replace(declaration, confirmation_handler=prepare)
    with pytest.raises(ToolInvocationError, match="exactly_one_unknown"):
        await bound.prepare_confirmation({}, context=object())
    assert prepared == []


@pytest.mark.asyncio
async def test_confirmation_revalidates_model_instances_from_binding(declaration):
    def prepare(arguments: EchoArguments, *, context: object) -> EchoConfirmation:
        return EchoConfirmation.model_construct(
            unknown=echo(arguments).unknown, approved="invalid boolean"
        )

    bound = replace(declaration, confirmation_handler=prepare)
    with pytest.raises(ValidationError):
        await bound.prepare_confirmation(known_values("first"), context=object())


def test_research_narrative_and_canonical_sources_survive_card_presentation():
    from argus.domain.research.contracts import ResearchSource
    from argus.domain.tool_contracts import LocalizedText, ToolCardPresentation

    fake = Faker()
    narrative = fake.paragraph()
    source = ResearchSource(url=fake.url(), title=fake.sentence())
    presentation = ToolCardPresentation(
        title=LocalizedText(locale_key="chat.tools.research.title"),
        narrative=narrative,
        sources=[source],
    )
    hydrated = ToolCardPresentation.model_validate_json(presentation.model_dump_json())
    assert hydrated.narrative == narrative
    assert hydrated.sources == [source]
    assert isinstance(hydrated.sources[0], ResearchSource)


@pytest.mark.parametrize("status", ["invalid", "ambiguous", "bounded", "unavailable"])
def test_research_narrative_cannot_bypass_failed_card_answer_guard(status):
    from argus.domain.tool_contracts import (
        LocalizedText,
        ToolCardPresentation,
        ToolFailure,
        ToolOutcome,
        ToolResultCard,
    )

    presentation = ToolCardPresentation(
        title=LocalizedText(locale_key="chat.tools.research.title"),
        narrative=Faker().paragraph(),
    )
    with pytest.raises(ValidationError, match="cannot present an answer"):
        ToolResultCard(
            tool_name="echo",
            call_id="failed",
            artifact_id="failed",
            card_type="facts",
            card_version=1,
            arguments={},
            outcome=ToolOutcome(status=status, failure=ToolFailure(code="no_answer")),
            presentation=presentation,
        )


@pytest.mark.parametrize("annotation", [EchoArguments | int, list[EchoArguments]])
def test_progress_path_requires_a_model_for_every_nonnull_branch(declaration, annotation):
    argument_type = create_model("MixedProgressArguments", values=(annotation, ...))

    def handler(arguments: NestedArguments) -> EchoResult:
        return echo(arguments.values)

    handler.__annotations__["arguments"] = argument_type
    with pytest.raises(ValueError, match="traverse typed model fields only"):
        replace(
            declaration,
            handler=handler,
            rules=(),
            policy=replace(declaration.policy, editable_fields=()),
            progress=replace(declaration.progress, argument_fields=("values.first",)),
        )


@pytest.fixture
def visual_payload():
    return {
        "kind": "portfolio_equity",
        "currency": "USD",
        "base_value": 0.0,
        "series": [{"time": Faker().date(), "value": 0.0}],
    }


def test_visual_evidence_round_trips_in_shared_card_presentation(visual_payload):
    from argus.domain import tool_contracts

    presentation = tool_contracts.ToolCardPresentation(
        title=tool_contracts.LocalizedText(locale_key="chat.tools.backtest.title"),
        visual=visual_payload,
    )
    hydrated = tool_contracts.ToolCardPresentation.model_validate_json(
        presentation.model_dump_json()
    )
    assert isinstance(hydrated.visual, tool_contracts.ToolVisual)
    assert isinstance(hydrated.visual.series[0], tool_contracts.ToolVisualPoint)
    assert hydrated.visual.model_dump() == visual_payload


@pytest.mark.parametrize("location", ["base_value", "series"])
@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), -float("inf"), True, "12.3"]
)
def test_visual_transport_rejects_nonfinite_or_coerced_numbers(
    visual_payload, location, value
):
    from argus.domain import tool_contracts

    if location == "base_value":
        visual_payload[location] = value
    else:
        visual_payload[location][0]["value"] = value
    with pytest.raises(ValidationError):
        tool_contracts.ToolVisual.model_validate(visual_payload)


@pytest.mark.parametrize("status", ["invalid", "ambiguous", "bounded", "unavailable"])
def test_visual_evidence_cannot_bypass_failed_card_answer_guard(visual_payload, status):
    from argus.domain.tool_contracts import (
        LocalizedText,
        ToolCardPresentation,
        ToolFailure,
        ToolOutcome,
        ToolResultCard,
    )

    presentation = ToolCardPresentation(
        title=LocalizedText(locale_key="chat.tools.backtest.title"),
        visual=visual_payload,
    )
    with pytest.raises(ValidationError, match="cannot present an answer"):
        ToolResultCard(
            tool_name="echo",
            call_id="failed",
            artifact_id="failed",
            card_type="facts",
            card_version=1,
            arguments={},
            outcome=ToolOutcome(status=status, failure=ToolFailure(code="no_answer")),
            presentation=presentation,
        )


def test_localized_value_preserves_its_canonical_raw_fact():
    from argus.domain.tool_contracts import LocalizedText, ToolFact

    fact = ToolFact(
        name="cadence",
        label=LocalizedText(locale_key="chat.tools.backtest.cadence"),
        value="monthly",
        value_text=LocalizedText(locale_key="receipt.cadence.monthly"),
    )
    hydrated = ToolFact.model_validate_json(fact.model_dump_json())
    assert hydrated.value == "monthly"
    assert hydrated.value_text.locale_key == "receipt.cadence.monthly"
    assert hydrated.value_text.interpolation_args == {}
