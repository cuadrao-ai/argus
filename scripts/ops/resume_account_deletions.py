"""Resume account deletion runs still in flight (Lane 6, operator-run sweep).

A run stays in flight while a third party (Apple, Plaid, Gmail, PostHog) hasn't
confirmed; the account is locked meanwhile and its auth delete waits. This pass
resumes each idle run through the same command the route runs, so the sweep
and a person's own retry can't diverge. A run another pass holds is counted
``busy`` and left alone. It runs inside scheduled_maintenance.py, which an
operator runs (PRIVATE_LAUNCH_RUNBOOK.md has the cadence); nothing schedules it.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

if __package__:
    from scripts.ops.destructive_database_target import (
        DestructiveDatabaseTargetError,
        announce_destructive_database_target,
        pin_destructive_database_target,
        resolve_destructive_database_target,
    )
else:
    from destructive_database_target import (  # type: ignore[no-redef]
        DestructiveDatabaseTargetError,
        announce_destructive_database_target,
        pin_destructive_database_target,
        resolve_destructive_database_target,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resume account deletion runs waiting on a third party.",
    )
    parser.add_argument("--limit", type=int, default=25, choices=range(1, 101))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    from argus.log_sink import configure_logging

    configure_logging()
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        target = resolve_destructive_database_target()
    except DestructiveDatabaseTargetError as exc:
        parser.error(str(exc))
    pin_destructive_database_target(target)
    announce_destructive_database_target(target, stream=sys.stderr)

    import os

    from argus.api.account_deletion_runtime import build_service
    from argus.domain.supabase_gateway import SupabaseGateway

    service = build_service(
        database_url=os.environ["DATABASE_URL"],
        supabase_client=SupabaseGateway.from_env().client,
    )
    result = service.resume_pending(limit=args.limit)
    print(json.dumps(result, sort_keys=True))
    # A run still waiting on a third party is expected, not a failure; a run
    # that raised something else is, so it never looks handled when it isn't.
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
