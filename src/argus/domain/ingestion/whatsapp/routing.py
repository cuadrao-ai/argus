"""Choose a destination using only the fiscal identities the sender can reach."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from argus.domain.business.fiscal_identity import normalized_taxpayer_id
from argus.domain.owner_scope import BusinessSpace

if TYPE_CHECKING:
    from argus.domain.ingestion.whatsapp.held import Reason


def route_document(
    eligible: Mapping[str, str], *, issuer: str | None, buyer: str | None
) -> BusinessSpace | Reason:
    """A single eligible space receives even unread files. Otherwise match the read."""
    if not eligible:
        return "no_eligible_business"
    if len(eligible) == 1:
        return BusinessSpace(next(iter(eligible)))

    buyer_id = normalized_taxpayer_id(buyer)
    parties = {normalized_taxpayer_id(issuer), buyer_id} - {None}
    matches = [
        BusinessSpace(space_id)
        for space_id, tax_id in eligible.items()
        if normalized_taxpayer_id(tax_id) in parties
    ]
    if len(matches) == 1:
        return matches[0]
    if matches:
        return "two_matches"
    return "no_match" if buyer_id else "no_buyer_rnc"
