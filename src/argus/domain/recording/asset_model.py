"""Accepted non-money ownership and debt-reference changes."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AssetChange:
    version: int
    previous_share_bps: int
    ownership_share_bps: int
    previous_debt_account_id: str | None
    related_debt_account_id: str | None
    recorded_by: str
    recorded_at: datetime
    idempotency_key: str
    identity_hash: str
