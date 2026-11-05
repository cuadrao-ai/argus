"""AST tripwire: private artifact prose may not acquire a new reader."""

import ast
from collections import Counter
from pathlib import Path

import pytest
from argus.api.artifact_presentation import (
    ARTIFACT_ROOT_PROSE_FIELDS,
    PRIVATE_ARTIFACT_PROSE_FIELDS,
)

ROOT = Path(__file__).resolve().parents[2]


def prose_reads(source: str, fields: frozenset[str]) -> list[tuple[str, str, str]]:
    readers: list[tuple[str, str, str]] = []

    class Visitor(ast.NodeVisitor):
        owner = "<module>"

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            previous = self.owner
            self.owner = node.name
            self.generic_visit(node)
            self.owner = previous

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Attribute(self, node: ast.Attribute) -> None:
            if isinstance(node.ctx, ast.Load) and node.attr in fields:
                readers.append((self.owner, node.attr, ast.unparse(node)))
            self.generic_visit(node)

        def visit_Subscript(self, node: ast.Subscript) -> None:
            if (
                isinstance(node.ctx, ast.Load)
                and isinstance(node.slice, ast.Constant)
                and node.slice.value in fields
            ):
                readers.append((self.owner, node.slice.value, ast.unparse(node)))
            self.generic_visit(node)

        def visit_Call(self, node: ast.Call) -> None:
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in {"get", "pop", "setdefault"}
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value in fields
            ):
                readers.append((self.owner, node.args[0].value, ast.unparse(node)))
            self.generic_visit(node)

    Visitor().visit(ast.parse(source))
    return readers


def private_reads(source: str) -> list[tuple[str, str]]:
    return [
        (owner, field)
        for owner, field, _ in prose_reads(source, PRIVATE_ARTIFACT_PROSE_FIELDS)
    ]


def root_prose_reader_paths() -> list[Path]:
    # These own artifact reads, not unrelated request/composer text. Glob new
    # artifact modules too; an existing generic transcript read is never a
    # module-wide waiver for a new artifact fallback.
    return sorted(
        {
            *ROOT.glob("src/argus/api/artifact_*.py"),
            *ROOT.glob("src/argus/domain/artifact_*.py"),
            *(
                ROOT / name
                for name in (
                    "src/argus/api/routers/conversations.py",
                    "src/argus/api/routers/history.py",
                    "src/argus/api/routers/search.py",
                    "src/argus/api/conversation_previews.py",
                    "src/argus/domain/conversation_previews.py",
                    "src/argus/domain/run_dossiers.py",
                )
            ),
        }
    )


def root_reader_inventory(overrides: dict[Path, str] | None = None) -> Counter:
    return Counter(
        (path.relative_to(ROOT).as_posix(), owner, expression)
        for path in root_prose_reader_paths()
        for owner, _, expression in prose_reads(
            (overrides or {}).get(path, path.read_text()), ARTIFACT_ROOT_PROSE_FIELDS
        )
    )


def test_root_prose_has_only_exact_generic_transcript_readers() -> None:
    assert root_reader_inventory() == Counter(
        {
            # Naming is private model context. Marker filters read only user text.
            (
                "src/argus/api/artifact_naming.py",
                "_conversation_title_context_from_messages",
                "message.content",
            ): 1,
            (
                "src/argus/api/conversation_previews.py",
                "latest_conversation_messages",
                "message.content",
            ): 1,
            # One user-marker read and one input to the sole scrubber, whose output
            # is then unwrapped. Neither is a public artifact fallback.
            (
                "src/argus/api/routers/conversations.py",
                "_public_message_projection",
                "message.content",
            ): 2,
            (
                "src/argus/api/routers/conversations.py",
                "_public_message_projection",
                "public.pop('content')",
            ): 1,
            # Reached only after typed artifacts/degraded compatibility return.
            (
                "src/argus/domain/conversation_previews.py",
                "project_conversation_preview",
                "message.get('content')",
            ): 1,
        }
    )


@pytest.mark.parametrize("field", sorted(ARTIFACT_ROOT_PROSE_FIELDS))
def test_root_prose_fallback_mutation_is_detected_in_real_reader(field: str) -> None:
    path = ROOT / "src/argus/domain/run_dossiers.py"
    mutated = (
        path.read_text()
        + f"\ndef leaked_template(message):\n    return message.get('{field}') or ''\n"
    )
    assert root_reader_inventory({path: mutated}) != root_reader_inventory()


def test_single_reader_boundary_blanks_the_shared_root_registry() -> None:
    tree = ast.parse((ROOT / "src/argus/api/artifact_presentation.py").read_text())
    boundary = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "reader_payload"
    )
    loops = [
        node
        for node in ast.walk(boundary)
        if isinstance(node, ast.For)
        and ast.unparse(node.iter) == "ARTIFACT_ROOT_PROSE_FIELDS"
    ]
    assert len(loops) == 1
    assert any(
        isinstance(node, ast.Assign)
        and [ast.unparse(target) for target in node.targets] == ["public[field]"]
        and isinstance(node.value, ast.Constant)
        and node.value.value == ""
        for node in ast.walk(loops[0])
    )


def test_runtime_source_prose_aliases_must_belong_to_the_scrub_registry() -> None:
    tree = ast.parse((ROOT / "src/argus/api/chat/streaming.py").read_text())
    extractor = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "runtime_result_message"
    )
    aliases = {
        node.args[0].value
        for node in ast.walk(extractor)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and node.args
        and isinstance(node.args[0], ast.Constant)
    }
    assert aliases <= ARTIFACT_ROOT_PROSE_FIELDS


@pytest.mark.parametrize(
    "expression",
    [
        "row.quick_take",
        "row['breakdown']",
        "row.get('result_readout')",
        "row.get('audit_context') or row.get('quick_take')",
    ],
)
def test_new_template_and_compatibility_fallback_reads_are_rejected(
    expression: str,
) -> None:
    assert private_reads(f"def new_template(row):\n    return {expression}")


def test_private_prose_has_only_explicit_storage_and_model_context_readers() -> None:
    # Private storage/index/model owners, not presentation templates. Job
    # compatibility is null at serialization; message projection is scrubbed at
    # the public reader. Pin occurrences too: ownership is not a blanket waiver.
    allowed = Counter(
        {
            (
                "src/argus/domain/backtest_message_projection.py",
                "_result_readout",
                "result_readout",
            ): 1,
            ("src/argus/domain/evidence.py", "evidence_digest_from_run", "quick_take"): 1,
            (
                "src/argus/domain/evidence.py",
                "evidence_preview_from_payload",
                "quick_take",
            ): 2,
            (
                "src/argus/domain/evidence.py",
                "evidence_preview_from_payload",
                "breakdown",
            ): 2,
            ("src/argus/domain/evidence.py", "_payload_from_run", "quick_take"): 1,
            ("src/argus/domain/evidence.py", "_payload_from_run", "breakdown"): 1,
        }
    )
    observed: Counter[tuple[str, str, str]] = Counter()
    for path in sorted((ROOT / "src" / "argus").rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        for owner, field in private_reads(path.read_text()):
            observed[(relative, owner, field)] += 1
    assert observed == allowed
