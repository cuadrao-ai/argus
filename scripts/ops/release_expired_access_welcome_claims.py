"""Release access-welcome claims stuck past the provider idempotency window."""

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
    return argparse.ArgumentParser(
        description=(
            "Delete unconsumed access-welcome claims older than the release "
            "boundary so a stuck approval becomes retryable."
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    from argus.log_sink import configure_logging

    configure_logging()
    parser = _parser()
    parser.parse_args(argv)
    try:
        target = resolve_destructive_database_target()
    except DestructiveDatabaseTargetError as exc:
        parser.error(str(exc))
    pin_destructive_database_target(target)
    announce_destructive_database_target(target, stream=sys.stderr)

    from argus.domain.supabase_gateway import SupabaseGateway

    gateway = SupabaseGateway.from_env()
    released = gateway.release_expired_private_alpha_access_welcome_claims()
    print(json.dumps({"released_access_welcome_claims": released}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
