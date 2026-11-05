"""The one owner of "this job's result is readable in its conversation".

A succeeded ``backtest_jobs`` row settles its conversation only once its
result can be hydrated. That rule is stated here, once, as an expression over
named facts. Both persistence layers derive from it:

- the memory store evaluates :data:`JOB_RESULT_HYDRATEABLE` over facts it
  gathers (``argus.api.conversation_activity``);
- the SQL function ``argus_private.backtest_job_result_hydrateable`` is
  rendered from the same expression by :func:`render_sql_function`, and the
  migration test asserts the checked-in function is exactly that rendering.

Each layer still owns how it observes a fact (an ``EXISTS`` against tables
versus a dict lookup); the composition of facts is owned here. A fact added to
the rule without an observer on either side fails loudly instead of silently
diverging.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from argus.domain.job_scopes import RESEARCH_OPERATION_SCOPE


@dataclass(frozen=True)
class Fact:
    name: str


@dataclass(frozen=True)
class AllOf:
    terms: tuple[Rule, ...]


@dataclass(frozen=True)
class AnyOf:
    terms: tuple[Rule, ...]


Rule = Fact | AllOf | AnyOf

# Only a succeeded row may settle: a research answer is persisted before its
# row flips to succeeded, so an early message never reads as finished work.
# A backtest settles through its completed run and evidence identity; a
# research job, which has no run by design, through the assistant message
# named by execution_metadata.research_result_message_id. The run branch is
# reachable for every scope.
JOB_RESULT_HYDRATEABLE: Rule = AllOf(
    (
        Fact("job_succeeded"),
        AnyOf(
            (
                Fact("run_result_readable"),
                AllOf((Fact("research_scope"), Fact("research_result_message_present"))),
            )
        ),
    )
)


def facts_of(rule: Rule) -> tuple[str, ...]:
    if isinstance(rule, Fact):
        return (rule.name,)
    names: list[str] = []
    for term in rule.terms:
        for name in facts_of(term):
            if name not in names:
                names.append(name)
    return tuple(names)


def evaluate(rule: Rule, observe: Mapping[str, Callable[[], bool]]) -> bool:
    """Evaluate ``rule`` with one observer per fact; short-circuits like SQL."""
    missing = [name for name in facts_of(rule) if name not in observe]
    if missing:
        raise KeyError(f"no observer for facts: {', '.join(missing)}")
    return _evaluate(rule, observe)


def _evaluate(rule: Rule, observe: Mapping[str, Callable[[], bool]]) -> bool:
    if isinstance(rule, Fact):
        return bool(observe[rule.name]())
    if isinstance(rule, AllOf):
        return all(_evaluate(term, observe) for term in rule.terms)
    return any(_evaluate(term, observe) for term in rule.terms)


def render_sql(rule: Rule, leaves: Mapping[str, str], *, indent: str = "    ") -> str:
    """Render ``rule`` as a SQL boolean expression, one leaf expression per fact."""
    missing = [name for name in facts_of(rule) if name not in leaves]
    if missing:
        raise KeyError(f"no SQL leaf for facts: {', '.join(missing)}")
    return _render(rule, leaves, indent)


def _render(rule: Rule, leaves: Mapping[str, str], indent: str) -> str:
    if isinstance(rule, Fact):
        return _reindent(leaves[rule.name], indent)
    joiner = "and" if isinstance(rule, AllOf) else "or"
    inner = indent + "  "
    rendered = [_render(term, leaves, inner) for term in rule.terms]
    body = f"\n{inner}{joiner} ".join(rendered)
    return f"(\n{inner}{body}\n{indent})"


def _reindent(text: str, indent: str) -> str:
    lines = text.strip("\n").splitlines()
    return "\n".join(indent + line if index else line for index, line in enumerate(lines))


# How SQL observes each fact. `j` is the public.backtest_jobs row. Identity
# columns only, never message prose.
SQL_LEAVES: Mapping[str, str] = {
    "job_succeeded": "j.status = 'succeeded'",
    "run_result_readable": """exists (
  select 1
  from public.backtest_runs as r
  join public.evidence_artifacts as e
    on e.source_run_id = r.id
   and e.user_id = r.user_id
   and e.source_conversation_id = r.conversation_id
  where r.id = j.result_run_id
    and r.user_id = j.user_id
    and r.conversation_id = j.conversation_id
    and r.status = 'completed'
    and r.conversation_result_card
      ->> 'evidence_artifact_id' = e.id::text
    and r.conversation_result_card
      ->> 'idea_id' = e.idea_id::text
    and r.conversation_result_card
      ->> 'idea_version_id' = e.idea_version_id::text
)""",
    "research_scope": f"j.operation_scope = '{RESEARCH_OPERATION_SCOPE}'",
    # uuid compared to uuid so the messages primary key is usable; a value
    # that is not a uuid compares to null instead of raising and failing the
    # whole activity batch.
    "research_result_message_present": """exists (
  select 1
  from public.messages as rm
  where rm.user_id = j.user_id
    and rm.conversation_id = j.conversation_id
    and rm.role = 'assistant'
    and rm.id = (
      case
        when (j.execution_metadata ->> 'research_result_message_id')
          ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        then (j.execution_metadata ->> 'research_result_message_id')::uuid
      end
    )
)""",
}

SQL_FUNCTION_NAME = "argus_private.backtest_job_result_hydrateable"
SQL_FUNCTION_SIGNATURE = f"{SQL_FUNCTION_NAME}(public.backtest_jobs)"


def render_sql_function() -> str:
    """The complete DDL for the SQL owner, rendered from the rule."""
    body = render_sql(JOB_RESULT_HYDRATEABLE, SQL_LEAVES, indent="  ")
    return f"""create or replace function {SQL_FUNCTION_NAME}(
  j public.backtest_jobs
)
returns boolean
language sql
stable
parallel safe
security invoker
set search_path = public
as $$
  select {body}
$$;

revoke all on function {SQL_FUNCTION_SIGNATURE} from public, anon, authenticated;
grant usage on schema argus_private to service_role;
grant execute on function {SQL_FUNCTION_SIGNATURE} to service_role;"""
