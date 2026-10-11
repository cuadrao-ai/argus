"""Every piece of text this repo sends to an interpretation model.

Two channels reach the model: the instruction text in prompt builders, and the
schema field descriptions it fills in. Both steer interpretation for every turn,
so both are frozen together by `test_interpreter_prompt_freeze.py`.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

MEASURED_ROOTS = (
    "src/argus/agent_runtime",
    "src/argus/domain",
    "src/argus/llm",
    "src/argus/context",
    "src/argus/nlp",
)

FINGERPRINT_PATH = Path(".agent/interpreter_prompt_fingerprint.json")
BUSINESS_DECLARATION_OWNER = "src/argus/domain/business/tools/declarations.py"
# These composers send dictionary messages rather than LangChain messages.
# Keep the API addition narrow: unrelated router prose is not this lane's scope.
READOUT_MESSAGE_OWNERS = frozenset(
    {
        "src/argus/agent_runtime/stages/explain.py",
        "src/argus/api/chat/breakdown.py",
    }
)
READOUT_INSTRUCTION_OWNERS = frozenset(
    {
        "src/argus/domain/result_readout_grounding.py",
        "src/argus/domain/result_readout_sources.py",
    }
)
READOUT_FACT_SHEET_OWNERS = frozenset(
    {
        "src/argus/domain/result_readout_fact_sheet.py",
        "src/argus/domain/result_readout_fact_definitions.py",
    }
)

_MESSAGE_CONSTRUCTORS = frozenset({"SystemMessage", "HumanMessage", "AIMessage"})
_PROMPT_FUNCTION_SUFFIXES = ("_prompt", "_instructions", "_directive", "_clause")
# String constants like DISCOVERY_ACT_GUIDANCE are concatenated into the
# interpreter's system prompt by name, so the prompt builder's own hash does
# not move when they change; they are hashed at their definition instead.
_GUIDANCE_CONSTANT_SUFFIX = "_GUIDANCE"


def _callee_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _joined_constants(node: ast.AST) -> str:
    """Concatenate every string constant under a node, in source order."""

    parts = [
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    ]
    return "".join(parts)


def _business_declaration_descriptions(node: ast.FunctionDef) -> list[tuple[str, str]]:
    found = []
    for expression in ast.walk(node):
        if not isinstance(expression, ast.GeneratorExp):
            continue
        call = expression.elt
        if not isinstance(call, ast.Call) or _callee_name(call) != "ToolDeclaration":
            continue
        description = next(
            (keyword.value for keyword in call.keywords if keyword.arg == "description"),
            None,
        )
        if not isinstance(description, ast.Name):
            continue
        for generator in expression.generators:
            if not isinstance(generator.target, ast.Tuple) or not isinstance(
                generator.iter, (ast.Tuple, ast.List)
            ):
                continue
            for index, target in enumerate(generator.target.elts):
                if not isinstance(target, ast.Name) or target.id != description.id:
                    continue
                for row in generator.iter.elts:
                    if not isinstance(row, ast.Tuple) or index >= len(row.elts):
                        continue
                    value = row.elts[index]
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        found.append(("ToolDeclaration.description", value.value))
    return found


def _model_facing_strings(
    tree: ast.AST,
    *,
    include_dictionary_messages: bool = False,
    include_readout_instructions: bool = False,
    include_fact_sheet_text: bool = False,
    include_business_declarations: bool = False,
) -> list[tuple[str, str]]:
    """(kind, text) for every string this module hands to a model."""

    found: list[tuple[str, str]] = []

    if include_fact_sheet_text:
        # Labels, meanings, units and derivation caveats are model input too.
        # Keep coverage local to the pure sheet owner; implementation docstrings
        # never reach the composer and should not force another measurement.
        docstrings = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(
                node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            )
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        }
        return [
            ("readout_fact_text", node.value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ]

    for node in ast.walk(tree):
        if include_dictionary_messages and isinstance(node, ast.Dict):
            fields = {
                key.value: value
                for key, value in zip(node.keys, node.values, strict=False)
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            role = fields.get("role")
            content = fields.get("content")
            if (
                isinstance(role, ast.Constant)
                and role.value in {"system", "user", "assistant"}
                and content is not None
            ):
                text = _joined_constants(content)
                if text:
                    found.append((f"dict.{role.value}.content", text))
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if (
                include_business_declarations
                and isinstance(node, ast.FunctionDef)
                and node.name == "get_business_declarations"
            ):
                found.extend(_business_declaration_descriptions(node))
            if node.name.endswith(_PROMPT_FUNCTION_SUFFIXES):
                body = _joined_constants(node)
                if body:
                    found.append((f"def {node.name}", body))
            continue

        if isinstance(node, ast.Assign):
            target_names = [
                target.id for target in node.targets if isinstance(target, ast.Name)
            ]
            if (
                include_readout_instructions
                and len(target_names) == 1
                and target_names[0].endswith("_INSTRUCTIONS")
            ):
                # Shared and surface-specific fragments are each measured at
                # their definition, including literals concatenated to a name.
                text = _joined_constants(node.value)
                if text:
                    found.append((target_names[0], text))
                continue
            if (
                len(target_names) == 1
                and target_names[0].endswith(_GUIDANCE_CONSTANT_SUFFIX)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
                and node.value.value
            ):
                found.append((target_names[0], node.value.value))
            continue

        if not isinstance(node, ast.Call):
            continue

        callee = _callee_name(node)

        if callee in _MESSAGE_CONSTRUCTORS:
            text = _joined_constants(node)
            if text:
                found.append((callee, text))
            continue

        if callee == "Field":
            for keyword in node.keywords:
                if keyword.arg != "description":
                    continue
                text = _joined_constants(keyword.value)
                if text:
                    found.append(("Field.description", text))

    return found


def model_facing_surface(repository_root: Path) -> dict[str, dict[str, object]]:
    """Per-file digest of everything the interpretation model reads."""

    surface: dict[str, dict[str, object]] = {}

    paths = {
        path for root in MEASURED_ROOTS for path in (repository_root / root).rglob("*.py")
    }
    paths.update(repository_root / name for name in READOUT_MESSAGE_OWNERS)
    for path in sorted(paths):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue

        relative = str(path.relative_to(repository_root))
        strings = _model_facing_strings(
            tree,
            include_dictionary_messages=relative in READOUT_MESSAGE_OWNERS,
            include_readout_instructions=relative in READOUT_INSTRUCTION_OWNERS,
            include_fact_sheet_text=relative in READOUT_FACT_SHEET_OWNERS,
            include_business_declarations=relative == BUSINESS_DECLARATION_OWNER,
        )
        if not strings:
            continue

        payload = chr(10).join(kind + chr(31) + text for kind, text in strings)
        surface[relative] = {
            "entries": len(strings),
            "chars": sum(len(text) for _, text in strings),
            "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        }

    return surface


def load_fingerprint(repository_root: Path) -> dict[str, object]:
    return json.loads((repository_root / FINGERPRINT_PATH).read_text(encoding="utf-8"))


def surface_drift(
    recorded: dict[str, dict[str, object]],
    observed: dict[str, dict[str, object]],
) -> tuple[list[str], list[str], list[str]]:
    """(changed, added, removed) files, comparing digests only."""

    changed = sorted(
        name
        for name in recorded.keys() & observed.keys()
        if recorded[name]["sha256"] != observed[name]["sha256"]
    )
    return (
        changed,
        sorted(observed.keys() - recorded.keys()),
        sorted(recorded.keys() - observed.keys()),
    )
