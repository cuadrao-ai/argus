"""The owner's stored Business receipt-reading setting, for tests that read."""

from __future__ import annotations

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
    return BusinessReceiptConsentStore(pool, lambda: ROUTE)


def turn_reading(
    setting: BusinessReceiptConsentStore, space_id: str, owner: str, enabled: bool = True
) -> None:
    shown = setting.status(space_id, owner)
    setting.set(
        space_id,
        owner,
        enabled=enabled,
        version=SCOPE_VERSION,
        disclosure_token=shown["disclosure_token"],
    )
