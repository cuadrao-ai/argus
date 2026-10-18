"""No writer may attach a result or advance a job's lifecycle ungated.

Three review rounds each found a new writer bypassing the consumption
guard's one statement: the mark_succeeded-only link guard, the
unconditional publisher, and the proof task's raw status write. This
suite enumerates, by construction, every site in ``src/`` and
``workflows/`` that writes ``public.backtest_jobs``, every migration
that writes it, and every caller of the link write, and asserts each one
is gated by (or provably inside) the lifecycle statement in
``argus.domain.backtest_job_lifecycle``. A future writer or caller that
is not classified here fails the suite instead of shipping a hole: the
fix is to route the write through a gated site, or to add it here WITH
its gate assertion, never to widen a gate.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCAN_ROOTS = ("src", "workflows")
WRITE_VERBS = {"update", "insert", "upsert", "delete"}


def _python_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        files.extend(sorted((REPO / root).rglob("*.py")))
    return files


class _FunctionIndex(ast.NodeVisitor):
    """Maps every statement to its enclosing qualified function name."""

    def __init__(self) -> None:
        self.spans: list[tuple[int, int, str]] = []
        self._stack: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._stack.append(node.name)
        self.generic_visit(node)
        self._stack.pop()

    def _visit_function(self, node: ast.AST) -> None:
        self._stack.append(node.name)  # type: ignore[attr-defined]
        self.spans.append(
            (node.lineno, node.end_lineno or node.lineno, ".".join(self._stack))
        )
        self.generic_visit(node)
        self._stack.pop()

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function

    def function_at(self, lineno: int) -> str:
        best = "<module>"
        best_size = None
        for start, end, name in self.spans:
            if start <= lineno <= end:
                size = end - start
                if best_size is None or size < best_size:
                    best, best_size = name, size
        return best


def _chain_facts(call: ast.Call) -> tuple[set[str], set[str]]:
    """Attribute names and table() string arguments along a builder chain."""
    attrs: set[str] = set()
    tables: set[str] = set()
    node: ast.AST = call
    while True:
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                attrs.add(func.attr)
                if func.attr == "table":
                    for arg in node.args:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            tables.add(arg.value)
                node = func.value
                continue
            break
        if isinstance(node, ast.Attribute):
            attrs.add(node.attr)
            node = node.value
            continue
        break
    return attrs, tables


def _module_sites(path: Path) -> list[tuple[str, str, str]]:
    source = path.read_text()
    tree = ast.parse(source)
    index = _FunctionIndex()
    index.visit(tree)
    rel = str(path.relative_to(REPO))
    sites: list[tuple[str, str, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            attrs, tables = _chain_facts(node)
            if "backtest_jobs" in tables:
                verbs = attrs & WRITE_VERBS
                if verbs:
                    sites.append(
                        (rel, index.function_at(node.lineno), "postgrest-" + min(verbs))
                    )

    for offset, line in enumerate(source.splitlines(), start=1):
        if "update public.backtest_jobs" in line:
            sites.append((rel, index.function_at(offset), "sql-update"))
        if "insert into public.backtest_jobs" in line:
            sites.append((rel, index.function_at(offset), "sql-insert"))
    return sorted(set(sites))


def _function_source(path: Path, function: str) -> str:
    source = (REPO / path).read_text()
    tree = ast.parse(source)
    index = _FunctionIndex()
    index.visit(tree)
    for start, end, name in index.spans:
        if name == function:
            return "\n".join(source.splitlines()[start - 1 : end])
    raise AssertionError(f"{function} not found in {path}")


def _requires(*needles: str, absent: tuple[str, ...] = ()):
    def check(function_source: str) -> None:
        for needle in needles:
            assert needle in function_source, f"gate marker missing: {needle!r}"
        for needle in absent:
            assert needle not in function_source, f"forbidden marker: {needle!r}"

    return check


# Every known writer of public.backtest_jobs, each with the assertion
# that proves its gate. Ordering: admission inserts, metadata merges,
# lifecycle transitions, result links.
EXPECTED_WRITE_SITES = {
    (
        "src/argus/domain/backtest_admission_gateway.py",
        "record_backtest_job_rejection",
        "postgrest-insert",
    ): _requires(
        '"status": "failed"',
        '"idempotency_key": receipt_key',
        '"rejected_idempotency_key": rejected_idempotency_key',
        '"finished_at": finished_at',
        absent=('"result_run_id":', '"started_at":'),
    ),
    (
        "src/argus/domain/supabase_gateway.py",
        "SupabaseGateway.create_backtest_job",
        "postgrest-insert",
    ): _requires(absent=("result_run_id",)),
    (
        "src/argus/domain/supabase_gateway.py",
        "SupabaseGateway.merge_backtest_job_execution_metadata",
        "postgrest-update",
    ): _requires('{"execution_metadata": metadata, "updated_at": _now_iso()}'),
    (
        "src/argus/domain/supabase_gateway.py",
        "SupabaseGateway.link_backtest_job_result",
        "postgrest-update",
    ): _requires(
        "job_result_attach_postgrest_filter",
        "job_success_write_postgrest_filter",
    ),
    (
        "src/argus/domain/supabase_gateway.py",
        "SupabaseGateway.mark_backtest_job_running",
        "postgrest-update",
    ): _requires('"result_run_id": None', '.eq("status", existing_status)'),
    (
        "src/argus/domain/supabase_gateway.py",
        "SupabaseGateway.mark_backtest_job_failed",
        "postgrest-update",
    ): _requires('"result_run_id": None'),
    (
        "src/argus/domain/supabase_gateway.py",
        "SupabaseGateway.complete_research_job",
        "postgrest-update",
    ): _requires(
        '.eq("operation_scope", RESEARCH_OPERATION_SCOPE)',
        '.in_("status", ["queued", "running"])',
        absent=('"result_run_id":',),
    ),
    (
        "src/argus/domain/backtest_admission_gateway.py",
        "finalize_direct_backtest_job",
        "postgrest-update",
    ): _requires('.eq("status", "running")'),
    (
        "workflows/backtest_job.py",
        "PostgresBacktestJobGateway._try_mark_backtest_job_running",
        "sql-update",
    ): _requires("for update", "_workflow_start_candidate", "result_run_id = null"),
    (
        "workflows/backtest_job.py",
        "PostgresBacktestJobGateway.merge_backtest_job_execution_metadata",
        "sql-update",
    ): _requires("set execution_metadata", absent=("result_run_id", "status =")),
    (
        "workflows/backtest_job.py",
        "PostgresBacktestJobGateway.link_backtest_job_result",
        "sql-update",
    ): _requires(
        "{job_result_attach_sql_predicate()}",
        "{job_success_write_sql_predicate()}",
    ),
    (
        "workflows/backtest_job.py",
        "PostgresBacktestJobGateway.mark_backtest_job_failed",
        "sql-update",
    ): _requires("result_run_id = null"),
    (
        "workflows/proof.py",
        "PostgresProofJobGateway.update_job_status",
        "sql-update",
    ): _requires("{job_success_write_sql_predicate()}"),
    (
        "workflows/proof.py",
        "PostgresProofJobGateway.create_proof_job",
        "sql-insert",
    ): _requires("'queued'", absent=("result_run_id",)),
}


def test_every_backtest_jobs_write_site_is_classified_and_gated() -> None:
    found: dict[tuple[str, str, str], None] = {}
    for path in _python_files():
        for rel, function, kind in _module_sites(path):
            found[(rel, function, kind)] = None

    unexpected = sorted(set(found) - set(EXPECTED_WRITE_SITES))
    missing = sorted(set(EXPECTED_WRITE_SITES) - set(found))
    assert not unexpected, (
        "New backtest_jobs write site(s) outside the lifecycle contract: "
        f"{unexpected}. Route the write through an existing gated writer, "
        "or classify it here together with the assertion that proves its "
        "gate derives from argus.domain.backtest_job_lifecycle."
    )
    assert not missing, (
        f"Known write site(s) disappeared: {missing}. If the writer moved "
        "or was renamed, update its classification here so the gate stays "
        "asserted."
    )

    for (rel, function, _kind), check in EXPECTED_WRITE_SITES.items():
        if function == "<module>":
            continue
        check(_function_source(Path(rel), function))


def test_link_write_callers_are_enumerated() -> None:
    """Callers inherit the gate from the implementations, which the write
    sites above pin; enumerating callers keeps a new call path a
    conscious, reviewed decision rather than a drive-by."""
    callers: set[tuple[str, str]] = set()
    for path in _python_files():
        source = path.read_text()
        if "link_backtest_job_result" not in source:
            continue
        tree = ast.parse(source)
        index = _FunctionIndex()
        index.visit(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "link_backtest_job_result"
            ):
                callers.add((str(path.relative_to(REPO)), index.function_at(node.lineno)))
    assert callers == {
        ("src/argus/api/chat/result_link.py", "link_shadow_backtest_job_result"),
        ("workflows/backtest_job.py", "run_backtest_job"),
    }, (
        f"Unrecognized link_backtest_job_result caller set: {sorted(callers)}. "
        "A new caller is gated by the implementation, but it must be "
        "enumerated here and its publisher must derive from the returned "
        "row, the way routers/agent.py derives from ResultLinkOutcome."
    )


MIGRATIONS = REPO / "supabase" / "migrations"


def _recreated_backtest_writers_are_contained(source: str) -> None:
    writers = {}
    for definition in source.split("CREATE OR REPLACE FUNCTION ")[1:]:
        if (
            "update public.backtest_jobs" in definition
            or "insert into public.backtest_jobs" in definition
        ):
            signature, body = definition.split("AS $function$", 1)
            writers[signature.split("(", 1)[0]] = body.split("$function$;", 1)[0]
    assert set(writers) == {
        "public.admit_backtest_job",
        "public.finalize_direct_backtest_success",
    }
    EXPECTED_MIGRATION_WRITERS["20260722000002_atomic_backtest_admission.sql"](
        writers["public.admit_backtest_job"]
    )
    EXPECTED_MIGRATION_WRITERS["20260722000004_serialize_direct_success.sql"](
        writers["public.finalize_direct_backtest_success"]
    )


# Migration files that write backtest_jobs, with the containment proof
# for each. Migrations are append-only, so a new writer shows up as an
# unclassified filename and fails the walk.
EXPECTED_MIGRATION_WRITERS = {
    "20260722000002_atomic_backtest_admission.sql": _requires(
        "failure_code = 'direct_execution_abandoned'",
        absent=("result_run_id =", "status = 'succeeded'"),
    ),
    "20260722000003_replay_legacy_reservations.sql": _requires(
        "failure_code = 'direct_execution_abandoned'",
        absent=("result_run_id =", "status = 'succeeded'"),
    ),
    "20260722000004_serialize_direct_success.sql": _requires(
        "for update",
        "v_job.status <> 'running'",
    ),
    "20260724102309_add_guest_session_allowances.sql": _requires(
        "failure_code = 'direct_execution_abandoned'",
        absent=("result_run_id =", "status = 'succeeded'"),
    ),
    "20260724211312_guest_workspace_handoffs.sql": _requires(
        "set user_id = p_destination_user_id",
        absent=("result_run_id =",),
    ),
    "20260726185021_harden_guest_lifecycle_ownership.sql": _requires(
        "set user_id = p_destination_user_id",
        absent=("result_run_id =",),
    ),
    # Reclassifies the seeder's proof rows out of every conversation; it
    # touches scope and conversation only, never status or the result link.
    "20260905000000_workflow_proof_jobs_leave_conversations.sql": _requires(
        "set operation_scope = 'workflows.proof'",
        "conversation_id = null",
        "where launch_payload ->> 'created_by' = 'workflows.proof_cli'",
        absent=("result_run_id =", "status ="),
    ),
    "20261018040000_harden_definer_search_paths.sql": _recreated_backtest_writers_are_contained,
}


def test_every_migration_writer_is_classified_and_contained() -> None:
    writers: dict[str, str] = {}
    for path in sorted(MIGRATIONS.glob("*.sql")):
        text = path.read_text()
        if (
            "update public.backtest_jobs" in text
            or "insert into public.backtest_jobs" in text
        ):
            writers[path.name] = text

    unexpected = sorted(set(writers) - set(EXPECTED_MIGRATION_WRITERS))
    missing = sorted(set(EXPECTED_MIGRATION_WRITERS) - set(writers))
    assert not unexpected, (
        f"New migration(s) write backtest_jobs: {unexpected}. Classify each "
        "here with the assertion that proves it cannot attach a result or "
        "revive a dead job outside the lifecycle statement."
    )
    assert not missing, f"Expected migration writer(s) missing: {missing}"

    for name, check in EXPECTED_MIGRATION_WRITERS.items():
        check(writers[name])
