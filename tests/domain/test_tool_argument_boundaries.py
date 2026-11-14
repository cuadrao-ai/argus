"""Declared objects reject lost facts while declared maps retain their own keys."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from dataclasses import replace
from typing import Any

import pytest
from argus.domain.tool_contracts import LocalizedText, ToolCardPresentation
from argus.domain.tool_declaration import (
    ToolCardBinding,
    ToolDeclaration,
    ToolPolicy,
    ToolProgressTemplate,
)
from faker import Faker
from pydantic import BaseModel, Field, ValidationError, field_validator

fake = Faker()


class LooseValue(BaseModel):
    amount: float | None = Field(default=0, ge=0)
    extra_parameters: dict[str, Any] = Field(default_factory=dict)


class NamedValue(BaseModel):
    label: str

    @field_validator("label")
    @classmethod
    def strip_label(cls, value: str) -> str:
        return value.strip()


class BoundaryArguments(BaseModel):
    detail: LooseValue | None = None
    items: list[LooseValue] = Field(default_factory=list)
    choice: LooseValue | NamedValue | None = None
    by_name: dict[str, LooseValue] = Field(default_factory=dict)
    extra_parameters: dict[str, Any] = Field(default_factory=dict)


def echo_arguments(arguments: BoundaryArguments) -> BoundaryArguments:
    return arguments


@pytest.fixture
def declaration() -> ToolDeclaration:
    return ToolDeclaration(
        name="boundary_echo",
        description="Return declared input facts unchanged.",
        handler=echo_arguments,
        policy=ToolPolicy(),
        progress=ToolProgressTemplate(locale_key="tools.echo.progress"),
        card=ToolCardBinding(
            card_type="facts",
            version=1,
            presenter=lambda _arguments, _outcome: ToolCardPresentation(
                title=LocalizedText(locale_key="tools.echo.title")
            ),
        ),
    )


def _parse(boundary: str, declaration: ToolDeclaration, arguments: dict[str, Any]):
    if boundary == "runtime":
        return declaration.validate_arguments(arguments)
    return declaration.call_arguments_type.model_validate(arguments)


@pytest.mark.parametrize("boundary", ["runtime", "declared_model"])
@pytest.mark.parametrize(
    "arguments",
    [
        {"detail": {"amount": 0, "unknown": 0}},
        {"items": [{"amount": None, "unknown": 0}]},
        {"choice": {"label": "named", "unknown": 0}},
        {"by_name": {"item": {"amount": 0, "unknown": 0}}},
    ],
    ids=["optional", "list", "union", "typed-map-value"],
)
def test_unknown_nested_typed_fields_are_rejected_before_discard(
    declaration, boundary, arguments
):
    with pytest.raises(ValidationError) as rejected:
        _parse(boundary, declaration, arguments)
    assert any(error["type"] == "extra_forbidden" for error in rejected.value.errors())


@pytest.mark.parametrize("boundary", ["runtime", "declared_model"])
def test_declared_maps_zero_null_defaults_and_validators_survive(declaration, boundary):
    maps = {"arbitrary": {"unknown": [0, None]}}
    arguments = {
        "detail": {"amount": None, "extra_parameters": maps},
        "items": [{"amount": 0}],
        "choice": {"label": "  named  "},
        "by_name": {"defaulted": {}},
        "extra_parameters": maps,
    }
    parsed = _parse(boundary, declaration, arguments)
    assert isinstance(parsed, BoundaryArguments)
    assert parsed.detail.amount is None
    assert parsed.items[0].amount == 0
    assert parsed.by_name["defaulted"].amount == 0
    assert parsed.choice.label == "named"
    assert parsed.extra_parameters == parsed.detail.extra_parameters == maps
    with pytest.raises(ValidationError):
        _parse(boundary, declaration, {"detail": {"amount": -1}})


@pytest.mark.asyncio
async def test_invocation_withholds_result_for_undeclared_nested_fact(declaration):
    outcome = await declaration.invoke({"detail": {"amount": 0, "unknown": 0}})
    assert outcome.status == "invalid"
    assert outcome.result is None


@pytest.mark.parametrize("boundary", ["runtime", "declared_model"])
def test_tool_schemas_close_typed_objects_and_keep_open_map_contracts(
    declaration, boundary
):
    if boundary == "runtime":
        schema = declaration.tool_schema()["parameters"]
        argument_schema = schema
    else:
        schema = declaration.call_arguments_type.model_json_schema()
        argument_schema = schema
    assert argument_schema["additionalProperties"] is False
    assert (
        argument_schema["properties"]["extra_parameters"]["additionalProperties"] is True
    )
    nested = [
        value
        for value in schema["$defs"].values()
        if value.get("title") in {"LooseValue", "NamedValue"}
    ]
    assert len(nested) == 2
    assert all(value.get("additionalProperties") is False for value in nested)


def test_tool_model_derivation_does_not_change_legacy_model_reads(declaration):
    replacement = replace(declaration, name="other_boundary_echo")
    for tool in (declaration, replacement):
        with pytest.raises(ValidationError):
            tool.validate_arguments({"detail": {"unknown": 0}})
    assert LooseValue.model_validate({"unknown": 0}).amount == 0
    assert BoundaryArguments.model_validate({"unknown": 0}).detail is None




def test_forward_references_resolve_in_the_callable_model_namespace():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            textwrap.dedent("""
            from pydantic import BaseModel, ValidationError
            from argus.domain.tool_contracts import LocalizedText, ToolCardPresentation
            from argus.domain.tool_declaration import (
                ToolCardBinding, ToolDeclaration, ToolPolicy, ToolProgressTemplate,
            )

            class ForwardArguments(BaseModel):
                value: list["DeferredValue"]

            class DeferredValue(BaseModel):
                amount: int

            def read_value(arguments: ForwardArguments) -> DeferredValue:
                return arguments.value[0]

            tool = ToolDeclaration(
                name="read_value", description="Read the supplied value.",
                handler=read_value, policy=ToolPolicy(),
                progress=ToolProgressTemplate(locale_key="tools.read.progress"),
                card=ToolCardBinding(card_type="facts", version=1,
                    presenter=lambda _args, _outcome: ToolCardPresentation(
                        title=LocalizedText(locale_key="tools.read.title"))),
            )
            assert tool.validate_arguments({"value": [{"amount": 0}]}).value[0].amount == 0
            try:
                tool.validate_arguments({"value": [{"amount": 0, "lost": 1}]})
            except ValidationError as error:
                assert error.errors()[0]["type"] == "extra_forbidden"
            else:
                raise AssertionError("The derived nested model discarded a field")
            assert ForwardArguments.model_validate(
                {"value": [{"amount": 0, "legacy": 1}]}
            ).value[0].amount == 0
            assert "additionalProperties" not in DeferredValue.model_json_schema()
            assert tool.tool_schema()["parameters"]["$defs"]["DeferredValue"][
                "additionalProperties"
            ] is False
        """),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
