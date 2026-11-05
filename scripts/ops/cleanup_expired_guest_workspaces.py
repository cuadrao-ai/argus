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
        description="Safely clean expired anonymous guest workspaces.",
    )
    parser.add_argument("--dry-run", action="store_true")
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

    from argus.domain.guest_cleanup import cleanup_expired_guest_workspaces
    from argus.domain.supabase_gateway import SupabaseGateway

    result = cleanup_expired_guest_workspaces(
        SupabaseGateway.from_env(),
        limit=args.limit,
        dry_run=args.dry_run,
    )
    print(json.dumps(result.as_dict(), sort_keys=True))
    # A failed retention purge exits non-zero too: a silent zero is how a
    # retention boundary becomes documentation instead of behavior.
    return 1 if result.auth_delete_failed or result.purge_failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
