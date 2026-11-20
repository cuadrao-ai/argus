from __future__ import annotations

from copy import deepcopy
from numbers import Real
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from argus.agent_runtime.state.models import IntentName, SimplificationOption


def freeze_contract_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType(
            {
                key: freeze_contract_payload(nested_value)
                for key, nested_value in value.items()
            }
        )
    if isinstance(value, list):
        return tuple(freeze_contract_payload(item) for item in value)
    if isinstance(value, tuple):
        return tuple(freeze_contract_payload(item) for item in value)
    if isinstance(value, set):
        return frozenset(freeze_contract_payload(item) for item in value)
    if isinstance(value, frozenset):
        return frozenset(freeze_contract_payload(item) for item in value)
    return value


def clone_contract_payload(value: Any) -> Any:
    if isinstance(value, MappingProxyType):
        return {
            key: clone_contract_payload(nested_value)
            for key, nested_value in value.items()
        }
    if isinstance(value, tuple):
        return [clone_contract_payload(item) for item in value]
    if isinstance(value, frozenset):
        return {clone_contract_payload(item) for item in value}
    return deepcopy(value)


class CapabilityRange(BaseModel):
    model_config = ConfigDict(frozen=True)

    minimum: float | None = None
    maximum: float | None = None
    allowed_values: tuple[Any, ...] = ()


class ValidationRule(BaseModel):
    model_config = ConfigDict(frozen=True)

    field_name: str
    rule_type: str
    message: str


class FieldDescription(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str
    description: str


class OptionalParameterSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    default_value: Any
    description: FieldDescription
    allowed_range: CapabilityRange | None = None

    @model_validator(mode="after")
    def freeze_default_value(self) -> "OptionalParameterSpec":
        object.__setattr__(
            self,
            "default_value",
            freeze_contract_payload(self.default_value),
        )
        return self


class UnsupportedCombination(BaseModel):
    model_config = ConfigDict(frozen=True)

    fields: dict[str, Any]
    reason: str

    @model_validator(mode="after")
    def freeze_fields(self) -> "UnsupportedCombination":
        object.__setattr__(
            self,
            "fields",
            MappingProxyType(
                {
                    key: freeze_contract_payload(value)
                    for key, value in self.fields.items()
                }
            ),
        )
        return self


class SimplificationTemplate(BaseModel):
    model_config = ConfigDict(frozen=True)

    category: str
    options: tuple[SimplificationOption, ...] = ()


class CapabilityContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str
    supported_intents: tuple[IntentName, ...] = ()
    supported_tool_families: tuple[str, ...] = ()
    required_field_descriptions: dict[str, FieldDescription] = Field(default_factory=dict)
    optional_parameters: dict[str, OptionalParameterSpec] = Field(default_factory=dict)
    validation_rules: tuple[ValidationRule, ...] = ()
    unsupported_combinations: tuple[UnsupportedCombination, ...] = ()
    simplification_templates: dict[str, SimplificationTemplate] = Field(
        default_factory=dict
    )

    @property
    def required_fields(self) -> list[str]:
        return list(self.required_field_descriptions)

    @property
    def optional_defaults(self) -> dict[str, Any]:
        return {
            name: clone_contract_payload(spec.default_value)
            for name, spec in self.optional_parameters.items()
        }

    @property
    def allowed_ranges(self) -> dict[str, CapabilityRange]:
        return {
            name: deepcopy(spec.allowed_range)
            for name, spec in self.optional_parameters.items()
            if spec.allowed_range is not None
        }

    def get_optional_parameter(self, name: str) -> OptionalParameterSpec:
        return deepcopy(self.optional_parameters[name])

    def get_allowed_range(self, name: str) -> CapabilityRange | None:
        parameter = self.optional_parameters.get(name)
        if parameter is None:
            return None
        return deepcopy(parameter.allowed_range)

    def get_simplification_options(self, category: str) -> list[SimplificationOption]:
        template = self.simplification_templates.get(category)
        if template is None:
            return []
        return [
            SimplificationOption.model_validate(option.model_dump(mode="python"))
            for option in template.options
        ]

    def describe_field(self, name: str) -> FieldDescription | None:
        if name in self.required_field_descriptions:
            return deepcopy(self.required_field_descriptions[name])
        parameter = self.optional_parameters.get(name)
        if parameter is None:
            return None
        return deepcopy(parameter.description)

    @model_validator(mode="after")
    def validate_contract_invariants(self) -> "CapabilityContract":
        object.__setattr__(
            self,
            "required_field_descriptions",
            MappingProxyType(dict(self.required_field_descriptions)),
        )
        object.__setattr__(
            self,
            "optional_parameters",
            MappingProxyType(dict(self.optional_parameters)),
        )
        object.__setattr__(
            self,
            "simplification_templates",
            MappingProxyType(dict(self.simplification_templates)),
        )

        overlapping_fields = set(self.required_field_descriptions).intersection(
            self.optional_parameters
        )
        if overlapping_fields:
            raise ValueError("Required and optional capability fields must not overlap.")

        declared_fields = set(self.required_field_descriptions).union(
            self.optional_parameters
        )
        unknown_rule_fields = {
            rule.field_name
            for rule in self.validation_rules
            if rule.field_name not in declared_fields
        }
        if unknown_rule_fields:
            unknown_names = ", ".join(sorted(unknown_rule_fields))
            raise ValueError(
                f"Validation rules reference unknown capability fields: {unknown_names}."
            )

        unknown_combination_fields = {
            field_name
            for combination in self.unsupported_combinations
            for field_name in combination.fields
            if field_name not in declared_fields
        }
        if unknown_combination_fields:
            unknown_names = ", ".join(sorted(unknown_combination_fields))
            raise ValueError(
                "Unsupported combinations reference unknown capability fields: "
                f"{unknown_names}."
            )

        mismatched_template_categories = {
            category
            for category, template in self.simplification_templates.items()
            if template.category != category
        }
        if mismatched_template_categories:
            category_names = ", ".join(sorted(mismatched_template_categories))
            raise ValueError(
                "Simplification template keys must match their declared category: "
                f"{category_names}."
            )

        for parameter_name, parameter in self.optional_parameters.items():
            self._validate_optional_parameter_default(
                parameter_name=parameter_name,
                parameter=parameter,
            )
        return self

    @staticmethod
    def _validate_optional_parameter_default(
        *,
        parameter_name: str,
        parameter: OptionalParameterSpec,
    ) -> None:
        allowed_range = parameter.allowed_range
        if allowed_range is None:
            return

        default_value = parameter.default_value

        if (
            allowed_range.allowed_values
            and default_value not in allowed_range.allowed_values
        ):
            allowed_values = ", ".join(
                str(value) for value in allowed_range.allowed_values
            )
            raise ValueError(
                f"Optional parameter '{parameter_name}' has default '{default_value}' "
                f"outside allowed values: {allowed_values}."
            )

        if not isinstance(default_value, Real) or isinstance(default_value, bool):
            return

        if allowed_range.minimum is not None and default_value < allowed_range.minimum:
            raise ValueError(
                f"Optional parameter '{parameter_name}' has default {default_value} "
                f"below minimum {allowed_range.minimum}."
            )
        if allowed_range.maximum is not None and default_value > allowed_range.maximum:
            raise ValueError(
                f"Optional parameter '{parameter_name}' has default {default_value} "
                f"above maximum {allowed_range.maximum}."
            )
