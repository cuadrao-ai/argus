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
DOCUMENT_EXTRACTOR_OWNER = "src/argus/domain/ingestion/documents/extractor.py"
DOCUMENT_EXTRACTION_OWNERS = frozenset(
    {DOCUMENT_EXTRACTOR_OWNER, "src/argus/domain/ingestion/documents/models.py"}
)
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


def _model_facing_strings(
    tree: ast.AST,
    *,
    include_dictionary_messages: bool = False,
    include_readout_instructions: bool = False,
    include_fact_sheet_text: bool = False,
    include_document_instructions: bool = False,
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
            if node.name.endswith(_PROMPT_FUNCTION_SUFFIXES):
                body = _joined_constants(node)
                if body:
                    found.append((f"def {node.name}", body))
            continue

        if isinstance(node, ast.Assign):
            target_names = [
                target.id for target in node.targets if isinstance(target, ast.Name)
            ]
            if include_document_instructions and target_names == ["_PROMPT"]:
                text = _joined_constants(node.value)
                if text:
                    found.append(("_PROMPT", text))
                continue
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
            include_document_instructions=relative == DOCUMENT_EXTRACTOR_OWNER,
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


def _document_scope(fingerprint: dict) -> dict:
    scopes = fingerprint.get("scoped_measurements")
    assert isinstance(scopes, dict) and set(scopes) == {"document_extraction"}
    scope = scopes["document_extraction"]
    assert isinstance(scope, dict)
    owners = scope.get("owners")
    assert isinstance(owners, list) and len(owners) == 2
    assert set(owners) == DOCUMENT_EXTRACTION_OWNERS
    surface = scope.get("surface")
    assert isinstance(surface, dict)
    if scope.get("status") == "UNMEASURED":
        assert surface == {} and scope.get("last_measured") is None
    else:
        assert scope.get("status") == "MEASURED"
        assert set(surface) == DOCUMENT_EXTRACTION_OWNERS
        assert isinstance(scope.get("last_measured"), dict)
    return scope


def fingerprint_surface(fingerprint: dict) -> dict[str, dict[str, object]]:
    legacy = fingerprint.get("surface")
    assert isinstance(legacy, dict)
    scope = _document_scope(fingerprint)
    assert not (set(legacy) & DOCUMENT_EXTRACTION_OWNERS)
    return legacy | scope["surface"]


def validate_document_extraction_measurement(scope: dict, scorecard: dict) -> None:
    _document_scope({"scoped_measurements": {"document_extraction": scope}})
    assert scope.get("status") == "MEASURED", "Document extraction is UNMEASURED"
    surface = scope.get("surface")
    assert isinstance(surface, dict) and set(surface) == DOCUMENT_EXTRACTION_OWNERS
    measured = scope.get("last_measured")
    assert isinstance(measured, dict), "Document extraction has no live measurement"
    assert isinstance(scorecard, dict)
    assert scorecard.get("scope") == "document_extraction"
    assert scorecard.get("status") == "passed"
    assert scorecard.get("surface") == surface
    for owner in DOCUMENT_EXTRACTION_OWNERS:
        entry = surface[owner]
        assert isinstance(entry, dict)
        for key in ("entries", "chars"):
            value = entry.get(key)
            assert isinstance(value, int) and not isinstance(value, bool) and value > 0
        digest = entry.get("sha256")
        assert isinstance(digest, str) and len(digest) == 64
        assert all(char in "0123456789abcdef" for char in digest)
    for recorded, actual in (("commit", "candidate_sha"), ("model", "model")):
        value = measured.get(recorded)
        assert isinstance(value, str) and value
        assert scorecard.get(actual) == value
    totals = scorecard.get("totals")
    assert isinstance(totals, dict)
    for key in ("passed", "failed", "unavailable"):
        assert isinstance(totals.get(key), int) and not isinstance(totals[key], bool)
    assert totals["passed"] > 0
    assert totals["failed"] == totals["unavailable"] == 0


def require_document_extraction_measurement(
    repository_root: Path, fingerprint: dict
) -> None:
    fingerprint_surface(fingerprint)
    scope = _document_scope(fingerprint)
    measured = scope.get("last_measured")
    assert isinstance(
        measured, dict
    ), "Document extraction live measurement is UNMEASURED"
    scorecard = measured.get("scorecard")
    assert isinstance(scorecard, str) and scorecard
    path = (repository_root / scorecard).resolve()
    evidence_root = (repository_root / "docs/reports/evidence").resolve()
    assert path.is_relative_to(evidence_root)
    assert (
        path.is_file()
    ), "Document extraction scorecard must travel with its fingerprint"
    validate_document_extraction_measurement(scope, json.loads(path.read_text()))


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
