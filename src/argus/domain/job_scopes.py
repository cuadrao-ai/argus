"""The one owner of every ``backtest_jobs.operation_scope`` value.

A scope is a fact three parties must agree on: the writer that stamps it on a
row, the readers that branch on it, and the database check that admits it.
They agree because every one of them derives from this tuple. The SQL check
constraint is rendered from it by :func:`render_scope_check_constraint`, and
the migration that installs the active constraint is pinned to that rendering;
a scope added here without a migration fails that test, and a scope added to
SQL by hand fails it too. ``tests/test_backtest_job_scopes.py`` walks every
production Python file and fails on a scope spelled anywhere but here, so a
consumer cannot quietly hold its own copy.

Which scopes may be *admitted* through the API is a different fact, owned by
the admission SQL, and is not restated here.
"""

from __future__ import annotations

# A chat run confirmed from a card; the only scope a conversation projects as
# a backtest result.
CHAT_RUN_SCOPE = "chat.run_backtest"
# A direct ``POST /backtests/run``; may carry no conversation.
DIRECT_RUN_SCOPE = "backtests.run"
# A thorough research run; settles through its answer message, never a run.
RESEARCH_OPERATION_SCOPE = "chat.research"
# The Render workflow runtime proof seeded by the canary; not conversation
# work, so it carries no conversation and no activity reader can project it.
PROOF_OPERATION_SCOPE = "workflows.proof"

OPERATION_SCOPES: tuple[str, ...] = (
    CHAT_RUN_SCOPE,
    DIRECT_RUN_SCOPE,
    RESEARCH_OPERATION_SCOPE,
    PROOF_OPERATION_SCOPE,
)

SCOPE_CHECK_CONSTRAINT_NAME = "backtest_jobs_operation_scope_check"


def render_scope_check_constraint() -> str:
    """The DDL that installs the check constraint for exactly these scopes."""
    values = ",\n".join(f"                '{scope}'" for scope in OPERATION_SCOPES)
    return f"""alter table public.backtest_jobs
    drop constraint if exists {SCOPE_CHECK_CONSTRAINT_NAME};

alter table public.backtest_jobs
    add constraint {SCOPE_CHECK_CONSTRAINT_NAME}
        check (
            operation_scope in (
{values}
            )
        );"""
