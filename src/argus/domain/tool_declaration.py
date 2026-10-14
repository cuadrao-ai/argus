"""Executable declarations: one owner for schemas, validation and tool policy."""

from __future__ import annotations

import inspect
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType, UnionType
from typing import Annotated, Any, ForwardRef, Literal, Union, get_args, get_origin

from loguru import logger
from pydantic import BaseModel, ConfigDict, ValidationError, create_model

from argus.domain.tool_contracts import (
    TOOL_INPUT_SOURCES_FIELD,
    LocalizedText,
    ToolCall,
    ToolCardPresentation,
    ToolFact,
    ToolFactSource,
    ToolFailure,
    ToolFailureStatus,
    ToolInputFact,
    ToolOutcome,
    ToolProgress,
    ToolRepair,
    ToolResultCard,
)


class ToolInvocationError(ValueError):
    """A declared domain failure; no partial numerical answer crosses it."""

    def __init__(
        self,
        status: ToolFailureStatus,
        *,
        code: str,
        fields: tuple[str, ...] = (),
        repair: ToolRepair | None = None,
    ) -> None:
        self.outcome = ToolOutcome(
            status=status,
            failure=ToolFailure(code=code, fields=list(fields), repair=repair),
        )
        super().__init__(code)


@dataclass(frozen=True)
class ExactlyOneUnknown:
    fields: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(self.fields) < 2 or len(set(self.fields)) != len(self.fields):
            raise ValueError("An unknown rule needs distinct argument fields")

    def validate(self, arguments: BaseModel) -> None:
        if sum(getattr(arguments, name) is None for name in self.fields) != 1:
            raise ToolInvocationError(
                "invalid", code="exactly_one_unknown", fields=self.fields
            )

    def schema(self) -> dict[str, Any]:
        # An omitted nullable field is a blank; every other field must be
        # explicitly present and non-null. Zero satisfies non-null.
        return {
            "oneOf": [
                {
                    "properties": {
                        name: {"type": "null"}
                        if name == unknown
                        else {"not": {"type": "null"}}
                        for name in self.fields
                    },
                    "required": [name for name in self.fields if name != unknown],
                }
                for unknown in self.fields
            ],
            "description": "exactly_one_unknown: " + ", ".join(self.fields),
        }


PublicReceiptPolicy = Literal["disabled", "typed_facts", "cited_facts"]


MAX_DRIVING_INPUTS = 5


@dataclass(frozen=True)
class ToolPolicy:
    execution: Literal["local", "workflow", "provider"] = "local"
    external_calls: int = 0
    confirmation: Literal["never", "required"] = "never"
    editable_fields: tuple[str, ...] = ()
    # The inputs that drive the result, most telling first; a card shows at most
    # MAX_DRIVING_INPUTS of them that carry a value.
    driving_fields: tuple[str, ...] = ()
    retain_unknown: bool = True
    public_receipt: PublicReceiptPolicy = "disabled"

    def __post_init__(self) -> None:
        if self.execution not in {"local", "workflow", "provider"}:
            raise ValueError("Unknown tool execution policy")
        if self.confirmation not in {"never", "required"} or self.external_calls < 0:
            raise ValueError("Invalid tool cost or confirmation policy")
        if self.public_receipt not in get_args(PublicReceiptPolicy):
            raise ValueError("Invalid tool public receipt policy")
        if self.execution == "local" and self.external_calls != 0:
            raise ValueError("A local zero-cost tool cannot make external calls")
        if self.editable_fields and (
            self.execution != "local" or self.confirmation != "never"
        ):
            raise ValueError("Instant recompute is reserved for free local tools")
        if set(self.driving_fields) - set(self.editable_fields):
            raise ValueError("A driving input must be editable")


@dataclass(frozen=True)
class ToolProgressTemplate:
    locale_key: str
    argument_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolUnit:
    field: str
    unit: LocalizedText
    source: Literal["argument", "result"] = "argument"


@dataclass(frozen=True)
class ToolCardBinding:
    card_type: str
    version: int
    presenter: Callable[[Any, ToolOutcome], ToolCardPresentation]

    def __post_init__(self) -> None:
        if not self.card_type or self.version < 1 or not callable(self.presenter):
            raise ValueError("A card needs a type, positive version and real presenter")


def _model_annotation(handler: Callable[..., Any], annotation: Any) -> type[BaseModel]:
    if isinstance(annotation, str):
        function: Any = handler
        if not inspect.isfunction(handler):
            function = function.__call__
        annotation = eval(annotation, function.__globals__)  # noqa: S307
    if not inspect.isclass(annotation) or not issubclass(annotation, BaseModel):
        raise TypeError("Tool arguments and return must be typed Pydantic models")
    return annotation


def _callable_contract(
    handler: Callable[..., Any],
) -> tuple[type[BaseModel], type[BaseModel], bool]:
    if not callable(handler):
        raise TypeError("A tool needs a real typed callable")
    signature = inspect.signature(handler)
    parameters = tuple(signature.parameters.values())
    if not parameters or len(parameters) > 2:
        raise TypeError("A tool has typed arguments and optional trusted context")
    argument = parameters[0]
    if argument.kind not in {
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    }:
        raise TypeError("The first tool parameter must be a typed argument model")
    uses_context = len(parameters) == 2
    if uses_context and (
        parameters[1].name != "context"
        or parameters[1].kind != inspect.Parameter.KEYWORD_ONLY
    ):
        raise TypeError("Only keyword-only trusted context may accompany arguments")
    argument_type = _model_annotation(handler, argument.annotation)
    result_type = _model_annotation(handler, signature.return_annotation)
    _require_unaliased_fields(argument_type, result_type)
    return argument_type, result_type, uses_context


def _require_unaliased_fields(*models: type[BaseModel]) -> None:
    # One field name owns schema, progress, validation, and stored arguments.
    pending: list[Any] = list(models)
    seen: set[type[BaseModel]] = set()
    while pending:
        annotation = pending.pop()
        if not inspect.isclass(annotation) or not issubclass(annotation, BaseModel):
            pending.extend(get_args(annotation))
            continue
        if annotation in seen:
            continue
        seen.add(annotation)
        for name, model_field in annotation.model_fields.items():
            if any(
                alias is not None and alias != name
                for alias in (
                    model_field.alias,
                    model_field.validation_alias,
                    model_field.serialization_alias,
                )
            ):
                raise ValueError("Tool model field aliases are not supported")
            pending.append(model_field.annotation)


def _closed_tool_arguments(model: type[BaseModel]) -> type[BaseModel]:
    """Derive a closed input tree without changing the callable's legacy models."""
    derived: dict[type[BaseModel], type[BaseModel]] = {}

    def close(annotation: Any, owner: type[BaseModel]) -> Any:
        if isinstance(annotation, (str, ForwardRef)):
            expression = (
                annotation if isinstance(annotation, str) else annotation.__forward_arg__
            )
            # These are trusted Python type annotations, never input values.
            annotation = eval(expression, vars(inspect.getmodule(owner)))  # noqa: S307
        if inspect.isclass(annotation) and issubclass(annotation, BaseModel):
            if annotation not in derived:
                closed = create_model(
                    annotation.__name__,
                    __base__=annotation,
                    __module__=annotation.__module__,
                    __config__=ConfigDict(extra="forbid", defer_build=True),
                )
                derived[annotation] = closed
                # Pydantic gives subclasses their own FieldInfo instances. Keep
                # defaults, constraints and validators while replacing only types.
                for model_field in closed.model_fields.values():
                    model_field.annotation = close(model_field.annotation, annotation)
            return derived[annotation]
        arguments = get_args(annotation)
        origin = get_origin(annotation)
        if not arguments or origin is Literal:
            return annotation
        closed_arguments = (
            (close(arguments[0], owner), *arguments[1:])
            if origin is Annotated
            else tuple(close(argument, owner) for argument in arguments)
        )
        if closed_arguments == arguments:
            return annotation
        return (
            Union[closed_arguments] if origin is UnionType else origin[closed_arguments]
        )

    closed: type[BaseModel] = close(model, model)
    closed.model_rebuild(force=True)
    return closed


@dataclass(frozen=True)
class ToolDeclaration:
    name: str
    description: str
    handler: Callable[..., Any]
    policy: ToolPolicy
    progress: ToolProgressTemplate
    card: ToolCardBinding
    rules: tuple[ExactlyOneUnknown, ...] = ()
    domain: tuple[str, ...] = ()
    units: tuple[ToolUnit, ...] = ()
    surfaces: frozenset[str] = frozenset({"personal"})
    confirmation_handler: Callable[..., Any] | None = None
    arguments_type: type[BaseModel] = field(init=False, repr=False)
    call_arguments_type: type[BaseModel] = field(init=False, repr=False)
    result_type: type[BaseModel] = field(init=False, repr=False)
    confirmation_result_type: type[BaseModel] | None = field(init=False, repr=False)
    _uses_context: bool = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if re.fullmatch(r"[a-z][a-z0-9_]{0,79}", self.name) is None:
            raise ValueError("A tool name must be a stable snake_case identity")
        if not self.surfaces or not self.surfaces <= {"personal", "business"}:
            raise ValueError("A tool needs declared supported surfaces")
        if not self.description or not callable(self.handler):
            raise TypeError("A tool needs a description and a real typed callable")
        argument_type, result_type, uses_context = _callable_contract(self.handler)
        object.__setattr__(self, "arguments_type", argument_type)
        object.__setattr__(self, "result_type", result_type)
        object.__setattr__(self, "_uses_context", uses_context)
        confirmation_type = None
        if self.confirmation_handler is not None:
            confirmation_args, confirmation_type, confirmation_context = (
                _callable_contract(self.confirmation_handler)
            )
            if confirmation_args is not argument_type:
                raise TypeError(
                    "Confirmation must use the same argument model as execution"
                )
            if not confirmation_context:
                raise TypeError("Confirmation requires keyword-only trusted context")
        elif self.policy.confirmation == "required":
            raise ValueError("Required confirmation needs a real confirmation handler")
        object.__setattr__(self, "confirmation_result_type", confirmation_type)
        argument_fields = set(argument_type.model_fields)
        named_fields = set(self.policy.editable_fields)
        for rule in self.rules:
            named_fields.update(rule.fields)
        if not named_fields <= argument_fields:
            raise ValueError("Tool policy references an unknown argument field")
        for rule in self.rules:
            for name in rule.fields:
                model_field = argument_type.model_fields[name]
                if (
                    type(None) not in get_args(model_field.annotation)
                    or model_field.default is not None
                    or model_field.default_factory is not None
                ):
                    raise ValueError(
                        "Unknown-rule fields must be nullable with default None and no factory"
                    )
        progress_names = set()
        for path in self.progress.argument_fields:
            _validate_argument_path(argument_type, path)
            name = path.rsplit(".", 1)[-1]
            if name in progress_names:
                raise ValueError("Progress argument fields must have unique names")
            progress_names.add(name)
        for unit in self.units:
            owner = argument_type if unit.source == "argument" else result_type
            if unit.field not in owner.model_fields:
                raise ValueError("Tool unit references an unknown typed field")
        LocalizedText(locale_key=self.progress.locale_key)
        object.__setattr__(
            self, "call_arguments_type", _closed_tool_arguments(argument_type)
        )

    def validate_arguments(self, arguments: Mapping[str, Any] | BaseModel) -> BaseModel:
        validated = self._validated_model(arguments)
        for rule in self.rules:
            rule.validate(validated)
        return validated

    def _validated_model(self, arguments: Mapping[str, Any] | BaseModel) -> BaseModel:
        """The typed model before cross-argument rules; a card can show it either way."""
        raw = (
            arguments.model_dump(mode="python")
            if isinstance(arguments, BaseModel)
            else dict(arguments)
        )
        # Even a permissive third-party model cannot admit undeclared tool args.
        extra = set(raw) - set(self.arguments_type.model_fields)
        if extra:
            raise ToolInvocationError(
                "invalid", code="unknown_argument", fields=tuple(sorted(extra))
            )
        validated = self.call_arguments_type.model_validate(raw)
        _require_finite_json(validated.model_dump(mode="json"))
        return validated

    def tool_schema(self) -> dict[str, Any]:
        parameters = self.call_arguments_type.model_json_schema()
        if self.rules:
            parameters.setdefault("allOf", []).extend(
                rule.schema() for rule in self.rules
            )
        return {
            "name": self.name,
            "description": self.description,
            "parameters": parameters,
            "returns": self.result_type.model_json_schema(),
            "domain": list(self.domain),
            "units": [
                {
                    "field": unit.field,
                    "source": unit.source,
                    "unit": unit.unit.model_dump(mode="json"),
                }
                for unit in self.units
            ],
            "failure_statuses": list(get_args(ToolFailureStatus)),
            "policy": {
                "execution": self.policy.execution,
                "external_calls": self.policy.external_calls,
                "confirmation": self.policy.confirmation,
                "public_receipt": self.policy.public_receipt,
                "editable_fields": list(self.policy.editable_fields),
                "retain_unknown": self.policy.retain_unknown,
            },
            "progress": {
                "locale_key": self.progress.locale_key,
                "argument_fields": list(self.progress.argument_fields),
            },
            "card": {"type": self.card.card_type, "version": self.card.version},
        }

    def progress_facts(self, arguments: BaseModel, *, call_id: str) -> ToolProgress:
        values = self.validate_arguments(arguments).model_dump(mode="json")
        return ToolProgress(
            locale_key=self.progress.locale_key,
            interpolation_args={
                path.rsplit(".", 1)[-1]: _progress_value(values, path)
                for path in self.progress.argument_fields
            },
            call_id=call_id,
            tool_name=self.name,
        )

    async def invoke(
        self, arguments: Mapping[str, Any] | BaseModel, *, context: Any = None
    ) -> ToolOutcome:
        validated, rejected = self._validated_or_rejected(arguments)
        if rejected is not None:
            return rejected
        try:
            result = self.handler(
                validated, **({"context": context} if self._uses_context else {})
            )
            if inspect.isawaitable(result):
                result = await result
            return self._succeeded(result)
        except ToolInvocationError as exc:
            return exc.outcome
        except Exception:  # noqa: BLE001
            return self._execution_failed()

    def invoke_sync(self, arguments: Mapping[str, Any] | BaseModel) -> ToolOutcome:
        """The same contract for a synchronous local callable; a re-run needs no loop."""
        validated, rejected = self._validated_or_rejected(arguments)
        if rejected is not None:
            return rejected
        try:
            if self._uses_context:
                raise TypeError("A synchronous re-run has no trusted context")
            result = self.handler(validated)
            if inspect.isawaitable(result):
                result.close()
                raise TypeError("A synchronous re-run cannot await a coroutine")
            return self._succeeded(result)
        except ToolInvocationError as exc:
            return exc.outcome
        except Exception:  # noqa: BLE001
            return self._execution_failed()

    def _validated_or_rejected(
        self, arguments: Mapping[str, Any] | BaseModel
    ) -> tuple[BaseModel | None, ToolOutcome | None]:
        try:
            return self.validate_arguments(arguments), None
        except ToolInvocationError as exc:
            return None, exc.outcome
        except (ValidationError, ValueError, TypeError):
            return None, ToolOutcome(
                status="invalid", failure=ToolFailure(code="invalid_arguments")
            )

    def _succeeded(self, result: Any) -> ToolOutcome:
        returned = _validate_return(self.result_type, result).model_dump(mode="json")
        return ToolOutcome(status="succeeded", result=returned)

    def _execution_failed(self) -> ToolOutcome:
        logger.warning("Tool execution failed its declared contract", tool_name=self.name)
        return ToolOutcome(
            status="unavailable", failure=ToolFailure(code="tool_execution_failed")
        )

    async def prepare_confirmation(
        self, arguments: Mapping[str, Any] | BaseModel, *, context: Any
    ) -> BaseModel:
        if self.confirmation_handler is None or self.confirmation_result_type is None:
            raise ValueError("This tool has no confirmation handler")
        validated = self.validate_arguments(arguments)
        result = self.confirmation_handler(validated, context=context)
        if inspect.isawaitable(result):
            result = await result
        return _validate_return(self.confirmation_result_type, result)

    def recompute_arguments(
        self, original: Mapping[str, Any] | BaseModel, changes: Mapping[str, Any]
    ) -> BaseModel:
        if self.policy.execution != "local" or self.policy.confirmation != "never":
            raise ValueError("This tool does not permit instant recompute")
        previous = self.validate_arguments(original).model_dump(mode="python")
        if not set(changes) <= set(self.policy.editable_fields):
            raise ValueError("An argument is not editable")
        revised = {**previous, **changes}
        if self.policy.retain_unknown:
            for rule in self.rules:
                before = {name for name in rule.fields if previous[name] is None}
                after = {name for name in rule.fields if revised[name] is None}
                if before != after:
                    raise ValueError("Recompute must retain the selected unknown")
        if TOOL_INPUT_SOURCES_FIELD in self.arguments_type.model_fields:
            revised[TOOL_INPUT_SOURCES_FIELD] = {
                **dict(previous.get(TOOL_INPUT_SOURCES_FIELD) or {}),
                **{name: {"kind": "user"} for name in changes},
            }
        return self.validate_arguments(revised)

    def result_card(
        self,
        *,
        call: ToolCall,
        outcome: ToolOutcome,
        artifact_id: str,
        input_revision: int = 0,
    ) -> ToolResultCard:
        if call.tool_name != self.name:
            raise ValueError("A result card must bind the declaration that executed")
        if outcome.status == "succeeded":
            returned = _validate_return(self.result_type, outcome.result)
            outcome = outcome.model_copy(
                update={"result": returned.model_dump(mode="json")}
            )
        try:
            # A rule failure keeps the typed model, so its inputs stay typeable.
            arguments = self._validated_model(call.arguments)
            if outcome.status == "succeeded":
                self.validate_arguments(arguments)
        except (ValueError, TypeError, ValidationError):
            if outcome.status == "succeeded":
                raise
            presentation = ToolCardPresentation(
                title=LocalizedText(locale_key="chat.tools.failed")
            )
            original = call.arguments
        else:
            original = arguments.model_dump(mode="json")
            if TOOL_INPUT_SOURCES_FIELD in self.arguments_type.model_fields:
                original = _with_default_sources(original, call.arguments)
            presentation = ToolCardPresentation.model_validate(
                self.card.presenter(arguments, outcome)
            )
            # Editability, unknown identity, units and provenance derive from the
            # declaration, never from a second policy hand-maintained per presenter.
            input_units = {
                unit.field: unit.unit for unit in self.units if unit.source == "argument"
            }
            result_units = {
                unit.field: unit.unit for unit in self.units if unit.source == "result"
            }
            input_sources = _input_sources(original)
            driving = [
                name
                for name in self.policy.driving_fields
                if original.get(name) is not None
            ][:MAX_DRIVING_INPUTS]
            presentation = presentation.model_copy(
                update={
                    "answer": _computed(_with_unit(presentation.answer, result_units))
                    if presentation.answer is not None
                    else None,
                    "rows": [
                        _computed(_with_unit(fact, result_units))
                        for fact in presentation.rows
                    ],
                    "inputs": [
                        ToolInputFact.model_validate(
                            {
                                **fact.model_dump(mode="python"),
                                "value": original[fact.name],
                                "unknown": any(
                                    fact.name in rule.fields for rule in self.rules
                                )
                                and original[fact.name] is None,
                                "editable": fact.name in self.policy.editable_fields
                                and original[fact.name] is not None,
                                "driving": fact.name in driving,
                                "unit": input_units.get(fact.name, fact.unit),
                                "source": ToolFactSource(kind="computed")
                                if any(fact.name in rule.fields for rule in self.rules)
                                and original[fact.name] is None
                                else fact.source
                                or input_sources.get(fact.name)
                                or ToolFactSource(kind="user"),
                            }
                        )
                        for fact in presentation.inputs
                    ],
                }
            )
        return ToolResultCard(
            tool_name=self.name,
            call_id=call.call_id,
            artifact_id=artifact_id,
            input_revision=input_revision,
            card_type=self.card.card_type,
            card_version=self.card.version,
            arguments=original,
            outcome=outcome,
            presentation=presentation,
        )


def _validate_return(model: type[BaseModel], result: Any) -> BaseModel:
    # Revalidate instances too: model_construct and mutable third-party models
    # cannot bypass this contract, including background completion and confirmation.
    raw = (
        result.model_dump(mode="python", warnings=False)
        if isinstance(result, BaseModel)
        else result
    )
    returned = model.model_validate(raw)
    _require_finite_json(returned.model_dump(mode="json"))
    return returned


def _with_unit(fact: ToolFact, units: Mapping[str, LocalizedText]) -> ToolFact:
    return fact.model_copy(update={"unit": units.get(fact.name, fact.unit)})


def _computed(fact: ToolFact) -> ToolFact:
    if fact.source is not None:
        return fact
    return fact.model_copy(update={"source": ToolFactSource(kind="computed")})


def _input_sources(arguments: Mapping[str, Any]) -> dict[str, ToolFactSource]:
    raw = arguments.get(TOOL_INPUT_SOURCES_FIELD)
    if not isinstance(raw, Mapping):
        return {}
    sources: dict[str, ToolFactSource] = {}
    for name, value in raw.items():
        try:
            sources[str(name)] = ToolFactSource.model_validate(value)
        except ValidationError:
            continue
    return sources


def _with_default_sources(
    arguments: dict[str, Any], stated: Mapping[str, Any]
) -> dict[str, Any]:
    """The arguments with every input the call left to its default recorded as an
    assumption, so a default never reads as a figure the reader stated."""
    sources = dict(arguments.get(TOOL_INPUT_SOURCES_FIELD) or {})
    for name, value in arguments.items():
        if (
            name != TOOL_INPUT_SOURCES_FIELD
            and name not in stated
            and name not in sources
            and value is not None
        ):
            sources[name] = ToolFactSource(kind="assumption").model_dump(mode="json")
    return {**arguments, TOOL_INPUT_SOURCES_FIELD: sources}


def _require_finite_json(value: Any) -> None:
    # JSON's allow_nan extension is not a financial answer or typed argument.
    json.dumps(value, allow_nan=False)


def _validate_argument_path(model: type[BaseModel], path: str) -> None:
    parts = path.split(".")
    for index, name in enumerate(parts):
        if name not in model.model_fields:
            raise ValueError("Progress references an unknown typed argument field")
        annotation = model.model_fields[name].annotation
        if index == len(parts) - 1:
            if not _progress_annotation(annotation):
                raise ValueError(
                    "Progress leaves must be scalar values or lists of strings"
                )
            return
        members = (
            get_args(annotation)
            if get_origin(annotation) in {Union, UnionType}
            else (annotation,)
        )
        candidates = [candidate for candidate in members if candidate is not type(None)]
        nested = [
            candidate
            for candidate in candidates
            if inspect.isclass(candidate) and issubclass(candidate, BaseModel)
        ]
        if len(nested) != 1 or len(candidates) != 1:
            raise ValueError("Progress paths traverse typed model fields only")
        model = nested[0]


def _progress_annotation(annotation: Any) -> bool:
    origin = get_origin(annotation)
    if origin is Annotated:
        return _progress_annotation(get_args(annotation)[0])
    if origin in {Union, UnionType}:
        return all(_progress_annotation(member) for member in get_args(annotation))
    if origin is Literal:
        return all(
            value is None or isinstance(value, (bool, int, float, str))
            for value in get_args(annotation)
        )
    if origin is list:
        return get_args(annotation) == (str,)
    return annotation is type(None) or (
        inspect.isclass(annotation) and issubclass(annotation, (bool, int, float, str))
    )


def _progress_value(values: dict[str, Any], path: str) -> Any:
    value: Any = values
    for name in path.split("."):
        value = value[name] if value is not None else None
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return ", ".join(value)
    return value


@dataclass(frozen=True)
class ToolCatalog:
    declarations: tuple[ToolDeclaration, ...]
    _by_name: Mapping[str, ToolDeclaration] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        declarations = tuple(self.declarations)
        by_name = {declaration.name: declaration for declaration in declarations}
        if len(by_name) != len(declarations):
            raise ValueError("A catalog cannot contain duplicate tool identities")
        object.__setattr__(self, "declarations", declarations)
        object.__setattr__(self, "_by_name", MappingProxyType(by_name))

    def get(self, name: str) -> ToolDeclaration | None:
        return self._by_name.get(name)

    def capability_text(self) -> str:
        return json.dumps(
            [declaration.tool_schema() for declaration in self.declarations],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
