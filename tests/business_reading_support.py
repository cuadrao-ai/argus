"""The owner's stored Business receipt-reading setting, for tests that read."""

from __future__ import annotations

from argus.domain.business.access import InMemoryAccessStore
from argus.domain.business.receipt_consent import (
    SCOPE_VERSION,
    BusinessReceiptConsentStore,
)

ROUTE = {
    "gateway": "fixture",
    "interpretation": [{"model": "fixture-reader"}],
    "reply": [],
}


def reading_setting(pool=None) -> BusinessReceiptConsentStore:  # noqa: ANN001
    if pool is not None:
        return BusinessReceiptConsentStore(pool, lambda: ROUTE)
    access = InMemoryAccessStore()
    return BusinessReceiptConsentStore(
        route_resolver=lambda: ROUTE, access_resolver=lambda: access
    )


def turn_reading(
    setting: BusinessReceiptConsentStore, space_id: str, owner: str, enabled: bool = True
) -> None:
    if setting.pool is None:
        setting.access_resolver().ensure_owner_grant(space_id, owner)
    shown = setting.status(space_id, owner)
    setting.set(
        space_id,
        owner,
        enabled=enabled,
        version=SCOPE_VERSION,
        disclosure_token=shown["disclosure_token"],
    )
