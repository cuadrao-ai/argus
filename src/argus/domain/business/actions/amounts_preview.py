from uuid import uuid4

from argus.domain.business.actions.facts import patched_facts, reviewed_amount_facts
from argus.domain.business.actions.fiscal import reviewed_fiscal_facts
from argus.domain.business.amount_inheritance import (
    inherit_amounts,
    inheritance_overrides,
)
from argus.domain.business.contracts.amounts import AmountsPreview, AmountsPreviewRequest
from argus.domain.business.contracts.dgii import FiscalInput, FiscalReview, PurchaseReview
from argus.domain.business.contracts.facts import (
    BusinessFactPatch,
    BusinessResolution,
    MontosReview,
)
from argus.domain.business.purchase_review import apply_purchase, net_amount
from argus.domain.business.review_flags import review_flags


def preview_amounts(resolution: BusinessResolution, request: AmountsPreviewRequest, *, paid: bool) -> AmountsPreview:
    source_ids = (uuid4(),)  # Preview provenance exists only for this calculation.
    before = resolution.facts
    declaration = inherit_amounts(before, resolution.dgii, resolution.fiscal_overrides, paid=paid)
    overrides = inheritance_overrides(before, declaration, None, resolution.fiscal_overrides, amount_derived=resolution.amount_derived)
    after = before
    if request.amount is not None:
        after = patched_facts(after, BusinessFactPatch(amount=request.amount), source_ids, origin="member_set")
    if request.itbis is not None:
        fiscal = before.fiscal
        after = reviewed_fiscal_facts(after, FiscalReview(
            fiscal=FiscalInput(rnc=fiscal.rnc.value if fiscal else None, ncf=(fiscal.ecf.value or fiscal.ncf.value) if fiscal else None, itbis=request.itbis.value),
            declaration=declaration or apply_purchase(None, PurchaseReview()),
        ), source_ids, "member_set")
    if request.net_amount is not None or request.legal_tip is not None:
        after = reviewed_amount_facts(after, MontosReview(net_amount=request.net_amount, legal_tip=request.legal_tip), source_ids, origin="member_set")
    declaration = inherit_amounts(after, declaration, overrides, paid=paid)
    return AmountsPreview(
        net_amount=net_amount(after, declaration),
        mismatch=next((flag for flag in review_flags(after, declaration=declaration) if flag.code == "amounts_mismatch"), None),
    )
