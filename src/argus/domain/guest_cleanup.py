from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Protocol

from loguru import logger


class GuestCleanupGateway(Protocol):
    def claim_expired_guest_workspaces(
        self,
        *,
        limit: int,
        dry_run: bool,
    ) -> list[dict[str, object]]: ...

    def purge_expired_visitor_usage(self, *, before: datetime | None = None) -> int: ...

    def purge_expired_guest_funnel_milestones(
        self,
        *,
        before: datetime | None = None,
    ) -> int: ...


@dataclass(frozen=True)
class GuestCleanupResult:
    dry_run: bool
    selected: int
    auth_deleted: int
    auth_preserved: int
    auth_delete_failed: int
    visitor_usage_purged: int = 0
    funnel_milestones_purged: int = 0
    purge_failed: int = 0

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


# The registry IS the wiring: this job purges exactly what is listed here, so a
# retention function that is not registered is not enforced anywhere. A boundary
# written only into SQL and docs is documentation, not behavior, and leaves
# IP-derived visitor digests stored forever.
EXPIRING_DATA_PURGES: tuple[tuple[str, str], ...] = (
    ("visitor_usage_purged", "purge_expired_visitor_usage"),
    ("funnel_milestones_purged", "purge_expired_guest_funnel_milestones"),
)


def purge_expired_visitor_data(
    gateway: GuestCleanupGateway,
    *,
    before: datetime | None = None,
) -> dict[str, int]:
    """Purge counts per table, plus how many purges failed.

    A failure is counted and logged rather than raised: retention must not
    abort workspace deletion. It is never silent, because the count reaches the
    operator's output and the job's exit code.
    """
    counts: dict[str, int] = {field_name: 0 for field_name, _ in EXPIRING_DATA_PURGES}
    counts["purge_failed"] = 0
    for field_name, method_name in EXPIRING_DATA_PURGES:
        try:
            counts[field_name] = int(getattr(gateway, method_name)(before=before))
        except Exception:
            counts["purge_failed"] += 1
            logger.opt(exception=True).warning(
                "Expired guest visitor data purge failed",
                purge=method_name,
            )
    return counts


def cleanup_expired_guest_workspaces(
    gateway: GuestCleanupGateway,
    *,
    limit: int,
    dry_run: bool,
) -> GuestCleanupResult:
    if limit < 1 or limit > 100:
        raise ValueError("cleanup limit must be between 1 and 100")
    candidates = gateway.claim_expired_guest_workspaces(
        limit=limit,
        dry_run=dry_run,
    )
    if dry_run:
        return GuestCleanupResult(
            dry_run=True,
            selected=len(candidates),
            auth_deleted=0,
            auth_preserved=0,
            auth_delete_failed=0,
        )

    deleted = 0
    preserved = 0
    failed = 0
    for candidate in candidates:
        user_id = str(candidate.get("user_id") or "")
        if not user_id:
            failed += 1
        elif candidate.get("auth_deleted") is True:
            deleted += 1
        else:
            preserved += 1
    purged = purge_expired_visitor_data(gateway)
    return GuestCleanupResult(
        dry_run=False,
        selected=len(candidates),
        auth_deleted=deleted,
        auth_preserved=preserved,
        auth_delete_failed=failed,
        visitor_usage_purged=purged["visitor_usage_purged"],
        funnel_milestones_purged=purged["funnel_milestones_purged"],
        purge_failed=purged["purge_failed"],
    )
