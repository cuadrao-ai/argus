"""Force-complete one third-party step of an account deletion (Lane 6, operator only).

For a step an operator has decided can never complete: Apple answers
``invalid_request`` because the person already removed the app in their Apple ID
settings, a provider is gone for good, or a token was sealed under a key no
process holds any more (``key_unproven``).

A dry run by default: it prints the step, how long it has waited and why, and
changes nothing. ``--confirm`` acts. Either way it is refused unless the step
has been pending for at least 7 days. With ``--confirm``, an Apple, Plaid or
Gmail step first gets one more revoke attempt, recorded in the run like any
pass; only what is still pending after it is recorded ``operator_forced``, with
the reason and the operator's name in the run record. The run is then resumed
at once so the account delete can finish.

The reason is kept in the run record after the deletion: write what happened
("Apple invalid_request for 7 days, app removed by the person"), never the
person's name, email or any other personal data. There is no route for this.

The ``storage`` step (retained document sources) is not forceable: fix Storage
and the next resume finishes it.
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

STEPS = ("apple", "plaid", "gmail", "analytics")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Force-complete one third-party step of an account deletion.",
    )
    parser.add_argument("--user-id", required=True)
    parser.add_argument(
        "--step",
        required=True,
        choices=STEPS,
        help="storage is not forceable: fix Storage and the next resume finishes it.",
    )
    parser.add_argument(
        "--reason",
        required=True,
        help="1-200 characters, kept in the run record; no personal data.",
    )
    parser.add_argument("--operator", required=True)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Act. Without it this is a dry run that changes nothing.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    from argus.log_sink import configure_logging

    configure_logging()
    parser = _parser()
    args = parser.parse_args(argv)
    if "@" in args.reason:
        parser.error("--reason must not contain an email address")
    try:
        target = resolve_destructive_database_target()
    except DestructiveDatabaseTargetError as exc:
        parser.error(str(exc))
    pin_destructive_database_target(target)
    announce_destructive_database_target(target, stream=sys.stderr)

    import os

    from argus.api.account_deletion_runtime import build_service
    from argus.domain.account_deletion.service import (
        AccountDeletionIncomplete,
        AccountDeletionRejected,
    )
    from argus.domain.supabase_gateway import SupabaseGateway

    service = build_service(
        database_url=os.environ["DATABASE_URL"],
        supabase_client=SupabaseGateway.from_env().client,
    )
    try:
        report = service.force_complete_step(
            user_id=args.user_id,
            step=args.step,
            reason=args.reason,
            operator=args.operator,
            confirm=args.confirm,
        )
    except ValueError as exc:
        parser.error(str(exc))
    except (AccountDeletionRejected, AccountDeletionIncomplete) as exc:
        # Includes step_not_pending and step_pending_under_7_days.
        print(json.dumps({"forced": False, "reason": str(exc)}), flush=True)
        return 1
    if not args.confirm:
        print(json.dumps({**report, "next": "re-run with --confirm to act"}), flush=True)
        return 0
    print(json.dumps(report), flush=True)
    try:
        outcome = service.delete_account(user_id=args.user_id, origin="force")
    except AccountDeletionIncomplete as exc:
        print(
            json.dumps(
                {
                    "forced": report["forced"],
                    "status": "in_progress",
                    "pending": exc.pending,
                }
            ),
            flush=True,
        )
        return 0
    print(json.dumps({"forced": report["forced"], "status": outcome.status}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
