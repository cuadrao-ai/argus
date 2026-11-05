"""Asset presentation derives from the same observations as account position."""

from dataclasses import asdict
from zoneinfo import ZoneInfo

from argus.domain.recording.accounts import OPTIONAL_ASSET_TYPES
from argus.domain.recording.asset_schemas import (
    AssetChangeResponse,
    AssetEstimate,
    AssetEstimateRevision,
    AssetProjection,
)
from argus.domain.recording.currency import format_minor_units
from argus.domain.recording.loop import CheckRecord, observations, position
from argus.domain.recording.records import OpeningRevision
from argus.domain.recording.repository import StoredAccount


def asset_projection(stored: StoredAccount) -> AssetProjection | None:
    if stored.account.type not in OPTIONAL_ASSET_TYPES:
        return None
    from argus.domain.recording.loop_reads import personal_share

    def revision(r: OpeningRevision | CheckRecord) -> AssetEstimateRevision:
        return AssetEstimateRevision(
            revision=r.revision,
            amount_minor=r.amount_minor,
            amount=format_minor_units(r.amount_minor, stored.account.currency),
            as_of=r.as_of.astimezone(ZoneInfo(r.time_zone)),
            time_zone=r.time_zone,
            estimate_basis=r.estimate_basis,
            reason=r.reason,
            recorded_by=r.recorded_by,
            recorded_at=r.recorded_at,
        )

    estimates = []
    for observation in observations(stored.opening, stored.checks):
        if stored.opening and observation.id == stored.opening.id:
            versions = [revision(r) for r in stored.opening.revisions]
        else:
            check = next(c for c in stored.checks if c.id == observation.id)
            versions = [revision(r) for r in (*check.prior_revisions, check)]
        estimates.append(
            AssetEstimate(
                **versions[-1].model_dump(),
                record_id=observation.id,
                kind="opening" if observation.kind == "opening" else "value_update",
                revisions=versions,
            )
        )
    balance = position(stored.opening, stored.checks, stored.expenses, stored.coverage)
    return AssetProjection(
        personal_position_minor=None
        if balance.amount_minor is None
        else personal_share(balance.amount_minor, stored.account.ownership_share_bps),
        current_estimate=estimates[-1] if estimates else None,
        estimates=estimates,
        related_debt_account_id=stored.related_debt_account_id,
        changes=[
            AssetChangeResponse.model_validate(asdict(c)) for c in stored.asset_changes
        ],
    )
